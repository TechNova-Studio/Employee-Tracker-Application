# 04. API Documentation

Base URL for staging:

```text
http://localhost:8000/api
```

Authentication uses DRF Token Authentication:

```http
Authorization: Token <token>
```

## Health and auth

| Method | Endpoint            | Purpose                                                 |
| ------ | ------------------- | ------------------------------------------------------- |
| GET    | `/api/health/`      | Backend health check                                    |
| POST   | `/api/auth/login/`  | Login; returns blocked status for policy-declined users |
| POST   | `/api/auth/logout/` | Logout audit record                                     |
| GET    | `/api/auth/me/`     | Current user/profile/company                            |

Login payload:

```json
{ "email": "superadmin@boldworkpulse.local", "password": "Demo@12345" }
```

## Admin resources

| Resource              | Endpoint                        |
| --------------------- | ------------------------------- |
| Plans                 | `/api/plans/`                   |
| Companies             | `/api/companies/`               |
| Departments           | `/api/departments/`             |
| Users                 | `/api/users/`                   |
| Subscriptions         | `/api/subscriptions/`           |
| Devices               | `/api/devices/`                 |
| Agent Versions        | `/api/agent-versions/`          |
| Policies              | `/api/policies/`                |
| Policy Acceptances    | `/api/policy-acceptances/`      |
| Sessions              | `/api/sessions/`                |
| Activities            | `/api/activities/`              |
| Screenshots           | `/api/screenshots/`             |
| Productivity Rules    | `/api/productivity-categories/` |
| Alerts                | `/api/alerts/`                  |
| AI Summaries          | `/api/ai-summaries/`            |
| Manager Reviews       | `/api/manager-reviews/`         |
| Demo Trial Codes      | `/api/demo-trial-codes/`        |
| Trial Signup Logs     | `/api/trial-signup-logs/`       |
| Trial Conversion Logs | `/api/trial-conversion-logs/`   |
| ERP Connectors        | `/api/erp-connectors/`          |
| ERP Events            | `/api/erp-events/`              |
| Audit Logs            | `/api/audit-logs/`              |
| Billing Invoices      | `/api/billing-invoices/`        |

All list/detail APIs are role-scoped by backend. Do not bypass this in frontend.
`/api/sessions/` and `/api/activities/` are read-only lists; use the desktop agent endpoints to create records. They accept `company_id` (Super Admin only), `user_id`, `from_date`, `to_date`, `page` and `status` (sessions) or `productivity` (activities). `/api/sessions/filter-options/` supplies scoped company/employee choices.

## Desktop agent APIs

| Method | Endpoint                                        | Important rule                                                       |
| ------ | ----------------------------------------------- | -------------------------------------------------------------------- |
| GET    | `/api/agent/version-check/`                     | Public check for latest/minimum supported version                    |
| POST   | `/api/agent/device/register/`                   | Rejects unsupported app version                                      |
| POST   | `/api/agent/session/start/`                     | Rejects unsupported version and blocks if latest policy not accepted |
| POST   | `/api/agent/session/stop/`                      | Stops own running session                                            |
| GET    | `/api/agent/session/status/`                    | Own running session                                                  |
| POST   | `/api/agent/heartbeat/`                         | Rejects unsupported version                                          |
| POST   | `/api/agent/activity/batch/`                    | Rejects unsupported version                                          |
| POST   | `/api/agent/screenshots/upload/`                | Rejects unsupported version; local storage works in staging          |
| POST   | `/api/agent/screenshots/presigned-placeholder/` | S3 placeholder only; not required for staging                        |

## Policy APIs

| Method | Endpoint               | Purpose                                                                       |
| ------ | ---------------------- | ----------------------------------------------------------------------------- |
| GET    | `/api/policy/current/` | Fetch current active policy and acceptance status                             |
| POST   | `/api/policy/accept/`  | Requires the current `policy_id`; stale policy returns 409; declined users need HR reactivation |
| POST   | `/api/policy/decline/` | Requires the current `policy_id`; stops the session and blocks login/session |

Policy text is immutable after publication. The Admin Web creates another version to change it; `GET /api/policies/company-options/` provides company dropdown values. See [Policy & Attendance Flow](POLICY_ATTENDANCE_ACTIVITY_FLOW.md).

## Screenshot protected access

| Method | Endpoint                             | Purpose                                    |
| ------ | ------------------------------------ | ------------------------------------------ |
| GET    | `/api/screenshots/<id>/view/`        | Protected screenshot view; logs access     |
| GET    | `/api/screenshots/<id>/download/`    | Protected screenshot download; logs access |
| POST   | `/api/screenshots/<id>/soft-delete/` | Logged soft delete                         |
| DELETE | `/api/screenshots/<id>/`             | Logged soft delete; not silent hard delete |

Do not expose direct media file URLs in UI.

## Reports

| Method | Endpoint                          | Scope                           |
| ------ | --------------------------------- | ------------------------------- |
| GET    | `/api/reports/dashboard-summary/` | Role-specific dashboard summary |
| GET    | `/api/reports/attendance/`        | Role-specific attendance report |
| GET    | `/api/reports/activity/`          | Role-specific activity report   |

## Trial/demo APIs

| Method | Endpoint                    | Purpose                                               |
| ------ | --------------------------- | ----------------------------------------------------- |
| POST   | `/api/trial/validate-code/` | Public demo code validation                           |
| POST   | `/api/trial/signup/`        | Public trial company creation through valid code only |
| POST   | `/api/trial/extend/`        | Scoped trial extension                                |
| POST   | `/api/trial/convert/`       | Scoped conversion to paid/internal based on role      |
| POST   | `/api/trial/cancel/`        | Scoped trial cancellation                             |
| GET    | `/api/trial/companies/`     | Scoped trial companies                                |
| GET    | `/api/trial/dashboard/`     | Scoped trial dashboard                                |

Sales/Admin cannot extend, convert or cancel random companies by ID.

## ERP connector API

| Method | Endpoint           | Purpose                                |
| ------ | ------------------ | -------------------------------------- |
| POST   | `/api/erp/ingest/` | Public token-based ERP event ingestion |

Token can be sent as header:

```http
X-WORKPULSE-TOKEN: <connector-token>
```

The connector token is accepted only in the `X-WORKPULSE-TOKEN` header; an `api_token` body field is not supported.

## Management commands

Run from backend folder:

```bat
venv\Scripts\activate
python manage.py generate_daily_ai_summaries
python manage.py process_pending_ai_jobs
python manage.py cleanup_old_screenshots
```

## Do not change these rules without management approval

- Do not expose direct screenshot URLs.
- Do not remove role/tenant scoping.
- Do not allow public company creation except trial signup.
- Do not add Docker/Redis/Celery/Kubernetes for staging.

## Screenshot / AI / Trial update

See [Screenshot, AI and Trial Flow](SCREENSHOT_AI_TRIAL_FLOW.md) for filters, generation/review APIs, signup validation and lifecycle examples. Trial company listing now returns the standard paginated envelope (`count`, `next`, `previous`, `results`); signup returns HTTP 201. Use the accompanying `Postman_Screenshot_AI_Trial.postman_collection.json` to test these flows.

## Billing / ERP settings update

See [Billing & ERP Flow](BILLING_ERP_FLOW.md) for controlled subscription configuration, invoice lifecycle APIs and secure connector token actions. Raw subscription writes and invoice edits/deletes are disabled. Company Admin billing access is read-only; Super Admin owns billing changes. Connector list/detail responses no longer expose the full token. Apply migration `0003_billinginvoice_billing_cycle_and_more`.
