---
title: Shadowed Training Column
status: implemented
category: bug-fix
date: 2026-10-12
---

# Shadowed Training Column

[English](2026-10-12-shadowed-training-column.md) | [中文](2026-10-12-shadowed-training-column.zh.md)

## Contract

**[INV-REC-13] Shadowed Training Column** follows the [training selection contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants). Name-field geometry comes from observed edges; operator identity comes from the existing template matcher.

## Evidence and implementation

The fui archive at 12:45 on October 12 contains Chestnut in both held and settled training selection frames. The held frame recognizes Chestnut. After release, the lower-right background falls below the segmentation threshold of 85, and the settled frame omits his field despite the complete visible name. Repeated searches end with the missing-operator warning. The fixtures retain only the two original RGB name bands, with no account panel: [held bands](../../../../arknights_mower/tests/fixtures/selection/training_chestnut_held_bands_20261012.png) and [settled bands](../../../../arknights_mower/tests/fixtures/selection/training_chestnut_settled_bands_20261012.png).

`operator_list_train` retains the existing segmentation for complete fields. An unmatched trailing leading edge borrows the complete opposite-row field bounds only in the rightmost column, with at most three pixels of leading-edge displacement. When those leading edges do not align, the preceding complete field in the affected row supplies its measured leading-to-right-edge width, and the inferred right edge must align with the other row's observed right edge within three pixels. The recovered field keeps its own row and displacement. All reference edges belong to the same Capture Frame; no held coordinates cross into a later observation. Template matching, Special Focus normalization, caches, inputs and observation timing retain their existing behavior.

The November 15 archive at 15:48 reproduces the omission with a working-status card above Chestnut. Its detected leading edge differs by ten pixels from the lower card, so the original leading-edge check rejects recovery. The lower row's preceding complete field supplies the width needed to recover Chestnut's field at x=1699–1874; the upper card's observed right edge at x=1876 independently confirms alignment. This extends the existing geometry decision without widening its three-pixel tolerance or reusing held coordinates. The new fixtures retain only the original [held bands](../../../../arknights_mower/tests/fixtures/selection/training_chestnut_working_held_bands_20261115.png) and [settled bands](../../../../arknights_mower/tests/fixtures/selection/training_chestnut_working_settled_bands_20261115.png).

Pre-flight simplification finds no redundant abstraction: the shared training processor serves both selection scanning and verification. The correction uses its existing row scan and name matcher without another detector or retry path. Recognition-only changes require no glossary update.

## Verification

[Offline regressions](../../../../arknights_mower/tests/training_tail_name_tests.py) replay the archived bands, cover the shadow in either row, preserve input pixels, reject absent peer geometry, misalignment and clipping, and retain unknown-name rejection. Scanner tests use the actual name processor with substituted inputs and observations in medium, high and xhigh modes. The held-to-settled path selects Chestnut at his fresh position after two observations without another swipe. Positive displacement controls retain each row's actual coordinates within the alignment tolerance.

The November replay additionally covers a working-status peer in either row, measured-width recovery with actual displacement, missing peer or same-row reference geometry, misaligned and clipped columns, and a recovered field with unknown text. The same held-to-settled scanner checks use the November bands in all three modes. On the pre-repair alpha commit, the final test cases produce eight failures and twenty passes; after the repair, all twenty-eight pass. Focused name recognition, cache, ROI, training-card, released-tail, page identity, page observation and search checks pass 269 tests, with the unrelated exhaustive name-template case deselected. No live device inputs are replayed.

## Standards Findings

PASS: The correction stays in the shared training processor, adds no configuration or resources, preserves the existing matching threshold and input pixels, and introduces no additional capture or input path. Changed Python files pass Ruff lint and format checks. The governance gate passes with two existing archived-reference compatibility warnings.

## Spec Findings

PASS: The new archived-frame regression fails before the correction and passes afterward. Focused recognition, name-cache, training-card, tail-release, page-identity, right-edge, ROI and governance tests pass 341 tests and 471 subtests. Differential replay of six existing training JPEG fixtures preserves all 35 previous name/scope pairs without additional detections. Verification uses offline frames and substituted device inputs only.
