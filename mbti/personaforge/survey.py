"""
Questionnaire-driven intensity profiles.

The plain `build_mbti("INTJ")` stamps every axis at the same ±strength, so all
INTJs look identical and J is no stronger than I. Real types have an *intensity
profile*: some axes are extreme, others mild. This module turns a set of
Likert-style items into that per-axis intensity, so a persona's vector reflects
how strongly each preference actually leans.

WHERE THE ITEMS COME FROM
-------------------------
This package ships NO third-party question text. You supply items yourself in a
local file (see personas/local/QUESTIONS.example.py). Each item declares which
axis it measures, which pole it pushes toward, and a weight:

    {"text": "...", "axis": "EI", "direction": +1, "weight": 1.0}

`direction` follows the same convention as mbti.py: +1 pushes the SECOND-letter
pole (I, N, F, P, and Turbulent for AT); -1 pushes the first (E, S, T, J, A).

TWO WAYS TO GET RESPONSES
-------------------------
1. Theory-derived (offline, default): a "typical TYPE" answers each item the way
   that type's cognitive-function lean predicts. No API, fully deterministic.
2. LLM-generated (optional): ask a model how a typical TYPE would answer, for a
   richer profile. Same opt-in pattern as the rest of the package.

Either way, responses are aggregated per axis into an intensity in [-1, 1].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .vector import _clamp
from .mbti import STACKS, FUNCTION_VALUES, MBTI_AXES, MBTIVector, type_to_vector


# --- item schema -------------------------------------------------------------

@dataclass
class Item:
    text: str
    axis: str            # one of EI, SN, TF, JP, AT
    direction: int       # +1 toward second-letter pole, -1 toward first
    weight: float = 1.0
    facet: Optional[str] = None   # optional value/facet this item taps; AGREEING
                                  # with the statement = MORE of this facet

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        facet = d.get("facet")
        return cls(text=d["text"], axis=d["axis"].upper(),
                   direction=int(d.get("direction", 1)),
                   weight=float(d.get("weight", 1.0)),
                   facet=str(facet).strip() if facet else None)


def load_items(dicts: List[dict]) -> List[Item]:
    items = [Item.from_dict(d) for d in dicts]
    for it in items:
        if it.axis not in ("EI", "SN", "TF", "JP", "AT"):
            raise ValueError(f"item axis must be one of EI/SN/TF/JP/AT, got {it.axis!r}")
    return items


# --- response models ---------------------------------------------------------

# A responder answers an item on a 1..5 Likert scale (3 = neutral).
Responder = Callable[[Item, str], int]


def theory_responder(item: Item, mbti_type: str) -> int:
    """Predict how a typical TYPE answers an item, from its function lean.

    Deterministic and offline. Combines three signals so intensity actually
    varies per axis (instead of saturating at 1/5):
      * which pole the type prefers on this axis (sign);
      * how *confident* the type is on that axis, from WHERE the relevant function
        sits in its stack (dominant = very confident, inferior = weak);
      * the item's own weight (a low-weight item pulls the answer toward neutral).
    Returns a float in [1, 5] (3 = neutral); aggregation handles the rest.
    """
    base = mbti_type.upper()
    tv = type_to_vector(base)
    axis_val = getattr(tv, item.axis)
    if item.axis == "AT":
        axis_pref = 0.0
    else:
        axis_pref = 1.0 if axis_val > 0 else -1.0

    # Confidence from stack POSITION of the function serving this axis.
    # dominant→1.0, auxiliary→0.75, tertiary→0.5, inferior→0.35, absent→0.55
    stack = STACKS[base]
    axis_funcs = {
        "EI": ("Ni", "Ne", "Ti", "Te", "Fi", "Fe", "Si", "Se"),  # any (attitude tells E/I)
        "SN": ("Ne", "Ni", "Se", "Si"),                            # perceiving functions
        "TF": ("Te", "Ti", "Fe", "Fi"),                            # judging functions
        "JP": ("Te", "Fe", "Se", "Ne", "Ti", "Fi", "Si", "Ni"),   # any (handled below)
    }
    pos_conf = {0: 1.0, 1: 0.75, 2: 0.5, 3: 0.35}
    relevant = axis_funcs.get(item.axis, ())
    confidence = 0.55
    for pos, fn in enumerate(stack):
        if fn in relevant:
            confidence = pos_conf[pos]
            break

    # For EI/JP, the dominant function's attitude is the clearest cue, so keep
    # those highly confident; SN/TF vary more by where N/S or T/F sits.
    if item.axis in ("EI",):
        confidence = max(confidence, 0.85)

    # agreement (does the item push the type's pole?), scaled by confidence AND
    # the item's own weight (weak items stay near neutral).
    agree = item.direction * axis_pref
    w = max(0.0, min(1.0, item.weight))
    score = agree * confidence * (0.4 + 0.6 * w)   # weight pulls toward neutral
    return 3.0 + 2.0 * score                         # float in [1,5]


def make_llm_responder(client, mbti_type: str):
    """Optional: a responder that asks an LLM how a typical TYPE answers.

    Batched into one call for all items; falls back to neutral (3) on failure.
    """
    from .model import Message, extract_json

    def responder(item: Item, t: str) -> int:
        # single-item fallback path (rarely used; batch path below is preferred)
        return 3

    # we expose a batch helper instead for efficiency
    def batch(items: List[Item]) -> Dict[int, int]:
        listing = "\n".join(f"{i}. {it.text}" for i, it in enumerate(items))
        sys = ("You simulate how a TYPICAL person of a given MBTI type answers a "
               "Likert questionnaire. For each numbered statement, give 1 (strongly "
               "disagree) to 5 (strongly agree) as that type would. Reply ONLY as "
               "JSON: {\"answers\": {\"0\": n, \"1\": n, ...}}.")
        prompt = f"Type: {mbti_type}\n\nStatements:\n{listing}"
        try:
            raw = client.complete(sys, [Message("user", prompt)], max_tokens=400)
            data = extract_json(raw)
            ans = data.get("answers", {})
            return {int(k): int(_clamp(int(v), 1, 5)) for k, v in ans.items()}
        except Exception:
            return {}

    responder.batch = batch  # attach
    return responder


# --- aggregation -------------------------------------------------------------

@dataclass
class IntensityProfile:
    axes: Dict[str, float] = field(default_factory=dict)   # EI/SN/TF/JP/AT in [-1,1]
    n_items: Dict[str, int] = field(default_factory=dict)
    facets: Dict[str, float] = field(default_factory=dict)  # facet -> endorsement [-1,1]

    def get(self, axis: str) -> float:
        return self.axes.get(axis, 0.0)


def _likert_to_signed(level: int) -> float:
    """1..5 -> -1..+1 (3 = 0)."""
    return (level - 3) / 2.0


def aggregate_profile(items: List[Item], responder: Responder,
                      mbti_type: str) -> IntensityProfile:
    """Aggregate item responses into per-axis intensity in [-1, 1].

    For each item: signed_response * direction * weight contributes to its axis.
    Averaged per axis and clamped. An axis with no items stays 0.
    """
    # support a batched LLM responder if present
    batch_answers: Dict[int, int] = {}
    if hasattr(responder, "batch"):
        batch_answers = responder.batch(items)  # type: ignore

    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    # facet endorsement: AGREEING with the statement (high Likert) = more of the
    # facet, so we use the raw signed agreement (NOT signed*direction, which is
    # axis-magnitude bookkeeping). A type that disagrees scores the facet down.
    facet_sums: Dict[str, float] = {}
    facet_counts: Dict[str, float] = {}
    for idx, it in enumerate(items):
        if batch_answers:
            level = batch_answers.get(idx, 3)
        else:
            level = responder(it, mbti_type)
        signed = _likert_to_signed(level)         # -1..+1
        contribution = signed * it.direction * it.weight
        sums[it.axis] = sums.get(it.axis, 0.0) + contribution
        counts[it.axis] = counts.get(it.axis, 0) + abs(it.weight)
        if it.facet:
            facet_sums[it.facet] = facet_sums.get(it.facet, 0.0) + signed * it.weight
            facet_counts[it.facet] = facet_counts.get(it.facet, 0.0) + abs(it.weight)

    axes: Dict[str, float] = {}
    for ax in ("EI", "SN", "TF", "JP", "AT"):
        if counts.get(ax):
            axes[ax] = _clamp(sums[ax] / counts[ax], -1.0, 1.0)
    facets: Dict[str, float] = {
        f: _clamp(facet_sums[f] / facet_counts[f], -1.0, 1.0)
        for f in facet_sums if facet_counts.get(f)
    }
    return IntensityProfile(axes=axes, n_items={k: 0 for k in axes}, facets=facets)


# --- apply a profile to an MBTI vector ---------------------------------------

# A facet must be endorsed at least this strongly to surface as a salience.
FACET_SALIENCE_MIN = 0.3

def profile_to_vector(mbti_type: str, profile: IntensityProfile,
                      min_strength: float = 0.25) -> MBTIVector:
    """Build an MBTIVector whose axis magnitudes come from the questionnaire.

    The SIGN of each axis is fixed by the type letters (an INTJ is introverted,
    period); the MAGNITUDE comes from the profile, so J can be stronger than I.
    Axes the questionnaire didn't cover fall back to the default ±0.8 stamp.
    """
    base = mbti_type.upper()
    stamped = type_to_vector(base)                # default signs + ±0.8 + stack + saliences
    for ax in ("EI", "SN", "TF", "JP"):
        sign = 1.0 if getattr(stamped, ax) > 0 else -1.0
        if ax in profile.axes:
            mag = max(min_strength, abs(profile.axes[ax]))
            setattr(stamped, ax, sign * mag)
    if "AT" in profile.axes:
        stamped.AT = profile.axes["AT"]
    # Data-driven saliences: facets the type endorses (questionnaire response
    # pattern) join the function-derived ones, so the persona reflects which
    # values this type actually scored high on — not just the 4 axis signs.
    for facet, score in profile.facets.items():
        if score >= FACET_SALIENCE_MIN:
            stamped.saliences[facet] = max(stamped.saliences.get(facet, 0.0),
                                           _clamp(score, 0.0, 1.0))
    return stamped.clamp()
