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

The green income button beside advanced settings below the schedule image opens the parameter dialog. The dialog runs the supplied calculator's fixed source snapshot in a browser Worker, using a detached schedule and advanced-settings snapshot. It reuses Mower's QR export and import with that same snapshot, then places a compact income header above the original schedule image. Defaults are three warmup days and twenty-eight measured days. Most parameters and results stay temporary. Growth and inventory default to the read-only Skland cache, with missing basic resources requiring input and manual sources available. Weights follow Mower income settings; explicit shared-algorithm selections persist and each run rereads current settings, while per-run custom weights remain temporary. Gold debt is enabled by default for delivery, without relaxing other material limits. Recycling reports only production counts, without random materials or value. The result window identifies source versions and model assumptions, and displays searchable logs and detailed flows before manual export. The compact image keeps product icons and net gold/LMD, omits absent products and marks actual drone usage on the captured facility positions. Users can name the schedule in the result window; manual JPG exports use the name only in the filename, followed by daily weighted income and measured days. The image header places daily weighted income on the left and small daily product badges on the right, alongside a simulation verification stamp stating total, warmup and sampled days. Recycling reuses the room-title recognition symbol. The initial visualization reused the Mower mood board to expose group curves and charge jumps. The user subsequently selected the calculator's source Gantt chart instead. Its fixed component and timeline builder retain facility/operator tracks, sampling-relative times, filtering, navigation and image export; the separate curve recorder and historical-chart changes are removed. A local wrapper adapts light/dark colors, controls, spacing and narrow-window layout to Mower without changing source behavior. Local source patches retain completion precision, optional gold debt, manufacturing cost observation and the read-only recruitment observer, with per-file hashes. Domain names and the distinction between simulated and actual staffing remain unchanged; no glossary edit is needed.

## Alternatives considered

A backend simulation would require another runtime or a rewrite of the supplied TypeScript engine. Running on the browser's main thread blocks cancellation. A second image format would add another importer despite the existing QR format supporting taller images. A fixed source copy keeps the feature available offline and auditable, at the cost of deliberate synchronization when the calculator or native scheduler changes.

## Verification

The 27 focused adapter, dialog and Worker tests pass, covering three warmup days, twenty-eight measured days, isolated input, finite inventory, gold debt, recycling counts, failures and cancellation. Dialog cases verify unknown cached quantities, shared-algorithm saves and rereads, and stale responses after close. An independently calculated unstaffed factory produces 560 gold bars over 28 measured days. Both staffed and all-Free dormitories complete the 31-day rotation simulation. Six fixed-engine suites pass 107 cases covering resting, shared groups, backups, inventory and production boundaries. Cache-interface checks cover authenticated read-only access and field filtering. Seven image-interface cases pass, including snapshots after saved-plan changes, light/dark themes and complete tall-image round trips.

The earlier result-window and morale implementation passed 91 focused frontend checks and five image-interface checks. These cover manual export with frozen inputs, named JPG downloads, sampled net LMD including manufacturing costs, icon filtering, event logs, and morale curves. Identical input with morale recording enabled and disabled produces identical income and resource flows. The existing decoder and plan parser read an actual browser-exported JPG with its original schedule and advanced settings. The production build includes a separate Worker; source-manifest and documentation structure checks pass. The subsequent compact-header layout passes 33 focused frontend checks and five image-interface checks with the schedule shifted below the header. A browser run with three warmup days, twenty-eight sampled days and drones assigned to B101 exported a 3012 × 1682 JPEG. Its stamp shows all three durations, and the decoder and plan parser recover the main plan, eight backup plans and advanced settings. Actual device income has not been compared.

The Gantt replacement passes 211 focused checks across 17 files, including the two scheduler fixes, fixed no-training assumptions, source timeline models, actual Worker output, browser archives and restored historical mood utilities. Enabling segment recording leaves income and resource flows unchanged for the same input. A browser run with three warmup days and twenty-eight sampled days restores its saved result after reload, renders facility and operator tracks, and exports a custom 24-hour PNG. Light and dark Mower themes are checked in the browser. The production build includes the independent Worker, and the source verifier checks 151 files and seven local patches.

## Consequences

The calculator follows its pinned Mower alpha reference; later native scheduling changes are not automatically incorporated. Estimates and ideal order runs are not measured income or proof of real-device feasibility. Large schedules can be slow; user cancellation retains observed diagnostics without attributing causation from activity alone. Imported images restore schedules and advanced settings, not transient calculation results.

Explicit shared-algorithm selection updates Mower income settings; reverting code does not undo that choice, so restore the previous algorithm in settings if needed. Existing exported images retain the original import format; their calculation results and cached data do not become configuration.
