# 모델 비교 종합 매트릭스 — Claude(Haiku) vs OpenAI(gpt-5.4-mini) (2026-06-27)

스크립트: `benchmarks/run_full_matrix.py` (K=5). 작업 정확도·MBTI 식별 모두 중립 심판 = Sonnet.
v2 동적 캡(입력 길이 비례) 적용 후 측정. 목적: **시나리오별 모델 매핑**.

## [A] 작업 품질 — 크기 × mode × detail (속도ms / 정확도 /5)
| size | mode·detail | Claude | GPT mini | 추천 |
|---|---|---|---|---|
| light | translate brief | 1624 / 5.0 | **1324** / 5.0 | GPT |
| light | translate full | 4634 / 2.4⚠ | **2026** / 2.0⚠ | GPT |
| light | explain brief | 1947 / 5.0 | **1492** / 5.0 | GPT |
| light | explain full | 5906 / 4.8 | **4055** / 5.0 | GPT |
| dense | translate brief | 4150 / 4.0 | **2298** / 4.4 | GPT |
| dense | translate full | 5972 / 5.0 | **3839** / 4.9 | GPT |
| dense | explain brief | 3169 / 4.9 | **2225** / 4.7 | GPT |
| dense | explain full | 9613 / 4.9 | **7582** / 5.0 | GPT |

- **GPT mini가 8/8 셀 속도 우위, 정확도는 전 구간 동급(둘 다 높음).**
- **동적 캡 효과 확인**: dense translate 정확도 1.5(이전) → 4.0~4.9(이번). 번역 안 잘림.
- ⚠️ **light translate full은 둘 다 낮음(2.x)** — 짧은 텍스트에 "자세히"가 붙어 번역 충실도↓. → translate는 brief 고정.

## [B] MBTI 페르소나 재현도 — 블라인드 식별 (exact / 축점수 /1)
| MBTI | Claude | GPT mini | 우세 |
|---|---|---|---|
| INTJ | 5/5 · 1.00 | 5/5 · 1.00 | = |
| INTP | 1/5 · 0.80 | 2/5 · 0.85 | GPT |
| **ENFP** | **4/5 · 0.95** | 0/5 · 0.60 | **Claude** |
| **ENFJ** | **3/5 · 0.90** | 0/5 · 0.70 | **Claude** |
| ISTP | 1/5 · 0.65 | 1/5 · 0.55 | Claude |
| ISFP | 0/5 · 0.55 | 0/5 · 0.55 | = |
| ESTJ | 0/5 · 0.65 | 0/5 · 0.50 | Claude |
| ESFJ | 0/5 · 0.60 | 0/5 · 0.55 | Claude |

- **페르소나는 Claude 우세 (5유형 vs GPT 1).** 특히 **감정형(ENFP·ENFJ)에서 격차 큼**(0.95/0.90 vs 0.60/0.70) — GPT mini는 따뜻한 F 페르소나를 잘 못 살림.
- 분석형(INTJ 동률, INTP GPT 약우세)은 비슷.
- 약한 유형(ISFP/ESxJ)은 둘 다 낮음 = Phase2 스타일레이어 자체 한계(어시스턴트 중력).

## 결론 — 트레이드오프
- **작업 속도·정확도** → **GPT mini** (전 구간 빠름, 정확도 동급)
- **MBTI 페르소나 재현** → **Claude(Haiku)** (특히 F형)

## 채택한 모델 매핑 (`SERVER_AI_BACKEND=auto`)
- **F형 페르소나(감정형: …F…)** → **Claude(Haiku)** — 페르소나 재현 우위(특히 ENFP/ENFJ)
- **T형 페르소나(사고형: …T…)** → **GPT mini** — 페르소나는 동급/근소, 속도 우위 취함
- **translate는 항상 brief** (full 금지 — 양쪽 다 번역 충실도↓)
- 동적 캡으로 dense에서도 번역 안 잘림

## 한계
K=5라 안정적이나 Part B exact는 N=5 정수 변동 있음. ENFP/ENFJ 격차(큼)는 신뢰, 약한 유형 차이는 노이즈 여지.
