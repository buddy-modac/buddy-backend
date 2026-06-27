# MBTI Image Assistant (mbti/)

이미지+텍스트를 받아 **선택한 MBTI 페르소나의 소통 스타일**로 번역/설명해주는 AI 서버.
`personaforge`(MBTI 엔진) + FastAPI 서버로 구성. (롤플레이 "캐릭터" 기능은 제외, MBTI 전용)

## 빠른 시작
```bash
cd mbti
./install.sh --all                # .venv 생성 + 패키지·서버 deps 설치 (--all = fastapi/uvicorn/httpx 포함)
cp server/.env.example server/.env.local   # API 키 입력 (아래)
./server/run.sh auto              # http://localhost:8000
```
> 서버를 쓰려면 `--all`(또는 `pip install -e ".[server]"`)이 필요해요. `./install.sh`만 하면 서버 deps가 빠집니다.
- 키 없이 로컬 테스트: `./server/run.sh` (구독 claude CLI, 비전 없음)
- 단일 프로바이더: `./server/run.sh api`(Anthropic) · `./server/run.sh openai`
- **auto**: 페르소나로 모델 라우팅(F형→Claude, T형→GPT mini) — 두 키 필요

## API 키 (server/.env.local — 절대 커밋 금지)
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...            # openai/auto 쓸 때
```
`.gitignore`가 `.env.local`·`*.db` 등을 막아 키·로컬 데이터가 커밋되지 않음.

## 로컬 페이지 (서버 실행 후)
| 경로 | 용도 |
|---|---|
| `/` | 테스트 콘솔(분석 + 스타일·detail 토글 + 흐름) |
| `/api` | **프런트 개발자용 API 명세** (시나리오별 복붙 요청) |
| `/sample-test` | v1·v2·Claude·GPT 속도/품질 비교 (localhost 전용) |
| `/admin` | DB 조회·삭제·필터 (localhost 전용) |
| `/quiz-ui` | MBTI 퀴즈 → persona 산출 |
| `/docs` | Swagger |

## 핵심 개념 / 동작
- **v1**(`/analyze`) = 정확/풍부(느림), **v2**(`/v2/analyze`) = Haiku·동적캡·이미지정책(빠름, 권장).
- **detail**: brief(기본)/full · **styled**: MBTI 스타일/기본 모드(담백) · **conversation_id·parent_id**: reply 체인.
- 모델 라우팅·정책·근거: [`docs/MODEL_ROUTING.md`](docs/MODEL_ROUTING.md)
- 서버 상세: [`server/README.md`](server/README.md) · 설치 상세: [`SETUP.md`](SETUP.md)

## 구조
```
mbti/
  personaforge/   # MBTI 엔진(코어 패키지)
  server/         # FastAPI 서버 + 로컬 HTML 페이지
  personas/       # curated/·mbti/ (MBTI 페르소나 데이터)
  docs/MODEL_ROUTING.md
  pyproject.toml · requirements.txt · install.sh · SETUP.md
```
