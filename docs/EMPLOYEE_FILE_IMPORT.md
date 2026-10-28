# Excel/CSV employee creation and mapping

Use this API to onboard many CRM employees in one Postman request. You do not need to create users one at a time or upload the spreadsheet into chat.

## Install and start

Activate the existing backend virtual environment, then run from `backend`:

```bat
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The file reader adds openpyxl 3.1.5 and defusedxml 0.7.1. This update adds no database migration; the previously supplied mapping migration 0005 must already be applied. Keep your existing environment configuration and database.

## Prepare the sheet

Use one worksheet, with headers in row 1 and one employee per subsequent row.

| Header | Required | Value |
|---|---|---|
| employee_id | Yes | Stable CRM employee ID, for example GLUTAPE0001 |
| first_name | Yes | Employee name; a full name is accepted |
| last_name | No | Surname; may be blank |
| email | Yes | Valid, unique employee email |
| is_active | Yes | true / false; Excel booleans, 1 / 0 and active / inactive also accepted |
| mobile | No | Text; keep leading zeroes and country prefix |

If your header is `name`, use it instead of `first_name`; do not include both. Header names are trimmed and case-insensitive. Unknown/duplicate headers are rejected. Format employee IDs and mobile numbers as Text before exporting. IDs and emails cannot repeat within a file. Source IDs retain their exact case. Names cannot be blank; formulas and Excel error cells are rejected. Paste values before uploading.

For Glutape's stated 148 employees, include all 148 rows with exactly 27 active and 121 inactive. These counts are not hard-coded in the API; verify them against the actual CRM export. No designation, role, department, manager or password columns are required or accepted.

`employee_import.example.csv` contains illustrative rows, not your CRM data. Upload `.xlsx` or a UTF-8 comma-separated `.csv`. Old `.xls` files must be saved as `.xlsx`. Maximum 1000 employee rows, 5 MiB compressed upload, 20 MiB expanded workbook and 10000 scanned worksheet rows. Additional worksheets are rejected so the imported sheet is unambiguous.

The file's `employee_id` becomes top-level ERP `external_id`. CRM does not need an `external_id` database column. A code like `GLUTAPE0001` is suitable only if permanent, unique within the connector and never reassigned. All future CRM events must send this same value. WorkPulse display employee codes are generated independently by the existing company prefix setting; file import does not overwrite them.

## Postman preview

1. Create a POST request: `http://127.0.0.1:8000/api/erp/employees/import/`, replacing the origin for a hosted backend.
2. Set Authorization to **No Auth**.
3. Add header `X-WORKPULSE-TOKEN` with the existing Glutape connector token.
4. The connector must be active and allow `erp_user_created`.
5. Choose **Body → form-data**:

| Key | Type | Value |
|---|---|---|
| file | File | Select your Excel/CSV file |
| dry_run | Text | true |

Do not manually set Content-Type to application/json or multipart/form-data; let Postman set the multipart boundary. Do not put the file under raw JSON. No employee/user/company ID form field is required. Optional `company_id`, if supplied, must equal the company identified by the token. Admin login tokens do not replace the connector token for this endpoint.

HTTP 200 preview example:

```json
{
  "status": "validated",
  "dry_run": true,
  "company_id": 7,
  "total": 148,
  "created": 148,
  "updated": 0,
  "active": 27,
  "inactive": 121,
  "employees": []
}
```

The example counts/company ID are illustrative. Actual responses include one entry per employee under `employees`; new users do not receive a persistent WorkPulse ID during preview. Preview checks syntax, existing email/mapping conflicts and company boundaries through the same processing used for save, then rolls back users, mappings, ERP events, audit logs, display-code counters, status changes, token deletion and session changes. A successful preview does not reserve IDs or guarantee the database remains unchanged before save; save validates again.

## Save

With the same file and header, change **dry_run** to **false** and send. The whole file saves in one transaction. The response has `status: processed`, counts and per-row `workpulse_employee_id` and `event_id`. Employees and connector-scoped mappings are saved together, and each saved lifecycle event is marked processed.

