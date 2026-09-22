"""T2.3 — BUG-2 失败可上报（S13 item 4；**点击类**）。

BUG-2 的诉求
------------
换班"扫不到目标干员"这类**业务失败**必须被上报，链路为：
1. `AgentSwapScanMixin._check_end_of_list()` / `_advance_page()` 抛
   `AgentSwapError`（**普通异常**，不是 `StepRetry`/`StepRestart`）；
2. 异常穿透到 `TaskDispatch.execute` → 记 `executor failed for task` 并 `return False`；
3. `MainLoop` 记 `task failed` 且置 `state.error = True`，任务被 `pop()`。

⚠️ 为什么必须"构造"扫不到的场景（而不是塞一个真不存在的干员名）
----------------------------------------------------------------
S13 原方案是"把不存在的干员名塞进 `--agents`，扫描必然走到列表末尾"。**实测走不到**：

- 名字不认识 ⇒ `_get_target_filter` 回落 `DEFAULT_FILTER="ALL"` ⇒ 需翻 27+ 页。
  实测（`tmp/t2_3_run2.log`）翻到第 5~20 页时游戏切 `LOGIN_LOADING(104)`，
  `_run_steps` 直接 `unexpected scene 104, abort`（`agent_swap_base.py:110`）并
  `return False` —— **末尾守卫永不触发**。
- 换成职介明确的真实名字（`末药`=MEDIC）后，面板**没有真正收窄**：
  `tmp/t2_3_run3.log` 显示 `filter=MEDIC` 但扫出的 names 含 `能天使`(SNIPER)、
  `德克萨斯`(PIONEER)，即仍是全体干员 ⇒ 同样要翻 27+ 页，同样到不了末尾。

因此改用**产品自身**的翻页上限守卫：把 `MAX_PAGE`（`constants.py`，产品常量，
**产品代码不改**）从 50 压到 3。`_advance_page` 到上限即抛
`AgentSwapError("AgentSwap: max page reached")` —— 这与"目标扫不到"是**同一语义**，
只是更快到达，且**不点任何干员**（`TARGET` 不是真实干员名，永远不会命中）。

正控（证伪对照）
----------------
主臂若 `state.error` 仍为 `False`，必须证明**下游链路本身是好的**，否则无法把
缺陷定位到 `_run_steps`。正控臂把 `agent_swap_base.py:126-128` 的
`except Exception: ... return False` **改成 `raise`**（一行修复的等价模拟，
`_run_steps_fixed` 是原文逐字副本），下游三条判据必须随即全部走通。

判据（逐条见 `_summarize`，PASS = 该**预测**被证实）：主臂 7 条（预期全部呈现缺陷）
+ 正控臂 4 条（预期全部走通）。二者同时成立 ⇒ 缺陷被完整复现并定位 ⇒ 结论 **失败**。

用法：`.venv\\Scripts\\python.exe tests\\live\\t2_3_bug2_report.py [--seconds 300]`

安全边界
--------
- **会点击游戏**：进 `room_1_2` → 打开选择面板 → 翻页扫描（**不点任何干员**：
  `TARGET` 非真实干员名，不可能命中）。
- 副作用：`RoomReader._persist()` 写 `tmp/mower.db` → 按 T2 规约 7 备份/还原。
- `state` 全程 `no_save_conf()`，不写 `conf.yml`。
- `finally` 里 `request_stop()`；`--seconds` 墙钟上限到时硬中断。
"""

import sys
from pathlib import Path

# 直接执行时 sys.path[0] 是 tests/live/，连 `tests` 包都解析不到；不硬算层数，向上找锚点。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "tests" / "_bootstrap.py").is_file():
        sys.path.insert(0, str(_parent))
        break

from tests._bootstrap import REPO_ROOT  # noqa: E402,F401

from tests.live.t2_common import (  # noqa: E402
    build_device,
    build_state,
    operator_rooms,
)
from tests.live.t2_nav import NavLegs, scene_of  # noqa: E402
from tests.live.t2_probe import CallMeter, SceneTracker, SwapCounters  # noqa: E402
from tests.live.t2_runner import run_probe_script, run_with_logs  # noqa: E402
from tests.live.t2_task import run_shift_task  # noqa: E402

