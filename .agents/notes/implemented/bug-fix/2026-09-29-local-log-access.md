---
title: Local log access without a configured token
status: implemented
category: bug-fix
date: 2026-09-29
---

# Local log access without a configured token

The shared WebSocket credential check rejects local log subscriptions without a token. The frontend also skips the connection when its URL has no token. Both behaviors prevent the local WebView from showing real-time logs in that state.

The desktop launcher keeps its runtime credential and loopback binding. Read-only log requests use the loopback and browser-origin boundary when no Web UI token is configured. AI chat, AI analysis, and mutating endpoints retain credential checks. Source-file access remains restricted by the existing allowlist. The shared WebSocket guard remains necessary for AI chat; a route-specific local log exception keeps the two access rules explicit.

[INV-WEB-01] Local Log Read Boundary is specified in the [Web Access contract](../../../../docs/subsystems/web-access.md). Offline tests cover tokenless local log streaming and HTTP reads, cross-origin and remote rejection, configured-token behavior, and frontend connection setup.
