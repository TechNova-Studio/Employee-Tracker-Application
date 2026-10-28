# 14. External Configuration And Production Readiness

This document does not postpone product features. It lists only real-world production configuration required after staging.

Staging works with:

```env
SCREENSHOT_STORAGE_MODE=local
AI_PROVIDER=mock
```

## Required before production

| Item | Why needed | `.env` / setting | Who provides | Staging works without it? | IT action |
|---|---|---|---|---|---|
| Domain | Public access | `BACKEND_BASE_URL`, admin URL | Management/IT | Yes | Point DNS after server is ready |
| SSL certificate | Secure HTTPS | Web server config | IT/vendor | Yes | Install certificate before production |
| S3 bucket | Production screenshot storage | `SCREENSHOT_STORAGE_MODE=s3`, S3 fields | IT/AWS owner | Yes | Create bucket and fill credentials |
| AI API key | Real AI summaries | `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` | Management/IT | Yes, mock works | Add key after approval |
| Razorpay/Stripe | Real billing | `RAZORPAY_*`, `STRIPE_*` | Accounts/Management | Yes | Configure only for paid rollout |
| Email/SMS | Notifications | `EMAIL_*` | IT/vendor | Yes | Configure provider credentials |
| Windows code signing | Trusted installer | Certificate outside `.env` | Management/IT | Yes | Sign installer before external rollout |
| Mac signing/notarization | Mac distribution | Apple developer credentials | Management/IT | Yes | Configure when Mac build required |
| HR/legal approval | Monitoring compliance | Policy content in admin web | HR/Legal/Management | Staging test yes | Finalize policy text |
| Backup policy | Production data safety | DB/server process | IT | Staging yes | Create scheduled backups |
| Server hardening | Production security | OS/web server | IT/vendor | Staging yes | Harden server before public access |

## Production notes

Production may later use Gunicorn/Nginx or equivalent normal hosting, but staging must not depend on this.

## Do not change these rules without management approval

- Do not switch to S3 before local staging is working.
- Do not switch AI from mock before staging test is complete.
- Do not activate billing provider until management approves.
