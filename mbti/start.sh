#!/usr/bin/env bash
# start.sh — 원샷: 설치(.venv + deps) → API 키 확인 → 서버 기동(api-vision).
#
#   ./start.sh
#
# 레포를 처음 클론한 사람이 이 한 줄이면 http://localhost:8000 까지 뜹니다.
# 전제: Anthropic API 키(api-vision 경로). 키는 server/.env.local 또는 환경변수로 주입.
# 재실행해도 안전합니다.
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

# 5) API 키 확인 (환경변수 우선 → .env.local). 템플릿 플레이스홀더는 거부.
KEY="${ANTHROPIC_API_KEY:-}"
if [ -z "$KEY" ] && [ -f server/.env.local ]; then
  KEY="$(grep -E '^ANTHROPIC_API_KEY=' server/.env.local | tail -1 | cut -d= -f2-)"
fi
case "$KEY" in
  ""|*여기에*)
    echo
    echo "✗ ANTHROPIC_API_KEY 가 비어 있습니다 (또는 템플릿 값 그대로)."
    echo "  server/.env.local 을 열어 실제 키를 넣고 다시 실행하세요:"
    echo "      ANTHROPIC_API_KEY=sk-ant-..."
    echo "  또는 환경변수로:  ANTHROPIC_API_KEY=sk-ant-... ./start.sh"
    echo "  키 발급: https://console.anthropic.com → API Keys"
    exit 1
    ;;
esac
echo "▶ ✓ API 키 확인됨"

# 6) 기동 — run.sh api 가 .env.local 로드 + 최종 검증 + URL 배너 + uvicorn 실행
exec ./server/run.sh api
