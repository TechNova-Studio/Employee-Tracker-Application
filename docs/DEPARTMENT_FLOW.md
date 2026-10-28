# Department flow

Admin Web → Departments is available to Super Admin, Company Admin and HR/Admin. Super Admin selects a company; the other two roles see only their assigned company. The list is filtered to the selected company.

1. Select a company and create a department. Its name must be unique within that company, ignoring case. The same name can be used in another company.
2. Use Rename to change a department's name. A department cannot be moved to another company.
3. Use Deactivate to hide it from the department dropdown when manually adding employees; existing employee assignments remain. Activate makes it available again. The API refuses hard deletion.

The relevant APIs are `GET /api/departments/company-options/`, `GET /api/departments/?company_id=<id>`, `POST /api/departments/` and `PATCH /api/departments/<id>/`. Super Admin must send `company` on create. Company Admin and HR/Admin have their company assigned by the backend and may omit that field.

Example create body for Super Admin:

```json
{"company": 1, "name": "IT", "is_active": true}
```

Run the backend migration from the earlier ERP employee update if it has not already been applied. This Department fix needs no new migration.
