#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
echo "Backend setup complete. Initial migration file is included; do not run makemigrations during staging setup."
