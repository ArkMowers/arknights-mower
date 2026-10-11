---
title: Daily Trust Rotation
status: implemented
category: feature
date: 2026-10-11
---

# Daily Trust Rotation

## Contract

[INV-SCHED-48] Trust Rotation preserves ordinary working and resting state, retains each assignment until its replacement limit, excludes other assignments of the same kind, and permits assistant/activity overlap. A verified ascending roster with no eligible operator below 200% ends the remaining inspection of that kind without clearing assignments.

The daily-task window runs one cancellable inspection at a configurable interval (24 hours by default). The feature and threshold preference both default to disabled; the threshold defaults to 100%. Without the preference, replacements require 200% trust. With the preference, an incumbent at or above the threshold yields to a candidate below it; without such candidates the incumbent remains until 200%. The top assistant position receives the lowest eligible trust first. Existing protected incumbents remain in place.

The assistant and activity-room rosters each exclude their own occupants, including rooms not yet visited. The two kinds permit overlap. Ordinary working and resting assignments, mood records and scheduling occupancy remain unchanged. Unbuilt activity rooms receive no inputs. Each built room opens the user tab at most once. Unknown trust, ambiguous selection or an unverified page stops inspection without confirming a candidate. A completed inspection alone records its timestamp; subsequent daily windows retry failures. Saturation is evaluated separately for the two kinds. The next interval reevaluates new operators.

## Simplification Review

Daily work already has a nine-minute scheduling window. One solver reuses the shared device, recognizer, scene navigation and atomic runtime-state writer. No scheduler task type, ordinary room assignment or projection abstraction is added. Existing `gaming_1` through `gaming_3` plan positions do not describe the eight activity-room positions; map inspection locates built activity-room labels directly after panning right, leaving all ordinary facility coordinates unchanged.

## Implementation and Verification

The solver verifies trust sorting, current selection and the selected operator before confirmation, and verifies the returned facility page. Offline tests cover threshold admission, separate candidate exclusions, saturated-candidate early exit, daily timing, failure persistence, unreadable trust and unbuilt room handling. Device checks exercise the same solver methods with the connected emulator.


The selector disables active base-skill priority, verifies the all-professions filter and ascending trust arrow, and scrolls to a stable list start under a finite budget. Assistant membership comes from the current occupants' verified names; activity badges exclude users in unvisited rooms. Candidate names absent from the local operator table or unreadable by OCR are skipped without confirmation. Unknown incumbent names stop inspection. Empty positions require the neutral admission-cross card before filling.

The inspection has an eight-minute monotonic budget and leaves at least one minute before the next scheduled task. Stop requests propagate without recording completion; a subsequent inspection discards recognized pending selections before navigation.

## Review Evidence

- Standards findings: none remaining. The daily caller reuses the shared device and recognizer, runtime completion is separate from configuration, and ordinary operator state is never written.
- Specification findings: none remaining. Separate roster exclusion, cross-kind overlap, threshold fallback, protected incumbents and per-kind saturation match the approved contract.
- Focused Python verification: 142 tests pass across `trust_rotation_tests.py`, `config_tests.py`, `verify_governance_tests.py` and the daily-window case in `base_scheduler_tests.py`.
- Focused frontend verification: 68 tests pass across `TrustSettings.test.js`, `config.test.js`, `configPartial.test.js` and `MaaBasic.test.js`. Production build, Ruff and format checks pass; the build retains dependency-format and chunk-size warnings.
- Authorized emulator checks: five distinct assistants remain at 0% trust across repeated inspection. A 200% activity occupant changes to an eligible 0% operator while the other two built-room occupants remain; the replacement also remains an assistant. Active base-skill priority is disabled before selecting. Pending-selection recovery, unbuilt-room skipping and ordinary facility navigation are observed.
- Evidence limits: the connected account has three built activity rooms. Eight built rooms, fully saturated rosters, threshold fallback and cancellation are covered offline. Candidates without a verified local-table name remain ineligible until recognizable resources are available.
- Structural governance passes with two unchanged historical archived-test-reference warnings. Code symbols resolve by static review.
