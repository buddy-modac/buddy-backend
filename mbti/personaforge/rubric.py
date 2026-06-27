"""
Rubric scoring — the machine-checkable "done".

Analogue of Sim Francisco's `rubric.rs` + `validate.rs`. There, a run was graded
by comparing predictions against frozen public ground truth (election results,
resolved markets) and the build only passed if the weighted score cleared a gate.

For a character chatbot there is no election to compare against, so the "ground
truth" becomes the *value vector itself*: a reply is good if it is consistent with
the personality the vector encodes. We score three things, each in [0,1]:

  * axis_consistency  — does the reply's tone match the character's axes?
  * salience_coverage — does the reply engage the character's pet topics when relevant?
  * voice_fidelity    — does the reply read like the character's speech style?

The weighted headline must clear `gate` (default 0.70, same spirit as Sim Francisco's
0.70 gate). Targets (the vector) are *frozen* during evaluation — only prompts /
persona generation may be tuned, exactly the Sim Francisco rule: "Tuning may only
touch persona generation, prompts, aggregation … never rubric targets."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .vector import ValueVector, AXIS_KEYS
from .persona import CharacterProfile


# Lexical cues that signal each axis pole *in a generated reply*. Distinct from
# collect.CUES (which scans descriptions); these scan first-person dialogue.
REPLY_CUES: Dict[str, Dict[str, List[str]]] = {
    "danger":  {"pos": ["kill", "destroy", "blood", "explode", "weapon", "hurt",
                        "죽", "터트", "폭발", "피", "위협", "없애"],
                "neg": ["safe", "gentle", "calm", "괜찮", "다정", "조심"]},
    "manip":   {"pos": ["trust me", "believe me", "secret", "promise", "믿어", "약속",
                        "비밀", "사실은"],
                "neg": ["honestly", "truth", "솔직", "진심", "정말로"]},
    "freedom": {"pos": ["escape", "run away", "free", "leave", "도망", "자유", "떠나",
                        "벗어"],
                "neg": ["stay", "duty", "must", "남", "임무", "해야"]},
    "impulse": {"pos": ["now", "!", "지금", "당장", "그냥"],
                "neg": ["wait", "think", "plan", "기다", "생각", "천천"]},
    "warmth":  {"pos": ["love", "care", "together", "사랑", "함께", "걱정", "좋아"],
                "neg": ["alone", "whatever", "don't care", "혼자", "상관없", "마음대로"]},
}


@dataclass
class ReplyScore:
    axis_consistency: float
    salience_coverage: float
    voice_fidelity: float
    headline: float
    detail: Dict[str, float] = field(default_factory=dict)
    # optional LLM judge score (None if keyword-only)
    llm_score: Optional[float] = None        # 0..1 holistic in-character score
    llm_notes: str = ""                       # short rationale from the judge

    def passed(self, gate: float = 0.70) -> bool:
        return self.headline >= gate


def _axis_consistency(reply: str, vec: ValueVector) -> float:
    """For each axis with a strong lean (|v|>0.33), reward replies whose cue
    balance points the same way; ignore near-zero axes (no expectation)."""
    low = reply.lower()
    scored = []
    for key in AXIS_KEYS:
        v = getattr(vec, key)
        if abs(v) <= 0.33:
            continue  # no strong expectation on this axis
        pos = sum(low.count(c.lower()) for c in REPLY_CUES[key]["pos"])
        neg = sum(low.count(c.lower()) for c in REPLY_CUES[key]["neg"])
        total = pos + neg
        if total == 0:
            scored.append(0.5)      # neutral: neither confirms nor violates
            continue
        lean = (pos - neg) / total  # -1..1
        # agreement: +1 if lean matches sign of v, -1 if opposite
        agree = lean if v > 0 else -lean
        scored.append((agree + 1) / 2)  # map to 0..1
    if not scored:
        return 0.5
    return sum(scored) / len(scored)


def _salience_coverage(reply: str, vec: ValueVector, prompt: str) -> float:
    """If the user prompt touches one of the character's salient topics, reward a
    reply that engages it. If no salient topic is in play, return neutral 1.0
    (nothing to cover)."""
    low_reply = reply.lower()
    low_prompt = prompt.lower()
    top = [t for t, _ in vec.top_saliences(3)]
    if not top:
        return 1.0
    relevant = [t for t in top if any(w in low_prompt for w in t.lower().split())]
    if not relevant:
        return 1.0
    hit = sum(1 for t in relevant
              if any(w in low_reply for w in t.lower().split()))
    return hit / len(relevant)


def _voice_fidelity(reply: str, profile: CharacterProfile) -> float:
    """Cheap proxy for 'sounds like the character': reply length in the expected
    band (short, dialogue-first) and not obviously assistant-like."""
    n_words = len(re.findall(r"\w+", reply))
    length_ok = 1.0 if 1 <= n_words <= 60 else (0.5 if n_words <= 90 else 0.2)
    assistant_tells = ["as an ai", "i'm an ai", "language model", "i cannot",
                       "도와드릴", "어시스턴트", "인공지능", "ai로서"]
    penalty = 0.0
    low = reply.lower()
    for t in assistant_tells:
        if t in low:
            penalty = 0.6
            break
    return max(0.0, length_ok - penalty)


DEFAULT_WEIGHTS = {"axis": 0.5, "salience": 0.2, "voice": 0.3}

# When an LLM judge is used, blend its holistic score with the keyword headline.
# The keyword score is cheap and stable; the LLM score is richer but variable.
# Default leans on the LLM (0.6) once it is available.
DEFAULT_LLM_BLEND = 0.6


def score_reply(
    reply: str,
    profile: CharacterProfile,
    user_prompt: str = "",
    weights: Optional[Dict[str, float]] = None,
    judge_client=None,
    llm_blend: float = DEFAULT_LLM_BLEND,
) -> ReplyScore:
    """Score a reply for in-character fidelity.

    Stage 1 (always): transparent keyword scoring — axis/salience/voice.
    Stage 2 (optional): pass `judge_client` (a ModelClient) to also get a holistic
    0..1 score from an LLM judge, blended into the headline by `llm_blend`.
    The keyword path runs offline with no deps, so default behaviour is unchanged.
    """
    w = weights or DEFAULT_WEIGHTS
    ac = _axis_consistency(reply, profile.vector)
    sc = _salience_coverage(reply, profile.vector, user_prompt)
    vf = _voice_fidelity(reply, profile)
    kw_headline = w["axis"] * ac + w["salience"] * sc + w["voice"] * vf

    score = ReplyScore(
        axis_consistency=ac,
        salience_coverage=sc,
        voice_fidelity=vf,
        headline=kw_headline,
        detail={"weights": w, "keyword_headline": kw_headline},
    )

    if judge_client is not None:
        llm_s, notes = _llm_judge(reply, profile, user_prompt, judge_client)
        if llm_s is not None:
            score.llm_score = llm_s
            score.llm_notes = notes
            score.headline = (1 - llm_blend) * kw_headline + llm_blend * llm_s
            score.detail["llm_blend"] = llm_blend

    return score


_JUDGE_SYSTEM = (
    "You are a strict acting coach judging whether a single reply stays true to a "
    "character. You are given the character's persona and the reply. Score how "
    "in-character the reply is from 0.0 (breaks character / generic / wrong tone) "
    "to 1.0 (unmistakably this character). Consider personality, motives, and "
    "voice; ignore length. Reply with ONLY JSON: "
    '{"score": 0.0-1.0, "notes": "short reason"}'
)


def _llm_judge(reply: str, profile: CharacterProfile, user_prompt: str, client):
    """Ask an LLM judge for a holistic in-character score. Returns (score, notes)
    or (None, "") on any failure — so a judge outage never breaks scoring."""
    from .model import Message, extract_json
    prompt = (f"Persona:\n{profile.persona_prose}\n\n"
              f"User said: {user_prompt or '(opening)'}\n"
              f"Character reply: {reply}\n\n"
              f"How in-character is the reply?")
    try:
        raw = client.complete(_JUDGE_SYSTEM, [Message("user", prompt)], max_tokens=200)
        data = extract_json(raw)
        s = float(data.get("score"))
        s = max(0.0, min(1.0, s))
        return s, str(data.get("notes", ""))[:200]
    except Exception:
        return None, ""
