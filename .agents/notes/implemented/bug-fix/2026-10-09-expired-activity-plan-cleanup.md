---
title: Expired Source Plan Cleanup
status: implemented
category: bug-fix
date: 2026-10-09
---

[INV-MAA-06] confines expiry cleanup to the source weekly plan after successful automatic fallback selection. Expired activity selections are removed from each daily row; the destination, ordinary stages, still-open activity stages, row settings and inventory rules retain their values. An early custom switch does not remove still-open stages.

Selected activity stage end times are retained alongside existing plan expiry metadata. This supports cleanup after a newer resource generation removes old time windows. Plan edits discard cached codes no longer selected; absence of stage-specific evidence never permits guessed deletion. Cleanup removes obsolete plan-end metadata and retains remaining stage deadlines. The change uses the existing atomic weekly-plan writer and active-plan handoff.

Activity options, inventory suggestions and displayed plan-end metadata reload when the installed resource version changes. Metadata refresh preserves local rule drafts and selected stages. Latest activity and inventory requests discard late responses from superseded requests. Existing domain concepts remain unchanged.

Offline tests exercise persisted source-only cleanup, destination runtime selection, removed resource windows, early and delayed custom switches, failed target selection and unchanged inventory rules. Frontend tests exercise resource refresh, custom-time preservation, retry and stale-response rejection. The product adds no rule explanation.

Verification: 50 focused Python tests and 38 frontend tests pass. Standards review confirms atomic source-plan persistence, bounded stage metadata, preserved configuration ownership and unchanged domain concepts. Specification review confirms source-only cleanup after successful fallback, preserved custom-time precedence and resource-dependent UI refresh. Structural governance passes independently.
