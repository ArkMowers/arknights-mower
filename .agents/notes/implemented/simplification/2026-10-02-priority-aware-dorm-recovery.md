---
title: Priority Aware Dormitory Recovery
status: implemented
category: simplification
date: 2026-10-02
---

# Priority Aware Dormitory Recovery

## Contract

[INV-SCHED-09] and [INV-SCHED-13] use the same strict recovery tier for ordinary and rescue bed allocation. Explicit priority precedes main primaries, low main primaries, priority replacements, standby primaries, ordinary replacements and idle operators. Rescue maintains completion targets without flattening these tiers. Equal tiers preserve current residents. Intelligent rescue retains configured recovery tiers; only explicit configuration raises priority.

Higher-tier arrivals can displace lower-tier recovery residents. Explicit idle-release exclusions and pending bed ownership remain binding. Known idle and ordinary replacement identities never acquire formal rescue protection through a missing legacy admission flag. Unknown operator identity remains protected.

Configured standby primaries retain standby eligibility during rescue unless the user explicitly requires full recovery or exhaustion. Low mood raises their allocation tier without requiring a bed for every standby member. A recovering required group member provides the return anchor. Displacement preserves that anchor and the group's working covers. Losing a required recovery member recalls the group and cancels obsolete return or release actions; replacement planning and selection share this compensation.

## Simplification

The shared tier and bed predicate replace unconditional rescue retention and the separate main-resident and standby-mood takeover barriers. Selection and idle replacement planning call the same predicate. No second candidate cache, admission migration pass or configuration option is introduced.

Measured MAA recovery targets govern assisted handoff. Crafting retains ordinary mood and reservation checks. Layout restoration retains current positions while capacity reduction selects by tier; active single recovery never displaces a higher-tier retained resident.

## Verification

`rescue_priority_takeover_tests.py` checks the full tier-pair matrix in both modes, legacy ordinary residents, configured standby and the actual idle replacement entry. The sanitized 2026-10-02 room-state replay admits each previously blocked group independently. Group, restart, selection, release, rescue backup and offline remote-state replay tests cover displacement compensation and retained recovery deadlines. Tests perform no device or network I/O.