New employees receive EMPLOYEE role and an unusable password. Use Users / Employees → Edit later to set role, department, manager and a login password. Existing mapped users retain role, department, manager and password. Supplied names, email, optional mobile and active status are synchronized. Inactive employees cannot log in; existing login tokens are removed and running sessions stop through the current ERP lifecycle service.

An identical reimport does not create duplicate users or mappings. It returns those users as `updated` and records a new processed ERP event per row. Reimporting an older sheet reapplies its profile and active/inactive values; use a current CRM export.

## Status sync and blank Employee ID

Department, designation and manager are optional and do not control employee lifecycle processing. A blank Employee ID in Users / Employees is an optional WorkPulse display code. When the company has no employee ID prefix and no display code was supplied, it stays blank. The CRM ID from the file is still stored separately as the mapping's `external_id`; a blank display code does not prevent status updates.

Users / Employees now displays the saved CRM mapping for company administrators, HR administrators and Super Admin. When the stored WorkPulse display code is blank and mappings agree on one source ID, the `employee_code` table cell shows that CRM ID. An assigned WorkPulse display code takes priority. If multiple connectors use different source IDs, the table shows `Multiple CRM IDs` and lists the actual connector/ID pairs under `crm_mapping`; it does not choose a source arbitrarily. `Not mapped` means the API returned no valid mapping for that employee. `Unavailable` means the backend did not provide mapping data yet. A disabled connector is shown alongside its saved mapping.

The user API includes read-only `erp_mappings` entries with `connector_id`, `connector_name`, `connector_active` and `external_id`. These contain no connector tokens. Employee search accepts saved CRM IDs and WorkPulse display codes as well as names and emails. Company scope is enforced for display and CRM-ID search; non-admin roles do not receive CRM mapping details. This change reads existing mappings and does not generate IDs or create links by email. Existing imported employees appear immediately after deploying both backend and frontend and refreshing; no database migration or reimport is required merely to show their mappings.

If imported status values were wrong, export current CRM values and reimport with the same employee IDs and connector. Preview with `dry_run=true`, review the counts, then save with `dry_run=false`. Existing mapped employees are updated, including active status. A preview response (`status: validated`) saves no employees, mappings or status changes.

Import creates mappings; the CRM backend must also deliver events after employee changes. For an employee imported as `GLUTAPE0001`, send the following to `POST /api/erp/ingest/` using the same `X-WORKPULSE-TOKEN` as the import. Replace the sample ID with the actual mapped CRM ID:

```json
{
  "event_type": "erp_user_inactive",
  "external_id": "GLUTAPE0001",
  "payload": { "is_active": false }
}
```

Do not switch to a numeric CRM database ID such as `21` after importing employee codes. Every event must use the same chosen source identity. `payload.employee_id` is an optional display code, so putting the source ID only there does not satisfy the required top-level `external_id`.

Inspect the actual sender's HTTP response and ERP Connector Settings → ERP events:

| Observation | Next check |
|---|---|
| HTTP 200, `status: processed`, `action: deactivated`, `is_active: false` | Refresh the employee list for the same company; confirm the returned `workpulse_employee_id` is the intended user. |
| HTTP 409, `code: mapping_required` | Check the exact source ID and connector against the saved mapping. |
| HTTP 400 | Check the required external ID, allowed event type, JSON booleans and company fields in the response detail. |
| HTTP 403 | Check the current connector token and whether the connector is active. |
| No event in the list | Check sender delivery and its HTTP response; token/payload rejection can occur before an event is recorded. |

An administrator can inspect the mapping with `GET /api/erp/employee-mappings/?connector_id=<actual connector ID>&search=<actual CRM employee ID>`, using their login `Authorization: Token <admin login token>`. The connector ID is not the company ID. This read endpoint uses admin login authentication, while ingest uses the connector token.

## Errors and retry

### Vercel 504 FUNCTION_INVOCATION_TIMEOUT

