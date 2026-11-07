---
title: Stable Selection Border Geometry
status: implemented
category: bug-fix
date: 2026-09-30
---

# Stable Selection Border Geometry

[English](2026-09-30-selection-border-geometry.md) | [中文](2026-09-30-selection-border-geometry.zh.md)

## Contract

- **[INV-REC-04] Selection Border Geometry**: The [selection verification contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) owns card geometry, dim-border recognition, small right-edge cuts and recovery for substantial clipping or ambiguous evidence.
- **[INV-REC-02] Occluded Operator Selection**: Neighboring borders cannot confirm an unselected card; an obscured upper border requires both vertical borders and the leading portion of the lower border.

## Evidence and implementation

The supplied scheduling archive shows seven selection failures from 22:23:05 through 22:27:36 while assigning Purestream and Spot to Manufacturing Station 2. The [captured frame](../../../../arknights_mower/tests/fixtures/selection/right_edge_spot_20260930.jpg) shows Spot selected at the right edge and Purestream unselected below. Name segmentation widens their shared name boundary from 1902 to 1912 after selection. Adding the former 14-pixel margin exceeds the 1920-pixel Capture Frame width, so both cards receive an unknown selection state. Spot's shadow also lowers the brightness of its blue border below the previous mask threshold.

`agent_card_selected` anchors normal card width to the name region's left edge and the fixed Capture Frame layout. Its normal-card blue mask accepts brightness values from 140 while retaining hue, saturation, and border coverage requirements. Training-card geometry and its brightness threshold remain unchanged. Small right-edge cuts use the actual visible borders; substantial clipping or ambiguous evidence still returns an unknown state. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) owns the permanent recognition rule.

Pre-flight simplification finds no redundant production abstraction in this path. The shared detector serves both scan modes and roster verification; the correction stays inside that detector and adds no selection retries or alternate state.

## Verification

[Offline regression tests](../../../../arknights_mower/tests/selection_border_geometry_tests.py) cover real name segmentation and border detection, both scan modes clicking only Purestream, roster verification selecting only Spot, dim borders at normal and right-edge positions with widened name regions, and genuinely clipped cards. A 128-case matrix covers all adjacent selected-neighbor combinations with bright and dim borders, normal and training cards, and notice occlusion. Blue portrait content does not count as a border. Existing normal, training, notice occlusion, and neighboring-border tests protect the other selection paths.

Differential replay against the alpha detector preserves all 2,192 unselected and 212 selected card observations. The 14 newly recognized selected observations all belong to Spot; no unselected observation changes to selected.

All seven captured failure frames replay with Spot selected, Purestream unselected, and no unknown card borders. The focused selection and governance suites pass 270 tests and four subtests.

## Further right-edge evidence

The [dormitory frame](../../../../arknights_mower/tests/fixtures/selection/dorm_right_edge_20261010.png) and [manufacturing frame](../../../../arknights_mower/tests/fixtures/selection/manufacturing_right_edge_20261010.png) retain stable rightmost name positions at 1725 and 1726 after release. The expected border region exceeds the 1920-pixel Capture Frame by eight and nine pixels. Both rooms start at the same column positions, so this evidence does not establish a facility-specific layout offset. The manufacturing probe calls the release's original selection-page and no-inertia gestures through MuMu IPC; its short diagnostic distance is deliberately chosen and does not establish which normal gesture produced the reported failure.

Complete-card border processing and selection timing remain unchanged. The detector handles small cuts in its existing out-of-bounds branch; the ordinary name segmenter also retains an open terminal band within the same geometry. It reuses [INV-REC-04] rather than creating another guarantee. Under [INV-06], operator identity, selection state and Capture Frame meaning remain stable, so the glossary needs no edit. Unknown-state scan failures log the operator name, name scope, frame dimensions and training-layout flag before existing recovery.

[Right-edge regressions](../../../../arknights_mower/tests/selection_right_edge_tests.py) use real name recognition on both lossless captured frames. Constructed selected cases translate the archived Spot/Purestream image and supply its known shifted name scopes, isolating border detection from name recognition. Both scan modes preserve Spot, click only Purestream, and retain their existing observation and wait counts. Roster verification accepts Spot without additional observations. Bright and dim borders, the small-cut boundary, substantial clipping, notice occlusion, a colored screen edge and neighboring borders retain their required states. Selected clipping is verified by constructed cases; a complete live scheduling task is not run.

The focused right-edge, existing geometry, training, tail-rebound, page-observation, delayed-frame and page-identity suites pass 357 tests. Ruff lint and formatting checks pass. Syntax-tree comparison confirms unchanged complete-card processing and unchanged swipe, page-observation and roster-verification methods. Standards and requirement review confirms the existing recovery and input-timing boundaries; structural governance checks pass with two existing archived-reference warnings.

Review replay using the actual name reader exposes another small-cut failure in the constructed selected frames. Translating the archive by thirteen or fourteen pixels removes the selected name band's closing black-to-white transition at the canvas edge. The reader returns ten cards instead of twelve; both scan modes retain the target without selecting it, and roster verification exhausts its observations. Restoring only the last two pixels of the segmentation row recovers Spot and Purestream with their correct border states, isolating the missing terminal boundary from name-template matching. This is constructed archive evidence, not a new captured selection failure.

The terminal-band repair follows the [selection contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) and keeps complete bands, reduced scanning and training on their existing paths. A glyph contour touching the new right crop boundary remains unknown. A rendered Spot name with seven pixels removed still matches Spot without that contour check; the guarded real reader and both callers reject the incomplete identity.

The additional real-reader regressions verify both scan modes and roster verification without injected name scopes or a replaced page observer. Thirteen of the first sixteen focused cases fail before the repair and all sixteen pass afterward; five further cases cover clipped glyphs and a dark page without a terminal start. The combined ten-file selection and name-recognition suite passes 413 tests. No live-device task is run. The existing owning triplet and invariant remain unchanged in lifecycle and meaning.

## Standards Findings

PASS: The shared detector remains the single selection-state implementation. The change introduces no device operations, persistent state, unbounded retries, or new domain terms. Governance, relative links, and glossary alignment pass.

## Spec Findings

PASS: Captured-frame recognition, both scan modes, and roster verification satisfy [INV-REC-04]. Existing training-card, notice-occlusion, neighboring-border, and delayed-selection tests preserve [INV-REC-02] and bounded recovery. Verification uses offline frames and mocked controls.
