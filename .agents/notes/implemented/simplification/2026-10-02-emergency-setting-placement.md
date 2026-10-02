---
title: Emergency Setting Placement
status: implemented
category: simplification
date: 2026-10-02
---

# Emergency Setting Placement

## Contract

[INV-01] preserves the existing configuration binding and disabled default. The automatic rescue checkbox appears once in scheduling advanced settings, immediately after the native rescue threshold. The MAA settings form has no rescue checkbox or unused binding. Advanced editing locks apply to the moved control.

The two existing components exchange the control without adding configuration keys, migrations or wrappers. The [recovery lifecycle](../../implemented/simplification/2026-10-02-maa-assisted-emergency.md) retains its backend behavior.

## Review and Verification

Standards Findings: the control reuses the configuration store and advanced form editing lock. Existing invariant registrations and glossary definitions remain accurate.

Spec Findings: the label is “自动救急” and the control remains a checkbox with help beside it. Focused MAA component and configuration-store tests, the production frontend build and governance checks verify the relocation.

Verification: both frontend suites pass 23 tests. The production build and all governance gates pass; governance unit tests pass 14 tests and 4 subtests.
