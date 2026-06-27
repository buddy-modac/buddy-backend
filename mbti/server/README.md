# AI Image Assistant 서버

프론트가 보낸 **이미지/추출텍스트 + MBTI 페르소나 + mode(번역/설명)**를 받아, **PersonaForge
Phase 2**(MBTI 스타일 어시스턴트) 프롬프트로 AI에 보내 해석하고 결과를 돌려주는 FastAPI 서버.

## 문서 설계와 달라진 점 (Phase 2 통합)
원본 설계의 단순 `MBTI_DESC` + `build_prompt` + Anthropic-API 직접호출을 **Phase 2로 교체**:
- 프롬프트 = `personaforge.build_assistant_system_prompt(persona, "Korean")`
  → A(베이스 어시스턴트) + B(인지기능 스택 기반 MBTI 스타일) + C(능력우선·반아첨·위기 가드레일).
- AI 호출 = **pluggable 백엔드** (`ai_backend.py`):
  | 백엔드 | 용도 | 전송 | 비전 | 키 |
  |---|---|---|---|---|
  | `api-vision` | **🟢 운영(실유저)** | Anthropic Messages API + base64 이미지 | ✓ 진짜 이미지 해석 | `ANTHROPIC_API_KEY` |
  | `subscription-text` | 🧪 로컬 개발/테스트 | `claude -p` (구독) | ✗ (추출 텍스트만) | 불필요 |
  - 실제 서비스는 **API 백엔드**(`SERVER_AI_BACKEND=api`)를 씁니다. 구독은 키 없이 빠르게 돌려볼 때만.

## 실행
```bash
# repo 루트에서 (.venv 활성화 상태)
source .venv/bin/activate
pip install -r server/requirements.txt          # personaforge는 이미 -e 설치됨
uvicorn server.main:app --reload                 # http://localhost:8000
```
- DB(`server/app.db`)·캐시(`server/server_cache.db`)는 첫 실행 시 자동 생성 (gitignore됨).
- API 문서(Swagger): http://localhost:8000/docs

### AI 백엔드 선택
```bash
# 🟢 운영(실유저) — API 키 + 진짜 이미지 비전
export ANTHROPIC_API_KEY="sk-ant-..."
export SERVER_AI_BACKEND=api
uvicorn server.main:app                # 또는: ./server/run.sh api

# 🧪 로컬 개발/테스트 — 키 없이 빠르게 (구독 claude CLI, 비전 없음)
uvicorn server.main:app                # SERVER_AI_BACKEND 미설정 시 기본

# 🤖 OpenAI(gpt-5.4-mini)
export OPENAI_API_KEY="sk-..."; export SERVER_AI_BACKEND=openai   # ./server/run.sh openai

# 🔀 auto — 페르소나로 모델 라우팅 (두 키 다 필요)
export SERVER_AI_BACKEND=auto          # ./server/run.sh auto
```

### 모델 매핑 (`auto`)
요약: **F형 페르소나 → Claude Haiku, T형 → GPT mini**, translate는 항상 brief, 캡은 입력 길이에 비례(동적).
→ 전체 매핑 표·정책·결정 근거는 **정본 문서** [`docs/MODEL_ROUTING.md`](../docs/MODEL_ROUTING.md) 참고. (단일 프로바이더는 `api`/`openai`, `auto`는 두 키 필요)

## 엔드포인트
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/analyze` | 이미지+텍스트 분석 (메인). `conversation_id`/`parent_id`로 reply 체인. `styled:false`면 **기본 모드**(담백·스타일 없음), 응답에 `styled` 에코 |
| GET | `/message/{id}` | 단건 (`?include_image=true`로 이미지 포함) |
| GET | `/conversation/{cid}` | 대화 타임라인 |
| GET | `/users/{nickname}/messages` | 닉네임별 목록 (페이징·mode 필터) |
| GET | `/users/{nickname}/conversations` | 닉네임별 대화 목록 |
| GET | `/users/{nickname}/summary` | 하루 질의 요약(번역/설명 분리+토픽). `?date`·`?refresh`, DB 캐시 |
| DELETE | `/message/{id}` | 삭제 (자식 parent_id는 NULL 정리) |
| GET | `/personas` | 16 MBTI + 말투 설명 |
| GET | `/health` | 상태 + 현재 AI 백엔드 |
| POST | `/quiz/start` · `/quiz/answer` · GET `/quiz/{id}` | MBTI 퀴즈 → 결과를 persona로 사용 |
| POST | `/clipboard` | 이미지 업로드(공개). 멀티파트 `file=`(+`nickname=`) 또는 JSON `{image_b64, media_type, name, nickname}`. → `{id, url, nickname, ...}` |
| GET | `/clipboard` | 업로드 목록(최신순). 각 항목에 바로 쓸 `url`·`nickname` 포함 |
| GET | `/clipboard/{id}/raw` | 원본 이미지 바이트(+`Content-Type`). `?download=1`로 다운로드 |
| DELETE | `/clipboard/{id}` | 삭제(공개) — 디스크 파일+메타 제거 |

> 클립보드는 **공개**(인증·제한 없음). 바이트는 `server/uploads/`(gitignore)에 디스크 저장, 메타만 SQLite. `nickname`은 선택(없으면 null→UI '익명'), `uploader_ip`도 기록. UI: `/clipboard-ui`(갤러리) · `/admin` 클립보드 탭.

## reply 체인 흐름
1. `POST /analyze` (conversation_id 없음) → `{id:1, conversation_id:"abc", parent_id:null}`
2. `POST /analyze` with `conversation_id:"abc", parent_id:1` → 서버가 1번 text/result를 프롬프트에 끼움
3. `GET /conversation/abc` → 타임라인

## 파일
- `main.py` — 앱·DB·엔드포인트
- `ai_backend.py` — pluggable AI 백엔드 (Phase 2 시스템 프롬프트 + 구독/API 전송)
- `personas.py` — 표시용 16 MBTI 설명 (유효성은 `ALL_TYPES`와 동기)
- `quiz.py` / `quiz_data.py` — MBTI 진단 퀴즈
