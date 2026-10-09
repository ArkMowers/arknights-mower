---
title: Held Swipe Capture
status: implemented
category: simplification
date: 2026-10-09
---

# Held Swipe Capture

## Contract

[INV-DEV-24] Held Swipe Capture: Selection page swipes acquire one Capture Frame during a shared 400 ms minimum endpoint hold, release the owned touch before reporting capture failure or cancellation, and never recover or replay input while held.

## Simplification audit and implementation

The four production selection-page callers share `BaseMixin.swipe_agent_page`. The existing `AgentPageObservation` carries the held frame to fast selection without a second capture. Slower profiles retain fresh-frame stability checks. The change reuses synchronous capture and existing input budgets instead of adding a capture thread, queue or separate selection engine. Other gesture paths retain their capture behavior; no-inertia gestures use the same 400 ms endpoint hold.

A single optional endpoint callback reaches the selected MuMu IPC, scrcpy or MaaTouch helper. Capture starts 100 ms after reaching the endpoint and the remaining hold follows capture. A slow capture extends the hold within the existing input budget. The callback collects errors until release finishes; release failure retains the structured uncertain-input verdict. Release of an already held touch has a separate one-second cleanup allowance and does not replay a gesture. Existing Capture Frame terminology covers this interface without glossary changes.

See the [device contract](../../../../docs/subsystems/device-control.md) and [scheduler contract](../../../../docs/subsystems/base-scheduler.md).

## Verification

Offline tests cover capture before release, all three input helpers, shared hold timing, cancellation and capture failure, release failure, fresh frame cache invalidation and reuse by fast selection. Focused device, selection and governance suites verify surrounding contracts.

## Standards Findings

PASS: The implementation retains the selected input backend and Instance Binding, registers [INV-DEV-24] in all three governance locations, reuses existing page observations and introduces no capture thread or glossary wording. Capture failures follow release; uncertain release remains a structured input failure without replay.

## Spec Findings

PASS: Selection page gestures acquire the held frame and every no-inertia gesture uses a 400 ms endpoint hold. Fast selection consumes the held frame once; slower selection retains fresh-frame stability checks. Verification is offline and does not establish live-device reproduction of the supplied incident.
