# MAA Runtime Core Contract

## 1. Initialization

`load_verified_maa` serializes desktop core validation and instance construction with the existing update transaction. It checks the configured core file, loads base and incremental resources, and verifies the instance's core version against `read_installed_version(fresh=True)` before acquiring a device connection. An unchanged SDK class and core file identity reuse the verified disk version; resource and cache changes still reload resources.

## 2. Failure Boundary

`MaaCoreRestartRequired` exposes code `maa_core_restart_required` and requests a Mower process restart. Stopping and starting the automation task does not replace a process-resident native image. A changed core identity is rejected before resource loading. A stale image discovered on first validation releases the unconnected instance without unloading the library. Failed resource loading or disk version probing creates no validated generation. Other connected MAA instances remain protected by the existing busy gate.

Android retains its host-managed core lifecycle. Configuration schemas, Scheduling Plans and device transport remain unchanged.

## 3. Subsystem Invariants

- **[INV-UPD-02] MAA Core Generation**: Desktop MAA initialization verifies the loaded core version against an independent disk probe before connection; replacement of a validated core requires a Mower process restart without unloading native handles, while resource-only updates preserve initialization.

[Core generation validation](../../.agents/notes/implemented/bug-fix/2026-10-05-maa-core-generation.md) records implementation and focused verification.
