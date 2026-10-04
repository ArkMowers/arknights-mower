---
title: Rescue recovery queue merging
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue recovery queue merging

## Contract and simplification

[INV-SCHED-03] retains each release member's bed identity and strict personal-limit deadlines. [INV-SCHED-09] batches predicted rescue recovery tasks at queue generation through the existing merge interval: one task per dormitory and one execution time per batch. Non-release tasks and strict limits interrupt batches. Ordinary full-mood releases and rescue target releases never share a batch.

The existing `merge_release_dorm` function runs after rescue release regeneration. No parallel merger or setting is introduced. Recovery targets remain authoritative in episode state; execution observes all due rooms and releases only measured-ready members. Replanning regenerates and merges the queue again without extending the interval.

## CI and review

The isolated fill projection shares an instance mock with the live solver. The rotation regression counts the live-state planning call separately and continues to require one actual arrangement. Standards review checks bed identity, task boundaries and shared merge behavior. Specification review checks same-room merging, cross-room timing, repeated regeneration and measured recovery.
