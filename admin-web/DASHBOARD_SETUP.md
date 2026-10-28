# WorkPulse dashboard and theme update

This update is based on the uploaded `admin-web.zip`. It keeps the existing
application pages and login API, and replaces the dashboard and app shell.
The productivity baseline import remains a separate step and is not run by
this UI update.

## What the dashboard shows

- Company roster, active/inactive headcount, employees reporting activity and
  recent online status.
- Recorded work time, active time and idle time.
- PRODUCTIVE, NEUTRAL, UNPRODUCTIVE and UNKNOWN application usage.
- Highest productive application time and lower productive share, with each
  employee's classification coverage visible.
- Hourly activity for a single day, daily activity for a longer date range.
- Department breakdown and most-used applications/domains.
- Searchable, sortable employee table with 10/20/50/100-row pagination.
- Employee detail drawer with time categories, trend and top applications.
- CSV export of all matching employees, including rows beyond the visible page.
- Light/dark controls on the login screen and app header. The preference is
  saved in the browser, and the first visit respects its preferred color scheme.
- Responsive navigation, horizontally scrollable data tables, keyboard focus
  styles, chart-data tables and reduced-motion support.

## Apply the complete patch

Use `WorkPulse_Dashboard_UI_Patch.zip` to update an existing project. Its paths
start with `admin-web/`, `backend/` and `docs/`. Extract into the project root
and merge matching paths. Keep your current environment configuration.

**The new dashboard requires the backend update as well as the frontend.**
`admin-web.zip` contains only the complete frontend source. That archive can
replace the frontend folder, but does not install the new dashboard endpoint.
Neither archive includes `node_modules`, build output or credentials.

### Backend

The patch supplies:

- `backend/core/dashboard_api.py`: the new read-only dashboard API.
- `backend/core/urls.py`: the existing project's routes with the new route added.
- `backend/core/test_team_dashboard.py`: 17 focused dashboard tests.
- `backend/core/productivity_api.py` and `test_productivity_rules.py`: compatibility
  files for the productivity route already referenced by the supplied URL file.
  No baseline records are created or changed by these files.

If your URL file has additional local routes, retain them and add these two
lines instead of replacing that file wholesale:

```python
from .dashboard_api import TeamDashboardView

# Inside urlpatterns:
path('reports/team-dashboard/', TeamDashboardView.as_view(), name='team-dashboard'),
```

Run the normal backend check, then deploy/restart the WorkPulse backend:

```bash
python manage.py check
```

No new dependency, model, migration, seed command or productivity-rule import
is required. Existing employee mappings and historical activity are preserved.

### Frontend

Preserve the API URL used by your environment. For example, in `admin-web/.env`
or your deployment's build environment:

```dotenv
VITE_API_BASE_URL=https://YOUR_WORKPULSE_BACKEND/api
```

Use the actual WorkPulse backend, including `/api`, and restart/rebuild after an
environment change. From `admin-web`:

```bash
npm install
npm run build
```

`npm install` is only needed if dependencies are not installed. Package versions
are unchanged. For local development, `npm run dev` uses the existing port 5174.

Deploy the backend before the new frontend. Sign in with the existing Glutape
Company Admin account. It automatically receives its own company scope; no
company ID needs to be typed into the UI. Use Refresh to fetch a fresh snapshot.
Light/dark controls remain available on every existing page.

## Company and role scope

| Role | Workforce dashboard scope |
| --- | --- |
| Super Admin | Must select a company; receives only that company's metrics |
| Company Admin / HR Admin | All users assigned to their own company |
| Manager | Assigned team within the same company |
| Employee | Own activity only |
| Sales Admin | Existing trial-sales summary; no workforce data |

Company, department and employee scope is enforced by the backend. Supplying
another company's ID does not bypass these restrictions. Inactive employees
remain available through the All/Inactive employment filters. Department and
employment filters affect the complete overview; search/status/sort controls
affect the employee table and its CSV export.

## Metric definitions

| Metric | Source and meaning |
| --- | --- |
| Recorded work time | Active + idle seconds from heartbeats captured in the selected dates |
| Application time | Recorded activity durations, separately summed across the four usage categories |
| Productive share | PRODUCTIVE / (PRODUCTIVE + NEUTRAL + UNPRODUCTIVE) |
| Classification coverage | Classified application time / all application time, including UNKNOWN |
| Most productive time | Highest PRODUCTIVE application duration among visible employees |
| Lower productive share | Lower share among employees with some classified application time |
| Working / Idle now | Latest heartbeat within 180 seconds, its session still running, employment active |
| Offline | No qualifying current heartbeat/session; not a judgment of work performed |

UNKNOWN is not counted as UNPRODUCTIVE. Employees with no classified activity
are excluded from the high/low comparison. Missing work telemetry is displayed
as a dash, not inferred from application duration. Work time and application
time must not be added together. These categories are usage data, not completed
tasks, CRM transactions or employee performance scores.

Dates are inclusive in the Django server's configured timezone, shown in the
UI. A view supports up to 93 days. Telemetry belongs to its captured timestamp;
multiple devices can report overlapping durations. Employee/department labels
and employment status reflect current assignments, rather than a historical
snapshot. Running-session totals are not used as all-time attendance totals.

The existing desktop agent does not reliably provide browser URLs and derives
domains from window titles. Website activity without usable capture can remain
UNKNOWN. This UI update does not implement browser URL capture or new rules.

## API examples

The existing authentication format is `Authorization: Token YOUR_WORKPULSE_TOKEN`.

```text
GET /api/reports/team-dashboard/?from_date=2026-10-16&to_date=2026-10-16
GET /api/reports/team-dashboard/?from_date=2026-10-10&to_date=2026-10-16&department_id=4
GET /api/reports/team-dashboard/?employee_id=172&from_date=2026-10-16&to_date=2026-10-16
GET /api/reports/team-dashboard/?page=2&page_size=20&sort=share_asc
GET /api/reports/team-dashboard/?export=csv&search=GLUTAPE
```

IDs are examples and must exist within the requesting user's permitted scope.
Super Admin requests additionally specify `company_id`. JSON responses contain
summary, paginated employees, comparison lists, department totals, trend and
top applications. CSV exports ignore pagination, retain the table filters and
escape spreadsheet formula prefixes. Responses use `Cache-Control: private, no-store`.

## Verification and limits

- Production Vite build passed with the unchanged React 18 / Vite 5 dependencies.
- 28 backend tests passed on isolated SQLite: 17 dashboard tests and 11 existing
  Productivity Rules API tests.
- 27 frontend checks passed using React static rendering, real component action
  handlers and dashboard responses generated by the actual isolated API.
- Checked company/manager/employee isolation, inactive users, date boundaries,
  UNKNOWN treatment, heartbeat-derived work time, 60-user pagination, complete
  CSV export, formula escaping, rule-history preservation and bounded queries.
- Checked populated/empty/loading/error/company-selection rendering, table and
  comparison actions, theme controls, access rules and escaped employee names.
- Numeric palette checks cover foreground/background contrast in both themes.
- Browser preview/control was unavailable in this environment. Actual viewport
  layout, focus behavior and live-browser interaction were not visually tested.
- No live database was changed and no deployment was performed.

`DASHBOARD_VERIFICATION.json` records the verification method and results. After
deploying, check a real Glutape account on desktop/mobile in both themes and
compare a known employee's times with the existing activity/heartbeat records.
