---
title: Selection Page Exit
status: implemented
category: bug-fix
date: 2026-10-07
---

# Selection Page Exit

[English](2026-10-07-selection-page-exit.md) | [中文](2026-10-07-selection-page-exit.zh.md)

## Contract

- **[INV-REC-06] Selection Page Exit**: Known facility roster pages detected during anomalous selection readings abort selection inputs and page-local fallback; normal readings add no page-template lookup or capture.
- Normal selection readings add no page-template lookup or capture. Anomalous readings use the current Capture Frame and the existing facility roster marker.

## Evidence and implementation

The supplied October 7 archive shows selected Weedy and Purestream at 10:06:54.511. Logged inputs clear selection at `(729, 1026)` and click Purestream at `(672, 810)`. The [transition frame](../../../../arknights_mower/tests/fixtures/selection/room_roster_transition_20261007.jpg) at 10:06:55.446 and [settled frame](../../../../arknights_mower/tests/fixtures/selection/room_roster_20261007.jpg) at 10:06:56.005 show the facility roster panel. Both fixtures preserve the original JPEG bytes. Selection name bands on that panel produce empty names at x=1455, which the former verifier labels as left-side clipping.

The failure stack enters high-mode verification after the first reordered click. That branch contains no confirmation or return input. No such input is logged between the valid selection frame and page exit. The archive contains neither device configuration nor native input-delivery evidence, and contains no observation between clearing and the first reordered click. The trigger of the page exit remains unestablished. The reported device behavior establishes failures in high mode and successful selection in xhigh; medium and low remain untested on that device. This correction does not attribute exit to confirmation, coordinate conversion, clearing, or the cyan badge sensitivity described in the [previous decision](../../implemented/bug-fix/2026-10-07-selection-status-badge.md).

`check_agent_page` requests a same-frame `arrange_check_in_on` lookup only for empty pages, unknown names, missing scopes or clipped normal first columns. Read errors and unknown borders use the same exit check. A normal card page does not invoke it. `AgentSelectionPageChanged` propagates through scanning and both selection-local recovery catches; existing room recovery reads actual occupants and keeps its bounded retry policy.

Reordering retains the existing mode-specific input timing and verification. Clearing adds no observation or feedback check. High mode keeps its existing per-click verification; xhigh keeps its batch strategy. Empty-target callers retain their immediate return. The clear-stage log records the fixed performance mode, observed selection and target roster without a screenshot or template lookup.

Pre-flight simplification retains the existing reader, selection verifier, facility marker and room recovery. No full scene classification, new retry policy, device backend modification, persistent state or glossary change is required. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) owns the permanent interface rules.

## Verification

[Original-frame regressions](../../../../arknights_mower/tests/selection_page_identity_tests.py) cover settled and transitioning room panels in medium, high and xhigh modes, both card layouts, page search, scanning and roster verification. Detection stops after one anomalous reading without input or another observation. The valid original selection frame retains real name and border recognition and performs only the existing connection lookup.

[Reorder regressions](../../../../arknights_mower/tests/choose_agent_filter_tests.py) preserve the original high-mode verification count without a clear-feedback read, retain xhigh batch clicks and propagate page exit through both filter-reset catches. [Room recovery regressions](../../../../arknights_mower/tests/room_retry_dispatch_tests.py) verify actual-occupant readback without confirmation replay and pending-task retention after bounded repeated exit. All controls are offline substitutes.

The focused selection, performance, room recovery and governance suites pass 574 tests and four subtests. Repository Ruff lint, format and governance checks pass. The room-retry test fixture isolates automatic performance feedback so its failure cases do not leak a mode cap into later suites.

The facility marker produces no false match across 159 full selection pages from the supplied archive. This is an offline recognition check, not a reproduction of native input delivery or a live-device test.

## Standards Findings

PASS: The change reuses shared recognition and recovery boundaries, registers the invariant in all three governance locations, and adds no device operations or glossary wording.

## Spec Findings

PASS: The supplied wrong-page frames produce a structured page-exit error instead of clipping timeout. Reordering retains its original input and verification counts without a clear-feedback check. The initiating page-exit event remains outside the archive's evidence.
