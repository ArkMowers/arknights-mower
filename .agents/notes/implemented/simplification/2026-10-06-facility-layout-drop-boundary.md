---
title: Facility Layout Drop Boundary
status: implemented
category: simplification
date: 2026-10-06
---

# Facility Layout Drop Boundary

## Contract

[INV-UI-07] excludes the whole Scheduling Plan facility layout from update drops, including card descendants, fixed facilities, backgrounds and gaps. The surrounding page and editing section below the layout retain their existing drop behavior. Facility sorting and local office/training display order remain unchanged.

## Simplification

`PlanEditor`'s facility layout owns one marker. The existing global ancestor lookup applies the exclusion to all layout descendants without repeated card markers, a page-level route check or additional event handlers.

## Verification

Rendered-component tests verify one layout boundary, covered avatars and uncovered editing containers in both plan types and both office/training orders. Global-update tests verify hint cleanup and update drops after leaving the excluded region. The frontend build updates local static assets.

## Standards Findings

PASS: one ancestor marker covers the complete layout without adding event handlers, drag state or route exclusions. Changed tests and global-update code pass lint; the editor retains 13 existing lint errors with no new findings. Governance and its 14 tests pass.

## Spec Findings

PASS: 28 focused frontend tests cover rendered scope, display order, update routing and facility swaps. The local frontend build succeeds; its generated plan chunk contains exactly one layout marker, and compressed assets match the original files.
