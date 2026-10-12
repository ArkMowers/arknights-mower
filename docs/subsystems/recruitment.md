# Recruitment Subsystem

## 1. Scope

`RecruitSolver` calculates recruitment tag results and applies the saved selection policy before queuing tag selection.

## 2. Selection Policy

`recruit_auto_5 = 1` selects five-star results automatically. `recruit_auto_5 = 2` leaves them for manual selection unless `recruit_auto_only5` is enabled and exactly one calculated choice remains. Existing equivalent-result collapsing occurs before this check. Manual handling sends the rare-tag notification, advances the recruitment slot and returns without queuing selection. Six-star and support robot handling, lower rarities and recruitment permit thresholds retain their existing rules.

## 3. Subsystem Invariants

- **[INV-RECRUIT-01] Manual Selection Authority**: Manual five-star recruitment never queues automatic selection unless the unique-choice exception is enabled and exactly one calculated choice remains.

## 4. Verification

[Offline policy tests](../../arknights_mower/tests/recruit_policy_tests.py) cover both modes, both exception states, single and multiple choices, equivalent results and other rarities. Device initialization and notification delivery are replaced with offline substitutes. The [decision](../../.agents/notes/implemented/simplification/2026-10-11-recruit-manual-selection.md) records the condition correction.
