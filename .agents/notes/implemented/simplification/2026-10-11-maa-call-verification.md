---
title: MAA Call Verification
status: implemented
category: simplification
date: 2026-10-11
---

# MAA Call Verification

[中文](2026-10-11-maa-call-verification.zh.md)

**[INV-MAA-08] Verified MAA Admission**: Resource loading, task submission and task startup require positive MAA results; rejected calls identify their phase and target, clear the pending run without recording successful execution, and preserve rollback backups.

The simplification audit identifies `VerifiedAsst` as the existing shared boundary for desktop and Android task submission and startup. The scheduler owns ordinary tasks, long tasks and optional theme restoration. Reusing that boundary removes the need for separate return-value policies at each call site. Both platforms download navigation at initialization. Desktop loads it through `Asst.load`; Android sends it to the host through `maa_navigation` so the active component loads the validated file while idle. Older hosts reuse component packaging and require a service restart only when the loaded component does not contain the navigation. An APK update enables direct loading, while the compatibility path remains available. No configuration schema or domain terminology changes.

Navigation downloads validate a nonempty JSON object before atomic replacement through the existing `write_json`. Download completion and successful MAA resource loading produce separate log entries. Desktop initialization checks `Asst.load` before handle construction and records the core version, resource timestamp and selected resource paths.

`MaaCallError` carries the failed phase and optional task type and stage. `VerifiedAsst` rejects a nonpositive task identifier and a rejected startup. The scheduler releases queued work on the ordinary failure path and preserves the original diagnostic if stopping also fails. Rejected admission never updates the last execution time or retires backups. Existing cancellation and device-failure propagation retain their exception types.

Android resource updates reuse the existing MirrorChyan MaaResource installer and remain independent of the official Android core component source. Source changes invalidate the resource update receipt. Android compatibility CI keeps the core Mirror restrictions and runs resource regressions separately, including resource Mirror availability and legacy navigation loading. No new configuration fields or domain concepts are introduced.

The [MAA integration specification](../../../../docs/subsystems/maa-integration.md) owns the interface contract. Offline regressions in `maa_admission_tests.py` cover rejection after partial submission, resource load failure and malformed downloads; `maa_backup_tests.py` covers rollback preservation.
