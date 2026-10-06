---
title: Vacant Single-Target Recovery
status: implemented
category: bug-fix
date: 2026-10-06
---

# Vacant Single-Target Recovery

## Contract

[INV-SCHED-20] preserves existing single-target residents. Admission and departure events fill vacant targets using eligible non-target residents across dormitories and current arrivals. Candidate order is identity tier, locality, then mood deficit. Equal-tier local residents avoid a second room operation; higher-tier remote residents still win.

Each vacancy exchanges only the target and selected donor beds. The chosen target stops competing immediately. No displacement chain or global reshuffle follows. Multiple vacancies are independent, while each room retains one final arrangement. Reservations, excluded residents, mandatory mood limits and actual occupancy remain authoritative.

## Simplification

The existing projected planner replaces its displacement loop with one minimum-candidate selection per vacancy. It does not add device reads, scheduled scans, caches or executor fallbacks. Complete residents are not added as recovery candidates. Idle mood changes and unrelated working plans do not trigger allocation.

## Verification

Focused tests cover existing-target stability, one-vacancy two-room bounds, local ties, higher-tier remote candidates, rear-bed candidate inclusion, reservations, completed residents, ordinary admission, release, takeover and restoration. Verification passes 648 tests and 6 subtests; Ruff and governance pass. Tests perform no live-device integration.

## Standards Findings

Pass: projected state remains isolated, swaps preserve residents, reservation guards remain in force, and the exact bilingual glossary replacement and locality addition are user-approved.

## Spec Findings

Pass: a rear-bed high-priority replacement can receive a vacant target, but cannot displace an established target. Equal-tier local candidates reduce the operation to one dormitory; a remote winner involves at most two per vacancy.
