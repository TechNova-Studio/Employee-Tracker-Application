# BOLD WorkPulse productivity telemetry fix — desktop 1.0.5

## Confirmed cause

The supplied Activity Timeline shows Google Chrome with titles such as
`WhatsApp - Google Chrome`, `(102) WhatsApp - Google Chrome` and
`(4) WhatsApp Business - Google Chrome`, with a blank Domain column.

The existing agent searched the window title for something resembling a domain
and did not send a URL. Those titles contain no `web.whatsapp.com`.
Windows `active-win` 8.2.1 supplies window/app metadata, but its browser `url`
property is macOS-only. The approved Glutape DOMAIN and CRM URL rules therefore
had no matching input on Windows. A browser name alone does not identify its site.

## What changes

- Desktop 1.0.5 obtains the current Windows browser address from Windows UI
  Automation. It reads the identified address control of the foreground window,
  checks its handle/process/title, and sends the real URL host/path and domain.
- If native active-window metadata supplies a browser URL, the agent uses it.
- No URL/domain is inferred from a tab title, filename or application name.
- Browser reads run in a separate, hidden process with a four-second timeout.
  Missing/blocked address controls leave the activity UNKNOWN and do not stop
  keyboard/mouse uploads. There is no previous-tab URL cache.
- Queries, fragments and URLs containing embedded credentials are not uploaded.
  URL rules should use host/path or non-sensitive path text.
- The backend derives a missing domain from an actual HTTP(S) URL, normalizes
  host casing/ports/trailing dots, and uses that same context for storage and
  classification. An actual URL overrides a conflicting supplied domain.
- Host/path URL rules, including the shared GitHub Pages CRM rule, are bound to
  the actual hostname. Unrelated pages containing the CRM address do not match.
- New Windows packaging checks require the active-window native binary and URL
  helper, in addition to the existing input and screenshot helpers.
- The 1.0.4 screenshot fix and global keyboard/mouse capture are included.

The approved 20 Glutape rules are unchanged. Department-specific rules retain
priority over company-wide rules. No guessed APP aliases or productive browser
rules are created. Exact Excel/Tally/other native APP rules remain pending their
approved telemetry confirmation.

## Apply the combined patch

1. Extract `WorkPulse_Productivity_Mismatch_Fix.zip` into the WorkPulse project
   root. Merge its `backend/` and `desktop-agent/` folders with those project
   folders. The archive contains complete replacements for changed files.
2. Deploy the updated backend to staging. Both `backend/core/views.py` and
   `backend/core/activity_context.py` are required together. No database schema
   migration or new environment variable is required by this fix.
3. On that backend, run the read-only baseline check:

   ```text
   python manage.py verify_glutape_productivity_rules --company-id 1
   ```

   This checks saved rules with synthetic inputs. It does not test browser URL
   capture. If it reports missing rules, inspect that environment; reinstalling
   the agent does not insert rules into an empty database.
4. Build a NEW Windows installer using the updated desktop source. Confirm its
   `.env` points to the WorkPulse backend being tested. Existing backend URL
   values are preserved; this patch does not supply or overwrite `.env`.

   ```powershell
   cd desktop-agent
   npm ci
   npm test
   npm run build:win
   ```

   Output: `dist-electron\BOLD WorkPulse-Setup-1.0.5.exe`.

   `npm ci` must include optional dependencies and installation scripts:
   `active-win` provides the native window metadata. If `check:browser` says
   its Windows binary is missing, resolve that dependency installation before
   distributing the build. Do not distribute a build that fails these checks.
5. On one employee PC, Punch Out and Quit the old agent, then install the new
   Setup EXE. Confirm version **1.0.5**. Source edits do not update an existing
   installed executable.
6. Log in, accept the current monitoring policy if required, Punch In, then use
   WhatsApp Web in Chrome for **60–90 seconds**. Keep the page focused, with the
   address bar unfocused. Refresh the admin Activity Timeline and examine NEW
   timestamps for that employee and company.
7. Verify the examples below. After this PC test passes, deploy the same backend
   changes to live, build/configure the agent for the live backend, and distribute
   that installer. If Agent Versions is used, publish version/download URL 1.0.5
   after the new installer is available. No automatic updater was added.

