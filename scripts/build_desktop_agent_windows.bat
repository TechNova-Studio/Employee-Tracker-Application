@echo off
cd /d %~dp0\..\desktop-agent
npm run build:win
pause
