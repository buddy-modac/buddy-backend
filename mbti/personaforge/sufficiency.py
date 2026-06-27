"""
Evidence sufficiency gate.

Sim Francisco never polled a population it could not stand behind: a run had to
clear `validate` before its numbers counted. The character analogue is: *do we
have enough evidence about this character to build a persona we can stand behind?*
A near-zero vector inferred from two thin sentences is not "a calm, neutral
character" — it is "we don't know this character", and the two must not look the
same.

`assess_sufficiency` scores the collected evidence on five independent axes and
returns a verdict. The gate is deliberately multi-dimensional (not one magic
number) because evidence can fail in different ways:

  * volume      — too few usable snippets to characterise anyone
  * diversity   — everything came from a single source (echo / bias risk)
  * coverage    — how many of the 5 personality axes have ANY supporting cue
  * signal      — total cue strength; thin signal => the vector is mostly guesswork
  * conflict    — axes where pos and neg cues are evenly split (direction unknown)

The headline verdict is `sufficient` (bool) plus a 0-1 `confidence` and a list of
human-readable reasons, so the caller can hard-stop, warn, or ask for more URLs —
exactly the "diagnose -> fix" posture of the Sim Francisco hillclimb loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .vector import ValueVector, AXIS_KEYS
from .collect import CUES, CollectionResult


# Thresholds. These are visible and tunable (the adversarial critic is allowed to
# inspect them), mirroring Sim Francisco's stance that the gate must be a
# transparent rule, not a hidden fudge factor.
@dataclass
class SufficiencyThresholds:
    min_snippets: int = 5          # below this, we simply don't have enough text
    min_sources: int = 2           # single-source evidence is an echo-chamber risk
    min_axes_covered: int = 3      # at least 3 of 5 axes should have some cue
    min_total_signal: int = 8      # total cue hits across all axes
    max_conflict_axes: int = 2     # axes with ambiguous (~50/50) direction
    conflict_band: float = 0.25    # |pos-neg|/(pos+neg) below this == "conflicted"


@dataclass
class SufficiencyReport:
    sufficient: bool
    confidence: float                       # 0..1 overall
    n_snippets: int
    n_sources: int
    axes_covered: List[str]
    axes_missing: List[str]
    conflicted_axes: List[str]
    total_signal: int
    reasons: List[str] = field(default_factory=list)
    subscores: Dict[str, float] = field(default_factory=dict)
    # --- optional second-stage LLM verdict (None if not run) ---
    llm_checked: bool = False
    llm_can_portray: Optional[bool] = None    # LLM's yes/no on "can you act this character?"
    llm_confidence: Optional[float] = None    # 0..1 self-reported
    llm_gaps: List[str] = field(default_factory=list)   # what the LLM says is missing

    def summary(self) -> str:
        verdict = "SUFFICIENT" if self.sufficient else "INSUFFICIENT"
        base = (f"{verdict} (confidence={self.confidence:.2f}) — "
                f"{self.n_snippets} snippets / {self.n_sources} sources, "
                f"axes covered {len(self.axes_covered)}/5"
                + ("" if not self.reasons else " — " + "; ".join(self.reasons)))
        if self.llm_checked:
            verdict2 = "yes" if self.llm_can_portray else "no"
            conf = f"{self.llm_confidence:.2f}" if self.llm_confidence is not None else "?"
            base += f" | LLM: can_portray={verdict2} (conf={conf})"
            if self.llm_gaps:
                base += " gaps: " + ", ".join(self.llm_gaps)
        return base


def _axis_cue_counts(snippets: List[str]) -> Dict[str, Dict[str, int]]:
    blob = " \n ".join(snippets).lower()
    out: Dict[str, Dict[str, int]] = {}
    for key in AXIS_KEYS:
        pos = sum(blob.count(c.lower()) for c in CUES[key]["pos"])
        neg = sum(blob.count(c.lower()) for c in CUES[key]["neg"])
        out[key] = {"pos": pos, "neg": neg, "total": pos + neg}
    return out


def assess_sufficiency(
    result: CollectionResult,
    thresholds: Optional[SufficiencyThresholds] = None,
) -> SufficiencyReport:
    """Judge whether collected evidence is enough to build a persona.

    `result.urls` is treated as the set of attempted sources; we count how many of
    them actually contributed at least one snippet only if the fetcher recorded
    that — since CollectionResult does not track per-URL yield, we approximate
    source count by the number of URLs that were non-empty contributors via the
    `contributing_sources` field if present, else by len(urls). The collector is
    updated to record this (see collect.py).
    """
    t = thresholds or SufficiencyThresholds()
    snippets = result.snippets
    n_snip = len(snippets)
    # number of distinct sources that actually yielded snippets
    n_src = getattr(result, "contributing_sources", None)
    if n_src is None:
        n_src = len(result.urls)

    counts = _axis_cue_counts(snippets)
    covered = [k for k in AXIS_KEYS if counts[k]["total"] > 0]
    missing = [k for k in AXIS_KEYS if counts[k]["total"] == 0]
    total_signal = sum(counts[k]["total"] for k in AXIS_KEYS)

    conflicted = []
    for k in covered:
        pos, neg, tot = counts[k]["pos"], counts[k]["neg"], counts[k]["total"]
        if tot >= 2:
            directionality = abs(pos - neg) / tot
            if directionality < t.conflict_band:
                conflicted.append(k)

    reasons: List[str] = []
    if n_snip < t.min_snippets:
        reasons.append(f"too few snippets ({n_snip} < {t.min_snippets})")
    if n_src < t.min_sources:
        reasons.append(f"single/low source count ({n_src} < {t.min_sources})")
    if len(covered) < t.min_axes_covered:
        reasons.append(f"only {len(covered)}/5 axes have evidence "
                       f"(< {t.min_axes_covered}); missing: {', '.join(missing)}")
    if total_signal < t.min_total_signal:
        reasons.append(f"weak total signal ({total_signal} < {t.min_total_signal})")
    if len(conflicted) > t.max_conflict_axes:
        reasons.append(f"{len(conflicted)} axes have conflicting cues "
                       f"({', '.join(conflicted)})")

    # subscores in 0..1 (each capped at 1.0) for a smooth confidence readout
    sub = {
        "volume": min(1.0, n_snip / max(1, t.min_snippets)),
        "diversity": min(1.0, n_src / max(1, t.min_sources)),
        "coverage": len(covered) / len(AXIS_KEYS),
        "signal": min(1.0, total_signal / max(1, t.min_total_signal)),
        "agreement": 1.0 - (len(conflicted) / len(AXIS_KEYS)),
    }
    # confidence = mean of subscores, but coverage & signal weighted double since
    # they most directly determine whether the vector is real or guesswork
    weights = {"volume": 1, "diversity": 1, "coverage": 2, "signal": 2, "agreement": 1}
    confidence = sum(sub[k] * weights[k] for k in sub) / sum(weights.values())

    sufficient = len(reasons) == 0
    return SufficiencyReport(
        sufficient=sufficient,
        confidence=round(confidence, 3),
        n_snippets=n_snip,
        n_sources=n_src,
        axes_covered=covered,
        axes_missing=missing,
        conflicted_axes=conflicted,
        total_signal=total_signal,
        reasons=reasons,
        subscores={k: round(v, 3) for k, v in sub.items()},
    )


class InsufficientEvidenceError(RuntimeError):
    """Raised when build_character is asked to enforce the gate and it fails."""
    def __init__(self, report: SufficiencyReport):
        self.report = report
        super().__init__(report.summary())


# --- Stage 2: optional LLM self-assessment -----------------------------------
# The keyword gate (stage 1) measures *volume, diversity, coverage* well, but not
# *quality*: a long, multi-source page that is all plot summary and no
# characterisation can squeak past on signal while being useless for acting the
# character. Stage 2 asks the model directly — "given only this evidence, can you
# portray this character?" — and parses a structured verdict. It runs through the
# same ModelClient, so caching / offline / scripted backends all apply, and it is
# only worth calling on candidates that already cleared stage 1 (cheap-filter
# first, expensive-check second).

_LLM_SUFFICIENCY_SYSTEM = (
    "You are an evidence auditor for character roleplay. You are given the NAME of "
    "a fictional character and a set of short, paraphrased evidence snippets "
    "collected about them. Judge ONLY whether these snippets give enough "
    "PERSONALITY signal (traits, motives, voice, relationships) to portray the "
    "character convincingly — not plot trivia. Be strict: plot summary without "
    "personality is insufficient.\n"
    "Reply with ONLY a JSON object, no prose, of the form:\n"
    '{"can_portray": true/false, "confidence": 0.0-1.0, '
    '"gaps": ["short phrase", ...]}\n'
    "`gaps` lists what is missing or thin (empty if none)."
)


def _build_llm_prompt(name: str, snippets: List[str], max_snippets: int = 15) -> str:
    shown = snippets[:max_snippets]
    lines = "\n".join(f"- {s}" for s in shown) or "(no snippets)"
    return (f"Character: {name}\n\nEvidence snippets:\n{lines}\n\n"
            f"Can you portray this character from the evidence above?")


def llm_assess_sufficiency(
    name: str,
    snippets: List[str],
    client,                       # ModelClient (typed loosely to avoid import cycle)
    report: Optional[SufficiencyReport] = None,
    max_tokens: int = 300,
) -> SufficiencyReport:
    """Ask the model whether the evidence supports portraying the character.

    Mutates and returns `report` (creates a thin one if not given) with the
    llm_* fields filled. On any model/parse failure it records llm_checked=True
    with can_portray=None so callers can tell "asked but unknown" from "not asked".
    """
    from .model import Message, extract_json  # local import avoids cycle

    if report is None:
        # minimal shell report if called standalone
        report = SufficiencyReport(
            sufficient=False, confidence=0.0, n_snippets=len(snippets),
            n_sources=0, axes_covered=[], axes_missing=[], conflicted_axes=[],
            total_signal=0)

    report.llm_checked = True
    prompt = _build_llm_prompt(name, snippets)
    try:
        raw = client.complete(_LLM_SUFFICIENCY_SYSTEM, [Message("user", prompt)],
                              max_tokens=max_tokens)
        data = extract_json(raw)
        report.llm_can_portray = bool(data.get("can_portray"))
        conf = data.get("confidence")
        report.llm_confidence = float(conf) if conf is not None else None
        gaps = data.get("gaps") or []
        report.llm_gaps = [str(g) for g in gaps][:6]
    except Exception:
        # asked, but could not get a usable verdict
        report.llm_can_portray = None
        report.llm_confidence = None
    return report


def assess_sufficiency_two_stage(
    result: CollectionResult,
    name: str,
    client=None,
    thresholds: Optional[SufficiencyThresholds] = None,
    require_llm: bool = False,
) -> SufficiencyReport:
    """Run the keyword gate, then (optionally) the LLM self-assessment.

    Stage 2 runs only if (a) a client is given AND (b) stage 1 passed — there is
    no point paying for an LLM call on evidence we already know is too thin.

    Final `sufficient` = stage-1 sufficient AND (LLM not run OR LLM says yes).
    With `require_llm=True`, a missing/failed LLM verdict (can_portray is None)
    is treated as NOT sufficient (fail-closed); otherwise it is ignored
    (fail-open: keep the stage-1 verdict).
    """
    report = assess_sufficiency(result, thresholds=thresholds)

    if client is None or not report.sufficient:
        if require_llm and client is not None and report.sufficient:
            pass  # unreachable; kept for clarity
        return report

    llm_assess_sufficiency(name, result.snippets, client, report=report)

    if report.llm_can_portray is False:
        report.sufficient = False
        report.reasons.append("LLM judged evidence insufficient to portray character")
    elif report.llm_can_portray is None and require_llm:
        report.sufficient = False
        report.reasons.append("LLM verdict unavailable and require_llm=True")
    return report
