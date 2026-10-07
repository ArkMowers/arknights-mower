---
title: Protected Mastery Skill Continuation
status: implemented
category: bug-fix
date: 2026-10-07
---

# Protected Mastery Skill Continuation

## Contract

[INV-SCHED-29] retains training-room protection when material-shortage candidates are skipped. A protected room permits continuation only for the observed trainee and the same uniquely identified skill. Unknown or ambiguous skill identity retains protection without starting another skill.

## Implementation

The existing bounded skill-page read records a unique partial-mastery skill on the current room observation. Empty-room admission compares both trainee and skill instead of bypassing protection for the same operator. Protected collection uses the existing strict panel resolver, and the start boundary repeats the admission check before changing plan status or staffing. No persistent identity or independent protection flag is added. Existing glossary definitions remain accurate.

## Verification

Offline tests cover same-skill continuation, different skills of the same operator, different operators, unreadable or ambiguous partial mastery, collection identity and start-boundary rejection. Existing material-skip and training-room tests retain their boundaries.
