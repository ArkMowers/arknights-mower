# Device Connection & Recovery Troubleshooting

Actionable operational guide for diagnosing device connection failures, offline states, capture decoding errors, and recovery budget timeouts.

Python verification commands below run from the repository root with the project's development environment. They use offline fixtures. UI actions and the ADB probe are manual observations of the selected installation; record their actual results separately. Connection success establishes the tested frame and target, not completion of a game operation.

## Local Development Origin

The backend and Vite use `MOWER_DEV_PORT` for the explicitly allowed loopback development port (default `5173`). Authentication remains required; other origins remain denied.

1. Set the same environment variable in both the backend and frontend terminals, for example in PowerShell:
   ```powershell
   $env:MOWER_DEV_PORT = '5174'
   ```
2. Start the backend and Vite with that environment. Vite reports an error if the requested port is occupied.
3. Verify the configured-origin policy offline from the repository root. The [frontend development guide](../../ui/README.md) explains the authenticated development URL:
   ```bash
   python -m pytest arknights_mower/tests/ai_security_tests.py -k configured_dev_port -q
   ```

---

## 1. Inspect Readiness Classification

Inspect `GET /device/status` through the authenticated application. It returns the last session observation under `readiness` and the last connection test under `preflight`; either can be `null` before an observation exists. This endpoint does not perform a fresh readiness check.

For a fresh selected-target check, stop the current task and choose `测试连接（只读）`. Its authenticated request is `POST /device/preflight` with the following body when using the saved Device Profile:

```json
{"device": {}}
```

### Verification Steps
1. Read the test response's `ok`, `status`, `serial` and, on failure, `error.code`, `error.message` and `error.action`. Session observations instead use `readiness.state` and `readiness.code`; these are distinct response objects in [DeviceControl](../../arknights_mower/utils/device/application.py).
2. For `status: absent` or `error.code: instance_stopped`, check the selected instance and configured installation paths. A stopped instance retains its identity; use the explicit start action when it is supported.
3. For `offline`, use the shared-server probe below. For `booting`, retain the selected instance and inspect the boot observations and stage logs in the [startup diagnosis](device-startup-stall.md).
4. Verify the verdict and selected-target policy offline:
   ```bash
   python -m pytest arknights_mower/tests/device_preflight_tests.py arknights_mower/tests/device_discovery_tests.py -q
   ```

---

## 2. Probe Shared ADB Server State

