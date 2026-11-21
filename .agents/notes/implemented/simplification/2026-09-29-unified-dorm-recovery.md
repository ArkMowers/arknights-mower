---
title: Unified dormitory recovery
status: implemented
category: simplification
date: 2026-09-29
---

# Unified dormitory recovery

## Contract

All scheduling uses one Dormitory Recovery policy. Retired experimental, workshop-rest-priority, initialization-restart, and backup-timing settings do not select alternate behavior. Older configuration files remain importable. Configuration and UI expose only active settings.

[INV-SCHED-07] Unified Dormitory Policy requires the same scheduling behavior regardless of retired mode keys. [INV-SCHED-02] preserves the Single-Target Recovery Target at its final slot throughout temporary selection and roster restoration. Preceding single-target providers and Fiammetta retain their positions regardless of mood. Other preceding slots retain full residents or use full eligible idle operators without single-target skills. Fullness uses valid measured mood first; otherwise an unexpired observed or sort-inferred card estimate of 24 counts as full without an extra numeric reading. Roster readback and confirmed full padding precede recording the assignment. Missing candidates or failed reads preserve the final roster and do not mark an unverified recovery assignment.

## Simplification evidence

The experimental flag selected parallel implementations throughout `base_schedule`, `operators`, and `scheduler_task`, with duplicate UI explanations and initialization paths. Removing these branches retains the converged shift planner, slot ownership checks, mood-limit releases, candidate exclusions, and deadline guards as the sole implementations. No constant-true compatibility mode remains.

Temporary padding slots remain Free until normal selection scans actual cards in descending mood order and chooses eligible idle green faces without single-target skills. Registration and cached mood are not prerequisites. The earlier filling-list reuse admitted inferred names from the complete operator catalog, including operators the account did not own. Candidate shortage now skips setup and allows the normal roster to complete. Full padding already in its preceding slot remains eligible for readback retries without moving other residents. These corrections preserve the glossary definitions and reuse [INV-SCHED-02] and [INV-SCHED-15].

The October 11 padding repair introduced `full_dorm_candidate` with a different evidence priority from ordinary candidate screening. A newer sort-inferred estimate selected its early-return branch but failed the observed-card tuple check, rejecting even an existing measured 24. The shared `dorm_candidate_mood` now supplies both checks, including the temporary selection snapshot. This correction reuses [INV-SCHED-02] and [INV-SCHED-15]; inferred values never populate measured samples or timestamps. Clearing selections and reselecting follows the existing workflow.

## Verification

Focused offline scheduling tests cover backup convergence, admission, initialization, charging, release deadlines, legacy configuration imports, and stable target placement, full padding, green-card confirmation, provider preservation and simultaneous low-mood fixed-cover arrivals. The earlier 21 focused scheduling, recovery, card, selection and page-search suites pass 862 offline cases, including visible unregistered green-card selection, multiple padding slots, unavailable-candidate fallback and confirmed-setup retries. Ruff, formatting, diff checks and the three governance gates pass; one existing Pydantic warning and two historical archived-reference warnings remain. Frontend configuration tests and a production build verify the removed controls and retained settings.

The October 12 mood-priority correction passes 353 cases across the six focused recovery, recording, initial-mood, card-mood and grouped-replacement suites. Regression cases exercise actual card scanning followed by temporary roster generation, observed and inferred caches, snapshot selection, measured-mood priority, expiry and future timestamps. The [incident record](../../../../docs/postmortem/2026-10-12-dorm-recovery-mood-priority.md) records remote evidence and introduction history.
