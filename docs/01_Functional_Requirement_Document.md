# 01 Functional Requirement Document

## 1. SaaS and company management
- Super Admin can create and view companies.
- Company Admin and HR/Admin can operate only within their company.
- Manager can see assigned team.
- Employee can see own session/status only.
- Glutape India Pvt. Ltd. is seeded as internal tenant.

## 2. Employee desktop agent
- Login.
- Version check before login.
- Device registration.
- Policy acknowledgement before work session.
- Start/stop session.
- Heartbeat.
- Active app/window title capture.
- Browser/domain capture where detectable from title.
- Idle/active time.
- Screenshot capture during active session.
- Offline queue and sync.

## 3. Monitoring policy
- Latest active company policy must be accepted before work session.
- Decline blocks user and alerts HR/Admin.
- New policy version requires fresh acceptance.

## 4. Force update
- API: `/api/agent/version-check/`.
- If installed version is below minimum supported version, login/session upload is blocked.
- Admin can manage agent version in web panel/API.

## 5. Productivity rules
- Company and department level app/domain/window rules.
- Categories: PRODUCTIVE, NEUTRAL, UNPRODUCTIVE, UNKNOWN.

## 6. Screenshots
- Captured only during active work session.
- Local media storage works for staging.
- S3-compatible fields are present for production.
- Every view/download/delete can be logged.
- Retention cleanup command is supplied.

## 7. AI daily analysis
- Command: `python manage.py generate_daily_ai_summaries`.
- Uses app/domain/activity/screenshot metadata.
- No automatic punishment; manager review is required.
- Rule-based fallback works without external AI key.

## 8. Alerts
Alerts exist for long idle, outdated agent, policy declined, AI risk flags and are extendable for screenshot failure, unknown devices, trial expiry and inactive-running sessions.

## 9. Demo/trial accounts
Sales/Admin can generate trial code. Customer can validate and create a trial company. Trial can be extended, expired or converted to paid/internal plan.

## 10. Billing skeleton
Plans and subscriptions exist for Internal, Trial, Basic, Pro, Business and Enterprise. Razorpay/Stripe production calls are placeholders until credentials are configured.

## 11. Glutape ERP connector
WorkPulse is separate. Glutape ERP can send events using API token to `/api/erp/ingest/`.

## Acceptance rule
The staging test passes when an employee can login, accept policy, start session, send heartbeat/activity, upload screenshot, and admin can view dashboard, alerts, AI summary and trial code flows.
