"""
Conversation memory management.

Long chats grow the message history without bound, so every turn re-sends an
ever-larger prompt — rising cost and eventual context overflow. This module keeps
the history within a budget using two strategies, mirroring the spirit of
Sim Francisco's batching/caching discipline (don't pay to resend what you don't
need):

  * **Sliding window** — keep the most recent N messages, drop older ones.
    Cheap, deterministic, no model call. Good default.
  * **Summarisation** — when over budget, fold the oldest messages into a short
    running summary via the model, keeping recent turns verbatim. Preserves
    long-range context (who the character is to the user, decisions made) that a
    pure window would forget. Optional, needs a client.

Token counting is a lightweight estimate (chars/4 with a per-message overhead),
which is enough for budgeting; we deliberately avoid a tokenizer dependency to
keep the package std-lib-only. The estimate is intentionally slightly
conservative (rounds up) so we stay under real limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .model import Message, ModelClient


def estimate_tokens(text: str) -> int:
    """Rough token estimate. ~4 chars/token for mixed English; Korean is denser
    so we bias upward a little. Conservative by design."""
    if not text:
        return 0
    # count CJK separately (closer to ~1.5 chars/token) from the rest (~4)
    cjk = sum(1 for c in text if "\uac00" <= c <= "\ud7a3" or "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4) + 1


def messages_tokens(messages: List[Message], per_msg_overhead: int = 4) -> int:
    return sum(estimate_tokens(m.content) + per_msg_overhead for m in messages)


@dataclass
class MemoryConfig:
    max_tokens: int = 2000          # budget for the rolling history (excl. system)
    keep_recent: int = 6            # always keep at least this many recent messages
    strategy: str = "window"        # "window" | "summarize"
    summary_client: Optional[ModelClient] = None   # required for "summarize"


_SUMMARY_SYSTEM = (
    "You compress chat history for a character roleplay. Summarise the older "
    "messages into a few terse third-person notes capturing: who the user is to "
    "the character, key facts established, and the emotional state/relationship. "
    "Keep it under 80 words. Output ONLY the summary text, no preamble."
)


def _summarize(messages: List[Message], client: ModelClient) -> str:
    convo = "\n".join(f"{m.role}: {m.content}" for m in messages)
    try:
        return client.complete(_SUMMARY_SYSTEM, [Message("user", convo)],
                               max_tokens=160).strip()
    except Exception:
        return ""


def manage_history(
    history: List[Message],
    config: Optional[MemoryConfig] = None,
) -> Tuple[List[Message], Optional[str]]:
    """Return (trimmed_history, summary_or_None) within the token budget.

    Never splits a turn unnaturally: it keeps the most recent `keep_recent`
    messages verbatim and either drops or summarises the rest.
    """
    config = config or MemoryConfig()
    if messages_tokens(history) <= config.max_tokens:
        return list(history), None

    keep = max(config.keep_recent, 1)
    recent = history[-keep:]
    older = history[:-keep]

    if config.strategy == "summarize" and config.summary_client and older:
        summary = _summarize(older, config.summary_client)
        # if recent alone still over budget, window it down further
        while messages_tokens(recent) > config.max_tokens and len(recent) > 1:
            recent = recent[1:]
        return recent, (summary or None)

    # default: sliding window — drop oldest until under budget
    trimmed = recent
    while messages_tokens(trimmed) > config.max_tokens and len(trimmed) > 1:
        trimmed = trimmed[1:]
    return trimmed, None
