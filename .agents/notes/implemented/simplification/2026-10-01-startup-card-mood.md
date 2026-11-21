---
title: Read-Only Startup Card Mood
status: implemented
category: simplification
date: 2026-10-01
---

# Read-Only Startup Card Mood

## Contract

Startup reads current occupants before backup evaluation, then estimates missing primary and priority replacement mood on one ordinary facility's selection page. The scan clears the pending selection to remove pinned residents, selects no cards, confirms no arrangements, and never rotates occupants through a dorm. It reuses the existing card estimator and transient candidate table. Enabled Idle Dormitory Recovery reuses cached eligible idle recovery candidates across scheduler runs. Measured recovery candidates or eligible unknown candidates with a valid low card estimate suppress a new scan. Shared candidate and reservation rules exclude working, reserved, blacklisted, active training, already-checked, completed, unknown-mood, and expired-estimate names; personal limits still require measured mood. Only an empty eligible cached recovery pool permits an ascending-card scan. Startup retains missing-primary-mood observation. Startup and regular planning share at most one physical scan per scheduler run; completed crafting replans after staff restoration using only affected candidate updates and existing estimates, without opening a card scan or resetting the per-run scan marker. Shift projection consumes the snapshot without device operations. The mood-ascending scan stops at the first green face and assigns transient estimates of 24 to all unscanned operator names. Earlier unreadable named cards stay unknown, and earlier low estimates remain unchanged even when overlapping pages are later unreadable. Card border checks reject an uncleared or ambiguous pending selection before it establishes the green boundary. Page and time guards stop exceptional scans after 20 pages, at the 45-second monotonic deadline, or before an imminent task. Unreadable observed cards remain unknown; inferred names never create live operator entries. Scan failures preserve partial estimates and continue normal startup. Device recovery and cancellation retain their existing propagation.

## Simplification Audit

The three initial dorm sampling methods have one startup caller and no external interface. Removing them also removes the sampling copy, temporary physical layout, special selection parameters, and arrangement bypasses. Startup retains actual room inspection, backup ordering, cached correction, and recovered training tasks. Legacy pending layouts supply room identifiers for one forced read despite recent timestamps; normal correction owns subsequent arrangements. New snapshots save live occupants and tasks plus remaining forced room identifiers, without card estimates or sampling layouts.

## Guarantees

[INV-SCHED-15] Selection Estimate Isolation: Selection-card mood estimates support candidate screening, ordering, and primary shift selection only; they never overwrite measured mood, timestamps, depletion rates, recovery deadlines, or mandatory personal limits. Facility-completion events refresh only affected candidates and preserve unrelated estimates and search checks. Regular candidate planning scans cards only when no eligible idle recovery candidate has valid measured or estimated mood.

Primary shift selection reads the same measured-first candidate mood function. Unknown primaries do not become exhausted through a missing reading. Generic `current_mood`, backup expressions, crafting, charging, and exhaustion timers keep their measured-cache semantics. Actual mood readback and position changes invalidate the affected card estimate; cached occupancy reads preserve it. Craft completion, completed group shifts, and training assistant releases refresh only their affected candidate estimates and search checks. The hourly exhausted-search reset clears the whole snapshot. Estimates retain their one-hour lifetime. Enabled Idle Dormitory Recovery reads departing occupants during normal replacement and new arrivals despite recent cached samples; training changes reuse the existing slot scan. These targeted mood reads do not request additional countdowns.

[English](2026-10-01-startup-card-mood.md) | [中文](2026-10-01-startup-card-mood.zh.md)

## Verification

Focused offline tests cover unchanged occupants, beds, tasks, and measured cache; no selection or confirmation; partial observation and cancellation; unreadable and unowned targets; ineffective selection clearing; overlapping unreadable cards; shared per-run observations, cached eligible measured/card/unregistered candidates preventing scans across runs, ineligible or expired candidates permitting scans, and the last candidate becoming reserved reopening observation; completed crafting preserving unrelated estimates and the scan marker whether or not the current run has scanned, including with imminent tasks; scoped group and assistant-release refresh; departing occupants and new arrivals overriding recent mood cache without additional countdowns; queued shifts avoiding redundant scans; transport failure propagation; the first green boundary and inferred full values; retained low and unreadable observations; page and time budgets; imminent tasks; legacy forced reads; startup backup/correction ordering; recovered training tasks; transient persistence; and a low-card main group producing a complete shift.

Cached occupancy correction retains precedence over estimated primary shifts; an unknown idle primary can return to its configured post before subsequent rotation. The 45-second deadline bounds loop advancement; navigation and page observation retain their own finite retries.

The 83 focused scheduling suites pass 2,392 tests and 43 subtests; Ruff and repository governance checks pass.

## Review

Standards Findings: Pass. Estimates remain transient, measured-only consumers retain their existing semantics, and cancellation releases the selection page. The glossary uses the exact bilingual wording approved by the user.

Spec Findings: Pass. Startup removes temporary admissions and uses read-only card observations while preserving actual occupancy, backup/correction ordering, and task ownership.
