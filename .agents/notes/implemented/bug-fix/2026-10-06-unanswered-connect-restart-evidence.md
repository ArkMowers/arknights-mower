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

The classification was inconsistent with what the observation proves. A TCP connect that completes the accept queue but receives no reply and a connect that never completes both describe a listener that answered nothing. Only a refused connect proves the port is free, and only a response proves a live process.

## Contract

[INV-DEV-19] Shared ADB Recovery supplies restart evidence from every unanswered host handshake. A listener that answered nothing within the budget supplies that evidence: the host never completed the TCP connect, the connected listener never replied, or a partially delivered reply stalled. Both observations count towards the same sustained-failure window of at least two observations over at least thirty monotonic seconds, and only that window authorizes the explicit coordinated restart.

An unanswered connect is not proof that no live process owns the port. It shows only that the service did not answer inside the budget, so it carries no more authority than an unanswered reply and still needs the full window.

A listener that answered with a malformed response, or that closed the connection before the response completed, remains a different observation. It proves a live process owns the port, so it supplies no restart evidence and preserves that process. A refused connect remains the only absence result and permits guarded startup without `kill-server`.

The [verified listener stop decision](2026-10-07-verified-adb-listener-stop.md) extends the protocol-stop boundary. A timed-out stop permits its verified Windows process fallback; an unverified or failed fallback preserves the recorded attempt, cooldown and startup refusal.

[INV-05] Shared ADB Guard remains unchanged: implicit `kill-server` stays prohibited and the explicit host-recovery boundary remains the only route that stops the shared service.

## Implementation

`probe_adb_server` reports a timeout in either phase as `SharedADBHandshakeTimeout` through one handler, and keeps `SharedADBError` for a malformed response, a connection closed before the response completed, an invalid protocol version and a non-timeout connect failure. The single handler also removed the flag that previously distinguished the phases and the duplicate raise that repeated the same verdict.

`SharedADBRecovery` keeps its existing gates: two observations, thirty monotonic seconds, the host-shared cross-process lock, the persisted wall-clock cooldown and the locked re-probe. The gates are unchanged; which unresolved observation supplies evidence is what widened.

## Verification

`adb_server_tests.py` verifies that a stalled connect and a stalled handshake both raise `SharedADBHandshakeTimeout` with one phase-neutral verdict, that a refused connect stays the only absence result, that a non-timeout connect failure stays unverified, and that malformed or truncated responses remain `SharedADBError`.

`adb_shared_server_tests.py` verifies that a connect-phase timeout accumulates inside the sustained-failure window instead of aborting, that no stop is attempted after the first two unanswered observations, that the first restart decision advances the shared generation, and that unverified process ownership retains a recorded, cooldown-bounded attempt without startup.
