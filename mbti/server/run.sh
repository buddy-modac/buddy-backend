#!/usr/bin/env bash
# server/run.sh — AI Image Assistant 서버를 한 번에 실행.
#
#   ./server/run.sh              # 구독(claude CLI) 백엔드, 키 불필요
#   ./server/run.sh api          # Anthropic 비전 백엔드 (server/.env.local 의 ANTHROPIC_API_KEY)
#   ./server/run.sh openai       # OpenAI 백엔드 (server/.env.local 의 OPENAI_API_KEY, 모델 gpt-5.4-mini)
#   ./server/run.sh auto         # 페르소나 라우팅: F형→Claude, T형→GPT mini (두 키 다 필요)
#
# repo 루트에서 실행하세요. 처음이면 install 안내를 먼저 따르세요(SETUP.md).

set -e
cd "$(dirname "$0")/.."          # repo 루트로 이동

# venv 활성화
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "✗ .venv 없음 — 먼저 설치하세요:  ./install.sh   (SETUP.md 참고)"
  exit 1
fi

# 서버 의존성 확인
python - <<'PY' || { echo "✗ 서버 의존성 없음 — 설치:  pip install -e \".[server]\""; exit 1; }
import fastapi, uvicorn, httpx  # noqa
PY

# .env.local 이 있으면 항상 로드 (server_ocr 은 백엔드와 무관하게 API 키가 필요)
if [ -f server/.env.local ]; then
  set -a; # shellcheck disable=SC1091
  source server/.env.local; set +a
fi

# 백엔드 선택
if [ "${1:-}" = "auto" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ] || [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "✗ auto 라우팅은 ANTHROPIC_API_KEY + OPENAI_API_KEY 둘 다 필요합니다 (server/.env.local)"
    exit 1
  fi
  export SERVER_AI_BACKEND=auto
  echo "▶ AI 백엔드: auto (F형→Claude Haiku, T형→GPT mini · 페르소나 라우팅)"
elif [ "${1:-}" = "openai" ]; then
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "✗ OPENAI_API_KEY 없음 — openai 백엔드는 키가 필요합니다 (server/.env.local 에 입력)"
    exit 1
  fi
  export SERVER_AI_BACKEND=openai
  echo "▶ AI 백엔드: openai (모델 ${SERVER_OPENAI_MODEL:-gpt-5.4-mini}, API 과금)"
elif [ "${1:-}" = "api" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "✗ ANTHROPIC_API_KEY 없음 — api 백엔드는 키가 필요합니다:"
    echo "    cp server/.env.example server/.env.local   # 그리고 키 입력"
    exit 1
  fi
  export SERVER_AI_BACKEND=api
  echo "▶ AI 백엔드: api-vision (이미지 비전, API 과금)"
else
  export SERVER_AI_BACKEND=subscription
  echo "▶ AI 백엔드: subscription (claude CLI, 키 불필요)"
  command -v claude >/dev/null 2>&1 || echo "  ⚠ 'claude' CLI 미설치 — 구독 백엔드엔 Claude Code 필요 (SETUP.md)"
  [ -n "${ANTHROPIC_API_KEY:-}" ] && echo "  ℹ .env.local 키 로드됨 → server_ocr(이미지 OCR) 사용 가능" \
                                  || echo "  ℹ API 키 없음 → server_ocr 은 501 (프론트 ocr_text 필요)"
fi

echo "▶ http://localhost:8000  (콘솔)  ·  /docs (API 문서)  ·  Ctrl+C 종료"
exec uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
