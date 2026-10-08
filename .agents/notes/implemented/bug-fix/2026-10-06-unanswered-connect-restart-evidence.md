---
title: Unanswered Connect Restart Evidence
status: implemented
category: bug-fix
date: 2026-10-06
---

# Unanswered Connect Restart Evidence

## Symptom

A shared ADB server that stops answering the host handshake never recovers. Every recovery cycle logs `设备恢复暂停，30 秒后重新检查所选目标：共享 ADB 握手无法验证，保留现有监听` and the selected emulator stays unusable until an external tool restarts the service. The observed incident repeats this warning for twenty-eight minutes while the service remains unreachable.

## Root cause

`probe_adb_server` distinguishes two timeout phases. A timeout while receiving the host reply raises `SharedADBHandshakeTimeout`; a timeout during the TCP connect raised a plain `SharedADBError`.

`SharedADBRecovery._require_host_timeout` admits only `SharedADBHandshakeTimeout` as host-failure evidence and raises `共享 ADB 握手无法验证，保留现有监听` for every other probe error. A connect-phase timeout therefore aborted recovery on its first observation, before `_failed_probes` and `_failed_since` were updated. Neither the sustained-failure window nor the restart decision was ever reached, so the coordinator never stopped the stalled service.

The classification was inconsistent with what the observation proves. A completed TCP connect without a reply and a connect that never completes both describe an unanswered host handshake. A timeout alone distinguishes neither a stalled listener nor an absent service whose connection refusal arrives after the probe budget.

Classifying both phases as restart evidence fixes the early abort but leaves another recovery failure. The coordinator's one-second observations can expire before a local connection refusal arrives. After a successful stop, `_wait_absent` continues to see timeouts instead of absence and exhausts the Recovery Budget. `_start` rejects that same unconfirmed observation before issuing startup.

## Contract

[INV-DEV-19] Shared ADB Recovery and [INV-05] Shared ADB Guard retain their existing guarantees. The [Device Control contract](../../../../docs/subsystems/device-control.md#3-subsystem-invariants) owns the full observation, coordinated restart and startup rules. [INV-SCHED-39] retains pending tasks under the [scheduler recovery contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants).

An unanswered connect remains uncertain until an independent listener query confirms absence. This distinguishes a delayed local connection refusal from an existing listener that supplies restart evidence. Extending the socket timeout alone cannot resolve a service that stays absent while connection observations continue to time out.

A malformed reply, premature response closure or response-stage timeout never uses native absence confirmation. This preserves evidence from a connection that reached a live process. A refused connect remains the raw socket probe's only absence result; the coordinator also accepts confirmed absence from successful Windows listener queries.

The [verified listener stop decision](2026-10-07-verified-adb-listener-stop.md) extends the protocol-stop boundary. A timed-out stop permits its verified Windows process fallback; an unverified or failed fallback preserves the recorded attempt, cooldown and startup refusal.

[INV-05] Shared ADB Guard remains unchanged: implicit `kill-server` stays prohibited and the explicit host-recovery boundary remains the only route that stops the shared service.

## Implementation

`probe_adb_server` reports both timeout phases as `SharedADBHandshakeTimeout` through one handler and records `phase` as `connect` or `response`. It keeps `SharedADBError` for malformed responses, premature closure, invalid protocol versions and non-timeout connect failures. Exceptions without phase metadata retain their existing recovery behavior.

`server_process.adb_listener_absent` reads bounded IPv4 and IPv6 owner tables without opening or terminating processes. The IPv6 record layout uses native `ctypes` alignment. Query errors never confirm absence, and any IPv6 listener on the shared port preserves possible dual-stack occupancy.

`SharedADBRecovery._observe` supplements only connect-phase timeouts with that query. It passes the enclosing deadline and cancellation checks through `remaining`; budget exhaustion and cancellation clear failed-host evidence before any mutation. `_wait_absent` and `_start` share this classification and obtain fresh evidence instead of trusting a stop acknowledgement or a previous absent observation.

`SharedADBRecovery` keeps the sustained-failure window, host-shared lock, persisted cooldown, locked re-probe and attempt generation. Confirmed absence takes the existing startup path without a stop; unresolved observations retain the coordinated restart gates.

## Concept impact

[INV-06] assessment preserves the names, meanings and boundaries of Shared ADB Guard, Recovery Budget and Instance Binding. Native listener observations extend implementation evidence inside the existing recovery coordinator; they add no persisted selections or domain concepts. The glossary requires no change.

## Verification

`adb_server_tests.py` verifies the shared timeout classification and phase metadata while preserving refused-connect, malformed-response and non-timeout failure behavior.

`adb_shared_server_tests.py` reproduces a local refusal delayed beyond the one-second probe. It verifies successful cold startup and startup after acknowledged or verified process stops, changed pre-start evidence, failed native queries, response-timeout isolation, cancellation and budget exhaustion. Two application sessions use the production coordinator, native-query boundary and session ADB adapter to verify same-target registration and helper reconstruction after service loss. Existing sustained-failure, cooldown, unverified-stop and cross-process lock regressions remain in this suite.

`adb_server_process_tests.py` substitutes both native tables and process APIs. It verifies empty tables, IPv4 and IPv6 listeners, unrelated records, query failures, truncated IPv6 records and enclosing-budget cancellation without opening process handles. Existing verified-termination regressions remain intact.

Focused verification also includes `adb_shared_transport_tests.py`, `device_adb_recovery_tests.py` and `scheduler_recovery_preservation_tests.py` for shared routing, application recovery and pending task preservation.

The six named offline suites pass with 397 tests and 22 subtests. Repository-wide Ruff lint and format checks pass, and `git diff --check` passes. `python scripts/verify_governance.py` passes with two existing archived test-reference compatibility warnings. Standards and requirements review find no unresolved defects. Native API, socket and helper substitutions bound this evidence; live-device behavior is not tested.
