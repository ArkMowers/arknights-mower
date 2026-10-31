---
title: Recycling Material Statistics
status: implemented
category: feature
date: 2026-10-11
---

# Recycling Material Statistics

## Contract

[INV-REC-12] binds recycling statistics to observed collection evidence. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants) owns collection, persistence, API and comparison guarantees.

## Pre-flight Simplification

Existing `record._conn` owns SQLite connections and table initialization. The new table uses that boundary, and the statistics route returns date-range totals independently of paginated detail rows. No additional database service, configuration field or scheduling task is introduced. The existing material scene remains the dismissal boundary for rewards.

The source-bound collection helper serves both entry paths. Existing material icons and the recycle facility title detector supply visual evidence. Collection uses the configured right-side facility order and existing footer badge recognition; roster reading returns from the conversion dashboard before opening residence information. Recycling roster reads bypass scheduling roster updates because collection statistics require observation without affecting scheduling state.

## Probability and Value Snapshot

The bundled `recycling_model.json` preserves the supplied workbook's calculation inputs, including its sanity valuations. Production reads JSON without an Excel runtime dependency. Equal material quantity is the comparison denominator because a collection can contain several materials and does not expose the underlying ordinary or extra draw counts. This benchmark describes a long-run mixture, not operator efficiency or a short-run guarantee.

The ordinary and extra weights each sum to 10000. The original workbook's weighted sanity values are 19.60789962777894 and 76.77420071774533. The extra-draw rate is 0.052613 per ordinary draw; dividing combined return by combined material quantity yields the displayed per-material benchmark. The formula and source ranges reside in the subsystem contract and the page's expandable explanation.

The valuation settings reuse the existing SQLite boundary. A bounded standard-library Excel reader merges one-time Yituliu price imports, retains omitted values, rejects identity conflicts atomically and stores future item identities without inventing drop probabilities. Reports and exports share the saved snapshot. Editable product ratios and recycling efficiency reproduce the supplied calculator’s theoretical conversion; they do not alter observed materials or the probability pool. The subsystem contract owns input rules and formulas.

## Presentation

The page combines four summary cards, a scrollable collection timeline, a quality donut with actual and theoretical shares, material totals and date filtering. Material icons and quality accents connect details to totals; mobile and dark layouts retain the same content. Request versioning prevents stale date or page responses from replacing newer results. Unknown observations have explicit labels and a warning rather than fabricated quantities or zero-valued returns.

## Verification

The Excel export uses the same summary computation as the page and streams all selected detail rows from one SQLite snapshot. Standard-library OOXML packaging avoids a new runtime dependency; five sheets separate the overview, collection evidence, material totals, quality shares and valuation inputs. The workbook preserves unknown observations and numeric types, while literal text cells retain operator names without interpreting formulas. The export button captures its date filters before the request and releases the download URL after use.

The focused recycling suite contains 34 passing offline tests covering event identity, date bounds, range totals independent of pagination, actual two-slot roster reads, verified empty versus unknown occupants, title and ready-marker gates, invalid quantities, source isolation, popup retries, API authentication and calculator reconciliation. Export tests cover more than one page of evidence, date exclusion, unknown observations, numeric comparison parity, literal text and authenticated attachments. A separate OpenXML reader confirms all five generated sheets, values, frozen headers and percentage formats. The supplied reward screenshot confirms 装置 × 1; duplicated reward crops verify multiple-item completeness and rejection of a missing label.

On the current alpha baseline, recycling statistics, infrastructure collection, recycling-facility staffing and room relocation suites pass (139 tests in total). Existing trading debounce checks from the source baseline and structural governance checks also pass, as do frontend route and chart-isolation tests. The frontend production build passes. Browser checks cover desktop, 390px mobile without horizontal overflow, and dark mode with example data and no console errors. Actual recycling occupant-panel calibration and live-device collection remain unverified; no live-device suite runs.

