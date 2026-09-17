"""实机换班验证：用真实设备跑一个 SHIFT_ON 任务，观察完整执行链路。

⚠️ 这个脚本会真的点击游戏！只在确认游戏已登录、且你愿意让它操作时运行。

用法（项目根目录）：
    .venv\\Scripts\\python.exe tests\\live\\verify_shift_live.py --room room_1_1
    .venv\\Scripts\\python.exe tests\\live\\verify_shift_live.py --room room_1_1 --seconds 120

安全设计：
  - 只跑一个房间（不是整套计划）
  - 硬性墙钟上限（默认 180 秒），到点强制 request_stop()，不会失控
  - 全程落在日志里，每个 step 都能看到
  - Ctrl+C 也能安全中止（finally 里会 request_stop）
"""

import argparse
import logging
import sys
import threading
import time
from datetime import datetime
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


def quiet_logs() -> None:
    from arknights_mower.utils.log import logger

    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        handler.setLevel(logging.INFO)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", default="room_1_1", help="要换班的房间")
    parser.add_argument("--seconds", type=int, default=180, help="墙钟上限（秒）")
    parser.add_argument(
        "--agents",
        default=None,
        help="逗号分隔的干员列表；省略则用 plan.json 里该房间的计划",
    )
    args = parser.parse_args()

    from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.operators import build_global_plan

    quiet_logs()

    from arknights_mower.scheduler.bootstrap import _build_dispatch, _build_infra
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.scheduler.loop import MainLoop
    from arknights_mower.scheduler.state import SchedulerState

    room = args.room

    print(f"[1] 加载计划，目标房间 = {room}")
    state = SchedulerState(global_plan=build_global_plan())
    if room not in state.plan:
        print(f"[FAIL] 计划里没有房间 {room}")
        print(f"       可用房间: {sorted(state.plan.keys())}")
        return 1

    if args.agents:
        agents = args.agents.split(",")
    else:
        agents = [r.agent for r in state.plan[room]]
    print(f"    计划干员: {agents}")

    print("\n[2] 连接设备")
    pause = ThreadPauseController()
    v1_device = Device()
    infra = _build_infra(v1_device, state, pause)
    print(f"    InfraKit OK, pause 同一对象 = {infra.pause is pause}")

    print("\n[3] 压入 SHIFT_ON 任务（只这一个房间）")
    state.task_queue.push(
        SchedulerTask(
            time=datetime.now(),
            type=TaskTypes.SHIFT_ON,
            plan={room: agents},
        )
    )
    print(f"    队列: {state.task_queue.peek()}")

    loop = MainLoop(state, [], _build_dispatch(), infra)
    thread = threading.Thread(target=loop.run_forever, daemon=True)

    print(f"\n[4] 启动 MainLoop（墙钟上限 {args.seconds}s）")
    print("    >>> 现在开始会真的点击游戏 <<<")
    thread.start()

    deadline = time.time() + args.seconds
    last = ""
    try:
        while thread.is_alive() and time.time() < deadline:
            time.sleep(1)
            task = state.task_queue.peek()
            status = (
                "队列空(任务已完成或失败)"
                if task is None
                else f"执行中 type={task.type}"
            )
            if status != last:
                print(
                    f"    [{time.strftime('%H:%M:%S')}] {status}  error={state.error}"
                )
                last = status
    except KeyboardInterrupt:
        print("\n    Ctrl+C，正在停止...")
    finally:
        pause.request_stop()
        thread.join(timeout=15)

    hit_deadline = thread.is_alive() or time.time() >= deadline
    print(f"\n[5] 结束: alive={thread.is_alive()}  超时={hit_deadline}")
    print(f"    state.error = {state.error}")
    print(f"    剩余队列 = {state.task_queue.peek()}")

    if thread.is_alive():
        print("\n[WARN] 达到墙钟上限仍未结束 —— 任务卡住了，这本身是有效发现")
    elif state.error:
        print("\n[FAIL] 任务执行失败（见上方日志的 executor failed）")
        return 1
    else:
        print("\n[OK] 任务执行完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
