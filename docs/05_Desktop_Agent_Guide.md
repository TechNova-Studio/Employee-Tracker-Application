# 05. Desktop Agent Guide

## Folder

```text
bold-workpulse/desktop-agent/
```

## Setup and run

From project root:

```bat
scripts\setup_desktop_agent_windows.bat
scripts\run_desktop_agent_windows.bat
```

## Login for staging

```text
employee@glutape.local
Demo@12345
```

## Expected first-run flow

1. Agent checks the global version; login checks the employee's company version before issuing a token.
2. If the app is below the applicable minimum supported version, the update screen appears.
3. Employee logs in.
4. Device registers with backend.
5. Latest monitoring policy appears if not accepted.
6. Employee accepts policy.
7. Employee starts work session.
8. Heartbeat, activity and screenshots upload during active session.
9. If internet is unavailable, heartbeat and activity records are queued locally and synced later.
10. On restart or a new policy release, the agent rechecks the latest policy and asks for acceptance before tracking.

## Server address and login recovery

On the login screen, select **Change server URL**, enter the backend address and click **Save & test connection**. Use `http://127.0.0.1:8000/api` when the backend runs on the same computer. On a different PC, enter the reachable backend URL, for example `https://workpulse.example.com/api`. The app adds `/api` if omitted and remembers the address on that PC. If `WORKPULSE_API_BASE` is set for the process, that configured address takes precedence and cannot be changed in the login form.

The backend must be reachable before employee login. Desktop sign-in requires a user assigned to a company, and device registration must complete. A saved login is checked with the backend at launch; a revoked token returns to the login form, while a temporary connection failure offers **Try again** without discarding the saved login. The app sends queued records only for the matching server, company and user. The company version rule is checked after the login identifies that company.

## Idle detection

The desktop agent uses Electron:

```javascript
powerMonitor.getSystemIdleTime();
```

This checks whole-computer idle time for staging and is not limited to mouse/keyboard inside the Electron app window.

## Privacy rules

The agent does not collect:

- keystroke content
- clipboard data
- webcam data
- microphone data

It records only mouse/keyboard counts, active app/window title, domain where technically possible, heartbeat, active/idle seconds and screenshots during a started work session.

## Windows build

```bat
scripts\build_desktop_agent_windows.bat
```

Code signing is external configuration for production only.

## Common errors

| Error                 | Fix                                                            |
| --------------------- | -------------------------------------------------------------- |
| Update required       | Check Agent Version Management screen or update app version    |
| Policy not accepted   | Accept latest policy in desktop agent                          |
| Policy declined       | HR/Admin must reactivate user in admin web                     |
| Screenshot missing    | Confirm session is running and `SCREENSHOT_STORAGE_MODE=local` |
| API connection failed | Confirm backend is running at `http://localhost:8000`          |
| Wrong server URL       | Open **Change server URL** on login and test the backend address |
| No company assigned    | Assign the user to a company in Admin Web before desktop login   |

## Do not change these rules without management approval

- Do not add keylogger/clipboard/webcam/microphone logic.
- Do not bypass force-update check.
- Do not bypass policy acceptance.

## Desktop npm install note

The desktop agent uses Electron. During `npm install`, Electron may download its runtime binary from Electron/GitHub download URLs in addition to the public npm registry. If desktop setup fails with a network/DNS error, first confirm internet access to public npm and Electron/GitHub download URLs. Do not solve this by adding Docker, Redis, Celery or changing architecture.
