# Employee file-import update — 8 October 2026

Added `POST /api/erp/employees/import/` for multipart `.xlsx` / `.csv` uploads authenticated by the existing ERP connector secret. A single upload can create missing employees and their CRM mappings together; the existing single-event ingest endpoint remains available for lifecycle events.

Changed files:

- `backend/core/erp_employee_import.py`: file parsing, required status/name/email/source-ID validation, row limits, duplicate checks and atomic onboarding/preview using the existing ERP lifecycle service.
- `backend/core/erp_employee_import_api.py`: connector authentication, multipart form-data API and structured errors.
- `backend/core/urls.py`: file-import route.
- `backend/requirements.txt`: openpyxl 3.1.5 and defusedxml 0.7.1.
- `backend/core/test_erp_employee_import.py`: 18 integration tests.
- `backend/core/erp_employee_mapping.py`, `backend/core/erp_mapping_api.py`, `backend/core/models.py`: source identity wording updated to allow a verified permanent CRM employee ID, including string codes. No schema change.
- `README.md`, `docs/ERP_EMPLOYEE_POSTMAN.md`, `docs/EMPLOYEE_FILE_IMPORT.md`: installation, spreadsheet contract and Postman steps.
- `docs/employee_import.example.csv`: illustrative input format.
- `docs/Postman_ERP_Employee_Lifecycle.postman_collection.json`: preview/save multipart requests 12 and 13.
- This changelog.

Validation: all 99 backend tests pass with the included SQLite test settings; system check reports no issues; `makemigrations --check --dry-run` reports no changes. The XLSX upload test imports 148 synthetic users with exactly 27 active and 121 inactive, and confirms mappings/events. CSV replay, dry-run/error rollback, company isolation and authorization checks also pass. No live employee data was uploaded or created, and PostgreSQL concurrency was not tested in this environment.

Deployment: install updated backend requirements, run existing migrations (including mapping migration 0005), restart the backend, then use the Postman preview request on your own file before save. No new migration is introduced by this file-import change. Future automatic CRM hooks/retries still need the separate CRM backend integration.
