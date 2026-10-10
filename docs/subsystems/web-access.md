# Web Access

## 1. Session Boundary

`webview_ui.run_desktop` binds the service to `127.0.0.1` when the Web UI token is empty. It generates a runtime credential for protected HTTP endpoints and AI WebSocket access. Configuring a Web UI token binds the service to `0.0.0.0` and requires that token for protected requests.

## 2. Log Read Interface

The local-only session accepts read-only log requests without a credential at `/log`, `/diagnostics/timeline`, `/diagnostics/errors`, and the diagnostic log and export routes. The request must arrive from a loopback address with a loopback Host. Browser origin and fetch metadata must identify the same local Web UI; the log WebSocket requires an Origin header. Cross-origin and remote requests fail. Sessions with a configured token require that credential.

AI chat at `/ws/chat`, AI analysis, diagnostic deletion, and other mutating endpoints do not receive the local log-read exemption. The source-snippet tool retains its file allowlist.

## 3. Diagnostic Browsing

The log schedule page opens in time browsing with adjacent ten-minute windows and a refresh action. The date picker is a draft; loading commits the displayed center and exporting uses that center. Ordinary windows expose their screenshots in capture order and select the frame nearest the center. The API returns at most the latest 1000 logs with an explicit truncation flag; exports retain the complete window. Error archives use a separate tab and keep their original merged bounds and saved evidence.

`GET /diagnostics/timeline?at=<milliseconds>` returns `logs`, `screenshots` (relative paths), and `truncated`. The existing log-read credential boundary applies. The [shared loader decision](../../.agents/notes/implemented/simplification/2026-10-10-log-window-navigation.md) records implementation and verification.

## 4. Subsystem Invariants

- **[INV-UI-12] Log Window Cohesion**: Displayed logs, screenshot navigation and export share one loaded time window or error archive; date drafts and superseded requests never replace that source, and failed source changes expose no stale evidence.

- **[INV-WEB-01] Local Log Read Boundary**: A WebView session without a configured token permits read-only log requests from loopback with valid browser origin metadata; remote and cross-origin requests are rejected, and AI chat and mutating endpoints retain their credential checks.

The [local log access decision](../../.agents/notes/implemented/bug-fix/2026-09-29-local-log-access.md) records the regression and verification.
