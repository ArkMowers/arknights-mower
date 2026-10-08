---
title: Recycling selection and local facility layout
status: implemented
category: feature
date: 2026-10-08
---

# Recycling selection and local facility layout

## Contract

[INV-SCHED-41] gives `recycle` two physical positions, optional Scheduling Plan membership and bounded selection entry. [INV-UI-08] keeps the order of office, training and recycling in local configuration; plan exports, identities, staffing, conditions and tasks retain their values. All three facilities can occupy any of the three right-side positions below the workshop. Dragging changes configuration, not the in-game construction layout.

The rebase target and the grouped bed-preemption branch originally register different guarantees as [INV-SCHED-37]. Recycling retains its complete guarantee under [INV-SCHED-41]; [INV-SCHED-37] continues to identify Group Preemption Priority. This registration change does not alter recycling behavior.

## Simplification audit

`agent_arrange_room` already calls the shared selector, confirmation and room readback. Recycling reuses the shared residence-information entry, card recognition and scheduling without a separate selection path. The two existing physical-capacity branches also cover recycling. The local list replaces the two-room boolean rather than introducing parallel settings. Main, backup and rescue pages reuse `PlanEditor` and the same configuration autosave.

## Implementation

`Plan1` and explicit `Task` preserve optional recycling entries and reject more than two positions. `Operators.get_current_room` and `get_agent_from_room` inspect two physical positions even with absent or partial static staff. Empty legacy schedules omit recycling during export. Right-side backup validation and merging follow the [optional staffing contract](../bug-fix/2026-10-08-right-side-backup-staffing.md); absent or partial primary staffing does not discard explicit recycling tasks. The map segmenter applies the validated three-room permutation after calculating physical positions, leaving other facilities fixed.

The dashboard template uses the English facility label and fixed mood label, excluding animation, occupancy and efficiency values. The room-title template excludes the floor number. Selection opens the standard residence-information list and taps its first operator row, using the same bounded entry loop as other facilities. Mood and occupancy reading use this list too. If the conversion dashboard is open, navigation returns to the room view before opening residence information. A confirmed shared selection page is required; unknown pages wait within a finite budget. Shared confirmation recognizes the recycling dashboard as a completed return; measured room readback completes staffing. The rescue facility registry includes recycling with capacity two, preserving primary and active backup staff in the effective roster and including all explicitly configured rescue staff in initial mood sampling. Existing duplicate, agent validity, facility completeness and staffing-count checks apply. Material input, efficiency boosting and product collection are outside this change.

The editor offers two recycling operator rows and native card dragging. The explicit move drop effect permits drops over nested card content. A separate drag payload and left-room source validation prevent dragging between layout cards and production-room assignments. The legacy `swap_contact_train` migrates only when the new order is absent; malformed or duplicate room lists fail validation. Local layout is excluded from exported advanced settings.

The [plan-transfer contract](../../../../docs/subsystems/plan-editor.md#2-plan-transfer) keeps the right-side cards clear during image export. Fourteen data segments replace sixteen so the original two left-side rows retain their positions without a larger image or a new footer. Each segment carries more compressed data; the complete Scheduling Plan remains intact. Decoder retries retain an unmodified image and verify payload completeness so fourteen detected segments of an older sixteen-code image do not end the scan prematurely. Scanning selects only QR symbols because avatar textures can otherwise contribute a false I25 barcode to the compressed stream. This repair reuses the existing export and import paths and invariants; Scheduling Plan and facility concepts retain their meanings, so no glossary edit or new decision record is required.

## Evidence and limits

The source is the [official expansion preview](https://www.bilibili.com/opus/1256772817402200067). User-supplied stills include native 1920×1080 room/map views and a 1280×720 dashboard. The third GIF shows multi-selection of Eyjafjalla and Angelina followed by one confirmation and return to the dashboard; the existing card reader, blue-frame detector and confirmation template recognize its stable frames. The second GIF verifies that the dashboard template rejects material-selection and confirmation overlays. The first GIF contains only idle animation.

Offline regressions cover legacy omission, primary/backup/task persistence, capacity rejection, six layout permutations, old-switch migration, card rendering, local-only configuration patches, entry recovery, real-frame confirmation return, shared selection/readback, rescue primary/backup deployment and initial sampling. Browser checks cover real native drag/drop and two recycling edit rows. No live game is available: the user specifies that recycling shares the residence-information list with other facilities; this common-panel path and room-view/dashboard return behavior still require live validation.

Export regressions verify light and dark JPEG round trips through `/dialog/save/img` and `/import` for normal and rescue plans, including recycling group bindings, backup staffing and tasks, and exclusion of local layout from JSON and image payloads. The QR-code suite also verifies an eight-backup fixture, unchanged right-side pixels and image dimensions, small-canvas completeness, legacy sixteen-code import, and retry after a partial legacy scan.

A supplied 3012×1236 dark image reproduces decompression failure with fourteen valid QR symbols and one zero-area I25 detection. QR-only scanning restores its complete payload and both normal and rescue import routes accept it using temporary configuration files. A synthetic one-pixel I25 barcode reproduces the same contamination with new and legacy images in both themes; all four cases fail before the scanner restriction and pass after it. The supplied image remains local and is not committed as a fixture.
