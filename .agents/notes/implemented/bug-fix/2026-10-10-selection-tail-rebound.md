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

The [selection contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) owns the operational boundary. A shared tail check reuses recognized name scopes and inspects only the remaining name bands. Existing bounded observation handles post-release movement; no new polling policy, capture worker, configuration field or gesture is introduced. Pre-flight assessment retains `AgentPageObservation` and the common page observer because their callers require frame ownership and coordinate stability. The repair changes neither Capture Frame meaning nor Instance Binding; glossary definitions remain valid.

## Verification

[Tail regressions](../../../../arknights_mower/tests/selection_tail_rebound_tests.py) exercise the production scan path with original-frame evidence and simulated post-release positions, both fast modes, both layouts and reduced scanning. They cover continuous rebound, failure to settle, a disappearing target, cancellation and unchanged held-frame reuse on ordinary pages. Slower modes require their full fresh-frame stability count even when the first released frame matches the held position.

The focused tail, held capture, page search, observation, delayed-frame, page identity, legacy performance, game performance and governance suites pass 269 tests. Ruff checks pass. `python scripts/verify_governance.py` passes with two pre-existing missing-suite warnings in one archived record. Tests use offline substitutes for release and rebound; the captured incident supplies real image recognition evidence, not a live input replay.

The remote `alexsun` instance reloads the matching patched source through its registered single-instance restart operation. Its new process is ready, the HTTP status remains `stopped`, and the manager and other instance processes retain their original process IDs. No live game inputs are executed for verification.

## Standards Findings

PASS: Review covers the working-tree diff and untracked tests, fixtures and triplet against the remote runtime baseline `581221310`. The check reuses the existing page observer and one-shot observation, leaves touch acquisition and release unchanged, and adds no persistent state or glossary definition. The independent coordinate-validity guarantee has all three required registrations.

## Spec Findings

PASS: Blank-tail held frames cannot supply fast click coordinates or count as slow-profile stability evidence. Moving, absent and cancelled targets do not produce stale clicks. Ordinary filled pages retain held-frame reuse, and rebound observation sends no additional swipe. Native runtime verification remains limited to loading the repaired module and service readiness.
