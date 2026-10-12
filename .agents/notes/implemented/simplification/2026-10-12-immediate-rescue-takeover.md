---
title: Immediate Rescue Takeover
status: implemented
category: simplification
date: 2026-10-12
---

# Immediate Rescue Takeover

## Contract

[INV-SCHED-09] gives an admitted rescue schedule immediate authority over all configured working positions, including both training-room slots. Unknown mood, training occupancy, reservations and queued compensation do not postpone takeover. Actual occupancy still determines completion and unfinished rooms after a device or recognition failure. [INV-SCHED-03] retains recovery release rules after takeover; queued releases do not preempt takeover.

## Simplification

The scheduler removes staffing admission filters and training correction suppression from rescue deployment and reconciliation. Selection retains observations without treating unreadable mood as a veto. One persisted task owns the full roster, dispatches before other queued tasks and updates their work-room restoration snapshots to the rescue roster. The existing arrangement executor owns confirmed input and bounded recovery.

## Verification

Behavior: 776 focused offline tests pass across automatic rescue, emergency recovery, training protection and task admission. Coverage includes complete dispatch, queued reservations and compensation, priority, both training slots, readback and partial continuation.

Structure: Ruff checks, format checks, `git diff --check` and `python scripts/verify_governance.py` pass. Governance reports two unchanged historical references as compatibility warnings.

Review: Production dispatch prioritizes takeover before ordinary observation and exit, bypasses training protection and rebases queued restoration snapshots. Actual readback and existing bounded execution recovery remain authoritative. Live-device execution is unverified. The exact bilingual glossary synchronization remains pending explicit user approval; `CONTEXT.md` and `CONTEXT.zh.md` are unchanged.
