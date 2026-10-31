---
title: Fixed Dormitory Cover Admission
status: implemented
category: bug-fix
date: 2026-10-08
---

# Fixed Dormitory Cover Admission

## Contract

[INV-SCHED-22] A configured fixed dormitory replacement remains eligible to retain its exact current slot during group shift-off, with single or multiple bindings. The slot remains fixed. Other rooms and slots cannot borrow that replacement; candidate mood limits, explicit reservations, unique matching and observed group confirmation remain authoritative.

## Implementation

`BaseSchedulerSolver._get_resting_plan` distinguishes retaining the target slot from borrowing an occupied fixed dormitory replacement by room and index. The existing `in_slot` predicate supplies the exception without requiring the primary to have multiple bindings. Candidate collection, group matching, bed admission and execution confirmation keep their existing boundaries.

## Verification

The supplied effective roster and logged occupants reproduce two empty candidate sets for dormitory primaries 琴柳 and 蜜莓 despite their configured replacements 赫默 and 埃癸斯 already occupying those exact fixed slots. The corrected admission retains both replacements while arranging the working members to rest. Offline tests cover zero and full mood, complete shift projection and confirmation, and rejection of other-slot borrowing, other-room borrowing, product reservations and prior candidate claims. The source archive contains no backup-condition document, so the roster replay verifies this admission boundary without claiming a complete device replay.
