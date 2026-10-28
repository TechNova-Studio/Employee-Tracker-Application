# AI Analysis Guide

Use **AI Daily Summaries** in Admin Web to generate and review daily summaries. Super Admin selects a company; Admin/HR operates within their company; Manager operates within their assigned team. Employees can read their own summaries.

The current engine is rule-based. It uses recorded heartbeat time, activity categories, top apps/domains and screenshot counts. It does not call an external AI provider. Configuring an API key alone does not enable a model integration.

Summaries are advisory. Human review is required before any employee-related action. No automatic disciplinary decision is made.

From `backend` with the environment activated:

```bat
python manage.py generate_daily_ai_summaries
python manage.py generate_daily_ai_summaries --date 2026-09-26
python manage.py process_pending_ai_jobs
```

The command and UI share the same generator. Identical reruns retain the review decision; changed data returns the summary to Pending while preserving review history. Heartbeats are attributed by their recorded local date so overnight sessions do not put the entire session into its start day.

See [Screenshot, AI and Trial Flow](SCREENSHOT_AI_TRIAL_FLOW.md) for the full UI flow, API requests, scope rules and verification steps.
