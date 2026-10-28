@echo off
echo === BOLD WorkPulse Desktop Agent Setup ===
cd /d %~dp0\..\desktop-agent
npm install
echo Desktop agent setup complete.
pause
