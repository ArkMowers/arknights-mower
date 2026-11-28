---
title: Shared Initial Mood Before Rescue
status: implemented
category: simplification
date: 2026-10-03
---

# Shared Initial Mood Before Rescue

## Contract

[INV-SCHED-09] evaluates intelligent rescue only after ordinary initial facility observations, candidate-card estimation and effective backup evaluation. Startup uses the ordinary mood reader and its per-facility INFO summaries. Forced initial observations share the ordinary pending-room checkpoint; partial observation yields before mandatory releases and resumes only unfinished rooms. Missing occupants lose stale measured timestamps. Existing episodes retain frozen staffing and final handoff rules.

## Simplification

The dedicated initial rescue room reader and its separate persistent room list are removed. Startup consumes its ordinary wakeup before candidate-card estimation, so the wakeup cannot reject its own scan as a pending task. No startup task is labelled as intelligent rescue before admission. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns this lifecycle.

## Verification

Focused offline regressions cover fresh and cached initialization, disabled rescue, interrupted observations, facility mood logs, candidate-scan eligibility and admission ordering. No live-device integration is used.

## Review

Standards Findings: No outstanding findings. Shared checkpoints preserve mandatory personal-limit releases and interrupted reads without adding a second initialization path. Ruff checks and formatting pass.

Spec Findings: No outstanding findings. Focused offline verification passes 1433 tests and 35 subtests, including initialization ordering, room summaries, resumed episodes, training and candidate scanning. The card-scan fixture mocks the existing room-detail step; production checks remain intact.
