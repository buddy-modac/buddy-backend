# MBTI Image Assistant (mbti/)

이미지+텍스트를 받아 **선택한 MBTI 페르소나의 소통 스타일**로 번역/설명해주는 AI 서버.
`personaforge`(MBTI 엔진) + FastAPI 서버로 구성. (롤플레이 "캐릭터" 기능은 제외, MBTI 전용)

## 빠른 시작 (원샷)
```bash
cd mbti
cp server/.env.example server/.env.local   # 그리고 ANTHROPIC_API_KEY 입력 (아래)
./start.sh                                  # 설치 + 키확인 + 서버 기동 → http://localhost:8000
```
`start.sh` = `.venv` 생성 → core+server deps 설치 → self-check → **api-vision 서버 기동** 까지 한 번에. 재실행 안전.
키를 환경변수로 주려면: `ANTHROPIC_API_KEY=sk-ant-... ./start.sh`

> **LAN 접속(기본값):** 서버는 `0.0.0.0`에 바인딩되어 **같은 와이파이의 폰·다른 PC에서도** 접속됩니다. 기동 시 출력되는 `http://<이-PC-IP>:8000` 을 쓰세요. (`/admin`·`/sample-test`는 이 PC에서만 — 외부는 403). 이 PC 전용으로 막으려면 `HOST=127.0.0.1 ./start.sh`.

> 수동/단계별 설치는 [`SETUP.md`](SETUP.md) 참고.
> 단일 프로바이더 직접 실행: `./server/run.sh api`(Anthropic) · `./server/run.sh openai`(키 필요).
> 키 없이 돌리는 구독(claude CLI) 백엔드는 개발용 — 비전 미지원, 자세한 건 `SETUP.md`.

## API 키 (server/.env.local — 절대 커밋 금지)
```
ANTHROPIC_API_KEY=sk-ant-...     # 필수 — 기본/권장 경로(api-vision). 없으면 start.sh가 거부
OPENAI_API_KEY=sk-...            # 선택 — openai/auto 백엔드 쓸 때만 필수
```
- **ANTHROPIC_API_KEY = 필수** ([console.anthropic.com](https://console.anthropic.com) → API Keys). `./start.sh`·`./server/run.sh api`는 이 키가 없으면 실행을 거부합니다.
- **OPENAI_API_KEY = 선택** — `openai`/`auto` 백엔드에서만 필요. `auto`는 두 키 모두 필요.
- `.gitignore`가 `.env.local`·`*.db` 등을 막아 키·로컬 데이터가 커밋되지 않음.

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
  pyproject.toml · requirements.txt · start.sh · install.sh · SETUP.md
```
