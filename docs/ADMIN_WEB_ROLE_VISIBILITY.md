# Admin Web role visibility

The sidebar uses the logged-in user's current `profile.role` from `/api/auth/me/` and hides pages outside the backend's allowed scope. Hiding a button is for clarity; Django permissions and company query scoping remain the access control.

| Page / group | Super Admin | Company Admin | HR/Admin | Sales/Admin | Manager | Employee |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Dashboard | Yes | Yes | Yes | Yes | Yes | Yes |
| Companies, billing, settings | Yes | Yes | No | No | No | No |
| Users | Yes | Yes | Yes | No | Team read | No |
| Departments, policy, productivity rules, ERP connectors, audit logs | Yes | Yes | Yes | No | No | No |
| Devices, agent versions, attendance, activity, screenshots, alerts, AI summaries | Yes | Yes | Yes | No | Scoped read | Own read |
| Trial codes and trial dashboard | Yes | If `can_generate_trials` | No | If `can_generate_trials` | No | No |

Trial Signup remains a public direct page (`/trial-signup`) and is not listed in the authenticated sidebar. Company Admin and Super Admin can manage agent versions; HR/Admin, Manager, and Employee see read-only data there. Employee cannot delete screenshots. Only Super Admin, Company Admin and HR/Admin can close alerts. Sales/Admin can use only trial-sales dashboard and trial-management pages; attendance and activity report APIs return 403 for that role.

## Smoke checks

Sign in separately as Super Admin, Company Admin, HR/Admin, Sales/Admin with and without `can_generate_trials`, Manager, and Employee. Check sidebar, then open each visible page and confirm no permission error. Verify that Employee cannot see Screenshot Delete, Manager cannot see Alert Close, and HR/Admin cannot see Agent Version Save. If a user's role changes, reload to refresh `/api/auth/me/` before checking the menu.

Billing update: only Super Admin can configure subscriptions, manage plans and create/issue/record payments/void invoices. Company Admin sees own-company billing records without write actions. ERP token reveal/rotation and connector changes are available only to Super/Company Admin; HR sees read-only connector/event details with masked token hints.
