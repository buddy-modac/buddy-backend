"""
Verifier + adversarial critic.

This is the most directly borrowed idea from Sim Francisco. There, before any
milestone was "done", an independent **verifier** re-ran validation and an
**adversarial critic** tried to *prove the gain was spurious* — overfit, model-
knowledge leakage, or weight-gaming. Completion gated on both (README §"The four
loops"; NOTES.md "Principles (load-bearing, for the adversarial critic)").

We port both roles to the character domain:

  * **Verifier** re-scores a reply independently (via rubric.score_reply) and
    checks it clears the gate. It is the "does it pass on the metric" half.

  * **AdversarialCritic** assumes the reply is *cheating* and looks for proof:
      - LEAKAGE: verbatim reproduction of source dialogue (copyright + "it only
        passes because it parroted canon"). Analogue of Sim Francisco's leakage
        rule ("never add post-cutoff info"; here: never reproduce canon lines).
      - STEREOTYPE: the reply leans on generic tropes for the archetype rather
        than reasoning from THIS character's specific vector. Analogue of the
        "anti-stereotype" failure in NOTES.md iter 0.
      - PERSONA BREAK: assistant-voice / out-of-character tells.
      - VECTOR DRIFT: the reply's implied tone contradicts a strong axis.

A reply is accepted only if the verifier passes AND the critic finds no fatal
objection — exactly the two-gate completion rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .persona import CharacterProfile
from .rubric import score_reply, ReplyScore, REPLY_CUES
from .vector import AXIS_KEYS
from .korean import stem_tokens, has_hangul


@dataclass
class Objection:
    kind: str           # "leakage" | "stereotype" | "persona_break" | "vector_drift"
    severity: str       # "fatal" | "warn"
    detail: str


# --- Leakage policy ----------------------------------------------------------
# Why this is a *policy* and not a fixed rule: detecting verbatim canon
# reproduction trades off two goods that genuinely conflict.
#
#   * Copyright safety  — reproducing source dialogue is a copyright concern,
#     and (in the Sim Francisco sense) "leakage": the model parroted an answer
#     instead of reasoning it out, so a pass is not evidence the engine works.
#   * Character fidelity — what makes a character feel most like themselves is
#     often their signature lines. Blocking every canon overlap can flatten the
#     character.
#
# There is no single correct setting; it depends on use. So the severity
# (fatal / warn / off) and the word-overlap threshold are caller-chosen.
#
#   threshold : minimum shared contiguous word run that counts as leakage.
#               Higher => only longer copied spans trip it (more fidelity).
#   severity  : "fatal" rejects the reply; "warn" flags but allows;
#               "off" disables leakage detection entirely.

@dataclass
class LeakagePolicy:
    threshold: int = 6
    severity: str = "fatal"     # "fatal" | "warn" | "off"
    # Korean comparison runs on morpheme STEMS (particles/endings stripped), so
    # an equivalent copied span yields a shorter run than English words. A
    # separate, lower threshold keeps Korean detection as sensitive as English.
    # If None, falls back to `threshold`.
    threshold_ko: Optional[int] = 4


# Presets for common stances. (threshold_ko keeps Korean as sensitive as English.)
LEAKAGE_STRICT = LeakagePolicy(threshold=5, threshold_ko=3, severity="fatal")   # public/commercial
LEAKAGE_BALANCED = LeakagePolicy(threshold=6, threshold_ko=4, severity="fatal") # default
LEAKAGE_LENIENT = LeakagePolicy(threshold=10, threshold_ko=7, severity="warn")  # private fan use
LEAKAGE_OFF = LeakagePolicy(threshold=6, threshold_ko=4, severity="off")        # disabled


@dataclass
class CritiqueResult:
    accepted: bool
    score: ReplyScore
    objections: List[Objection] = field(default_factory=list)

    def fatal(self) -> List[Objection]:
        return [o for o in self.objections if o.severity == "fatal"]

    def summary(self) -> str:
        if self.accepted:
            return f"ACCEPTED (headline={self.score.headline:.2f})"
        reasons = "; ".join(f"{o.kind}:{o.detail}" for o in self.fatal())
        return f"REJECTED (headline={self.score.headline:.2f}) — {reasons}"


# --- Verifier ---------------------------------------------------------------

class Verifier:
    """Independent re-scorer. The 'passes the metric' gate.

    Pass `judge_client` (a ModelClient) to enable the optional LLM judge inside
    scoring; without it, scoring stays keyword-only and offline.
    """
    def __init__(self, gate: float = 0.70, judge_client=None, llm_blend: float = 0.6):
        self.gate = gate
        self.judge_client = judge_client
        self.llm_blend = llm_blend

    def check(self, reply: str, profile: CharacterProfile,
              user_prompt: str = "") -> ReplyScore:
        return score_reply(reply, profile, user_prompt,
                           judge_client=self.judge_client, llm_blend=self.llm_blend)


# --- Adversarial critic ------------------------------------------------------

_ASSISTANT_TELLS = ["as an ai", "i'm an ai", "language model", "i cannot help",
                    "i can't help", "어시스턴트", "인공지능", "ai로서", "도와드릴게요",
                    "제가 도와"]

# Generic tropes that, if they dominate a reply with no specific grounding,
# suggest stereotype-reasoning rather than character-reasoning.
_GENERIC_TROPES = ["as a villain", "being evil", "i am dangerous", "fear me",
                   "i am the strongest", "악역답게", "나는 악당", "두려워해라"]


class AdversarialCritic:
    """Assumes the reply is cheating and tries to prove it."""

    def __init__(self, leakage_ngram: Optional[int] = None,
                 leakage_policy: Optional[LeakagePolicy] = None):
        # leakage_policy takes precedence; leakage_ngram kept for back-compat
        if leakage_policy is not None:
            self.leakage_policy = leakage_policy
        elif leakage_ngram is not None:
            self.leakage_policy = LeakagePolicy(threshold=leakage_ngram, severity="fatal")
        else:
            self.leakage_policy = LEAKAGE_BALANCED
        # exposed for back-compat / inspection
        self.leakage_ngram = self.leakage_policy.threshold

    def critique(
        self,
        reply: str,
        profile: CharacterProfile,
        canon_lines: Optional[List[str]] = None,
        user_prompt: str = "",
    ) -> List[Objection]:
        objs: List[Objection] = []
        low = reply.lower()

        # 1) LEAKAGE — verbatim canon reproduction (policy-controlled)
        if canon_lines and self.leakage_policy.severity != "off":
            leak = self._find_leakage(reply, canon_lines)
            if leak:
                objs.append(Objection(
                    "leakage", self.leakage_policy.severity,
                    f"overlaps canon line by {leak}-word span"))

        # 2) PERSONA BREAK — assistant voice / out of character
        for tell in _ASSISTANT_TELLS:
            if tell in low:
                objs.append(Objection(
                    "persona_break", "fatal", f"assistant tell: '{tell}'"))
                break

        # 3) STEREOTYPE — leans on generic tropes, ignores specific saliences
        trope_hits = [t for t in _GENERIC_TROPES if t in low]
        engages_salience = any(
            any(w in low for w in topic.lower().split())
            for topic, _ in profile.vector.top_saliences(3))
        if trope_hits and not engages_salience:
            objs.append(Objection(
                "stereotype", "warn",
                f"generic trope {trope_hits} with no specific grounding"))

        # 4) VECTOR DRIFT — reply tone contradicts a strong axis
        drift = self._vector_drift(reply, profile)
        for d in drift:
            objs.append(d)

        return objs

    def _find_leakage(self, reply: str, canon_lines: List[str]) -> Optional[int]:
        """Return the length of the longest shared token n-gram >= threshold.

        Tokens are morpheme stems for Korean (so 도망가자 / 도망갔어 match) and
        lowercased words for other languages (unchanged). Korean uses the
        policy's `threshold_ko` since stem runs are shorter than English word
        runs for an equivalent copied span. See korean.stem_tokens.
        """
        # pick threshold by whether canon/reply are Korean
        korean = has_hangul(reply) or any(has_hangul(c) for c in canon_lines)
        if korean and self.leakage_policy.threshold_ko is not None:
            threshold = self.leakage_policy.threshold_ko
        else:
            threshold = self.leakage_policy.threshold

        r_words = stem_tokens(reply)
        best = 0
        for line in canon_lines:
            c_words = stem_tokens(line)
            best = max(best, _longest_common_ngram(r_words, c_words))
        return best if best >= threshold else None

    def _vector_drift(self, reply: str, profile: CharacterProfile) -> List[Objection]:
        objs = []
        low = reply.lower()
        for key in AXIS_KEYS:
            v = getattr(profile.vector, key)
            if abs(v) < 0.6:   # only police *strong* leans
                continue
            pos = sum(low.count(c.lower()) for c in REPLY_CUES[key]["pos"])
            neg = sum(low.count(c.lower()) for c in REPLY_CUES[key]["neg"])
            if pos + neg == 0:
                continue
            lean = (pos - neg) / (pos + neg)
            # strong positive axis but reply leans clearly negative (or vice versa)
            if v > 0.6 and lean < -0.5:
                objs.append(Objection("vector_drift", "warn",
                            f"axis '{key}' is +{v:.2f} but reply leans negative"))
            elif v < -0.6 and lean > 0.5:
                objs.append(Objection("vector_drift", "warn",
                            f"axis '{key}' is {v:.2f} but reply leans positive"))
        return objs


def _longest_common_ngram(a: List[str], b: List[str]) -> int:
    """Length of the longest contiguous shared token run between a and b."""
    if not a or not b:
        return 0
    # classic DP for longest common substring over token lists
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


# --- Two-gate completion -----------------------------------------------------

def review(
    reply: str,
    profile: CharacterProfile,
    verifier: Optional[Verifier] = None,
    critic: Optional[AdversarialCritic] = None,
    canon_lines: Optional[List[str]] = None,
    user_prompt: str = "",
    gate: float = 0.70,
) -> CritiqueResult:
    """Run both gates. Accept only if verifier passes AND no fatal objection.

    Mirrors Sim Francisco: "Completion gates on both [verifier and critic]."
    """
    verifier = verifier or Verifier(gate=gate)
    critic = critic or AdversarialCritic()

    score = verifier.check(reply, profile, user_prompt)
    objs = critic.critique(reply, profile, canon_lines, user_prompt)

    has_fatal = any(o.severity == "fatal" for o in objs)
    accepted = score.passed(gate) and not has_fatal
    return CritiqueResult(accepted=accepted, score=score, objections=objs)
