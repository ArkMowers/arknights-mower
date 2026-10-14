---
format: decision
title: Prefer dormitory isolation during admission
status: implemented
category: feature
date: 2026-10-14
---

# Prefer dormitory isolation during admission

## Problem

The supplied October 14 logs load an isolation group containing 机械师, 逻各斯 and 电弧, but admit 机械师 beside the fixed dormitory replacement 电弧. The previous admission logic compared the displaced resident's recovery deficit before isolation, and the original optimizer protected every single-target bed and existing resident. A different dormitory has an eligible ordinary bed, so capacity alone does not explain the cohabitation.

The [original isolation decision](../../implemented/feature/2026-10-05-dormitory-isolation-groups.md) and [manual bed-order decision](../../implemented/feature/2026-10-08-manual-dorm-priority.md) deliberately keep isolation subordinate to recovery order. This decision replaces that ordering and exchange boundary while retaining their configuration persistence, shared admission scoring and reservation responsibilities.

## Decision

The user confirms that isolation takes precedence over a new arrival's single-target position. [Projected Dormitory Isolation](../../../../docs/subsystems/base-scheduler.md#projected-dormitory-isolation) owns the expanded behavior. Admission may exchange new arrivals and existing ordinary-bed residents, including moving a new single-target recipient to another dormitory's ordinary bed. Fixed staffing, existing single-target residents, exclusions, reservations and explicit backup slots remain protected.

Isolation does not remove occupants or bypass admission capacity and takeover eligibility. Among equally isolated arrangements, recovery tiers select the feasible recovery allocation. An idle resident therefore does not automatically inherit the new arrival's single-target bed when a suitable primary can use it. The exchange search accepts only an improvement in cohabitation or, without increasing cohabitation, recovery allocation. It uses projections and the existing execution-time recovery refresh rather than a new correction task.

The implementation and focused offline coverage are present in the working tree. The user approved the exact bilingual glossary changes, which now define the same isolation boundary.

## Alternatives considered

- Retaining isolation as the last tie-breaker preserves the old position guarantees but repeats the reported arrangement despite an available alternative.
- Moving the new arrival to an ordinary bed and giving its target bed to the first idle resident separates the group but ignores a higher-tier eligible primary. The user explicitly questions this outcome; recovery-tier comparison remains necessary after isolation.
- Moving fixed covers or creating a later isolation correction would change explicit staffing or add avoidable extra arrangements. Admission-time exchanges preserve those boundaries.

## Verification

The [isolation regressions](../../../../arknights_mower/tests/dorm_isolation_tests.py) exercise takeover ordering, existing ordinary-bed swaps, a new target yielding to an ordinary bed, recovery-tier selection, projection isolation, unchanged actual deadlines and refreshed projected deadlines. Complete-shift coverage keeps 电弧 fixed and selects a primary rather than 安哲拉 for the vacated target. The regressions also verify named, positional, product and explicit backup reservation protection and the absence of a separate isolation correction for already admitted residents.

The current working tree passes 564 focused offline tests across isolation, stable recovery allocation, protected beds, complete shifts, recovery confirmation, state restoration, pending execution and rescue filling. Ruff and all three structural document checks pass. Static review follows every isolation caller and confirms that ordinary filling, complete shifts and rescue pass their named and positional reservations. No live-device outcome is claimed.

## Consequences

The user accepts slower ordinary recovery for a new arrival when it avoids same-group cohabitation. Existing ordinary residents may move during that admission, so affected rooms require fresh timing and changed targets require normal single-target confirmation. The bounded pair-exchange search may leave unavoidable or locally irreducible cohabitation and never delays admission to search indefinitely. Independent zero-mood countdown behavior observed in the supplied logs is outside this change.
