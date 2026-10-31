---
title: Recoverable Device Cleanup
status: implemented
category: bug-fix
date: 2026-10-08
---

# Recoverable Device Cleanup

## Contract

[INV-DEV-22] Recoverable Owned Cleanup retains original resource owners after failed cleanup. Only unfinished cleanup repeats. Successful cleanup clears the failure before a new verified startup; unresolved cleanup continues to block replacement. Device Profile, foreign resources and shared ADB state remain unchanged.

## Boundary and simplification

A cached cleanup failure describes the last attempt, rather than current device connectivity. Device Control retains a failed Device owner and retries its cleanup during close or recovery. Device retains only resources whose close fails; completed resources detach once. Successful release of unrelated resources never clears a cleanup failure without a retained owner to verify. The existing recovery cooldown and guarded ADB commands provide the retry boundary without an additional recovery loop or unconditional error reset.

DroidCast tracks remote cleanup independently of its host process. Host process termination and HTTP closure continue despite remote failure. A failed remote query or kill retains the unique process name; failed forward inspection or removal retains the owned port. Every retry verifies the process command line and exact selected-serial forward mapping before mutation. A replacement process or mapping stays untouched. Cleanup commands retain their existing finite timeouts.

## Verification

Hermetic tests cover offline cleanup followed by successful recovery, repeated failed close, retained remote and forward responsibilities, changed foreign process and forward identities, one-time completed host cleanup, unchanged Device Profile, preserved uncertain-input pauses and unresolved failure blocking startup. Existing device ownership, capture, shutdown and recovery tests remain authoritative.
