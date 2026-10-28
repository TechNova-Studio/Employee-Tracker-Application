# 11. QA Test Cases

Run these after the 8-hour go-live checklist. Record pass/fail with screenshot.

## A. Setup tests

1. ZIP extracts to one `bold-workpulse/` folder.
2. `.env.example` copies to `.env`.
3. Backend setup runs without Docker/Redis/Celery.
4. `python manage.py migrate` runs using included initial migration.
5. `python manage.py seed_demo_data` creates users, plans, policy, agent version, trial codes and sample records.
6. Health check returns OK.
7. Admin web starts on `http://localhost:5174`.
8. Desktop agent starts through Electron.

## B. Login and policy tests

1. Super Admin can login to admin web.
2. Employee can login to desktop agent.
3. Latest policy appears before first session if not accepted.
4. Accept policy creates `PolicyAcceptance` record.
5. Session start succeeds only after latest active policy is accepted.
6. Create a new active policy version; employee session start must be blocked until re-accepted.
7. Decline policy; login/session must be blocked with `POLICY_DECLINED`.
8. Declined employee cannot self-reactivate by calling policy accept with old token.
9. HR/Admin reactivates user; employee sees policy again.
10. Accepting an old `policy_id` after a new version was published returns 409; the agent shows the new text.
11. Restart with a cached login; a new policy must appear before the next session.

## C. Force update tests

1. Version check returns latest and minimum supported version.
2. Set minimum supported version above desktop app version.
3. Device register must return blocked/outdated.
4. Session start must return blocked/outdated.
5. Heartbeat must return blocked/outdated.
6. Activity batch upload must return blocked/outdated.
7. Screenshot upload must return blocked/outdated.
8. Outdated-agent alert is created.

## D. Role and tenant isolation tests

| Role          | Required result                                                                     |
| ------------- | ----------------------------------------------------------------------------------- |
| Super Admin   | Can see all companies, users, sessions, alerts, policies, audit logs and ERP events |
| Company Admin | Can view/update own company basic settings only                                     |
| Company Admin | Cannot create/delete another company manually                                       |
| Company Admin | Cannot see other company users/sessions/screenshots/audit logs                      |
| HR/Admin      | Sees own company HR/policy/activity data only                                       |
| Sales/Admin   | Sees own generated/assigned trial-sales dashboard only                              |
| Sales/Admin   | Cannot extend/convert/cancel a random company ID                                    |
| Sales/Admin   | Cannot convert trial to `INTERNAL` / Not Billable                                   |
| Manager       | Sees assigned team summary only                                                     |
| Manager       | Cannot see non-team employee data                                                   |
| Employee      | Sees only own records                                                               |
| Employee      | Cannot see company-wide sensitive data                                              |
| Employee      | Cannot see ERP event payloads                                                       |
| Employee      | Cannot see screenshots of others                                                    |
| Employee      | Cannot manage plans, companies, billing or audit logs                               |

## E. CompanyPlan permission tests

1. Super Admin can create/update/delete plans.
2. Company Admin can read active plans only.
3. HR/Admin can read active plans only.
4. Sales/Admin can read active plans only.
5. Manager cannot manage plans.
6. Employee cannot manage plans.

## F. Screenshot security tests

1. Desktop uploads screenshot in local mode.
2. Admin sees screenshot metadata.
3. Serializer does not expose raw `file` URL.
4. View button uses protected endpoint.
5. Download button uses protected endpoint.
6. View creates `ScreenshotAccessLog`.
7. Download creates `ScreenshotAccessLog`.
8. Delete/soft-delete creates `ScreenshotAccessLog`.
9. Standard DELETE also soft-deletes and logs; it must not silently hard-delete.
10. Manager can access only team screenshots.
11. Employee can access only own screenshots.

## G. Activity and attendance tests

1. Start session from desktop agent.
2. Confirm heartbeat appears.
3. Confirm active/idle seconds update.
4. Confirm app/window activity appears.
5. Confirm mouse/keyboard counts are counts only, not key content.
6. Confirm no clipboard/webcam/microphone access exists.
7. Idle detection uses system idle time, not only Electron window activity.
8. Filter sessions and activity by company/employee/date, use pagination beyond 50 rows and verify Manager/Employee scope.
9. Creating a new active policy or declining it auto-stops the running session; later uploads report the policy gate.

## H. AI summary tests

1. Keep `AI_PROVIDER=mock`.
2. Run `python manage.py generate_daily_ai_summaries`.
3. AI summary record appears.
4. Manager review page/list is scoped.
5. AI output is advisory only.

## I. Trial/demo tests

1. Sales/Admin generates 5-day code.
2. Sales/Admin generates 7-day code.
3. Sales/Admin generates 10-day code.
4. Invalid code is rejected.
5. Expired code is rejected.
6. Cancelled code is rejected.
7. Valid code creates trial company.
8. Trial company gets Trial plan and expiry date.
9. Trial company is isolated from other companies.
10. Trial expiry blocks/limits access as configured.
11. Super Admin can extend trial.
12. Sales/Admin can extend only scoped trial.
13. Super Admin can convert trial to paid.
14. Sales/Admin can convert only scoped trial.
15. Conversion preserves users, devices, activity logs, screenshots, policy acceptances and AI summaries.
16. Trial extension, cancellation and conversion create audit logs.

## J. ERP connector tests

1. Company Admin creates own connector.
2. Public ingestion rejects invalid token.
3. Public ingestion accepts valid token.
4. ERP event is stored against connector company.
5. Employee cannot read ERP event payloads.
6. Company Admin/HR/Admin sees own-company events only.

## K. Billing tests

1. Glutape is Internal / Not Billable.
2. Trial company has Trial subscription.
3. Converted company has selected paid plan.
4. Employee cannot access billing data.

## Do not change these rules without management approval

- Do not skip permission tests.
- Do not expose direct screenshot media URLs.
- Do not add Docker/Redis/Celery/Kubernetes.
- Do not replace backend/desktop logic with older or Kimi code.

## Screenshot / AI / Trial regression gate

Follow [Screenshot, AI and Trial Flow](SCREENSHOT_AI_TRIAL_FLOW.md) for preview/download, scope and filter testing, first review and changed-summary review reset, single/reusable-code signup, rollback, expiry/extension, paid conversion and cancellation. Verify the Windows desktop stops tracking when a trial expires or is cancelled.

## Billing / ERP settings regression gate

Follow [Billing & ERP Flow](BILLING_ERP_FLOW.md) and its Postman collection for billing lifecycle/role tests, token rotation/disable, event validation and payload scope tests. Apply migration `0003_billinginvoice_billing_cycle_and_more` first.
