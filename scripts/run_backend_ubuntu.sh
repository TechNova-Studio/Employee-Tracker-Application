#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000
