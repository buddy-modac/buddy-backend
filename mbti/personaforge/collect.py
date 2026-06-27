"""
Evidence collection + vector inference ("ingest").

Character-domain analogue of Sim Francisco's `ingest_pums` binary: where they
ingested ACS PUMS microdata to seed the population, we ingest *web text about a
character* (wiki/analysis/personality-DB pages) to seed the value vector.

Two layers:
  1. Fetching (network). Pluggable `Fetcher` so the core stays testable offline.
     The default `RequestsFetcher` hits the web; `StaticFetcher` replays canned
     pages for deterministic tests.
  2. Inference. `infer_vector_from_evidence` turns collected snippets into a
     ValueVector using transparent keyword-cue scoring. This is intentionally
     simple and inspectable (no hidden ML), mirroring Sim Francisco's stance that
     the estimator must be "a standard, transparent model, not a tuned fudge factor."

COPYRIGHT: we store only short, paraphrased descriptive snippets — never long
verbatim quotes or dialogue. `sanitize_snippet` enforces a hard length cap and
strips obvious quoted dialogue, so collected evidence cannot become a dialogue
dump that the chatbot would parrot.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol
from urllib.parse import quote

from .vector import ValueVector, AXIS_KEYS, AXES


# --- Fetcher abstraction -----------------------------------------------------

class Fetcher(Protocol):
    def get(self, url: str) -> str: ...


class StaticFetcher:
    """Deterministic fetcher for tests: maps URL substrings to canned text."""
    def __init__(self, pages: Dict[str, str]):
        self.pages = pages

    def get(self, url: str) -> str:
        for key, text in self.pages.items():
            if key in url:
                return text
        return ""


# A browser-like User-Agent. Many wikis (notably Fandom, behind Cloudflare)
# answer 403 to an obvious bot UA but serve normally to a browser. Sending a
# browser UA + standard Accept headers is the "UA workaround".
#
# NOTE: presenting as a browser to get past a bot block can run against a site's
# terms of service / robots policy. This is meant for low-volume, personal
# research use; prefer passing exact `source_urls`, or paste sources locally
# (see personas/local/CHARACTER_SOURCES.example.py) when a site disallows bots.
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Safari/537.36")
_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class RequestsFetcher:
    """Live fetcher. Uses `requests` if available; degrades gracefully.

    Sends browser-like headers by default so bot-blocking wikis (e.g. Fandom)
    don't 403. Pass `browser_headers=False` to send only a plain UA.
    """
    def __init__(self, timeout: float = 10.0, pause: float = 0.5,
                 user_agent: str = _BROWSER_UA, browser_headers: bool = True):
        self.timeout = timeout
        self.pause = pause
        self.user_agent = user_agent
        self.browser_headers = browser_headers

    def get(self, url: str) -> str:
        import requests  # imported lazily so the package works without network deps
        time.sleep(self.pause)
        if self.browser_headers:
            headers = dict(_BROWSER_HEADERS, **{"User-Agent": self.user_agent})
        else:
            headers = {"User-Agent": self.user_agent}
        r = requests.get(url, timeout=self.timeout, headers=headers)
        r.raise_for_status()
        return r.text


# --- Snippet sanitation (copyright guard) ------------------------------------

_QUOTE_RE = re.compile(r"[\"\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f].{0,400}?"
                       r"[\"\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f]")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def sanitize_snippet(text: str, max_chars: int = 240) -> str:
    """Strip HTML, remove quoted dialogue, collapse whitespace, hard-cap length.

    Removing quoted spans is the key copyright guard: descriptive prose about a
    character is fine to keep; verbatim dialogue is not.
    """
    text = _TAG_RE.sub(" ", text)
    text = _QUOTE_RE.sub(" ", text)          # drop quoted dialogue
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


# --- Keyword cue tables (transparent, inspectable) ---------------------------
# Each axis has POSITIVE cues (push toward +1) and NEGATIVE cues (push toward -1).
# Matching is substring, case-insensitive. Tunable and fully visible — the
# adversarial critic (see critic.py) is allowed to inspect these.

CUES: Dict[str, Dict[str, List[str]]] = {
    "danger": {
        "pos": ["violent", "lethal", "deadly", "assassin", "kill", "explosive",
                "ruthless", "dangerous", "weapon", "bomb", "merciless", "antagonist"],
        "neg": ["gentle", "harmless", "kind", "innocent", "soft", "peaceful", "timid"],
    },
    "manip": {
        "pos": ["manipulat", "deceive", "deception", "scheming", "calculat",
                "facade", "mask", "trick", "lure", "strategic", "cunning"],
        "neg": ["honest", "sincere", "earnest", "genuine", "straightforward",
                "transparent", "naive"],
    },
    "freedom": {
        "pos": ["escape", "freedom", "free", "run away", "yearn", "longing",
                "normal life", "trapped", "cage", "elope", "liberation"],
        "neg": ["loyal", "duty", "obedient", "submissive", "status quo",
                "conformi", "settled", "content"],
    },
    "impulse": {
        "pos": ["impulsive", "explosive", "reckless", "unpredictable", "sudden",
                "volatile", "rampage", "outburst", "spontaneous"],
        "neg": ["calculated", "deliberate", "patient", "methodical", "controlled",
                "composed", "disciplined", "strategic"],
    },
    "warmth": {
        "pos": ["affection", "tender", "warm", "caring", "love", "empath",
                "protective", "compassion", "kindred", "sincere feelings"],
        "neg": ["cold", "detached", "ruthless", "callous", "distant", "aloof",
                "indifferent", "merciless"],
    },
}

# Topic salience cues: topic name -> trigger words.
SALIENCE_CUES: Dict[str, List[str]] = {
    "freedom and a normal life": ["normal life", "freedom", "escape", "school", "ordinary"],
    "love and connection": ["love", "romance", "connection", "relationship", "intimacy"],
    "duty and mission": ["mission", "duty", "orders", "assignment", "trained"],
    "violence and combat": ["fight", "battle", "combat", "violence", "weapon", "kill"],
    "control and power": ["control", "power", "dominat", "rule", "manipulat"],
    "loyalty": ["loyal", "protect", "devotion", "faithful"],
    "tragedy and the past": ["tragic", "backstory", "past", "childhood", "loss"],
}


def infer_vector_from_evidence(snippets: List[str]) -> ValueVector:
    """Score axes from collected evidence using transparent keyword cues.

    Returns a ValueVector. Each axis score is (pos_hits - neg_hits) normalised
    by total hits, so an axis with no evidence stays at 0 (honest about
    uncertainty rather than guessing).
    """
    blob = " \n ".join(snippets).lower()
    vec = ValueVector()
    for key in AXIS_KEYS:
        pos = sum(blob.count(c.lower()) for c in CUES[key]["pos"])
        neg = sum(blob.count(c.lower()) for c in CUES[key]["neg"])
        total = pos + neg
        if total == 0:
            score = 0.0
        else:
            score = (pos - neg) / total
            # dampen toward 0 when evidence is thin (fewer than 4 hits)
            confidence = min(1.0, total / 4.0)
            score *= confidence
        setattr(vec, key, score)

    sal: Dict[str, float] = {}
    for topic, words in SALIENCE_CUES.items():
        hits = sum(blob.count(w.lower()) for w in words)
        if hits:
            sal[topic] = min(1.0, hits / 5.0)
    vec.saliences = sal
    return vec.clamp()


# --- LLM-based inference (optional) ------------------------------------------
# The keyword table above is transparent and offline, but it counts literal
# words and so misses paraphrase: "presenting romantic interest, later revealed
# as an assassin" plainly implies manipulation + danger, yet trips no cue. When
# a model client is supplied, we let it read the snippets and rate the axes
# directly. Keyword inference remains the default and the fallback.

def infer_vector_llm(snippets: List[str], client, name: str = "the character",
                     model: Optional[str] = None) -> ValueVector:
    """Infer the value vector by asking a model to read the snippets.

    `client` is a ModelClient (its backend may be the API or the `claude` CLI).
    Falls back to keyword inference on any error or unparseable output, so it is
    always safe to enable.
    """
    if not snippets:
        return ValueVector()

    axis_lines = "\n".join(
        f"  {a.key}: -1.0 = {a.neg}; +1.0 = {a.pos}" for a in AXES)
    evidence = "\n".join(f"- {s}" for s in snippets[:20])
    prompt = (
        f"Read these descriptive snippets about the fictional character "
        f"\"{name}\" and rate their personality on each axis from -1.0 to 1.0. "
        f"Base the rating only on what the snippets support; use 0.0 for an axis "
        f"with no evidence.\n\n"
        f"AXES:\n{axis_lines}\n\n"
        f"Also list up to 4 topic saliences (what the character cares about most) "
        f"as name->weight in [0,1].\n\n"
        f"SNIPPETS:\n{evidence}\n\n"
        f"Output ONLY JSON of the form:\n"
        f'{{"danger":0.0,"manip":0.0,"freedom":0.0,"impulse":0.0,"warmth":0.0,'
        f'"saliences":{{"topic":0.0}}}}'
    )
    try:
        from .model import Message, extract_json  # lazy: keep core import-light
        raw = client.complete(
            "You are a precise character-analysis tool. Output only JSON.",
            [Message("user", prompt)], max_tokens=400, model=model)
        data = extract_json(raw)
        return ValueVector.from_dict(data)      # validates axes + saliences, clamps
    except Exception:
        return infer_vector_from_evidence(snippets)


# --- Collection orchestration ------------------------------------------------

@dataclass
class CollectionResult:
    name: str
    urls: List[str] = field(default_factory=list)
    snippets: List[str] = field(default_factory=list)
    inferred: Optional[ValueVector] = None
    contributing_sources: int = 0      # how many URLs actually yielded >=1 snippet


# Templates tried when the caller doesn't pass exact URLs. {slug} = name.
# Fandom is added first (and only) when the source work is known, because its
# subdomain is work-specific and its character pages are the richest source.
DEFAULT_SOURCE_TEMPLATES = [
    "https://tvtropes.org/pmwiki/pmwiki.php/Characters/{slug}",
    "https://en.wikipedia.org/wiki/{slug}",
]


def _slugify_work(work: str) -> str:
    """'Chainsaw Man' -> 'chainsaw-man' (a Fandom subdomain)."""
    return re.sub(r"[^a-z0-9]+", "-", work.lower()).strip("-")


def default_source_urls(name: str, source_work: str = "unknown") -> List[str]:
    """Best-effort source URLs guessed from name (+ work, if known).

    When the work is known we try, in order: the Fandom character page (richest,
    but often Cloudflare-blocked), the *disambiguated* Wikipedia title
    `Name_(Work)` (this is what dodges homonyms like the French town 'Rezé' vs
    the character 'Reze'), TV Tropes, then the bare Wikipedia name as a last
    resort (kept only because the homonym guard will reject it if it's wrong).
    """
    slug = quote(name.replace(" ", "_"))
    urls: List[str] = []
    work = (source_work or "").strip()
    if work and work.lower() != "unknown":
        wslug = _slugify_work(work)
        if wslug:
            urls.append(f"https://{wslug}.fandom.com/wiki/{slug}")
        work_paren = quote(f"{name.replace(' ', '_')}_({work.replace(' ', '_')})")
        urls.append(f"https://en.wikipedia.org/wiki/{work_paren}")
    urls += [t.format(slug=slug) for t in DEFAULT_SOURCE_TEMPLATES]
    return urls


# Words that signal a page is about a *fictional character*, used as a fallback
# disambiguation cue when the work title has no distinctive token to count.
_FICTION_CONTEXT = ("fictional character", "anime", "manga", "light novel",
                    "protagonist", "antagonist", "anti-hero", "anti-villain",
                    "voiced by", "video game", "the series", "character in")

# A page is "about the work" only if a distinctive work token recurs at least
# this many times. A disambiguation hatnote mentions the work once or a few
# times (French town 'Rezé': chainsaw=3); a real character page mentions it
# constantly (Reze (Chainsaw Man): chainsaw=214). The gap is wide, so the exact
# threshold is not delicate.
_SUBJECT_MIN_MENTIONS = 5


def _page_is_about_subject(raw: str, name: str, source_work: str) -> bool:
    """Homonym guard: does this page actually concern the wanted character?

    Returns True (don't filter) when the work is unknown — we have nothing to
    check against. When the work IS known, accept only if a distinctive token of
    the work title recurs (>= _SUBJECT_MIN_MENTIONS), which separates a page
    that is *about* the work from one that merely links to it in a hatnote. If
    the work title has no token long enough to count, fall back to looking for
    fictional-character cues.
    """
    work = (source_work or "").strip().lower()
    if not work or work == "unknown":
        return True
    low = raw.lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", work) if len(t) >= 4]
    if tokens:
        best = max(len(re.findall(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low))
                   for t in tokens)
        return best >= _SUBJECT_MIN_MENTIONS
    return any(p in low for p in _FICTION_CONTEXT)


def collect_evidence(
    name: str,
    fetcher: Fetcher,
    source_urls: Optional[List[str]] = None,
    source_work: str = "unknown",
    max_snippets: int = 12,
    sentence_min_len: int = 40,
) -> CollectionResult:
    """Fetch pages, sanitise into descriptive snippets, infer a vector.

    `source_urls` lets the caller pass exact pages (recommended). If omitted,
    best-effort templated URLs are guessed from the name (+ `source_work`, which
    also enables a Fandom URL). The homonym guard (`_page_is_about_subject`) is
    applied ONLY to guessed URLs — caller-supplied URLs are trusted as-is, so
    explicit pages and offline StaticFetcher tests are never second-guessed.
    """
    guessed = source_urls is None
    if guessed:
        source_urls = default_source_urls(name, source_work)

    result = CollectionResult(name=name, urls=list(source_urls))
    contributing = 0
    for url in source_urls:
        try:
            raw = fetcher.get(url)
        except Exception:
            continue
        if not raw:
            continue
        if guessed and not _page_is_about_subject(raw, name, source_work):
            continue                      # skip homonym/unrelated auto-guessed page
        before = len(result.snippets)
        room = max_snippets - len(result.snippets)
        result.snippets.extend(
            _page_snippets(raw, name, room, sentence_min_len))
        if len(result.snippets) > before:
            contributing += 1
        if len(result.snippets) >= max_snippets:
            break

    result.contributing_sources = contributing
    result.inferred = infer_vector_from_evidence(result.snippets)
    return result


# A page with more sentences than this is treated as a roster/long article, so
# we extract only the wanted character's neighbourhood instead of the first N
# sentences (which on a character-list page belong to OTHER characters).
_ROSTER_SENTENCE_COUNT = 60


def _page_snippets(raw: str, name: str, limit: int,
                   sentence_min_len: int) -> List[str]:
    """Extract up to `limit` clean, descriptive snippets for `name` from a page.

    On a long roster page, restrict to sentences near a mention of the character
    name (their entry) so we don't ingest other characters' descriptions. On a
    short/dedicated page, scan sequentially as before.
    """
    sents = [sanitize_snippet(ch) for ch in
             re.split(r"(?<=[.!?])\s+", _TAG_RE.sub(" ", raw))]

    name_re = re.compile(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])")
    is_roster = len(sents) > _ROSTER_SENTENCE_COUNT
    has_name = any(name_re.search(s.lower()) for s in sents)

    if is_roster and has_name:
        # keep each name-mentioning sentence + the one following it (the blurb)
        keep = set()
        for i, s in enumerate(sents):
            if name_re.search(s.lower()):
                keep.add(i)
                if i + 1 < len(sents):
                    keep.add(i + 1)
        ordered = [sents[i] for i in sorted(keep)]
        # these are name-proximate (relevant by construction), so we don't also
        # require descriptive hints — that would drop the character's own blurb
        # ("A café employee … revealed as a Bomb Devil assassin" has no pronoun).
        require_descriptive = False
    else:
        ordered = sents
        require_descriptive = True

    out: List[str] = []
    for s in ordered:
        if len(s) >= sentence_min_len and not _looks_like_markup(s) \
                and (not require_descriptive or _looks_descriptive(s)):
            out.append(s)
        if len(out) >= limit:
            break
    return out


_DESCRIPTIVE_HINTS = ("she ", "he ", "they ", "her ", "his ", "character",
                      "personality", "is a", "who ", "trait")

# Signatures of CSS/JS that survive tag-stripping on real wiki pages and must
# not become "evidence" (e.g. "function(){var className=…", ".mw-parser-output").
_MARKUP_SIGNS = ("{", "}", "@media", "@import", "function(", "mw-parser-output",
                 "client-js", "px;", "color:", "<", ">", "://")


def _looks_descriptive(s: str) -> bool:
    low = s.lower()
    return any(h in low for h in _DESCRIPTIVE_HINTS)


def _looks_like_markup(s: str) -> bool:
    return any(sign in s for sign in _MARKUP_SIGNS)
