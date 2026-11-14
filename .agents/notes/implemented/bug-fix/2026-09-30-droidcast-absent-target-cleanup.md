---
title: DroidCast Absent Target Cleanup
status: implemented
category: bug-fix
date: 2026-09-30
---

# DroidCast Absent Target Cleanup

## Contract

[INV-DEV-16] Absent Target Cleanup permits idempotent DroidCast cleanup and subsequent verified startup when the selected target disappears and no owned forward remains. Unknown transport failures, surviving owned forwards and host-resource cleanup failures remain blocking. Foreign resources and shared ADB state remain unchanged.

## Boundary and simplification

The existing DroidCast cleanup boundary classifies an exact selected-device-not-found response as an absent remote helper only for explicitly permitted cleanup commands. Capture and installation failures keep their existing classification. Forward inventory is a guarded server-level read without a device selector; removals retain the selected serial and require the exact owned mapping. A failed removal succeeds only when another guarded inventory read confirms that the mapping no longer belongs to this session.

Host process termination and HTTP closure run even when the target is absent. The Device Control cleanup-failure guard remains unchanged: real cleanup failures still prevent another startup. No vendor-specific branch, shared-server restart, global forward removal or unconditional error-cache reset is introduced. Device Profile and Instance Binding remain unchanged.

## Verification

Hermetic tests cover target disappearance, foreign mapping preservation, repeated close, the next verified instance startup, removal/disconnection races, surviving owned forwards, guarded host inventory, malformed or unavailable inventory and an unconfirmed offline transport. Existing permission-denied, changed process identity and host-resource cleanup tests remain authoritative.

Read-only preflight capture tests require the verified ADB binary for every command. Only the exact server-level `forward --list` inventory omits the device selector; every other capture and cleanup command retains the selected serial.
