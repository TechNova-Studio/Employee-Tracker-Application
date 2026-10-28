# 18. Backend, Frontend and Desktop IT Execution Guide

This document is written specifically for the Glutape IT team. Follow this document exactly. Do not redesign, refactor, add Docker, add Redis/Celery, change architecture, or merge older ZIPs.

## Final source-of-truth ZIP

Use only:

```text
BOLD_WorkPulse_FINAL_MERGED_IT_READY_QA_PATCHED.zip
```

Do not use older WorkPulse ZIPs and do not copy code from the Kimi version or earlier generated versions.

## Team responsibility split

| Person | Responsibility | What not to do |
|---|---|---|
| Backend IT person | PostgreSQL DB, `.env`, Django setup, migrations, seed data, backend APIs, permissions smoke test | Do not change models, do not run `makemigrations`, do not add Docker/Redis/Celery |
| Frontend IT person | Admin web setup, page navigation test, role login test, trial screens, screenshot viewer test | Do not change API endpoints, do not bypass permission errors, do not point to old backend |
| Desktop/Electron IT person | Desktop agent setup, employee login, policy acceptance, session, heartbeat, screenshot, Windows build test | Do not add keylogger/clipboard/webcam/microphone, do not bypass force update or policy |
| Manager/Reviewer | Record pass/fail evidence and send blocker report | Do not ask for redesign during first run |

## First-day staging rule

For the first staging run use only:

```env
SCREENSHOT_STORAGE_MODE=local
AI_PROVIDER=mock
```

Do not configure S3, real AI API, Razorpay/Stripe, domain, SSL or code signing during the first 8-hour staging run.

## Backend IT person: exact steps

### 1. Extract ZIP

Extract the ZIP. Expected folder:

```text
bold-workpulse/
```

### 2. Check required software

Open Command Prompt:

```bat
python --version
node --version
npm --version
psql --version
```

Required:

- Python 3.11 or 3.12 only
- Node.js LTS
- PostgreSQL 14+

Do not use Python 3.13 for the first staging run.

### 3. Create database

Create PostgreSQL database:

```sql
CREATE DATABASE bold_workpulse;
```

### 4. Configure `.env`

From `bold-workpulse` root:

```bat
copy .env.example .env
notepad .env
```

Set only these values first:

```env
DB_NAME=bold_workpulse
DB_USER=postgres
DB_PASSWORD=YOUR_POSTGRES_PASSWORD
DB_HOST=localhost
DB_PORT=5432
SCREENSHOT_STORAGE_MODE=local
AI_PROVIDER=mock
```

Expected: `.env` is in the project root, not inside `backend`.

### 5. Run backend setup

```bat
scripts\setup_backend_windows.bat
```

Expected:

- virtualenv is created inside backend
- Python packages install
- migrations run
- seed data command runs
- demo users are created

Important: do not run `makemigrations` during staging unless management approves a model change.

### 6. Start backend

```bat
scripts\run_backend_windows.bat
```

Open:

```text
http://localhost:8000/api/health/
```

Expected:

```json
{"status":"ok","product":"BOLD WorkPulse"}
```

### 7. Backend smoke tests

Test these using admin web or API tool:

| Test | Expected |
|---|---|
| Super Admin login | Success |
| Employee login | Success, but session blocked until policy accepted |
| Company Admin creates company | Blocked |
| Company Admin creates plan | Blocked |
| Employee opens audit logs | Blocked |
| Employee opens ERP events | Blocked |
| Session start before policy | Blocked |
| Session start after policy | Allowed |

## Frontend IT person: exact steps

### 1. Start admin web setup

Open second Command Prompt from `bold-workpulse` root:

```bat
scripts\setup_admin_web_windows.bat
scripts\run_admin_web_windows.bat
```

Open:

```text
http://localhost:5174
```

### 2. Login test

Login:

```text
superadmin@boldworkpulse.local
Demo@12345
```

Expected: Dashboard opens.

### 3. Screen test order

Test screens in this order:

