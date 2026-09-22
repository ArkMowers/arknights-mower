"""T1.1 — 启动无假任务实机验收（S1；**零点击**）。

验收目标（§10.3「S13 分片执行」T1.1）
------------------------------------
真机跑 `bootstrap.run()`：
1. 日志**无** `pushed SHIFT_ON`（S1 已删除 `bootstrap.py` 的硬编码假任务）
2. loop **存活**（空转不崩）

判据不靠"某行日志没出现"这种弱证据，而是三重独立证据：

| 证据 | 采集方式 | 期望 |
|---|---|---|
| 任务推送计数 | 包 `TaskQueue.push` 计数器 | **0**（任何类型都不该被推） |
| 日志行 | `LogCapture` 抓 `utils.log.logger` | `pushed SHIFT_ON` / `test: pushed` 各 **0** 行 |
| 点击计数 | 类级替换 `PCDevicePort.tap/swipe/swipe_path` | **0**（本就是 §10.3 的硬约束） |

用法（项目根目录）
------------------
    .venv\\Scripts\\python.exe tests\\live\\t1_1_no_fake_task.py
    .venv\\Scripts\\python.exe tests\\live\\t1_1_no_fake_task.py --seconds 30

安全边界
--------
- **不 tap / swipe**（类级守住，计数用于事后断言）
- **不派发任何任务**：`config.conf.workshop_settings == []` 使 `WorkshopPlanner.condition()` 为 False，
  `_build_planners` 只注册这一个 planner → 队列恒空
- 副作用：`bootstrap.run()` 的 `finally` 会写 `tmp/mower.db` → 先 `Copy-Item` 备份，`finally` 还原
- `run()` 在本脚本里跑在**观察者线程之外**的子线程（`run_forever` 是阻塞循环），
  墙钟到点用 `request_stop()` 结束它

⚠️ 存活判据**不得只看窗口末尾**：`--seconds` 同时是墙钟上限，窗口末尾恰好是
`request_stop()` 的触发点，在那里读 `is_alive()` 只会读到"刚被停掉" —— 那是竞态，
会假红。因此本脚本在**整个窗口内逐秒连续采样**存活，并让安全网定时器比观察窗口
晚 `CLOCK_GRACE_SECONDS` 触发（停止动作由观察者自己发出）。
"""

import argparse
import sys
import threading
from pathlib import Path

# 直接执行（python tests/live/xxx.py）时 sys.path[0] 是 tests/live/，仓库根不在其中，
# 连 `tests` 这个包都还解析不到。这里**不硬算层数**，改为向上找 tests/_bootstrap.py 锚点；
# 真正的路径引导一律由 tests._bootstrap 负责。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "tests" / "_bootstrap.py").is_file():
        sys.path.insert(0, str(_parent))
        break

# 副作用：把仓库根写入 sys.path
from tests._bootstrap import REPO_ROOT  # noqa: E402,F401

from tests.live.t1_common import (  # noqa: E402
    CLOCK_GRACE_SECONDS,
    LogCapture,
    WallClockStop,
    db_backup,
    idle_wait,
    quiet_logs,
)

FAKE_TASK_MARKERS = ("pushed SHIFT_ON", "test: pushed")


def _install_push_recorder() -> list:
    """包 `TaskQueue.push`，记录所有被推送的任务。"""
    from arknights_mower.scheduler.queue import TaskQueue

    pushed: list = []
    original = TaskQueue.push

    def _recording_push(self, task) -> None:
        pushed.append(task)
        return original(self, task)

    TaskQueue.push = _recording_push
    return pushed


def _install_click_recorder() -> list:
    """类级替换 `PCDevicePort` 的点击原语，保证零点击并计数。"""
    from arknights_mower.scheduler.infra.pc_device_port import PCDevicePort

    clicks: list = []

    def _recorder(kind: str):
        def _fn(self, *args, **kwargs) -> None:
            clicks.append((kind, args))

        return _fn

    for name in ("tap", "swipe", "swipe_path"):
        setattr(PCDevicePort, name, _recorder(name))
    return clicks


