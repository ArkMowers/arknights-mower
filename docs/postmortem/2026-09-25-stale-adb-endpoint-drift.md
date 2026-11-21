# Postmortem: Stale ADB Endpoint Reuse and Target Drift

- **Date**: 2026-09-25
- **Status**: Resolved
- **Impacted Subsystems**: Device Control Subsystem (`DeviceSession`, `DeviceProfile`)
- **Governing Invariants**: `[INV-02]`, `[INV-03]`

---

## 1. Summary

During multi-simulator testing on developer workstations, switching the active device preset from MuMu 12 to LDPlayer 9 resulted in commands executing against the wrong emulator instance. The session reconnected to the previously cached serial `127.0.0.1:16384` (belonging to MuMu 12) rather than discovering and binding to the LDPlayer instance on port `5555`.

---

## 2. Timeline & Root Cause Analysis

### 2.1 Narrative Timeline
1. A developer configured Arknights Mower to automate an Arknights session on a running MuMu 12 instance (`127.0.0.1:16384`).
2. The user opened Device Settings in the Web UI and switched the preset selection to `windows.ldplayer9`, intending to target an LDPlayer instance.
3. The configuration model updated `preset_id = "windows.ldplayer9"` but left `last_serial = "127.0.0.1:16384"` intact in persistent storage.
4. When `DeviceSession.connect()` executed, the connection logic prioritized the cached `last_serial` to accelerate initialization. Because port `16384` remained open and accepted ADB commands, the session reported a successful connection.
5. In-game automation dispatched touch gestures and key events intended for LDPlayer directly into the active MuMu 12 instance, disrupting another running task.

### 2.2 Root Cause
Two structural defects permitted this behavior:
1. **Endpoint Leak Across Target Switches**: Updating preset or instance parameters failed to invalidate the cached endpoint (`last_serial`), allowing stale addresses to bleed across emulator boundaries.
2. **Target Drift on Connection**: The session did not verify whether the active ADB serial actually matched the configured simulator vendor or instance identity prior to dispatching operational commands.

---

## 3. Preventive Architecture Invariants

To eliminate this defect class permanently, the following invariant contracts were codified in [CODING_STANDARDS.md](../../CODING_STANDARDS.md) and enforced across all device layers:

- **[INV-02] Target Rebinding Clears Endpoints**: Changing `preset_id`, installation directory, manager path, configuration path, or instance identifier must immediately clear `last_serial`. No cached endpoint may survive a target re-specification.
- **[INV-03] Failure Preserves Target Identity**: Discovery, preflight, or recovery failure must never silently alter persistent configuration, switch backends, or automatically fallback to another online device on the host. If the targeted instance is unreachable, the session halts with a structured error verdict.

---

## 4. Verification & Regression Coverage

The fix is validated by targeted unit test suites:
- `test_target_rebinding_clears_serial`: Verifies in `arknights_mower/tests/device_session_tests.py` that updating `preset_id` or `instance_id` immediately sets `last_serial = None`.
- `test_unmatched_target_fails_cleanly`: Verifies that an offline or unresolvable instance halts execution without connecting to foreign online devices detected by the host ADB server.