1. Dashboard
2. Users / Employees
3. Departments
4. Agent Versions
5. Policy + Acceptances
6. Devices
7. Attendance Sessions
8. Activity Timeline
9. Screenshot Viewer
10. AI Daily Summaries
11. Alerts
12. Demo Code Generator
13. Trial Dashboard
14. Trial Signup Page
15. Billing Placeholder
16. ERP Connector Settings
17. Audit Logs

### 4. Trial test

As Super Admin or Sales/Admin:

1. Open Demo Code Generator.
2. Generate 5-day trial code.
3. Open Trial Signup Page.
4. Validate code.
5. Create trial company.
6. Open Trial Dashboard.
7. Extend trial.
8. Convert trial to BASIC.

Expected: trial company is created, extended and converted without IT database editing.

### 5. Frontend rules

Do not change API endpoint names. If a 403 error appears, first check whether the logged-in role is allowed for that action. Do not bypass backend permissions from frontend.

## Desktop/Electron IT person: exact steps

### 1. Start desktop setup

Open third Command Prompt from `bold-workpulse` root:

```bat
scripts\setup_desktop_agent_windows.bat
scripts\run_desktop_agent_windows.bat
```

### 2. Employee login

Login:

```text
employee@glutape.local
Demo@12345
```

Expected first-run flow:

1. Version check passes.
2. Employee login succeeds.
3. Policy screen appears.
4. Employee accepts policy.
5. Start Work Session button appears.
6. Start session.
7. Heartbeat/activity begin uploading.
8. Screenshot upload happens after configured interval / initial delay.

### 3. Admin verification

After desktop session starts, frontend/admin person should verify:

| Admin screen | Expected result |
|---|---|
| Devices | Employee device visible |
| Attendance | Running/stopped session visible |
| Activity Timeline | App/window activity visible |
| Screenshot Viewer | Screenshot appears after capture/upload |
| Alerts | Long idle/outdated/policy alerts if triggered |

### 4. Desktop build test

Only after dev run succeeds:

```bat
scripts\build_desktop_agent_windows.bat
```

Production code signing is external configuration. Do not stop staging because code signing is not available.

## AI summary test

After session/activity exists, backend person runs:

```bat
cd backend
venv\Scripts\activate
python manage.py generate_daily_ai_summaries
python manage.py process_pending_ai_jobs
```

Expected: AI summary appears in admin web using mock/rule-based fallback.

## Screenshot cleanup test

Backend person runs:

```bat
python manage.py cleanup_old_screenshots
```

Expected: command runs without error. It may delete nothing during staging.

## Blocker reporting format

If anything fails, send only this format:

| Field | Required detail |
|---|---|
| Area | Backend / Admin Web / Desktop Agent |
| Command used | Exact command copied from Command Prompt |
| URL | Exact URL tested |
| Login used | Email/role |
| Expected result | What should have happened |
| Actual result | What happened |
| Screenshot | Attach screenshot |
| Time | Time of test |

Do not send vague messages like “not working”.

## Common issues and fixes

| Issue | Likely reason | Fix |
|---|---|---|
| `database does not exist` | DB not created | Create `bold_workpulse` in PostgreSQL |
| `password authentication failed` | Wrong DB password in `.env` | Correct `DB_PASSWORD` |
| `npm install` fails | Internet/npm registry issue | Confirm system can access public npm registry |
| Backend health fails | Backend not running or migration failed | Check backend command window |
| Admin API failed | Backend not running or wrong API URL | Confirm `http://localhost:8000/api/health/` |
| Desktop login fails | Backend not running | Start backend first |
| Policy blocks session | Policy not accepted | Accept policy in desktop agent |
| Policy declined blocks login | Employee declined policy | HR/Admin reactivates user in admin web |
| Screenshot not visible | No session/screenshot yet | Start session and wait for screenshot upload |
| Old version blocked | Agent minimum version rule | Check Agent Version screen |

## Final instruction

First make the supplied staging flow work. Do not add features, change architecture, use older ZIPs, or start redesign during the first run.


## Desktop npm install note

The desktop agent uses Electron. During `npm install`, Electron may download its runtime binary from Electron/GitHub download URLs in addition to the public npm registry. If desktop setup fails with a network/DNS error, first confirm internet access to public npm and Electron/GitHub download URLs. Do not solve this by adding Docker, Redis, Celery or changing architecture.
