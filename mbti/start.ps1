# start.ps1 — start.sh 의 Windows(PowerShell) 버전.
#
#   우클릭 > "PowerShell로 실행"  또는  터미널에서:  .\start.ps1
#
# 하는 일: .venv 활성화 → server/.env.local 의 키 로드/검증 → auto 백엔드로 uvicorn 기동.
# 전제: 한 번은 setup 이 되어 있어야 함(.venv + deps). 안 되어 있으면 아래 안내가 뜸.
# 기본은 auto(F형->Claude, T형->GPT, 두 키 필요). 다른 백엔드는 -Backend 인자로:
#   .\start.ps1 -Backend api       # Anthropic 키만
#   .\start.ps1 -Backend openai    # OpenAI 키만
param([string]$Backend = "auto")

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Windows 콘솔에서 한글/특수문자 출력 깨짐·인코딩 에러 방지
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "[X] .venv 가 없습니다. 먼저 설치하세요:" -ForegroundColor Red
  Write-Host "    python -m venv .venv"
  Write-Host "    .venv\Scripts\python.exe -m pip install -e `".[server]`""
  exit 1
}

# server/.env.local 로드 (KEY=VALUE 줄만, 주석/빈 줄 무시)
$envFile = Join-Path $PSScriptRoot "server\.env.local"
if (-not (Test-Path $envFile)) {
  Copy-Item (Join-Path $PSScriptRoot "server\.env.example") $envFile
  Write-Host "[i] server\.env.local 생성됨 — 실제 키를 넣고 다시 실행하세요." -ForegroundColor Yellow
}
foreach ($line in Get-Content $envFile -Encoding UTF8) {
  if ($line -match '^\s*#') { continue }
  if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
    $name = $matches[1]; $val = $matches[2].Trim()
    # 플레이스홀더(빈 값 · 한글 견본 · '여기에' 포함)는 환경에 넣지 않는다.
    # → auto 라우팅과 서버가 '진짜 키'만 인식하도록. (API 키는 항상 ASCII)
    if ([string]::IsNullOrWhiteSpace($val) -or $val -match '[^\x00-\x7F]' -or $val -like '*여기에*') { continue }
    Set-Item -Path "Env:$name" -Value $val
  }
}

function Has-Key([string]$name) {
  # 위 로더가 플레이스홀더는 환경에 안 넣으므로, 값이 있으면 진짜 키.
  $v = (Get-Item "Env:$name" -ErrorAction SilentlyContinue).Value
  return -not [string]::IsNullOrWhiteSpace($v)
}

function Need-Key([string]$name, [string]$hint) {
  if (-not (Has-Key $name)) {
    Write-Host "[X] $name 가 비었거나 템플릿 값 그대로입니다." -ForegroundColor Red
    Write-Host "    server\.env.local 을 열어 실제 키를 넣으세요. (발급: $hint)"
    exit 1
  }
}

switch ($Backend) {
  "auto"   {
    # 가진 키로 자동 폴백 → 세 키 중 최소 하나만 있으면 됨.
    if (-not (Has-Key "ANTHROPIC_API_KEY") -and -not (Has-Key "OPENAI_API_KEY") -and -not (Has-Key "GEMINI_API_KEY")) {
      Write-Host "[X] AI 키가 하나도 없습니다. server\.env.local 에 아래 중 하나라도 넣으세요:" -ForegroundColor Red
      Write-Host "    ANTHROPIC_API_KEY  (https://console.anthropic.com)"
      Write-Host "    OPENAI_API_KEY     (https://platform.openai.com)"
      Write-Host "    GEMINI_API_KEY     (https://aistudio.google.com  ·무료, 이것만으로도 비전 분석 가능)"
      exit 1
    }
    $env:SERVER_AI_BACKEND = "auto"
    $have = @()
    if (Has-Key "ANTHROPIC_API_KEY") { $have += "Claude" }
    if (Has-Key "OPENAI_API_KEY")    { $have += "GPT" }
    if (Has-Key "GEMINI_API_KEY")    { $have += "Gemini" }
    Write-Host "[>] AI 백엔드: auto (F형->Claude, T형->GPT, 빈 자리는 Gemini 폴백 · 보유: $($have -join ' '))" -ForegroundColor Green
  }
  "api"    {
    Need-Key "ANTHROPIC_API_KEY" "https://console.anthropic.com"
    $env:SERVER_AI_BACKEND = "api"
    Write-Host "[>] AI 백엔드: api (Anthropic 비전)" -ForegroundColor Green
  }
  "openai" {
    Need-Key "OPENAI_API_KEY" "https://platform.openai.com"
    $env:SERVER_AI_BACKEND = "openai"
    Write-Host "[>] AI 백엔드: openai (GPT)" -ForegroundColor Green
  }
  "gemini" {
    Need-Key "GEMINI_API_KEY" "https://aistudio.google.com (무료)"
    $env:SERVER_AI_BACKEND = "gemini"
    Write-Host "[>] AI 백엔드: gemini (Gemini 2.5 Flash · 무료·비전)" -ForegroundColor Green
  }
  default  { Write-Host "[X] 알 수 없는 -Backend: $Backend (auto|api|openai|gemini)" -ForegroundColor Red; exit 1 }
}

$bind = if ($env:HOST) { $env:HOST } else { "0.0.0.0" }
$port = if ($env:PORT) { $env:PORT } else { "8000" }

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host "  서버 기동 — 바인딩 ${bind}:${port}  (같은 와이파이의 다른 기기/폰에서도 접속)"
Write-Host "    이 PC:        http://localhost:${port}/"
Write-Host "    Swagger 문서: http://localhost:${port}/docs"
Write-Host "    헬스체크:     http://localhost:${port}/health"
Write-Host "    종료: Ctrl+C"
Write-Host "------------------------------------------------------------"

& $py -m uvicorn server.main:app --host $bind --port $port --reload
