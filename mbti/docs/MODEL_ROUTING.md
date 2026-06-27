# 모델 라우팅 / 매핑 (정본)

> 서버가 요청을 어떤 LLM으로 보내는지의 **단일 참조 문서**.
> ⚠️ **최종 진실은 코드** (`server/ai_backend.py`의 `pick_backend()`·`v2_params()`·`MODEL`/`HAIKU`/`OPENAI_MODEL`). 이 문서는 그 요약이다 — 코드 바뀌면 같이 갱신할 것.
> 근거(측정 데이터): [`benchmarks/provider_matrix_20260627.md`](../benchmarks/provider_matrix_20260627.md)

## 1) `auto` — 페르소나별 모델 매핑 (권장 운영 모드)
MBTI 3번째 글자(T/F)로 라우팅:
| 페르소나 | v1 (`/analyze`) | v2 (`/v2/analyze`) |
|---|---|---|
| **F형** (…F…, 감정형: ENFP·ENFJ·ISFJ·ESFJ·INFP·INFJ·ISFP·ESFP) | Claude Sonnet | **Claude Haiku** |
| **T형** (…T…, 사고형: INTJ·INTP·ENTJ·ENTP·ISTJ·ISTP·ESTJ·ESTP) | gpt-5.4-mini | **gpt-5.4-mini** |

`SERVER_AI_BACKEND=auto` 일 때만. **ANTHROPIC_API_KEY + OPENAI_API_KEY 둘 다** 필요.

## 2) 백엔드 모드별 모델 (`SERVER_AI_BACKEND`)
| 모드 | v1 모델 | v2 모델 | 비고 |
|---|---|---|---|
| `subscription` (기본) | claude -p (Sonnet) | claude -p (Haiku) | 키 불필요·비전 없음(로컬 테스트) |
| `api` | claude-sonnet-4-6 | claude-haiku-4-5 | Anthropic 단일 |
| `openai` | gpt-5.4-mini | gpt-5.4-mini | OpenAI 단일 |
| **`auto`** | F:Sonnet / T:gpt-mini | **F:Haiku / T:gpt-mini** | 페르소나 라우팅(위 1번) |

실행: `./server/run.sh [api|openai|auto]` (인자 없으면 subscription).

## 3) v2 처리 정책 (mode별)
| mode | detail | 이미지 전송 | 출력 캡(max_tokens) |
|---|---|---|---|
| translate | **brief 강제** (full 무시) | 생략(텍스트만) | 동적 = `max(400, OCR자수×2.2)` |
| explain | brief / full | 포함(비전) | 동적 = `max(500/1200, OCR자수×1.0)` |

- 캡은 입력(OCR) 길이에 비례 → 긴 약관 등 dense 번역이 잘리지 않음(상한 4000).
- `provider:"anthropic"|"openai"` 를 요청 바디에 넣으면 그 요청만 강제(비교용, 예: `/sample-test`).
- 실제 사용 모델은 응답 `model` 및 DB·admin `모델` 컬럼에 기록.

## 4) 왜 이렇게 (근거 요약)
2026-06-27 K=5 벤치([상세](../benchmarks/provider_matrix_20260627.md)):
- **작업 속도/정확도**: gpt-5.4-mini가 모든 시나리오(light·dense × translate·explain)에서 **더 빠르고 정확도 동급**.
- **MBTI 페르소나 재현**: Claude 우세, 특히 **감정형 ENFP/ENFJ에서 격차 큼**(축점수 0.95/0.90 vs GPT 0.60/0.70). 분석형(INTJ/INTP)은 동급.
- **절충**: 페르소나가 동급인 **T형은 빠른 GPT**, 페르소나가 제품 가치인 **F형은 재현 잘하는 Claude**. translate full은 양쪽 다 번역 충실도↓ → brief 고정.

## 5) 변경 시 체크리스트
모델/라우팅을 바꾸면: `server/ai_backend.py` 수정 → **이 문서 표 갱신** → (큰 변경이면) 벤치 재측정 후 `benchmarks/`에 새 dated 리포트 추가.
