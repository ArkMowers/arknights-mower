---
title: In-game Selection Performance Test
status: implemented
category: feature
date: 2026-10-10
---

# In-game Selection Performance Test

[中文](2026-10-10-game-performance-test.zh.md)

## Decision

The explicit desktop test owns one device run and uses dormitory one without confirming an arrangement. It starts from the base overview or that dormitory's room view. Conservative preparation identifies two targets beyond the initial page; each measured round uses the candidate mode's production swipe, selection, reorder and roster verification. Three consecutive successful rounds recommend the mode. The first failed round restarts at the next lower mode; failure at low produces no recommendation. Device faults, navigation/preparation faults and cancellation abort rather than masquerading as performance failures.

The test uses a finite total deadline, cancellable I/O and bounded cleanup. Its device run explicitly defers operation-cancellation close until compensation finishes; test deadline exhaustion uses the same cancellation path while reporting failure. Default run cancellation and shutdown gates retain their existing behavior. It cancels temporary selections on completion or ordinary cancellation; shutdown or an unavailable device can prevent cleanup and is reported. It never confirms staffing or modifies saved modes, independent timing values or automatic feedback. Explicit adoption saves only the selected mode. Device or timing edits invalidate recommendations. Connection resource readings remain informational in the UI.

## Simplification and Ownership

The connection recommendation record owns read-only resource observation. This decision independently owns a user-initiated input test. The implementation reuses the existing worker lifecycle and device run boundary, and shares selection/reorder primitives with normal scheduling. It adds no persisted benchmark cache or second device owner. Existing domain definitions remain unchanged.

## Guarantee and Verification

[INV-SCHED-45] Selection Performance Test Isolation covers bounded descending trials, explicit adoption and staffing/state preservation. Offline checks exercise successful runs, first-failure downgrade, all-mode failure, wrong selected names, unchanged pages, preparation/device faults, cancellation, cleanup, worker admission and stale UI results. The production fast scanner and roster reader reject the recorded Ulpianus/Skadi versus Beehunter/Skadi misselection. Normal scheduling and explicit trials share reorder coordinates and timing.

Eight focused backend suites pass 198 cases; six frontend suites pass 188 cases. After integration with held-swipe capture, six focused selection suites pass 172 cases. The cancellation repair adds a regression that first reproduces premature session closure during device I/O; five focused test, session, shutdown and held-swipe suites then pass 86 cases. The frontend production build, changed-file Ruff, ESLint, formatting and governance checks pass. Governance retains two historical archived-reference warnings.

Local MuMu Pro testing with DroidCast capture and scrcpy input passes all three `xhigh` rounds and verifies the actual selected roster and reordering. The room remains empty at 0/5 after cleanup. A second live run exposes premature session closure on cancellation; after the repair, cancelling a run with two completed rounds returns cancelled, exits selection and preserves 0/5 occupancy. A final complete live run after the repair again passes all three extreme-mode rounds and preserves 0/5 occupancy. Saved mode and timing values remain unchanged. Downgrade and misselection rejection are exercised offline; the live device does not fail the extreme-mode rounds.

Standards review confirms worker admission and shutdown ownership, lock order, cancellable status polling, finite I/O and sleep deadlines, bounded compensation, unchanged automatic feedback and glossary definitions. Requirement review confirms extreme-first trials, three consecutive passes, first-failure downgrade, no low fallback after low failure, exact selected-name verification, explicit adoption and invalidation on Device Profile or timing edits. No actionable findings remain in the reviewed scope. The live result describes the current MuMu instance and timing configuration; other devices require their own test.
