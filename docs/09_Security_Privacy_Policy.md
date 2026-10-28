# 09. Security and Privacy Policy

## Design principle

BOLD WorkPulse is a transparent employee work-control system, not hidden spyware.

## Explicitly not implemented

- No keystroke content logging
- No clipboard logging
- No webcam access
- No microphone access
- No hidden malware-like behaviour

The desktop agent records mouse/keyboard **counts only**, not key content.

## Role-based access control

| Role | Scope |
|---|---|
| Super Admin | All companies and system records |
| Company Admin | Own company only |
| HR/Admin | Own company HR/policy/activity scope |
| Sales/Admin | Own generated/assigned trial-sales scope only |
| Manager | Assigned team only |
| Employee | Own permitted data only |

## Tenant isolation rules

Every tenant-specific model has a company reference. Querysets are scoped server-side. The frontend must not be treated as a security layer.

Sensitive APIs scoped by backend include:

- ManagerReview
- TrialSignupLog
- TrialConversionLog
- TrialDashboard
- AuditLog
- BillingInvoice
- ERPConnector
- ERPEvent
- AgentVersion where company-specific
- Screenshots
- PolicyAcceptance

## Screenshot security

Screenshots are not exposed by direct media URL. UI must use:

```text
/api/screenshots/<id>/view/
/api/screenshots/<id>/download/
```

Every view/download/delete creates `ScreenshotAccessLog`.

Standard DELETE is converted to logged soft delete. IT should use the UI Delete button or `/soft-delete/` endpoint.

## Policy control

- Employee must accept latest active policy before session start.
- If policy is declined, login/session is blocked.
- Declined employee cannot self-reactivate using an old token.
- HR/Admin or Company Admin must reactivate the profile.
- If a new policy version is created, users must accept again.

## Force update control

Unsupported desktop agent versions are rejected on:

- device register
- session start
- heartbeat
- activity batch upload
- screenshot upload

An outdated-agent alert is created.

## ERP event privacy

ERP event payloads may contain business-sensitive data. Employees are blocked. Company Admin/HR/Admin see own-company events only. Public ingestion remains token-based.

## Do not change these rules without management approval

- Do not expose screenshot file path or media URL.
- Do not allow employees to read company-wide data.
- Do not add keylogger, clipboard, webcam or microphone access.
- Do not weaken tenant isolation for convenience.
