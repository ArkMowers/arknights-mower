---
title: Training Name Decoration Isolation
status: implemented
category: bug-fix
date: 2026-10-09
---

# Training Name Decoration Isolation

[English](2026-10-09-training-name-decoration.md) | [中文](2026-10-09-training-name-decoration.zh.md)

## Contract

**[INV-REC-09] Training Name Decoration** follows the [training recognition contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants). The user-configured Special Focus marker can appear on any operator.

## Evidence and implementation

The October 9 scheduling archive shows Ulpianus in the training selection list while `operator_list_train` returns an empty name for his card. Both training attempts terminate at the list boundary. The Special Focus graphic joins the name during dilation and shifts template normalization. The original JPEG fixtures preserve the [first page](../../../../arknights_mower/tests/fixtures/selection/training_ulpianus_first_20261009.jpg) and the [final scrolled page](../../../../arknights_mower/tests/fixtures/selection/training_ulpianus_scrolled_20261009.jpg).

The training name processor detects the marker's yellow pixels at the leading edge. For marked cards, it right-aligns the observed name region and existing training templates, retaining the five-pixel dilation margin. It removes leading decoration only when upper-half geometry separates it from the complete name. Overlapping decoration remains in the observed region; right alignment preserves the name's position without cutting at hyphens or middle dots. The matching threshold remains 0.60. Unmarked training cards and ordinary selection retain their existing alignment. The bounded name cache distinguishes alignment modes, resource reload clears it, and model arrays remain unchanged.

Pre-flight simplification finds no redundant abstraction: `operator_list_train` serves scanning and verification through the shared name matcher. The correction stays in these existing processors without another recognition or retry path. This extension reuses the owning triplet and `[INV-REC-09]`. Recognition-only changes require no glossary updates.

## Verification

[Offline regressions](../../../../arknights_mower/tests/training_name_decoration_tests.py) replay the original JPEG pages and verify that input Capture Frames remain unchanged. Rendering the archived marker with all 432 existing training name templates preserves every full name, including Chinese names, Latin letters, hyphens and middle dots. A separate 38-case matrix covers 19 names in both rows. These rendered cases expand coverage; the real screenshots provide evidence for Ulpianus only.

Actual `BaseMixin.scan_agent` calls select Ulpianus from both archived pages in medium, high and xhigh modes. Another 24 cases select four different marked operators across both rows and all three modes. Inputs and observations use offline substitutes. Unknown-name rejection and [name cache reload](../../../../arknights_mower/tests/name_template_cache_tests.py) controls pass.

Differential replay of all 17 logged training selection frames against the alpha baseline recovers Ulpianus in every frame and preserves the other 121 name/scope pairs. The focused recognition, training selection, page search, page identity, resource reload and governance suites pass 213 tests and 453 subtests. Changed Python files pass Ruff lint and format checks. Repository governance gates pass with two existing historical-reference compatibility warnings. Verification uses archived and rendered frames without a live device.

## Standards Findings

PASS: The correction stays inside shared recognition, changes no scheduling mechanics or device resources, and keeps one owning record and invariant. Alignment does not mutate shared models, and resource reload invalidates cached names.

## Spec Findings

PASS: Both supplied failed-search pages recognize and select Ulpianus. All rendered training names and the additional operator scans pass. Unknown names remain rejected at the existing threshold; other archived training name/scope readings remain unchanged.
