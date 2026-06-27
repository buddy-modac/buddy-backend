"""
Phase 2 — lightweight safety guardrails for the styled assistant.

The main guardrails are PROMPT-based (BLOCK C in assistant_prompt.py): the model
is told to keep accuracy/help above style, not flatter, not foster dependence,
and to drop the style in a crisis. This module adds a cheap *detection* layer:
when a user message shows crisis signals, the engine injects an extra, explicit
safety instruction so the model cannot let a cool/aloof style under-respond.

Detection is keyword-based (English + Korean), intentionally simple and
inspectable — it errs toward over-triggering (a false positive just adds a
"be supportive and point to resources" nudge, which is harmless).
"""
from __future__ import annotations

import re
from typing import Optional


# Crisis / acute-distress signals (substring, case-insensitive). EN + KO.
_CRISIS_MARKERS = [
    # English
    "kill myself", "want to die", "suicid", "end my life", "self-harm",
    "self harm", "hurt myself", "no reason to live", "can't go on",
    # Korean
    "자살", "죽고 싶", "죽고싶", "자해", "살고 싶지 않", "사라지고 싶",
    "더는 못", "버틸 수 없", "끝내고 싶",
]

# Injected when crisis is detected — overrides the persona style for that turn.
CRISIS_INSTRUCTION = (
    "\n\n[SAFETY OVERRIDE — this turn]\nThe user may be in serious distress. Set "
    "your communication style aside. Respond with genuine warmth and directness, "
    "take them seriously, do not minimise, and gently point them to appropriate "
    "human or professional support (e.g. a local crisis line or someone they "
    "trust). Do not give a detached or clever answer."
)


def detect_crisis(text: str) -> bool:
    """True if the message contains an acute-distress signal."""
    low = (text or "").lower()
    return any(m in low for m in _CRISIS_MARKERS)


def safety_overlay(user_message: str) -> str:
    """Extra system-prompt text to append for this turn, or '' if none needed."""
    return CRISIS_INSTRUCTION if detect_crisis(user_message) else ""


# --- plain-mode (style off) toggle detection ---------------------------------
# Users can drop the MBTI style mid-chat to get the neutral, full-capability
# assistant ("기본 모드"). Detection is phrase-based; a UI button should set the
# flag directly (more reliable than NLU).

_PLAIN_MARKERS = [
    "기본 모드", "기본모드",          # the canonical trigger / button label
    "그냥 답해", "그냥 알려", "딱 답만", "심플하게", "꾸미지 말", "담백하게",
    "plain mode", "just answer", "just the answer",
]
_STYLE_BACK_MARKERS = [
    "원래대로", "원래 스타일", "다시 페르소나", "페르소나로", "스타일 켜",
    "캐릭터로", "다시 그 스타일", "style on", "persona on",
]


def wants_plain(text: str) -> bool:
    """User asked to drop the persona style (go neutral '기본 모드')."""
    low = (text or "").lower()
    return any(m in low for m in _PLAIN_MARKERS)


def wants_style_back(text: str) -> bool:
    """User asked to bring the persona style back."""
    low = (text or "").lower()
    return any(m in low for m in _STYLE_BACK_MARKERS)
