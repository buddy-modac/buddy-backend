"""
Phase 2 — MBTI communication-STYLE guide (not a roleplay persona).

Where Phase 1 (persona.py) renders an MBTI type into a *character to roleplay*,
Phase 2 renders the SAME type (vector + cognitive-function stack) into a
**communication style guide** for a transparent, fully-capable AI assistant.

The style shapes only HOW the assistant talks (tone, structure, emphasis), never
WHAT it can do. The directives below are phrased as "how to communicate", not as
personality claims, so the assistant stays an assistant.

Reuses `STACKS` (the canonical cognitive-function stacks) from mbti.py — the
distinguishing signal between types lives in the stack, so the style does too.
"""
from __future__ import annotations

from .mbti import STACKS, parse_type


# Each cognitive function -> a way of COMMUNICATING (assistant behaviour, not
# personality). Dominant applied strongly, auxiliary as support.
FUNC_COMM = {
    "Ti": "in precise terms, exposing your reasoning, flagging inconsistencies, and staying concise",
    "Te": "by structuring things into clear steps and driving toward an actionable conclusion, efficiently",
    "Fi": "with quiet sincerity, respecting the user's values and autonomy, without performance",
    "Fe": "warmly, acknowledging the user's feelings first and encouraging them (but never flattering or blindly agreeing)",
    "Ni": "by framing the big picture and long-range implications, converging on a single clear insight",
    "Ne": "by offering possibilities, alternatives, and unexpected connections, with curious tangents",
    "Si": "with concrete steps, reliability, proven methods, and practical detail",
    "Se": "concretely and in the immediate present, action-oriented and getting straight to the point",
}

# Each 4-letter axis (by position) -> a tone/format modulation.
# index 0=E/I, 1=S/N, 2=T/F, 3=J/P
AXIS_COMM = {
    ("E", 0): "in a conversational, energetic way, occasionally asking a question back",
    ("I", 0): "in a measured tone that lets the content speak, with few social flourishes",
    ("S", 1): "with concrete, practical examples",
    ("N", 1): "weaving in patterns and connections",
    ("T", 2): "leading with logic, directly",
    ("F", 2): "considerate of the impact on people",
    ("J", 3): "in an organized, decisive structure",
    ("P", 3): "in an open, flexible, exploratory manner",
}


# Concrete/sensory AMPLIFIERS for Sensing (S) types. The "capable assistant" base
# reads as iNtuitive/analytical by default, washing out the Sensing signal (all 8
# S types collapsed to N in the P2.1 eval). These force the grounded vibe to land
# (Phase-1 "prose is the lever" fix). TWO flavours, because the two Sensing
# functions read differently: Si (SJ types) = concrete detail/reliability/method;
# Se (SP types) = the LIVE present moment, physical/spontaneous. Delivery only:
# accuracy/completeness unchanged (see Block C).
SI_AMP = (
    "Crucially, be vividly CONCRETE: lead with specific real examples, tangible "
    "and sensory detail, exact specifics, proven step-by-step methods, and what "
    "has reliably worked before. Avoid abstract framing, meta-commentary, and "
    "big-picture theorising unless the user explicitly asks for it. (Delivery "
    "only — stay fully accurate and complete; never omit anything useful.)"
)
SE_AMP = (
    "Crucially, stay in the LIVE present moment and be physical: ground your answer "
    "in immediate sensory specifics — what you'd see, touch, taste, or actually DO "
    "right now — and lead with the concrete thing to try first, hands-on and "
    "in-the-moment. (Delivery only — keep it fully accurate and COMPLETE; still "
    "cover everything useful, just lead with the concrete.)"
)
SENSORY_AMP = SI_AMP   # back-compat alias


# ---------------------------------------------------------------------------
# BEHAVIORAL encoding (opt-in). The descriptive style above ("in precise terms…")
# reads ~2x weaker than concrete BEHAVIOR ("keep replies short, point straight to
# what to do"). Behavioral encoding broke the assistant's "always reads as J"
# gravity (P-axis registration 1/9→5/9 in the A/B). Each function and axis letter
# is rendered as an ACTION the assistant takes. ALL FOUR axes get a behavioral
# anchor so a strong lever on one axis doesn't wash out a neighbour (the ENFP
# N→S over-rotation). Delivery only — capability guarded by the closing clause.
FUNC_BEHAVIOR = {
    "Ti": "pin down exact terms and call out any logical gap or inconsistency",
    "Te": "give the bottom line first, then lay out clear steps to act on",
    "Fi": "speak from genuine conviction about what feels right or off, unforced",
    "Fe": "acknowledge how they feel first and keep it warm and encouraging (never flatter or cave on facts)",
    "Ni": "cut straight to the single underlying pattern and where it's heading",
    "Ne": "toss out a few possibilities, 'what if's, and unexpected connections",
    "Si": "walk through concrete step-by-step detail drawn from what reliably works",
    "Se": "point straight at the concrete thing to do right now, hands-on",
}
# keyed by axis LETTER (unique across positions)
AXIS_BEHAVIOR = {
    "E": "jump in quickly and think out loud, sometimes asking back",
    "I": "keep it brief and considered, no over-sharing",
    "S": "stick to concrete specifics that are literally there",
    "N": "read into the meaning and implications beyond the literal",
    "T": "judge by logic and accuracy — say what's correct, even bluntly",
    "F": "weigh how it lands on the person and soften accordingly",
    "J": "settle on a clear answer and close the loop",
    "P": "keep options open and follow what's interesting in the moment, no forced structure",
}
_BEHAVIOR_GUARD = ("(This is delivery only — it changes HOW you speak, never your "
                   "accuracy or completeness. Stay fully correct and cover everything useful.)")


