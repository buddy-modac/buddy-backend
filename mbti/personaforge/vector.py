"""
Character value vectors.

Direct analogue of Sim Francisco's `ValueVector` (crates/sim-core/src/agent.rs).
Where Sim Francisco compressed a *voter's* leanings into a handful of [-1, 1] axes
(economic, social, trust, change) plus issue saliences, we compress a *fictional
character's* personality into character-appropriate axes plus topic saliences.

The key inherited idea: a personality is a compact, machine-readable vector that
(a) is cheap to store and compare, and (b) can be rendered to natural-language prose
for an LLM to reason over. The vector never *decides* what the character says — that
is left to the LLM at poll time, exactly as the Sim Francisco code comment states:
"the specific vote on a given measure is left to the LLM reasoning over the persona,
not hardcoded."
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple


# --- Axis registry -----------------------------------------------------------
# Each axis runs from -1.0 to +1.0. `neg`/`pos` are the natural-language poles
# used by the prose renderer (see persona.py). `mid` is the hedge word.
#
# These five axes were chosen to be expressive across a wide range of fiction
# (heroes, villains, tricksters) while staying small enough to reason about.
# Sim Francisco used domain-specific axes (economic L/R etc.); ours are the
# character-fiction equivalent.

@dataclass(frozen=True)
class Axis:
    key: str
    label: str
    neg: str           # word/phrase for strongly negative pole
    mid: str           # word/phrase near zero
    pos: str           # word/phrase for strongly positive pole


AXES: Tuple[Axis, ...] = (
    Axis("danger",  "softness vs danger",
         "gentle and non-threatening",
         "situationally volatile",
         "hiding lethal violence beneath the surface"),
    Axis("manip",   "sincerity vs manipulation",
         "mostly honest and direct",
         "selectively guarded",
         "calculatedly manipulative toward a goal"),
    Axis("freedom", "stability vs freedom-craving",
         "content with stability and the status quo",
         "open to some change",
         "yearning intensely for freedom and escape"),
    Axis("impulse", "caution vs impulsiveness",
         "careful and deliberate",
         "balanced",
         "impulsive and explosive"),
    Axis("warmth",  "coldness vs warmth",
         "cold and distant toward others",
         "selectively open",
         "unexpectedly warm toward those they care about"),
)

AXIS_KEYS: Tuple[str, ...] = tuple(a.key for a in AXES)
_AXIS_BY_KEY: Dict[str, Axis] = {a.key: a for a in AXES}


def axis_word(v: float, axis: Axis) -> str:
    """Map a numeric axis value to its descriptive word.

    Mirrors Sim Francisco's `axis_word` in agent.rs: thresholds at ±0.33.
    """
    if v < -0.33:
        return axis.neg
    if v > 0.33:
        return axis.pos
    return axis.mid


@dataclass
class ValueVector:
    """A character's compact, mutable opinion/personality state.

    All axes are clamped to [-1, 1]; saliences (how much the character cares
    about a topic) to [0, 1]. Mirrors the clamp() behaviour in agent.rs.
    """
    danger: float = 0.0
    manip: float = 0.0
    freedom: float = 0.0
    impulse: float = 0.0
    warmth: float = 0.0
    # topic salience: name -> weight in [0,1]. Free-form (analogue of s_housing etc.)
    saliences: Dict[str, float] = field(default_factory=dict)

    def clamp(self) -> "ValueVector":
        for k in AXIS_KEYS:
            setattr(self, k, _clamp(getattr(self, k), -1.0, 1.0))
        self.saliences = {k: _clamp(v, 0.0, 1.0) for k, v in self.saliences.items()}
        return self

    def axis_values(self) -> Dict[str, float]:
        return {k: getattr(self, k) for k in AXIS_KEYS}

    def describe(self) -> str:
        """Short natural-language summary of the leanings, for prompts.

        Direct analogue of ValueVector::describe() in agent.rs.
        """
        parts = [axis_word(getattr(self, a.key), a) for a in AXES]
        top = self.top_saliences(2)
        sal = ""
        if top:
            names = " and ".join(t[0] for t in top)
            sal = f" Cares most about {names}."
        return "; ".join(parts) + "." + sal

    def top_saliences(self, n: int) -> List[Tuple[str, float]]:
        return sorted(self.saliences.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def distance(self, other: "ValueVector") -> float:
        """Euclidean distance over the 5 axes. Used for clustering / drift checks."""
        return sum((getattr(self, k) - getattr(other, k)) ** 2 for k in AXIS_KEYS) ** 0.5

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ValueVector":
        known = {k: float(d.get(k, 0.0)) for k in AXIS_KEYS}
        sal = {str(k): float(v) for k, v in (d.get("saliences") or {}).items()}
        return cls(saliences=sal, **known).clamp()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
