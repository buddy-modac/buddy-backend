"""
Provenance — where each persona's personality came from.

Every persona, character or MBTI, carries a `Provenance` recording exactly what
its vector was built from. This makes the honest answer to "where did you get
this?" a first-class, inspectable part of the profile rather than something
buried in code comments.

Two persona kinds, two provenance shapes:

  * CHARACTER personas cite the **web pages** that were fetched, the snippets
    actually used (paraphrased, dialogue stripped), and note that quotes were
    removed for copyright. The URLs are the citable source.

  * MBTI personas cite **theoretical sources**, because there is nothing to
    scrape — the 16 types are a fixed framework:
      - the 5-axis structure (Mind/Energy/Nature/Tactics/Identity) follows the
        16Personalities NERIS model (public model structure, not copied text);
      - the cognitive-function stack follows the Harold Grant model (Jungian
        lineage; not official MBTI, and theoretically contested);
      - the saliences are DERIVED from the standard meaning of each cognitive
        function, not copied from any type-description site.

Citing structure/theory is fine; copying a site's prose is not. CHARACTER
collection already strips quoted dialogue; MBTI never ingests third-party prose
at all (it derives from function definitions), so neither path reproduces
copyrighted descriptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SourceRef:
    """A single cited source."""
    label: str                      # human-readable name
    url: Optional[str] = None       # link if it is a web source
    kind: str = "web"               # "web" | "theory" | "derived"
    note: str = ""                  # how it was used / caveat


@dataclass
class Provenance:
    """Full provenance for one persona."""
    persona_kind: str               # "character" | "mbti"
    method: str                     # one-line description of how the vector was built
    sources: List[SourceRef] = field(default_factory=list)
    snippets_used: int = 0          # for character: how many evidence snippets fed the vector
    copyright_note: str = ""        # how copyrighted material was avoided

    def add(self, label: str, url: Optional[str] = None,
            kind: str = "web", note: str = "") -> "Provenance":
        self.sources.append(SourceRef(label=label, url=url, kind=kind, note=note))
        return self

    def render(self) -> str:
        """Human-readable provenance block (for CLI / docs / 'where from?')."""
        lines = [f"Persona kind : {self.persona_kind}",
                 f"Method       : {self.method}"]
        if self.snippets_used:
            lines.append(f"Evidence used: {self.snippets_used} snippet(s)")
        if self.sources:
            lines.append("Sources:")
            for s in self.sources:
                tag = {"web": "🔗", "theory": "📖", "derived": "⚙"}.get(s.kind, "•")
                link = f" — {s.url}" if s.url else ""
                note = f"  ({s.note})" if s.note else ""
                lines.append(f"  {tag} {s.label}{link}{note}")
        if self.copyright_note:
            lines.append(f"Copyright    : {self.copyright_note}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "persona_kind": self.persona_kind,
            "method": self.method,
            "snippets_used": self.snippets_used,
            "copyright_note": self.copyright_note,
            "sources": [{"label": s.label, "url": s.url, "kind": s.kind, "note": s.note}
                        for s in self.sources],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Provenance":
        prov = cls(
            persona_kind=d.get("persona_kind", ""),
            method=d.get("method", ""),
            snippets_used=int(d.get("snippets_used", 0) or 0),
            copyright_note=d.get("copyright_note", ""),
        )
        for s in d.get("sources", []):
            prov.sources.append(SourceRef(
                label=s.get("label", ""), url=s.get("url"),
                kind=s.get("kind", "web"), note=s.get("note", "")))
        return prov


# --- canonical theory sources for MBTI (reused across all 16 types) ----------

def mbti_theory_sources() -> List[SourceRef]:
    """The fixed theoretical references behind every MBTI persona."""
    return [
        SourceRef(
            "16Personalities / NERIS model (5-axis structure incl. Assertive–Turbulent)",
            "https://www.16personalities.com/articles/our-theory",
            kind="theory",
            note="public model structure followed; no profile text copied"),
        SourceRef(
            "Harold Grant cognitive-function stack (Jungian lineage)",
            "https://en.wikipedia.org/wiki/Cognitive_functions",
            kind="theory",
            note="determines dom/aux/tert/inf; not official MBTI, theoretically contested"),
        SourceRef(
            "C. G. Jung, Psychological Types (1921)",
            None,
            kind="theory",
            note="origin of the eight cognitive functions"),
        SourceRef(
            "Saliences derived from standard cognitive-function meanings",
            None,
            kind="derived",
            note="generated from function definitions, not copied from type-description sites"),
    ]


CHARACTER_COPYRIGHT_NOTE = (
    "Quoted dialogue stripped at collection; vector inferred from paraphrased "
    "descriptive snippets only. No verbatim canon reproduced.")

MBTI_COPYRIGHT_NOTE = (
    "No third-party type descriptions ingested; saliences derived from function "
    "theory. Type framework is a public structure, not a copyrighted text.")
