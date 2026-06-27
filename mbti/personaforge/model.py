"""
Model client with a deterministic SQLite cache.

Analogue of Sim Francisco's `model.rs`. Inherited design:

  * **sha256 cache key** over (model | system | user | max_tokens). Identical calls
    return the cached response, so "clean mode" is byte-reproducible and free on
    re-run — the exact property the Sim Francisco README highlights.
  * **Offline mode.** When offline, only cache hits succeed; a miss raises. This is
    what makes the whole test-suite runnable with zero network and zero API key.
  * **Pluggable backend.** The real Anthropic call is isolated in `_call_live` so
    tests can inject a scripted client.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional


def cache_key(model: str, system: str, user: str, max_tokens: int) -> str:
    h = hashlib.sha256()
    for part in (model, system, user, str(max_tokens)):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class Cache:
    """SQLite-backed response cache. Mirrors the Cache struct in model.rs."""
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "  key TEXT PRIMARY KEY, model TEXT NOT NULL,"
            "  response TEXT NOT NULL, created INTEGER)"
        )
        self.conn.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT response FROM llm_cache WHERE key=?", (key,))
            row = cur.fetchone()
        if row:
            self.hits += 1
            return row[0]
        self.misses += 1
        return None

    def put(self, key: str, model: str, response: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO llm_cache(key, model, response, created) "
                "VALUES (?,?,?,strftime('%s','now'))",
                (key, model, response))
            self.conn.commit()


@dataclass
class Message:
    role: str   # "user" | "assistant"
    content: str


# A scripted backend: maps a user-message substring to a canned reply.
ScriptedBackend = Callable[[str, str, List[Message], int], str]


class ModelClient:
    """Completion client with caching and offline mode.

    Parameters
    ----------
    model : default model id (e.g. "claude-sonnet-4-6")
    cache : optional Cache; if None, no caching
    offline : if True, never hit the network — cache hits only
    backend : optional scripted backend for tests (system, model, messages, max_tokens) -> text
    """
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        cache: Optional[Cache] = None,
        offline: bool = False,
        backend: Optional[ScriptedBackend] = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        api_url: str = "https://api.anthropic.com/v1/messages",
    ):
        self.model = model
        self.cache = cache
        self.offline = offline
        self.backend = backend
        self.api_key_env = api_key_env
        self.api_url = api_url
        self.live_calls = 0

    def complete(
        self,
        system: str,
        messages: List[Message],
        max_tokens: int = 1000,
        model: Optional[str] = None,
    ) -> str:
        model = model or self.model
        # cache key uses the *last user message* joined with prior turns for stability
        convo = "\n".join(f"{m.role}:{m.content}" for m in messages)
        key = cache_key(model, system, convo, max_tokens)

        if self.cache:
            hit = self.cache.get(key)
            if hit is not None:
                return hit

        if self.backend is not None:
            text = self.backend(system, model, messages, max_tokens)
        elif self.offline:
            raise RuntimeError(f"offline mode: cache miss for model {model}")
        else:
            text = self._call_live(system, messages, max_tokens, model)

        if self.cache:
            self.cache.put(key, model, text)
        return text

    def _call_live(self, system: str, messages: List[Message],
                   max_tokens: int, model: str) -> str:
        import requests
        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} not set")
        self.live_calls += 1
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        r = requests.post(
            self.api_url, timeout=60,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            data=json.dumps(body),
        )
        r.raise_for_status()
        data = r.json()
        return "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()


def extract_json(text: str):
    """Pull the first JSON array/object out of a model reply. Mirrors extract_json
    in model.rs (models sometimes wrap JSON in prose or code fences)."""
    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "")
    start = min((i for i in (cleaned.find("["), cleaned.find("{")) if i != -1),
                default=-1)
    if start == -1:
        raise ValueError("no JSON found")
    # find matching end by scanning
    end = max(cleaned.rfind("]"), cleaned.rfind("}"))
    if end <= start:
        raise ValueError("no JSON end found")
    return json.loads(cleaned[start:end + 1])
