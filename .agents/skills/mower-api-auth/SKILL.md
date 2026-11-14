---
name: mower-api-auth
description: Use when adding, changing or reviewing an Arknights Mower HTTP route, WebSocket or other remotely callable backend interface. Decide whether the Web UI token is required and verify the chosen boundary with focused tests.
---

# Mower API Authentication

## Scope

Apply this skill to every new or changed remotely callable backend interface, even when the requested change does not mention authentication. Read the affected subtree instructions and the [Web Access contract](../../../docs/subsystems/web-access.md) before choosing the boundary. Existing sibling routes are evidence of project intent, not a substitute for evaluating the new interface.

## Authentication Decision

For each interface, identify its methods, callers, network exposure, returned data, accepted input, side effects and work it can trigger. Record one of these decisions in the task evidence before implementation or review completes:

- **Token required:** Use the existing Web UI token boundary when the interface reads non-public user, operational or diagnostic data; changes persisted or runtime state; controls automation, devices, processes or updates; accepts configuration, executable or uploaded content; accesses files; initiates network calls or material work; or otherwise exposes a capability that an untrusted network client must not invoke.
- **Contracted exception:** Leave an interface tokenless only when an owning contract explicitly defines it as public or grants a narrower boundary. State that source and verify every condition of the exception. A read-only method, loopback-oriented product flow, browser Origin check, CORS policy, frontend-only caller or neighbouring tokenless route does not by itself establish an exception.

Use the repository's existing enforcement point for the selected boundary: `@require_token` for ordinary protected HTTP routes, the established WebSocket authorization helper for WebSockets, and `@require_log_read` only for the contracted local log-read exception. Do not create a second token comparison or weaken the configured-token behavior. Authentication is separate from input validation, confirmation, rate limiting and authorization for a specific operation; retain those controls when they are also required.

## Verification

Add focused offline tests beside the owning route tests.

1. For a protected interface, verify that a missing and an invalid token are rejected before parsing, persistent writes, process or device actions, filesystem access, network calls or other material work. Verify the current instance token reaches the intended success or validation path.
2. For a contracted tokenless exception, verify its complete boundary. Local log-read exceptions cover the relevant loopback, Host and browser-origin conditions and reject remote or cross-origin requests; configured-token sessions still require the credential.
3. For route groups or multiple methods on one path, exercise every method and representation whose boundary can differ. Frontend page navigation and JSON API dispatch remain distinct where the Web Access contract says so.

Review the final diff for every added or changed route registration and authorization decorator. Report the decision, contract source and focused tests for each interface; an omitted decision is an unresolved review finding.

## Completion

Every added or changed remotely callable interface has an explicit, evidence-backed authentication decision, uses the existing enforcement boundary and has focused tests proving both rejection and permitted access without unauthorized side effects.
