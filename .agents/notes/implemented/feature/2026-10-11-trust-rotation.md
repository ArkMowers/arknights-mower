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


The selector disables active base-skill priority, verifies the all-professions filter and ascending trust arrow, and scrolls to a stable list start under a finite budget. Assistant membership comes from the current occupants' verified names; activity badges exclude users in unvisited rooms. Candidate names absent from the local operator table or unmatched by the existing name templates are skipped without confirmation. Unknown incumbent names stop inspection. Empty positions require the neutral admission-cross card before filling.

The inspection has an eight-minute monotonic budget and leaves at least one minute before the next scheduled task. Stop requests propagate without recording completion; a subsequent inspection discards recognized pending selections before navigation.

## Review Evidence

- Standards findings: none remaining. The daily caller reuses the shared device and recognizer, runtime completion is separate from configuration, and ordinary operator state is never written.
- Specification findings: none remaining. Separate roster exclusion, cross-kind overlap, threshold fallback, protected incumbents and per-kind saturation match the approved contract.
- Focused Python verification: 142 tests pass across `trust_rotation_tests.py`, `config_tests.py`, `verify_governance_tests.py` and the daily-window case in `base_scheduler_tests.py`.
- Focused frontend verification: 68 tests pass across `TrustSettings.test.js`, `config.test.js`, `configPartial.test.js` and `MaaBasic.test.js`. Production build, Ruff and format checks pass; the build retains dependency-format and chunk-size warnings.
- Authorized emulator checks: five distinct assistants remain at 0% trust across repeated inspection. A 200% activity occupant changes to an eligible 0% operator while the other two built-room occupants remain; the replacement also remains an assistant. Active base-skill priority is disabled before selecting. Pending-selection recovery, unbuilt-room skipping and ordinary facility navigation are observed.
- Evidence limits: the initial connected account has three built activity rooms; the later remote account supplies eight built rooms. Fully saturated rosters, threshold fallback and cancellation are covered offline. Candidates without a verified local-table name remain ineligible until recognizable resources are available.
- Structural governance passes with two unchanged historical archived-test-reference warnings. Code symbols resolve by static review.

## Name Recognition Repair Evidence (2026-10-12)

Remote logs from two affected instances stop during incumbent assistant-name collection, before activity-room inspection. Replaying one saved failure frame reproduces detection splitting `克莱门莎` into `克莱` and `莎`, dropping the intervening glyph after confidence filtering. The other saved JPEG identifies `罗德岛隐秘队` correctly, so that instance's original name-reading failure is not reproduced from the compressed frame. A lossless activity-room frame also exposes a recognition-only OCR failure (`旅骨商` instead of `旅骨`), which its saved JPEG does not reproduce.

The existing operator-selection templates also recognize these name fields. The selector crop changes from `(20, 155)–(350, 215)` to `(20, 160)–(350, 205)`. The activity-room crop changes from `(1420, 640)–(1750, 710)` to `(1440, 650)–(1690, 695)` to exclude the upper badge and side margins. Selector dark text uses inverse binarization; activity-room light text uses ordinary binarization, both at threshold 140. Each complete field scales uniformly to each template's text height, allowing one pixel of antialiasing variation at half-pixel steps. This accommodates the existing smaller fonts for long names and preserves their punctuation and spacing. A fixed selector scale of 0.725 overflows the 200-pixel template canvas for the real seven-character `泰拉大陆调查团` field, while height-based matching recognizes the complete name.

Matching reuses the existing selection templates and normalized correlation, requires a score above 0.6 and a distinct-name margin of at least 0.05, and caches at most 256 complete fields. Resource reload clears this cache along with the ordinary name cache. Border-touching text, text shorter than 15 pixels, oversized normalized contours and unmatched or unknown names remain unreadable. Budget checks surround matching. Other page labels and trust values retain OCR. This repair changes name-reading pixels without changing the domain contract or glossary.

Twenty-six real name fields covering twenty-two operators match correctly, including seven-character Chinese names, separated punctuation and `Miss.Christine`. Diagnostic best-match scores for the twenty-five selector and earlier activity samples range from 0.86 to 0.96. The additional activity-room sample verifies the full `泰拉大陆调查团` readback. Fixtures retain only name strips with enough surrounding pixels to verify production crops. All 121 focused cases pass across `trust_rotation_tests.py`, `name_template_cache_tests.py`, `character_name_roi_tests.py` and the daily-window caller in `base_scheduler_tests.py`. They exercise incumbent collection through `run()`, candidate verification and activity-room readback through `_replace()`, blank/clipped/oversized/weak fields, ambiguous or unknown names, deadlines, both name-cache invalidations and unchanged ordinary selection pixels.

An earlier OCR fallback repair supplies runtime history: a normal daily invocation completes inspection and writes `2026-10-12T05:33:09.624205`; a separate inspection on the other instance completes in 219.63 seconds, retaining all five protected assistants and confirming six activity-room replacements with readback. Those observations precede the template implementation. The original solver and the pre-template source files remain backed up remotely. The latter instance's ordinary scheduler remains stopped by its independent dormitory shift-target conflict, which occurs before the daily window.

The deployed height-based revision verifies an authorized manual activity assignment to `泰拉大陆调查团` at 200% trust through both selector and activity-room name templates. A subsequent full inspection completes in 78.5 seconds, reads all five assistant names, retains their protected assignments, visits all eight built activity rooms, replaces that 200% occupant with `克莱门莎` at 0% and verifies the returned name and trust. Device cleanup succeeds. The process-control restart restores both affected instances with their original ports and stopped state after installation; other instance processes remain unchanged.
