---
title: Training Name Decoration Isolation
status: implemented
category: bug-fix
date: 2026-10-09
---

# Training Name Decoration Isolation

[English](2026-10-09-training-name-decoration.md) | [中文](2026-10-09-training-name-decoration.zh.md)

## Contract

**[INV-REC-09] Training Name Decoration**: Training name recognition excludes separable leading yellow-white decoration using observed text geometry, preserves complete names, and retains the existing unknown-name matching threshold.

## Evidence and implementation

The October 9 scheduling archive shows Ulpianus in the training selection list while `operator_list_train` returns an empty name for his card. Both training attempts terminate at the list boundary. The yellow-white decoration joins the name during dilation and shifts template normalization. The original JPEG fixtures preserve the [first page](../../../../arknights_mower/tests/fixtures/selection/training_ulpianus_first_20261009.jpg) and the [final scrolled page](../../../../arknights_mower/tests/fixtures/selection/training_ulpianus_scrolled_20261009.jpg).

The training name processor detects yellow pixels at the leading edge and locates separated text in the upper half of the name strip before full-height normalization. It clears only pixels preceding that observed text boundary. It does not use a fixed-width name crop, operator-specific rules, new models or a lower matching threshold. Inseparable content retains the existing matcher and unknown-name behavior.

Pre-flight simplification finds no redundant abstraction: `operator_list_train` serves scanning and verification through the shared name matcher. The correction stays inside its existing name processor without another recognition or retry path. Recognition-only changes require no glossary updates.

## Verification

[Offline regressions](../../../../arknights_mower/tests/training_name_decoration_tests.py) replay the original JPEG pages, check both name rows, preserve long names and unknown-name rejection, and verify that input Capture Frames remain unchanged. Real training scans select the observed card in medium, high and xhigh modes with offline input and observation substitutes. Existing name normalization and training selection suites cover the adjacent contracts.

Differential replay of all 17 logged training selection frames recovers Ulpianus in every frame and preserves the other 121 name/scope pairs. The two retained fixtures match Ulpianus above 0.84 after normalization; the matching threshold remains 0.60. The focused recognition, training selection, page search, page identity and governance suites pass 143 tests and 21 subtests on the updated alpha baseline. Changed Python files pass Ruff lint and format checks, and all repository governance gates pass with two existing historical-reference compatibility warnings. Verification uses archived frames without a live device.

## Standards Findings

PASS: The correction stays inside the shared training name processor, changes no scheduling mechanics or device resources, and registers its invariant in the subsystem specification, coding standards and review checklist.

## Spec Findings

PASS: Both supplied failed-search pages recognize and select Ulpianus. Long-name and unknown-name controls pass without a fixed-width crop or threshold change; all other logged training name/scope readings remain unchanged.
