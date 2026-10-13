---
format: decision
title: Base Group Estimates
status: implemented
category: feature
date: 2026-10-13
---

# Base Group Estimates

## Problem

Read-only groups need estimates from selected operators. Estimates must distinguish actual and hypothetical maximum progression, skill upgrades, facilities and recipes without mutating scheduling state or persisting selections.

## Decision

Pre-flight review finds no reusable efficiency calculator. One pure calculator serves the existing group page; explicit rules replace parsing numbers from rich skill descriptions. Skill-family counts reuse active skill names. The run-order entry remains a display-only roster; nineteen other presets provide estimates. Immutable presets retain their browsing boundary. Selection, mode and condition changes remain in memory and never modify Scheduling Plans or browser storage. Accessories start selected and provide roster conditions only. Core and alternative operators start unselected. Only hovering the small skill label opens its description; operator cards have no skill popover and skill labels have no navigation action.

Actual mode uses active, unreplaced skills from the shared Skland snapshot. Missing progression prevents actual estimates. An explicit maximum-skill checkbox uses the highest version per skill key. Jaye prefers actual Skland progression when owned and all skill states are known, including when maximum-skill mode is enabled. Only unavailable or incomplete progression uses the manually chosen fallback stage. The fallback remains in page memory, and details identify the effective stage and source. No current-order-count control exists, and estimates assume empty orders. The calculator defaults to a 252 layout, twenty dormitory residents, level-one dormitories and a drone capacity of 250. The right-side-max assumption remains an internal calculation contract. Training efficiency is excluded. Ling and Dusk use their group's smoke or perception mode. Metrics separate facility production, recruitment, faction resources and recovery. Deep Sea Hunters fill as many factories as needed at the chosen hunters per factory, defaulting to two per factory; each factory has its own result. Four hunters at one per factory produce four results. Time-dependent production defaults to a fixed thirty-hour average with no duration control; the per-group average-efficiency checkbox switches to peak output when disabled. Mechanist contributes 36% on average or 40% at peak with maximum skills. Facility snapshots never overwrite this page-local choice. Elite facility count follows selected elite operators, including accessories, assuming separate facilities; it may exceed five, while individual skills retain their five-facility and ten-facility caps. It has no manual override. Kirara converts actual gold lines only, excluding virtual Durin lines. Order-limit conversions exclude facility capacity and use only the positive net increase after combining operator additions and deductions. Degenbrecher converts first; Jaye calculates his deduction from efficiency including Degenbrecher’s conversion but excluding Swire’s conversion; Swire then converts the remaining net increase. General, experience, gold and Originium production are labeled separately; recipe-specific results include general output and are not added together. Aegis is a core operator and contributes power-station charging when selected. Capacity conflicts suppress totals. Threshold conversions count complete groups and expose their arithmetic.

Skland refresh reads facility conditions from the roster response when present, otherwise from a bounded request to player/info for the same bound role. Only normalized counts and levels join the atomic roster snapshot; the additional response's identity and status data are not saved. Optional facility-read failure preserves successful roster synchronization. The shared validated payload cache supplies both progression and conditions with one file read per version. The authenticated building-skill snapshot includes base_conditions. The page fills available trade, manufacture and power counts, extra recruitment slots derived from office level, reception level and the highest dormitory level. Missing fields do not become zero or erase other condition values. Reopening the page without facility data uses defaults.

The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the public boundary. [Calculator tests](../../../../ui/src/utils/baseGroupEstimates.test.js) cover formulas, modes, Jaye progression priority and fallback stage, accessory exclusion, facility capacities, defaults and input isolation. [Component tests](../../../../ui/src/components/BaseGroups.test.js) cover default selection, filtering, condition updates and storage isolation. [Snapshot tests](../../../../arknights_mower/tests/building_skills_tests.py) cover shared reads, office levels and highest dormitory levels. [Refresh tests](../../../../arknights_mower/tests/cultivate_depot_tests.py) cover same-role requests, failure isolation, concurrent refresh order and inventory preservation.

The [base combination calculations](https://www.bilibili.com/read/cv39359110/) give a promoted Jaye, SilverAsh and Swire example with Gnosis in the Control Center: 25% base skill efficiency, 18×4% from Jaye after deducting two orders, and 8×4% from Swire, totaling 129%. Focused regressions also verify 125% for Degenbrecher, SilverAsh and Swire with Gnosis; 121% for promoted Jaye, SilverAsh and Degenbrecher with Gnosis; and 145% for unpromoted Jaye with SilverAsh and either Swire or Degenbrecher.

## Alternatives considered

Parsing numbers from rich skill descriptions cannot express replacements, conditions or cross-facility relationships, so explicit pure rules own estimates. Adding accessory skills directly would misattribute other-facility output, so accessories provide roster conditions only.

## Consequences

Formula fixtures, reactive condition tests, changed-file lint and the production build pass. Browser verification confirms selection, unavailable-progression messages, manual conditions, two-factory hunter output, compact portraits, skill-label-only hover and no horizontal overflow. Existing build dependency and chunk-size warnings remain.
