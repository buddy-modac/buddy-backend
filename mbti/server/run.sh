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

# .env.local 이 있으면 로드 (server_ocr 은 백엔드와 무관하게 API 키가 필요).
# 단, 이미 환경변수로 준 키가 우선 — .env.local 의 플레이스홀더가 실제 키를 덮어쓰지 않도록.
_PRE_ANTHROPIC="${ANTHROPIC_API_KEY:-}"; _PRE_OPENAI="${OPENAI_API_KEY:-}"; _PRE_GEMINI="${GEMINI_API_KEY:-}"
if [ -f server/.env.local ]; then
  set -a; # shellcheck disable=SC1091
  source server/.env.local; set +a
fi
[ -n "$_PRE_ANTHROPIC" ] && ANTHROPIC_API_KEY="$_PRE_ANTHROPIC"
[ -n "$_PRE_OPENAI" ] && OPENAI_API_KEY="$_PRE_OPENAI"
[ -n "$_PRE_GEMINI" ] && GEMINI_API_KEY="$_PRE_GEMINI"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" OPENAI_API_KEY="${OPENAI_API_KEY:-}" GEMINI_API_KEY="${GEMINI_API_KEY:-}"

# 키 보유 여부(비었거나 템플릿 플레이스홀더면 '없음'). auto 는 이걸로 폴백 라우팅.
has_key() { case "${!1:-}" in ""|*여기에*) return 1 ;; *) return 0 ;; esac; }

# 키가 비었거나 .env.example 템플릿 플레이스홀더(...여기에...)면 실패시키는 헬퍼
need_key() {  # $1=키 이름, $2=발급 안내
  local v="${!1:-}"
  case "$v" in
    "")        echo "✗ $1 없음 — server/.env.local 에 입력하세요 ($2)"; exit 1 ;;
    *여기에*)  echo "✗ $1 가 템플릿 값 그대로입니다 — server/.env.local 에 실제 키를 넣으세요 ($2)"; exit 1 ;;
  esac
}
ANTHROPIC_HINT="https://console.anthropic.com → API Keys"
OPENAI_HINT="https://platform.openai.com → API keys"

# 백엔드 선택
if [ "${1:-}" = "auto" ]; then
  # auto 는 가진 키로 자동 폴백 → 키가 최소 하나는 있어야 함(없으면 subscription = 비전X).
  GEMINI_HINT="https://aistudio.google.com → Get API key (무료)"
  if ! has_key ANTHROPIC_API_KEY && ! has_key OPENAI_API_KEY && ! has_key GEMINI_API_KEY; then
    echo "✗ AI 키가 하나도 없습니다 — server/.env.local 에 아래 중 하나라도 넣으세요:"
    echo "    ANTHROPIC_API_KEY ($ANTHROPIC_HINT)"
    echo "    OPENAI_API_KEY    ($OPENAI_HINT)"
    echo "    GEMINI_API_KEY    ($GEMINI_HINT)  ← 무료, 이것만으로도 비전 분석 가능"
    exit 1
  fi
  export SERVER_AI_BACKEND=auto
  _have=""
  has_key ANTHROPIC_API_KEY && _have="${_have}Claude "
  has_key OPENAI_API_KEY && _have="${_have}GPT "
  has_key GEMINI_API_KEY && _have="${_have}Gemini "
  echo "▶ AI 백엔드: auto (F형→Claude, T형→GPT, 빈 자리는 Gemini 폴백 · 보유: ${_have})"
elif [ "${1:-}" = "gemini" ]; then
  need_key GEMINI_API_KEY "https://aistudio.google.com → Get API key (무료)"
  export SERVER_AI_BACKEND=gemini
  echo "▶ AI 백엔드: gemini (Gemini 2.5 Flash · 무료 티어·비전)"
elif [ "${1:-}" = "openai" ]; then
  need_key OPENAI_API_KEY "$OPENAI_HINT"
  export SERVER_AI_BACKEND=openai
  echo "▶ AI 백엔드: openai (모델 ${SERVER_OPENAI_MODEL:-gpt-5.4-mini}, API 과금)"
elif [ "${1:-}" = "api" ]; then
  need_key ANTHROPIC_API_KEY "$ANTHROPIC_HINT"
  export SERVER_AI_BACKEND=api
  echo "▶ AI 백엔드: api-vision (이미지 비전, API 과금)"
else
  export SERVER_AI_BACKEND=subscription
  echo "▶ AI 백엔드: subscription (claude CLI, 키 불필요)"
  command -v claude >/dev/null 2>&1 || echo "  ⚠ 'claude' CLI 미설치 — 구독 백엔드엔 Claude Code 필요 (SETUP.md)"
  case "${ANTHROPIC_API_KEY:-}" in
    ""|*여기에*) echo "  ℹ API 키 없음 → server_ocr 은 501 (프론트 ocr_text 필요)" ;;
    *)           echo "  ℹ .env.local 키 로드됨 → server_ocr(이미지 OCR) 사용 가능" ;;
  esac
fi

# 0.0.0.0 으로 바인딩 → 같은 와이파이(LAN)의 다른 기기/폰에서도 접속 가능.
# HOST 환경변수로 덮어쓸 수 있음 (예: HOST=127.0.0.1 ./server/run.sh api → 이 PC 전용).
BIND="${HOST:-0.0.0.0}"; PORT="${PORT:-8000}"
# 표시용 LAN IP 탐지 (macOS en0/en1 → Linux hostname -I)
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$LAN_IP" ] && LAN_IP="<이-기기-IP>"
BASE="http://${LAN_IP}:${PORT}"
echo ""
echo "────────────────────────────────────────────────────────────"
echo "  ▶ 서버 기동 — 바인딩: ${BIND}:${PORT}  (같은 와이파이의 다른 기기에서 접속 가능)"
echo "  ─ 다른 기기/폰에서 (이 PC LAN IP) ────────────────────────"
printf "    %-32s %s\n" "${BASE}/"            "콘솔(분석)"
printf "    %-32s %s\n" "${BASE}/api"         "API 명세"
printf "    %-32s %s\n" "${BASE}/docs"        "Swagger 문서"
printf "    %-32s %s\n" "${BASE}/quiz-ui"     "MBTI 퀴즈"
printf "    %-32s %s\n" "${BASE}/health"      "헬스체크"
echo "  ─ 이 PC 전용 (외부 기기는 403 차단) ──────────────────────"
printf "    %-32s %s\n" "http://localhost:${PORT}/sample-test" "속도/품질 비교"
printf "    %-32s %s\n" "http://localhost:${PORT}/admin"       "DB 관리자"
echo "  ────────────────────────────────────────────────────────"
echo "  이 PC에서는 http://localhost:${PORT} 로도 접속됩니다 · 종료: Ctrl+C"
echo "────────────────────────────────────────────────────────────"
exec uvicorn server.main:app --host "${BIND}" --port "${PORT}" --reload
