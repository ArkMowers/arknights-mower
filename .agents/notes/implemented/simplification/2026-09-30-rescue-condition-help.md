---
title: Rescue Condition Help
status: implemented
category: simplification
date: 2026-09-30
---

# Rescue Condition Help

[English](2026-09-30-rescue-condition-help.md) | [中文](2026-09-30-rescue-condition-help.zh.md)

## Contract

Selecting the rescue condition displays the existing `HelpText` question button immediately to the right of the condition selector. Its tooltip contains `rescue_condition_help` and the boolean expression example. The dialog contains no rescue banner or preset button. Condition editing, serialized expressions, and scheduling behavior retain their existing contracts; no new architectural invariant or glossary entry is introduced.

## Simplification

The banner and inline paragraph repeat the same description. The preset button is the only caller of `use_rescue_trigger`, and its editor remount key has no other consumer. Removing the banner also removes that handler, its imports, and the remount state. `HelpText` supplies the same appearance, hover behavior, keyboard focus, and viewport width limit as other description buttons.

## Verification

Focused [rescue expression tests](../../../../ui/src/utils/trigger_rescue.test.js), Vue component compilation, formatting, and repository governance checks cover the retained expression contract and source validity. The [original rescue condition decision](../../implemented/feature/2026-09-30-rescue-backup-condition.md) defines scheduling behavior.

## Standards Findings

PASS: Existing core invariants remain satisfied. The change adds no persistent state or resource lifecycle and uses the shared help component. Governance checks and their 14 tests with four subtests pass.

## Spec Findings

PASS: The banner is absent and the rescue selector has a conditional question button on its right. Three rescue expression tests, Vue compilation, ESLint, and Prettier pass.
