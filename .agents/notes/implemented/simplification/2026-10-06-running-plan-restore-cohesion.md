---
title: Running Plan Restore Cohesion
status: implemented
category: simplification
date: 2026-10-06
---

# Running Plan Restore Cohesion

## Contract

[INV-CFG-02] binds restoration of the Scheduling Plan to its startup advanced-settings snapshot. Successful restoration persists both models, preserves unrelated configuration and reloads both frontend stores before autosave resumes. Validation and write failures retain the previous models and files.

## Simplification Audit

`restore_running_plan` has one production caller in `Plan.vue`. Its explicit advanced-settings replacement retains imported settings even when the associated plan is restored. Removing this exception reuses `export_advanced_settings` and `apply_advanced_settings`; no separate setting history or new transaction abstraction is introduced.

`build_global_plan(include_source=True)` captures the actual configuration's advanced settings independently of the editable plan. Restoration rejects a snapshot without those settings. The endpoint validates before writing and compensates failed writes with the original file bytes under the existing configuration lock. Frontend restoration reads configuration before the plan; failed reads retain the autosave pause and request a page refresh.

## Verification

`restore_running_plan_tests.py` covers startup configuration independent of stale plan metadata, restoration of imported settings, preserved unrelated settings, invalid or unavailable snapshots and compensated failures before and after either file write. `configBackup.test.js` covers paired frontend reload before autosave resumes.

## Standards Findings

Pass. [INV-CFG-02] is registered in the subsystem specification, coding standards and review checklist. Restoration uses the existing configuration lock and advanced-settings functions. Unrelated configuration and the immutable source snapshot remain unchanged. Note, link and controlled-language checks pass; existing domain definitions cover this interface correction.

## Spec Findings

Pass. A startup threshold of 150 and interval of two hours replace imported values of 20 and three hours on restoration. Both files persist restored settings; either write failure retains the prior models and original file bytes. The actual page handler reloads both stores before resuming autosave and keeps autosave paused after a read failure. The focused backend suites pass 101 tests and four subtests; the frontend suite passes 14 tests.
