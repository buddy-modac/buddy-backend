"""
Character registry + one-call pipeline.

`build_character` is the high-level entry point that runs the whole Sim
Francisco-style pipeline for a character:

    collect evidence (web)  ->  infer vector  ->  finalize persona (seeded)
                                                      |
                                                      v
                                            CharacterProfile (ready to chat)

Characters can be saved to / loaded from JSON files (the analogue of swapping
`rubric.yaml` to retarget Sim Francisco on a new problem — here you swap a
character file to retarget the whole engine on a new character).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import List, Optional

from .vector import ValueVector
from .persona import CharacterProfile
from .collect import (collect_evidence, Fetcher, infer_vector_from_evidence,
                      infer_vector_llm)
from .sufficiency import (assess_sufficiency, assess_sufficiency_two_stage,
                          SufficiencyThresholds,
                          SufficiencyReport, InsufficientEvidenceError)


def build_character(
    name: str,
    source_work: str = "unknown",
    identity: str = "",
    speech_style: str = "natural conversational",
    languages: Optional[List[str]] = None,
    fetcher: Optional[Fetcher] = None,
    source_urls: Optional[List[str]] = None,
    manual_vector: Optional[ValueVector] = None,
    global_seed: int = 42,
    jitter: float = 0.0,
    require_sufficient: bool = False,
    thresholds: Optional[SufficiencyThresholds] = None,
    sufficiency_client=None,
    require_llm: bool = False,
    inference_client=None,
) -> CharacterProfile:
    """Run the full pipeline and return a ready-to-chat CharacterProfile.

    If `fetcher` is given, evidence is collected from the web (or canned pages)
    and the vector is inferred from it. If `manual_vector` is given it overrides
    inference. With neither, the vector starts at zero (a blank slate).

    `jitter` (default 0.0 = off) optionally adds seeded per-axis variation; see
    CharacterProfile.finalize for why it is off by default for single characters.
    Use it only to generate several subtly different takes on the same character.

    Evidence sufficiency
    --------------------
    When evidence was collected, it is graded and the report is attached to
    `profile.sufficiency`. A near-zero vector built from two thin sentences is
    "we don't know this character", not "a neutral character" — the gate makes
    that distinction explicit.

    Two stages:
      * Stage 1 (always): keyword gate `assess_sufficiency` — volume, source
        diversity, axis coverage, signal, conflict. Offline, no API.
      * Stage 2 (optional): pass `sufficiency_client` (a ModelClient) to also ask
        the model "can you portray this character from this evidence?". Runs only
        if stage 1 passed (cheap-filter first). Catches the case stage 1 misses:
        lots of text that is plot summary, not characterisation.

      * require_sufficient=False (default): build anyway, attach the report.
      * require_sufficient=True: raise InsufficientEvidenceError if the gate fails.
      * require_llm=True: also fail if the LLM verdict is unavailable (fail-closed).

    A `manual_vector` bypasses the gate (the caller asserted the personality
    directly, so there is no evidence to judge).
    """
    evidence: List[str] = []
    inferred: Optional[ValueVector] = None
    report: Optional[SufficiencyReport] = None
    collected_urls: List[str] = []

    if fetcher is not None:
        result = collect_evidence(name, fetcher, source_urls=source_urls,
                                  source_work=source_work)
        evidence = result.snippets
        # LLM inference reads the snippets as language (catches paraphrase the
        # keyword table misses); keyword inference stays the default/fallback.
        if inference_client is not None:
            inferred = infer_vector_llm(result.snippets, inference_client,
                                        name=name)
            result.inferred = inferred
        else:
            inferred = result.inferred
        collected_urls = result.urls
        report = assess_sufficiency_two_stage(
            result, name, client=sufficiency_client,
            thresholds=thresholds, require_llm=require_llm)
        if require_sufficient and manual_vector is None and not report.sufficient:
            raise InsufficientEvidenceError(report)

    vector = manual_vector or inferred or ValueVector()

    profile = CharacterProfile(
        name=name,
        source_work=source_work,
        identity=identity,
        vector=vector,
        speech_style=speech_style,
        languages=languages or ["en"],
        evidence=evidence,
    )
    profile.finalize(global_seed=global_seed, jitter=jitter)
    profile.sufficiency = report
    profile.provenance = _character_provenance(
        manual_vector is not None, collected_urls, len(evidence))
    return profile


def _character_provenance(is_manual: bool, urls: List[str], n_snippets: int):
    """Build provenance for a character persona."""
    from .provenance import Provenance, SourceRef, CHARACTER_COPYRIGHT_NOTE
    if is_manual:
        return Provenance(
            persona_kind="character",
            method="vector asserted manually by caller (no web inference)",
            sources=[SourceRef("caller-provided vector", None, kind="derived",
                               note="personality specified directly, not collected")],
        )
    prov = Provenance(
        persona_kind="character",
        method="vector inferred from web-collected, paraphrased evidence",
        snippets_used=n_snippets,
        copyright_note=CHARACTER_COPYRIGHT_NOTE,
    )
    for u in urls:
        prov.add(u, url=u, kind="web", note="fetched; quotes stripped at collection")
    if not urls:
        prov.add("no sources fetched", None, kind="derived",
                 note="vector is empty/neutral")
    return prov


def save_character(profile: CharacterProfile, path: str) -> None:
    # save the PRE-jitter base vector so load+finalize reproduces the same
    # jittered vector exactly (idempotent round-trip).
    base = profile._base_vector or profile.vector
    data = {
        "name": profile.name,
        "source_work": profile.source_work,
        "identity": profile.identity,
        "speech_style": profile.speech_style,
        "languages": profile.languages,
        "evidence": profile.evidence,
        "vector": base.to_dict(),
    }
    # MBTI personas carry their identity in `.mbti` + a hand-rendered prose, not
    # in the (empty) ValueVector — persist both so they round-trip intact
    # (otherwise load would rebuild a generic character prose and lose the type).
    if profile.mbti is not None:
        data["mbti"] = profile.mbti.to_dict()
        data["persona_prose"] = profile.persona_prose
    if profile.provenance is not None:
        data["provenance"] = profile.provenance.to_dict()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_character(path: str, global_seed: int = 42) -> CharacterProfile:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    profile = CharacterProfile(
        name=data["name"],
        source_work=data.get("source_work", "unknown"),
        identity=data.get("identity", ""),
        vector=ValueVector.from_dict(data.get("vector", {})),
        speech_style=data.get("speech_style", "natural conversational"),
        languages=data.get("languages", ["en"]),
        evidence=data.get("evidence", []),
    )
    # Restore an MBTI persona (vector + prose) BEFORE finalize, so finalize keeps
    # the saved prose instead of rebuilding a generic character one.
    if "mbti" in data:
        from .mbti import MBTIVector
        profile.mbti = MBTIVector.from_dict(data["mbti"])
        profile.persona_prose = data.get("persona_prose", "")
    profile.finalize(global_seed=global_seed)
    if "provenance" in data:
        from .provenance import Provenance
        profile.provenance = Provenance.from_dict(data["provenance"])
    return profile
