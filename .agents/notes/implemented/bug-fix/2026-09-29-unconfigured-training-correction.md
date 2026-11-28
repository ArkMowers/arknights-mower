---
title: Correction from an unconfigured training room
status: implemented
category: bug-fix
date: 2026-09-29
---

# Correction from an unconfigured training room

## Contract

[INV-SCHED-08] limits static correction to configured slots. A scheduled operator found in another room retains its configured return target; restoring the source slot requires that slot to exist in the effective Scheduling Plan. Missing training-room entries, empty lists, and a missing second slot do not fail correction or add implicit training assignments.

Automatic mastery continues to read both physical slots. Existing training-state protection and the assistant-follow setting retain their behavior.

## Implementation

`agent_get_mood` checks the source room and slot before restoring its scheduled occupant. The existing correction path remains authoritative; no fallback training plan or alternate correction engine is introduced. Domain glossary definitions remain unchanged.

## Verification

Offline tests reproduce `KeyError: 'train'` and source-slot `IndexError` before the fix. They cover both physical slots with absent, empty, and one-slot schedules, with automatic mastery enabled and disabled. Existing selection, arranging, and training protection tests verify the shared execution paths.
