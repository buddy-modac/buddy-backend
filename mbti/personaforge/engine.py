"""
The chat engine: persona injection + poll + self-correcting review loop.

Ties everything together. The flow mirrors Sim Francisco's poll path plus its
self-correction loop (`/sf:hillclimb`: validate -> diagnose -> fix -> verify+critic
-> repeat):

  1. Build the system prompt from the character's persona (persona injection).
  2. Call the model (poll).
  3. Run the verifier + adversarial critic (review).
  4. If rejected, regenerate with a corrective nudge appended to the system
     prompt, up to `max_retries`. This is the character-domain hillclimb: each
     retry feeds the critic's objections back in as guidance.

"Done" is machine-checkable (clears the gate, no fatal objection), never
human-confirmed — the Sim Francisco completion criterion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .persona import CharacterProfile, build_system_prompt
from .model import ModelClient, Message
from .critic import Verifier, AdversarialCritic, review, CritiqueResult
from .memory import MemoryConfig, manage_history, estimate_tokens, messages_tokens


@dataclass
class Turn:
    user: str
    reply: str
    critique: CritiqueResult
    attempts: int


@dataclass
class ChatEngine:
    profile: CharacterProfile
    client: ModelClient
    language: str = "Korean"
    gate: float = 0.70
    max_retries: int = 2
    canon_lines: Optional[List[str]] = None      # for leakage detection
    history: List[Message] = field(default_factory=list)
    verifier: Verifier = field(default_factory=Verifier)
    critic: AdversarialCritic = field(default_factory=AdversarialCritic)
    transcript: List[Turn] = field(default_factory=list)
    memory: Optional["MemoryConfig"] = None       # None = keep full history

    def _system(self, corrective: str = "", summary: str = "") -> str:
        extra = ""
        if summary:
            extra += f"\n[EARLIER CONTEXT]\n{summary}"
        if corrective:
            extra += ("\n" + corrective)
        return build_system_prompt(
            self.profile, language=self.language,
            extra_rules=extra or None)

    def _prepare_history(self):
        """Apply memory management; return (messages_to_send, summary_or_None)."""
        if self.memory is None:
            return self.history, None
        return manage_history(self.history, self.memory)

    def say(self, user_message: str, max_tokens: int = 600) -> Turn:
        """One turn: poll the model, review, self-correct if needed."""
        self.history.append(Message("user", user_message))
        corrective = ""
        last: Optional[CritiqueResult] = None
        reply = ""

        send_history, summary = self._prepare_history()

        for attempt in range(1, self.max_retries + 2):
            system = self._system(corrective, summary or "")
            reply = self.client.complete(system, send_history, max_tokens=max_tokens)
            last = review(
                reply, self.profile,
                verifier=self.verifier, critic=self.critic,
                canon_lines=self.canon_lines,
                user_prompt=user_message, gate=self.gate,
            )
            if last.accepted:
                break
            # build corrective nudge from objections (the hillclimb 'diagnose -> fix')
            corrective = self._corrective_from(last)

        self.history.append(Message("assistant", reply))
        turn = Turn(user=user_message, reply=reply, critique=last, attempts=attempt)
        self.transcript.append(turn)
        return turn

    def _corrective_from(self, result: CritiqueResult) -> str:
        lines = ["[CORRECTION — your previous reply was rejected, fix these]"]
        for o in result.objections:
            if o.kind == "leakage":
                lines.append("- Do NOT reuse canon dialogue. Say something new in your own words.")
            elif o.kind == "persona_break":
                lines.append("- Never speak like an assistant. Stay fully in character.")
            elif o.kind == "stereotype":
                lines.append("- Avoid generic tropes. React from THIS character's specific motives.")
            elif o.kind == "vector_drift":
                lines.append(f"- Tone mismatch: {o.detail}. Match the personality more closely.")
        if result.score.headline < self.gate:
            lines.append("- Be more distinctly in-character; keep it short and dialogue-first.")
        return "\n".join(lines)

    def reset(self) -> None:
        self.history.clear()
        self.transcript.clear()
