---
title: In-game Selection Performance Test
status: implemented
category: feature
date: 2026-10-10
---

# In-game Selection Performance Test

[中文](2026-10-10-game-performance-test.zh.md)

## Decision

The explicit desktop test owns one device run and uses dormitory one without confirming an arrangement. It reuses Device Control startup, foreground game launch and production scene-graph navigation to reach the base. An existing base overview or that dormitory's room view continues directly. Login verification, agreement prompts and pre-existing unconfirmed operations stop for manual resolution. Conservative preparation identifies two targets newly reached after three forward swipes. Each independent selection test clears and resets the list, then uses the candidate mode for three forward swipes before selection, reorder and roster verification. Intermediate scans read the held frame without selecting any operator. One complete selection operation counts as one test; three consecutive successful tests recommend the mode. The first failed round restarts at the next lower mode; failure at low produces no recommendation. Device faults, navigation/preparation faults and cancellation abort rather than masquerading as performance failures.

The test has no overall deadline. Finite round counts, cancellable I/O with existing per-operation deadlines and bounded cleanup retain operational control. Its device run explicitly defers operation-cancellation close until compensation finishes; cleanup has an independent ten-second budget. Default run cancellation and shutdown gates retain their existing behavior. It cancels temporary selections on completion or ordinary cancellation; shutdown or an unavailable device can prevent cleanup and is reported. It never confirms staffing or modifies saved modes, independent timing values or automatic feedback. Explicit adoption saves only the selected mode. Device or timing edits invalidate recommendations. Connection resource readings remain informational in the UI.

## Simplification and Ownership

The connection resource observation record owns read-only resource observation. This decision independently owns a user-initiated input test. The implementation reuses the existing worker lifecycle and device run boundary, and shares selection/reorder primitives with normal scheduling. It adds no persisted benchmark cache or second device owner. Existing domain definitions remain unchanged.

## Guarantee and Verification

[INV-SCHED-45] Selection Performance Test Isolation covers bounded descending trials, explicit adoption and staffing/state preservation. Offline checks exercise successful runs, first-failure downgrade, all-mode failure, wrong selected names, unchanged pages, preparation/device faults, cancellation, cleanup, worker admission and stale UI results. The production fast scanner and roster reader reject the recorded Ulpianus/Skadi versus Beehunter/Skadi misselection. Normal scheduling and explicit trials share reorder coordinates and timing.

Eight focused backend suites pass 198 cases; six frontend suites pass 188 cases. After integration with held-swipe capture, six focused selection suites pass 172 cases. The cancellation repair adds a regression that first reproduces premature session closure during device I/O; five focused test, session, shutdown and held-swipe suites then pass 86 cases. The frontend production build, changed-file Ruff, ESLint, formatting and governance checks pass. Governance retains two historical archived-reference warnings.

Local MuMu Pro testing with DroidCast capture and scrcpy input passes all three `xhigh` rounds and verifies the actual selected roster and reordering. The room remains empty at 0/5 after cleanup. A second live run exposes premature session closure on cancellation; after the repair, cancelling a run with two completed rounds returns cancelled, exits selection and preserves 0/5 occupancy. A final complete live run after the repair again passes all three extreme-mode rounds and preserves 0/5 occupancy. Saved mode and timing values remain unchanged. Downgrade and misselection rejection are exercised offline; the live device does not fail the extreme-mode rounds.

Automatic entry regressions exercise the production quick-login and base-navigation edges, direct continuation from the base, manual-verification boundaries and reobservation of a transient login match without input. Long-running solver and HTTP-worker regressions advance a fake clock beyond the former four-minute cap while retaining three verified rounds and compensation. Resource-observation regressions assert the absence of hardware recommendations across seven guest configurations.

Before the multi-swipe extension, after lowering the simulator configuration, a live cold-start run automatically starts the stopped selected instance, launches the game, logs in using the existing quick-login flow and navigates to the base. It passes all three `xhigh` rounds, then exits selection with dormitory one still at 0/5. This run takes about four minutes forty seconds, exceeding the removed total cap; saved mode and timing values remain unchanged. At that stage, eight focused backend suites pass 183 cases, and six frontend suites pass 188 cases. A transient loading frame initially mistaken for a verification page motivates reobservation before the manual-action stop; genuine verification and agreement prompts remain manual.

The multi-swipe extension is verified offline: six focused backend suites pass 166 cases, two affected frontend suites pass nine cases, and the production UI build passes. Regressions first reproduce the single-swipe behavior, then verify three swipes before any selection, current-page coordinates for subsequent swipes, targets first reached on the third swipe, independent preparation for each selection test and cancellation between swipes. Per the user's instruction, this extension is deployed locally without further live simulator or computer-control testing.

Standards review confirms worker admission and shutdown ownership, lock order, cancellable status polling, finite per-operation I/O deadlines, bounded compensation, unchanged automatic feedback and glossary definitions. Requirement review confirms extreme-first trials, three consecutive passes, first-failure downgrade, no low fallback after low failure, exact selected-name verification, explicit adoption and invalidation on Device Profile or timing edits. No actionable findings remain in the reviewed scope. The live result describes the current MuMu instance and timing configuration; other devices require their own test.
