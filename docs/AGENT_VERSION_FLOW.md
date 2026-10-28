# Desktop agent version: setup and testing

## Publish an installer

1. Change `desktop-agent/package.json` `version` to the release number, for example `2.0.0`, and build the appropriate installer with `scripts\build_desktop_agent_windows.bat` (or `npm run build:win` in `desktop-agent`). The installed app reports this package version.
2. Put the built installer on a reachable HTTPS download location. Copy its direct URL to **Installer download URL** in Admin Web > **Agent Version Management**. Alternatively, set `DESKTOP_AGENT_DOWNLOAD_URL` in the backend environment for a common fallback link. There is no `/downloads/` server route in this project; `http://localhost:8000/downloads/...` will not serve an installer.
3. Create an active rule with `latest_version` equal to the built agent version, and `minimum_supported_version` at or below it. To require updates, set minimum above the older installed version. The optional SHA-256 checksum is returned in the API; the current agent does not verify downloaded installers automatically.

## Rule scopes

| Actor | Actions | Effective rule |
| --- | --- | --- |
| Super Admin | Select **Global** or a company; create, edit, activate, deactivate | Active company rule wins, then active global rule, then server defaults |
| Company Admin | Manage own company rules; see global rules read-only | Own company rule wins over global |
| HR/Admin, Manager, Employee | View and test rules | Own company rule wins over global |

Only the newest active rule per company/platform is used. Creating or activating an active rule deactivates other active rules in that scope and platform. Deactivating a company rule restores the active global rule (if present). Editing cannot move a rule to another company; create a new rule for the new scope.

Platforms supported by the form: `windows`, `linux`, `darwin` (macOS). Versions are one to three numeric components, for example `2.1.0`.

## Agent behavior

- Before login, the public version check shows the global rule. Login sends `app_version` and `platform`, so the backend checks the employee's company rule *before* issuing a token. The agent shows the update screen for a blocked version.
- On launch with an existing login, the authenticated check uses the employee's company rule. If a rule changes while the agent runs, the server rejects unsupported heartbeat/activity/screenshot requests; the agent stops tracking and displays the update screen.
- Admin Web logins that do not send `app_version` are unaffected. Backend device registration and session start also reject unsupported versions with HTTP `426` and `blocked_reason: OUTDATED_AGENT`.

## API / Postman examples

Use `Authorization: Token <ADMIN_TOKEN>` and `Content-Type: application/json` for managing rules:

```http
POST /api/agent-versions/
Authorization: Token <SUPER_ADMIN_TOKEN>
Content-Type: application/json

{"company":1,"platform":"windows","latest_version":"2.0.0","minimum_supported_version":"2.0.0","download_url":"https://example.com/WorkPulse-Setup-2.0.0.exe","release_notes":"Desktop update","is_active":true}
```

Omit `company` to create a global rule as Super Admin. Company Admin requests are always assigned to their own company. To edit or deactivate a rule:

```http
PATCH /api/agent-versions/12/
Authorization: Token <ADMIN_TOKEN>
Content-Type: application/json

{"is_active":false}
```

To test an installed version, call `GET /api/agent/version-check/?platform=windows&version=1.0.0`. Without a token, this returns the global rule. With an employee or Company Admin token, it returns their company rule. A Super Admin can add `&company_id=1` to preview a company rule. The response includes `force_update_required`, `download_url`, `latest_version`, and `minimum_supported_version`.

Test the login gate with `POST /api/auth/login/` and body `{"email":"employee@example.com","password":"...","app_version":"1.0.0","platform":"windows"}`. If the company minimum is `2.0.0`, expect HTTP `426` with the effective version and installer URL; a valid newer agent should receive a token.

Backend tests: `python manage.py test core.tests --settings=workpulse_project.test_settings`. Web build: `npm run build` from `admin-web`. Desktop renderer build: `npm run build:react` from `desktop-agent` after installing its npm dependencies.