def main() -> int:
    parser = argparse.ArgumentParser(description="T1.1 启动无假任务（零点击）")
    parser.add_argument("--seconds", type=int, default=30, help="墙钟上限（秒）")
    args = parser.parse_args()

    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.utils import config
    from arknights_mower.utils.path import get_path

    quiet_logs()

    db_path = Path(get_path("@app/tmp")) / "mower.db"
    print(f"[0] mower.db 路径 = {db_path}")
    print(f"[0] workshop_settings = {config.conf.workshop_settings!r}")
    print(f"[0] 观察窗口 = {args.seconds}s，安全网 = {args.seconds + CLOCK_GRACE_SECONDS}s")

    pause = ThreadPauseController()
    clock = WallClockStop(
        args.seconds + CLOCK_GRACE_SECONDS, on_timeout=pause.request_stop
    ).start()

    pushed = _install_push_recorder()
    clicks = _install_click_recorder()

    outcome: dict = {"error": None}
    worker_alive_after_restore = None
    ok = False
    try:
        with db_backup(db_path) as backup:
            print(f"[0] mower.db 已备份 -> {backup.name}")

            with LogCapture() as logs:
                def _run() -> None:
                    from arknights_mower.scheduler.bootstrap import run

                    try:
                        run(pause=pause)
                    except BaseException as exc:  # noqa: BLE001 - 探测需记录任何退出原因
                        outcome["error"] = f"<{type(exc).__name__}> {exc}"

                worker = threading.Thread(target=_run, daemon=True, name="bootstrap-run")
                worker.start()
                print("[1] bootstrap.run() 已启动，开始观察 ...")

                # 存活必须在**整个窗口内连续采样**，不能只看窗口末尾：
                # `--seconds` 同时是墙钟上限，窗口末尾恰好是 request_stop 触发点，
                # 在那里读 is_alive() 只会读到"刚被停掉"，是竞态而非结论。
                alive_samples: list[bool] = []
                elapsed = 0.0
                while worker.is_alive() and elapsed < args.seconds:
                    idle_wait(1.0)
                    elapsed += 1.0
                    alive_samples.append(worker.is_alive())
                alive_count = sum(alive_samples)
                print(
                    f"[2] 观察结束 {elapsed:.0f}s: 采样 {len(alive_samples)} 次，"
                    f"存活 {alive_count} 次"
                )

                pause.request_stop()
                worker.join(timeout=10)
                print(f"[3] request_stop() 后: alive={worker.is_alive()}")

                pushed_types = [getattr(t, "type", None) for t in pushed]
                marker_hits = {
                    marker: logs.count(marker) for marker in FAKE_TASK_MARKERS
                }
                idled = logs.count("no pending tasks, idling")
                stopped = logs.count("MainLoop stopped")

            # db_backup 的 finally 会回写 mower.db；回写前必须确认写库的线程已退出，
            # 否则 run() 的 finally 可能覆盖还原结果。
            worker_alive_after_restore = worker.is_alive()

        print(f"\n[4] 队列推送总数 = {len(pushed)}  types={pushed_types}")
        for marker, hits in marker_hits.items():
            print(f"[4] 日志行 '{marker}' = {hits}")
        print(f"[4] 'no pending tasks, idling' 行数 = {idled}")
        print(f"[4] 'MainLoop stopped' 行数 = {stopped}")
        print(f"[4] 存活采样 = {alive_count}/{len(alive_samples)}")
        print(f"[4] tap/swipe/swipe_path 调用数 = {len(clicks)}")
        print(f"[4] run() 线程内异常 = {outcome['error']}")
        print("[4] mower.db 已在线程退出后按 Copy-Item 还原")

        checks = {
            "队列无任何任务推送": len(pushed) == 0,
            "日志无 pushed SHIFT_ON": marker_hits["pushed SHIFT_ON"] == 0,
            "日志无 test: pushed": marker_hits["test: pushed"] == 0,
            "零点击（tap/swipe 计数 0）": len(clicks) == 0,
            "loop 持续存活（≥3 次采样）": alive_count >= 3,
            "loop 未提前自行退出（存活到窗口末尾）": bool(alive_samples)
            and alive_samples[-1],
            "空转确实发生（idling 日志 ≥1）": idled >= 1,
            "run() 线程正常退出（request_stop 生效）": outcome["error"] is None,
            "还原时写库线程已退出": worker_alive_after_restore is False,
        }
        print()
        passed = 0
        for name, good in checks.items():
            print(f"    -> {'PASS' if good else 'FAIL'}  {name}")
            passed += int(good)
        print(f"\n[T1.1] {passed}/{len(checks)} 项通过")
        ok = passed == len(checks)
    except KeyboardInterrupt:
        print("\n    Ctrl+C，正在停止...")
    finally:
        clock.cancel()
        pause.request_stop()

    print("\n[OK] T1.1 全部通过" if ok else "\n[FAIL] T1.1 存在未通过项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
