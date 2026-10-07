---
title: Yituliu growth survey and local operator statistics
status: implemented
category: feature
date: 2026-10-07
---

# Yituliu growth survey and local operator statistics

Growth planning presents locally computed operator statistics and public community survey filters in the existing Mower interface. Operator cards, selected growth goals, material budgets and execution actions retain their existing ownership. Community observations describe a sample rather than official recommendations or combat-strength rankings.

[INV-GROWTH-02] isolates the public survey from local identity, credentials and plan mutations. The backend requests `https://auth.yituliu.cn/open/ak-operator-statistics/result` without a token or local account fields. It retains a validated cache for twenty-four hours; refresh failure preserves the last valid snapshot and returns its stale state with an error. Missing or invalid metrics remain unknown. Personal statistics derive from the local owned roster and never enter the public survey request. A user-configured write-only token enables one automatic upload after each actual successful Skland refresh; reading an existing cache or saving the token does not trigger an upload. A separate manual action uploads the current cached progression immediately without retrying network requests. Public retrieval never depends on that token. Upload failure preserves the local cache and successful Skland result, and produces a separate readable synchronization status. The settings controls appear immediately below the Skland accounts in Mower settings. Credential responses expose configured state only, and credentials never appear in logs. Provider personal-profile read APIs remain outside this feature.

The fixed upload destination is `POST https://backend.yituliu.cn/open-api/operator/upload`; `Authorization` contains the raw write-only token, without a Bearer prefix. The verified provider contract is the [published OpenAPI document](https://backend.yituliu.cn/v3/api-docs). The body contains game UID, nickname, channel/server identity and `operatorDataList` progression fields only, including ownership, level, elite phase, potential, rarity, basic-skill level, mastery levels and module levels. It contains no account password, Skland credential or warehouse inventory. The local cache stores explicitly bound player identity for this upload; legacy caches without that identity require a successful Skland refresh first. Token configuration remains in a separate local configuration file with restricted permissions and is absent from the general configuration response.

The frontend uses the public observations to filter and sort locally owned operators, and keeps unavailable-data feedback separate from a true zero rate. Filtering changes only presentation. User selection and removal continue through the existing plan APIs. The personal-statistics component and survey filters replace the previous overview and general filter surface rather than adding a parallel route or duplicate planning store.

Implementation uses independently written code. A repository file named LICENSE that contains no software-license grant is not treated as permission to copy implementation. The interface attributes the survey to Yituliu, links the source and CC BY-NC 4.0 content license, and labels the observations as unofficial and not a strength ranking.

Offline verification covers credential-free requests, response validation, fresh-cache reuse, stale-cache preservation, absent rates, local personal aggregation, unchanged plans when filters change, single-upload successful-refresh hooks, manual fixed-destination uploads, upload-failure isolation and credential non-disclosure. The growth-planning subsystem contract owns the implemented interface fields and metric denominators.

The authenticated local interface consists of `GET /growth-survey`, `GET/PUT/DELETE /growth-sync-token` and manually confirmed `POST /growth-sync`. `cultivate.start` uploads the exact newly persisted snapshot once through `sync_after_cultivate`; `/cultivate-fetch` reports that upload independently. Token status returns configuration and success/failure metadata without complete or partial credentials. The token file has mode `0600`.

Personal operator, material and investment-ranking tabs aggregate one- through six-star rosters. The section starts collapsed and uses actual progression capabilities for each rarity. Shared operator forms deduplicate ownership, progression and basic-skill costs; their distinct skills and modules retain separate counts. Survey thresholds use owned-sample denominators and require complete histograms before presenting a rate. Unknown observations cannot hide an operator as completed. The [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns API fields, cache timing, metric formulas and upload behavior.

A process-shared lock serializes each complete Skland fetch, cache write and upload transaction, preserving progression ordering when refresh requests overlap. A two-thread offline test verifies that an older delayed fetch cannot upload after a newer transaction.
