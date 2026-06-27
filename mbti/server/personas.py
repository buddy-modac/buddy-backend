"""Display-friendly persona list for /personas.

NOTE: 이 한 줄 설명은 *표시용*일 뿐이다. 실제 AI 동작은 Phase 2의
`build_assistant_system_prompt`(인지기능 스택 기반 3블록 프롬프트)가 결정한다.
유효 페르소나 = personaforge.ALL_TYPES (16개)와 동일.
"""
from personaforge import ALL_TYPES

MBTI_DESC = {
    "INTJ": "전략적이고 논리적이며 간결하게 핵심만 전달하는",
    "INTP": "분석적이고 호기심 많으며 원리를 파고드는",
    "ENTJ": "단호하고 목표지향적이며 결론부터 말하는",
    "ENTP": "재치있고 아이디어가 넘치며 토론을 즐기는",
    "INFJ": "통찰력 있고 따뜻하며 의미를 짚어주는",
    "INFP": "감성적이고 진심을 담아 부드럽게 말하는",
    "ENFJ": "공감적이고 격려하며 사람을 챙기는",
    "ENFP": "따뜻하고 활기차며 비유를 잘 쓰는",
    "ISTJ": "정확하고 체계적이며 사실 위주로 말하는",
    "ISFJ": "세심하고 배려깊으며 차분히 설명하는",
    "ESTJ": "현실적이고 효율적이며 명확하게 지시하는",
    "ESFJ": "친근하고 사교적이며 따뜻하게 안내하는",
    "ISTP": "실용적이고 군더더기 없이 핵심만 말하는",
    "ISFP": "온화하고 감각적이며 부담없이 표현하는",
    "ESTP": "활동적이고 직설적이며 생동감 있게 말하는",
    "ESFP": "쾌활하고 표현이 풍부하며 즐겁게 말하는",
}

VALID_PERSONAS = set(ALL_TYPES)            # 16 — single source of truth
VALID_MODES = {"translate", "explain"}

# safety: 표시 dict가 16종과 어긋나지 않게
assert VALID_PERSONAS == set(MBTI_DESC), "MBTI_DESC와 ALL_TYPES 불일치"

# MBTI 궁합 Top-3 (16personalities/인지기능 골든페어 기준). 1순위=보완형 골든페어.
COMPATIBILITY = {
    "INTJ": ["ENFP", "ENTP", "INFJ"],
    "INTP": ["ENTJ", "ENFJ", "INFJ"],
    "ENTJ": ["INTP", "INFP", "ENFP"],
    "ENTP": ["INFJ", "INTJ", "ENFJ"],
    "INFJ": ["ENFP", "ENTP", "INTJ"],
    "INFP": ["ENFJ", "ENTJ", "INFJ"],
    "ENFJ": ["INFP", "ISFP", "INTP"],
    "ENFP": ["INTJ", "INFJ", "ENTJ"],
    "ISTJ": ["ESFP", "ESTP", "ISFJ"],
    "ISFJ": ["ESTP", "ESFP", "ESTJ"],
    "ESTJ": ["ISFP", "ISTP", "ESFJ"],
    "ESFJ": ["ISTP", "ISFP", "ESTJ"],
    "ISTP": ["ESFJ", "ESTJ", "ENFJ"],
    "ISFP": ["ESTJ", "ESFJ", "ENFJ"],
    "ESTP": ["ISFJ", "ISTJ", "ESFP"],
    "ESFP": ["ISTJ", "ISFJ", "ESTP"],
}

# safety: 16종 전부 · 각 3개 · 자기 자신 제외 · 유효 타입 · 중복 없음
assert set(COMPATIBILITY) == VALID_PERSONAS, "COMPATIBILITY 키가 16종과 불일치"
for _t, _lst in COMPATIBILITY.items():
    assert len(_lst) == 3 and len(set(_lst)) == 3, f"{_t} 궁합은 서로 다른 3개여야"
    assert _t not in _lst, f"{_t} 궁합에 자기 자신 포함 불가"
    assert all(x in VALID_PERSONAS for x in _lst), f"{_t} 궁합에 잘못된 타입"


def compatibility_for(persona: str):
    """궁합 Top-3 → [{rank, type, desc}]. 모르는 타입이면 빈 리스트."""
    return [{"rank": i, "type": t, "desc": MBTI_DESC[t]}
            for i, t in enumerate(COMPATIBILITY.get(persona, []), 1)]
