# Integrating a Simulator Preset

Developer recipe for integrating an Android emulator preset through the existing Device Profile, discovery, connection testing and session boundaries. Start with the [Device Control task entry](../subsystems/device-control.md#start-with-the-affected-operation) and a supported provider on the same host platform.

---

## 1. Register Preset Identifier

Add the platform-specific identifier to `PresetId` in [`device_profile.py`](../../arknights_mower/utils/config/device_profile.py). Keep platform availability, capture compatibility and UI labels aligned with the actual provider.

### Verification Steps
1. Add `LEGACY_NAMES` entries only for legacy configurations the provider actually supports. Inspect `profile_from_legacy` and `Conf.updated` before choosing compatibility behavior.
2. Add the label and relevant placeholders in [`deviceSettings.js`](../../ui/src/utils/deviceSettings.js). Check supported host and capture/touch choices rather than advertising unsupported combinations.

---

## 2. Implement Deterministic Discovery

Implement the provider under `arknights_mower/utils/device/` and connect it to [`DiscoveryService`](../../arknights_mower/utils/device/discovery.py). Windows providers enter through [`WindowsDiscoveryIO`](../../arknights_mower/utils/device/windows_discovery.py); platform-specific providers use the corresponding service branch. Reuse [`run_manager_command`](../../arknights_mower/utils/device/manager_io.py) for bounded, checked manager output and parse the vendor's actual format.

### Verification Steps
1. Test the parser with saved manager output, including empty, malformed, partial and multiple-instance results. Inject the command runner so these tests launch no vendor manager.
2. Preserve stable instance identity separately from the currently observed endpoint. Connect selected-target checks through `DiscoveryService.check_binding` and `PreflightService`; failures return repair guidance while preserving the user's selection.
3. Return transient candidate results for explicit selection. If the preset supports instance lifecycle actions, wire its selected-instance adapter in [`session_io.py`](../../arknights_mower/utils/device/session_io.py) and expose start capability through the existing backend list. Discovery does not itself authorize starting a VM.

---

## 3. Verify Target Rebinding Isolation

In a focused test, verify endpoint clearance through the configuration update boundary, rather than `DeviceProfile.model_copy`, which does not apply `Conf.updated` rules. The root [test fixture](../../conftest.py) isolates application data. This example uses an existing preset; use the registered preset in its regression:

```python
from arknights_mower.utils.config.conf import Conf

original = Conf(device={"preset_id": "manual.other", "last_serial": "old-serial"})
rebound = original.updated({"device": {"preset_id": "windows.mumu12"}})
assert rebound.device.last_serial == ""
assert original.device.last_serial == "old-serial"
```

### Verification Steps
1. Exercise authenticated `/conf` updates and save/reload, as in [`device_config_tests.py`](../../arknights_mower/tests/device_config_tests.py), so the test covers the real persistent caller.
2. Exercise discovery and session callers with two distinct instance identities and changing endpoints. Failed checks preserve the selected instance; a different online target does not become a fallback.

---

## 4. Place the necessary evidence

Update current platform behavior in the [device contract](../subsystems/device-control.md) and add user steps where the integration changes them. Keep reproduction and verification in the change or PR report. Apply [record ownership](../../.agents/notes/AGENTS.md#1-record-ownership) when the integration introduces a durable independent choice whose rationale existing code, tests and contracts cannot explain. Reuse its existing owner where one exists; a new preset alone does not require a record. A justified proposal reaches implemented status only after the relevant implementation, verification and review are complete.

---

## 5. Execute Targeted Verification

From the repository root, run the affected configuration, discovery and session suites, plus the provider-specific tests added for the integration:

```bash
python -m pytest arknights_mower/tests/device_config_tests.py arknights_mower/tests/device_discovery_tests.py arknights_mower/tests/device_session_tests.py -q
python scripts/verify_governance.py
```

For changed UI selection logic, run `npm test -- src/utils/deviceSettings.test.js` from `ui/`. These checks substitute vendor output, ADB responses and device observations; they establish parsing, selection, persistence and bounded recovery policy. Actual installation discovery, launch and usable Capture Frames still require recorded observations on the supported platform. Keep any unobserved platform behavior explicit in the delivery report.