The automatic-rescue collection-deadline test limits visible prompts to orders and manufacturing products and asserts the complete tap sequence. This preserves its ordinary-collection scope under [INV-SCHED-09] while recycling-specific tests exercise reward recognition. The automatic-rescue, infrastructure-collection and recycling-collection suites pass together (252 offline tests).

The final merged alpha baseline passes 178 focused recycling, valuation-import, infrastructure-collection, staffing and room-relocation tests. Thirteen frontend tests cover settings saves, incremental import feedback, failures, retries, routes and chart isolation. The supplied price worksheet imports 101 finite values while reporting nine optional unpriced items. An independent OpenXML reader verifies the final five-sheet export, numeric valuation inputs, frozen headers, filters and percentage formats.

## Standards Findings

Pass: the change preserves device recovery propagation, uses existing SQLite ownership and bounded recognition retries, avoids Scheduling Plan mutation, and includes only the explicitly approved glossary wording.

## Spec Findings

Pass for offline evidence and UI: both collection entry paths, time and actual roster snapshots, quantities, quality statistics and equal-material sanity comparison and full-range Excel export have focused coverage. Live recycling occupant-panel recognition remains a stated verification limit.

## Shared Income Settings

Mower settings places material valuation and base-report algorithms beside Yituliu synchronization. The report retains preset selection and custom coefficient editing at its original position, saving to the same configuration; the recycling page exposes the active assumptions and a settings link. The existing SQLite row stores algorithm selection, product coefficients and recycling efficiency. Confirmed server values take precedence over browser configuration; valid legacy report selections migrate once after a successful save. Reset is an explicit saved choice, so an old browser selection cannot restore itself afterward.

The offline default is the Yituliu SideStory export captured on 2026-10-12, including its activity-average-stage switch and currency coefficients. The bundled growth catalog owns this snapshot and attribution. Legacy calculator defaults upgrade to these values, while imported prices and omitted-item defaults remain available. Recycling summaries, Excel exports and current growth statistics use the same active valuation. One recommendation response captures its catalog once for both growth aggregates. Historical growth observations retain their original values and provenance.

Focused tests cover algorithm persistence and mismatched presets, authenticated API saves, migration, explicit reset precedence, failure preservation, imported future-item prices shared by recycling and growth, and retained legacy imports. Browser checks use example data rather than account or device traffic.

The preset uses CE6 for LMD and CE6/LS6 for EXP (0.23456 base-report algorithm), includes activity-token LMD value, retains four retired materials at token-equivalent LMD prices, and values purple sugar/polyester through crafting. White-to-green and green-to-blue crafting use Nine-Colored Deer; blue-to-purple and purple-to-gold use Nian.

Focused verification of the shared settings and defaults passes 316 backend tests and 38 frontend tests. Report tests exercise preset and custom saves, immediate earnings recalculation including special gold, tooltip rendering and failed-save preservation. Backend tests cover exact bundled pricing parameters and values, shared future-material imports, legacy migration and saved-choice precedence. The frontend production build and governance checks pass; live-device collection remains pending.

## Borderline quantity recognition

The 2026-10-12 archived reward frame shows 装置 × 1, but quantity OCR replays at approximately 0.94976 and fails the former 0.95 gate. The reader uses the relaxed confidence limits in the subsystem contract while preserving name/icon agreement, complete geometry and exact integer quantities; a complete observation is recorded without waiting for a second matching frame. The same [INV-REC-12] governs this repair. The unchanged JPEG fixture exercises the actual reader through collection persistence; focused cases retain rejection for low-confidence names, counts and icons. Archived JPEG replay identifies the rejection point but does not reconstruct all original uncompressed readings.

Focused recycling collection, valuation, infrastructure collection and recycling staffing suites pass 134 tests. Remote offline replay with the changed reader recognizes 装置 × 1 in all three archived observation frames; no live collection is triggered.
