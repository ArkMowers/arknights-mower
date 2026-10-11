---
title: Recycling Material Statistics
status: implemented
category: feature
date: 2026-10-11
---

# Recycling Material Statistics

## Contract

[INV-REC-11] binds recycling statistics to observed collection evidence. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants) owns collection, persistence, API and comparison guarantees.

## Pre-flight Simplification

Existing `record._conn` owns SQLite connections and table initialization. The new table uses that boundary, and the statistics route returns date-range totals independently of paginated detail rows. No additional database service, configuration field or scheduling task is introduced. The existing material scene remains the dismissal boundary for rewards.

The source-bound collection helper serves both entry paths. Existing material icons and the recycle facility title detector supply visual evidence. Collection uses the configured right-side facility order and existing footer badge recognition; roster reading returns from the conversion dashboard before opening residence information. Recycling roster reads bypass scheduling roster updates because collection statistics require observation without affecting scheduling state.

## Probability and Value Snapshot

The bundled `recycling_model.json` preserves the supplied workbook's calculation inputs, including its sanity valuations. Production reads JSON without an Excel runtime dependency. Equal material quantity is the comparison denominator because a collection can contain several materials and does not expose the underlying ordinary or extra draw counts. This benchmark describes a long-run mixture, not operator efficiency or a short-run guarantee.

The ordinary and extra weights each sum to 10000. Their weighted sanity values are 19.60789962777894 and 76.77420071774533. The extra-draw rate is 0.052613 per ordinary draw; dividing combined return by combined material quantity yields the displayed per-material benchmark. The formula and source ranges reside in the subsystem contract and the page's expandable explanation.

## Presentation

The page combines four summary cards, a scrollable collection timeline, a quality donut with actual and theoretical shares, material totals and date filtering. Material icons and quality accents connect details to totals; mobile and dark layouts retain the same content. Request versioning prevents stale date or page responses from replacing newer results. Unknown observations have explicit labels and a warning rather than fabricated quantities or zero-valued returns.

## Verification

The Excel export uses the same summary computation as the page and streams all selected detail rows from one SQLite snapshot. Standard-library OOXML packaging avoids a new runtime dependency; four sheets separate the overview, collection evidence, material totals and quality shares. The workbook preserves unknown observations and numeric types, while literal text cells retain operator names without interpreting formulas. The export button captures its date filters before the request and releases the download URL after use.

The focused recycling suite contains 34 passing offline tests covering event identity, date bounds, range totals independent of pagination, actual two-slot roster reads, verified empty versus unknown occupants, title and ready-marker gates, invalid quantities, source isolation, popup retries, API authentication and calculator reconciliation. Export tests cover more than one page of evidence, date exclusion, unknown observations, numeric comparison parity, literal text and authenticated attachments. A separate OpenXML reader confirms all four generated sheets, values, frozen headers and percentage formats. The supplied reward screenshot confirms 装置 × 1; duplicated reward crops verify multiple-item completeness and rejection of a missing label.

On the current alpha baseline, recycling statistics, infrastructure collection, recycling-facility staffing and room relocation suites pass (139 tests in total). Existing trading debounce checks from the source baseline and structural governance checks also pass, as do frontend route and chart-isolation tests. The frontend production build passes. Browser checks cover desktop, 390px mobile without horizontal overflow, and dark mode with example data and no console errors. Actual recycling occupant-panel calibration and live-device collection remain unverified; no live-device suite runs.

## Standards Findings

Pass: the change preserves device recovery propagation, uses existing SQLite ownership and bounded recognition retries, avoids Scheduling Plan mutation, and includes only the explicitly approved glossary wording.

## Spec Findings

Pass for offline evidence and UI: both collection entry paths, time and actual roster snapshots, quantities, quality statistics and equal-material sanity comparison and full-range Excel export have focused coverage. Live recycling occupant-panel recognition remains a stated verification limit.
