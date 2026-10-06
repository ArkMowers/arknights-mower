---
title: Shared Group Shift Selection
status: implemented
category: simplification
date: 2026-10-06
---

# Shared Group Shift Selection

The plan editor repeats the group border expression in twelve facility views. One binding-style function supplies equal color segments to every view. The scheduler reuses its existing replacement matching and bed allocation for group followers; it introduces no separate shift engine.

[INV-SCHED-25]

## Verification

Focused tests cover legacy serialization, main and backup loading, group-specific replacements, overlapping shifts, duplicate-bed prevention, replacement and bed admission failure, saved and projected active bindings, excluded mood and recovery deadlines, ordinary correction, dormant group returns, fixed dormitory followers, retained in-slot covers, temporary bed opening and occupied-bed closure, per-group primary dormitory replacements and standby followers without a bed. Frontend tests cover independent columns, deletion, equal color segments and plan export. Browser checks confirm addition, editing and deletion in the real component.

## Standards Findings

Pass. [INV-SCHED-25] is registered in the scheduling specification, coding standards and review checklist. Runtime group membership remains separate from persisted bindings and projections copy mutable maps. The exact bilingual glossary addition is approved by the user. 

## Spec Findings

Pass. The plus button adds a group/replacement column; each column receives an equal avatar color segment. The latest triggered group supplies replacements; shared operators do not drive group mood or return timing. Resting standby configuration remains effective, allowing followers to leave work without reserving a bed and return with their group.
