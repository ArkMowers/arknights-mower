---
title: Estimated Idle Replacement
status: implemented
category: bug-fix
date: 2026-10-02
---

# Estimated Idle Replacement

## Contract

[INV-SCHED-13] shares eligible low selection-card estimates between candidate screening and vacant-bed selection. For unfinished residents, an estimate does not independently authorize occupied-bed replacement. An eligible registered applicant whose valid scheduling mood is below its own cap may replace a measured-full dynamic resident, including one retained for full occupancy, under [Protected Recovery Beds](../../../../docs/subsystems/base-scheduler.md#protected-recovery-beds). Unknown candidates require selection-page confirmation; estimates never establish measured mood or recovery deadlines. Ordinary release, exclusions, reservations and mandatory personal limits retain their own admission rules.

The [protected-bed decision](2026-10-09-protected-dorm-bed-tiers.md), under [INV-SCHED-43], supersedes this record's former guarantee that a low estimate bypasses completed-resident retention. Estimated candidates in the first four protected tiers retain legal lower-tier takeovers. Standby and ordinary replacement applicants require valid current mood no greater than 80% of their own upper limit; same-tier takeovers of unfinished residents remain denied.

## Historical Failure Boundary

The original repair connects low-estimate screening and unknown selection after an exhausted search. The shared estimate subset remains active, but an unknown or invalid estimate does not release a retained resident. Valid low estimates use the shared scheduling-mood rule for completed dynamic residents; they do not establish measured mood or recovery timing. Selection consumes the subset after vacancy or release admission; tier-aware takeover uses the shared protected-bed predicate.

The [classification audit](../simplification/2026-10-02-estimated-idle-candidate-classification.md) records the simplification. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent behavior. Existing glossary definitions remain accurate.

## Verification

Offline tests verify that registered and unregistered low-card candidates, with active or exhausted search and either idle-release switch setting, permit registered candidates to replace measured-full dynamic residents without establishing measured mood. Unregistered names still wait for an independently admitted release and selection-page registration. Negative cases cover expired, future and full estimates, working and reserved candidates, blacklists, estimates at personal caps and unfinished residents. Planning preserves operator samples and bed deadlines. The real dormitory 3 arrangement entry confirms the admitted release and fill rather than skipping an unchanged roster.
