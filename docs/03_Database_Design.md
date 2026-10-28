# 03 Database Design

## Core SaaS tables
- CompanyPlan
- Company
- Subscription
- BillingInvoice

## User and role tables
- Django auth User
- Profile
- Department

## Agent and monitoring tables
- Device
- AgentVersion
- PolicyVersion
- PolicyAcceptance
- WorkSession
- Heartbeat
- ActivityLog
- Screenshot
- ScreenshotAccessLog

## Productivity and management-control tables
- AppWebsiteCategory
- Alert
- DailyAISummary
- ManagerReview
- AuditLog

## Trial/demo tables
- DemoTrialCode
- TrialSignupLog
- TrialConversionLog

## ERP connector tables
- ERPConnector
- ERPEvent

## Tenant rule
Every tenant-specific table is directly company-scoped or company-scoped through a parent relation.

- Direct company field: Company, Department, Subscription, Device, PolicyVersion, PolicyAcceptance, WorkSession, Heartbeat, ActivityLog, Screenshot, ScreenshotAccessLog, AppWebsiteCategory, Alert, DailyAISummary, TrialSignupLog, TrialConversionLog, ERPConnector, ERPEvent, AuditLog, BillingInvoice.
- Derived company scope: ManagerReview is scoped through `ai_summary.company`.
- DemoTrialCode is scoped through generated_by/sales_owner company and used_by_company for trial management.
- AgentVersion supports global staging rules with `company = null` and optional company-specific rules.

## Migration instruction
Initial migration is included:

```text
backend/core/migrations/0001_initial.py
```

The setup script runs:

```bat
python manage.py migrate
python manage.py seed_demo_data
```

Do not rely on `makemigrations` during staging setup. Run `makemigrations` only later when developers intentionally change models.
