"""
Claude Code CLI backend — drive the persona engine with a Claude *subscription*
instead of an Anthropic API key.

WHY THIS EXISTS
---------------
`ModelClient._call_live` talks to `https://api.anthropic.com/v1/messages`, which
needs a pay-as-you-go **API key** (ANTHROPIC_API_KEY). A claude.ai Pro/Max
*subscription* is a different billing system and cannot authenticate that HTTP
endpoint.

But the locally-installed `claude` CLI (Claude Code) IS authenticated by the
subscription, and its headless print mode (`claude -p`) returns a one-shot
completion. This backend shells out to it, so the whole pipeline
(collect -> vector -> chat -> verifier/critic loop) runs at **no extra cost** on
just a subscription.

HOW IT PLUGS IN
---------------
`ModelClient` already supports a pluggable `backend` callable and prefers it over
`_call_live` (see model.py). So this is purely *additive* — the original API-key
path is untouched and remains the default:

    from personaforge import ModelClient, Cache, ClaudeCLIBackend
    client = ModelClient(backend=ClaudeCLIBackend(), cache=Cache("cache.db"))

CAVEATS (vs. the real API path)
  * Skips the `api.anthropic.com` HTTP call, JSON parsing (`extract_json`) and
    auth handling — so it does NOT verify that the live-API code works in
    production. Use a real key for that.
  * `max_tokens` is advisory only (the CLI has no token-cap flag); persona prompts
    already ask for short replies.
  * One subprocess per turn (~the CLI's startup latency), so it is slower than a
    direct HTTP call.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from .model import Message


@dataclass
class ClaudeCLIBackend:
    """A `ScriptedBackend`-compatible callable backed by the `claude` CLI.

    Parameters
    ----------
    model : if set, passed to `claude --model`; if None, the per-call model id
            from ModelClient is forwarded (e.g. "claude-sonnet-4-6"). Pass an
            alias like "opus"/"sonnet" to pin a tier, or "" to use the CLI's own
            session default.
    bin   : path/name of the CLI executable (default "claude").
    timeout : seconds to wait for one completion before raising.
    extra_args : additional flags appended to every invocation.
    verbose : print the resolved command (minus prompt bodies) to stderr.
    """
    model: Optional[str] = None
    bin: str = "claude"
    timeout: float = 120.0
    extra_args: List[str] = field(default_factory=list)
    verbose: bool = False

    def __post_init__(self):
        if shutil.which(self.bin) is None:
            raise RuntimeError(
                f"'{self.bin}' CLI not found on PATH. Install Claude Code "
                "(https://claude.com/claude-code) and log in with your subscription."
            )

    # ModelClient calls: backend(system, model, messages, max_tokens) -> str
    def __call__(self, system: str, model: str,
                 messages: List[Message], max_tokens: int) -> str:
        prompt = self._build_prompt(messages)
        chosen = self.model if self.model is not None else model

        cmd = [self.bin, "-p", prompt, "--system-prompt", system]
        if chosen:                       # "" => omit, use CLI session default
            cmd += ["--model", chosen]
        cmd += self.extra_args

        if self.verbose:
            import sys
            print(f"[ClaudeCLIBackend] model={chosen or '(default)'} "
                  f"turns={len(messages)}", file=sys.stderr)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"claude CLI timed out after {self.timeout}s") from None

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"claude CLI failed (exit {result.returncode}): "
                               f"{err[:300]}")
        return result.stdout.strip()

    @staticmethod
    def _build_prompt(messages: List[Message]) -> str:
        """Flatten the conversation into a single prompt.

        The CLI's print mode is stateless, so — like the API path, which resends
        the full `messages` each call — we reconstruct the whole exchange every
        turn. The persona/roleplay rules live in the system prompt, so here we
        only carry the dialogue and point at the latest user line.
        """
        if not messages:
            return ""
        *prior, last = messages
        if not prior:
            return last.content
        lines = ["[Conversation so far]"]
        for m in prior:
            who = "User" if m.role == "user" else "You"
            lines.append(f"{who}: {m.content}")
        lines += ["", f"User: {last.content}", "",
                  "(Reply in character to the last User message. "
                  "Output only your line, nothing else.)"]
        return "\n".join(lines)
