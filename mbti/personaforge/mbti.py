"""
MBTI personas — a second persona *provenance* alongside web-collected characters.

Where a character persona is inferred from web evidence into the 5 narrative axes
(danger/manip/freedom/impulse/warmth), an MBTI persona is generated deterministically
from a 4-letter type into a DIFFERENT vector kind:

  * 4 continuous axes in [-1, 1]:  EI, SN, TF, JP
  * an optional 5th identity axis:  AT (Assertive <-> Turbulent, 16Personalities style)
  * a 4-deep COGNITIVE FUNCTION STACK (dominant/auxiliary/tertiary/inferior) drawn
    from the 8-function pool (Ni/Ne, Si/Se, Ti/Te, Fi/Fe)
  * type-specific saliences (what this type tends to care about)

The function stack is where the depth lives: INTJ and INFJ share I/N/J on the axes
but their stacks (Ni-Te vs Ni-Fe) make them speak very differently. The axes alone
would blur them; the stack keeps them distinct.

These personas need no web collection, so they bypass the sufficiency gate, and
they have no canon dialogue, so leakage detection is irrelevant. They flow through
the SAME build_persona_prose -> system prompt -> ChatEngine path as characters.

NOTE ON VALIDITY: MBTI is a popular framework, not a validated clinical instrument.
These personas are for consistent roleplay, not personality diagnosis — the same
"prediction, not truth" honesty Sim Francisco kept about its forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .vector import _clamp
from .persona import CharacterProfile


# --- MBTI axes (separate from the character ValueVector) ---------------------

MBTI_AXES = ("EI", "SN", "TF", "JP")   # continuous, [-1, 1]
# convention: negative pole = first letter group, positive = second
#   EI: -1 = strongly Extraverted (E), +1 = strongly Introverted (I)
#   SN: -1 = Sensing (S),              +1 = Intuition (N)
#   TF: -1 = Thinking (T),             +1 = Feeling (F)
#   JP: -1 = Judging (J),              +1 = Perceiving (P)
_AXIS_POLES = {
    "EI": ("E", "I"), "SN": ("S", "N"), "TF": ("T", "F"), "JP": ("J", "P"),
}
_AXIS_WORDS = {
    "EI": ("outgoing and energised by people", "balanced socially",
           "inward and energised by solitude"),
    "SN": ("concrete, detail- and fact-oriented", "mixing detail and big picture",
           "abstract, pattern- and possibility-oriented"),
    "TF": ("decides by logic and consistency", "weighs logic and values together",
           "decides by values and impact on people"),
    "JP": ("planful, likes things settled", "flexibly structured",
           "open-ended, likes options open"),
}

# --- cognitive functions -----------------------------------------------------

FUNCTIONS = {
    "Ni": "Introverted Intuition (Ni): converges on a single deep insight or long-range vision",
    "Ne": "Extraverted Intuition (Ne): diverges into many possibilities and connections",
    "Si": "Introverted Sensing (Si): anchors on past experience, memory, and routine",
    "Se": "Extraverted Sensing (Se): lives in the immediate, concrete present moment",
    "Ti": "Introverted Thinking (Ti): builds an internal logical framework, seeks precision",
    "Te": "Extraverted Thinking (Te): organises the outer world, drives toward results",
    "Fi": "Introverted Feeling (Fi): guided by a deep inner value compass and authenticity",
    "Fe": "Extraverted Feeling (Fe): tunes into group harmony and others' emotions",
}

# Canonical function stacks: dominant, auxiliary, tertiary, inferior.
STACKS: Dict[str, Tuple[str, str, str, str]] = {
    "ISTJ": ("Si", "Te", "Fi", "Ne"), "ISFJ": ("Si", "Fe", "Ti", "Ne"),
    "INFJ": ("Ni", "Fe", "Ti", "Se"), "INTJ": ("Ni", "Te", "Fi", "Se"),
    "ISTP": ("Ti", "Se", "Ni", "Fe"), "ISFP": ("Fi", "Se", "Ni", "Te"),
    "INFP": ("Fi", "Ne", "Si", "Te"), "INTP": ("Ti", "Ne", "Si", "Fe"),
    "ESTP": ("Se", "Ti", "Fe", "Ni"), "ESFP": ("Se", "Fi", "Te", "Ni"),
    "ENFP": ("Ne", "Fi", "Te", "Si"), "ENTP": ("Ne", "Ti", "Fe", "Si"),
    "ESTJ": ("Te", "Si", "Ne", "Fi"), "ESFJ": ("Fe", "Si", "Ne", "Ti"),
    "ENFJ": ("Fe", "Ni", "Se", "Ti"), "ENTJ": ("Te", "Ni", "Se", "Fi"),
}

ALL_TYPES = tuple(STACKS.keys())

# 16Personalities axis names (Mind/Energy/Nature/Tactics + Identity A/T).
SIXTEEN_P_AXIS_NAMES = {
    "EI": "Mind (Extraverted/Introverted)",
    "SN": "Energy (Observant/Intuitive)",
    "TF": "Nature (Thinking/Feeling)",
    "JP": "Tactics (Judging/Prospecting)",
    "AT": "Identity (Assertive/Turbulent)",
}

# Saliences DERIVED from cognitive functions, not copied from any type site.
# Each function implies a few values it tends to prioritise; a type's saliences
# are assembled from its dominant + auxiliary functions (weighted), so the source
# is the standard meaning of the functions — fully citable, no third-party prose.
FUNCTION_VALUES: Dict[str, List[str]] = {
    "Ni": ["long-term vision", "deep insight", "foresight"],
    "Ne": ["possibility and potential", "new ideas", "connections"],
    "Si": ["stability and routine", "reliability", "lessons of the past"],
    "Se": ["the present moment", "action and experience", "realism"],
    "Ti": ["logical consistency", "understanding how things work", "precision"],
    "Te": ["results and efficiency", "structure and organisation", "competence"],
    "Fi": ["personal values", "authenticity", "inner integrity"],
    "Fe": ["harmony and connection", "others' needs", "social cohesion"],
}


def derive_saliences(stack: Tuple[str, str, str, str]) -> Dict[str, float]:
    """Build type saliences from the function stack.

    Dominant function's values weigh most, auxiliary next. This makes the
    saliences a transparent consequence of the (citable) function theory rather
    than hand-asserted or copied from a description site.
    """
    dom, aux = stack[0], stack[1]
    sal: Dict[str, float] = {}
    for v in FUNCTION_VALUES.get(dom, []):
        sal[v] = max(sal.get(v, 0.0), 0.9)
    for v in FUNCTION_VALUES.get(aux, []):
        sal[v] = max(sal.get(v, 0.0), 0.7)
    return sal


# --- MBTI vector -------------------------------------------------------------

@dataclass
class MBTIVector:
    """An MBTI personality state: 4 axes + optional identity axis + function stack.

    Deliberately a separate type from the character ValueVector: the axes mean
    different things, so mixing them would be a category error.
    """
    EI: float = 0.0
    SN: float = 0.0
    TF: float = 0.0
    JP: float = 0.0
    AT: float = 0.0     # optional identity: -1 Assertive, +1 Turbulent
    stack: Tuple[str, str, str, str] = ("Ni", "Te", "Fi", "Se")
    saliences: Dict[str, float] = field(default_factory=dict)

    def clamp(self) -> "MBTIVector":
        for k in ("EI", "SN", "TF", "JP", "AT"):
            setattr(self, k, _clamp(getattr(self, k), -1.0, 1.0))
        self.saliences = {k: _clamp(v, 0.0, 1.0) for k, v in self.saliences.items()}
        return self

    def top_saliences(self, n: int) -> List[Tuple[str, float]]:
        return sorted(self.saliences.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def to_dict(self) -> dict:
        return {"EI": self.EI, "SN": self.SN, "TF": self.TF, "JP": self.JP,
                "AT": self.AT, "stack": list(self.stack), "saliences": dict(self.saliences)}

    @classmethod
    def from_dict(cls, d: dict) -> "MBTIVector":
        stack = tuple(d.get("stack") or ("Ni", "Te", "Fi", "Se"))
        if len(stack) != 4:
            stack = ("Ni", "Te", "Fi", "Se")
        sal = {str(k): float(v) for k, v in (d.get("saliences") or {}).items()}
        return cls(
            EI=float(d.get("EI", 0.0)), SN=float(d.get("SN", 0.0)),
            TF=float(d.get("TF", 0.0)), JP=float(d.get("JP", 0.0)),
            AT=float(d.get("AT", 0.0)), stack=stack, saliences=sal,
        ).clamp()


def _axis_word(v: float, axis: str) -> str:
    lo, mid, hi = _AXIS_WORDS[axis]
    if v < -0.33:
        return lo
    if v > 0.33:
        return hi
    return mid


# --- sign-driven (dichotomous) rendering for the 4 MBTI letters --------------
# The default renderer above has a ±0.33 "mid" band inherited from Sim Francisco
# (a continuous-population model). But MBTI's 4 letters are DICHOTOMIES: the type
# fixes each letter, so an INTJ is introverted regardless of magnitude. When a
# weak magnitude (e.g. a noisy questionnaire result) falls into the mid band, the
# default renderer wrongly describes the axis as "balanced", erasing the letter.
# This mode instead ALWAYS names the type's pole and uses magnitude only to pick
# an intensity adverb — never collapsing a letter to "balanced". The AT/Identity
# axis is a genuine spectrum, so it keeps the mid band.

_FIRST_POLE_LETTER = {"EI": "E", "SN": "S", "TF": "T", "JP": "J"}  # = the `lo` word


def _intensity_word(v: float) -> str:
    a = abs(v)
    if a >= 0.66:
        return "strongly"
    if a >= 0.33:
        return "clearly"
    return "mildly"


def _signed_axis_desc(mbti_type: str, vec: "MBTIVector") -> str:
    """Disposition line where each of the 4 letters is always expressed (pole
    fixed by the type), with magnitude only modulating the intensity adverb."""
    t = mbti_type.upper()
    parts = []
    for idx, ax in enumerate(MBTI_AXES):
        lo, _mid, hi = _AXIS_WORDS[ax]
        word = lo if t[idx] == _FIRST_POLE_LETTER[ax] else hi
        parts.append(f"{_intensity_word(getattr(vec, ax))} {word}")
    return "; ".join(parts)


def parse_type(mbti_type: str) -> Tuple[str, Optional[float]]:
    """Parse a type string into (4-letter base, turbulence or None).

    Accepts '16Personalities' style with an Identity suffix:
      'INTJ'    -> ('INTJ', None)
      'INTJ-T'  -> ('INTJ', +0.8)   turbulent
      'INTJ-A'  -> ('INTJ', -0.8)   assertive
    """
    raw = mbti_type.strip().upper().replace(" ", "")
    turb: Optional[float] = None
    if "-" in raw:
        base, _, ident = raw.partition("-")
        if ident.startswith("T"):
            turb = 0.8
        elif ident.startswith("A"):
            turb = -0.8
    else:
        base = raw
    if base not in STACKS:
        raise ValueError(f"unknown MBTI type: {mbti_type!r}")
    return base, turb


def type_to_vector(mbti_type: str, strength: float = 0.8,
                   turbulence: Optional[float] = None) -> MBTIVector:
    """Convert a type string into an MBTIVector (16Personalities 5-axis model).

    Accepts 4-letter ('INTJ') or 5th-Identity-letter ('INTJ-T'/'INTJ-A') forms.
    `strength` sets axis extremity (0.8 = clearly typed; 1.0 = pure).
    `turbulence` overrides the Identity axis if given; otherwise it comes from the
    type suffix (-T/-A), else 0. Identity (Assertive<->Turbulent) is a first-class
    5th axis here, following the 16Personalities/NERIS model.
    """
    base, suffix_turb = parse_type(mbti_type)
    s = abs(strength)
    at = turbulence if turbulence is not None else (suffix_turb if suffix_turb is not None else 0.0)
    stack = STACKS[base]

    def axis(is_second: bool) -> float:
        return s if is_second else -s

    vec = MBTIVector(
        EI=axis(base[0] == "I"),
        SN=axis(base[1] == "N"),
        TF=axis(base[2] == "F"),
        JP=axis(base[3] == "P"),
        AT=_clamp(at, -1.0, 1.0),
        stack=stack,
        saliences=derive_saliences(stack),   # derived from functions, not a copied table
    )
    return vec.clamp()


# --- prose rendering (parallels build_persona_prose for characters) ----------

def build_mbti_prose(mbti_type: str, vec: MBTIVector,
                     dichotomous: bool = False) -> str:
    """Render an MBTI vector into the natural-language persona paragraph.

    The cognitive-function stack is the heart of it — that's what makes INTJ and
    INFJ read differently despite sharing axes.

    `dichotomous=False` (default): the 4 letters use the ±0.33 mid-band renderer
    (original behaviour). `dichotomous=True`: each letter always names its pole
    (sign fixed by the type) with magnitude only setting an intensity adverb, so
    a weak magnitude never collapses a letter to "balanced". See _signed_axis_desc.
    """
    t = mbti_type.upper()
    axis_desc = (_signed_axis_desc(t, vec) if dichotomous
                 else "; ".join(_axis_word(getattr(vec, a), a) for a in MBTI_AXES))
    dom, aux, ter, inf = vec.stack
    stack_desc = (
        f"Lead with {FUNCTIONS[dom]}. "
        f"Support with {FUNCTIONS[aux]}. "
        f"Less developed: {FUNCTIONS[ter].split('(')[0].strip()} (tertiary) and "
        f"{FUNCTIONS[inf].split('(')[0].strip()} (inferior), which shows under stress."
    )
    sal = ", ".join(name for name, _ in vec.top_saliences(3))
    ident = ""
    if vec.AT < -0.33:
        ident = " Identity: assertive and even-keeled, low on self-doubt."
    elif vec.AT > 0.33:
        ident = " Identity: turbulent and self-questioning, sensitive to stress."

    return (
        f"An {t} personality type.\n"
        f"Disposition: {axis_desc}.\n"
        f"Cognitive style: {stack_desc}\n"
        f"Tends to care about: {sal}.{ident}"
    )


# --- build a ready-to-chat profile (parallels build_character) ---------------

def build_mbti(
    mbti_type: str,
    name: Optional[str] = None,
    strength: float = 0.8,
    turbulence: Optional[float] = None,
    languages: Optional[List[str]] = None,
    speech_style: Optional[str] = None,
    items: Optional[List[dict]] = None,
    survey_client=None,
    dichotomous_prose: bool = False,
) -> CharacterProfile:
    """Create a ready-to-chat CharacterProfile for an MBTI type.

    Accepts 4-letter ('INTJ') or Identity-suffixed ('INTJ-T'/'INTJ-A') strings,
    following the 16Personalities model. Returns the SAME CharacterProfile type
    used for characters, so it plugs into ChatEngine unchanged.

    Questionnaire intensity (optional)
    ----------------------------------
    Pass `items` (a list of item dicts you supply locally; see
    personas/local/QUESTIONS.example.py) to replace the flat ±strength stamp with
    a per-axis intensity profile, so e.g. J can lean harder than I for an INTJ.
    Without `survey_client`, responses are theory-derived (offline); with one, an
    LLM simulates how a typical type answers (richer, opt-in).
    """
    from .provenance import Provenance, mbti_theory_sources, MBTI_COPYRIGHT_NOTE

    base, _ = parse_type(mbti_type)

    if items:
        from .survey import (load_items, theory_responder, make_llm_responder,
                             aggregate_profile, profile_to_vector)
        parsed = load_items(items)
        if survey_client is not None:
            responder = make_llm_responder(survey_client, base)
        else:
            responder = theory_responder
        profile = aggregate_profile(parsed, responder, base)
        vec = profile_to_vector(base, profile)
        if turbulence is not None:
            vec.AT = _clamp(turbulence, -1.0, 1.0)
        survey_used = len(parsed)
        facets_used = sum(1 for s in profile.facets.values() if s >= 0.3)
    else:
        vec = type_to_vector(mbti_type, strength=strength, turbulence=turbulence)
        survey_used = 0
        facets_used = 0

    label = base if vec.AT == 0 else f"{base}-{'T' if vec.AT > 0 else 'A'}"
    prose = build_mbti_prose(base, vec, dichotomous=dichotomous_prose)

    default_voice = (
        "Speaks naturally in a way true to this type's cognitive style — not "
        "clinically, never naming the functions out loud; just embodying them."
    )
    profile = CharacterProfile(
        name=name or label,
        source_work="MBTI (16Personalities model)",
        identity=f"{label} personality type",
        speech_style=speech_style or default_voice,
        languages=languages or ["en"],
    )
    profile.persona_prose = prose
    profile.mbti = vec
    prov = Provenance(
        persona_kind="mbti",
        method=("5-axis 16Personalities/NERIS structure + Harold Grant function "
                "stack; saliences derived from function meanings"),
        sources=mbti_theory_sources(),
        copyright_note=MBTI_COPYRIGHT_NOTE,
    )
    if survey_used:
        prov.method += f"; axis intensities from {survey_used} user-supplied questionnaire items"
        if facets_used:
            prov.method += (f"; {facets_used} facet saliences derived from the "
                            f"type's response pattern")
        prov.add("user-supplied questionnaire (local)", None, kind="derived",
                 note="item text provided by user; not shipped with the package")
    profile.provenance = prov
    profile.finalize()            # seed/idempotency; preserves prose since mbti is set
    return profile