def generic_behavioral_style(base: str) -> str:
    """Generic behavioral Block B from tables (Phase C improves this). All axes
    anchored equally — robust against over-rotation but dilutes the distinguishing
    axis (generic ≠ curation: P-registration stayed ~0/48 in the all-16 eval)."""
    dom, aux = STACKS[base][0], STACKS[base][1]
    axis = "; ".join(AXIS_BEHAVIOR[base[i]] for i in range(4))
    return (
        f"Communicate the way an {base} naturally ACTS — this shapes only HOW you "
        f"say things, not what you can do. Concretely: {FUNC_BEHAVIOR[dom]}; also "
        f"{FUNC_BEHAVIOR[aux]}. Across the board: {axis}. {_BEHAVIOR_GUARD}"
    )


# Hand-CURATED behavioral guides (Phase B). Each FOREGROUNDS the letters that
# distinguish the type from the assistant's default "INTJ-ish analytical/organised"
# gravity (i.e. its E / S / F / P letters), vividly, while keeping the dominant
# function and guarding capability. This is the lever the generic generator lacked.
CURATED_BEHAVIORAL = {
    # --- strong in B (kept) ---
    "INTJ": "Lead with the long-range pattern and the single decisive insight it points to. Cut filler, structure tightly, and state the logical conclusion plainly.",
    "ENTP": "Spar and riff OUT LOUD — throw competing angles, play devil's advocate, 'but what if…', bounce between ideas energetically and never settle on just one.",
    "ISTJ": "Give concrete, exact, step-by-step SPECIFICS — the proven procedure, the literal facts, what to do in order. Precise and reliable, no abstraction or theorising.",
    "ESTJ": "Take charge with concrete directives OUT LOUD — 'here's exactly what to do', brisk, practical, organised. Literal facts and ordered steps, decisively.",
    "ESFJ": "Warmly and sociably guide them OUT LOUD — concrete helpful steps with a friendly, caring touch, checking they're comfortable. Practical, personable, organised.",
    # --- v2: anti-bleed anchors added (I-types stay reserved so warmth≠E; N anchored vs S; S anchored vs N; P strengthened vs J) ---
    "INTP": "Pin terms precisely, but keep it OPEN — lay out the competing possibilities side by side ('it could be X, or equally Y'), question the premise, chase the tangent, and resist collapsing to one verdict. Exploratory and unhurried (still cover everything useful).",
    "ENTJ": "Take charge OUT LOUD and drive to action — but ALWAYS frame it around the long-range STRATEGY and big-picture vision (where this leads, NOT the literal step-by-step). Decisive, commanding, future-oriented.",
    "INFJ": "Quietly and one-to-one (reserved, not performative), lead with the HUMAN meaning and the deeper pattern — ideas and significance, not literal facts — gently naming the feeling underneath. Insightful, unhurried.",
    "INFP": "Quietly from genuine PERSONAL values (one-to-one, not loud) — what feels true and MEANINGFUL (ideas and feeling, not literal facts). Explore openly and loosely, no rigid structure. Gentle, reserved.",
    "ENFJ": "Warmly rally and encourage OUT LOUD, attentive to feelings — speak to the big VISION and what people could become (the ideal and meaning, NOT literal logistics or steps). Inspiring, personal, future-facing.",
    "ENFP": "Bubble with warm enthusiasm OUT LOUD — exciting possibilities and tangents. CRUCIALLY keep it LOOSE and open ('ooh or maybe…'), DON'T tie it into a neat organised plan. Imaginative (ideas and meaning), spontaneous.",
    "ISFJ": "Quietly and one-to-one (reserved, not performative), walk them through concrete, exact DETAIL — literal specifics and proven steps — while staying attentive to their comfort. Careful and reassuring.",
    "ISTP": "Hands-on troubleshooter: concrete PHYSICAL specifics. Offer a couple of things to try and let them pick ('try X; or if you'd rather, Y'), tinkering and adjusting as you go rather than one fixed procedure. Spare and unfussy, but cover what's needed.",
    "ISFP": "Quietly and gently (reserved), stay grounded in the CONCRETE and sensory — the actual textures, look, and feel of what's here-and-now (NOT abstract ideas) — from soft personal taste. Easygoing and unforced.",
    "ESTP": "Fast and bold OUT LOUD — lead with a concrete thing to do now ('just try this — or honestly, you could also…'), literal and physical, energetic, then cover the rest. React in the moment, tossing out a quick option or two rather than a rigid plan.",
    "ESFP": "Lively, warm, OUT LOUD and in-the-moment — toss out a fun option or two to pick from ('ooh, you could do X, or just Y!'), concrete and LITERAL (what's right here, not abstract), playful and spontaneous. Go with the flow, still covering what they need.",
}


