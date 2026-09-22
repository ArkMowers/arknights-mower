"""T1.3 — pause/stop 有效性实机验收（S13 item 9；连真机但**零点击、不派发任务**）。

为什么这个检查最容易失败（S13 规则 6 / T1 规约 1）
--------------------------------------------------
**恒真陷阱**：若观察者用 `pause.wait()` 观察"暂停后是否真的停住"，观察者自己会被
**同一个 pause 挂起** —— 于是它根本没机会采样，验证恒真。

本脚本的做法：把 `MainLoop._run_planners` 包一层**计数器**。
`_run_planners` 每轮迭代都被调用、**本身不经过 pause**，所以 pause 后计数应停止增长。
观察者线程则用 `threading.Event.wait`（**与 pause 协议无关**，也非 `time.sleep`）采样。

**并且先跑正向对照**：未 pause 时计数**必须**增长。若正向对照就不增长，
说明观察量本身失效 —— 本脚本判 `INVALID`（非 PASS），不给出结论（S4 flaky 教训）。

用法（项目根目录）
------------------
    .venv\\Scripts\\python.exe tests\\live\\t1_3_pause_stop.py
    .venv\\Scripts\\python.exe tests\\live\\t1_3_pause_stop.py --seconds 90 --settle 3 --window 4

安全边界
--------
- **不 tap / swipe**：`PCDevicePort.tap/swipe/swipe_path` 被替换成记录器，计数用于事后断言
- **不派发任何任务**：`workshop_settings == []` → 队列恒空；另包 `TaskDispatch.execute`
  记录任何意外执行，计数必须为 0
- 真机只做**只读**探测：`Device()` 连接 + `screencap()` + `get_scene()`
- 全部等待走 `threading.Event.wait`（非 `pause.wait`、非 `time.sleep`）；见 §10.2 豁免规则 2
- `finally: request_stop()`；`Ctrl+C` 可安全中断
"""

import argparse
import sys
import threading
import time
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
    WallClockStop,
    idle_wait,
    no_save_conf,
    quiet_logs,
)

STOP_DEADLINE_SECONDS = 10.0  # S13 item 9 判据：request_stop() 后 ≤10s 结束线程


def _make_observed_loop():
    """返回 `(ObservedLoop 子类)`：把 `_run_planners` 包一层计数器。

    计数器在**每轮迭代**递增，且 `_run_planners` 的执行**位于 pause 检查之后、
    `pause.wait()` 之前** —— 因此它随"推进"增长，不与 pause 共享阻塞原语。
    """
    from arknights_mower.scheduler.loop import MainLoop

    class ObservedLoop(MainLoop):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.ticks = 0

        def _run_planners(self) -> None:
            self.ticks += 1
            return super()._run_planners()

    return ObservedLoop


def _install_guards() -> tuple:
    """零点击守卫 + 任务派发守卫，两者都返回调用记录列表。"""
    from arknights_mower.scheduler.dispatch import TaskDispatch
    from arknights_mower.scheduler.infra.pc_device_port import PCDevicePort

    clicks: list = []

    def _click_recorder(kind: str):
        def _fn(self, *args, **kwargs) -> None:
            clicks.append((kind, args))

        return _fn

    for name in ("tap", "swipe", "swipe_path"):
        setattr(PCDevicePort, name, _click_recorder(name))

    dispatched: list = []
    real_execute = TaskDispatch.execute

    def _execute_recorder(self, task, infra) -> bool:
        dispatched.append(task)
        return real_execute(self, task, infra)

    TaskDispatch.execute = _execute_recorder
    return clicks, dispatched


def preflight() -> dict:
    """只读探测真机：adb 可达性、游戏是否运行、截图尺寸、当前场景。"""
    from arknights_mower.utils import config
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.recognize import Recognizer

    info: dict = {"ok": False}
    print(f"[pre] adb          = {config.conf.adb}")
    print(f"[pre] maa_adb_path = {config.conf.maa_adb_path}")
    print(f"[pre] touch_method = {config.conf.touch_method}")
    print(f"[pre] droidcast    = {config.conf.droidcast.enable}")

    device = Device()
    print(f"[pre] Device() OK  device_id = {device.device_id}")

    recognizer = Recognizer(device)
    scenes = []
    for i in range(3):
        recognizer.update()
        scene = recognizer.get_scene()
        shape = None if recognizer.img is None else recognizer.img.shape
        scenes.append(scene)
        print(f"[pre] 识别 [{i}] scene={scene}  img={shape}")
        if i < 2:
            idle_wait(1.0)

    info.update(
        {
            "ok": True,
            "device": device,
            "recognizer": recognizer,
            "scenes": scenes,
            "consistent": len(set(scenes)) == 1,
        }
    )
    print(f"[pre] 场景连读 3 次一致 = {info['consistent']}  {scenes}")
    return info


def measure(loop, seconds: float) -> int:
    """在 `seconds` 内观察 ticks 的增量。观察者仅用 Event.wait 采样。"""
    start = loop.ticks
    idle_wait(seconds)
    return loop.ticks - start


