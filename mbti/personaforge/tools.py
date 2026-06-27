"""
Phase 2 — pluggable tool interface (P2.1: interface + mock stubs only).

The styled assistant must be able to *do AI things* — fetch weather, look up
news, calculate, etc. P2.1 ships the INTERFACE and mock implementations so the
engine and tests work end-to-end offline; real implementations (live weather /
search, or native model tool-use) land in P2.2.

Design note (decision D3): tools are kept behind a tiny `Tool` protocol so the
same engine works with (a) self-built tools that we run in Python — works on the
subscription CLI backend — and (b) later, native model tool-use via the API. The
engine treats a tool's `run()` output as FACT; the MBTI style only changes how
that fact is phrased, never the fact itself.
"""
from __future__ import annotations

from typing import Dict, List, Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    def run(self, query: str) -> str: ...


class MockWeatherTool:
    """Stub weather tool — returns canned data (real impl in P2.2)."""
    name = "weather"
    description = "Get the weather for a place/date. (mock)"

    def run(self, query: str) -> str:
        return "[mock weather] rain, 12mm, 18°C"


class MockNewsTool:
    """Stub news/search tool — returns a canned link (real impl in P2.2)."""
    name = "news"
    description = "Find a relevant article link for a topic. (mock)"

    def run(self, query: str) -> str:
        return "[mock news] https://example.org/article (a relevant piece)"


def tool_registry(tools: List[Tool]) -> Dict[str, Tool]:
    """Index tools by name for lookup."""
    return {t.name: t for t in tools}


def tools_catalog(tools: List[Tool]) -> str:
    """Human/LLM-readable list of available tools, for the system prompt."""
    if not tools:
        return ""
    lines = "\n".join(f"- {t.name}: {t.description}" for t in tools)
    return ("\n\n[AVAILABLE TOOLS]\nYou may use these (their output is fact; phrase "
            "it in your style, never alter the fact):\n" + lines)
