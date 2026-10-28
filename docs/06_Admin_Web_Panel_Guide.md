# 06. Admin Web Panel Guide

## Folder

```text
bold-workpulse/admin-web/
```

## Start commands

From project root:

```bat
scripts\setup_admin_web_windows.bat
scripts\run_admin_web_windows.bat
```

Admin web URL:

```text
http://localhost:5174
```

## Login

```text
superadmin@boldworkpulse.local
Demo@12345
```

## Page structure

The final admin web uses page-wise files:

- `DashboardPage.jsx`
- `CompanyPage.jsx`
- `UsersPage.jsx`
- `DepartmentsPage.jsx`
- `DevicesPage.jsx`
- `PolicyPage.jsx`
- `AgentVersionPage.jsx`
- `AttendancePage.jsx`
- `ActivityPage.jsx`
- `ScreenshotPage.jsx`
- `AISummaryPage.jsx`
- `AlertsPage.jsx`
- `TrialCodesPage.jsx`
- `TrialDashboardPage.jsx`
- `BillingPage.jsx`
- `ERPConnectorPage.jsx`
- `AuditLogPage.jsx`
- `SettingsPage.jsx`

## What to test first

1. Dashboard opens.
2. Users page lists seeded users.
3. Policy page shows policy versions and acceptances.
4. Agent Version page shows version rule.
5. Screenshot page shows protected view/download buttons after desktop upload.
6. Trial Code page generates a code.
7. Trial Signup page creates a trial company.
8. Trial Dashboard extends/converts only scoped trial companies.

## Expected behavior

- Screens use FINAL_GATE backend endpoints only.
- Screens do not need raw JSON for daily testing.
- Backend still enforces all permissions even if UI button is visible.

## Common errors

| Error | Fix |
|---|---|
| API error / failed to fetch | Confirm backend is running at `http://localhost:8000` |
| 403 forbidden | Login role does not have permission for that page/action |
| Empty screenshots | Start desktop session and wait for screenshot upload |
| Trial action not allowed | Use allowed Sales/Admin scope or Super Admin |

## Do not change these rules without management approval

- Do not point UI to Kimi backend.
- Do not bypass protected screenshot endpoint.
- Do not add a UI library that complicates setup.
