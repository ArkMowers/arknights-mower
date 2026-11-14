---
title: Log forwarding with explicit credentials
status: implemented
category: bug-fix
date: 2026-10-10
---

# Log forwarding with explicit credentials

The frontend constructs `/log` from the browser origin, including its public port and `wss` for HTTPS. A proxy can terminate HTTPS or rewrite Host to an internal address. Comparing browser Origin with that backend address rejects a correctly authenticated log subscription.

The [Web Access contract](../../../../docs/subsystems/web-access.md) owns the interface and [INV-WEB-02]. The log route uses its explicit first-frame token as the authorization boundary, independently of Origin, Host and forwarded headers. This credential is not attached automatically by the browser. Tokenless local access retains [INV-WEB-01]; AI and diagnostic mutation routes retain their existing origin checks.

The pre-flight simplification audit retains the shared credential guard and leaves the origin parser unchanged for its other callers. The log route selects credential-only authorization through its existing route-specific flag. No additional proxy parser or configuration is introduced.

## Standards Findings

The change preserves the five-second credential deadline, bounded log subscriptions and tokenless loopback restrictions. It changes no domain definitions, configuration schemas, device lifecycles or scheduling mechanics.

## Spec Findings

Offline regression tests cover valid credentials with HTTPS termination, changed ports, rewritten Host, IPv6 and absent Origin. They reject missing and invalid credentials and tokenless access with forwarded headers, and preserve AI and diagnostic origin checks. A loopback WebSocket test exercises the production `/log` route with a public HTTPS Origin and internal HTTP Host, verifies initial history and receives a later log record. Frontend tests verify public WebSocket URLs and credential transmission on reconnect. Live frp or router deployment remains unverified.

Verification on the alpha-based PR checkout passes 54 targeted backend tests and 13 frontend tests. Ruff, Prettier and whitespace checks pass. Governance passes its three structural checks with two existing archived-reference compatibility warnings. Standards and specification review finds no actionable issues.
