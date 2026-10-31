---
title: Mastery Trainee and Material Boundaries
status: implemented
category: bug-fix
date: 2026-10-07
---

# Mastery Trainee and Material Boundaries

## Contract

[INV-SCHED-29] skips material-shortage candidates before their first confirmed training. A material failure after confirmed training retains the current plan boundary until its materials are ready. Protected rooms preserve the observed trainee without restricting the selected skill. Collection progress belongs only to the observed skill.

## Implementation

The bounded skill-page read returns protection without inferring skill identity. Protected empty-room admission and the start boundary compare the observed trainee only; collection within the same observation uses the panel trainee. Strict collection matching attributes progress to the observed skill; unmatched collection receives no plan credit and preserves room protection.

A material failure with a recorded training expiry retains its failure reason when the warehouse scan resets failed plans to idle. A shared selector supplies the waiting plan to preparation, scan admission and empty-room dispatch. Preparation and scan admission evaluate only that plan, and dispatch rejects other plan keys and selects the exact waiting row before higher-priority duplicates. Confirmed training clears its material-wait reason. No new persistent field or lifecycle status is added. Existing glossary terms remain accurate.

## Verification

Offline tests cover same-trainee different-skill admission, cache-clearing restart with multiple or unreadable mastery tiers, different or unreadable trainees, collection attribution, rejection before staffing mutation, persistent material failure after retry, later-task rejection, preparation and scan resumption after stock refresh, and shortage skipping before the first confirmed training, and release of the wait after target completion.
