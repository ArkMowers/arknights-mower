---
title: Frontend navigation and API dispatch
status: implemented
category: bug-fix
date: 2026-10-12
---

# Frontend navigation and API dispatch

`/mastery-recommendation` belongs to both Vue and the JSON API. A successful API response bypasses the existing 404 page fallback and appears as raw JSON on refresh. The earlier page-refresh test excludes this collision. No existing active decision owns this dispatch boundary.

[INV-WEB-04] Frontend Navigation Dispatch is specified in the [Web Access contract](../../../../docs/subsystems/web-access.md#6-frontend-navigation). Known page navigation is resolved before API dispatch using the existing route manifest. API clients retain their route handlers, and cache variants distinguish navigation from API requests.

The complexity assessment finds one manifest reader in `server.not_found` and no redundant public abstraction. Shared manifest and navigation predicates keep the new dispatch check and existing 404 fallback aligned. The process loads the immutable route set at startup; request dispatch never opens the manifest, preserving memory-only screenshot previews. Domain concepts, configuration schemas, device control and scheduling remain unchanged; no glossary edit is needed.

Focused verification in `arknights_mower/tests/web_routing_tests.py` covers every manifest page, the overlapping API, GET and HEAD, query strings, case, trailing slashes, request metadata, cache variants, non-read methods and preserved 404 responses. The original implementation fails the navigation and cache-variant regressions. The repaired routing suite passes all 10 tests; the governance suite passes 27 tests and `npm test -- src/routes.test.js` passes the manifest consistency test. `python scripts/verify_governance.py` passes its structural checks with two existing archived-reference warnings.

Standards review confirms shared request predicates and no glossary or persistence changes. Requirements review confirms dispatch through Flask's real request hooks, preserved API responses and focused coverage for all 17 manifest pages. Packaged desktop browser refresh remains a manual verification step.

The CI follow-up reproduces the screenshot preview failure caused by per-request manifest reads. After moving loading to startup, `pytest arknights_mower/tests/screenshot_tests.py arknights_mower/tests/web_routing_tests.py -q` passes 78 tests, including request dispatch with manifest reads forbidden. Existing screenshot assertions remain unchanged.
