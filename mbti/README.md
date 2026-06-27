# MBTI Image Assistant (mbti/)

이미지+텍스트를 받아 **선택한 MBTI 페르소나의 소통 스타일**로 번역/설명해주는 AI 서버.
`personaforge`(MBTI 엔진) + FastAPI 서버로 구성. (롤플레이 "캐릭터" 기능은 제외, MBTI 전용)

## 빠른 시작 (원샷)
```bash
cd mbti
cp server/.env.example server/.env.local   # 그리고 ANTHROPIC + OPENAI 키 입력 (아래)
./start.sh                                  # 설치 + 키확인 + 서버 기동 → http://localhost:8000
```
`start.sh` = `.venv` 생성 → core+server deps 설치 → self-check → **auto 라우팅 서버 기동**(F형→Claude, T형→GPT) 까지 한 번에. 재실행 안전.
키를 환경변수로 주려면: `ANTHROPIC_API_KEY=sk-ant-... OPENAI_API_KEY=sk-... ./start.sh`

> **LAN 접속(기본값):** 서버는 `0.0.0.0`에 바인딩되어 **같은 와이파이의 폰·다른 PC에서도** 접속됩니다. 기동 시 출력되는 `http://<이-PC-IP>:8000` 을 쓰세요. (`/admin`·`/sample-test`는 이 PC에서만 — 외부는 403). 이 PC 전용으로 막으려면 `HOST=127.0.0.1 ./start.sh`.

> 수동/단계별 설치는 [`SETUP.md`](SETUP.md) 참고.
> 단일 프로바이더 직접 실행: `./server/run.sh api`(Anthropic) · `./server/run.sh openai`(키 필요).
> 키 없이 돌리는 구독(claude CLI) 백엔드는 개발용 — 비전 미지원, 자세한 건 `SETUP.md`.

## API 키 (server/.env.local — 절대 커밋 금지)
```
ANTHROPIC_API_KEY=sk-ant-...     # 필수 — Claude(비전·F형). 없으면 start.sh가 거부
OPENAI_API_KEY=sk-...            # 필수 — GPT(T형). 없으면 start.sh가 거부
```
- **둘 다 필수** — `./start.sh`(=auto 라우팅)는 두 키가 없거나 템플릿 값 그대로면 실행을 거부합니다.
  - ANTHROPIC: [console.anthropic.com](https://console.anthropic.com) → API Keys · OPENAI: [platform.openai.com](https://platform.openai.com) → API keys
- 단일 프로바이더만 쓸 거면 `./server/run.sh api`(Anthropic만) 또는 `./server/run.sh openai`(OpenAI만).
- `.gitignore`가 `.env.local`·`*.db` 등을 막아 키·로컬 데이터가 커밋되지 않음.

## 로컬 페이지 (서버 실행 후)
| 경로 | 용도 |
|---|---|
| `/` | 테스트 콘솔(분석 + 스타일·detail 토글 + 흐름) |
| `/api` | **프런트 개발자용 API 명세** (시나리오별 복붙 요청) |
| `/sample-test` | v1·v2·Claude·GPT 속도/품질 비교 (localhost 전용) |
| `/admin` | DB 조회·삭제·필터 (localhost 전용) |
| `/quiz-ui` | MBTI 퀴즈 → persona 산출 |
| `/clipboard-ui` | 공개 이미지 클립보드(갤러리) 데모 — 업로드/조회/다운로드 |
| `/docs` | Swagger |

**이미지 클립보드 API** (공개): `POST /clipboard`(멀티파트 `file=`+`nickname=` 또는 JSON `{image_b64,media_type,name,nickname}`) · `GET /clipboard`(목록, 각 항목에 `url`·`nickname`) · `GET /clipboard/{id}/raw`(원본 바이트, `?download=1`로 다운로드) · `DELETE /clipboard/{id}`. 프런트는 받은 `url`을 `<img src>`에 그대로 쓰면 됨(디코딩 불필요). `nickname`은 선택(없으면 '익명'). 업로드 이미지는 `server/uploads/`에 저장(gitignore).

> **다른 기기에 띄운 서버의 관리 페이지를 내 PC에서 보려면:** 관리용 엔드포인트(`/admin`·`/sample-test`·`/messages`·`DELETE /message/{id}`)는 기본 localhost 전용(외부 403)입니다. 서버 실행 기기에서 `SERVER_ADMIN_ALLOW_IPS` 에 **내 PC의 IP**를 추가하면 이 네 개가 모두 그 IP에서 열립니다 (`server/.env.local` 또는 환경변수, 콤마 구분·CIDR 가능). 차단 시 403 응답에 **현재 접속 IP**가 찍히니 그 값을 그대로 넣으면 됩니다. 예: `SERVER_ADMIN_ALLOW_IPS=192.168.0.50`.

## 핵심 개념 / 동작
- **v1**(`/analyze`) = 정확/풍부(느림), **v2**(`/v2/analyze`) = Haiku·동적캡·이미지정책(빠름, 권장).
- **detail**: brief(기본)/full · **styled**: MBTI 스타일/기본 모드(담백) · **conversation_id·parent_id**: reply 체인.
- **페르소나 추출 + A/B/C 프롬프트 구조**: [`docs/PERSONA_AND_PROMPT.md`](docs/PERSONA_AND_PROMPT.md)
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
