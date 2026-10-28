# Manual Staging Smoke Test - Corrected Pack

1. Backend health check returns `ok`.
2. Super Admin login works.
3. Company Admin sees only own company.
4. Employee login works only when policy has not been declined.
5. Employee decline policy, then login is blocked with `POLICY_DECLINED`.
6. HR/Admin reactivates employee from User screen.
7. Employee accepts latest policy.
8. Session start works after policy acceptance.
9. Create a new active policy version.
10. Same employee session start is blocked until the new policy is accepted.
11. Set minimum desktop version above installed version.
12. Confirm device register/session/heartbeat/activity/screenshot APIs reject unsupported agent with HTTP 426.
13. Confirm outdated-agent alert is created.
14. Start desktop agent with valid version.
15. Confirm heartbeat and activity arrive.
16. Confirm screenshot upload arrives.
17. Open screenshot from Admin Web using protected View button.
18. Download screenshot using protected Download button.
19. Confirm ScreenshotAccessLog records view/download.
20. Generate demo code.
21. Trial signup creates company.
22. Trial extend works for scoped company.
23. Trial convert works for scoped company.
24. Trial cancel works for scoped company.
25. Try random company ID for trial extend/convert/cancel and confirm it is rejected.
26. Run `python manage.py generate_daily_ai_summaries` and confirm AI Summary page shows rule-based result.

## Final gate role permission smoke test

Run after seed data and login setup:

- Super Admin can write plans and companies.
- Company Admin cannot create/delete company or write plan.
- Company Admin can update own basic company settings only.
- Sales/Admin dashboard shows only own trial/sales scope.
- Manager dashboard shows assigned team only.
- Employee dashboard shows own data only.
- Employee cannot open ERP events, audit logs, billing invoices or other employee records.
- Sales/Admin cannot extend/convert/cancel a random trial company outside generated/assigned trial code scope.
- Policy acceptance list is read-only and role-scoped.