def run_check(args) -> bool:
    from arknights_mower.scheduler.bootstrap import _build_dispatch, _build_planners
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.scheduler.state import SchedulerState
    from arknights_mower.utils.operators import build_global_plan

    clicks, dispatched = _install_guards()
    ObservedLoop = _make_observed_loop()

    print("\n[1] 只读预探测（真机）")
    info = preflight()

    print("\n[2] 构造 SchedulerState（save_conf 置 no-op）")
    with no_save_conf() as save_calls:
        state = SchedulerState(global_plan=build_global_plan())
    print(f"    房间数 = {len(state.plan)}  save_conf 被拦截 = {len(save_calls)}")

    pause = ThreadPauseController()
    clock = WallClockStop(
        args.seconds + CLOCK_GRACE_SECONDS, on_timeout=pause.request_stop
    ).start()

    from arknights_mower.scheduler.bootstrap import _build_infra

    infra = _build_infra(info["device"], state, pause)
    print(f"    pause 同一对象 = {infra.pause is pause}")
    loop = ObservedLoop(state, _build_planners(state), _build_dispatch(), infra)

    results: list[tuple[str, bool]] = []
    valid = True

    def record(name: str, ok: bool) -> None:
        results.append((name, ok))
        print(f"    -> {'PASS' if ok else 'FAIL'}  {name}")

    thread = threading.Thread(target=loop.run_forever, daemon=True, name="main-loop")
    try:
        print(f"\n[3] 启动 MainLoop（观察前 settle {args.settle}s）")
        thread.start()
        idle_wait(args.settle)
        print(f"    启动后 alive = {thread.is_alive()}  ticks = {loop.ticks}")

        # ---------- 正向对照（必须先成立，否则观察量失效） ----------
        print(f"\n[4] 正向对照：未 pause，观察 {args.window}s")
        delta_normal = measure(loop, args.window)
        print(f"    ticks 增量 = {delta_normal}（必须 > 0）")
        if delta_normal <= 0:
            valid = False
            print("    [INVALID] 正向对照不增长 —— 观察量失效，本次验证无效，不得判 PASS")
        record("正向对照：未 pause 时 ticks 增长", delta_normal > 0)

        # ---------- pause 后必须停止推进 ----------
        print(f"\n[5] pause() 后观察（settle {args.settle}s + 窗口 {args.window}s）")
        pause.pause()
        print(f"    is_paused = {pause.is_paused}  alive = {thread.is_alive()}")
        idle_wait(args.settle)  # 让线程走到 wait_if_paused 并停稳
        frozen = loop.ticks
        delta_paused = measure(loop, args.window)
        print(f"    ticks 增量 = {delta_paused}（必须 = 0）  冻结读数 = {frozen}")
        record("pause 后 is_paused = True", pause.is_paused)
        record("pause 后线程仍存活（是被挂起，不是崩了）", thread.is_alive())
        record("pause 后 ticks 增量为 0", delta_paused == 0)

        # ---------- resume 后必须恢复推进 ----------
        print(f"\n[6] resume() 后观察 {args.window}s")
        pause.resume()
        print(f"    is_paused = {pause.is_paused}")
        delta_resumed = measure(loop, args.window)
        print(f"    ticks 增量 = {delta_resumed}（必须 > 0）")
        record("resume 后 is_paused = False", not pause.is_paused)
        record("resume 后 ticks 增长", delta_resumed > 0)

        # ---------- request_stop 必须在 ≤10s 内结束线程 ----------
        print(f"\n[7] request_stop() 计时（判据 ≤{STOP_DEADLINE_SECONDS}s）")
        t0 = time.monotonic()
        pause.request_stop()
        thread.join(timeout=STOP_DEADLINE_SECONDS)
        stop_elapsed = time.monotonic() - t0
        print(f"    线程结束耗时 = {stop_elapsed:.2f}s  alive = {thread.is_alive()}")
        record("request_stop 后线程未存活", not thread.is_alive())
        record(
            f"线程结束耗时 ≤{STOP_DEADLINE_SECONDS}s",
            stop_elapsed <= STOP_DEADLINE_SECONDS,
        )
    except KeyboardInterrupt:
        print("\n    Ctrl+C，正在停止...")
    finally:
        clock.cancel()
        pause.request_stop()
        thread.join(timeout=STOP_DEADLINE_SECONDS)

    print(f"\n[8] 零点击 / 零派发断言")
    print(f"    tap+swipe+swipe_path 调用数 = {len(clicks)}")
    print(f"    TaskDispatch.execute 调用数 = {len(dispatched)}")
    print(f"    队列剩余 = {state.task_queue.peek()}")
    record("零点击（tap/swipe 计数 0）", len(clicks) == 0)
    record("零任务派发", len(dispatched) == 0)
    record("队列为空", state.task_queue.peek() is None)
    record("观察量独立于 pause（正向对照已成立）", valid)

    passed = sum(1 for _, ok in results if ok)
    print(f"\n[T1.3] {passed}/{len(results)} 项通过; 观察量有效 = {valid}")
    if not valid:
        print("[INVALID] 观察量失效 —— 本次 T1.3 结论无效（不是 FAIL，是不成立）")
    return valid and passed == len(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="T1.3 pause/stop 有效性（零点击）")
    parser.add_argument("--seconds", type=int, default=90, help="墙钟上限（秒）")
    parser.add_argument("--settle", type=float, default=3.0, help="每段前置稳定时间")
    parser.add_argument("--window", type=float, default=4.0, help="每段观察窗口")
    args = parser.parse_args()

    quiet_logs()
    print(f"[0] 观察者实现：MainLoop._run_planners 计数器 + threading.Event.wait 采样")
    print(f"[0] 墙钟上限 = {args.seconds}s（安全网 {args.seconds + CLOCK_GRACE_SECONDS}s）")

    ok = False
    try:
        ok = run_check(args)
    except KeyboardInterrupt:
        print("\n    Ctrl+C，正在停止...")
    print("\n[OK] T1.3 全部通过" if ok else "\n[FAIL] T1.3 存在未通过项或无效")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())