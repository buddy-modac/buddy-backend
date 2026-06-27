"""
Blind identification — does the persona actually read as itself?

The hard question we never answered: is an "INTJ" persona actually INTJ, and is a
"Reze" persona actually Reze? Until now nothing measured that. This module does,
in the spirit of Sim Francisco's leakage-free backtest:

  1. Have the persona answer some neutral prompts (generation).
  2. Show ONLY those answers — never the label — to a fresh LLM judge.
  3. Ask the judge to identify the persona (which MBTI type? which character from
     this candidate list?).
  4. If the judge recovers the intended identity, the persona carries its signal.

This is a backtest, not a vibe check: the judge sees no label, so a correct guess
means the personality genuinely came through in the words. A wrong guess is
diagnostic — the judge's actual guess tells you what the persona reads as instead
(e.g. an "INTJ" that keeps reading as INTP means the T/structure axis is weak).

Two identification modes:
  * MBTI  : recover the 4-letter type, scored per-axis (4 binary letters).
  * CHARACTER : pick the right name from a candidate list (multiple choice).

All model calls go through the standard ModelClient, so caching / offline /
scripted backends apply, and the whole thing is testable without a network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .persona import CharacterProfile, build_system_prompt
from .model import ModelClient, Message, extract_json
from .engine import ChatEngine


# Neutral probes: open-ended, not leading toward any type/character. The persona
# must reveal itself through HOW it answers, not because the question asks it to.
DEFAULT_PROBES = [
    "What do you do with a completely free afternoon?",
    "A friend asks for advice on a big decision. How do you respond?",
    "What bothers you most about how other people behave?",
    "Describe how you'd plan a trip.",
]


@dataclass
class IdentificationResult:
    intended: str                       # the true label
    guess: str                          # the judge's identification
    correct: bool
    score: float                        # 1.0 correct; for MBTI, partial per-letter
    detail: str = ""                    # judge's rationale (short)
    answers: List[str] = field(default_factory=list)   # the answers shown to the judge

    def summary(self) -> str:
        verdict = "✓" if self.correct else "✗"
        return (f"{verdict} intended={self.intended} guess={self.guess} "
                f"score={self.score:.2f}"
                + (f" — {self.detail}" if self.detail else ""))


def _collect_answers(profile: CharacterProfile, client: ModelClient,
                     probes: List[str], language: str = "English",
                     max_tokens: int = 200) -> List[str]:
    """Generate the persona's answers to neutral probes (no self-correction loop
    needed here; we want the raw voice)."""
    answers = []
    for probe in probes:
        system = build_system_prompt(profile, language=language)
        reply = client.complete(system, [Message("user", probe)], max_tokens=max_tokens)
        answers.append(reply)
    return answers


# --- MBTI identification -----------------------------------------------------

_MBTI_JUDGE_SYSTEM = (
    "You are an expert at typing personalities. You'll see several answers written "
    "by one person. Infer their MBTI type. Consider energy (E/I), information "
    "(S/N), decisions (T/F), structure (J/P). Reply ONLY as JSON: "
    '{"type": "XXXX", "reason": "short"}'
)


def identify_mbti(
    profile: CharacterProfile,
    client: ModelClient,
    judge_client: Optional[ModelClient] = None,
    probes: Optional[List[str]] = None,
    language: str = "English",
) -> IdentificationResult:
    """Generate answers as the persona, then have a judge recover the MBTI type.

    Scored per-letter (4 letters): 1.0 = all four recovered, 0.75 = three, etc.
    `correct` means an exact 4-letter match.
    """
    if profile.mbti is None:
        raise ValueError("identify_mbti requires an MBTI persona (build_mbti)")
    judge_client = judge_client or client
    probes = probes or DEFAULT_PROBES

    # intended 4-letter type from the persona's axes
    v = profile.mbti
    intended = (("I" if v.EI > 0 else "E") + ("N" if v.SN > 0 else "S")
                + ("F" if v.TF > 0 else "T") + ("P" if v.JP > 0 else "J"))

    answers = _collect_answers(profile, client, probes, language)
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(probes, answers))
    try:
        raw = judge_client.complete(_MBTI_JUDGE_SYSTEM,
                                    [Message("user", listing)], max_tokens=150)
        data = extract_json(raw)
        guess = str(data.get("type", "")).strip().upper()[:4]
        reason = str(data.get("reason", ""))[:200]
    except Exception:
        guess, reason = "", "judge failed"

    # per-letter score
    matches = sum(1 for a, b in zip(intended, guess) if a == b) if len(guess) == 4 else 0
    score = matches / 4.0
    return IdentificationResult(
        intended=intended, guess=guess or "?", correct=(guess == intended),
        score=score, detail=reason, answers=answers)


# --- Character identification (multiple choice) ------------------------------

_CHAR_JUDGE_SYSTEM = (
    "You'll see several answers written by one fictional character, plus a list of "
    "candidate characters. Pick which candidate wrote them. Reply ONLY as JSON: "
    '{"name": "<one of the candidates>", "reason": "short"}'
)


def identify_character(
    profile: CharacterProfile,
    candidates: List[str],
    client: ModelClient,
    judge_client: Optional[ModelClient] = None,
    probes: Optional[List[str]] = None,
    language: str = "English",
) -> IdentificationResult:
    """Generate answers as the character, then have a judge pick it from a list.

    `candidates` must include the true name. Score is 1.0 if matched else 0.0.
    """
    judge_client = judge_client or client
    probes = probes or DEFAULT_PROBES
    intended = profile.name

    if intended not in candidates:
        candidates = [intended] + list(candidates)

    answers = _collect_answers(profile, client, probes, language)
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(probes, answers))
    prompt = f"Candidates: {', '.join(candidates)}\n\nAnswers:\n{listing}"
    try:
        raw = judge_client.complete(_CHAR_JUDGE_SYSTEM,
                                    [Message("user", prompt)], max_tokens=150)
        data = extract_json(raw)
        guess = str(data.get("name", "")).strip()
        reason = str(data.get("reason", ""))[:200]
    except Exception:
        guess, reason = "", "judge failed"

    correct = guess.lower() == intended.lower()
    return IdentificationResult(
        intended=intended, guess=guess or "?", correct=correct,
        score=1.0 if correct else 0.0, detail=reason, answers=answers)


# --- batch evaluation --------------------------------------------------------

@dataclass
class IdentificationReport:
    results: List[IdentificationResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.correct for r in self.results) / len(self.results)

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def summary(self) -> str:
        lines = [f"Identification report — {len(self.results)} persona(s)",
                 f"  exact accuracy: {self.accuracy:.0%}",
                 f"  mean score:     {self.mean_score:.2f}"]
        for r in self.results:
            lines.append("  " + r.summary())
        return "\n".join(lines)


def evaluate_mbti_types(
    types: List[str],
    client: ModelClient,
    judge_client: Optional[ModelClient] = None,
    builder=None,
) -> IdentificationReport:
    """Build each MBTI type, run blind identification, aggregate accuracy.

    `builder` defaults to build_mbti; injectable for tests.
    """
    from .mbti import build_mbti
    builder = builder or build_mbti
    report = IdentificationReport()
    for t in types:
        prof = builder(t)
        report.results.append(identify_mbti(prof, client, judge_client))
    return report
