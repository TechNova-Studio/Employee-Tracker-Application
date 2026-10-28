@echo off
echo === BOLD WorkPulse Backend Setup ===
cd /d %~dp0\..\backend
IF NOT EXIST ..\.env (
  echo ERROR: .env not found. Copy .env.example to .env at project root first.
  exit /b 1
)
python -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
echo Backend setup complete. Initial migration file is included; do not run makemigrations during staging setup.
pause
