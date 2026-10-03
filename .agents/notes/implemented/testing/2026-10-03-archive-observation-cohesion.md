---
title: Archive Observation Cohesion
status: implemented
category: testing
date: 2026-10-03
---

# Archive Observation Cohesion

## Contract

[INV-DIAG-07] keeps assertions over merged error metadata and invalidated log files inside the existing archive lock. Log removal establishes invalidation; it does not establish completion of the following atomic manifest replacement. The regression retains its bounded invalidation wait and asserts log absence, the merged error count and the latest error timestamp.

## Simplification Evidence

`ScreenshotStore._archiver` already owns one critical section for log invalidation and manifest replacement. The test reuses that lock without adding a production completion API, a second worker, a retry helper or a longer polling delay. Screenshot storage and intelligent rescue behavior remain unchanged.

## Verification

A controlled delay before the second manifest replacement reproduces the original stale-counter assertion. The same delay verifies the corrected observation boundary. Focused screenshot storage, cleanup and governance suites verify adjacent behavior. The three focused suites pass 93 tests and 22 subtests. Scoped Ruff, formatting, whitespace and the three governance gates pass. The first independent snapshot review confirms the regression and correction, independently passes 93 tests and 22 subtests, and reports Spec Findings PASS. Its standards finding identifies the proposed-note link; this triplet resides in implemented and the subsystem links to that location. The final independent review of snapshot `f21aecaeb8ded18327ae0c0e0f1b203f64c10c99` reports Standards Findings PASS and Spec Findings PASS with no actionable findings, independently passes 93 tests and 22 subtests, and confirms the delayed manifest boundary. Three governance gates and scoped Ruff and formatting pass; 3964 snapshot files retain their hashes. Additional controls confirm that incorrect merged counts and last-error timestamps still fail the corrected assertions. CI results are recorded after execution.
