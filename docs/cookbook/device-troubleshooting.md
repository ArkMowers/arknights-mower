# Device Connection & Recovery Troubleshooting

Actionable operational guide for diagnosing device connection failures, offline states, capture decoding errors, and recovery budget timeouts.

## Local Development Origin

The backend and Vite use `MOWER_DEV_PORT` for the explicitly allowed loopback development port (default `5173`). Authentication remains required; other origins remain denied.

1. Set the same environment variable in both the backend and frontend terminals, for example in PowerShell:
   ```powershell
   $env:MOWER_DEV_PORT = '5174'
   ```
2. Start the backend and Vite with that environment. Vite reports an error if the requested port is occupied.
3. Verify that authenticated WebSocket requests from that loopback port succeed and requests from an unconfigured port are rejected:
   ```bash
   pytest arknights_mower/tests/ai_security_tests.py -k configured_dev_port
   ```

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

### LD Screenshot Enhancement

1. Select Windows LDPlayer 9 or 14 and confirm the target instance through device detection. Select **LD 截图增强** in the capture backend menu; keep scrcpy or MaaTouch for input.
2. Confirm that the emulator installation contains `ldopengl64.dll` and uses landscape 1920×1080. The adapter requires Windows x64 and a manager version reporting dimensions in `list2`.
3. Run the read-only connection test. A missing DLL, unreported dimensions or changed instance produces a visible capture error. Upgrade the emulator or manually select another compatible capture backend before retrying.
4. Verify the adapter offline without launching an emulator:
   ```bash
   pytest arknights_mower/tests/device_ld_capture_tests.py arknights_mower/tests/device_capture_compatibility_tests.py
   ```

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

## Detect and Start a Selected Emulator

1. Select the emulator preset and click `检测实例`. MuMu Pro detection opens its manager application if needed. Multiple candidates remain a selection list.
2. Select the intended instance. Detection checks it, starts it only if stopped, and saves its identity after connection verification succeeds.
3. Use the dropdown `测试连接（只读）` to inspect a stopped instance without opening or starting it. BlueStacks 5, BlueStacks Air and manual serial profiles require manual startup.
4. Verify that a rejected target keeps its selected identity. Inspect MuMu Pro directly with its official read-only command:

```sh
/Applications/MuMuPlayer.app/Contents/MacOS/mumutool info 1
```

The [device contract](../subsystems/device-control.md) defines launch scope and immediate authorization.
