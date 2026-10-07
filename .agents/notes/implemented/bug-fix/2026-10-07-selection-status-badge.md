---
title: Selection Status Badge Isolation
status: implemented
category: bug-fix
date: 2026-10-07
---

# Selection Status Badge Isolation

[English](2026-10-07-selection-status-badge.md) | [中文](2026-10-07-selection-status-badge.zh.md)

## Contract

- **[INV-REC-04] Selection Border Geometry**: Partial horizontal color from status badges and adjacent cards does not make a normal card unknown when both vertical borders and the leading lower border are absent. Real clipping, full horizontal-border evidence and ambiguous vertical-border evidence retain bounded recognition recovery.
- **[INV-REC-02] Occluded Operator Selection**: An obscured upper border still requires both vertical borders and the leading lower border to confirm selection.

## Evidence and implementation

The supplied October 7 scheduling archive contains eleven arrangement failures between 10:05:12 and 10:09:56. Ten corresponding archived frames show Purestream selected below an unselected Weedy; one shows a facility roster panel rather than the selection page. The [captured selection frame](../../../../arknights_mower/tests/fixtures/selection/purestream_badge_20261007.jpg) preserves the original JPEG bytes.

Direct JPEG replay already verifies Purestream before this correction. JPEG color changes and the absence of per-card border diagnostics prevent the archive from identifying the exact live unknown card. The frame nevertheless exposes a deterministic sensitivity: Weedy's cyan status badge contributes to the upper-edge blue mask, and Purestream's upper border contributes to the trailing lower-edge mask. Normalizing only the badge's cyan pixels raises upper coverage from approximately 16.8% to 21.1%; lower coverage remains 25%, while both vertical edges and the leading lower edge remain absent. The former detector returns unknown, and real roster verification reproduces the logged timeout with an empty last-read roster in both scan modes. This boundary regression supports the suspected failure mechanism without claiming a lossless replay of the live frame.

`agent_card_selected` classifies a normal card as unselected when both horizontal coverages are below 45%, both vertical coverages are below 20%, and leading lower coverage is below 20%. Existing positive selection checks run first. Training-card detection, frame bounds, name segmentation, observation timing and unknown-state recovery retain their existing contracts. `wait_for_arranged_agents` records unknown card names and scopes before waiting again. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md#28-operator-selection-verification) owns the permanent rule.

Pre-flight simplification finds no redundant abstraction: the shared border detector serves scanning and verification. The correction stays in that detector without adding another recognition path, state store or retry policy. No glossary term changes are required.

## Verification

[Focused regressions](../../../../arknights_mower/tests/selection_border_geometry_tests.py) cover original JPEG and explicit badge-color boundary frames, both scan modes preserving the existing selection, real roster verification without input, three partial-badge widths, ambiguous vertical evidence and complete horizontal evidence. Six new boundary cases fail before the correction and pass afterward. Existing dim-border, notice-occlusion, neighbor, training, delayed-input, page-observation and name-region tests retain their assertions. Controls and time waits use offline substitutes.

Differential replay across 159 full selection pages preserves all 1,725 unselected and 183 selected card verdicts from the original JPEG archive. The focused selection and governance suites pass 311 tests and four subtests; repository Ruff lint, format and governance checks pass.

## Standards Findings

PASS: The shared detector remains the recognition boundary. The change adds no persistent configuration or device operations, and registers the existing invariant's extension in all three governance locations.

## Spec Findings

PASS: Badge and neighboring-border interference no longer causes the reproduced verification timeout. Selected Purestream remains selected; clipped and ambiguous cards retain recovery. Live RGB confirmation remains outside the evidence provided by the JPEG archive.
