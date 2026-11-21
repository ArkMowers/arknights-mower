---
title: Log window navigation and shared loading
status: implemented
category: simplification
date: 2026-10-10
---

# Log window navigation and shared loading

`LogSchedule.vue` has two log-loading paths, each with one template action caller. They duplicate loading, failure and stale-response handling. One loader accepts either a time center or an error archive and updates logs and screenshots together. The screenshot navigator uses the selected source list directly instead of a separate manual-image override.

Time browsing is the default two-column view. Adjacent ten-minute windows, refresh, an explicit loaded range and ordinary screenshot navigation make retained history accessible. Error archives use a separate tab with their existing deletion, export and AI actions. The navigation menu uses `TimeOutline` independently of the base report icon. Symmetric inline padding follows the content container from 16 to 40 pixels; the heading wraps to keep the return link visible when space is limited.

[INV-UI-12] Log Window Cohesion is specified in the [Web Access contract](../../../../docs/subsystems/web-access.md). A draft date never changes the loaded source or export center. Only the latest request commits data; switching sources clears old content, and failed reads expose an error without stale evidence. Log parsing follows the file formatter, including milliseconds and CRITICAL. The ordinary API exposes the screenshot list and truncation state while retaining its 1000-row display limit and complete export.

Offline frontend tests cover overlapping requests, draft/export isolation, window navigation, screenshot selection, failure, and parsing. A fixed current time keeps navigation fixtures in the past in both UTC and Asia/Shanghai; each test restores its clock spy. Backend tests cover the ordinary endpoint and multiline record boundaries. No scheduling mechanics, device lifecycle or persisted configuration changes occur.

## Standards Findings

PASS. The shared loader preserves [INV-UI-12], the read-only API retains [INV-WEB-01], and no glossary or persisted configuration change is required. Governance, focused unit tests and frontend lint pass.

## Spec Findings

PASS. Time navigation, ordinary screenshot browsing, correct log levels, source-consistent export and the distinct menu icon match the requested behavior. The redundant heading eyebrow is removed. Both tabs at 390, 900, 1200 and 1520 pixels retain the complete return link and have no horizontal overflow at 100% and 140% CSS zoom. The 19 focused frontend tests pass in UTC and Asia/Shanghai. Verification uses simulated logs and no live devices.
