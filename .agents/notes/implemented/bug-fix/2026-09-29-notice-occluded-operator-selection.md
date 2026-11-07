---
title: Operator Selection Under a Scrolling Notice
status: implemented
category: bug-fix
date: 2026-09-29
---

# Operator Selection Under a Scrolling Notice

[English](2026-09-29-notice-occluded-operator-selection.md) | [中文](2026-09-29-notice-occluded-operator-selection.zh.md)

## Contract

- **[INV-REC-02] Occluded Operator Selection**: A card with an obscured upper selection border is confirmed only when both vertical borders and the leading portion of its lower border are visible; adjacent card borders cannot confirm selection.
- An ambiguous border retains the bounded `AgentSelectionNotReady` recovery path. A complete border retains the existing upper, lower, and side check.

## Evidence and implementation

The `alexsun` capture at 15:50:27 shows the scrolling maintenance notice covering the upper border of the selected operator card. The operator name remains readable; the lower border and both vertical borders remain visible. The previous border check returns an unknown state, and roster verification repeatedly reports an empty selection. After the notice disappears, verification reads the same operator correctly.

`agent_card_selected` accepts the unobscured lower and two vertical borders. It samples the leading portion of the lower border because a selected card in the row below can contribute pixels to the trailing portion. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent recognition rule.

## Verification

Offline tests cover a selected normal card and training card under an upper notice, a normal roster verification without a room retry, and an unselected card surrounded by selected neighbors. The captured frames confirm that only the intended card is selected with and without the notice.
