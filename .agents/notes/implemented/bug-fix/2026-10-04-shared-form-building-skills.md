---
title: Shared Form Building Skills
status: implemented
category: bug-fix
date: 2026-10-04
---

# Shared Form Building Skills

## Contract

[INV-SCHED-09] uses the shared name-based building-skill catalog for alternate forms. The highest valid progression among owned forms proves unlocks; missing form records do not invalidate known progression. No form-ID list limits future forms.

## Simplification

A partial skill snapshot retains known eligible workers. Sufficient known candidates and known fixed-worker skills avoid card scanning; otherwise bounded scanning supplements the pool. New card observations replace that worker's cached entry, including exclusion for low mood. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns candidate selection. [INV-SCHED-15] keeps estimates separate from measured recovery evidence.

## Verification and Review

Standards Findings: No outstanding findings. The shared BOX remains read-only; measured mood and selection-time eligibility remain intact. No form registry or persistent candidate cache is added.

Spec Findings: No outstanding findings. Focused offline verification passes 482 tests and 4 subtests, including future forms, missing progression, partial snapshots and low-mood exclusion during supplemental scanning.