ROOM = "room_1_2"
# 非真实干员名 ⇒ `_get_target_filter` → "ALL"、`_get_target_sort` → DEFAULT_SORT，
# 面板上永远不可能命中它，因此**全程不点任何干员**（无半成品排班的充分条件）。
TARGET = "T2_不存在的干员_zzz"
MAX_PAGE_OVERRIDE = 3

# 主臂的吞异常点（`agent_swap_base.py:127` 的 `logger.exception`）与
# 执行器层的重抛点（`executors/base.py:104`）日志前缀不同，据此区分两层。
SWALLOW_MARK = "AgentSwap step select: unhandled error"
GUARD_MARK = "max page reached"
DISPATCH_MARK = "executor failed for task"
TASKFAIL_MARK = "task failed"


def _run_steps_fixed(self, steps: list) -> bool:
    """`agent_swap_base.py:_run_steps` 的**逐字副本**，仅末尾一行不同。

    原文（缺陷点）：

        except Exception:
            logger.exception(f"AgentSwap step {step.name}: unhandled error")
            return False                      # ← 失败被降级为"正常结束"

    本副本：

        except Exception:
            logger.exception(f"AgentSwap step {step.name}: unhandled error")
            raise                             # ← 唯一改动

    正控用它替换 `AgentSwapBase._run_steps`，以证明"只要不吞，下游就通"。
    """
    from collections import deque

    from arknights_mower.scheduler.scene import Scene
    from arknights_mower.scheduler.steps import StepRestart, StepRetry
    from arknights_mower.utils.log import logger

    initial = list(steps)
    queue = deque(initial)
    while queue:
        self._pause.wait_if_paused()
        scene = self._get_scene()
        if scene not in (
            Scene.RIIC_OPERATOR_SELECT,
            Scene.INFRA_ARRANGE_ORDER,
            Scene.LOADING,
            Scene.CONNECTING,
        ):
            logger.warning(f"AgentSwap: unexpected scene {scene}, abort")
            return False
        if scene in (Scene.LOADING, Scene.CONNECTING):
            continue
        step = queue[0]
        logger.info(f"AgentSwap step={step.name} scene={scene}")
        if step.enter(scene):
            try:
                extra = step.act() if step.act else None
                queue.popleft()
                if extra is not None:
                    queue = deque(extra) + queue
            except StepRetry:
                continue
            except StepRestart:
                queue = deque(initial)
            except Exception:
                logger.exception(f"AgentSwap step {step.name}: unhandled error")
                raise
    return True


def _probe(args, pause) -> dict:
    from arknights_mower.scheduler.services import agent_swap_scan as scan_mod
    from arknights_mower.scheduler.services.agent_swap_base import AgentSwapBase
    from arknights_mower.utils.path import get_path

    db_path = Path(get_path("@app/tmp")) / "mower.db"
    before = operator_rooms(db_path)

    port, recog, infra = build_device(pause)
    nav = infra.navigator
    tracker = SceneTracker(nav)
    legs = NavLegs(nav, tracker, CallMeter(_recording(port)))

    print(f"[2] 导航进入 {ROOM}（只为满足 executor 前置场景）")
    legs.navigate(scene_of("INFRA_MAIN"), "to_infra_main")
    legs.enter_room(ROOM)

    state, _workshop, save_calls = build_state()
    infra.state = state
    arm_seconds = max(90.0, args.seconds / 2)

    original_pages = scan_mod.MAX_PAGE
    scan_mod.MAX_PAGE = MAX_PAGE_OVERRIDE
    print(
        f"[3] 主臂：MAX_PAGE {original_pages} -> {MAX_PAGE_OVERRIDE}"
        f"（产品自身的翻页上限守卫）target={TARGET!r}"
    )
    try:
        main, main_lines = run_with_logs(
            lambda: run_shift_task(infra, state, ROOM, [TARGET], arm_seconds)
        )
        print(
            f"    error={main['error']}  queue_len={main['queue_len']}"
            f"  still_alive={main['still_alive']}"
        )

        print("\n[4] 正控臂：把 `_run_steps` 吞异常的 `return False` 改成 `raise`")
        state2, _w2, _c2 = build_state()
        infra.state = state2
        original_run_steps = AgentSwapBase._run_steps
        AgentSwapBase._run_steps = _run_steps_fixed
        try:
            control, control_lines = run_with_logs(
                lambda: run_shift_task(infra, state2, ROOM, [TARGET], arm_seconds)
            )
        finally:
            AgentSwapBase._run_steps = original_run_steps
        print(
            f"    error={control['error']}  queue_len={control['queue_len']}"
            f"  still_alive={control['still_alive']}"
        )
    finally:
        scan_mod.MAX_PAGE = original_pages

    after = operator_rooms(db_path)
    return {
        "main": main,
        "control": control,
        "main_lines": main_lines,
        "control_lines": control_lines,
        "unchanged": before == after,
        "before": before,
        "after": after,
        "save_calls": len(save_calls),
        "legs": legs.legs,
        "max_page_original": original_pages,
        "arm_seconds": arm_seconds,
    }


