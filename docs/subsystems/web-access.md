# Web Access

## 1. Session Boundary

`webview_ui.run_desktop` binds the service to `127.0.0.1` when the Web UI token is empty. It generates a runtime credential for protected HTTP endpoints and AI WebSocket access. Configuring a Web UI token binds the service to `0.0.0.0` and requires that token for protected requests.

## 2. Log Read Interface

The local-only session accepts read-only log requests without a credential at `/log`, `/diagnostics/timeline`, `/diagnostics/errors`, and the diagnostic log and export routes. The request must arrive from a loopback address with a loopback Host. Browser origin and fetch metadata must identify the same local Web UI; the log WebSocket requires an Origin header. Cross-origin and remote requests fail. Sessions with a configured token require that credential.

AI chat at `/ws/chat`, AI analysis, diagnostic deletion, and other mutating endpoints do not receive the local log-read exemption. The source-snippet tool retains its file allowlist.

For authenticated `/log` subscriptions, the first frame carries the valid Web UI token within five seconds. This credential authorizes the log subscription independently of Origin, Host, scheme or port, including absent Origin and proxy-rewritten Host values. HTTPS termination and port forwarding require WebSocket upgrades to reach the backend; forwarded headers grant no tokenless access. Other routes retain their existing origin checks.

## 3. Diagnostic Browsing

The log schedule page opens in time browsing with adjacent ten-minute windows and a refresh action. The date picker is a draft; loading commits the displayed center and exporting uses that center. Ordinary windows expose their screenshots in capture order and select the frame nearest the center. The API returns at most the latest 1000 logs with an explicit truncation flag; exports retain the complete window. Error archives use a separate tab and keep their original merged bounds and saved evidence.

`GET /diagnostics/timeline?at=<milliseconds>` returns `logs`, `screenshots` (relative paths), and `truncated`. The existing log-read credential boundary applies. The [shared loader decision](../../.agents/notes/implemented/simplification/2026-10-10-log-window-navigation.md) records implementation and verification.

## 4. Subsystem Invariants

