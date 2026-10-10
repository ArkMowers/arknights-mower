---
title: Released Selection Tail Coordinates
status: implemented
category: bug-fix
date: 2026-10-10
---

# Released Selection Tail Coordinates

[English](2026-10-10-selection-tail-rebound.md) | [中文](2026-10-10-selection-tail-rebound.zh.md)

## Decision

[INV-REC-10] governs the validity of held selection coordinates at the list tail. [INV-DEV-24] continues to govern acquisition and touch release, as recorded by the [held capture decision](../../implemented/simplification/2026-10-09-held-swipe-capture.md). These are separate guarantees: successful capture and release do not establish that coordinates survive endpoint rebound.

The original [tail frame](../../../../arknights_mower/tests/fixtures/selection/tail_held_20261010.jpg) contains a correctly recognized Gladiia card and a blank right tail. The following archived selection shows selected Verdant after the logged click on Gladiia's held-frame coordinate. The [ordinary page](../../../../arknights_mower/tests/fixtures/selection/page_held_20261010.jpg) retains a partially visible rightmost card beyond the reduced recognition boundary. Both fixtures preserve the original JPEG bytes.

The later training-room incident supplies an original [held tail frame](../../../../arknights_mower/tests/fixtures/selection/training_tail_held_20261010.jpg) at 15:07:07.331 and a [filter-reset frame](../../../../arknights_mower/tests/fixtures/selection/training_tail_returned_20261010.jpg) at 15:07:08.647. The held frame recognizes Myrtle with a blank tail before the open profession sidebar. Including that dark sidebar in the training tail check hides the blank region. The logged click leaves Shu selected; the filter-reset frame does not recognize Myrtle behind the sidebar. These images preserve the original JPEG bytes. They establish the captured states, not the exact motion immediately after release.

This extension reuses [INV-REC-10] for tail coordinates and [INV-REC-05] for observed training identity. The incident also exposes an unconditional trainee exemption in both room retry and assignment readback: the actual Shu occupant is accepted for the named Myrtle target. Existing protection already expresses a frozen trainee as `Current`, so named targets can use the common roster comparison without relaxing training protection. The same decision triplet owns these connected selection and recovery failures.

The [selection contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) owns the operational boundary. A shared tail check reuses recognized name scopes and inspects only the remaining name bands. Existing bounded observation handles post-release movement; no new polling policy, capture worker, configuration field or gesture is introduced. Pre-flight assessment retains `AgentPageObservation` and the common page observer because their callers require frame ownership and coordinate stability. The repair changes neither Capture Frame meaning nor Instance Binding; glossary definitions remain valid.

## Verification

[Tail regressions](../../../../arknights_mower/tests/selection_tail_rebound_tests.py) exercise the production scan path with original-frame evidence and simulated post-release positions, both fast modes, both layouts and reduced scanning. They cover continuous rebound, failure to settle, a disappearing target, cancellation and unchanged held-frame reuse on ordinary pages. Slower modes require their full fresh-frame stability count even when the first released frame matches the held position.

Training regressions extend the actual scan path with the original training images and simulated released positions. [Training arrangement regressions](../../../../arknights_mower/tests/train_follow_correction_tests.py) exercise sidebar closure, named-target selection, room retry and assignment readback. They assert that wrong occupants do not complete a task, repeated failure retains the plan, matching occupants avoid reselection and frozen or free slots retain their semantics. The two extended suites pass 87 tests. The focused selection, training, protection, observation and held-capture checks pass 428 tests and 21 subtests, excluding the unrelated exhaustive name-template case. Ruff and governance checks pass; governance retains the two historical missing-suite warnings described below. The earlier 269-test result and remote reload describe the original repair.

The subsequent review reproduces an outdated [fast training search fixture](../../../../arknights_mower/tests/low_frame_rate_tests.py): the new sidebar check reaches a recognizer substitute without `find` before the end-page assertions run. The fixture now simulates open and closed training sidebars through the existing filter substitute. It verifies profession preservation and sidebar closure while retaining three swipes, four scans, held-frame ownership and rejection before final selection verification. The focused selection, training, observation, filter and protection checks pass 364 tests and 21 subtests. Ruff and governance checks pass with the same historical warnings. This repair changes only offline verification and its recorded evidence.

The focused tail, held capture, page search, observation, delayed-frame, page identity, legacy performance, game performance and governance suites pass 269 tests. Ruff checks pass. `python scripts/verify_governance.py` passes with two pre-existing missing-suite warnings in one archived record. Tests use offline substitutes for release and rebound; the captured incident supplies real image recognition evidence, not a live input replay.

The remote `alexsun` instance reloads the matching patched source through its registered single-instance restart operation. Its new process is ready, the HTTP status remains `stopped`, and the manager and other instance processes retain their original process IDs. No live game inputs are executed for verification.

## Standards Findings

PASS: Review covers the working-tree diff and untracked tests, fixtures and triplet against the remote runtime baseline `581221310`. The check reuses the existing page observer and one-shot observation, leaves touch acquisition and release unchanged, and adds no persistent state or glossary definition. The independent coordinate-validity guarantee has all three required registrations.

PASS: The training extension is compared with upstream alpha `2c1f68a7d4a9e811dd8d3e6a83bec5923ad4b1ae`, including unstaged changes and both untracked fixtures. It reuses the existing sidebar closure and room retry, with no new invariant identifier, lifecycle transition or domain definition. The earlier remote reload above applies only to the original repair; this extension has offline verification.

## Spec Findings

PASS: Blank-tail held frames cannot supply fast click coordinates or count as slow-profile stability evidence. Moving, absent and cancelled targets do not produce stale clicks. Ordinary filled pages retain held-frame reuse, and rebound observation sends no additional swipe. Native runtime verification remains limited to loading the repaired module and service readiness.

PASS: An open training sidebar does not suppress the blank-tail check, and target search exposes the rightmost names before scanning. Named trainee mismatches cannot complete room retry or assignment readback; bounded failure retains the plan. Locked, protected and unreadable trainee slots remain frozen by the existing room gate. The training extension has no live device replay or runtime deployment verification.
