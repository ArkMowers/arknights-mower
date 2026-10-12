---
title: Independent MAA Updates
status: implemented
category: simplification
date: 2026-10-11
---

# Independent MAA Updates

[中文](2026-10-11-maa-independent-updates.zh.md)

Both automatic update policies follow the [independent update admission contract](../../../../docs/subsystems/maa-integration.md#independent-update-admission), historically referenced as [INV-MAA-10].

The simplification audit finds one combined automatic-check entry point in `MaaBasic.vue` and two existing update endpoints. The policy separates eligibility inside that entry point and reuses the endpoints, mutual exclusion and rollback copies. It introduces no additional update worker or independent installer.

Core and resource updates each persist their automatic-check and automatic-install switches. New installations disable all four switches. Legacy combined checks initialize both check switches without enabling installation; explicit resource preferences survive reload. Update checks run on settings-page entry and relevant configuration changes. Automatic installation is opt-in, requires a current successful check, and uses the existing idle-engine gate. Disabling a policy or changing its target or source while a check is pending prevents automatic installation from the old response.

A valid published resource timestamp remains eligible when the local timestamp is unknown. The check receipt still binds the target, source and observed local version and is consumed once. Connection-preset reads and failed resource loads distinguish missing, malformed and read-denied configuration files. Resource merging makes only its staged replacement files writable before overlaying archive data.

The [MAA integration specification](../../../../docs/subsystems/maa-integration.md) owns the interface contract. Offline tests cover independent policies, legacy migration, unknown versions, check binding and file-access failures.

Standards and requirements review confirms independent persisted choices, stale-response rejection, existing idle-engine admission and rollback ownership. The focused policy, update-route, resource-installer, MAA-admission, connectivity and configuration suites pass. Frontend component, policy-store and partial-save suites pass 67 tests. Governance checks pass with two unchanged archived-reference warnings. The reported Windows file ACL failure requires validation on the affected machine.
