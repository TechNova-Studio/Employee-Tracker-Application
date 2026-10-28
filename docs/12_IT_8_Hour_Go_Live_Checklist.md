# 12. IT 8-Hour Go-Live Checklist

Follow this exact order. Do not redesign or change architecture during staging.

## 0. Folder

Extract only:

```text
BOLD_WorkPulse_FINAL_MERGED_IT_READY_QA_PATCHED.zip
```

Expected extracted folder:

```text
bold-workpulse/
```

## 1. Check required software

Use:

- Python 3.11 or 3.12 only
- Node.js LTS
- PostgreSQL 14+

Commands:

```bat
python --version
node --version
npm --version
psql --version
```

Expected result: commands print versions without error.

## 2. Create PostgreSQL database

Open pgAdmin or psql and create:

```sql
CREATE DATABASE bold_workpulse;
```

## 3. Configure environment

From `bold-workpulse` root:

```bat
copy .env.example .env
notepad .env
```

Fill only these first:

```env
DB_NAME=bold_workpulse
DB_USER=postgres
DB_PASSWORD=YOUR_POSTGRES_PASSWORD
DB_HOST=localhost
DB_PORT=5432
SCREENSHOT_STORAGE_MODE=local
AI_PROVIDER=mock
```

Expected result: `.env` exists in project root, not inside backend.

## 4. Backend setup

```bat
scripts\setup_backend_windows.bat
```

Expected result:

- virtualenv created
- requirements installed
- `python manage.py migrate` completed
- `python manage.py seed_demo_data` completed

Common error:

- `password authentication failed`: fix `DB_PASSWORD` in `.env`.
- `database does not exist`: create `bold_workpulse` database.

## 5. Start backend

```bat
scripts\run_backend_windows.bat
```

Open:

```text
http://localhost:8000/api/health/
```

Expected result:

```json
{"status":"ok","product":"BOLD WorkPulse"}
```

## 6. Admin web setup and run

Open a second Command Prompt:

```bat
scripts\setup_admin_web_windows.bat
scripts\run_admin_web_windows.bat
```

Open:

```text
http://localhost:5174
```

Login:

```text
superadmin@boldworkpulse.local
Demo@12345
```

Expected result: dashboard opens without raw JSON form dependency for core screens.

## 7. Desktop agent setup and run

Open a third Command Prompt:

```bat
scripts\setup_desktop_agent_windows.bat
scripts\run_desktop_agent_windows.bat
```

Login:

```text
employee@glutape.local
Demo@12345
```

Expected result:

1. Version check passes.
2. Policy screen appears if not accepted.
3. Accept policy.
4. Start work session.
5. Heartbeat/activity/screenshot uploads begin.

## 8. Run AI summary command

From backend folder:

```bat
cd backend
venv\Scripts\activate
python manage.py generate_daily_ai_summaries
python manage.py process_pending_ai_jobs
```

Expected result: AI summaries are created using mock/rule-based fallback.

## 9. Screenshot test

In admin web:

1. Open Screenshot Viewer.
2. Click Refresh.
3. Click View.
4. Click Download.
5. Click Delete only for test screenshot.

Expected result:

- Screenshot opens through protected endpoint.
- No direct media URL is shown.
- Access logs are created.

## 10. Trial test

In admin web as Super Admin or Sales/Admin:

1. Open Demo Code Generator.
2. Generate 5-day code.
3. Open Trial Signup Page.
4. Validate code.
5. Create trial company.
6. Open Trial Dashboard.
7. Extend trial.
8. Convert trial to BASIC.

Expected result: extend/convert/cancel only works for allowed scoped trial companies.

## 11. Permission smoke tests

Use different logins:

| Login | Must confirm |
|---|---|
| Super Admin | Sees all companies and all dashboard totals |
| Company Admin | Sees only Glutape company data |
| HR/Admin | Sees own company policy/employee/activity scope |
| Sales/Admin | Sees own generated/assigned trial dashboard only |
| Manager | Sees assigned team summary only |
| Employee | Sees only own records and cannot open ERP events, audit logs, billing or screenshots of others |

## 12. Report format for blockers only

Send:

- Command used
- Screenshot
- URL
- Login used
- Expected result
- Actual result
- Time of test

## Do not change these rules without management approval

- Do not run `makemigrations` unless management approves a model change.
- Do not add Docker/Redis/Celery/Kubernetes.
- Do not switch screenshot storage to S3 during staging.
- Do not switch AI provider from `mock` during staging.


## Desktop npm install note

The desktop agent uses Electron. During `npm install`, Electron may download its runtime binary from Electron/GitHub download URLs in addition to the public npm registry. If desktop setup fails with a network/DNS error, first confirm internet access to public npm and Electron/GitHub download URLs. Do not solve this by adding Docker, Redis, Celery or changing architecture.
