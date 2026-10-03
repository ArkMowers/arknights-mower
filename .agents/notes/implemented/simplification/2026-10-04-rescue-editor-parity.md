---
title: Rescue Editor Parity
status: implemented
category: simplification
date: 2026-10-04
---

# Rescue Editor Parity

## Contract

The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns rescue document isolation and facility compatibility under [INV-SCHED-09]. Mower infrastructure settings own the independent checkbox and editor entry. The editor shares normal controls, group fields and replacement fields, hiding only lower operator rules. Its return action drains saves before navigating to Mower settings. File import remains available; the right dropdown copies normal main facilities without replacing rescue backups. Export retains the complete document.

The rescue editor displays a help panel below the facility editor covering activation, facility compatibility, independent operator selections, Free-bed priorities, import/export scope and normal handoff. Ordinary replacement entries do not schedule rescue rotations; trade-room replacements select trade order operators, and Fiammetta replacements select charging targets.

The bottom cleanup action clears group labels and ordinary replacements across rescue main and backup plans. It preserves primary assignments, all trade order operators, Fiammetta charging targets (including inherited slots), and backup conditions and tasks; the normal schedule remains unchanged.

## Simplification

Removing rescue-specific editor branches preserves one facility UI. The existing plan store and save coordinator own copying and persistence. The existing effective rescue-plan validator compares facility types and staffing capacities after backup overlays, before episode creation.

## Verification

Focused store tests cover independent copies, failed reads, preserved backups and excluded rescue settings. Offline startup tests cover type and capacity mismatches and effective backup matching. Backend tests pass 175 cases and 4 subtests; seven focused frontend suites pass 48 cases. Four affected Vue components compile. Governance gates pass. No live device tests run.

## Standards Findings

Shared controls and existing persistence boundaries preserve isolation; glossary changes have explicit approval.

## Spec Findings

Only the lower operator rules are hidden. Import and export retain full-document actions, and normal schedule transfer excludes automatic rescue settings.
