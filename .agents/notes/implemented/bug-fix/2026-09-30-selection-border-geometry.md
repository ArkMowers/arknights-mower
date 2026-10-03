---
title: Stable Selection Border Geometry
status: implemented
category: bug-fix
date: 2026-09-30
---

# Stable Selection Border Geometry

[English](2026-09-30-selection-border-geometry.md) | [中文](2026-09-30-selection-border-geometry.zh.md)

## Contract

- **[INV-REC-04] Selection Border Geometry**: Normal operator card borders remain anchored to card geometry when a selected border widens the recognized name region; dim blue borders preserve selection, and genuinely clipped or ambiguous borders retain bounded recognition recovery.
- **[INV-REC-02] Occluded Operator Selection**: Neighboring borders cannot confirm an unselected card; an obscured upper border requires both vertical borders and the leading portion of the lower border.

## Evidence and implementation

The supplied scheduling archive shows seven selection failures from 22:23:05 through 22:27:36 while assigning Purestream and Spot to Manufacturing Station 2. The [captured frame](../../../../arknights_mower/tests/fixtures/selection/right_edge_spot_20260930.jpg) shows Spot selected at the right edge and Purestream unselected below. Name segmentation widens their shared name boundary from 1902 to 1912 after selection. Adding the former 14-pixel margin exceeds the 1920-pixel Capture Frame width, so both cards receive an unknown selection state. Spot's shadow also lowers the brightness of its blue border below the previous mask threshold.

`agent_card_selected` anchors normal card width to the name region's left edge and the fixed Capture Frame layout. Its normal-card blue mask accepts brightness values from 140 while retaining hue, saturation, and border coverage requirements. Training-card geometry and its brightness threshold remain unchanged. Actual clipping still returns an unknown state. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent recognition rule.

Pre-flight simplification finds no redundant production abstraction in this path. The shared detector serves both scan modes and roster verification; the correction stays inside that detector and adds no selection retries or alternate state.

## Verification

[Offline regression tests](../../../../arknights_mower/tests/selection_border_geometry_tests.py) cover real name segmentation and border detection, both scan modes clicking only Purestream, roster verification selecting only Spot, dim borders at normal and right-edge positions with widened name regions, and genuinely clipped cards. A 128-case matrix covers all adjacent selected-neighbor combinations with bright and dim borders, normal and training cards, and notice occlusion. Blue portrait content does not count as a border. Existing normal, training, notice occlusion, and neighboring-border tests protect the other selection paths.

Differential replay against the alpha detector preserves all 2,192 unselected and 212 selected card observations. The 14 newly recognized selected observations all belong to Spot; no unselected observation changes to selected.

All seven captured failure frames replay with Spot selected, Purestream unselected, and no unknown card borders. The focused selection and governance suites pass 270 tests and four subtests.

## Standards Findings

PASS: The shared detector remains the single selection-state implementation. The change introduces no device operations, persistent state, unbounded retries, or new domain terms. Governance, relative links, and glossary alignment pass.

## Spec Findings

PASS: Captured-frame recognition, both scan modes, and roster verification satisfy [INV-REC-04]. Existing training-card, notice-occlusion, neighboring-border, and delayed-selection tests preserve [INV-REC-02] and bounded recovery. Verification uses offline frames and mocked controls.
