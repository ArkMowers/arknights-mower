---
title: Verified ADB Listener Stop
status: implemented
category: bug-fix
date: 2026-10-07
---

# Verified ADB Listener Stop

## Contract

After the existing sustained unanswered-handshake window, lock, cooldown and locked re-probe authorize restart, a timed-out protocol stop permits a Windows process stop only for the shared port owner whose executable matches the selected ADB. A retained process handle prevents PID reuse from changing the termination target. Ownership and unanswered status are rechecked before termination; startup waits for confirmed port release within the existing Recovery Budget.

## Implementation boundary

Protocol rejection and malformed replies do not authorize forced termination. The Windows fallback uses native local process and TCP-table APIs without process-name searches, process-tree termination or a new dependency. Other platforms, missing access rights, ambiguous port ownership, executable mismatch and changed ownership retain bounded failed recovery with persisted cooldown and no startup.

The native stop waits for completion through the retained handle because [TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess) is asynchronous. [GetExtendedTcpTable](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable) supplies listener ownership.

## Verification

Offline tests substitute all socket, process, native API and clock operations. They cover a wedged protocol stop, exact executable validation, retained-handle cleanup, changed or reused identities, healthy re-probes, cancellation, timeout, failed termination and absence verification before startup.
