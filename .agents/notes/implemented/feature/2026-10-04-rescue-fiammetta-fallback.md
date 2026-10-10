---
title: Rescue Fiammetta Fallback
status: implemented
category: feature
date: 2026-10-04
---

# Rescue Fiammetta Fallback

## Contract

[INV-SCHED-09] retains configured Fiammetta targets while any is below full measured mood. When every configured target is full, normal primaries without special mood caps or reservation conflicts become fallback candidates in ascending measured mood order. Unknown readings, training and workshop occupancy are excluded. Ordinary charging thresholds and warm-up restrictions remain active.

## Simplification

The existing charging planner and temporary-roster restoration execute fallback charging. A task marker permits the selected fallback through rescue filtering without modifying configured targets. Release labels display only “自动救急” in the UI and task report.

## Verification

Offline tests cover normal target precedence, lowest eligible fallback, special caps, unknown mood, reservations, normal-mode isolation and task filtering. Existing Fiammetta selection and restoration tests remain applicable.

## Standards Findings

Existing invariants and configuration remain unchanged. Glossary text has explicit user approval. No independent charge executor is added.

## Spec Findings

The exclusion follows configured mood caps rather than operator names. Missing charging configuration does not enable fallback charging.
