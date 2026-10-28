# Windows screenshot fix — 1.0.4

## Confirmed defect

The packaged 1.0.3 app kept these screenshot-desktop files inside app.asar:

- node_modules/screenshot-desktop/lib/win32/screenCapture_1.3.2.bat
- node_modules/screenshot-desktop/lib/win32/app.manifest

The installed library rewrites its own source paths from app.asar to
app.asar.unpacked before copying those helpers into the Windows temporary
folder. In the old package both rewritten paths were missing. A developer PC
with helpers already cached in its temporary folder can conceal this defect;
a fresh employee PC may fail capture with ENOENT.

The builder now explicitly unpacks the Windows screenshot helper directory.
Pre-package and afterPack checks fail the build if either helper is missing or
empty. The actual rebuilt Windows package was checked, including byte equality
against both original dependency files.

## Apply and build on Windows

Use the full dist.zip or WorkPulse_Screenshot_Fix.zip. ZIP paths are relative to
`desktop-agent`; merge/replace there and preserve newer unrelated local edits.
The patch includes the earlier native input capture update and keeps employee
keyboard/mouse counters off the desktop UI. Unused old hashed UI assets may
remain after merging; dist/index.html references the current files.

```powershell
npm ci
npm test
npm run build:win
```

Install the NEW `dist-electron\BOLD WorkPulse-Setup-1.0.4.exe` on one employee
PC first. Confirm footer version 1.0.4. Copying source or reinstalling an older
Setup EXE does not apply this packaging correction.

Log in with that employee's account, accept the monitoring policy and Punch In.
The first capture is scheduled after 10 seconds, with later captures at the
company interval. Allow network time, then refresh the admin Screenshot Viewer
with the correct company, employee and date. Verify new timestamps.

This source ZIP is not an installer. Windows directory packaging was verified
on the build host; actual Windows screen capture and the final NSIS installer
still need the Windows build/smoke test above.

## Capture and upload diagnostics

Failed capture/upload attempts now write a bounded screenshot-diagnostics.json
support snapshot in Electron's userData directory and log a
`[WorkPulse screenshot]` line. Errors are no longer inserted into the offline
queue as if they were screenshots to retry; no image existed in those entries.

In the Electron developer console, support can inspect:

```javascript
window.workpulse.screenshotDiagnostics().then(report =>
  console.log(JSON.stringify(report, null, 2))
)
```

This support call is not shown on the employee attendance screen. It returns
version, session/capture state, module availability, failure phase, HTTP status
and a bounded error line. It does not expose screenshot bytes, authentication
headers/tokens, employee identity or AWS credentials. Logout clears the snapshot.

- phase=module/capture with ENOENT: confirm version 1.0.4 is installed and check
  whether security software blocked a helper. Do not disable system protection.
- phase=upload with 401: the authentication session expired.
- 403: inspect the policy, employee status, company tracking gate or version gate.
- 404: inspect the active session, endpoint and session/device association.
- 501: the checked backend has only local screenshot upload/view support. Merely
  setting S3 environment variables does not implement its S3 handlers; a separate
  backend S3 implementation is required. Switching production to local storage
  is not a durable S3 solution.
- 5xx or network timeout: inspect the WorkPulse backend/network.

Failed image uploads are not saved for durable offline replay by this patch;
the next eligible capture attempts again at the company interval. Captures and
uploads are scoped to the current employee/token/session. Lock/suspend and
Punch Out block new captures, overlapping captures share one operation, and
pending captures cannot upload after capture permission is withdrawn.

For a server-side storage check, run this read-only command in the WORKPULSE
Heroku app console, outside the Python >>> shell:

```bash
python manage.py shell -c "from django.conf import settings; print(settings.SCREENSHOT_STORAGE_MODE)"
```

## Verification

59 automated tests pass. Screenshot checks cover required packaging assets,
EMPLOYEE-token/device upload, startup/interval scheduling, missing helper and
storage-501 diagnostics, temporary-file cleanup, logout, screen lock and Punch
Out during pending capture. Existing keyboard/mouse, policy, login and queue
isolation tests also pass. Test screenshot bytes are synthetic, not real user
screens. React production build and Windows directory packaging pass.

Backend code and cloud credentials are not included in this patch. The existing
public API configuration is preserved. No database migration is needed.
