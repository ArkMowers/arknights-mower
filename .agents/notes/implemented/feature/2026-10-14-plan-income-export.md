---
format: decision
title: Scheduling Plan income image export
status: implemented
category: feature
date: 2026-10-14
---

# Scheduling Plan income image export

## Problem

The [Scheduling Plan Editor](../../../../docs/subsystems/plan-editor.md) previously transferred complete schedules without an income-estimation entry. Users need an adjustable simulation followed by one income image that retains the original schedule for import.

## Decision

The green income button beside advanced settings below the schedule image opens the parameter dialog. The dialog runs the supplied calculator's fixed source snapshot in a browser Worker, using a detached schedule and advanced-settings snapshot. It reuses Mower's QR export and import with that same snapshot, then appends the income report below the original schedule image. Defaults are three warmup days and twenty-eight measured days. Most parameters and results stay temporary. Growth and inventory default to the read-only Skland cache, with missing basic resources requiring input and manual sources available. Weights follow Mower income settings; explicit shared-algorithm selections persist and each run rereads current settings, while per-run custom weights remain temporary. Gold debt is enabled by default for delivery, without relaxing other material limits. Recycling reports only production counts, without random materials or value. Reports identify source versions and model assumptions. Local source patches record per-file hashes for completion precision, all-Free dormitories and optional gold debt. Domain names and the distinction between simulated and actual staffing remain unchanged; no glossary edit is needed.

## Alternatives considered

A backend simulation would require another runtime or a rewrite of the supplied TypeScript engine. Running on the browser's main thread blocks cancellation. A second image format would add another importer despite the existing QR format supporting taller images. A fixed source copy keeps the feature available offline and auditable, at the cost of deliberate synchronization when the calculator or native scheduler changes.

## Verification

The 27 focused adapter, dialog and Worker tests pass, covering three warmup days, twenty-eight measured days, isolated input, finite inventory, gold debt, recycling counts, failures and cancellation. Dialog cases verify unknown cached quantities, shared-algorithm saves and rereads, and stale responses after close. An independently calculated unstaffed factory produces 560 gold bars over 28 measured days. Both staffed and all-Free dormitories complete the 31-day rotation simulation. Six fixed-engine suites pass 107 cases covering resting, shared groups, backups, inventory and production boundaries. Cache-interface checks cover authenticated read-only access and field filtering. Seven image-interface cases pass, including snapshots after saved-plan changes, light/dark themes and complete tall-image round trips.

Browser verification exercises the income entry, parameter dialog and automatic download. The existing decoder and plan parser read the downloaded PNG with its original schedule and advanced settings. The production build includes a separate Worker; source-manifest and documentation structure checks pass. Actual device income has not been compared.

## Consequences

The calculator follows its pinned Mower alpha reference; later native scheduling changes are not automatically incorporated. Estimates and ideal order runs are not measured income or proof of real-device feasibility. Large schedules can be slow; user cancellation retains observed diagnostics without attributing causation from activity alone. Imported images restore schedules and advanced settings, not transient calculation results.

Explicit shared-algorithm selection updates Mower income settings; reverting code does not undo that choice, so restore the previous algorithm in settings if needed. Existing exported images retain the original import format; their calculation results and cached data do not become configuration.
