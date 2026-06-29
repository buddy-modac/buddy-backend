#!/usr/bin/env bash
# start.sh — 원샷: 설치(.venv + deps) → API 키 확인 → 서버 기동(api-vision).
#
#   ./start.sh
#
# 레포를 처음 클론한 사람이 이 한 줄이면 http://localhost:8000 까지 뜹니다.
# 전제: ANTHROPIC + OPENAI 두 API 키 (auto 라우팅: F형→Claude, T형→GPT).
#       키는 server/.env.local 또는 환경변수로 주입. 재실행해도 안전합니다.
set -e
cd "$(dirname "$0")"            # mbti/ 루트로 이동

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "✗ python3 없음 — python.org 또는 'brew install python'"; exit 1; }
echo "▶ Python: $($PY --version)"

# 1) virtualenv
if [ ! -d ".venv" ]; then
  echo "▶ .venv 생성..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2) 의존성 (core + server: fastapi/uvicorn/httpx)
echo "▶ 의존성 설치 (core + server)..."
python -m pip install --upgrade pip >/dev/null
pip install -e ".[server]" >/dev/null
echo "  ✓ 설치 완료"

# 3) self-check (오프라인·무료)
if python -m personaforge.check >/dev/null 2>&1; then
  echo "▶ ✓ self-check 통과"
else
  echo "  ⚠ self-check 경고 — 계속 진행"
fi

# 4) server/.env.local 준비 (없으면 템플릿 복사)
if [ ! -f server/.env.local ]; then
  cp server/.env.example server/.env.local
  echo "▶ server/.env.local 생성됨 (.env.example 복사)"
fi

# 5) API 키 확인 (환경변수 우선 → .env.local). 빈 값/템플릿 플레이스홀더 거부.
#    auto 라우팅(F형→Claude, T형→GPT)은 ANTHROPIC + OPENAI 두 키 모두 필요.
read_key() {  # $1=키 이름 → 값 출력 (env 우선, 없으면 .env.local)
  local v="${!1:-}"
  if [ -z "$v" ] && [ -f server/.env.local ]; then
    v="$(grep -E "^$1=" server/.env.local | tail -1 | cut -d= -f2-)"
  fi
  printf '%s' "$v"
}
check_key() {  # $1=키 이름, $2=발급 URL
  local v; v="$(read_key "$1")"
  case "$v" in
    ""|*여기에*)
      echo
      echo "✗ $1 가 비어 있습니다 (또는 템플릿 값 그대로)."
      echo "  server/.env.local 을 열어 실제 키를 넣고 다시 실행하세요:  $1=..."
      echo "  또는 환경변수로:  $1=... ./start.sh"
      echo "  키 발급: $2"
      exit 1
      ;;
  esac
}
# auto 라우팅은 가진 키로 폴백하므로, 세 키 중 최소 하나만 있으면 됩니다.
#   Anthropic+OpenAI → F형 Claude / T형 GPT,  Gemini(무료) → 전부 Gemini, 빈 자리는 Gemini 폴백.
has_some() { local v; v="$(read_key "$1")"; case "$v" in ""|*여기에*) return 1;; *) return 0;; esac; }
if ! has_some ANTHROPIC_API_KEY && ! has_some OPENAI_API_KEY && ! has_some GEMINI_API_KEY; then
  echo
  echo "✗ AI 키가 하나도 없습니다. server/.env.local 에 아래 중 하나라도 넣고 다시 실행하세요:"
  echo "    ANTHROPIC_API_KEY  (https://console.anthropic.com → API Keys)"
  echo "    OPENAI_API_KEY     (https://platform.openai.com → API keys)"
  echo "    GEMINI_API_KEY     (https://aistudio.google.com → Get API key · 무료)"
  exit 1
fi
_have=""
has_some ANTHROPIC_API_KEY && _have="${_have}Claude "
has_some OPENAI_API_KEY && _have="${_have}GPT "
has_some GEMINI_API_KEY && _have="${_have}Gemini "
echo "▶ ✓ AI 키 확인됨 (보유: ${_have})"

# 6) 기동 — run.sh auto 가 .env.local 로드 + 최종 검증 + URL 배너 + uvicorn 실행
#    (F형→Claude, T형→GPT 페르소나 라우팅, 두 키 사용)
exec ./server/run.sh auto
