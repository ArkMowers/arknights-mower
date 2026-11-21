---
title: Owned ADB Recovery
status: archived
category: architecture
date: 2026-10-01
---

# Owned ADB Recovery

> Superseded by [Shared ADB Recovery](../../implemented/simplification/2026-10-01-shared-adb-recovery.md). This archived note preserves the original committed ownership contract; it is not the active [INV-DEV-19] contract.

## Contract

[INV-DEV-19] Owned ADB Recovery isolates desktop simulator runs on an ephemeral loopback port. A foreground child with verified listener ownership supplies the service. Two failed service observations spanning at least thirty seconds permit one owned-process rebuild within the current Recovery Budget. An offline target with a healthy service never authorizes a server rebuild.

[INV-05] Shared ADB Guard remains unchanged for settings, physical devices and native Android. Recovery never sends kill-server or terminates another process. The owned server disables USB, emulator scanning and multicast discovery; only explicitly verified TCP endpoints connect. Runtime ports never reach Device Profile or global process environment.

The selected binary requires ADB protocol 1.0.41 or newer, whose foreground server supports disabling USB and emulator discovery. Saved SDK emulator aliases register only their console/ADB port pair before the existing AVD-name verification; failed identity checks never authorize device dispatch.

## Ownership and Continuation

Device Control retains the server across transient connection failures and idle helper cleanup. Whole-run cleanup releases helpers before the server. Real release failure prevents process replacement. Each replacement uses a newly reserved port; a foreign listener fails ownership validation without adoption or termination.

Direct sockets, ADB CLI commands, capture and input helpers share the caller's server context. Native MAA command templates receive an explicitly quoted executable and port prefix. Vendor ADB delegation receives a child-only server environment. No wrapper executable, persisted port setting or separate recovery loop is introduced.

Numeric loopback host routing prevents ADB CLI auto-start; a lost owned listener is recovered only by its foreground owner. MAA disables AdbLite and exit-time ADB termination before connecting. A helper's confirmed pre-send rejection leaves input undispatched, but a previously transmitted gesture packet keeps the whole operation uncertain.

MAA routing covers templates using `[Adb]`. Custom templates with their own executable or hard-coded shared port are outside this routing contract.

Service recovery shares the session deadline and attempt count. Target identity verification precedes helper reconstruction; the scheduler, pending tasks and uncertain-input pause remain unchanged.

Only failed service probes advance the failure window; caller budget exhaustion and cancellation do not count. Device Control records the server generation only after successful helper binding. A changed generation requires full helper reconstruction even when a previous recovery cycle failed its frame check.

## Simplification and Verification

The existing guarded ADB boundary supplies one routing context instead of duplicating lifecycle logic in each emulator adapter. Focused hermetic tests substitute server processes, listener ownership, socket probes and clocks. They cover healthy-service offline targets, sustained service failure, port conflicts, cancellation, cleanup order, transport routing and same-target recovery. No live device or remote configuration is changed; simulator startup waiting remains in its existing location. No glossary definition changes.
