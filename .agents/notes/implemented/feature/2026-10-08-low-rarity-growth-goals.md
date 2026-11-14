---
title: Low-rarity growth goals
status: implemented
category: feature
date: 2026-10-08
---

# Low-rarity growth goals

Owned one-, two- and three-star operators appear in the existing growth-planning list. Resource definitions determine their valid promotion phases, level caps and available skill upgrades. Three-star operators can plan elite-one progression and basic skill levels one through seven; one- and two-star operators expose only their supported level targets. Unsupported mastery and module controls remain absent.

The implementation reuses the current goal store, shared material budget and crafting preparation. Valid target derivation replaces the assumption that every listed operator can reach elite two. Basic-skill planning is independently selectable when supported, without requiring a mastery plan. Shared prerequisites and costs still count once under [INV-GROWTH-01], and invalid promotion or skill targets are rejected before saving.

Personal operator statistics cover every rarity from one through six and start collapsed. Each rarity exposes its actual maximum phase and level, and whether mastery and modules apply. Full growth means the resource-defined cap, including elite-zero level thirty for one and two stars and elite-one level fifty-five for three stars. New historical snapshots include these rarities; older snapshots with missing low-rarity metrics are not backfilled with zero or fabricated trend points. Expanding the statistics leaves growth plans and public survey state unchanged.

Recommendations expose resource-derived `level_goals` entries with id, elite phase, level, label and material summary. The discrete level slider is the only level-target control. One- through three-star operators show only unplanned and full-growth nodes, with actual maxima of elite-zero level thirty for one/two stars and elite-one level fifty-five for three stars. Dragging changes a local draft; releasing, clicking a node or changing the selection with the keyboard saves automatically. Separate apply and full-growth buttons are absent, and arbitrary numeric targets are not introduced. Three-star basic-skill planning uses `skill7` with its actual minimum elite-one level-one prerequisite, which remains internal even though it is not a visible slider node. It is shared with any explicit promotion goal and remains required when the explicit level target is cleared. The four survey dimensions use capsule-style segmented selectors with fixed percentage nodes ordered 90, 80, 70, 60, 50, 40, 30, 20, 10 and 0.325 from left to right. Clicking selects a node and clicking the selected node again clears it; no manual numeric input or continuous percentage slider is provided. Idle filtering remains available.

Focused offline tests cover low-rarity catalog inclusion, actual maximum targets, three-star promotion and basic-skill costs, rejection of unavailable targets, all-rarity statistics, missing historical values, and the default collapsed statistics surface. No additional calculator or parallel planning state is introduced.

The [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns target ids, capability flags and display semantics.
