---
title: Estimated Idle Replacement
status: implemented
category: bug-fix
date: 2026-10-02
---

# Estimated Idle Replacement

## Contract

[INV-SCHED-13] shares eligible low selection-card estimates between candidate screening and vacant-bed selection. An estimate does not independently authorize occupied-bed replacement or clear full-occupancy retention. Unknown candidates require selection-page confirmation; estimates never establish measured mood or recovery deadlines. Ordinary release, exclusions, reservations and mandatory personal limits retain their own admission rules.

The [protected-bed decision](2026-10-09-protected-dorm-bed-tiers.md), under [INV-SCHED-43], supersedes this record's former guarantee that a low estimate bypasses completed-resident retention. Estimated candidates in the first four protected tiers retain legal lower-tier takeovers. Standby and ordinary replacement applicants require valid current mood no greater than 80% of their own upper limit; same-tier takeovers remain denied.

## Historical Failure Boundary

The original repair connects low-estimate screening and unknown selection after an exhausted search. The shared estimate subset remains active, but an estimate alone no longer releases a retained resident. Selection consumes the subset after vacancy or release admission; tier-aware takeover uses the shared protected-bed predicate.

The [classification audit](../simplification/2026-10-02-estimated-idle-candidate-classification.md) records the simplification. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent behavior. Existing glossary definitions remain accurate.

## Verification

Offline tests verify that registered and unregistered low-card candidates, with active or exhausted search and either idle-release switch setting, preserve full-occupancy retention until an independently admitted ordinary release. Selection then fills the vacancy without establishing measured mood. Negative cases cover expired, future and full estimates, working and reserved candidates, blacklists, mandatory limits and unfinished residents. Planning preserves operator samples and bed deadlines. The real dormitory 3 arrangement entry confirms the admitted release and fill rather than skipping an unchanged roster.
