# Integrating a Simulator Preset

Developer recipe for integrating a new Android emulator preset, implementing deterministic discovery, and adhering to device invariants.

---

## 1. Register Preset Identifier

Register the unique preset identifier in the device configuration model:

```python
# arknights_mower/utils/config/device_profile.py
PresetId = Literal[
    "windows.mumu12",
    "windows.ldplayer9",
    "windows.ldplayer14",
    "windows.nox",
    "windows.bluestacks5",
    "macos.mumu_pro",
    "macos.bluestacks_air",
    "linux.genymotion",
    "linux.redroid",
    "linux.waydroid",
    "custom.vendor_name",  # Newly registered preset
]
```

### Verification Steps
1. Add the preset identifier to `PresetId` and `LEGACY_NAMES` in [`DeviceProfile`](../../arknights_mower/utils/config/device_profile.py).
2. Ensure default manager paths and configuration heuristics are declared in preset defaults.

---

## 2. Implement Deterministic Discovery

Implement the vendor discovery provider in `arknights_mower/utils/device/`:

```python
# arknights_mower/utils/device/custom_vendor_discovery.py
import subprocess


def parse_vendor_instances(manager_path: str) -> list[dict]:
    # Enforce bounded execution timeout (INV-01)
    proc = subprocess.run(
        [manager_path, "list", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=True,
    )
    return parse_instances_json(proc.stdout)
```

### Verification Steps
1. Wrap all external CLI commands with explicit timeouts (`timeout=5.0`).
2. Parse instance identifier, instance name, and connection endpoints deterministically.
3. Ensure no unconfirmed discovery candidates are written directly to persistent configuration (`[INV-01]`).

---

## 3. Verify Target Rebinding Isolation

Ensure changing the preset or instance resets existing endpoints:

```python
def test_preset_switch_clears_serial():
    profile = DeviceProfile(preset_id="windows.mumu12", last_serial="127.0.0.1:16384")
    # Target rebinding must clear last_serial (INV-02)
    rebound = profile.model_copy(update={"preset_id": "custom.vendor_name"})
```

### Verification Steps
1. Verify that updating `preset_id` resets `last_serial` to prevent stale endpoint reuse (`[INV-02]`).
2. Verify that discovery failures never alter persisted fields or fall back to other online devices (`[INV-03]`).

---

## 4. Author Decision Note Triplet

Create the bilingual decision note triplet under `.agents/notes/implemented/feature/`:
- `YYYY-MM-DD-custom-vendor-name.md` (authoritative English specification)
- `YYYY-MM-DD-custom-vendor-name.zh.md` (aligned Chinese mirror)
- `YYYY-MM-DD-custom-vendor-name.sidecar.json` (metadata schema)

### Verification Steps
1. Verify frontmatter matches filename date and category `feature`.
2. Confirm machine-readable sidecar references relevant invariants and test suites.

---

## 5. Execute Targeted Verification

Run focused unit tests to confirm the integration:

```bash
pytest arknights_mower/tests/device_config_tests.py
pytest arknights_mower/tests/device_session_tests.py
python scripts/verify_governance.py
```