For a manual host observation, verify that the shared ADB daemon responds over its control socket. The [Shared ADB Guard contract](../subsystems/device-control.md#3-subsystem-invariants) governs startup and recovery:

```python
from arknights_mower.utils.device.adb_client.server import probe_adb_server

version = probe_adb_server(timeout=5.0)
print(f"ADB daemon protocol version: {version}")
```

### Verification Steps
1. Run `probe_adb_server(timeout=5.0)`.
2. `None` means connection refusal. A timeout or invalid response raises `SharedADBHandshakeTimeout` or `SharedADBError`; it does not establish absence or authorize an immediate restart. Use the selected-target connection action to enter the bounded production recovery path.
3. Verify the handshake and recovery policy offline without restarting the host server:
   ```bash
   python -m pytest arknights_mower/tests/adb_server_tests.py arknights_mower/tests/adb_shared_server_tests.py -q
   ```

---

### Windows Socket Access Denied (WinError 10013)

Windows reports `WinError 10013` when a socket operation is denied. The shared-server error names the attempted address, retains the original error and points to host network access permissions. This code alone does not identify which host setting caused the denial; see Microsoft's [Windows Sockets error codes](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2).

1. Save the complete file log around the failure using the [startup diagnosis](device-startup-stall.md). Check whether the same Mower process also reports this error for HTTPS requests. Record the affected operations and timestamps before attributing the failure to the emulator or ADB server.
2. Review firewall and security-software network access rules for the running Mower executable and the selected ADB executable. Check their actual installation paths and any host network diagnostics for the denial. The error alone does not establish port exhaustion or a particular security product as the cause.
3. After correcting a confirmed host problem, run `测试连接（只读）` for the original selected instance and retain its result. If the denial persists, preserve the logs and host diagnostics for further investigation. Increasing the boot timeout or changing capture and touch backends does not grant Windows network access.

The offline `windows_socket_denial` and `socket_denial_at_final_start_check` cases in [shared ADB recovery tests](../../arknights_mower/tests/adb_shared_server_tests.py) verify error propagation and preservation of the shared service. They do not reproduce or repair the host configuration that denies access.

---

## 3. Verify Canvas Frame Decoding

### LD Screenshot Enhancement

1. Select Windows LDPlayer 9 or 14 and confirm the target instance through device detection. Select **LD 截图增强** in the capture backend menu; keep scrcpy or MaaTouch for input.
2. Confirm that the emulator installation contains `ldopengl64.dll` and uses landscape 1920×1080. The adapter requires Windows x64 and a manager version reporting dimensions in `list2`.
3. Run the read-only connection test. A missing DLL, unreported dimensions or changed instance produces a visible capture error. Upgrade the emulator or manually select another compatible capture backend before retrying.
4. Verify the adapter offline without launching an emulator:
   ```bash
   python -m pytest arknights_mower/tests/device_ld_capture_tests.py arknights_mower/tests/device_capture_compatibility_tests.py -q
   ```

Connection testing validates the decoded RGB matrix and returns its dimensions as `observations.frame: [1920, 1080]` on success. This is the frame observation from [PreflightService](../../arknights_mower/utils/device/preflight.py), rather than the logical display size or a preview image.

### Verification Steps
1. Run the read-only connection test and inspect its frame observation or capture error. `frame_size_mismatch` carries the `fix_size` action; an unavailable capture retains its own error.
2. For an emulator, confirm landscape 1920×1080 in its settings. For a physical device, use the explicit Temporary Preparation action and inspect the resulting frame; the reported display size alone does not establish readiness.
3. Verify decoding and wrong-frame rejection offline with `python -m pytest arknights_mower/tests/device_preflight_tests.py -q`. Successful fixture decoding does not establish current emulator output or recognition accuracy.

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
4. Verify the finite deadline and retry policy offline. These fixtures do not measure how long the selected installation takes to boot:
   ```bash
   python -m pytest arknights_mower/tests/device_session_tests.py -k 'budget or deadline' -q
   ```

## Detect and Start a Selected Emulator

1. Select the emulator preset and click `检测实例`. MuMu Pro detection opens its manager application if needed. Multiple candidates remain a selection list.
2. Select the intended instance. The selection persists its identity before connection testing; failed readiness preserves that selection. Detection starts only the selected supported instance after a stopped verdict.
3. Use the dropdown `测试连接（只读）` to inspect a stopped instance without opening or starting it. BlueStacks 5, BlueStacks Air and manual serial profiles require manual startup.
4. Verify that a rejected target keeps its selected identity. Inspect MuMu Pro directly with its official read-only command:

```sh
/Applications/MuMuPlayer.app/Contents/MacOS/mumutool info 1
```

The [device contract](../subsystems/device-control.md) defines launch scope and immediate authorization.

### BlueStacks Air on macOS

1. Open the intended BlueStacks Air instance manually. In Settings → Advanced, enable Android Debug Bridge (ADB), save, and wait for the Android desktop.
2. In the standalone Mower manager, open the instance's 连接与启动 editor and enable 独立配置 to select a manual ADB address. Choose the BlueStacks Air preset. Leave its application path empty for automatic detection, or use `/Applications/BlueStacks.app`; the bundled ADB is `/Applications/BlueStacks.app/Contents/MacOS/hd-adb`.
3. Click 检测可用实例. Air returns ADB addresses and states rather than named VM bindings. Select the address displayed by the intended instance's settings, then Save. A running emulator alone does not establish that ADB or the game connection is ready; follow any detection error before starting the Mower instance.
4. `/Applications/BlueStacks Air multi-instance manager.app` is BlueStacks' separate multi-instance application. Do not substitute it for the player application path. Mower's Air preset does not read `bluestacks.conf` or provide automatic emulator start/stop; use the ADB address shown by BlueStacks rather than assuming every instance uses port 5555.

The [managed device configuration rules](../subsystems/web-access.md#managed-device-configuration) define address selection and saving in the standalone manager.
