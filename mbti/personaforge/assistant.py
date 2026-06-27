"""
Phase 2 — AssistantEngine: an MBTI-STYLED, fully-capable AI assistant.

Separate from Phase 1's ChatEngine on purpose (decision D2): ChatEngine runs an
adversarial roleplay critic (leakage / persona_break / stereotype / vector_drift)
that is WRONG here — e.g. "I'm an AI" would be rejected as a persona_break, yet
that transparency is REQUIRED for an assistant. So this engine is light: build
the 3-block assistant prompt, manage memory, apply a safety overlay on crisis,
optionally expose tools, and answer. Capability/accuracy is never gated on style.

Phase 1 code is untouched; this is the `mode="assistant"` path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .model import ModelClient, Message
from .memory import MemoryConfig, manage_history
from .assistant_prompt import build_assistant_system_prompt
from .guardrails import safety_overlay, wants_plain, wants_style_back
from .tools import Tool, tools_catalog


@dataclass
class AssistantTurn:
    user: str
    reply: str
    crisis_flagged: bool = False
    style_on: bool = True                 # was the MBTI style active this turn?
    tools_offered: List[str] = field(default_factory=list)


@dataclass
class AssistantEngine:
    """An MBTI-styled assistant. `mbti_type` sets only the communication style.

    The user can drop the style mid-chat ("기본 모드") to get the neutral,
    full-capability assistant, and bring it back ("원래대로"). A UI can also flip
    it directly via `say(..., style=False/True)`. Transitions are announced briefly.
    """
    mbti_type: str
    client: ModelClient
    language: str = "English"
    tools: List[Tool] = field(default_factory=list)
    memory: Optional[MemoryConfig] = None
    style_enabled: bool = True
    amplify: bool = True                   # concrete/sensory boost for S types
    behavioral: bool = False               # behavioral (vs descriptive) Block B encoding
    plain_label: str = "기본 모드"
    history: List[Message] = field(default_factory=list)
    transcript: List[AssistantTurn] = field(default_factory=list)

    def _system_prompt(self) -> str:
        sysp = build_assistant_system_prompt(
            self.mbti_type, self.language,
            include_style=self.style_enabled, plain_label=self.plain_label,
            amplify=self.amplify, behavioral=self.behavioral)
        if self.tools:
            sysp += tools_catalog(self.tools)
        return sysp

    def _prepare_history(self):
        if self.memory is None:
            return self.history, None
        return manage_history(self.history, self.memory)

    def say(self, user_message: str, max_tokens: int = 600,
            style: Optional[bool] = None) -> AssistantTurn:
        """One turn. Honesty/help/safety always outrank style. `style` forces the
        mode for this turn (UI button); None = keep state but obey in-message
        commands ('기본 모드' / '원래대로')."""
        self.history.append(Message("user", user_message))

        # resolve style state + whether we switched this turn
        switched = None
        if style is not None:
            if style != self.style_enabled:
                switched = "on" if style else "off"
            self.style_enabled = style
        elif wants_plain(user_message) and self.style_enabled:
            self.style_enabled, switched = False, "off"
        elif wants_style_back(user_message) and not self.style_enabled:
            self.style_enabled, switched = True, "on"

        send_history, summary = self._prepare_history()
        system = self._system_prompt()
        if summary:
            system += f"\n\n[EARLIER CONTEXT]\n{summary}"
        crisis = bool(safety_overlay(user_message))
        if crisis:
            system += safety_overlay(user_message)

        reply = self.client.complete(system, send_history, max_tokens=max_tokens)

        # brief transition announcement (engine-side, not model)
        if switched == "off":
            reply = f"({self.plain_label}로 답할게요)\n\n{reply}"
        elif switched == "on":
            reply = f"(다시 {self.mbti_type}답게 갈게요)\n\n{reply}"

        self.history.append(Message("assistant", reply))
        turn = AssistantTurn(user=user_message, reply=reply, crisis_flagged=crisis,
                             style_on=self.style_enabled,
                             tools_offered=[t.name for t in self.tools])
        self.transcript.append(turn)
        return turn

    def reset(self) -> None:
        self.history.clear()
        self.transcript.clear()
