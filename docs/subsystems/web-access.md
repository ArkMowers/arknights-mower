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