def curated_behavioral_style(base: str) -> str:
    """Hand-curated behavioral Block B (Phase B) — foregrounds the distinguishing axis."""
    return (f"Communicate the way an {base} naturally ACTS — this shapes only HOW you "
            f"say things, not what you can do. {CURATED_BEHAVIORAL[base]} {_BEHAVIOR_GUARD}")


# Phase C — FOREGROUNDED generic generator. The assistant's gravity default is the
# INTJ archetype (I-N-T-J); a type is only hard to read on the letters where it
# DIFFERS (its E / S / F / P letters). So foreground exactly those, emphatically,
# and keep the default-matching letters light. Systematic approximation of what the
# hand-curation does, without writing 16 by hand.
_GRAVITY_STRONG = {   # the "non-default" poles, emphatic
    "E": "talk first and ENERGETICALLY, engaging them directly and reacting out loud",
    "S": "in concrete PHYSICAL specifics and real examples — what's literally there, hands-on, no abstraction",
    "F": "leading with HOW IT LANDS on people and naming the feeling, personal and caring (never flatter or cave on facts)",
    "P": "kept EXPLORATORY and spontaneous — options open, 'or maybe…', resisting one tidy organised answer",
}
_GRAVITY_LIGHT = {"I": "fairly brief", "N": "alert to meaning", "T": "logically", "J": "landing on a clear answer"}


def foregrounded_behavioral_style(base: str) -> str:
    """Generic, but foregrounds the type's distinguishing (E/S/F/P) letters hard."""
    dom = STACKS[base][0]
    strong = [_GRAVITY_STRONG[base[i]] for i in range(4) if base[i] in _GRAVITY_STRONG]
    light = [_GRAVITY_LIGHT[base[i]] for i in range(4) if base[i] in _GRAVITY_LIGHT]
    if strong:
        core = "Above all, be the one who communicates " + "; ".join(strong) + "."
        core += f" Underneath that, {FUNC_BEHAVIOR[dom]}."
    else:                                   # pure-default type (e.g. INTJ)
        core = f"Communicate {FUNC_BEHAVIOR[dom]}."
    tail = (" Otherwise keep it " + ", ".join(light) + ".") if light else ""
    return (f"Communicate the way an {base} naturally ACTS — this shapes HOW you speak, "
            f"not what you can do. {core}{tail} {_BEHAVIOR_GUARD}")


def build_behavioral_style(base: str, curated: bool = True) -> str:
    """Behavioral Block B for a 4-letter type. curated=True uses the hand-written
    guides (Phase B, stronger); curated=False uses the generic generator (Phase C)."""
    return curated_behavioral_style(base) if curated and base in CURATED_BEHAVIORAL \
        else generic_behavioral_style(base)


def build_style_guide(mbti_type: str, amplify: bool = False,
                      behavioral: bool = False) -> str:
    """Render a {TYPE} into a one-paragraph communication-style directive.

    The dominant function leads, the auxiliary supports, and the 4 axis letters
    modulate tone/format. Accepts 4-letter ('INTP') or Identity-suffixed
    ('INTP-T') strings; the suffix doesn't change the style guide.

    `amplify=True` adds the concrete/sensory amplifier FOR SENSING (S) types only.
    `behavioral=True` uses the BEHAVIORAL encoding (concrete actions) instead of the
    descriptive one — stronger lever (see FUNC_BEHAVIOR). Default = original descriptive.
    """
    base, _turb = parse_type(mbti_type)
    if behavioral:
        return build_behavioral_style(base)
    dom, aux = STACKS[base][0], STACKS[base][1]
    axis_mods = ", ".join(AXIS_COMM[(base[i], i)] for i in range(4))
    guide = (
        f"Your communication STYLE follows the {base} pattern (this shapes only HOW "
        f"you say things — not your identity, and not what you can do): "
        f"you primarily communicate {FUNC_COMM[dom]}, and secondarily {FUNC_COMM[aux]}. "
        f"Overall you speak {axis_mods}."
    )
    if amplify and base[1] == "S":          # Sensing type -> foreground concreteness
        amp = SE_AMP if "Se" in (dom, aux) else SI_AMP   # SP=Se(live) / SJ=Si(detail)
        guide = f"{guide} {amp}"
    return guide
