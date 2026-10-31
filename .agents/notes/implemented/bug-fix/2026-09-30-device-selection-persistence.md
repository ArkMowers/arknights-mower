---
title: Device Selection Persistence
status: implemented
category: bug-fix
date: 2026-09-30
---

# Device Selection Persistence

## Contract

[INV-UI-03] Selected Instance Persistence requires selection of a detected instance to save its explicit identity before connection testing or startup. Connection failure preserves that choice without persisting an unverified endpoint or game package. A failed identity save prevents lifecycle actions and preserves the previous saved Device Profile. Candidate lists remain ephemeral.

## Boundary and simplification

`DeviceSettings.bindInstance` reuses `saveDiscoveredDevice` rather than maintaining another identity projection. The selected instance index and its identity verification fields persist separately from readiness. Manual identity edits remain drafts until successful validation. Startup confirmation requirements remain unchanged.

## Verification

Component tests cover multiple candidates, failed startup followed by an explicit retry, and rejected identity saves. The session test covers a new startup after an exhausted Recovery Budget: the action counter and deadline reset while the selected identity remains unchanged. A single transaction retains its original budget.
