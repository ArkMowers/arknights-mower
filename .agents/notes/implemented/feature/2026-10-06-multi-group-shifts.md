---
title: Multiple Group Shift Bindings
status: implemented
category: feature
date: 2026-10-06
---

# Multiple Group Shift Bindings

Each operator retains one facility slot and multiple group/replacement bindings. The latest triggered group selects its binding. Shared operators follow shifts without contributing to group mood or recovery timing. Failed replacement or bed allocation preserves the previous binding. Legacy single-group plans retain their behavior.

[INV-SCHED-25]

## Verification

Focused tests cover legacy serialization, main and backup loading, group-specific replacements, overlapping shifts, duplicate-bed prevention, replacement and bed admission failure, saved and projected active bindings, excluded mood and recovery deadlines, ordinary correction, dormant group returns, fixed dormitory followers, retained in-slot covers, temporary bed opening and occupied-bed closure, per-group primary dormitory replacements and standby followers without a bed. Frontend tests cover independent columns, deletion, equal color segments and plan export. Browser checks confirm addition, editing and deletion in the real component. Dispatch tests select the binding before shift preparation and skip selection while an intervening task executes. Scheduling and restart fixtures supply an offline maintenance result, keeping announcement requests out of CI while the announcement-specific suite retains its own responses.

## Standards Findings

Pass. [INV-SCHED-25] is registered in the scheduling specification, coding standards and review checklist. Runtime group membership remains separate from persisted bindings and projections copy mutable maps. The exact bilingual glossary addition is approved by the user.

## Spec Findings

Pass. The plus button adds a group/replacement column; each column receives an equal avatar color segment. The latest triggered group supplies replacements; shared operators do not drive group mood or return timing. Resting standby configuration remains effective, allowing followers to leave work without reserving a bed and return with their group.