`dist.zip` is the complete desktop **source** at 1.0.5, including previous fixes.
It can replace the desktop source folder instead of merging the desktop patch.
Install the generated Setup EXE on employee PCs. Node/npm are needed on the
build computer; employee PCs receive the installer.

## Expected classifications using actual browser addresses

| Employee department | Captured site | Expected |
| --- | --- | --- |
| Sales / Purchase / Customer Service / HR / Dispatch | web.whatsapp.com | PRODUCTIVE |
| Accounts / IT / Factory / Store | web.whatsapp.com | NEUTRAL |
| HR | linkedin.com | PRODUCTIVE |
| Accounts | linkedin.com | NEUTRAL |
| IT | chatgpt.com | PRODUCTIVE |
| Sales | chatgpt.com | NEUTRAL |
| Any | boldsoftmations.github.io/crm-frontend/ | PRODUCTIVE |
| Any | mail.google.com | PRODUCTIVE |
| Any | Unclassified site/app | UNKNOWN |
| Any | LockApp.exe / Windows lock screen | UNKNOWN |

Confirm that each employee's WorkPulse department is assigned correctly. An
employee without a department gets the company-wide default; for WhatsApp that
is NEUTRAL. The backend does not infer a department from an email address.

## Support check if Domain remains blank

While a work session is running, use Chrome on a normal website for at least
60–90 seconds. Open `%APPDATA%` and the WorkPulse user-data folder, then read
`browser-diagnostics.json` before logging out.

It contains only the timestamp/version, source, availability flags and a bounded
error code. It does not include the URL, title, employee identity or tokens.

- `state=captured`, `source=windows_address_bar`, `domain_available=true`: inspect
  the NEW uploaded activity and the saved rules/employee department.
- `ADDRESS_BAR_UNAVAILABLE`: the address control could not be identified. PWA
  windows, unsupported/localized browser controls or restricted accessibility
  can have no accessible address. A site cannot be identified from its title.
- `ADDRESS_BAR_FOCUSED`: the bar was being edited; the draft was not recorded.
- `WINDOW_CHANGED`: foreground window/tab/title changed during the read. Keep
  the browser page focused for another interval.
- `AUTOMATION_UNAVAILABLE`, `BROWSER_READ_FAILED` or `BROWSER_READ_TIMEOUT`:
  the Windows helper could not complete. Share the diagnostic JSON; do not
  disable security software to make the read succeed.
- `WINDOW_METADATA_UNAVAILABLE`: active-window metadata was unavailable.
- `state=not_browser`: the foreground application was not a supported browser.

Known browser names/processes include Chrome, Edge, Firefox, Brave, Opera and
Vivaldi. Address-control accessibility depends on the installed browser and
Windows environment. Actual Windows capture remains a required rollout check.

## History and verification evidence

Existing activities retain their stored classification. Updating rules or this
code does not silently rewrite historical reports. Old title-only records cannot
be reliably assigned a website after the fact. Any historical correction would
need a separately reviewed scope and evidence.

Validation completed in the development environment:

- **74 desktop automated tests passed**, including browser-context and existing
  input/screenshot/session tests. Windows UI Automation responses are simulated.
- **62 backend automated tests passed**, including real API ingestion, department
  precedence, URL normalization, tenant isolation and unchanged history.
- **150 approved Glutape policy examples passed**; 12 exact-APP confirmations
  remain pending. The approved rule master remains 20 entries.
- React production build passed.
- Windows x64 directory packaging passed. Packaged 1.0.5 runtime source and
  unpacked browser/input/screenshot helper assets were checked.
- Actual Windows UI Automation runtime and NSIS Setup EXE installation could not
  be executed on this Linux development host. The ZIPs are source/patch archives.

`TEST_RESULTS.json` contains the context examples and validation summary.

References for the implementation:

- Microsoft UI Automation TreeWalker:
  https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.treewalker
- Chromium native Windows UI Automation:
  https://developer.chrome.com/blog/windows-uia-support-update
