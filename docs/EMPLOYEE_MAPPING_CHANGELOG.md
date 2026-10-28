# Employee mapping API changes — 8 October 2026

Implemented: admin create/list/detail mapping endpoints, paginated employee selection, atomic bulk validation/save, CSV mapping import, connector-scoped lifecycle resolution, employee creation + mapping in one transaction, and migration restoration of previously archived links.

Identity: `external_id` is the stable CRM employee/user primary key as a string. `workpulse_employee_id` is the Django User ID returned by `/api/users/`; it is not the nested Profile ID or display employee code. Source and target IDs may differ.

Validation: 71 backend tests passed using the project's SQLite test settings. Django system checks passed and `makemigrations --check --dry-run` reported no changes. All bundled Postman collection files parse successfully. Migration tests cover upgrades from 0003 and archived links from 0004, including original IDs/timestamps.

Production limits: this is an updated source package, not a deployed API. PostgreSQL locking has not been load-tested. Full CRM source is not part of this package, so actual CRM hooks, ID exports and durable delivery retries still need integration. New ERP accounts need password setup/SSO. No frontend mapping page was added; Postman/admin API clients can use the endpoints.

Installation and payloads: see `ERP_EMPLOYEE_POSTMAN.md` and `Postman_ERP_Employee_Lifecycle.postman_collection.json`. Run the included migrations before starting the updated backend.

## Changed and added files

- `README.md`
- `backend/core/erp_employee_mapping.py`
- `backend/core/erp_employee_sync.py`
- `backend/core/erp_mapping_api.py`
- `backend/core/management/commands/import_erp_mappings.py`
- `backend/core/migrations/0005_explicit_erp_employee_mapping.py`
- `backend/core/models.py`
- `backend/core/test_employee_identity.py`
- `backend/core/test_erp_mapping.py`
- `backend/core/test_erp_mapping_migration.py`
- `backend/core/test_identity_migration.py`
- `backend/core/tests.py`
- `backend/core/urls.py`
- `backend/core/views.py`
- `docs/BILLING_ERP_FLOW.md`
- `docs/ERP_EMPLOYEE_POSTMAN.md`
- `docs/Postman_Billing_ERP_Settings.postman_collection.json`
- `docs/Postman_ERP_Employee_Lifecycle.postman_collection.json`
- `docs/employee_mapping.example.csv`