- <a id="frontend-navigation-dispatch"></a>**Frontend Navigation Dispatch**: Known frontend page navigation resolves before API dispatch according to the [frontend navigation contract](#6-frontend-navigation).

- <a id="log-window-cohesion"></a>**Log Window Cohesion**: Displayed logs, screenshot navigation and export share one loaded time window or error archive; date drafts and superseded requests never replace that source, and failed source changes expose no stale evidence.

- <a id="local-log-read-boundary"></a>**Local Log Read Boundary**: A WebView session without a configured token permits read-only log requests from loopback with valid browser origin metadata; remote and cross-origin requests are rejected, and AI chat and mutating endpoints retain their credential checks.
- <a id="credentialed-log-forwarding"></a>**Credentialed Log Forwarding**: Log WebSockets with a valid first-frame token are authorized independently of Origin, Host and forwarded headers; tokenless access remains restricted to the local log-read boundary.
- <a id="managed-instance-admission"></a>**Managed Instance Admission**: Individual and bulk manager launches use the same stopped-process, selected-directory, update and port checks. Startup reservations prevent another launch before runtime registration appears.
- <a id="stopped-instance-configuration"></a>**Stopped Instance Configuration**: Manager edits require the instance process to have exited, not merely stopped automation. Name, directory, deletion and connection settings share the backend guard; future instance settings reuse it.

The [local log access decision](../../.agents/notes/implemented/bug-fix/2026-09-29-local-log-access.md) records the regression and verification.

The [credentialed log forwarding decision](../../.agents/notes/implemented/bug-fix/2026-10-10-https-log-forwarding.md) records the proxy compatibility boundary and verification.

## 5. Desktop Startup

`webview_ui.run_desktop` evaluates `start_automatically` once per process, in foreground and background modes. It claims startup ownership before exposing the HTTP service. `/status.desktop_startup_handled` and the existing `/status.auto_start_handled` remain true throughout that desktop process, including while stopped and when automatic tasks are disabled. The desktop flag also identifies process-owned resource automation; update restarts on other hosts do not claim that ownership. Browser refresh, closing and reopening the window, tray browser actions, and importing configuration do not schedule another automatic start. Manual task controls remain available.

The startup worker waits for the active software update operation to finish. When resource checking and automatic installation are enabled, it checks and completes installation before admitting automatic tasks. Resource installation uses a credentialed POST context; ordinary task startup uses a separate credentialed GET context for `/start/<mode>`, without requesting temporary device preparation. Resource check or installation failure preserves the existing resource fallback and still permits task startup. Stop or application shutdown cancels pending automatic admission, including during the resource step. Resource automation also runs when task autostart is disabled. The frontend observes tracked resource jobs and retains manual resource installation.

Update and process-operation restarts preserve their explicit policy: `MOWER_RESUME_MODE` values `0` and `1` select that task mode; otherwise `MOWER_RESTART_JOB` requires `MOWER_RESUME_RUN=1` and resumes mode `2`. The persisted autostart option does not override an explicit stopped restart. Other hosts that do not claim desktop startup ownership retain their existing frontend fallback; this change does not alter the separate Android launcher.

The [desktop startup decision](../../.agents/notes/implemented/bug-fix/2026-10-11-desktop-process-autostart.md) records the cause and verification.

## 6. Frontend Navigation

For GET and HEAD requests, an explicit positive `text/html` Accept entry and a missing, `document` or `iframe` Sec-Fetch-Dest identify page navigation. At process startup, known pages load from the distribution's `frontend-routes.json`, falling back to the source manifest when absent. Request matching uses this immutable set without reading the manifest and ignores case and trailing slashes. Navigation to these pages returns `index.html` before API dispatch, including `/mastery-recommendation`, which shares its URL with a JSON endpoint. Both representations declare `Vary: Accept, Sec-Fetch-Dest`.

JSON clients, wildcard Accept requests and non-read methods retain API dispatch and credential checks. Documentation files and directories retain their static responses. Unknown APIs and missing assets retain 404 responses; unknown extensionless page navigation outside API and resource prefixes retains Vue's missing-page display.

The [navigation dispatch decision](../../.agents/notes/implemented/bug-fix/2026-10-12-frontend-navigation-dispatch.md) records the defect and focused verification.

## 7. Desktop Instance Manager

[`manager.py`](../../manager.py) exposes the manager bridge; [`InstanceController`](../../arknights_mower/utils/manager_instances.py) owns lifecycle admission and offline configuration writes. Instance names and directories remain in `instances.json`. The manager reads current runtime registrations with a strict, single-attempt scan and combines them with persisted launch reservations. Unreadable state blocks operations rather than authorizing another process or configuration overwrite. Resolved, case-normalized data directories identify instances, including directory aliases. A reservation remains active while its child process is alive, across manager window recreation; verified process exit releases it. Starting successfully means that process creation succeeded, not that HTTP startup is ready.

The UI shows stopped, starting, running and stopping process states. Starting and running managed instances expose Stop, which sends the existing instance-specific graceful exit request, including before registration completes. It stops the entire instance and its automation, not just the automation thread. Stopping does not permit editing or restarting until process exit. Non-managed instances sharing a directory block launch and edits but must be exited from their own application. The manager does not kill unrelated processes or force termination after a stop request.

Manager list and configuration mutations run under a shared admission lock and recheck live processes. Folder selection releases that lock while the dialog is open, then verifies the original row and both directories before saving. The UI disables configuration controls while a process is live and closes stale edit dialogs; the backend remains authoritative. Bulk open and close each require a confirmation dialog. Bulk open checks each row's eligibility immediately before dispatch, silently skips ineligible rows and retains the individual startup checks. Actual startup failures remain warnings and do not prevent other eligible rows from being processed. Repeated registration scans and port probes add overhead with many instances. Deletion requires a separate confirmation naming the instance; it removes only the manager entry, not the saved files. Status refresh cancels a pending deletion if the selected row changes or becomes non-editable. Ordinary frontend bridge calls have a fifteen-second response budget; that deadline only ends the frontend wait and does not cancel Python work. Native directory selection waits for the user's confirmation or cancellation without that deadline and retains the UI's busy state until the call returns or fails, followed by a bounded state refresh. State refresh failures disable actions until a complete snapshot is available again.

Connection settings use each instance's `config/conf.yml`, under `webview.token` and `webview.port`, rather than a second copy in `instances.json`. A blank port saves as `0` and requests a random port. Managed launches honor an explicit port from 1 through 65535 regardless of whether a token is configured. Existing token binding rules in [Session Boundary](#1-session-boundary) remain unchanged. Standalone desktop launches retain their token-dependent fixed-port selection, with `0` also resolving to a random usable port. Active fixed ports and pending launches reserve their port during admission, and the final HTTP bind remains authoritative if an external process takes that port after the check. The same stopped-instance dialog edits [assistant authorization](ai-assistant.md#managed-assistant-authorization); model-provider configuration stays in Mower settings.

Connection settings are drafts until Save. Writes preserve other YAML fields, including unknown private settings, and use atomic replacement. If only legacy `conf.yml` exists, the manager copies its complete mapping into the current path with the selected connection fields; normal startup retains responsibility for other configuration migrations. Invalid or unreadable configuration is not replaced with defaults. Failed configuration or instance-list writes retain the previous saved data. These changes preserve existing domain-concept definitions and require no glossary changes.

Focused offline verification: `pytest arknights_mower/tests/manager_tests.py arknights_mower/tests/manager_instance_controls_tests.py`; from `ui/`, `npm test -- manager/bridge.test.js manager/MowerManager.test.js`. Desktop lifecycle and registration regressions live in `webview_ui_tests.py`, `desktop_lifecycle_tests.py` and `update_runtime_tests.py` under `arknights_mower/tests/`. No live device or game operation is needed for these checks.
