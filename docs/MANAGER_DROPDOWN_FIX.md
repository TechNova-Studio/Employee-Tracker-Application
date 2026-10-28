# Manager dropdown refresh — 8 October 2026

Users / Employees now explicitly reloads department and manager options after every successful employee create or update. This includes creating a Manager while already using the create form. The page's Refresh button also reloads dropdown options, so role changes made elsewhere can be reflected without reloading the entire page.

Company form-options requests bypass browser cache. Existing request cancellation prevents a previous company or edit request from replacing the current options.

The backend role update and form-options query already support promoted managers; no production backend change or database migration is needed for this fix. The backend tests now verify the complete promotion and assignment flow.

## Install

1. Copy `admin-web/src/pages/UsersPage.jsx` from this ZIP into the existing project.
2. Restart the admin web development server with `npm run dev`, or run `npm run build` and serve the new build if using the production frontend.
3. Refresh the browser once to load the updated frontend.

## Verify

1. Open Users / Employees and edit an active employee in Glutape.
2. Set Role to MANAGER and save.
3. In the returned Create User form, select that employee in Manager (optional).
4. Create the next employee and confirm the saved manager assignment.
5. Create another user with Role MANAGER and confirm the new manager appears in the following create form.
6. If roles were changed elsewhere, click Refresh to reload the manager options.

New manager assignments require both User.is_active and Profile.is_active_employee to be true. Managers remain scoped to the selected company, and an employee cannot select themselves while editing. Existing inactive assignments may still appear as a current value on their existing employee's edit form.

## Validation

- All 101 backend tests passed with SQLite test settings.
- Four React component checks passed: promote and assign the next employee, Refresh after an external role change, create a new manager, and Super Admin company switching. Demotion, inactive exclusion and self-management are also checked within these flows.
- Existing employee UI checks passed for editing, saving, cancellation, nullable assignments, passwords, creation, pagination and role visibility.
- Vite production build passed.
- Browser visual inspection and PostgreSQL concurrency load tests were not performed.

## Changed files

- `admin-web/src/pages/UsersPage.jsx`
- `backend/core/test_employee_update.py` (regression tests)
- `README.md`
- `docs/EMPLOYEE_EDIT_FLOW.md`
- `docs/MANAGER_DROPDOWN_FIX.md`
