# Recruitment Subsystem

## 1. Scope

`RecruitSolver` calculates recruitment tag results, applies the saved selection policy before queuing tag selection, and records operators obtained from completed slots.

## 2. Selection Policy

`recruit_auto_5 = 1` selects five-star results automatically. `recruit_auto_5 = 2` leaves them for manual selection unless `recruit_auto_only5` is enabled and exactly one calculated choice remains. Existing equivalent-result collapsing occurs before this check. Manual handling sends the rare-tag notification, advances the recruitment slot and returns without queuing selection. Six-star and support robot handling, lower rarities and recruitment permit thresholds retain their existing rules.

## 3. Subsystem Invariants

- <a id="manual-selection-authority"></a>**Manual Selection Authority**: Manual five-star recruitment never queues automatic selection unless the unique-choice exception is enabled and exactly one calculated choice remains.

### Result recognition before dismissal

The token icon identifies `RECRUIT_AGENT`, but the profession icon can still be obscured by the entrance animation. [`RecruitSolver.recruit_result`](../../arknights_mower/solvers/recruit.py) requires a recognized profession icon before cropping and matching the operator name. A missing icon raises `RecognizeError` without recording a result or tapping the display. [`BaseSolver.run`](../../arknights_mower/utils/solver.py) applies its existing consecutive recognition-failure budget and refreshes the observation between attempts. Recruitment adds no separate wait loop or retry counter.

The result handler taps only after recording the name, or when that integer slot already has a recorded result. An already recorded result is not recognized again, and each call sends at most one tap. Cancellation and other recognition or device exceptions propagate to the caller without an extra dismissal tap.

Repeatedly unreadable frames exhaust the existing retry budget and return the partial results under the existing solver behavior. This does not establish that the slot was recognized: the daily scheduler can still record the recruitment run time, and subsequent scene navigation can leave the display. Name-template confidence rules and daily scheduling completion semantics are outside this repair.

## 4. Verification

[Offline policy tests](../../arknights_mower/tests/recruit_policy_tests.py) cover both modes, both exception states, single and multiple choices, equivalent results and other rarities. Device initialization and notification delivery are replaced with offline substitutes. The [decision](../../.agents/notes/implemented/simplification/2026-10-11-recruit-manual-selection.md) records the condition correction.

[Result tests](../../arknights_mower/tests/recruit_result_tests.py) replay the profession, name and token regions from the October 2, 2026 incident screenshots through the production matcher and result handler. They cover the unreadable animation frame, successful recognition of Lava on the following frame, integer-slot deduplication, failure propagation and the existing bounded retry path. Device input, waits and notification delivery use offline substitutes; no live game timing is verified.