This means Vercel ended the HTTP invocation at its time limit; it is not a
successful import or a spreadsheet validation response. The previous deployment
config explicitly capped Django at 60 seconds. The bundled `backend/vercel.json`
now sets `workpulse_project/wsgi.py` to 300 seconds and selects `pdx1` (Portland),
near the current Render database in Oregon. Keeping the function near the
database reduces latency for the per-employee database operations. The screenshot
alone does not prove which database operation took too long.

For the existing deployment, keep Vercel Root Directory set to `backend` and
place this config beside `manage.py`. Enable Fluid compute if it is disabled;
300 seconds is supported on Hobby with Fluid compute. Deploy the updated config,
then confirm the Django function's duration is 300 seconds and region is `pdx1`
in the new deployment. If deploying from the repository root instead, the config
belongs there and the function key must be `backend/workpulse_project/wsgi.py`.

Retry the same file with `dry_run=true`, keeping the connector header and
multipart form-data. Send `dry_run=false` only after a successful validation.
Repeated source IDs on the same connector resolve the existing employee mapping.
After a timed-out save, check Users / Employees before retrying: an HTTP timeout
alone does not tell you whether the transaction committed before the response.

For the initial import, you can also run the existing backend locally against
the same live Render database and use the same API through Postman:

```bat
python manage.py runserver
```

```text
POST http://127.0.0.1:8000/api/erp/employees/import/
X-WORKPULSE-TOKEN: YOUR_GLUTAPE_CONNECTOR_TOKEN
```

Use the same file/dry_run form-data fields. This avoids Vercel's HTTP invocation
limit; the created employees and mappings are stored in the configured shared
Render database and appear in the deployed app. Verify the local database
hostname before sending a saving request. If hosted imports still time out,
inspect Vercel runtime logs and database connection/query durations rather than
assuming the file is invalid. This configuration is not a background import
queue and has not been tested against the live deployment.

Official references: [function duration](https://vercel.com/docs/functions/configuring-functions/duration),
[Django entrypoint configuration](https://vercel.com/docs/frameworks/full-stack/django),
and [function regions](https://vercel.com/docs/functions/configuring-functions/region).

Validation and processing failures reported by the import API roll back the whole
file. A gateway timeout must be handled as described above. Validation responses
include actual worksheet/CSV row numbers (header is row 1).

| HTTP | Meaning | Action |
|---|---|---|
| 400 | Invalid file, columns, row values, missing status or duplicates | Fix the reported rows and preview again |
| 403 | Invalid/inactive token or creation event disabled | Check the intended company connector |
| 409 | Existing email without mapping, conflicting email or invalid mapping | Review and explicitly link the existing user through the admin mapping API; then retry the file |
| 415 | Wrong request content type | Use multipart form-data with a File field |
| 500 | Unexpected processing failure; batch rolled back | Check server logs before retrying |

No automatic matching by name/email is performed. A globally existing account with an unlinked email is reported as `mapping_required` even if outside this connector's company. Protected Super Admin and cross-company mappings cannot be imported. Missing IDs are not invented. A token rotation/connector disable during file validation is rechecked under the company/connector lock before saving.

CSV mapping commands and `/api/erp/employee-mappings/bulk/` link existing users only. This file-import endpoint performs employee onboarding. Single employee events still use `/api/erp/ingest/` with JSON. Automatic future CRM delivery hooks/retries remain work in the separate CRM project; importing a sheet does not install them.

## Verification

```bat
python manage.py test core --settings=workpulse_project.test_settings
python manage.py makemigrations --check --dry-run --settings=workpulse_project.test_settings
```

Automated coverage includes real multipart CSV/XLSX uploads, 148 users with 27/121 status counts, replay, dry-run and error rollback, protected mappings, company isolation, token/event checks, row validation and malformed files. SQLite tests do not verify PostgreSQL concurrency or import actual production employee data.

Implementation references: [DRF multipart parser](https://www.django-rest-framework.org/api-guide/parsers/#multipartparser), [openpyxl workbook reader](https://openpyxl.pages.heptapod.net/openpyxl/api/openpyxl.reader.excel.html).
