# Employee edit update — 8 October 2026

Users can be created with name/email and an optional password. Users / Employees now provides Edit, Save Changes and Cancel Edit. Name, email, role, department, manager and an optional new password can be updated. Employee/company identities and CRM mapping remain stable.

Added employee search, company filtering for Super Admin and pagination so all employees can be reviewed. Department/manager choices are company-scoped. Optional assignments can be cleared. Invalid roles, cross-company assignments, self-management and invalid changes to CRM-linked accounts are rejected.

No designation model or field is added. Existing WorkPulse permission roles are configured manually.

Validation: all 81 backend tests passed using SQLite; migration check reported no changes. React component interaction checks passed for editing, saving, cancellation, nullable fields, optional passwords, basic creation, pagination and role visibility. Vite production build passed. PostgreSQL lock contention and browser visual QA were not performed.

See EMPLOYEE_EDIT_FLOW.md for setup, employee updating and password onboarding. Previously included CRM mapping APIs, migration 0005, CSV import and ERP ingestion remain included. Full CRM event hooks/retry delivery are still separate integration work.

## Changed/added files in this update

- `README.md`
- `admin-web/src/pages/CompanyPage.jsx`
- `admin-web/src/pages/UsersPage.jsx`
- `backend/core/serializers.py`
- `backend/core/test_employee_update.py`
- `backend/core/views.py`
- `docs/EMPLOYEE_EDIT_FLOW.md`
- `docs/ERP_EMPLOYEE_POSTMAN.md`
