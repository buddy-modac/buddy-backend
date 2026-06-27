"""
Self-check: confirm PersonaForge works after install.

Run:
    python -m personaforge.check
    # or, if installed:  personaforge-check

Exercises the whole offline pipeline (character + MBTI) with no API key and no
network, and reports optional features (requests, kiwipiepy) availability.
"""
from __future__ import annotations

import sys


def _ok(msg): print(f"  \033[32m✓\033[0m {msg}")
def _no(msg): print(f"  \033[31m✗\033[0m {msg}")
def _info(msg): print(f"  \033[36mi\033[0m {msg}")


def main() -> int:
    print("PersonaForge self-check\n" + "-" * 40)
    failed = 0

    # 1. core import
    try:
        import personaforge as pf
        _ok(f"import personaforge (v{pf.__version__})")
    except Exception as e:
        _no(f"import failed: {e}")
        return 1

    # 2. character pipeline (offline, StaticFetcher + scripted model)
    try:
        from personaforge import (build_character, StaticFetcher, ChatEngine,
                                   ModelClient, Cache)
        pages = {"a": "She is dangerous and lethal, manipulative behind a gentle "
                      "facade, yearning for freedom, impulsive yet warm."}
        reze = build_character("Reze", source_work="Test",
                               fetcher=StaticFetcher(pages),
                               source_urls=["http://x/a"])
        assert reze.persona_prose
        client = ModelClient(cache=Cache(":memory:"),
                             backend=lambda s, m, msgs, mt: "도망가자.")
        eng = ChatEngine(profile=reze, client=client)
        turn = eng.say("안녕")
        assert turn.reply
        _ok("character pipeline (collect → vector → chat)")
    except Exception as e:
        _no(f"character pipeline: {e}"); failed += 1

    # 3. MBTI pipeline
    try:
        from personaforge import build_mbti
        intj = build_mbti("INTJ-T")
        assert "Ni" in intj.persona_prose
        assert intj.provenance is not None
        _ok("MBTI pipeline (16P 5-axis + function stack + provenance)")
    except Exception as e:
        _no(f"MBTI pipeline: {e}"); failed += 1

    # 4. questionnaire intensity (offline)
    try:
        from personaforge import build_mbti
        items = [{"text": "alone", "axis": "EI", "direction": 1, "weight": 0.3},
                 {"text": "planned", "axis": "JP", "direction": -1, "weight": 1.0}]
        shaped = build_mbti("INTJ", items=items)
        assert shaped.mbti is not None
        _ok("questionnaire intensity profile")
    except Exception as e:
        _no(f"questionnaire: {e}"); failed += 1

    # 5. optional features
    print("-" * 40)
    try:
        import requests  # noqa
        _ok("optional: requests (live web + live API)")
    except Exception:
        _info("optional: requests NOT installed  → pip install 'personaforge[live]'")
    try:
        from personaforge import korean_backend
        b = korean_backend()
        if b == "kiwipiepy":
            _ok("optional: kiwipiepy (precise Korean leakage)")
        else:
            _info("optional: kiwipiepy NOT installed → using heuristic fallback "
                  "(pip install 'personaforge[korean]')")
    except Exception as e:
        _info(f"optional korean check skipped: {e}")

    print("-" * 40)
    if failed == 0:
        print("\033[32mAll core checks passed.\033[0m You're ready to go.")
        print("Next: see README 'Quick start' (server: ./start.sh)")
        return 0
    print(f"\033[31m{failed} core check(s) failed.\033[0m")
    return 1


if __name__ == "__main__":
    sys.exit(main())