def _recording(port) -> list:
    from tests.live.t2_common import recording_port

    return recording_port(port)


def _summarize(result: dict, lines: list) -> bool:
    main = result["main"]
    control = result["control"]
    mc = SwapCounters(result["main_lines"])
    cc = SwapCounters(result["control_lines"])

    print("\n[6] 主臂（未修复）关键日志")
    for line in mc.find(GUARD_MARK)[:2]:
        print(f"    {line[:200]}")
    for line in mc.find(SWALLOW_MARK)[:2]:
        print(f"    {line[:200]}")

    print("\n[7] 正控臂（`return False` -> `raise`）关键日志")
    for line in cc.find(DISPATCH_MARK)[:2]:
        print(f"    {line[:200]}")
    for line in cc.find(TASKFAIL_MARK)[:2]:
        print(f"    {line[:200]}")

    # 每条判据是一个**预测**；PASS = 预测被证实。
    checks = {
        "[主] 到达翻页上限并抛出 AgentSwapError": mc.count(GUARD_MARK) > 0,
        "[主] 异常被 `_run_steps` 吞掉（记录 unhandled error）":
            mc.count(SWALLOW_MARK) > 0,
        "[主] 未到达 dispatch（无 executor failed for task）":
            mc.count(DISPATCH_MARK) == 0,
        "[主] 主循环未记 task failed": mc.count(TASKFAIL_MARK) == 0,
        "[主] state.error 未被置位（BUG-2 现象）": main["error"] is False,
        "[主] 任务未结束、仍挂在队列里": main["queue_len"] > 0,
        "[主] 无半成品排班（房间构成未变）": result["unchanged"],
        "[正控] 守卫仍触发 AgentSwapError": cc.count(GUARD_MARK) > 0,
        "[正控] dispatch 记 executor failed for task":
            cc.count(DISPATCH_MARK) > 0,
        "[正控] 主循环记 task failed": cc.count(TASKFAIL_MARK) > 0,
        "[正控] state.error == True 且任务已清空":
            control["error"] is True and control["queue_len"] == 0,
    }
    print("\n[8] 判据逐条结果（PASS = 预测被证实）")
    passed = 0
    for name, good in checks.items():
        print(f"    -> {'PASS' if good else 'FAIL'}  {name}")
        passed += int(good)

    main_ok = all(list(checks.values())[:7])
    control_ok = all(list(checks.values())[7:])
    print(f"\n[T2.3] {passed}/{len(checks)} 条预测成立"
          f"（主臂缺陷复现={main_ok} 正控下游走通={control_ok}）")
    print(f"[T2.3] 主臂 MAX_PAGE {result['max_page_original']} -> {MAX_PAGE_OVERRIDE}，"
          f"臂预算 {result['arm_seconds']:.0f}s；save_conf 调用 {result['save_calls']} 次")

    if main_ok and control_ok:
        print("[结论] 失败（产品缺陷）：失败被 `_run_steps` 降级为正常结束，"
              "`state.error` 永远为 False。")
        print("[归因] 代码问题 —— `agent_swap_base.py:126-128` 的 "
              "`except Exception: ... return False`；"
              "`AgentSwapError` 已按约定为普通异常，下游 dispatch/loop 经正控证明完好。")
    else:
        print("[结论] INVALID：预测未全部成立，本次复现不成立，需重跑。")
    return False


def main() -> int:
    return run_probe_script(
        description="T2.3 BUG-2 失败可上报",
        boundary="安全边界：翻页扫描但不点干员（TARGET 非真实干员名，不可能命中）",
        probe=_probe,
        summarize=_summarize,
        default_seconds=300,
    )


if __name__ == "__main__":
    raise SystemExit(main())