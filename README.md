# EMPLOYEE TRACKER — Admin Web and Backend Only

This package contains the complete `admin-web/` and `backend/` source folders.
The latest backend productivity URL/domain matching fix is included.
The current admin dashboard, employee management, reports and light/dark UI are included.

## Admin web

Use your existing admin-web environment configuration. For a fresh checkout,
create `admin-web/.env` and set the actual WorkPulse backend API URL, including `/api`:

```dotenv
VITE_API_BASE_URL=https://your-workpulse-backend.example/api
```

Replace the example with your staging/live WorkPulse backend. Then run:

```powershell
cd admin-web
npm ci
npm run dev
```

Production build: `npm run build`. Vite embeds environment values during build,
so rebuild the admin web after changing its backend URL.

## Backend

Use your existing backend environment/database configuration. For a fresh
Python virtual environment, install the existing requirements and database URL parser:

```powershell
cd backend
python -m pip install -r requirements.txt dj-database-url==2.2.0
python manage.py check
python manage.py runserver
```

For an existing deployment, the productivity matching fix needs no new database
migration. New databases still need the project's normal migrations before use.
Keep `core/views.py` and `core/activity_context.py` together when deploying.

Check the approved Glutape rules in the chosen backend environment:

```text
python manage.py verify_glutape_productivity_rules --company-id 1
```

The approved 20 rules and department overrides are retained. Exact native APP
rules still need confirmed telemetry names. Existing activity classifications
are retained, so historical reports do not silently change.

## Browser activity dependency

Browser DOMAIN/URL rules require a real URL/domain from the installed agent.
A blank-domain record with only a title such as `WhatsApp - Google Chrome`
cannot reliably identify the website. The previously provided agent 1.0.5 adds
Windows browser URL capture; this archive supplies the admin/backend components.
No desktop source, Electron runtime, node_modules, installer, live environment
files, database files or screenshot data is packaged here.

## Verification

The latest backend passed 62 automated tests and 150 approved Glutape rule
examples. Admin source is preserved from the latest admin-web archive.
Archive integrity and component boundaries were checked during packaging.
See `backend/TEST_RESULTS.json` and `admin-web/DASHBOARD_VERIFICATION.json` for
component-specific evidence. Deployment and employee-PC validation are separate.
