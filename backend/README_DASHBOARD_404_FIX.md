# WorkPulse dashboard 404 fix

The new admin dashboard requests `GET /api/reports/team-dashboard/`. The uploaded backend had no matching URL or dashboard implementation, so Django returned HTTP 404.

## Apply the small patch

Merge the patch into the project folder containing `backend/`:

- `backend/core/dashboard_api.py`: dashboard data, company selection, employee pagination, department summaries, usage charts and filtered CSV export.
- `backend/core/urls.py`: imports and registers `TeamDashboardView`. All existing routes from the uploaded ZIP are retained.
- `backend/core/test_team_dashboard.py`: dashboard regression checks.

If your local URL file has additional custom routes, keep them and add only these two lines in the appropriate places:

```python
from .dashboard_api import TeamDashboardView

# Inside urlpatterns:
path('reports/team-dashboard/', TeamDashboardView.as_view(), name='team-dashboard'),
```

Deploy the patched WorkPulse backend to staging, then refresh the admin dashboard. A Super Admin must select Glutape from the company dropdown to load its metrics. A Company Admin automatically sees their assigned company.

No database migration, employee import, productivity-rule import or new environment variable is required for this fix. Keep the backend's existing database, CRM SSO settings and environment configuration.

## Verify in the deployed backend console

```bash
python manage.py shell -c "from django.urls import resolve; print(resolve('/api/reports/team-dashboard/').func.view_class)"
```

Expected: `<class 'core.dashboard_api.TeamDashboardView'>`.

In the browser Network panel, the authenticated request to `/api/reports/team-dashboard/` should return HTTP 200. A Super Admin's first response includes company options; after selection it includes the selected company's metrics. A bare unauthenticated request receives 401/403.

If the deployed route still returns 404, check that the backend deployment includes these files and that the admin web API base URL points to that same backend.

## Validation

44 tests passed against the uploaded backend in an isolated in-memory SQLite database: 17 dashboard, 11 productivity-rule API and 16 Glutape baseline tests. Checks cover role and company isolation, empty data, company selection, date boundaries, employee pagination beyond 50 users, UNKNOWN handling, employee-code fallback, CSV export and preservation of historical activity.

This verifies local backend behavior. No live or staging deployment or database operation was performed here.

The full backend ZIP is an alternative to the patch. It contains the uploaded source plus this fix; environment secrets and Python caches are excluded. Keep your existing `.env` for local use and existing Heroku Config Vars for deployment.
