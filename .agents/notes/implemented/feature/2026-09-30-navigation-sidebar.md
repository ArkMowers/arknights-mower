---
format: decision
title: Navigation Sidebar
status: implemented
category: feature
date: 2026-09-30
---

# Navigation Sidebar

[中文](2026-09-30-navigation-sidebar.zh.md)

## Problem

Separate desktop and mobile navigation definitions drift in labels and page coverage; collapse controls can overlap the scrolling list.

## Decision

Current navigation rules are owned by the [UI subtree instructions](../../../../ui/AGENTS.md#2-navigation-shell); the definition is [navigation.js](../../../../ui/src/navigation.js).

[INV-UI-04] Single Navigation Definition: the desktop sidebar, the mobile tab bar and the mobile page drawer render from `ui/src/navigation.js`. That definition lists every production page route exactly once; the development-only taskflow prototype is excluded from production navigation. Internal entries resolve to registered routes; external entries use canonical https URLs and open in a new tab without opener access.

## Original layout

This section records the initial layout. The current branding, collapse controls, saved placements and mobile tabs follow [Sidebar Layout and Editing](../../../../docs/subsystems/web-access.md#sidebar-layout-and-editing) and the [UI navigation rules](../../../../ui/AGENTS.md#2-navigation-shell); the single navigation definition remains the selected design.

The sidebar is a column: a scrolling section list above a pinned footer. The footer holds the Mower AI assistant entry and the collapse control, so the list scrollbar never overlaps a control. The collapse control is a button with `aria-expanded` and `aria-controls`, and it works identically with and without the window shell.

Collapsing keeps the icon column fixed and fades labels. A collapsed row shows its label in a tooltip on hover or keyboard focus. Section titles become dividers of equal height, so rows do not shift. The active row derives from router matching (`aria-current="page"`) instead of a stored selection.

Below 680px, a bottom tab bar lists four frequent pages and a More button. More opens a drawer containing the full sidebar and stays highlighted on pages outside the tab bar. The watermark covers the content area only. The collapse state is not persisted; widths below 850px collapse automatically until the user toggles.

## Alternatives considered

The removed duplicate navigation definitions and collapse controls are recorded in the [consolidation decision](../simplification/2026-09-30-navigation-shell-consolidation.md).

## Consequences

One definition keeps production pages reachable in both layouts. Mobile access to less frequent pages requires the More drawer; collapse state remains transient.

## Verification

The original record reports the following verification results.

`ui/src/navigation.test.js` covers route coverage, entry uniqueness, external URL form, the mobile tab subset and the More highlight. `ui/src/components/NavigationShell.test.js` renders both components under the real route table. It checks one link per entry, external link attributes, a single current entry, section labelling and the collapse control state. It also checks that every icon draws an svg; the [ES module icon imports note](../bug-fix/2026-09-30-vicons-esm-imports.md) records why icons come from `es/` files. Browser preview covers both themes, window-shell and browser modes, and mobile width. The [consolidation note](../simplification/2026-09-30-navigation-shell-consolidation.md) records the removed copies.
