# 시작 가이드 (설치 · 서버 실행)

PersonaForge를 **다른 PC에서 처음 받아 실행**하는 사람을 위한 안내서입니다.
복사-붙여넣기로 따라 하면 됩니다. (macOS / Linux 기준, Windows는 맨 아래 참고)

---

## 0. 이게 뭔가요?
- **PersonaForge** — MBTI 페르소나 엔진 (Python). 코어는 **외부 의존성 0**(순수 표준 라이브러리).
- **server/** — 프론트가 보낸 이미지/텍스트를 MBTI 스타일 AI로 해석해 돌려주는 FastAPI 서버.
- AI 호출 백엔드는 둘 중 하나:
  - **🟢 API(api-vision) — 실제 운영/배포용 (기본 권장).** Anthropic API 키 사용. 진짜 이미지 비전 지원. **실제 유저는 이걸 씁니다.**
  - **🧪 구독(subscription) — 로컬 개발/빠른 테스트용.** 로컬 `claude` CLI(Claude Code) 사용, API 키 불필요. 단 비전(이미지 해석)은 안 되고 OCR 텍스트 기반. (키 없이 동작 확인할 때만)

---

## 1. 필요한 것 (Prerequisites)
| 항목 | 필수? | 비고 |
|---|---|---|
| **Python 3.8+** | ✅ | `python3 --version` (3.10+ 권장) |
| **git** | ✅ | 레포 클론 |
| **Anthropic API 키** | **운영이면 ✅** | [console.anthropic.com](https://console.anthropic.com) → API Keys. 실제 서비스(비전 포함)의 기본 경로 |
| Claude Code (`claude` CLI) | 개발/테스트용(선택) | 키 없이 빠르게 돌려볼 때만. [claude.com/claude-code](https://claude.com/claude-code) 설치+로그인 |

> **오프라인 테스트만** 할 거면 Python + git 만 있으면 됩니다 (AI 호출 없음).

---

## 2. 설치 (3줄)
```bash
git clone <레포-URL> personaforge
cd personaforge
./install.sh                 # .venv 생성 + 패키지 설치 + self-check
```
`install.sh` 가 하는 일: `.venv` 가상환경 생성 → `pip install -e ".[test]"` → 자가진단 출력. **재실행해도 안전.**

### 서버까지 쓰려면 (FastAPI 등 추가)
```bash
source .venv/bin/activate
pip install -e ".[server]"   # fastapi, uvicorn, httpx
```
> 한 번에 다 깔려면: `pip install -e ".[all]"` (서버+테스트+한국어+웹수집 전부)

---

## 3. 설치 확인 (AI 없이, 무료)
```bash
source .venv/bin/activate
python -m pytest tests/ -q          # 180개 테스트 통과해야 정상
python examples/demo_offline.py     # 오프라인 데모
```

---

## 4. 서버 실행 🚀
repo 루트에서:

### 🟢 A. API 백엔드 — 실제 운영/배포 (기본 권장)
실제 유저가 쓰는 경로. **진짜 이미지 비전** 지원.
```bash
cp server/.env.example server/.env.local   # 그리고 .env.local 에 실제 API 키 입력
./server/run.sh api
```
- `.env.local` 은 **gitignore로 커밋이 막혀** 있습니다. 키를 절대 커밋하지 마세요.
- 운영 환경에선 `.env.local` 대신 환경변수로 주입해도 됩니다: `ANTHROPIC_API_KEY=... SERVER_AI_BACKEND=api uvicorn server.main:app`

### 🧪 B. 구독 백엔드 — 로컬 개발/빠른 테스트 (선택)
API 키 없이 동작만 확인할 때. `claude` CLI(Claude Code) 로그인 필요. **비전은 안 되고** OCR 텍스트 기반.
```bash
./server/run.sh
```
- `translate`는 완전, `explain`은 텍스트 기반(이미지 비전 미사용).

### 서버가 뜨면
- **테스트 콘솔:** http://localhost:8000  ← 이미지 올리고 MBTI·모드 골라 분석, **흐름 타임라인·요청/응답·결과**를 한눈에
- **API 문서(Swagger):** http://localhost:8000/docs
- **헬스체크:** http://localhost:8000/health (현재 백엔드 표시)
- DB(`server/app.db`)는 첫 실행 시 자동 생성 (gitignore됨)

> 수동 실행을 원하면: `uvicorn server.main:app --reload` (백엔드는 `SERVER_AI_BACKEND` 환경변수로 선택)

---

## 5. 주요 엔드포인트 (요약)
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/analyze` | 이미지+텍스트 분석 (메인). `?debug=1` 이면 단계별 타이밍 |
| GET | `/conversation/{id}` · `/users/{nick}/messages` | 대화/유저 조회 |
| POST | `/quiz/start` · `/quiz/answer` | MBTI 퀴즈 → 결과를 persona로 사용 |
| GET | `/personas` · `/health` | 16 MBTI 목록 · 상태 |

자세한 명세는 `server/README.md`.

---

## 6. 문제 해결 (Troubleshooting)
| 증상 | 해결 |
|---|---|
| `command not found: claude` | 구독 백엔드엔 Claude Code 필요 → [설치·로그인](https://claude.com/claude-code), 또는 API 백엔드 사용 |
| `AI 호출 실패` (구독) | `claude` 로그인 상태 확인 (`claude` 실행), 구독 토큰 한도 확인 |
| `502 / ANTHROPIC_API_KEY 없음` | api 백엔드인데 키 없음 → `server/.env.local` 에 키 입력 |
| `ModuleNotFoundError: fastapi` | `pip install -e ".[server]"` |
| `.venv` 없음 | `./install.sh` 먼저 |
| 포트 8000 사용중 | `uvicorn server.main:app --port 8001` 등 다른 포트 |

---

## 7. 프로젝트 구조
```
personaforge/
├─ personaforge/      # 코어 엔진 (Phase 1 롤플레이 + Phase 2 스타일 어시스턴트)
├─ server/            # FastAPI 서버 (이미지 어시스턴트 + 퀴즈 + 테스트 콘솔)
│  ├─ main.py · ai_backend.py · quiz.py · console.html
│  ├─ run.sh · .env.example · README.md
├─ tests/             # 180개 테스트
├─ examples/          # 데모 스크립트
├─ docs/              # 설계·결정·개요 문서 (PHASE2_BUILD_LOG, idea.html, ...)
├─ benchmarks/        # 측정 스크립트·결과
├─ install.sh · pyproject.toml · README.md · SETUP.md(이 파일)
```

---

## 8. Windows 참고
- `install.sh`/`run.sh` 는 bash 스크립트입니다. **Git Bash** 또는 **WSL**에서 실행하거나, 수동으로:
  ```powershell
  python -m venv .venv
  .venv\Scripts\activate
  pip install -e ".[server]"
  uvicorn server.main:app --reload
  ```
- 구독 백엔드는 `claude` CLI가 PATH에 있어야 합니다.

---

문서: 전체 개요는 `docs/personaforge_overview.pdf`, Phase 2 상세는 `README.md`의 Phase 2 섹션.
