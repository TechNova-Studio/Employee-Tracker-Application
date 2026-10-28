# Create basic employees, then update them in WorkPulse

## Initial creation

Create employees through the existing ERP `erp_user_created` request with their CRM primary key in `external_id`, email and name. The connector token identifies Glutape. The employee and CRM mapping are saved together. Department, manager and designation are not required for this onboarding flow.

You can also create a WorkPulse user manually in **Users / Employees** with a selected company, email and name. Role defaults to EMPLOYEE. Password, employee display code, department and manager are optional. A manual creation without a password creates an account with no usable password; it does not receive a shared default password. Manual creation requires a separate reviewed CRM mapping through the mapping API.

## Update employees after creation

1. Open **Users / Employees**.
2. Super Admin may choose Glutape in **Company filter**. Company Admin and HR/Admin see their own company employees.
3. Find an employee using the search field or Previous/Next pagination.
4. Click **Edit** on the employee row.
5. Update first name, last name, email, role, department and manager.
6. If login needs to be enabled, enter **New password (optional)**. Leaving it blank keeps the current password unchanged.
7. Click **Save Changes**. **Cancel Edit** discards unsaved edits.

After every successful create or update, the department and manager dropdowns reload from the selected company's current form-options API. An active employee promoted to **MANAGER** is available when creating the next employee. Creating a new manager also refreshes the next create form. **Refresh** reloads both the employee table and form options, including changes made elsewhere.

Choose **No department** / **No manager** to clear those assignments. Existing inactive department/manager assignments remain available as current values; new assignments must use active records from the employee's company. An employee cannot manage themselves.

Company and employee display code are read-only in the edit form. The WorkPulse User ID and the CRM mapping are preserved. Department and manager dropdowns are limited to the employee's company. A linked employee cannot be moved to another company or promoted to a platform Super Admin through the update API.

Designation is not added. Existing WorkPulse roles control application permissions. ERP metadata updates preserve the manually configured role, department and manager. A later CRM name/email update can replace the corresponding basic details.

## Update API

Use the authorized WorkPulse admin login token:

```http
PATCH /api/users/<workpulse_user_id>/
Authorization: Token <admin-login-token>
Content-Type: application/json
```

```json
{
  "first_name": "Rahul",
  "last_name": "Sharma",
  "email": "rahul@example.com",
  "role": "EMPLOYEE",
  "department": null,
  "manager": null
}
```

Use actual same-company department and manager IDs when assigning them. Omit `password` to leave it unchanged; provide a nonblank password to set it. This endpoint takes a WorkPulse User ID, not the CRM external ID or nested Profile ID.

Super Admin, Company Admin and HR/Admin can update permitted employees. Employees and Managers have read access to their existing scoped records and do not receive Edit controls. Company-scoped admins cannot update Super Admin accounts or other companies' users. An account's own role change refreshes its admin session UI so its available actions match the new role.

## Verification

Latest verification: 101 backend tests passed using SQLite test settings, including promotion → manager options → next employee assignment, demotion and inactive-manager exclusion. React component interaction checks cover these manager refresh flows and the existing editing, creation, pagination and role visibility flows. The admin web production build passed. Browser visual inspection and PostgreSQL concurrency load tests were not performed.

No new migration is required for employee editing. An installation that has not applied the earlier mapping API update still needs the included migrations:

```bat
python manage.py migrate
```

Build/run the updated admin web using the existing project commands. CRM event hooks and durable delivery retries remain pending in the separate CRM backend.
