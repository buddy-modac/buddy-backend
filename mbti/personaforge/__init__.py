"""
PersonaForge — character persona engine.

A faithful port of the Sim Francisco hackathon project's core ideas
(github.com/tejasprabhune/simfrancisco) from synthetic-population polling to
fictional-character chatbots:

  Sim Francisco                         PersonaForge
  ---------------------------------     ------------------------------------
  ACS PUMS microdata                    web-collected character evidence
  ValueVector (econ/social/...)         ValueVector (danger/manip/...)
  build_persona_prose                   build_persona_prose
  seeded deterministic agents           seeded deterministic characters
  batched LLM poll                      LLM chat turn
  PUMS-weighted aggregation             rubric scoring
  rubric.yaml + validate gate           ReplyScore + gate
  verifier + adversarial critic         Verifier + AdversarialCritic
  /sf:hillclimb self-correction         ChatEngine retry loop
  sqlite (model,prompt) cache           sqlite (model,prompt) cache
"""
from .vector import ValueVector, AXES, AXIS_KEYS, axis_word
from .persona import CharacterProfile, build_persona_prose, build_system_prompt, char_seed
from .collect import (collect_evidence, infer_vector_from_evidence,
                      infer_vector_llm,
                      StaticFetcher, RequestsFetcher, sanitize_snippet)
from .model import ModelClient, Cache, Message, cache_key, extract_json
from .cli_backend import ClaudeCLIBackend
from .rubric import score_reply, ReplyScore
from .critic import (Verifier, AdversarialCritic, review,
                     CritiqueResult, Objection,
                     LeakagePolicy, LEAKAGE_STRICT, LEAKAGE_BALANCED,
                     LEAKAGE_LENIENT, LEAKAGE_OFF)
from .engine import ChatEngine, Turn
from .memory import (MemoryConfig, manage_history, estimate_tokens,
                     messages_tokens)
from .registry import build_character, save_character, load_character
from .sufficiency import (assess_sufficiency, assess_sufficiency_two_stage,
                          llm_assess_sufficiency, SufficiencyThresholds,
                          SufficiencyReport, InsufficientEvidenceError)
from .korean import stem_tokens, has_hangul, backend_name as korean_backend
from .mbti import (build_mbti, type_to_vector, build_mbti_prose, MBTIVector,
                   ALL_TYPES, STACKS, FUNCTIONS, parse_type, derive_saliences)
from .provenance import Provenance, SourceRef, mbti_theory_sources
from .survey import (Item, load_items, theory_responder, make_llm_responder,
                     aggregate_profile, profile_to_vector, IntensityProfile)
from .identify import (identify_mbti, identify_character, evaluate_mbti_types,
                       IdentificationResult, IdentificationReport, DEFAULT_PROBES)
# Phase 2 — MBTI as a communication-style layer on a capable, transparent assistant
from .style import (build_style_guide, build_behavioral_style, FUNC_COMM, AXIS_COMM,
                    FUNC_BEHAVIOR, AXIS_BEHAVIOR)
from .assistant_prompt import build_assistant_system_prompt, BASE_ASSISTANT, PRIORITIES
from .guardrails import detect_crisis, safety_overlay, wants_plain, wants_style_back
from .tools import Tool, MockWeatherTool, MockNewsTool, tool_registry, tools_catalog
from .assistant import AssistantEngine, AssistantTurn

__version__ = "1.0.0"

__all__ = [
    "ValueVector", "AXES", "AXIS_KEYS", "axis_word",
    "CharacterProfile", "build_persona_prose", "build_system_prompt", "char_seed",
    "collect_evidence", "infer_vector_from_evidence", "infer_vector_llm",
    "StaticFetcher", "RequestsFetcher", "sanitize_snippet",
    "ModelClient", "Cache", "Message", "cache_key", "extract_json",
    "ClaudeCLIBackend",
    "score_reply", "ReplyScore",
    "Verifier", "AdversarialCritic", "review", "CritiqueResult", "Objection",
    "LeakagePolicy", "LEAKAGE_STRICT", "LEAKAGE_BALANCED", "LEAKAGE_LENIENT",
    "LEAKAGE_OFF",
    "ChatEngine", "Turn",
    "MemoryConfig", "manage_history", "estimate_tokens", "messages_tokens",
    "build_character", "save_character", "load_character",
    "assess_sufficiency", "assess_sufficiency_two_stage", "llm_assess_sufficiency",
    "SufficiencyThresholds", "SufficiencyReport", "InsufficientEvidenceError",
    "stem_tokens", "has_hangul", "korean_backend",
    "build_mbti", "type_to_vector", "build_mbti_prose", "MBTIVector",
    "ALL_TYPES", "STACKS", "FUNCTIONS", "parse_type", "derive_saliences",
    "Provenance", "SourceRef", "mbti_theory_sources",
    "Item", "load_items", "theory_responder", "make_llm_responder",
    "aggregate_profile", "profile_to_vector", "IntensityProfile",
    "identify_mbti", "identify_character", "evaluate_mbti_types",
    "IdentificationResult", "IdentificationReport", "DEFAULT_PROBES",
    "build_style_guide", "build_behavioral_style", "FUNC_COMM", "AXIS_COMM",
    "FUNC_BEHAVIOR", "AXIS_BEHAVIOR",
    "build_assistant_system_prompt", "BASE_ASSISTANT", "PRIORITIES",
    "detect_crisis", "safety_overlay", "wants_plain", "wants_style_back",
    "Tool", "MockWeatherTool", "MockNewsTool", "tool_registry", "tools_catalog",
    "AssistantEngine", "AssistantTurn",
]
