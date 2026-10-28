# 15. Final Merge Source Of Truth

## Final package rule

`BOLD_WorkPulse_FINAL_MERGED_IT_READY_QA_PATCHED.zip` is the only ZIP to be given to Glutape IT.

Do not use:

- `BOLD_WorkPulse_SaaS_First_IT_Handover.zip`
- `BOLD_WorkPulse_SaaS_First_IT_Handover_CORRECTED.zip`
- `BOLD_WorkPulse_SaaS_First_IT_Handover_FINAL_GATE.zip`
- `BOLD_WorkPulse_SaaS_First_IT_Handover_kimi.zip`

## What was kept from FINAL_GATE

- Django backend structure
- Models, serializers, views, URLs and permissions
- Initial migration
- Seed command
- Policy acceptance enforcement
- Force-update enforcement
- Protected screenshot endpoints and ScreenshotAccessLog
- Trial/demo account module
- Billing skeleton
- ERP connector and token-based public ingestion
- Electron desktop agent tracking logic
- System idle detection using Electron `powerMonitor.getSystemIdleTime()`

## What was borrowed from Kimi

Kimi was used only for reference/inspiration in these areas:

- Page-wise admin web structure
- Sidebar/screen naming clarity
- Documentation presentation style
- `.gitignore` cleanup ideas

Kimi backend, authentication, model design, permissions and desktop tracking logic were not copied into the final source of truth.

## Final access-control rules

- Super Admin: all companies and system-wide records.
- Company Admin: own company only; cannot create/delete other companies.
- HR/Admin: own company HR/policy/activity scope.
- Sales/Admin: generated or assigned trial-sales scope only.
- Manager: assigned team only.
- Employee: own permitted data only.

## Staging configuration

Use local screenshot storage and mock AI:

```env
SCREENSHOT_STORAGE_MODE=local
AI_PROVIDER=mock
```

## Rollback

If staging fails due to local machine setup, do not use older ZIPs. Fix environment setup or report the exact command error.

## Do not change these rules without management approval

- Do not add Docker, Redis, Celery, Kubernetes or microservices.
- Do not expose direct media URLs for screenshots.
- Do not allow employee access to company-wide data.
- Do not allow Sales/Admin to extend/convert/cancel random companies by ID.
- Do not replace backend/desktop logic with Kimi code.
