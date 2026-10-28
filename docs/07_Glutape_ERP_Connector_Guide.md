# 07 Glutape ERP Connector Guide

## Purpose

BOLD WorkPulse must remain standalone. Glutape ERP can send important work events to WorkPulse through API.

## Endpoint

`POST http://localhost:8000/api/erp/ingest/`

## Header

```text
X-WORKPULSE-TOKEN: <connector-token>
```

## Example body

```json
{
  "event_type": "pi_created",
  "external_id": "PI-2026-0001",
  "payload": {
    "customer": "Demo Customer",
    "created_by": "employee@glutape.local",
    "amount": 125000
  }
}
```

## Supported event examples

- lead_created
- followup_added
- pi_created
- pi_updated
- invoice_created
- dispatch_updated
- transporter_assigned
- capa_created
- price_engine_task_updated
- inventory_entry_created
- erp_user_login

## IT instruction

Do not merge WorkPulse database into Glutape ERP database. Use API only.

## Connector settings and event results

Create/edit a connector in Admin Web, choose its event permissions and copy the generated token into the ERP backend. "View token" and "Rotate token" are limited to Super/Company Admin and logged. List responses show a masked hint; disable a connector to stop new ingestion without deleting its event history. See [Billing & ERP Flow](BILLING_ERP_FLOW.md).

The business event examples above are stored as Received (HTTP 202); they do not trigger business workflow processing. The four employee lifecycle events are processed synchronously. See [Employee Lifecycle Postman Guide](ERP_EMPLOYEE_POSTMAN.md).
