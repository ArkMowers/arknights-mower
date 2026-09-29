# Device Connection & Recovery Troubleshooting

Actionable operational guide for diagnosing device connection failures, offline states, capture decoding errors, and recovery budget timeouts.

---

## 1. Inspect Readiness Classification

When a device fails to initialize or drops offline, query the device readiness status:

```python
from arknights_mower.utils import config
from arknights_mower.utils.device.session import DeviceSession

session = DeviceSession(config.conf.device)
verdict = session.readiness()
print(
    f"Status: {verdict.status}, Code: {verdict.code}, Remedy: {verdict.remedy_action}"
)
```

### Verification Steps
1. Execute the query above or perform a `GET /device/readiness` request.
2. If `verdict.status == "absent"`, verify that the emulator application process is running and that the configured installation or manager path exists on the host filesystem.
3. If `verdict.status == "offline"`, proceed to Step 2 to probe the transport layer.
4. If `verdict.status == "booting"`, inspect whether Android boot has completed (`getprop sys.boot_completed`).

---

## 2. Probe Shared ADB Server State

In accordance with `[INV-05]`, never execute `adb kill-server`. Verify that the shared ADB daemon is responsive over its control socket:

```python
from arknights_mower.utils.device.adb_client.server import probe_adb_server

# Probe shared ADB daemon version over socket (default 127.0.0.1:5037)
version = probe_adb_server(timeout=5.0)
print(f"ADB daemon protocol version: {version}")
```

### Verification Steps
1. Run `probe_adb_server(timeout=5.0)`.
2. If `probe_adb_server()` returns `None` (connection refused), start the daemon using standard unprivileged CLI: `adb start-server`.
3. Verify that existing debug tools or other emulator instances retain uninterrupted connections.

---

## 3. Verify Canvas Frame Decoding

If capture operations return errors, verify that decoded frames strictly conform to the 1920×1080 RGB standard:

```python
frame = session.capture_frame()
print(f"Shape: {frame.shape}, Dtype: {frame.dtype}")
assert frame.shape == (1080, 1920, 3), f"Invalid canvas frame shape: {frame.shape}"
```

### Verification Steps
1. Check the captured matrix shape and datatype.
2. Confirm that width equals 1920 and height equals 1080.
3. If the emulator window uses non-standard aspect ratios, adjust the emulator display settings to 1920×1080 (16:9) or apply temporary preparation for physical devices.

---

## 4. Tune Bounded Recovery Policy

If device reboots exceed standard deadlines on slower host machines, adjust the recovery budget parameters dynamically in configuration:

```json
{
  "device": {
    "recovery_timeout": 240.0,
    "recovery_attempts": 4,
    "recovery_local_wait": 15.0
  }
}
```

### Verification Steps
1. Open Advanced Device Settings in the Web UI or send a `PATCH /conf` payload.
2. Set `recovery_timeout` to provide adequate boot headroom while maintaining a bounded deadline.
3. Set `recovery_local_wait` to grant sufficient stabilization time post-boot before initiating game launch.
4. Verify recovery behavior by running the targeted unit test:
   ```bash
   pytest arknights_mower/tests/device_session_tests.py -k test_recovery_budget
   ```
