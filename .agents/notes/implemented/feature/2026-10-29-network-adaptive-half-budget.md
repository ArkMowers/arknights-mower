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

Keep the original setting as each purpose's baseline and qualify compensation strictly above half of that baseline. The [Arknights Mower Recognition Subsystem Description](../../../../docs/subsystems/recognition.md#network-adaptive-waits) owns raw observation collection, qualification, ordinary-wait consumption and waiting bounds. The [Arknights Mower Base Scheduling Subsystem Description](../../../../docs/subsystems/base-scheduler.md#run-order-network-adaptation) owns per-task binding, entry advancement and restoration cleanup. The two switches remain independent and default off; the fraction and allowance cap do not add configuration fields.

The earlier implementation selected the latest qualifying record, included equality at half, capped the allowance at 120 seconds and consumed each record once for run orders and once for ordinary waiting. It did not fall back to older records after the latest qualifying record was consumed. That choice kept one old incident from repeatedly granting extensions, while preventing a newer short response from hiding a qualifying observation. It also accepted visible login-connection text as evidence, protected three waiting scenes and advanced entry only when the adapted confirmation buffer plus a 45-second preparation allowance exceeded the original lead. These are historical choices, superseded by the revised behavior below; the verification figures retained below belong to that earlier implementation.

The revised requirement treats recurring network delay as evidence shared by nearby runs, while each run keeps its own temporary parameters. Therefore select the largest qualifying raw record within its own fifteen-minute lifetime. Ordinary waiting still consumes one unconsumed record per episode, but one run finishing does not remove protection already bound to another. The scheduler binds all eligible runs within twenty minutes when a network wait ends, rather than tying compensation to a later queue lookup or an extra periodic check. Started runs freeze their selected allowance through required original-roster restoration; only their own successful restoration clears it. This addresses successive runs in the same period without renewing shared evidence merely because it was referenced.

The user selected strict comparison, a ninety-second allowance cap and `CONNECTING` as the sole observation source. Keep the full measured duration before qualification and capping; a timeout remains only an observed lower bound. Login and unknown scenes are excluded from both collection and adaptive waiting, avoiding reliance on publisher or startup delays as network evidence. `LOADING` receives existing compensation without creating evidence. Both supported scenes inherit a compensated run's frozen allowance throughout its independent waits, even with global adaptive waiting off, because earlier confirmation alone does not prevent a subsequent wait timeout. An enabled ordinary-wait allowance and the run allowance use their maximum, not a sum. Separate `CONNECTING` segments are not added together, and protected waits continue to produce fresh measurements for later runs.

The revised entry rule uses the adapted confirmation buffer's share of the original entry lead: at or above half, increase that run's lead by the full adapted buffer. This replaces the earlier fixed preparation allowance with the user's chosen relationship between confirmation and entry. Repeated binding starts from the original appointment, not the previously advanced time. The cap and each continuous episode's finite budgets bound extensions; neither ninety seconds nor one half is claimed to be statistically optimal.

History remains transient and bounded to fifteen minutes and 1024 observations. A shorter later record does not extend a larger earlier record's lifetime. Saved base timings and the existing domain concepts remain unchanged; no glossary edit is needed. [Configuration controls](../../../../ui/src/components/TaskSettingsPanels.vue) explain the source, strict threshold, maximum selection and per-run scope for standalone and manager-launched instances using the same names as the logs.

## Alternatives considered

- **A fixed ten- or five-second collection threshold:** A ten-second filter drops the nine-second observation before the fifteen-second run-order buffer can use it. Lowering the filter to five seconds still applies one absolute definition to different user timings and can compensate a fifty-second buffer for a comparatively small delay. Recording raw evidence and deciding at consumption preserves the relevant difference.
- **A fixed one-third threshold:** This makes a fifteen-second buffer react from five seconds rather than seven and a half. The selected half-base rule requires a larger relative delay before extending the next operation. This is a deliberate conservative choice, not a claim that one half is statistically optimal.
- **A configurable fraction:** Another control would require users to tune a ratio without enough real network evidence to guide that choice. Keep the two feature switches and their original timing settings; reconsider configurability only if later device observations demonstrate materially different needs.
- **Filtering collection with a consumer's half-base threshold:** The collector would discard an observation that another purpose, or a later smaller base, could use. Collection stays independent of qualification.
- **Adding five seconds to every selected observation or treating every timeout as eligible:** The extra time has no measured basis, while a timeout proves only that a response had not finished by the observed time. Both choices can enlarge another purpose's timing despite failing its own threshold.

