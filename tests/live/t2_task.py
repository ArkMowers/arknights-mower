"""T2 换班任务与房间读数的**共享驱动**（实机脚本，不参与门禁 G1 收集）。

T2.2/T2.3/T2.4 三项都要"真实跑一次换班任务"并"进房间读构成"，逐字复制会超
300 行上限且口径易漂移。本模块收口这两件事：

| 原语 | 用途 |
|---|---|
| `run_shift_task` | 压一个 `SHIFT_ON` 任务 → 真实 `MainLoop` 跑一轮 → 返回 `state.error` / 队列长度 |
| `read_room_via_nav` | 进房间 → 打开详情面板 → 用 `read_room_stable` **连读 N 次**（T2.5 规范） |

⚠️ `MainLoop.run_forever` 是死循环，因此放**守护线程**里跑，等任务被 `pop()`
（即本轮判定已完成）或墙钟到点后 `request_stop()`。

⚠️ 本文件名**不以 `_tests.py` 结尾**，因此不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations


def run_shift_task(
    infra, state, room: str, plan: list[str], seconds: float
) -> dict:
    """压一个 `SHIFT_ON` 任务进队列，用真实 `MainLoop` 跑一轮并取证。

    返回 `{"still_alive", "error", "queue_len"}`：
    - `still_alive=True` 表示墙钟到点任务仍未结束（本身是有效发现）
    - `error` 即 `state.error`，BUG-2 的核心判据
    - `queue_len` 为 0 表示任务已被 `pop()`（`MainLoop` 每轮都会 pop）
    """
    import threading
    import time as _time
    from datetime import datetime

    from arknights_mower.scheduler.bootstrap import _build_dispatch
    from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
    from arknights_mower.scheduler.loop import MainLoop

    state.task_queue.clear()
    state.error = False
    state.task_queue.push(
        SchedulerTask(
            time=datetime.now(), type=TaskTypes.SHIFT_ON, plan={room: list(plan)}
        )
    )
    loop = MainLoop(state, [], _build_dispatch(), infra)

    def _target() -> None:
        # `Resettable.wait_if_paused` 用 `MowerExit` 打断循环（这是安全网的基础）。
        # 在这里接住它，避免线程抛出未捕获异常、在日志里留下误导性的 traceback。
        from arknights_mower.utils.csleep import MowerExit

        try:
            loop.run_forever()
        except MowerExit:
            pass

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    deadline = _time.monotonic() + seconds
    while thread.is_alive() and _time.monotonic() < deadline:
        from tests.live.t1_common import idle_wait

        idle_wait(1.0)
        if state.task_queue.peek() is None:
            # 任务已被 pop ⇒ 本轮判定已完成，让循环自己退出
            break

    infra.pause.request_stop()
    thread.join(timeout=20)
    result = {
        "still_alive": thread.is_alive(),
        "error": bool(getattr(state, "error", False)),
        "queue_len": len(state.task_queue),
    }
    # `request_stop()` 置位的是**粘性** stop（`thread_pause.py:28-30`）。调用方
    # 通常还要继续导航去读房间终态，因此这里解除 stop，避免复查腿被 `MowerExit`
    # 打断。仅当控制器提供 `resume_run`（见 `t2_common.resettable_pause_class`）。
    resume = getattr(infra.pause, "resume_run", None)
    if resume is not None:
        resume()
    return result


def read_room_via_nav(nav, recog, infra, state, room: str, label: str = "",
                      legs=None):
    """进 `room` → 打开详情面板 → 连读 `DEFAULT_STABLE_READS` 次。

    返回 `(readings, consistent)`。这是 T2.5 规范要求的**唯一**读数入口：
    一次读数不得作为结论，不一致即判 INVALID（由调用方负责裁决）。

    `legs`：可选的 `NavLegs`。传入时，进入房间的两条腿会用 `NavLegs` 记录，
    调用方据此直接断言"201 -> 205 -> 230 出现了"—— 比事后从 `SceneTracker`
    的采样序列里找更可靠（`_get_scene` 的采样点可能跳过短暂的 205）。
    """
    from tests.live.t2_read import (
        DEFAULT_STABLE_READS,
        impossible_duplicates,
        read_room_stable,
        reset_room_scroll,
        vary_slot,
    )
    from tests.live.t2_nav import scene_of

    from arknights_mower.scheduler.infra.room_reader import RoomReader

    print(f"\n    [{label or room}] 只读探测 {room} 构成")
    if int(nav._get_scene()) != int(scene_of("INFRA_MAIN")):
        if legs is not None:
            legs.navigate(scene_of("INFRA_MAIN"), f"nav_to_infra:{label or room}")
        else:
            nav.navigate(scene_of("INFRA_MAIN"))

    enter_scene = None
    if legs is not None:
        enter = legs.enter_room(room)
        enter_scene = enter["after"]
    else:
        nav.enter_room(room)
    if int(nav._get_scene()) == int(scene_of("INFRA_DETAILS")):
        if legs is not None:
            legs.open_detail(room)
        else:
            nav._wait_room_detail()

    reader = RoomReader(infra.device, recog, nav)
    # **必须**每次读数前复位滚动：`scan_room` 读第 4~5 槽位时会向上滑屏却不滑回，
    # 不复位则第 2 次起读到错误行（T2.5 已证实，见 `tmp/t2_5_diag_restore.py`）。
    readings, consistent = read_room_stable(
        reader,
        room,
        state,
        DEFAULT_STABLE_READS,
        reset=lambda: reset_room_scroll(nav, recog),
    )
    for i, reading in enumerate(readings, 1):
        print(f"      第 {i} 次: {reading}")
    dup = impossible_duplicates(readings)
    print(f"      一致={consistent} 不一致槽位={vary_slot(readings)}")
    if dup:
        # 同宿舍不可能有两个同名干员 ⇒ 读数不可信，不能作为快照依据。
        print(f"      [不可信] 同屏重名 {dup}（物理不可能）⇒ 本次快照作废")
    return readings, consistent and not dup

def recover_to_index(nav, recog, max_back: int = 2) -> dict:
    """环境恢复：把游戏从选人面板/确认框救回 INDEX，**最多按 `max_back` 次返回键**。

    ⚠️ 教训（2026-09-19）：初版环境恢复无上限地连按返回键，结果按到了
    `EXIT_GAME` 确认框，把游戏**整个退出**（`dumpsys window` 显示 launcher
    在前台，需 `monkey` 重新拉起）。因此这里：
    - 返回键步数**硬上限**（默认 2 次）；
    - 遇到 `224` 确认框走 `dismiss_leave_infra_dialog`（点确认框，不按返回）。
    """
    from tests.live.t2_nav import dismiss_leave_infra_dialog, scene_of
    from tests.live.t2_probe import scene_name

    if int(nav._get_scene()) == int(scene_of("LEAVE_INFRASTRUCTURE")):
        result = dismiss_leave_infra_dialog(nav, recog)
        return {"steps": ["dismiss_224"], "after": result["after"]}

    steps: list[str] = []
    for _ in range(max_back):
        name = scene_name(int(nav._get_scene()))
        if name in ("INDEX", "INFRA_MAIN"):
            break
        nav._back()
        nav.wait_scene_stable(max_duration=3.0, min_stable=2)
        steps.append(name)
    return {"steps": steps, "after": int(nav._get_scene())}
