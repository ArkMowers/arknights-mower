---
title: MAA Settings Help and Checkbox
status: implemented
category: simplification
date: 2026-10-02
---

# MAA Settings Help and Checkbox

## Contract

The MAA settings form places the assistance checkbox after theme restoration settings on desktop and Android. Its visible label is `协助救急`, and its checked state binds directly to `maa_emergency_infrast_enable`. [INV-SCHED-09] retains the independent, disabled-by-default assistance setting defined in the [recovery contract](../../implemented/simplification/2026-10-02-maa-assisted-emergency.md).

Theme restoration instructions use the existing `HelpText` question-mark control beside the form label. The form contains no duplicate standalone theme explanation. This reuses the existing focus and pointer help behavior without adding a presentation abstraction.

## Review

Standards Findings: the existing configuration reference owns persistence, and shared help controls provide the instructions. No scheduling invariant changes.

Spec Findings: assistance follows theme settings, uses a checkbox with the requested label, and theme instructions remain accessible from its question-mark help.

Verification: the existing component and configuration suites pass 23 tests. Prettier, the diff check and all three governance gates pass.
