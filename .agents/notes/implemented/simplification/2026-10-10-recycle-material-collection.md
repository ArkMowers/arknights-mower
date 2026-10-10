---
title: Recycling Material Collection
status: implemented
category: simplification
date: 2026-10-10
---

# Recycling Material Collection

## Contract

[INV-REC-10] requires the recycling icon and collection badge in the base to-do footer before collecting material output. The existing fifteen-minute collection cooldown applies. The shared `Scene.MATERIEL` transition dismisses the reward; the next observed scene determines navigation back to the base.

## Simplification Audit

`BaseSchedulerSolver.todo_list` has two production callers: normal scene dispatch and `EmergencyRecoveryMixin._emergency_collect`. Its per-resource `while` loop increments a local counter and immediately breaks after its first tap. A single `if` preserves one tap per resource and removes the redundant loop and counter. No public interface consumes those locals.

The recycling prompt joins the existing collection map. Its 78×78 icon template includes the collection badge and uses the footer search region at the existing correlation threshold of 0.9. The reward already matches `materiel_ico`; no additional scene or dismissal handler is necessary. Existing domain definitions cover this recognition change.

## Verification

Offline fixtures preserve the three supplied 1920×1080 screenshots. Tests cover base, to-do and reward scene recognition, recycling collection and reward dismissal through the actual scene graph, quantity changes, horizontal footer movement, missing badges, other collection icons, matches outside the footer, cooldown boundaries and one tap per resource. Device capture and input use mocks.

## Standards Findings

Pass. [INV-REC-10] is registered in the subsystem specification, coding standards and review checklist. Recognition uses the standard Capture Frame and existing matching threshold. Collection adds no device lifecycle, configuration or scheduling policy change. Governance, lint and formatting checks pass.

## Spec Findings

Pass. The supplied to-do screenshot collects the recycling output once. The reward screenshot follows the existing confirmation transition and returns to the base without restarting the game. The focused collection, automatic rescue, navigation recognition, recycling facility and governance suites pass 292 tests, including 20 collection tests. Verification uses no live device.
