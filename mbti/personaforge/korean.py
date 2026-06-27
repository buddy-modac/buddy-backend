"""
Korean-aware tokenisation for leakage detection.

The word-level leakage check in critic.py compares contiguous token runs. That
works well for English but under-detects Korean: "도망가자" (run away — let's)
and "도망갔어" (ran away) share the stem 도망가- but are different surface words,
so a naive whitespace split treats them as unrelated. A character could then
reproduce a canon line with trivial ending changes and slip past the check.

This module normalises Korean text to morpheme stems before comparison:

  * If `kiwipiepy` is installed, use it to extract content morphemes
    (verbs/adjectives/nouns) and drop particles/endings — so 도망가자 and
    도망갔어 both reduce to 도망가/가- stems and match.
  * If not installed, fall back to a dependency-free heuristic that strips
    common Korean particles/endings from each token. Less precise, but keeps the
    package working with zero extra deps (the project's standing rule).

For non-Korean text the tokeniser is a passthrough (lowercased word split), so
English behaviour is unchanged.
"""
from __future__ import annotations

import re
from typing import List, Optional

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def has_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(text))


# --- optional kiwipiepy backend ---------------------------------------------

_kiwi = None
_kiwi_tried = False

# content morpheme tags we keep (noun/verb/adjective/root/adverb families)
_CONTENT_TAGS = ("NNG", "NNP", "NNB", "NR", "NP",   # nouns
                 "VV", "VA", "VX", "VCP", "VCN",     # verbs/adjectives
                 "MAG", "MAJ",                         # adverbs
                 "XR", "SL", "SH", "SN")              # roots, foreign, numbers


def _get_kiwi():
    global _kiwi, _kiwi_tried
    if _kiwi_tried:
        return _kiwi
    _kiwi_tried = True
    try:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
    except Exception:
        _kiwi = None
    return _kiwi


# --- dependency-free Korean fallback ----------------------------------------
# Strips frequent particles/endings so inflected forms collapse toward a stem.
# Ordered longest-first so multi-char endings go before single-char ones.
_KO_SUFFIXES = [
    "습니다", "ㅂ니다", "었어요", "았어요", "겠어요", "에서는", "으로는",
    "이라고", "라고", "처럼", "보다", "에게", "한테", "께서", "에서", "으로",
    "까지", "부터", "마다", "조차", "마저", "밖에", "이나", "나마",
    "었어", "았어", "겠어", "어요", "아요", "지요", "네요", "군요", "거든",
    "는데", "은데", "니까", "어서", "아서", "려고", "면서", "도록",
    "는", "은", "을", "를", "이", "가", "에", "의", "와", "과", "도",
    "만", "고", "면", "서", "자", "야", "아", "어", "지", "라", "다", "요",
]


def _strip_korean(token: str) -> str:
    """Heuristically reduce one Korean token toward its stem."""
    t = token
    # iteratively peel known endings (at most a few rounds)
    for _ in range(3):
        peeled = False
        for suf in _KO_SUFFIXES:
            if len(t) > len(suf) + 1 and t.endswith(suf):
                t = t[: -len(suf)]
                peeled = True
                break
        if not peeled:
            break
    return t


# --- public API --------------------------------------------------------------

def stem_tokens(text: str) -> List[str]:
    """Return a list of comparison tokens.

    Korean -> content-morpheme stems (kiwipiepy) or heuristic stems (fallback).
    Non-Korean -> lowercased word tokens (unchanged behaviour).
    Mixed text is handled token by token.
    """
    if not has_hangul(text):
        return [w.lower() for w in _WORD_RE.findall(text)]

    kiwi = _get_kiwi()
    if kiwi is not None:
        out: List[str] = []
        for tok in kiwi.tokenize(text):
            if tok.tag in _CONTENT_TAGS:
                out.append(tok.form.lower())
        # if morph analysis yielded nothing useful, fall through to heuristic
        if out:
            return out

    # dependency-free fallback: split on whitespace/punct, strip Korean endings
    out = []
    for w in _WORD_RE.findall(text):
        if _HANGUL_RE.search(w):
            out.append(_strip_korean(w).lower())
        else:
            out.append(w.lower())
    return [t for t in out if t]


def backend_name() -> str:
    """Report which backend is active (useful for diagnostics/tests)."""
    return "kiwipiepy" if _get_kiwi() is not None else "heuristic"
