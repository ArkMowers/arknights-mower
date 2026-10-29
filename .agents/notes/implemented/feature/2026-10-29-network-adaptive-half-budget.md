---
format: decision
title: Qualify network compensation against half of each original base
status: implemented
category: feature
date: 2026-10-29
---

# Qualify network compensation against half of each original base

[中文](2026-10-29-network-adaptive-half-budget.zh.md)

## Problem

The same network response can threaten a short Grandet confirmation buffer while remaining comfortably inside a longer page-wait timeout. A nine-second response matters differently to a fifteen-second run-order buffer, a thirty-second page-wait timeout and a fifty-second run-order buffer. Filtering observations through one fixed definition of a slow response loses this distinction before the caller can judge its own timing.

Users need temporary protection during recurring network delays without changing their saved timings or treating a local loading screen as network trouble. They also need a predictable rule for why an observation changes one use but leaves the other unchanged. The existing independent switches, bounded waiting and original-roster restoration remain responsible for their own behavior.

## Decision

Use a fixed one-half qualification threshold for each compensation purpose, based on that purpose's original user setting. The [Arknights Mower Recognition Subsystem Description](../../../../docs/subsystems/recognition.md#network-adaptive-waits) owns raw observation collection, qualification, independent consumption and waiting bounds. The [Arknights Mower Base Scheduling Subsystem Description](../../../../docs/subsystems/base-scheduler.md#run-order-network-adaptation) owns the selected run-order buffer and its application to queue entry and confirmation. The fraction is not a new configuration field.

Keep raw explicit network durations in the shared instance history. Apply the half-base comparison when a consumer selects compensation, not when recording the observation. A recorded duration equal to the threshold qualifies. Thus a nine-second record can increase a fifteen-second Grandet buffer to twenty-four seconds while an ordinary thirty-second scene timeout remains thirty seconds; a fifty-second Grandet buffer also stays fifty seconds. Qualification uses the uncapped duration, then compensation caps the selected duration at 120 seconds. No fixed five-second margin is added. This preserves each user's original timing as the baseline and measures a delay relative to the room the user has already allowed for it.

Each purpose first finds the latest record meeting its current threshold and then checks consumption. A newer short record cannot hide an earlier qualifying record. If the latest qualifying record is already consumed for that purpose, there is no fallback to older records. Failed qualification and planning do not consume evidence. Run orders and scene waiting consume independently, so one cannot silently remove the other's opportunity or repeatedly claim old history.

Evidence comes only from continuous `CONNECTING` or visible `login_connecting` text, including the logical `LOGIN_CONNECTING` source within the login-loading scene. General loading and publisher screens may use existing protection but create no evidence. Source changes restart measurement; separate short waits are not summed. A timeout records only an observed lower bound and still has to pass each purpose's own threshold. Within a running order, `CONNECTING` inherits the already selected run-order allowance without a second half-base check; all three supported wait recipients can independently use a qualifying scene-wait allowance, even with global adaptive waiting off. The temporary scope uses their maximum rather than adding them.

The two switches remain independent and default to off. History is transient, bounded to fifteen minutes and 1024 observations, and saved base timings are not rewritten. The existing concepts and their boundaries remain unchanged; no glossary edit is needed. [Configuration controls](../../../../ui/src/components/TaskSettingsPanels.vue) explain the fixed fraction and examples for both standalone and manager-launched instances.

## Alternatives considered

- **A fixed ten- or five-second collection threshold:** A ten-second filter drops the nine-second observation before the fifteen-second run-order buffer can use it. Lowering the filter to five seconds still applies one absolute definition to different user timings and can compensate a fifty-second buffer for a comparatively small delay. Recording raw evidence and deciding at consumption preserves the relevant difference.
- **A fixed one-third threshold:** This makes a fifteen-second buffer react from five seconds rather than seven and a half. The selected half-base rule requires a larger relative delay before extending the next operation. This is a deliberate conservative choice, not a claim that one half is statistically optimal.
- **A configurable fraction:** Another control would require users to tune a ratio without enough real network evidence to guide that choice. Keep the two feature switches and their original timing settings; reconsider configurability only if later device observations demonstrate materially different needs.
- **Filtering collection with a consumer's half-base threshold:** The collector would discard an observation that another purpose, or a later smaller base, could use. Collection stays independent of qualification.
- **Adding five seconds to every selected observation or treating every timeout as eligible:** The extra time has no measured basis, while a timeout proves only that a response had not finished by the observed time. Both choices can enlarge another purpose's timing despite failing its own threshold.

## Consequences

A small relative delay leaves the next operation unchanged, even if the observation was a timeout under a shorter source timeout. Explicit-source collection avoids extending protection from ordinary local loading, but cannot attribute network delays without recognized evidence. The bounded history can evict old observations under unusually frequent waits, and process restart clears this transient evidence. One-use consumption and expiry prevent a single old incident from authorizing an indefinite series of extensions.

Increasing a maximum waiting allowance does not make a recovered page wait for the whole allowance. Compensation also does not establish that an order was missed, guarantee network recovery or repair unrelated recognition errors. Original-roster restoration, caller-controlled timeout recovery and finite episode budgets remain necessary.

Revisit the fixed fraction using real-device response durations, relevant original buffers, missed-run outcomes and timeout or restart outcomes. Offline boundary tests establish the selected rule, not the best ratio for all networks. A different ratio or an additional control needs evidence that the current fixed choice consistently misses useful protection or extends ordinary operations too often.

## Verification

On 2026-10-29, the focused `venv/Scripts/python.exe -m pytest` run passed 600 tests and 33 subtests across sixteen files after integration with alpha at `9dba661968a5a8eb4232e360bf2f765eb881fab5`. It covered the three adaptation suites, adaptive configuration and profiles, run-order windows, confirmation, restoration and restoration progress, countdown reading, staffing admission, entry, startup, arrangement refresh, planning wakeup and the main-loop news checker. This includes exact half thresholds, nine-second observations against different original bases, raw-duration comparison before the cap, independent consumption, temporary run-order waiting protection and retained tasks whose base setting changes before execution.

From `ui/`, `node node_modules/vitest/vitest.mjs run src/components/TaskSettingsPanels.navigation.test.js src/stores/configNetworkAdaptive.test.js src/task-workflow/model.test.js` passed 105 tests. Ruff, targeted ESLint, Prettier and `git diff --check` also passed. Structural verification is separate: `venv/Scripts/python.exe scripts/verify_governance.py --base HEAD` checks bilingual decision structure, relative document links and restricted terms. It does not verify runtime behavior or an optimal network threshold.

The relevant offline checks are [raw history and qualification](../../../../arknights_mower/tests/network_adaptation_tests.py), [scene waiting](../../../../arknights_mower/tests/waiting_network_adaptation_tests.py), [run-order timing](../../../../arknights_mower/tests/run_order_network_adaptation_tests.py), [configuration persistence](../../../../arknights_mower/tests/network_adaptive_config_tests.py), [frontend saves](../../../../ui/src/stores/configNetworkAdaptive.test.js) and [actual control bindings](../../../../ui/src/components/TaskSettingsPanels.navigation.test.js). They provide verification entry points; their presence alone is not a pass. Live-device improvement and an optimal ratio are not established by these offline checks.
