"""
Deterministic, seeded persona generation + prompt assembly.

Analogue of Sim Francisco's `persona.rs`. Key inherited properties:

  * **Seeded & deterministic.** Persona generation uses a seeded RNG so the same
    (character, seed) always produces the same persona. This is the reproducibility
    guarantee Sim Francisco relied on (`agent_seed = hash(sim_seed, idx)`).
  * **No LLM during persona build.** Building the persona is pure rules + RNG. The
    LLM is only ever called later, at poll/chat time (see model.py / poll.py).
  * **Prose rendering.** `build_persona_prose` turns the numeric vector into a
    natural-language paragraph the LLM reads — the character analogue of
    Sim Francisco's `build_persona_prose`.
  * **Small per-instance jitter.** A ±0.1 random nudge per axis gives variation
    between instances of the same archetype, exactly like make_value_vector's
    `rng.gen_range(-0.1..0.1)` tail.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .vector import ValueVector, AXES, axis_word


def char_seed(global_seed: int, name: str) -> int:
    """Stable seed for a character. Analogue of agent_seed(sim_seed, idx)."""
    h = hashlib.sha256()
    h.update(str(global_seed).encode())
    h.update(b"|")
    h.update(name.encode("utf-8"))
    return int.from_bytes(h.digest()[:8], "little")


@dataclass
class CharacterProfile:
    """A complete character spec: identity + vector + voice + sources.

    This is the character analogue of a Sim Francisco Agent (PUMS record + value
    vector + persona prose). Instead of census microdata, the 'evidence' comes
    from the web-collected source snippets in `evidence`.
    """
    name: str
    source_work: str = "unknown"
    identity: str = ""                       # one-line role
    vector: ValueVector = field(default_factory=ValueVector)
    speech_style: str = "natural conversational"
    languages: List[str] = field(default_factory=lambda: ["en"])
    evidence: List[str] = field(default_factory=list)   # web-collected snippets (paraphrased)
    seed: int = 0
    persona_prose: str = ""                  # filled by build_persona_prose
    _base_vector: Optional[ValueVector] = None  # pre-jitter vector (for idempotent finalize)
    sufficiency: object = None               # SufficiencyReport (set by build_character)
    mbti: object = None                      # MBTIVector if this is an MBTI persona, else None
    provenance: object = None                # Provenance: where this persona came from

    def finalize(self, global_seed: int = 42, jitter: float = 0.0) -> "CharacterProfile":
        """Render prose, deterministically and idempotently.

        `jitter` controls optional per-instance variation. It defaults to 0.0
        (OFF): the vector inferred from evidence is our best estimate of the
        character, so by default we use it as-is.

        Why it's optional and off by default: Sim Francisco applied a ±0.1 nudge
        to model within-cluster individual variation — hundreds of synthetic
        residents shared one archetype, and the jitter spread them into a
        realistic cloud. A fictional character is a population of ONE, so there is
        no within-cluster spread to simulate; nudging the vector would just add
        noise to our best estimate. The hook is kept for the rare case of wanting
        several subtly different "takes" on the same character: pass e.g.
        jitter=0.1 and vary global_seed to get distinct-but-related variants.

        Idempotent: jitter is always applied to the saved base vector, so calling
        finalize twice (e.g. after save/load) never stacks noise.
        """
        if self._base_vector is None:
            # first finalize: remember the un-jittered (inferred/given) vector
            self._base_vector = ValueVector.from_dict(self.vector.to_dict())
        base = self._base_vector
        self.seed = char_seed(global_seed, self.name)
        new_vec = ValueVector.from_dict(base.to_dict())
        if jitter and jitter > 0.0:
            rng = random.Random(self.seed)
            for ax in AXES:
                cur = getattr(base, ax.key)
                setattr(new_vec, ax.key, cur + rng.uniform(-jitter, jitter))
            new_vec.clamp()
        self.vector = new_vec
        # MBTI personas render their own prose (function stack etc.); don't clobber it.
        if self.mbti is None:
            self.persona_prose = build_persona_prose(self)
        return self


def build_persona_prose(p: CharacterProfile) -> str:
    """Render the numeric vector into a natural-language paragraph.

    Direct analogue of build_persona_prose in persona.rs. The output is what the
    LLM reads as its persona — never the raw numbers.
    """
    leanings = p.vector.describe()
    ident = p.identity or "a fictional character"
    prose = (
        f"{p.name}, {ident} (from {p.source_work}).\n"
        f"Personality: {leanings}\n"
        f"Voice: {p.speech_style}"
    )
    return prose


# --- System prompt assembly (the "persona injection") ------------------------
# This is where the persona becomes an LLM instruction. Sim Francisco kept its
# prompts neutral and leakage-free; we keep ours faithful to the character while
# forbidding verbatim reproduction of copyrighted lines.

SYSTEM_TEMPLATE = """You are roleplaying as the fictional character "{name}" from {work}. Stay fully in character and answer in {lang}.

[PERSONA]
{prose}

[BEHAVIOUR RULES]
- Embody the personality axes and voice above with consistency across the whole conversation.
- Do NOT copy verbatim lines from the source work. Generate NEW dialogue that this personality would plausibly say.
- Keep replies short and in-character (1-4 sentences), dialogue-first, minimal stage direction.
- Never reveal that you are an AI, a model, or a persona. Never break character.
- If asked something the character could not know, react the way the character would, not like an assistant.
{extra}"""


def build_system_prompt(
    p: CharacterProfile,
    language: str = "Korean",
    extra_rules: Optional[str] = None,
) -> str:
    extra = ("\n" + extra_rules) if extra_rules else ""
    return SYSTEM_TEMPLATE.format(
        name=p.name,
        work=p.source_work,
        lang=language,
        prose=p.persona_prose or build_persona_prose(p),
        extra=extra,
    )
