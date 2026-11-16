---
format: decision
title: Supplied operator growth through MAA
status: implemented
category: feature
date: 2026-11-16
---

# Supplied operator growth through MAA

## Problem

Mower plans promotion and basic-skill prerequisites and prepares their materials, but these actions require manual game operations. Cloud progression can lag successful game actions. Reusing MAA's complete cultivation behavior would introduce an independent workshop and chip-production policy alongside Mower's resource reservations.

## Decision

Mower keeps growth goals and resource admission. A separate default-off switch admits supplied promotion targets and single basic-skill upgrades through MAA; skill seven requires observed elite one. Mower retains crafting and mastery. Its temporary manufacturing-line workflow supplies dual chips without moving staff. Persist confirmed progression with inventory payments and prevent lagging cloud snapshots from overwriting pending results. Stop MAA's material-shortage entries before it can synthesize or manufacture independently.

## Alternatives considered

Implementing all operator-page actions natively would also support independent level goals, but duplicates recognition and promotion/skill interactions already available in MAA. Forwarding the whole growth queue to MAA cannot preserve Mower's crafting, mastery and material-allocation responsibilities. Counting queued production as finished inventory cannot establish whether chips were actually produced.

## Verification

Passing focused offline checks cover finished-material admission, elite-one prerequisites, generation/task-bound callbacks, duplicate payment protection, cloud convergence, failure recovery and nearest-finish manufacturing selection. Existing product-switch and synchronization regressions remain applicable. MuMu observation on 2026-11-16 reads both manufacturing facilities, selects B202, uses 23 drones, manufactures one Guard Dualchip and restores gold with a 99-unit queue without moving staff. Menu-name recognition covers all eight professions; quantity recognition covers one through four in unconfirmed Guard previews. Native MAA cultivation and Android resource loading still require separate device observation.

## Consequences

MAA does not report the exact denominations of consumed battle records. Leveling-related inventory must remain unknown until observed again. A short native production can still fail or be interrupted; temporary product restoration survives that interruption. The resource overrides depend on upstream MAA task names.

The implementation and operating boundaries are maintained in [Supplied MAA Growth](../../../../docs/subsystems/growth-planning.md#maa-supplied-growth). [MAA growth tests](../../../../arknights_mower/tests/maa_growth_tests.py) exercise real admission, persistent receipts and the scheduler callback entry; existing product-switch and synchronization suites check the reused paths. The device observation covers the native dual-chip workflow only; MAA cultivation remains unverified on devices. The default-off switch permits incremental adoption.
