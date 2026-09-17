"""只读探测：打开指定房间的干员选择面板，读出真实列表顺序，然后原路退出。

⚠️ 这个脚本会点击游戏，但**只点击「空位」打开选择面板**，绝不点击任何干员。
   它的目的是回答一个问题：free 补位分支实际会点到哪个干员？

背景：
  AgentSwapService._do_select() 的 free 分支（agent_swap_service.py:222-232）
  取 self._cache 里第一个「在 _agent_list 中」的条目就点，不判断该干员是否
  已经站在房里。若面板把已上场干员排在最前，就会点中它 -> 取消勾选 -> 房间少人。
  本脚本复现 _do_scan 的读数，让这个推断变成可判定的事实。

用法（项目根目录）：
    .venv\\Scripts\\python.exe tests\\live\\probe_select_panel.py --room dormitory_2
    .venv\\Scripts\\python.exe tests\\live\\probe_select_panel.py --room dormitory_2 --slot 2

安全性：
  - 只 tap 一次「空位」，其余全是 back 返回
  - 结束前强制退回到 INFRA_MAIN
  - 不写入任何状态、不提交任何变更
"""

import argparse
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", default="dormitory_2")
    parser.add_argument("--slot", type=int, default=0, help="点第几个空位(默认0=左上)")
    args = parser.parse_args()

    import logging

    from arknights_mower.scheduler.constants import INFRA_ROOM_SLOT_TAP
    from arknights_mower.scheduler.graph import build_default_graph
    from arknights_mower.scheduler.infra.pc_device_port import PCDevicePort
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.scheduler.navigator import Navigator
    from arknights_mower.scheduler.scene import Scene
    from arknights_mower.utils.character_recognize import operator_list
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.log import logger
    from arknights_mower.utils.recognize import Recognizer

    logger.setLevel(logging.INFO)
    for h in logger.handlers:
        h.setLevel(logging.INFO)

    room = args.room
    pause = ThreadPauseController()
    dev = Device()
    port = PCDevicePort(dev, pause)
    recog = Recognizer(dev)

    def get_scene() -> int:
        recog.update()
        return recog.get_scene()

    nav = Navigator(port, build_default_graph(), get_scene, pause, recog)

    print(f"[1] 导航到 INFRA_MAIN，目标房间 = {room}")
    if not nav.navigate(Scene.INFRA_MAIN):
        print("[FAIL] 无法到达基建主界面")
        return 1
    print(f"    scene = {get_scene()}")

    print(f"\n[2] 进入 {room}")
    if not nav.enter_room(room):
        print(f"[FAIL] 无法进入 {room}")
        nav.navigate(Scene.INFRA_MAIN)
        return 1
    scene = get_scene()
    if scene == Scene.INFRA_DETAILS:
        nav._wait_room_detail()
        scene = get_scene()
    print(f"    scene = {scene}")

    print(f"\n[3] 点第 {args.slot} 个空位打开选择面板（这是唯一一次非返回点击）")
    port.tap(*INFRA_ROOM_SLOT_TAP)
    nav.wait_scene_stable(max_duration=2.0, min_stable=3)
    panel_scene = get_scene()
    print(f"    scene = {panel_scene}  (期望 {Scene.INFRA_ARRANGE_ORDER})")

    if panel_scene != Scene.INFRA_ARRANGE_ORDER:
        print(f"[WARN] 未进入选择面板（scene={panel_scene}），放弃探测")
        nav.navigate(Scene.INFRA_MAIN)
        return 1

    print("\n[4] 复现 _do_scan 的读数：operator_list(full_scan=True)")
    recog.update()
    cache = operator_list(recog.img, full_scan=True)
    names = [r[0] if isinstance(r, tuple) else r for r in cache]
    print(f"    读到 {len(cache)} 个条目:")
    for i, item in enumerate(cache):
        name = item[0] if isinstance(item, tuple) else item
        box = item[1] if isinstance(item, tuple) else None
        print(f"      [{i}] {name}   box={box}")

    from arknights_mower.data import agent_list

    agent_set = set(agent_list)

    print("\n[5] 结论推演 — free 分支会点谁？")
    pick = None
    for name in names:
        if name in agent_set:
            pick = name
            break
    if pick is None:
        print("    没有合法候选 -> free 分支 while 循环走完，return None")
        print("    后果：_free_count 不减，回到 scan -> 翻页直到 MAX_PAGE")
    else:
        print(f"    free tap 会点 = 【{pick}】  (列表第 {names.index(pick)} 位)")

    print("\n[6] 该房间计划内的干员是否出现在列表里？")
    from arknights_mower.scheduler.state import SchedulerState
    from arknights_mower.utils.operators import build_global_plan

    state = SchedulerState(global_plan=build_global_plan())
    planned = [r.agent for r in state.plan.get(room, [])]
    print(f"    计划 = {planned}")
    for p in planned:
        if p == "Free":
            continue
        mark = "⚠️ 在列表中(会被误点)" if p in names else "不在列表中(安全)"
        print(f"      {p}: {mark}")

    print("\n[7] 原路退出（不点击任何干员）")
    for i in range(4):
        nav._back()
        nav.wait_scene_stable(max_duration=1.5, min_stable=2)
        sc = get_scene()
        print(f"    back {i + 1} -> scene={sc}")
        if sc == Scene.INFRA_MAIN:
            break
    nav.navigate(Scene.INFRA_MAIN)
    print(f"    最终 scene = {get_scene()}")

    print("\n[OK] 探测结束，未提交任何变更")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
