---
title: Intelligent Rescue Startup Release Windows
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Startup Release Windows

## Contract

[INV-SCHED-03] applies strict-release operation windows to startup observations with or without an active intelligent rescue episode. Every completed room observation refreshes releases before another operation begins. Startup yields before card scanning when its forty-five-second allowance is unavailable. A selected release dispatches before pending initialization and is not replaced on every dispatch attempt.

Unread startup rooms persist independently of rescue episode state. A deferred startup retains the initial mood gate, authorizes no backup transition or rescue decision and resumes only unread rooms. An empty completed-room list remains distinguishable from an unstarted observation while card scanning waits. Successful initialization clears the pending list. Restored room identities are restricted to the current plan.

## Simplification

Startup uses the existing room reader, release generator, operation-budget predicate and rescue check task. The current runtime snapshot stores one nullable room list; no placeholder rescue episode or compatibility path is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the interface guarantees.

## Verification

Offline tests use the real infrastructure dispatch boundary, strict-release generation and runtime snapshot. Virtual time covers cached and uncached releases, newly measured completion, partial startup restoration, deferred card scanning and selected-release dispatch. Existing initial mood and intelligent rescue tests preserve ordinary startup behavior. Device and storage boundaries remain isolated.

## Review

Standards Findings: startup progress uses existing persistence and bounded observation mechanisms, retaining mandatory release and initialization gates.

Spec Findings: enabled intelligent rescue without an existing episode cannot delay personal-limit departure during startup. Default full-mood managers remain able to yield beds under shared recovery tiers.

Ten targeted offline suites pass 616 tests and 26 subtests. Governance tests pass 14 tests and 4 subtests. Scoped Ruff, formatting, whitespace and all governance gates pass. A fresh independent conversation reviews the immutable commit before publication.
