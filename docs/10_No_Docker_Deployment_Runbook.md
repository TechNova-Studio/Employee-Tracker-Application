# 10. No-Docker Deployment Runbook

## Rule

BOLD WorkPulse v1 staging must run without Docker, Redis, Celery, Kubernetes, microservices or CI/CD.

## Backend

```bat
copy .env.example .env
notepad .env
scripts\setup_backend_windows.bat
scripts\run_backend_windows.bat
```

Expected backend URL:

```text
http://localhost:8000/api/health/
```

## Admin web

```bat
scripts\setup_admin_web_windows.bat
scripts\run_admin_web_windows.bat
```

Expected admin URL:

```text
http://localhost:5174
```

## Desktop agent

```bat
scripts\setup_desktop_agent_windows.bat
scripts\run_desktop_agent_windows.bat
```

## Background commands

No Celery is used. Run management commands manually or through Windows Task Scheduler later.

```bat
cd backend
venv\Scripts\activate
python manage.py generate_daily_ai_summaries
python manage.py process_pending_ai_jobs
python manage.py cleanup_old_screenshots
```

## Staging defaults

```env
SCREENSHOT_STORAGE_MODE=local
AI_PROVIDER=mock
```

## Rollback

1. Stop command windows.
2. Keep database backup if created.
3. Do not use older ZIPs.
4. Report exact command error.

## Do not change these rules without management approval

- Do not add Docker.
- Do not add Redis/Celery.
- Do not change architecture during staging.
