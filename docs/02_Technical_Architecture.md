# 02 Technical Architecture

## Stack

- Backend: Django, Django REST Framework, PostgreSQL.
- Admin Web: React + Vite.
- Desktop Agent: Electron + React + active-win + screenshot-desktop.
- Storage: local media fallback; S3-compatible placeholder for production.
- AI: Django management commands with rule-based fallback.

## No-Docker architecture

This pack intentionally avoids Docker, Redis, Celery, Kubernetes, microservices and CI/CD dependency. Junior IT can run it using normal commands.

## Main components

1. `backend/` - API, models, admin, management commands.
2. `admin-web/` - web admin panel.
3. `desktop-agent/` - employee agent.
4. `docs/` - handholding documents.
5. `scripts/` - Windows setup/run scripts.

## Data flow

1. Employee opens desktop agent.
2. Agent checks version.
3. Employee logs in.
4. Agent registers device.
5. Agent fetches active policy.
6. Employee accepts policy.
7. Employee starts session.
8. Agent sends heartbeat/activity/screenshot.
9. Admin views dashboards and reports.
10. Management command generates daily AI summary.

## Tenant isolation

Most operational models include a `company` FK. API viewsets filter querysets by logged-in user's company unless the user is Super Admin.

## External integrations

- S3: controlled by `.env` and storage mode.
- AI provider: controlled by `.env`; mock/rule fallback works without key.
- Razorpay/Stripe: skeleton only until credentials are available.
- Glutape ERP: optional API token connector.