## Consequences

A small relative delay leaves the next operation unchanged, even if the observation was a timeout under a shorter source timeout. Sole-source collection avoids attributing ordinary loading or login delays to the network, but misses delays without recognized `CONNECTING` evidence. The bounded history can evict old observations under unusually frequent waits, and process restart clears it. Ordinary waits use a record once; run bindings preserve only each already selected task's protection. Expiry prevents new bindings from continuing to use a stale incident, while the ninety-second cap and episode budgets keep waiting finite.

One incident may protect several pending runs and may remain in a task snapshot after its shared record expires. This deliberately differs from one allowance for only the next run. A later task outside the event-time window receives no binding unless a new observation occurs; no extra timer fills that gap. Turning off Grandet mode or switching to Drone Acceleration removes that task's inheritance. A frozen started run cannot adjust itself to a worse delay first encountered during that run, although the new measurement can protect later runs.

Increasing a maximum waiting allowance does not make a recovered page wait for the whole allowance. Compensation also does not establish that an order was missed, guarantee network recovery or repair unrelated recognition errors. Original-roster restoration, caller-controlled timeout recovery and finite episode budgets remain necessary.

Revisit the fixed fraction using real-device response durations, relevant original buffers, missed-run outcomes and timeout or restart outcomes. Offline boundary tests establish the selected rule, not the best ratio for all networks. A different ratio or an additional control needs evidence that the current fixed choice consistently misses useful protection or extends ordinary operations too often.

## Verification

Historical verification of the earlier latest-record and one-use implementation: on 2026-10-29, the focused `venv/Scripts/python.exe -m pytest` run passed 600 tests and 33 subtests across sixteen files after integration with alpha at `9dba661968a5a8eb4232e360bf2f765eb881fab5`. It covered the three adaptation suites, adaptive configuration and profiles, run-order windows, confirmation, restoration and restoration progress, countdown reading, staffing admission, entry, startup, arrangement refresh, planning wakeup and the main-loop news checker. This included equality at half, nine-second observations against different original bases, raw-duration comparison before the cap, independent consumption, temporary run-order waiting protection and retained tasks whose base setting changed before execution. Those results do not establish the revised policy described above.

For that earlier implementation, `node node_modules/vitest/vitest.mjs run src/components/TaskSettingsPanels.navigation.test.js src/stores/configNetworkAdaptive.test.js src/task-workflow/model.test.js` from `ui/` passed 105 tests. Ruff, targeted ESLint, Prettier and `git diff --check` also passed. Structural verification is separate: `venv/Scripts/python.exe scripts/verify_governance.py --base HEAD` checks bilingual decision structure, relative document links and restricted terms. It does not verify runtime behavior or an optimal network threshold. Updated checks must distinguish the new strict boundary, largest-record selection, multiple task bindings and restoration scope from those historical results.

The relevant offline checks are [raw history and qualification](../../../../arknights_mower/tests/network_adaptation_tests.py), [scene waiting](../../../../arknights_mower/tests/waiting_network_adaptation_tests.py), [run-order timing](../../../../arknights_mower/tests/run_order_network_adaptation_tests.py), [configuration persistence](../../../../arknights_mower/tests/network_adaptive_config_tests.py), [frontend saves](../../../../ui/src/stores/configNetworkAdaptive.test.js) and [actual control bindings](../../../../ui/src/components/TaskSettingsPanels.navigation.test.js). They provide verification entry points; their presence alone is not a pass. Live-device improvement and an optimal ratio are not established by these offline checks.
