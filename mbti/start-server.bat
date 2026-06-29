@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Buddy 서버를 시작합니다... (종료하려면 이 창에서 Ctrl+C)
powershell -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
