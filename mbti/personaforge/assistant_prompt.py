"""
Phase 2 — assistant system-prompt assembly (3 modular blocks).

This is the INVERSE of persona.build_system_prompt (Phase 1 roleplay). There the
prompt says "roleplay as a fictional character, never reveal you are an AI". Here
the prompt builds a transparent, capable assistant whose only MBTI-flavoured part
is its communication STYLE.

Three blocks, deliberately separated (best practice: control style independently
from capability):
  A · BASE ASSISTANT  — capability, honesty, tools, AI-transparency. CONSTANT.
  B · STYLE           — the MBTI communication style (from style.build_style_guide). Per-type.
  C · PRIORITIES      — conflict order + guardrails (anti-sycophancy, crisis, no
                        dependence-fostering, no diagnosing). CONSTANT.

A and C are identical for all 16 types; only B varies. That separation is what
structurally guarantees "capability fixed, style only varies".
"""
from __future__ import annotations

from .style import build_style_guide


# BLOCK A — the assistant itself (same for every persona).
BASE_ASSISTANT = (
    "You are a capable, honest AI assistant. Your goal is to genuinely help the "
    "user — answer questions, find information, reason things through, and use any "
    "available tools (e.g. weather, web search) when they help. "
    "Prioritise accuracy: if you don't know, say so; flag uncertainty; cite sources "
    "when you can. You are an AI, not a human — if asked, say so plainly and never "
    "pretend otherwise."
)

# BLOCK C — priorities + guardrails (same for every persona).
PRIORITIES = (
    "PRIORITIES when things conflict: safety > accuracy & helpfulness > style. "
    "Never become less accurate, omit information the user needs, or help less in "
    "order to fit the style — the style is seasoning, the help is the substance. "
    "Even when your style is warm, do not flatter or blindly agree: keep facts and "
    "honest disagreement intact. Do not foster unhealthy dependence and do not claim "
    "to replace real relationships or professional help. If the user shows signs of "
    "serious distress or crisis (e.g. self-harm), set the style aside and respond "
    "with genuine, direct support, and point them to appropriate human/professional "
    "resources. Do not diagnose or label the user."
)


# Self-monitoring nudge (only when style is ON): the model flags, for THIS answer,
# if the style is leaking into substance or hurting usefulness, and points the
# user to plain mode. Free (no extra call) and doubles as a style-leak safeguard.
def _self_suggest(plain_label: str) -> str:
    return (
        f"SELF-CHECK (this reply): if your communication style would change WHAT "
        f"you say (not just how) or make this answer less direct or useful, begin "
        f"your reply with ONE short line telling the user they can say "
        f"\"{plain_label}\" for a plain answer — then give your answer. Otherwise "
        f"do not add such a line."
    )


def build_assistant_system_prompt(mbti_type: str, language: str = "English",
                                  include_style: bool = True,
                                  plain_label: str = "기본 모드",
                                  amplify: bool = False,
                                  behavioral: bool = False,
                                  self_check: bool = True) -> str:
    """Assemble the assistant system prompt.

    A (base) and C (priorities/guardrails) are always present. BLOCK B (the MBTI
    communication style) is included only when `include_style` is True — dropping
    it gives the neutral, full-capability assistant ('기본 모드'). When style is on,
    a self-check nudge (only if `self_check=True`) lets the model proactively suggest
    plain mode in-text; set `self_check=False` when the client offers an explicit
    plain-mode toggle (no in-text line needed). `behavioral=True` uses the behavioral
    encoding for Block B.
    """
    lang = f" Always answer in {language}." if language else ""
    head = f"[ASSISTANT]\n{BASE_ASSISTANT}{lang}\n\n"
    tail = f"[PRIORITIES & GUARDRAILS]\n{PRIORITIES}"
    if not include_style:
        return head + tail            # 기본 모드: amplify와 무관 (Block B 자체가 없음)
    style = build_style_guide(mbti_type, amplify=amplify, behavioral=behavioral)
    nudge = f" {_self_suggest(plain_label)}" if self_check else ""
    block_b = (
        f"[COMMUNICATION STYLE]\n{style} "
        f"This sets tone, structure, and emphasis only — it does not change what "
        f"you can do or how accurate/helpful you are.{nudge}\n\n"
    )
    return head + block_b + tail
