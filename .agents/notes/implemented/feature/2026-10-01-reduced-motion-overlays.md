---
format: decision
title: Reduced Motion for Drawer and Tooltip
status: implemented
category: feature
date: 2026-10-01
---

# Reduced Motion for Drawer and Tooltip

## Problem

Drawer and Tooltip transitions continue under the reduced-motion preference unless their runtime styles are overridden.

## Decision

The styles are in [mower.css](../../../../ui/src/theme/mower.css).

Under `prefers-reduced-motion: reduce`, the naive-ui Drawer panel, its mask and the Tooltip skip their enter and leave transitions and land on the end state. `ui/src/theme/mower.css` sets `transition: none !important` on their `*-transition-enter-active` and `*-transition-leave-active` classes. With no transition duration, Vue's `<Transition>` finishes on the next frame and still fires `after-enter` and `after-leave`, so the Drawer's focus trap and unmount follow their normal path.

## Boundary

naive-ui inserts its component styles at runtime after `mower.css`, so a rule of equal specificity loses. `!important` overrides the Drawer slide and Tooltip scale transitions. The mask's `fade-in` transition already carries `!important`, so its selector adds a `.n-drawer-container >` parent to win on specificity. The selectors carry no `.provider` prefix because both components teleport to `body`. Other overlays (Modal, Popover, Dropdown, Message) keep their transitions.

## Alternatives considered

Equal-specificity overrides lose to styles inserted later by naive-ui. The selected selectors and priority rules address that observed ordering.

## Consequences

The overrides depend on naive-ui transition class names and affect only Drawer and Tooltip; other overlays retain their transitions.

## Verification

The original record reports the following verification results.

In headless Chrome against the dev server, with `prefers-reduced-motion` emulated, the mobile page drawer and a collapsed-sidebar tooltip report a computed `transition` of `none` during `enter-active`, and both reach `translateX(0)` and `scale(1)` with opacity 1 within one frame. Without the preference they keep the 0.3 s slide, 0.2 s mask fade and 0.15 s scale.
