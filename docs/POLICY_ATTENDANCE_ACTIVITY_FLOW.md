# Policy acceptance, attendance and activity

## Admin Web flow

1. Sign in as Super Admin, select a company on **Monitoring Policy & Acceptances**, and publish a version with its title and full policy text. Company Admin/HR are assigned their own company automatically.
2. A newly active version replaces the prior active policy for that company. Its text, title and version cannot be edited after publication; publish another version to change the content. Deactivate/activate existing versions from the table. Deleting a version is disabled so historical acceptances remain auditable.
3. Ask the employee to sign in to the desktop agent, read the current policy and accept or decline it. **Acceptance History** shows employee, policy version, response and time. A decline blocks login and tracking until HR reactivates the employee. Reactivation requires a fresh acceptance.
4. Check **Attendance Sessions** for employee, company, start/stop, status, active/idle seconds and device. Check **Activity Timeline** for app/window/domain, category, duration and mouse/keyboard counts. Use company, employee, date and status/category filters and Previous/Next for more than 50 records.

Super Admin sees all tenants, Company Admin/HR only their company, Manager only assigned team records, Employee only their own records. The list APIs are read-only; the desktop endpoints alone write session and activity records.

## Agent behavior

- On login or restart, the agent fetches the latest active company policy. If none is published, the agent shows **Policy unavailable** and cannot start a session.
- `POST /api/policy/accept/` and `/api/policy/decline/` require the `policy_id` the employee read. If a new policy was published while the employee was reading, the server responds `409 POLICY_CHANGED`; the agent refreshes the new text before a decision.
- Session start requires a registered device, a supported agent version and the latest active policy acceptance. The first heartbeat runs after the first minute; stopping sooner sends a final partial heartbeat. Only successfully accepted heartbeats add to active/idle totals.
- A newly active policy auto-stops running sessions. A later heartbeat/activity/screenshot attempt returns `403 POLICY_NOT_ACCEPTED`; the agent stops tracking and presents the new policy. The desktop dashboard also lets employees review the accepted policy and withdraw consent. Declining/withdrawing auto-stops the session and blocks further tracking.
- If the agent crashes with a locally remembered session, restart closes that session. If another session replaced the current one, the agent stops the old tracking loop when the server responds `404`.
- Offline heartbeat and activity requests are queued. The agent tries to sync pending items before stopping and before starting a new session; when an activity request fails after a successful heartbeat, only the activity is queued so attendance totals are not duplicated by that retry. Records from sessions already invalidated by a policy change remain in the local queue and require IT review.

## API examples for Postman

All requests below use `Authorization: Token <TOKEN>`; POST/PATCH requests use `Content-Type: application/json`.

```http
POST /api/policies/
{"company":1,"version":"2.0","title":"Workplace monitoring","body":"Full policy shown to the employee","is_active":true}
```

`company` is mandatory for Super Admin and omitted for Company Admin/HR. Then fetch `GET /api/policy/current/` using the employee's token. The response contains the active `policy.id`, `accepted` and any `blocked_reason`.

```http
POST /api/policy/accept/
{"policy_id":12,"device_id":"AGENT-DEVICE-ID"}
```

Use the same `policy_id` for `POST /api/policy/decline/`. Create the device before starting a session:

```http
POST /api/agent/device/register/
{"device_id":"AGENT-DEVICE-ID","app_version":"1.0.0","platform":"windows"}

POST /api/agent/session/start/
{"device_id":"AGENT-DEVICE-ID","app_version":"1.0.0","platform":"windows"}
```

Use the returned session ID for heartbeats and activity:

```http
POST /api/agent/heartbeat/
{"session_id":25,"device_id":"AGENT-DEVICE-ID","app_version":"1.0.0","platform":"windows","active_seconds":45,"idle_seconds":0,"is_idle":false}

POST /api/agent/activity/batch/
{"session_id":25,"device_id":"AGENT-DEVICE-ID","app_version":"1.0.0","platform":"windows","activities":[{"app_name":"Chrome","domain":"crm.example.com","window_title":"CRM","duration_seconds":45,"mouse_count":3,"keyboard_count":2}]}
```

Lists: `GET /api/sessions/?company_id=1&user_id=8&from_date=2026-09-01&to_date=2026-09-25&status=STOPPED&page=1` and `GET /api/activities/?company_id=1&user_id=8&productivity=PRODUCTIVE&page=1`. `GET /api/sessions/filter-options/?company_id=1` returns scoped company/employee dropdown options. `GET /api/policies/company-options/` returns policy company options.

Run integration tests from `backend` with `python manage.py test core.tests --settings=workpulse_project.test_settings`. Build each UI with `npm run build` in `admin-web`, and `npm run build:react` in `desktop-agent` after installing its npm dependencies.
