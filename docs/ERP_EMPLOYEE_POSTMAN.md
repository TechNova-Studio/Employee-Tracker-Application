# CRM employee mapping and onboarding API — 8 October 2026

This is the current employee ERP contract. WorkPulse resolves `connector + external_id` through `ERPEmployeeMapping`. `external_id` is the chosen stable CRM employee ID as a string, for example `GLUTAPE0001` when CRM's `employee_id` is permanent, unique within the connector and never reassigned. If that code can change or be reused, use the permanent CRM database primary key instead. Use the same chosen value and case in every export, mapping and event; do not switch between codes and database IDs. WorkPulse User IDs, Profile IDs and generated display codes are separate. Email is account data and a duplicate-account check, not a matching key.

## Install

From the updated `backend` folder, with the virtual environment activated:

```bat
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The included migration 0005 restores archived mapping records, preserving their IDs, relationships and timestamps. Do not edit or delete migrations 0001–0004 or use `--fake` to bypass them. An existing installation at 0003 can upgrade directly with the included migration chain; an installation already at 0004 restores its archived mappings. Company prefixes and WorkPulse display codes remain independent of the CRM mapping.

Import `Postman_ERP_Employee_Lifecycle.postman_collection.json`. Set `base_url`, `admin_token`, `connector_id`, `workpulse_employee_id`, `crm_employee_id`, `workpulse_token` and `employee_email` to real staging values. Example IDs in this guide are illustrative.

## Authentication

Admin mapping APIs use a WorkPulse admin login token:

```http
Authorization: Token <admin-login-token>
Content-Type: application/json
```

Super Admin and Company Admin may save mappings. HR/Admin may read mappings. Company Admin and HR/Admin access only their own company. Employee, Manager and Sales/Admin cannot access mapping APIs. The connector secret does not authorize these admin operations.

ERP ingestion uses the connector secret:

```http
X-WORKPULSE-TOKEN: <erp-connector-token>
Content-Type: application/json
```

Configure the connector to allow `erp_user_created`, `erp_user_updated`, `erp_user_active` and `erp_user_inactive`. The token identifies the company; any supplied company ID must match it.

## A. Existing WorkPulse employee: list, select, link

Find an existing connector through `GET /api/erp-connectors/`. Employee selection:

```http
GET /api/erp/employee-mappings/form-options/?connector_id=3&search=Rahul
```

The response is paginated with `count`, `next`, `previous` and `results`. Each employee row exposes `workpulse_employee_id` (Django User primary key), `workpulse_profile_id`, name, email, display code, active status and any linked CRM ID. Both active and inactive company employees are available; Super Admin is excluded.

Save the reviewed relationship:

```http
POST /api/erp/employee-mappings/
```

```json
{"connector_id":3,"external_id":"21","workpulse_employee_id":85}
```

HTTP 201 creates the link. Repeating the same link returns HTTP 200 and the same mapping ID. An already-linked source ID or target employee cannot be silently reassigned; conflicting links return HTTP 409. Invalid target employees return 400; inaccessible connectors return 404.

Review links:

```http
GET /api/erp/employee-mappings/?connector_id=3&search=21
GET /api/erp/employee-mappings/<mapping_id>/
```

List responses are paginated. Super Admin can filter with `company_id`; another company's filter is forbidden to company-scoped admins. Mapping update/delete is intentionally unavailable: remapping is a separate reviewed operation.

## B. Employee absent from WorkPulse: create and map together

Use the existing employee creation event API; no prior manual WorkPulse employee creation is required:

```http
POST /api/erp/ingest/
```

```json
{
  "event_type":"erp_user_created",
  "external_id":"21",
  "payload":{"email":"new.employee@example.com","first_name":"New","last_name":"Employee","is_active":true}
}
```

A successful response is HTTP 200 with `status: processed`, `user_id`, `workpulse_employee_id` and `external_id`. Employee and mapping are saved in one transaction. Repeating this create request resolves the existing mapping and cannot create another employee. ERP-created employees receive the EMPLOYEE role and an unusable password; password setup/SSO remains a separate onboarding task.

If an account already uses that email and no source mapping exists, the API returns HTTP 409 with `code: mapping_required`. Review and explicitly link the existing employee using flow A. It does not automatically link by email or name.

An optional `payload.employee_id` is a WorkPulse display code only. It never determines which employee is updated. A company prefix may generate a display code when one is not supplied.

## C. Test inactive, active and profile update

Send these requests individually against the same mapped staging employee:

```json
{"event_type":"erp_user_inactive","external_id":"21","payload":{"is_active":false}}
```

```json
{"event_type":"erp_user_active","external_id":"21","payload":{"is_active":true}}
```

```json
{"event_type":"erp_user_updated","external_id":"21","payload":{"email":"updated.employee@example.com","first_name":"Updated","mobile":"1234567890"}}
```

They must resolve the same WorkPulse User ID. Inactivation also revokes login tokens and stops running sessions. Roles are retained; Super Admin and cross-company mappings cannot be processed. Missing mapping returns HTTP 409 `mapping_required`, without creating a user. Invalid/missing external IDs return 400; invalid/disabled connector token returns 403. Failed employee events retain an error and remain unprocessed.

## D. Bulk mapping API

Validate reviewed existing employee links:

```http
POST /api/erp/employee-mappings/bulk/
```

```json
{
  "connector_id":3,
  "dry_run":true,
  "rows":[
    {"external_id":"21","workpulse_employee_id":85},
    {"external_id":"34","workpulse_employee_id":92}
  ]
}
```

Set `dry_run` to false to save. Maximum 1000 rows per API batch. Dry runs save neither mappings nor audit rows. The entire batch rolls back on invalid IDs, company mismatches, duplicate rows or conflicting links. Response includes `created`, `unchanged`, `dry_run` and reviewed mappings. Reimporting identical relationships is safe.

## E. CSV import command

The CSV must contain actual, reviewed IDs:

```csv
crm_employee_id,workpulse_employee_id
21,85
34,92
```

```bat
python manage.py import_erp_mappings --connector-id 3 --file employee_mapping.csv --dry-run
python manage.py import_erp_mappings --connector-id 3 --file employee_mapping.csv
```

The command is included in this backend. It accepts up to 10000 rows / 5 MiB and validates before committing the batch. It links existing WorkPulse Users; it does not create them.

## F. Create and map employees from an Excel/CSV upload

`POST /api/erp/employees/import/` accepts Postman **Body → form-data**, with `file` of type **File** and `dry_run` of type **Text** (`true` validates, `false` saves). Use **No Auth** and the header `X-WORKPULSE-TOKEN`; let Postman generate the multipart Content-Type/boundary. The connector must allow `erp_user_created`. Company is determined by its token.

Required file columns are `employee_id,first_name,email,is_active`; optional columns are `last_name,mobile`. `name` may replace `first_name` for a full-name column. Use a single worksheet in `.xlsx`, or UTF-8 comma-separated `.csv`. Max 1000 employees / 5 MiB. Include active status in every row; a blank or omitted status is rejected. File `employee_id` becomes ERP `external_id`, and does not overwrite the WorkPulse display code.

Validation and DB conflicts return sheet row numbers and save no part of the file. Dry-run executes the same checks and rolls back all writes. Successful save returns counts and WorkPulse User IDs; repeating a file updates mapped users instead of duplicating them. Existing unmapped email accounts require explicit admin linking. See [complete file-import guide](EMPLOYEE_FILE_IMPORT.md) and `employee_import.example.csv`. Requests 12 and 13 in the Postman collection support file preview and save.

## Configure employee details later

After onboarding, open Users / Employees and use **Edit** to set role, department, manager and an optional login password. Name/email can also be edited. CRM mappings remain linked to the same WorkPulse User ID. Manual name/email creation is available with an optional password; manual creation needs a separate CRM link. See `EMPLOYEE_EDIT_FLOW.md`. Designation is not added.

## CRM integration still required

The full CRM backend is not included in this project. Its backend developer must use the same stable source identity chosen for onboarding, add event emission after successful CRM saves and configure the connector endpoint/token. For a permanent CRM `employee_id` such as `GLUTAPE0001`, use `external_id = str(crm_employee.employee_id)`; if a database primary key was chosen, keep using that instead. Inspect the actual CRM model before wiring the sender. No new external-ID column is needed in CRM.

The earlier email-based CRM sender must be updated before use; it omits the now-required external ID. Durable CRM delivery retries, event ordering, department/manager/designation sync, password onboarding and a frontend mapping page are separate work. The mapping APIs are ready for an admin frontend or individual Postman requests.

## Verification

Run backend tests with the existing SQLite test settings:

```bat
python manage.py test core --settings=workpulse_project.test_settings
python manage.py makemigrations --check --dry-run --settings=workpulse_project.test_settings
```

Tests cover tenant permissions, differing source/target IDs, duplicate and conflicting links, atomic onboarding/import, token/session revocation, preserved roles and upgrade/restoration of archived mappings. SQLite tests do not verify PostgreSQL lock contention or a live CRM deployment.
