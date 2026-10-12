---
title: Yituliu OAuth Upload
status: implemented
category: simplification
date: 2026-10-11
---

# Yituliu OAuth Upload

**[INV-GROWTH-05] Confirmed OAuth Upload**: Yituliu synchronization sends only bound game UID and validated operator fields to the fixed OAuth save endpoint with a Bearer token, and advances its success baseline only after an integer business code of 200 and complete nonnegative save counts.

The [growth contract](../../../../docs/subsystems/growth-planning.md) defines the interface. Both automatic refresh and manual synchronization call `sync_cached_operators`; `_upload` has one production caller. The existing lock and local digest serve both entry points, while the token and sync baseline reside in the `yituliu_sync` block of `conf.yml`; the older `yituliu_sync.json` file is a one-time migration source. The adapter replaces the legacy upload schema directly, removes nickname/channel validation and the legacy ownership field, and adds no parallel client or authentication store. Nickname and channel changes no longer trigger transmission because the OAuth payload excludes them.

The payload contains `playerInfo.akUid` and `operators`. Skill values combine basic skill level and mastery stage; absent skills remain zero. `potentialRank` retains the cached zero-based rank. All five equipment branches remain explicit, including zero values, because omitted fields reset to zero on the provider. A confirmed result requires created, updated and unchanged counts summing to the submitted roster size. Business failures and malformed confirmations preserve the successful digest. Known business errors produce local messages without reflecting remote text or credentials. Redirects and uncertain retries remain disabled.

Offline synchronization, refresh, settings and governance checks cover the contract. The glossary introduces no changed domain concepts.

Validation on 2026-10-11: 113 focused backend tests and 8 frontend tests pass. Ruff and frontend lint/format checks pass. Structural governance passes with two existing historical archived-test reference warnings. One authorized live upload of the existing local Skland snapshot confirms 429 updated operators, zero created and zero unchanged; a repeat local sync skips transmission and preserves the success timestamp. The supplied token has no read scope (`80008`), so the evidence is the save confirmation rather than a readback. Temporary isolated settings are removed after validation; credentials and player data are absent from the patch.

Manual sync refreshes Skland immediately through `cultivate.start` and reuses its single `sync_after_cultivate` result. Refresh failure sends no older cached roster; successful refresh retains existing local payload validation and digest suppression. The settings description states this order directly. Offline tests cover fresh roster upload, failed refresh, missing token and one-upload behavior.

Validation on 2026-10-12 for the storage relocation: 63 focused Yituliu synchronization tests pass with the complete service route test excluded, and 27 focused configuration persistence tests pass. Python syntax compilation passes for the changed modules and focused test file. Governance checks pass with the same two historical archived-test reference warnings.

Storage review repairs reuse the configuration lock for Yituliu and workshop operations because independent locks allow a stale general-settings copy to restore a deleted token or overwrite a sync baseline. Yituliu writes stage a configuration copy and restore the previous object on failure. An explicit empty private block distinguishes a saved deletion from a pending legacy import when cleanup fails. These repairs preserve the existing domain concepts and decision lifecycle.

Review validation on 2026-10-12: ten added regression cases fail before the repair and pass afterward. All 224 focused Yituliu synchronization, workshop automation, manual configuration, preset recovery, growth crafting order and Skland refresh tests pass, including the complete service route case. Another 27 focused configuration persistence tests pass. The synchronization suite adds fifteen cases covering shared-lock ordering, failed migration/save/clear/baseline writes, retry persistence, failed legacy cleanup and general configuration saves before migration. Ruff lint and formatting, Python syntax compilation and structural governance checks pass; governance retains the same two historical archived-test reference warnings.

Further storage review finds the same explicit-state loss in advanced-settings reconstruction and a missing transaction lock in plan import. The repair remains confined to two production files: advanced-settings application copies only validated allowed fields onto the existing configuration copy, and plan import holds the existing configuration lock throughout its transaction. Running-plan restoration already holds that lock and reuses the same application function. No additional migration state or transaction abstraction is introduced. Nine added cases cover import/restoration before migration, unrelated values and explicit state, and concurrent Token clear/replacement routes; seven fail before the repair, while the two existing restoration-lock cases pass. All nine pass afterward. Focused synchronization, backup, running-plan restoration and configuration tests report 221 passed with 12 subtests; seven existing symlink cases cannot run because Windows reports missing privilege (`WinError 1314`) before their business assertions.
