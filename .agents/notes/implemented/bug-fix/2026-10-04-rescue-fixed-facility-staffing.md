---
title: Rescue Fixed-Facility Staffing
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue Fixed-Facility Staffing

## Contract

[INV-SCHED-09] includes configured workshop and training-room assignments in the effective rescue main and backup plans. Workshop capacity is one slot; training capacity is two slots. Omitted facilities remain untouched; explicit empty slots remain vacant. Ordinary facility type, level and product matching stays enforced.

## Simplification

The existing rescue resolver and staffing task include both facilities. Existing training correction protection masks unavailable slots before dispatch and reconciliation; specialized task flows retain ownership. No separate takeover task or staffing subsystem is introduced.

## Verification

Offline tests cover backup overlays, empty slots, fixed capacities, duplicate workers, complete dispatch and reconciliation, and both training assistant-follow settings. Governance checks and Vue compilation validate the contract and UI help.

## Standards Findings

Existing arrangement and training protection boundaries remain authoritative. Glossary additions have explicit approval.

## Spec Findings

Configured workshop and training staff are deployed. Protected training slots do not indefinitely block completed working-facility arrangements.
