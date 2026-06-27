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
