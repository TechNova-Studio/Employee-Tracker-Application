# 13 Doubts Answered In Advance

## Should IT use Docker?
No. Do not use Docker for v1 staging.

## Is WorkPulse part of Glutape ERP database?
No. It is standalone SaaS. Glutape ERP integration is API-based only.

## Can employee use desktop agent as admin panel?
No. Admin is web-based. Desktop is employee agent only.

## Can staging run without S3?
Yes. Use local screenshot storage.

## Can staging run without AI key?
Yes. Rule-based AI summary fallback is included.

## Can staging run without payment gateway?
Yes. Billing skeleton exists. Payment gateway is External Configuration Required.

## Should agent be invisible?
No. The product must be transparent and policy-based.

## Should we record keystrokes?
No. Only mouse/keyboard counts, not content.

## What should IT not change without approval?
- Tenant isolation.
- Policy acknowledgement.
- No hidden monitoring.
- No cross-company access.
- Trial conversion data preservation.
- No Docker requirement for v1 staging.
