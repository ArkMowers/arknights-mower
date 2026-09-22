"""T2 实机脚本的**统一 main() 脚手架**（实机脚本，不参与门禁 G1 收集）。

T2.1/T2.2/T2.3/T2.4/T2.5 五项都要做同一套外围动作，逐字复制既超 300 行上限、
又容易出现口径漂移。本模块把它收敛成一处：

| 步骤 | 说明 |
|---|---|
| 解析 `--seconds` | S13 规则 2：每个脚本都必须有墙钟上限 |
| 打印安全边界 + 前后 SHA256 | T2 规约 7 的副作用证据（`mower.db` / `conf.yml`） |
| `db_backup_t2` | `Copy-Item` 备份 `tmp/mower.db`，`finally` 还原，无 `.t2bak` 残留 |
| `WallClockStop` | 墙钟到点调 `pause.request_stop()`，比观察窗口多 `CLOCK_GRACE_SECONDS` |
| `LogCapture` | 收集日志行交给 `summarize`（换班链路判据以日志为准） |
| `finally: request_stop()` | 正常结束、Ctrl+C、异常三条路径都收敛 |

`probe` 回调签名：`probe(args, pause) -> dict`（取证），可抛 `MowerExit`（墙钟打断）。
`summarize` 回调签名：`(result, log_lines) -> bool`（判据 + 结论），返回是否全过。

⚠️ 本文件名**不以 `_tests.py` 结尾**，因此不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations

import argparse
from pathlib import Path


def run_with_logs(fn):
    """跑 `fn()` 并返回 `(返回值, 该段日志行)`。

    T2.2/T2.4 的**证伪对照**必须与主流程分开记账：主流程的 `free tap` 应为 3 次，
    证伪段（BUG-1 修复前写法）必须为 0 次。`run_probe_script` 只在最外层挂一个
    `LogCapture`，两段日志会混在一起，因此这里给单段单独挂一个 handler。
    """
    from tests.live.t1_common import LogCapture

    with LogCapture() as capture:
        value = fn()
    return value, list(capture.lines)


def run_probe_script(
    *,
    description: str,
    boundary: str,
    probe,
    summarize,
    default_seconds: int = 240,
    extra_args=(),
) -> int:
    """跑一次 T2 取证脚本，返回进程退出码（0 = 全部判据通过）。

    参数：
    - `description` / `boundary`：`--help` 文本与安全边界首行打印
    - `probe(args, pause)`：取证主体，返回结果字典
    - `summarize(result, log_lines)`：判据与结论，返回 `bool`
    - `extra_args`：`(flag, kwargs)` 列表，供脚本追加自己的开关
      （如 T2.5 的 `--times`）
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--seconds", type=int, default=default_seconds,
                        help="墙钟上限（秒）")
    for flag, kwargs in extra_args:
        parser.add_argument(flag, **kwargs)
    args = parser.parse_args()

    from arknights_mower.utils import config
    from arknights_mower.utils.path import get_path

    from tests.live.t1_common import (
        CLOCK_GRACE_SECONDS,
        LogCapture,
        WallClockStop,
        quiet_logs,
        sha256_file,
    )
    from tests.live.t2_common import (
        db_backup_t2,
        idle_wait,
        resettable_pause_class,
    )

    quiet_logs()
    db_path = Path(get_path("@app/tmp")) / "mower.db"
    conf_path = Path(get_path("@app")) / "conf.yml"
    db_before = sha256_file(db_path)
    conf_before = sha256_file(conf_path)
    print(f"[0] {boundary}")
    print(f"[0] mower.db  = {db_before}")
    print(f"[0] conf.yml  = {conf_before}")
    print(f"[0] workshop_settings = {config.conf.workshop_settings!r}")

    # 用**可复位**的 stop：`run_shift_task` 跑完任务后会 `request_stop()` 让
    # `MainLoop` 退出，但其后还要导航去读房间终态（T2.2/T2.4）。粘性 stop 会把
    # 复查腿打断；`mark_clock_timeout` 保证安全网本身不可被解除。
    pause = resettable_pause_class()()
    clock = WallClockStop(
        args.seconds + CLOCK_GRACE_SECONDS, on_timeout=pause.mark_clock_timeout
    ).start()
    print(f"[0] 观察窗口 {args.seconds}s，安全网 {args.seconds + CLOCK_GRACE_SECONDS}s")

    result: dict = {}
    log_lines: list[str] = []
    try:
        with db_backup_t2(db_path) as backup:
            print(f"[0] mower.db 已备份 -> {backup.name}")
            with LogCapture() as capture:
                result = probe(args, pause)
                log_lines = list(capture.lines)
    except KeyboardInterrupt:
        print("\n    Ctrl+C，正在停止...")
    except Exception as exc:  # noqa: BLE001 - 探测脚本需报告任何中断原因
        print(f"\n[ABORT] {type(exc).__name__}: {exc}")

    finally:
        clock.cancel()
        pause.request_stop()
        idle_wait(0.2)

        print(f"\n[9] mower.db  = {sha256_file(db_path)}  (跑前 {db_before})")
        print(f"[9] conf.yml  = {sha256_file(conf_path)}  (跑前 {conf_before})")
        print(f"[9] 无 .t2bak 残留 = {not list(db_path.parent.glob('*.t2bak'))}")

    if not result:
        print("\n[FAIL] 未取得任何取证数据")
        return 1
    ok = summarize(result, log_lines)
    return 0 if ok else 1