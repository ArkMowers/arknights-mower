---
title: Zero-Mood Replacement Exemptions and Validation Reuse
status: implemented
category: simplification
date: 2026-10-11
---

# Zero-Mood Replacement Exemptions and Validation Reuse

## Contract

[INV-SCHED-46] Zero-Mood Replacement Exemption: Working primaries configured for zero-mood work may omit replacements only when ungrouped or when every member of that binding is configured for zero-mood work; mixed groups and Fiammetta charging retain required replacements.

## Simplification Evidence

The manual endpoint calls `init_and_validate` before `validate_backup_plans`, which repeats baseline validation. The combination loop also validates the all-disabled baseline again and rebuilds identical effective schedules. `merge_plan` deep-copies entire backup metadata although only assigned slots need ownership separation.

Validation reuses successful effective schedules only within one invocation. Its key includes ordered facilities and slots, every binding, products, all merged configuration fields and maintenance primary slots. Declaration order and Current inheritance remain authoritative. Each distinct schedule uses the runtime checker; budget and failure semantics remain unchanged. Reported checks count actual baseline and distinct merged-schedule checks. The UI permits one in-flight manual validation request.

## Verification

Focused zero-mood, backup validation, multi-group and dormitory group tests cover exemptions, conflicting merged configurations, isolation, budgets and result reuse. Source plans and actual occupancy remain isolated. The subsystem contract owns the active behavioral specification.

## Standards Findings

Pass. [INV-SCHED-46] is registered in the subsystem contract, coding standards and review checklist. Result reuse is scoped to one invocation and bounded by the existing combination limit. Backup overlays copy only assigned slots; merged configuration remains independently copied. Existing domain definitions cover the change without glossary edits. Governance checks cover note format, relative links and avoided terms.

## Spec Findings

Pass. Ungrouped and entirely zero-mood working groups may omit ordinary replacements; mixed groups retain complete validation. Supplied ordinary candidates in entirely zero-mood working groups retain unique matching; omitted lists do not participate. Tests cover independent bindings, supplied replacement validity, Fiammetta targets, revalidation after edits, maintenance permission isolation, source isolation and the five-second budget. The repository fixture drops from 32 checks to 13; on alpha `7d31a6af`, median elapsed time across three runs drops from 126 ms to 66 ms. A nine-backup fixture with independent conditions and identical overlays drops from 512 checks to two and from 215 ms to 116 ms. Timings describe only the current offline fixtures and environment.
