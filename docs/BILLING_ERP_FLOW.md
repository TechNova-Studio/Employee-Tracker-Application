# Billing and ERP Connector update

## Apply the update

Keep the existing local `.env`. Activate the backend environment, apply migration `0003_billinginvoice_billing_cycle_and_more`, and restart the backend and Admin Web.

```bat
cd backend
venv\Scripts\activate
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

In another terminal:

```bat
cd admin-web
npm install
npm run dev
```

The migration adds invoice calculation/timestamp/notes fields and `ERPConnector.token_rotated_at`. It preserves existing invoices, connectors, tokens and employee mappings. Previous placeholder invoices keep their existing status and amount; no payment is inferred by the migration.

## Billing & Subscriptions

### Roles

- Super Admin can configure plans/subscriptions and create, issue, void or record payment against invoices.
- Company Admin can read their own company's subscription and billing records. Their UI does not show billing mutation actions. The backend enforces the same restriction.
- HR, Manager, Sales and Employee cannot access billing/subscription records. Existing permitted read access to the plan catalogue for trial-related flows is retained.

### Plan and subscription setup

1. Open **Billing & Subscriptions** and select a company or view all companies.
2. Super Admin can add/edit the six supported plan codes. Plan code is immutable. Rates cannot be negative; user/device limits and retention must be positive. Internal and Trial plans must have zero rates.
3. Deactivate a plan to remove it from new subscription selection. Existing subscriptions retain their rate and history; plans cannot be deleted through the API.
4. Select **Configure subscription**, choose an active company, an active paid/internal plan and the billing cycle. Internal uses None; paid plans use Monthly or Annual.
5. This synchronizes company plan, capacities, retention and subscription rate/status. A plan below the company's current active user/device count is rejected.
6. Trial companies use the existing **Trial Dashboard → Convert** flow. Suspended companies must be reactivated before configuration.

Plan `price_per_user` and subscription `price_per_user` are treated as **monthly INR rates** in this manual billing flow. Annual billing uses 12 monthly rates; no automatic annual discount is applied. A zero-rate negotiated/Enterprise subscription cannot generate an invoice until a billable plan rate is configured and applied to the subscription. Changing a plan's rate does not silently change existing subscription rates.

AI/ERP plan feature flags remain existing metadata; this update does not add entitlement enforcement for those flags. They are not shown as functional switches in the new plan editor.

### Invoice lifecycle

1. A billable subscription displays **Create draft**. Choose the start date and optional notes.
2. Backend captures active tenant user count (active Django account and active employee profile), monthly rate, cycle, currency, description and total. The client cannot supply a different company, amount, status, quantity or currency.
3. Monthly total = active users × monthly rate. Annual total = active users × monthly rate × 12. Decimal arithmetic is used.
4. The end date is one calendar billing cycle after the chosen start, minus one day. Month/year additions clamp to the target month's last valid day before subtracting one day. For example, 1 September through 30 September is monthly; an annual cycle starting 29 February 2024 ends 27 February 2025.
5. Overlapping non-void billing periods are blocked, including existing placeholder records with dates. Company locking serializes generation against other billing changes on PostgreSQL.
6. **Issue** moves Draft to Issued. **Record payment** requires Issued and a nonblank bank/payment reference, then records the full amount as Paid. Repeating the same completed action does not duplicate the audit record.
7. **Void** requires a reason and is available only for Draft/Issued records. A paid record cannot be voided. Obsolete legacy placeholders may be voided by Super Admin to release a blocked billing period, but cannot be issued or marked paid through this flow.
8. Amount/rate/user count remain historical snapshots even if the plan or employee count later changes. Invoices cannot be edited or hard-deleted through the API.

Invoice numbers use `WP-MANUAL-<year>-<database ID>`. The details screen shows calculation, period, status, issue/payment/void timestamps, payment reference, recorder and notes. Totals are grouped by currency and status, so legacy foreign-currency records are not mixed into INR totals.

**Implemented scope:** internal/manual billing records. Recording payment confirms money already received elsewhere. It does not charge a customer, contact a gateway, email an invoice or enable checkout. Taxes, GST/tax invoices, partial payments, refunds, recurring scheduling, discounts and proration are not implemented. Razorpay/Stripe integration still requires implementation as well as credentials; putting a key in `.env` alone does not enable it.

## ERP Connector Settings

### Configuration and tokens

1. Super Admin selects the company; Company Admin is scoped to their own company. HR can read settings/events but cannot edit or reveal/rotate tokens.
2. Create a named connector and select allowed events. The four employee lifecycle events are selected by default. An active connector requires at least one event.
3. Event names are validated lowercase names containing letters, digits and underscores (maximum 64 characters). Duplicate entries are normalized; lists above 50 entries and invalid data types are rejected. API clients can register valid custom business-event names; these are received-only. The UI preserves previously configured custom names.
4. Connector names are unique case-insensitively within a company through the controlled API. Company cannot be changed after creation. There is no hard delete; Disable retains history and employee mappings.
5. Tokens are generated on the server. Create, **View token**, and **Rotate token** return the full token only to an authorized admin with `Cache-Control: private, no-store`. List/detail endpoints return a masked hint.
6. Reveals/rotations are audited without storing the secret in new audit payloads. Existing audit API responses redact token/password fields. Legacy database audit entries are preserved.
7. Rotating invalidates the old token immediately. Copy the new token to the **ERP backend** before sending more events. Disabling blocks new ingestion with that token. Rotation does not create a new connector or lose mappings.

The token dialog holds the secret in memory and clears it on close; it is not saved to localStorage. No actual ERP connection is claimed from the Active switch alone: **Last received** and event results are the delivery evidence.

### Ingestion and event viewer

```http
POST /api/erp/ingest/
Content-Type: application/json
X-WORKPULSE-TOKEN: <connector-token>
```

```json
{
  "event_type": "erp_user_created",
  "external_id": "21",
  "payload": {
    "email": "employee@example.com",
    "first_name": "Example",
    "is_active": true
  }
}
```

The connector token determines the company. Each employee event must include `external_id`, containing the stable CRM employee/user primary key as a string. An explicit connector + external-ID mapping identifies the WorkPulse User. Email and display employee codes are metadata, not lookup keys. Creation requires email; active/inactive events need only the source ID and optional status. See `ERP_EMPLOYEE_POSTMAN.md` for mapping APIs, bulk import and onboarding.

- **Processed:** one of the four employee lifecycle events completed. Existing create/update/active/inactive behavior is preserved.
- **Failed:** an employee event failed processing; view its error. Resolve the source problem and send a current corrected event. The UI does not replay historical events, which could be stale.
- **Received:** an allowed business/custom event was stored with HTTP 202. There is no business workflow processor for it yet.
- **Pending:** an unprocessed employee record without a recorded failure, for example a legacy record.

The event list has company, source connector, type, result, date and employee ID/email/reference search filters plus pagination. List responses omit full payloads; **View details** fetches the authorized complete payload and timestamps. Employee/Sales cannot access ERP events; Managers retain their existing own-company read access through the event API.

Employee lifecycle lookup uses explicit connector-scoped CRM ID mapping. Existing users must be linked first; a create event can create a missing employee and its mapping atomically. Existing email collisions require review and explicit linking. New employees still need secure password setup/SSO. CRM hooks/retries, department/manager/designation synchronization, source ordering and immutable event-ID deduplication remain separate work.

## APIs and Postman

Import `Postman_Billing_ERP_Settings.postman_collection.json`. Set the admin token and company/plan/subscription/connector variables for staging. Execute requests individually. Issue/payment/void and token rotation change state; do not run them against a production account merely to inspect responses.

| Method | Endpoint | Body / filters |
|---|---|---|
| GET / POST / PATCH | `/api/plans/`, `/api/plans/{id}/` | Super Admin writes; plan validation above |
| GET | `/api/subscriptions/` | `company_id`, `page` |
| GET | `/api/subscriptions/form-options/` | Companies, active paid/internal plans, permissions |
| GET | `/api/subscriptions/overview/` | Optional `company_id`; counts and currency/status totals |
| POST | `/api/subscriptions/configure/` | `company_id`, `plan_id`, `billing_cycle` |
| GET | `/api/billing-invoices/` | `company_id`, `status`, `page` |
| POST | `/api/billing-invoices/` | `subscription_id`, `billing_period_start`, optional `notes` |
| GET | `/api/billing-invoices/{id}/` | Invoice snapshot and lifecycle timestamps |
| POST | `/api/billing-invoices/{id}/issue/` | `{}` |
| POST | `/api/billing-invoices/{id}/record-payment/` | `{ "reference": "BANK-..." }` |
| POST | `/api/billing-invoices/{id}/void/` | `{ "reason": "..." }` |
| GET | `/api/erp-connectors/form-options/` | Optional `company_id`; companies, event catalogue, connector choices, ingest URL |
| GET | `/api/erp-connectors/` | `company_id`, `status=ACTIVE/INACTIVE`, `page`; no full token |
| POST | `/api/erp-connectors/` | `name`, `allowed_event_types`, `is_active`; Super Admin must include `company` |
| PATCH | `/api/erp-connectors/{id}/` | `name`, `allowed_event_types`, `is_active` |
| POST | `/api/erp-connectors/{id}/reveal-token/` | `{}`; admin only |
| POST | `/api/erp-connectors/{id}/rotate-token/` | `{}`; admin only |
| GET | `/api/erp-events/` | `company_id`, `connector_id`, `status`, `event_type`, `search`, `from_date`, `to_date`, `page` |
| GET | `/api/erp-events/{id}/` | Scoped full payload |

## Verification

```bat
cd backend
python manage.py test core.tests --settings=workpulse_project.test_settings --verbosity 1
python manage.py makemigrations --check --dry-run --settings=workpulse_project.test_settings
cd ..\admin-web
npm run build
```

Focused tests cover role/tenant isolation, exact decimal calculation, annual periods, duplicate/overlapping drafts, immutable invoice snapshots, manual payment/void transitions, legacy placeholders, plan validation, pagination, token masking/rotation/disable, audit redaction, event selection validation, employee/business result states and event details. API tests use SQLite. PostgreSQL concurrency behavior and live browser/Windows operation still require staging verification.
