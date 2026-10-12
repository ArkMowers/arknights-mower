# Device Startup Stall Diagnosis

The connection message confirms only that the instance and its endpoint are ready. The task reaches the game check after preflight and after capture and touch initialization complete. The [device contract](../subsystems/device-control.md) defines the stage records and the [INV-DEV-20] command output ownership.

1. Save the `log/runtime.log.<date>_<hour>` files covering at least five minutes before and after startup. The UI `/log` WebSocket shows INFO and above only; the files carry DEBUG. Save the neighbouring file too when the window crosses an hour boundary. Remove tokens and account details before sharing, and keep timestamps, function names, command arguments, error codes and tracebacks.

   ```powershell
   Get-ChildItem -LiteralPath '.\log' -Filter 'runtime.log.<YYYY-MM-DD>_*'
   Get-Content -LiteralPath '.\log\runtime.log.<YYYY-MM-DD>_<HH>' -Tail 2000
   ```

2. Classify the stall from the file log against the emulator display.

   | File log and display | Verdict |
   | --- | --- |
   | The file stops growing after the connection message, with no error | A wait without a record; the UI alone cannot name the call |
   | DEBUG keeps growing, then a device or capture error appears | Waiting inside the Recovery Budget ends in a failure result |
   | The file keeps growing and the game reaches the foreground, but only the UI stops updating | The log delivery or UI presentation path needs inspection |

3. Locate the operation through stage and command boundaries. `正在检查设备 ADB、游戏安装与截图...` marks preflight start; `设备预检通过，正在初始化截图与触控...` marks helper initialization start; `设备初始化完成` marks completed initialization. The DEBUG records `设备预检命令开始`, `设备预检 ADB 命令开始` and `MuMu 输入版本查询开始` carry arguments or the instance together with the effective timeout. A start record without its completion record names the command once the following traceback is read with it. A shared ADB check and its command spend one budget.

4. Record the Mower process count, whether instances share a directory, whether the stalled instance answers the mouse, and that process's CPU usage. Keep the selected instance index, the window title and the ADB serial. The settings page also locks device settings during startup; the lock label does not prove initialization finished.

5. Reproduce the command return deadline offline with the inherited-handle fixture, without connecting an emulator.

   ```bash
   pytest arknights_mower/tests/device_command_tests.py -q
   ```

   The fixture lets a descendant of the command retain stdout/stderr and verifies command timeout, successful exit and non-zero exit separately. The test releases the descendant and reaps the owned process. Command waiting does not depend on descendant EOF, and timeout cleanup stops neither the shared ADB server nor another instance.

6. Verify on site against the complete stage log and the final result. The offline reproduction proves the inherited-handle defect; attributing one MuMu stall to it still requires that stall's DEBUG file log or a repeated run with this change.
