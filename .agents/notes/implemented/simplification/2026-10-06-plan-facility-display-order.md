---
title: Plan Facility Display Order
status: implemented
category: simplification
date: 2026-10-06
---

# Plan Facility Display Order

## Contract

[INV-UI-08] binds the office/training display order to the existing local `swap_contact_train` setting. Every main and backup plan retains its facility identities and assignments. Plan transfer carries neither the display order nor the setting. Existing backend facility positioning remains unchanged.

## Simplification

Two duplicated card structures share one keyed rendering loop. The component computes the two facility identities in display order and retains the training-slot labels, avatars, selection handler and update-drop exclusion. No additional settings, persisted plan fields or backend changes are introduced.

## Verification

Rendered-component tests toggle the existing setting in both plan types, verify avatar order and unchanged serialized plans, and check that exported advanced settings exclude the field. Focused configuration-backup and update-drop tests verify adjacent contracts. The frontend build supplies the local static assets.

## Standards Findings

PASS: one keyed loop replaces two repeated card structures. Facility selection and assignments retain their original identities, and update-drop exclusion remains on both cards. No plan schema or backend changes occur. Test lint passes; the component retains 13 existing lint errors, reduced from 15, with no new findings. Governance and its 14 focused tests pass.

## Spec Findings

PASS: 24 focused frontend tests cover both plan types, repeated setting changes, unchanged serialized data and existing backup/drop behavior. `npm run build` succeeds and updates `ui/dist`, the local server's static asset directory. The generated plan chunk includes both display orders, and its compressed copy matches. Existing table-markup and chunk-size build warnings remain.
