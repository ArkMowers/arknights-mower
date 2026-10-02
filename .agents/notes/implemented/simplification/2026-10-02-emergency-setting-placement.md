---
title: Emergency Setting Placement
status: implemented
category: simplification
date: 2026-10-02
---

# Emergency Setting Placement

## Contract

[INV-01] preserves the existing configuration binding and disabled default. The intelligent rescue checkbox appears once in the Mower settings card, immediately after the display theme. The MAA settings form has no rescue checkbox or unused binding. The settings page uses the existing configuration autosave.

The two existing components exchange the control without adding configuration keys, migrations or wrappers. The [recovery lifecycle](../../implemented/simplification/2026-10-02-native-automatic-rescue.md) defines Mower temporary staffing and measured recovery.

## Review and Verification

Standards Findings: the control reuses the configuration store and disabled default. Configuration keys and recovery behavior stay consistent.

Spec Findings: the label is “智能救急” and the control remains a checkbox with help beside it. Focused configuration-store tests, the production frontend build and governance checks verify the relocation.

Verification: the configuration-store suite passes 17 tests after the relocation. The production build and all governance gates pass; governance unit tests pass 14 tests and 4 subtests.
