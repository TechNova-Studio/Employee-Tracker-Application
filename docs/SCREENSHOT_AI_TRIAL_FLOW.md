# Screenshot, AI Summary, Demo Code and Trial flows

## Apply and run

Use this ZIP as the updated source. Keep your existing local `.env` and database.

```bat
cd backend
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

In another terminal:

```bat
cd admin-web
npm install
npm run dev
```

Restart the desktop agent after updating its source. This change adds no database migration; `migrate` applies any previous pending migrations.

## Screenshot Viewer

- Select company (Super Admin), employee and date range. Lists are paginated with 50 rows per page.
- **View screenshot** opens an authenticated preview inside the page. Fit/actual size and previous/next apply to the loaded page.
- Downloads use the actual image format. Preview blob URLs are revoked on close/change. Stored images are not exposed through public media URLs.
- View, download and soft deletion are logged. Employee may only view/download their own records. Manager is limited to their assigned team. Sales has no access.
- Delete requires an in-page confirmation and hides the record; access history remains.
- Upload requires a registered device, a running matching session, current policy acceptance and a permitted company. Supported images: PNG, JPEG and WebP, maximum 20 MB. The server calculates SHA-256 and validates an optional supplied checksum.
- Local storage is implemented. S3 upload/view remains unimplemented and returns an explicit configuration error; setting S3 variables alone does not implement a storage adapter.

## AI Daily Summaries

1. Select a company/employee filter and a summary date.
2. Admin/HR/Manager can select **Generate summaries**. Super Admin must select a company first; Manager generation is limited to their team. Employees have read-only access to their own summaries.
3. Open **View / review** for time totals, top apps/websites, screenshot count and observations.
4. Submit Reviewed, Ignored, Confirmed or Explanation Requested; the last option requires notes. Employee cannot see the review form.
5. Review history is append-only. The first review is permitted without an existing review row. A stale open summary is rejected when its supplied update timestamp no longer matches.

The current implementation is **rule-based**, shared by the API and management command. It does not call an external AI provider even if `AI_API_KEY` is set. It does not report an invented confidence percentage. Observations are advisory and require human review.

Actual work time comes from heartbeats on the requested date in the backend's `TIME_ZONE` (default Asia/Kolkata). This attributes overnight sessions to the correct recorded day. Legacy/sample sessions without any heartbeat use session counters on their start date. Offline uploads use the server's recorded capture time; original offline capture-time attribution is not implemented.

Generating an unchanged summary preserves its review status. New/changed data resets it to Pending and keeps all previous reviews. App/domain classifications come from configured productivity rules; they do not establish work quality or misconduct.

```bat
python manage.py generate_daily_ai_summaries --date 2026-09-26
python manage.py process_pending_ai_jobs
```

## Demo Code Generator and public signup

- Forms start without fake customer details. An active TRIAL plan is required.
- Company, contact, allowed users/devices, trial duration (1–90 days), local expiry date/time, sales-owner and lead-source fields are validated. User/device allowances cannot exceed the configured TRIAL plan capacity.
- Sales may assign only themselves; Company Admin may assign eligible users in their company; Super Admin may choose any eligible owner.
- Generated codes and ownership/audit fields are server-controlled. Terms cannot be edited after creation. Cancel the code and create another if terms need to change. No hard-delete API is exposed.
- Copy the code/signup link, or open `/trial-signup?code=...`. Public validation reveals only signup terms, not internal notes/contact details.
- Signup requires a valid code, company/name, valid unique admin email and a password accepted by Django's password validators.
- Company, subscription, administrator, initial policy, redemption and success log are created in one transaction. A failed write rolls back all of them.
- Single-use codes can enroll one company. Reusable codes stay active until expiry/cancellation and retain all enrolled-company associations in signup logs.
- A cancelled code stops future signup; use **Trial Dashboard → Cancel trial** to cancel an enrolled company.
- Signup returns HTTP 201. The customer can then sign in with their chosen password. Company Admin should publish the organization's monitoring policy before inviting employees.

## Trial Dashboard

- Shows only trial-origin companies in scope, including their converted/cancelled history. Unrelated paid/internal companies are excluded, including for Super Admin.
- Company actions use named selections. Expired trials are recognized from their end date when the dashboard/list is loaded; subscriptions and running sessions are updated accordingly.
- Extend: 1–90 whole days, active/expired trials only. Active trials extend from the current end date; expired trials extend from now.
- Convert: active/expired trials only, a configured active paid plan, Monthly/Annual. Internal/Not Billable is available only to Super Admin and uses billing cycle None.
- Conversion updates the subscription, plan capacities and retention period. A plan below the current user/device count is rejected. Trial dates remain historical and no longer block paid/internal sessions.
- Conversion does not collect a payment. The existing payment integration is still a placeholder.
- Cancellation suspends the company, cancels the subscription and auto-stops running sessions. The agent stops on the next request and shows the company status message. Extend/convert/cancel cannot be repeated on already converted/cancelled companies.
- Company/session/history records are retained. The code's redemption history remains visible after conversion/cancellation.
- `codes_used` counts ever-redeemed codes. `converted_trials` counts converted companies, including reusable-code enrollments. Conversion percentage = converted companies / activated trial companies, not codes generated.

Expiry is enforced when the dashboard/list is loaded and on tracking requests. An offline agent cannot receive server state until it reconnects. No new background scheduler is installed by this patch.

## APIs for testing

Use `Authorization: Token <token>` except on public validation/signup. Import `Postman_Screenshot_AI_Trial.postman_collection.json`; fill the collection variables for your environment.

| Method | API path | Parameters/body |
|---|---|---|
| GET | `/api/screenshots/filter-options/` | Optional `company_id` |
| GET | `/api/screenshots/` | `company_id`, `user_id`, `from_date`, `to_date`, `page` |
| GET | `/api/screenshots/{id}/view/` | Protected image stream |
| GET | `/api/screenshots/{id}/download/` | Protected attachment |
| POST | `/api/screenshots/{id}/soft-delete/` | `{}`; permitted admins/manager only |
| POST | `/api/agent/screenshots/upload/` | Multipart `file`, `session_id`, `device_id`, `app_version`, optional `checksum` |
| GET | `/api/ai-summaries/filter-options/` | Optional `company_id` |
| GET | `/api/ai-summaries/` | Same scope/date/page filters; optional `review_status` |
| POST | `/api/ai-summaries/generate/` | `date`, optional `user_id`; `company_id` required for Super Admin |
| GET | `/api/manager-reviews/` | `ai_summary`, `page` |
| POST | `/api/manager-reviews/` | `ai_summary`, `status`, `remarks`, optional `summary_updated_at` from summary |
| GET | `/api/demo-trial-codes/form-options/` | Eligible owners and active TRIAL plan |
| GET / POST | `/api/demo-trial-codes/` | GET: `status`, `search`, `page`; POST: code terms/contact fields |
| POST | `/api/demo-trial-codes/{id}/cancel/` | `{}`; available/expired codes only |
| POST | `/api/trial/validate-code/` | Public `{ "code": "BOLD-..." }` |
| POST | `/api/trial/signup/` | Public `code`, `company_name`, `admin_name`, `admin_email`, `password`, optional `mobile` |
| GET | `/api/trial/companies/` | `status`, `search`, `page`; **paginated** `{count,next,previous,results}` response |
| GET | `/api/trial/dashboard/` | Scoped metrics |
| POST | `/api/trial/extend/` | `company_id`, `days` |
| POST | `/api/trial/convert/` | `company_id`, `plan_code`, `billing_cycle`, optional `notes` |
| POST | `/api/trial/cancel/` | `company_id` |

## Verification

```bat
cd backend
python manage.py test core.tests --settings=workpulse_project.test_settings --verbosity 1
python manage.py makemigrations --check --dry-run --settings=workpulse_project.test_settings
cd ..\admin-web
npm run build
cd ..\desktop-agent
npm run build:react
node --check electron/main.js
node --check electron/preload.js
```

The test suite covers upload/image validation, protected access and logs, tenant/team/employee scoping, pagination, generation/review/rerun behavior, overnight heartbeat totals, stale reviews, signup rollback/duplicate use, reusable-code scope, expiry/extension/conversion, paid session startup and cancellation gates. API tests use SQLite; PostgreSQL concurrent redemption locking and browser/native Windows runtime should be checked in staging. No live browser smoke test was completed in this workspace because the Chromium download failed.
