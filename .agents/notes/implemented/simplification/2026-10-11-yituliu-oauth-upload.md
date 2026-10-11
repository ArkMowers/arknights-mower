---
title: Yituliu OAuth Upload
status: implemented
category: simplification
date: 2026-10-11
---

# Yituliu OAuth Upload

**[INV-GROWTH-05] Confirmed OAuth Upload**: Yituliu synchronization sends only bound game UID and validated operator fields to the fixed OAuth save endpoint with a Bearer token, and advances its success baseline only after an integer business code of 200 and complete nonnegative save counts.

The [growth contract](../../../../docs/subsystems/growth-planning.md) defines the interface. Both automatic refresh and manual synchronization call `sync_cached_operators`; `_upload` has one production caller. The existing lock, local digest and token file serve both entry points. The adapter replaces the legacy upload schema directly, removes nickname/channel validation and the legacy ownership field, and adds no parallel client or authentication store. Nickname and channel changes no longer trigger transmission because the OAuth payload excludes them.

The payload contains `playerInfo.akUid` and `operators`. Skill values combine basic skill level and mastery stage; absent skills remain zero. `potentialRank` retains the cached zero-based rank. All five equipment branches remain explicit, including zero values, because omitted fields reset to zero on the provider. A confirmed result requires created, updated and unchanged counts summing to the submitted roster size. Business failures and malformed confirmations preserve the successful digest. Known business errors produce local messages without reflecting remote text or credentials. Redirects and uncertain retries remain disabled.

Offline synchronization, refresh, settings and governance checks cover the contract. The glossary introduces no changed domain concepts.

Validation on 2026-10-11: 113 focused backend tests and 8 frontend tests pass. Ruff and frontend lint/format checks pass. Structural governance passes with two existing historical archived-test reference warnings. One authorized live upload of the existing local Skland snapshot confirms 429 updated operators, zero created and zero unchanged; a repeat local sync skips transmission and preserves the success timestamp. The supplied token has no read scope (`80008`), so the evidence is the save confirmation rather than a readback. Temporary isolated settings are removed after validation; credentials and player data are absent from the patch.
