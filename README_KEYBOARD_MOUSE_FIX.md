# BOLD WorkPulse keyboard/mouse capture — 1.0.3

This source update is based on the supplied attendance-style `dist.zip`.
The desktop attendance screen does not show keyboard/mouse counters or native
input status. Counts are captured in the background during an approved work
session and uploaded for the existing admin Activity Timeline.

The exact reason for the reported Windows `0/1` counts has not yet been
reproduced on that workstation. This release retains the global native counter,
exposes native failures instead of swallowing their details, and adds a direct
runtime check and upload diagnostics. A Windows test result is still needed
before claiming that the workstation issue is resolved.

## Apply

Use either the full `dist.zip` or `WorkPulse_Keyboard_Mouse_Fix.zip`, not both.
Both ZIPs use paths relative to the `desktop-agent` folder. Merge/replace there.
The patch supports the original upload and version 1.0.2, including removal of
its employee-facing input-counter UI. Preserve newer unrelated local edits.

From `desktop-agent`, on Windows with Node.js 22:

```powershell
npm ci
npm test
npm run diagnose:input
```

Close the running WorkPulse agent before the standalone input check. After
`WORKPULSE_INPUT_CHECK_START` appears, switch to Notepad, type 10 or more letters
and perform at least two actual mouse clicks. Wait 30 seconds for the final
`INPUT_CHECK_RESULT` line. The test uses Electron and the production native
monitor; it makes no backend requests, does not sign in, and saves no typed text.
Its numeric results appear only in the developer terminal, not the employee UI.

| Result | Meaning and next action |
| --- | --- |
| PASS | At least two key-down and two mouse-button-down events were received. Continue with the work-session upload check below. |
| NATIVE_CAPTURE_FAILED | The module could not load/start, or failed during the run. Send the final result's error_code and error_detail. |
| NO_KEYBOARD_OR_CLICKS | The hook started but no counted events arrived. Confirm typing and clicking during the test and share the result. |
| PARTIAL_INPUT | Only partial/single-device input was received. Send the final result and specify which inputs you performed. |
| CANCELLED | The test was interrupted and capture was stopped. Run it again for a complete result. |

The input test never generates artificial key or mouse events. Mouse movement
and scrolling do not count as clicks. A PASS establishes reception on that
machine during this test, not exact capture of every physical event or successful
backend delivery.

## Build and check the admin

After the local test passes:

```powershell
npm run build:win
```

Install the new output on the test employee PC:

```text
dist-electron\BOLD WorkPulse-Setup-1.0.3.exe
```

The footer must show version 1.0.3. Replacing source files or the React `dist/`
folder does not update an already-installed EXE. This ZIP contains source,
not a completed Setup EXE. No backend migration is needed for these changes.

Log in, accept the existing policy if requested, Punch In, type and click in
Notepad/Excel, then wait 60–70 seconds. Refresh the admin Activity Timeline and
inspect NEW rows for that employee, company and timestamp. Each row contains
interval counts rather than session totals. Older rows are unchanged.

Punch Out flushes the final partial interval and stops capture. Lock/suspend,
logout, authentication expiry, policy gates and application exit stop/pause the
native listener. Zero input counts do not automatically mean idle or
unproductive; idle detection and activity classification remain separate.

## If the native test passes but the admin still shows 0/1

The agent overwrites a single `input-diagnostics.json` support snapshot in its
Electron userData directory. It records version, native status/error, session
aggregate counts and the most recent live activity-upload attempt. Where the
backend returns saved activity items, it also records the saved integer counts,
so capture, transmission and server values can be compared.

In the Electron developer console, use the following support call and copy its
JSON output (this is not a control displayed in the normal desktop UI):

```javascript
window.workpulse.inputDiagnostics().then(data =>
  console.log(JSON.stringify(data, null, 2))
)
```

If using the developer terminal, optional `WORKPULSE_INPUT_DEBUG=True` enables
`[WorkPulse input]` snapshots during `npm start`. Native initialization errors
and server count mismatches are logged without enabling this flag.

Interpret the report:

- capture.state=unavailable: inspect error_code/error_detail.
- Native reception works but capture totals remain zero: check that the new
  agent is Punch In and permitted to capture (not locked, suspended or stopped).
- capture totals increase and last_activity_attempt.outcome=uploaded: compare
  keyboard_count/mouse_count with server_keyboard_count/server_mouse_count.
- uploaded_count_mismatch: the response's saved values differ from the sent
  integers. This is logged without retrying an already-created record.
- queued_after_activity / queued_after_heartbeat: inspect the HTTP status and
  the existing offline queue/sync flow. This is the last LIVE attempt at its
  timestamp; queued data may subsequently have been delivered by queue replay.
- Equal nonzero sent/server counts: inspect the admin's employee, timestamp,
  company, server and selected row.

Diagnostics omit login tokens, authorization headers, employee identity, window
content, URLs, raw keys and pointer coordinates. Native error text is limited
to one bounded line. Sign-out clears session totals and the last upload snapshot.

## Verified here

- 51 automated tests passed: input aggregation, session lifecycle, final flush,
  concurrent stop/upload, screen lock, policy/login gates, offline isolation,
  upload diagnostics, mismatch handling, privacy and employee-screen rendering.
- Production React build passed, 41 modules; no employee input counters remain.
- Dependency versions are unchanged from 1.0.2, including Electron 28.2.0 and
  pinned uiohook-napi 1.5.4.
- Windows x64 application directory packaging succeeded. The native prebuilt
  was checked in app.asar.unpacked. Packaged source bytes/version were checked.
- The Linux host's real native-loader failure was correctly reported as
  ERR_DLOPEN_FAILED / missing libXtst.so.6, rather than a successful zero count.

The Windows application was not interactively executed here. Automated input
events are simulated. Run the direct Windows test above before distribution.
The final NSIS installer must be built on Windows; this host lacks Wine.

## Main files

- electron/input-monitor.js: global aggregate counter and native error status.
- electron/main.js: session capture, 60-second uploads and support snapshots.
- electron/input-report.js: bounded support metadata fields.
- electron/diagnose-input.js, scripts/diagnose-input.js: explicit local test.
- electron/preload.js: support-only diagnostics IPC.
- src/screens/DashboardScreen.jsx: attendance UI without input-counter display.
- package.json/package-lock.json: version 1.0.3 and diagnostic command.
- tests/: native-event simulation, upload and lifecycle regression checks.
