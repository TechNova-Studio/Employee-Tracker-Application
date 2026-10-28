# 16 - Correction Audit Report

## Verified blocker corrections applied

| Area | Correction applied |
|---|---|
| RBAC | Added `backend/core/permissions.py` with strict role classes and applied them to protected resources. |
| Tenant isolation | Scoped direct company tables by company and derived tables through parent company relations. ManagerReview is scoped through AI summary company/team. |
| Trial management | Extend, convert and cancel now require allowed trial company scope. Random company ID access is blocked. |
| Trial audit | Extend, convert, cancel and demo-code cancel create audit logs. |
| Policy control | Login blocks `POLICY_DECLINED`; session start requires latest active policy acceptance. |
| Force update | Unsupported agent versions rejected on device register, session start, heartbeat, activity and screenshot upload. |
| Outdated alert | Outdated-agent alert is created when unsupported version is detected. |
| Desktop idle | Desktop agent uses Electron `powerMonitor.getSystemIdleTime()` for whole-computer idle detection. |
| Privacy | No key content, clipboard, webcam or microphone capture added. |
| Screenshot security | Direct media URL removed; protected view/download endpoints added; view/download/delete logs access. |
| Admin web | Key screens have simple forms instead of raw JSON for management staging tests. |
| Dependencies | React, Vite, Electron and related packages are pinned. |
| Migrations | `0001_initial.py` included; setup runs migrate and seed only. |
| Docs | 8-hour checklist, runbook, API, QA and security docs updated. |

## Remaining external configuration only

- Production S3 bucket and credentials.
- AI API provider key if real AI is required.
- Razorpay/Stripe production credentials.
- Domain, SSL and production server hardening.
- Windows code signing and Mac notarization.
- Final HR/legal approval of monitoring policy.

Staging does not require these items.
