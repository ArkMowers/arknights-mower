---
title: Dormitory and Group Shift Planning
status: implemented
category: bug-fix
date: 2026-10-01
---

Bed takeover and rescue standby eligibility follow [priority-aware dormitory recovery](../simplification/2026-10-02-priority-aware-dorm-recovery.md), which supersedes unconditional bed retention described here.

# Dormitory and Group Shift Planning

[English](2026-10-01-dormitory-and-group-shift-planning.md) | [中文](2026-10-01-dormitory-and-group-shift-planning.zh.md)

## Contract

[INV-SCHED-13] Dormitory Candidate Consistency: Idle Dormitory Recovery planning and selection share eligibility, reservations, and known/unknown mood classification; unknown readings never establish full recovery, and completed crafting replans recovery after actual staff restoration.

[INV-SCHED-14] Complete Group Replacement Matching: A grouped shift considers all eligible replacement assignments and accepts a complete matching whenever one exists; insufficient replacements or beds preserve the group's original arrangement.

The unified dormitory policy plans primary group recovery before idle vacancy filling. Rescue retains occupied unfinished recovery beds and fills only remaining unreserved vacancies; main-plan rescue identities and backup conditions retain their alpha contracts. Metadata rebuilding preserves only nonempty vacancy-fill tasks whose changed slots remain vacant. Due dormitory release tasks complete their own arrangement without inline crafting. Crafting rechecks configured recipe scope, enablement, and available stock before operator movement. Queue admission and dispatch share diagnostic reasons: insufficient or unread mood, protected recovery, task reservations, disabled settings, disallowed recipe scope, missing stock readings, ingredient reserves, output caps, and missing deer material combinations. Logs name the operator and blocking condition; stock failures include the affected material and available quantity. Successful restoration consumes the completed first workshop task by identity before observation; other pending tasks still block a fresh scan.

Normal planning and successful crafting restoration share `_plan_dorm_recovery`. The completed batch restores staff once, reads actual recovery times, refreshes idle-candidate search, and replans primary recovery before ordinary filling. Enabled Idle Dormitory Recovery does not wait for the five-minute automatic crafting window. Failed restoration does not plan from speculative positions. Ordinary individual releases use each resident's measured completion deadline; both single and merged dispatch recheck identity and postpone unfinished recovery without changing other residents' releases. Mandatory personal-limit releases retain advance scheduling around blocking tasks.

Ordinary vacancy fillers and idle replacements do not enroll in protected recovery batches, including when rescue starts after admission. Shift projection and actual room readback share the admission rule for `Operator.temporary_dorm_fill`; merged shifts retain ordinary fill origins, including unresolved game-selected candidates. Repeated reads and ordinary rearrangements preserve the marker, while formal off-shift admission and departure clear it. Operator rebuilding and runtime snapshot restoration preserve the admission distinction without altering the live state. Saved ordinary fillers retain their ability to yield beds after restart; formal recovery residents remain protected. Legacy snapshots without the marker default to formal recovery. Restart tests serialize the actual snapshot and execute startup restoration before checking identity, mood, bed deadline, and takeover eligibility.

Grouped shifts use `match_replacements` to retain a feasible first choice and reassign shared replacements when later members have fewer options. Each eligible group is attempted once per planning pass and recomputed on the next pass; a full member cannot suppress a later eligible member's attempt. Dispatch converges subsequent shifts, backup conditions, corrections, and final filling on a copy before the actual arrangement.

Exhausted-group support first computes the maximum matching of free replacements, coordinates only unmatched members, and recomputes the group after each support arrangement. Bed coordination requires a complete replacement matching. Failure diagnostics report the actual unmatched count and available candidates.

The [shared candidate decision](../simplification/2026-10-01-idle-dorm-candidate-pipeline.md) owns the simplification evidence. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md), [coding standards](../../../../CODING_STANDARDS.md), and [review checklist](../../../skills/mower-code-review/references/invariants-checklist.md) register the permanent rules.

## Verification

Offline regressions cover unknown versus verified readings, plan/selection reservation agreement, true-vacancy filling during rescue, formal occupied-bed protection, temporary fillers yielding beds, independent crafting and material readiness, post-crafting replanning, individual recovery deadlines, the logged perception-group replacement conflict, infeasible matching, and shift convergence. Device operations and external data reads use test doubles. Lost-return regressions retain real primary recovery and metadata rebuilding while mocking only card observation, so repeated planning verifies exactly one return at the effective limit.

The 79 focused selection, dormitory, shift, crafting, restart, and governance suites pass 2,168 tests and 22 subtests. Diagnostic regressions distinguish unavailable operators from material shortages and preserve ready recipes among blocked recipes. The real log-access regression binds only the request-serving method to its fixture stream, leaving the background log consumer on the original stream. Its client reads fragmented handshake bytes so a coalesced first log frame cannot remain queued in the test client handshake parser. Authentication, exact payload checks, and receive deadlines remain unchanged. The three governance gates and Ruff pass. Complete and maximum partial matching agree with an independent solver across all 65,536 four-by-four candidate graphs.

## Standards Findings

Pass. The change preserves device and configuration invariants, uses transient dormitory admission state, shares candidate and replacement rules, and synchronizes the glossary with explicit user approval. Ruff and the governance gates pass.

## Spec Findings

Pass. Primary recovery precedes ordinary dormitory work and automatic crafting. Due vacancy filling rechecks primary demand while preserving partial arrangements and retry compensation. Candidate selection verifies unknown mood, group matching reassigns shared replacements, and ordinary filler projections retain their ability to yield beds. Actual replacement or bed shortages reject the complete group.
