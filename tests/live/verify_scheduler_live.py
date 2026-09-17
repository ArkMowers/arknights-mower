"""实机验证脚本：在真实设备上跑 v5 scheduler，观察场景识别与 pause/stop 行为。

用法（项目根目录）：
    .venv\\Scripts\\python.exe tests\\live\\verify_scheduler_live.py        # 只读探测
    .venv\\Scripts\\python.exe tests\\live\\verify_scheduler_live.py --run  # 真正启动 MainLoop

只读探测（默认）不点击屏幕、不修改任何状态，仅验证：
  1. conf.yml 的 adb 地址/ adb 路径 是否可用
  2. Device() 能否连上、screencap() 是否返回 1920x1080
  3. Recognizer.get_scene() 能否识别当前画面
  4. 场景图从当前场景出发是否有出边（能否导航）

--run 额外启动真实 MainLoop，并验证 A1 修复：
   pause()/resume() 生效，request_stop() 能真正终止 run_forever。
"""

import argparse
import logging
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


def quiet_logs() -> None:
    """utils/log.py 把 level 固定成 DEBUG，识别一帧会刷上百行。

    这里只提高本进程的 logger level，不碰 log.py，也不影响落盘的日志文件。
    """
    from arknights_mower.utils.log import logger

    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        handler.setLevel(logging.INFO)


def probe() -> bool:
    from arknights_mower.utils import config
    from arknights_mower.utils.scene import SceneComment

    quiet_logs()

    print(f"[conf] adb          = {config.conf.adb}")
    print(f"[conf] maa_adb_path = {config.conf.maa_adb_path}")
    print(f"[conf] droidcast    = {config.conf.droidcast.enable}")
    print(f"[conf] touch_method = {config.conf.touch_method}")

    if not Path(config.conf.maa_adb_path).exists():
        print(f"[FAIL] adb 路径不存在: {config.conf.maa_adb_path}")
        return False

    from arknights_mower.utils.device.device import Device

    print("\n[dev] 正在连接设备...")
    try:
        device = Device()
    except Exception as exc:
        print(f"[FAIL] Device() 失败: {exc}")
        return False
    print(f"[dev] OK  device_id = {device.device_id}")

    from arknights_mower.utils.recognize import Recognizer

    recog = Recognizer(device)

    print("\n[recog] 连续识别 5 次：")
    ok = False
    for i in range(5):
        recog.update()
        scene = recog.get_scene()
        label = SceneComment.get(scene, "UNKNOWN")
        shape = None if recog.img is None else recog.img.shape
        print(f"  [{i}] scene={scene} ({label})  img={shape}")
        if scene is not None and scene != -1:
            ok = True
        time.sleep(1)

    if not ok:
        print("\n[WARN] 场景始终为 -1（未知）。请把游戏开到基建/首页再试。")

    from arknights_mower.scheduler.graph import build_default_graph
    from arknights_mower.scheduler.scene import Scene as V2Scene

    graph = build_default_graph()
    scene = recog.get_scene()
    try:
        v2_scene = V2Scene(scene)
    except ValueError:
        print(f"\n[graph] 场景 {scene} 不在 v5 Scene 枚举内，跳过可达性检查")
    else:
        for target in (V2Scene.INFRA_MAIN, V2Scene.INDEX):
            path = graph.find_path(v2_scene, target)
            if path is None:
                print(f"\n[graph] {v2_scene.name} -> {target.name}: 不可达")
            else:
                steps = " -> ".join(f"{t.target.name}" for t in path)
                print(f"\n[graph] {v2_scene.name} -> {target.name}: {len(path)} 步")
                print(f"        {steps}")

    print("\n[OK] 只读探测完成")
    return True


def run_loop() -> bool:
    """用真实 InfraKit 启动 MainLoop，验证 pause/stop 是否真的生效（A1）。"""
    from arknights_mower.scheduler.bootstrap import _build_infra, _build_planners
    from arknights_mower.scheduler.dispatch import TaskDispatch
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.scheduler.loop import MainLoop
    from arknights_mower.scheduler.state import SchedulerState
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.operators import build_global_plan

    print("\n=== 启动 MainLoop（实体链路）===")
    try:
        state = SchedulerState(global_plan=build_global_plan())
    except Exception as exc:
        print(f"[FAIL] SchedulerState 构建失败: {exc}")
        print("       -> 请先在网页界面配置基建排班计划 (plan.json)")
        return False

    pause = ThreadPauseController()
    device = Device()
    infra = _build_infra(device, state, pause)
    print(f"[ok] InfraKit 构建完成; pause 同一对象 = {infra.pause is pause}")

    dispatch = TaskDispatch()
    loop = MainLoop(state, _build_planners(state), dispatch, infra)

    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    time.sleep(2)
    print(f"[1] 运行中: alive={thread.is_alive()}")

    pause.pause()
    time.sleep(1)
    print(f"[2] pause() 后: is_paused={pause.is_paused} alive={thread.is_alive()}")

    pause.resume()
    time.sleep(1)
    print(f"[3] resume() 后: is_paused={pause.is_paused} alive={thread.is_alive()}")

    t0 = time.time()
    pause.request_stop()
    thread.join(timeout=10)
    elapsed = time.time() - t0
    print(f"[4] request_stop() 后 {elapsed:.2f}s: alive={thread.is_alive()}")

    if thread.is_alive():
        print("\n[FAIL] A1 未通过：stop 无法终止 MainLoop")
        return False
    print("\n[OK] A1 通过：stop 能真正终止 MainLoop")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="启动真实 MainLoop")
    args = parser.parse_args()

    if not probe():
        return 1
    if args.run:
        if not run_loop():
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
