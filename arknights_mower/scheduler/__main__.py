"""scheduler 包的命令行入口。

定位：**诊断/调试入口**，不是生产启动路径。生产启动走 `bootstrap.run()`。

用法：
    python -m arknights_mower.scheduler                  # 正常启动（走默认 StartMode.FULL）
    python -m arknights_mower.scheduler test-scene       # 只读：连续打印 20 次当前 scene
    python -m arknights_mower.scheduler test-arrange     # 启动，start_type="test"

`test-arrange` 说明：它只是以非标准 `start_type` 调用 `run()`，用于人工调试启动流程。
它**不再**像以前那样硬编码往任务队列里塞一条换班假任务 —— 那条假任务属于
启动期硬编码违规，已随 S1 删除。现在 `test-arrange` 与普通启动的差别仅在于
`start_type` 不匹配任何 `StartMode`，因此既不恢复待执行任务、也不清空队列。

关于等待：两个入口都不再使用阻塞式固定睡眠。等待界面就绪一律走
`Navigator.wait_scene_stable()`（连续截图的像素差异判断动画/加载是否结束）
或 `PauseController.wait()`（pause-aware，且可被 `request_stop()` 提前打断）。
"""

import sys

from arknights_mower.scheduler.bootstrap import run


def _recognize(recognizer):
    """采一帧并返回 scene —— 与 `bootstrap._build_infra` 内的 get_scene 同形。"""
    recognizer.update()
    return recognizer.get_scene()


def test_scene():
    """只读诊断：连续打印当前 scene，用于人工确认识别层与导航层是否正常。

    每轮先 `wait_scene_stable()` 等界面稳定再采下一次，替代原先固定 5 秒的睡眠：
    语义仍是「等界面就绪」，但由截图差异判定而非固定时长，且可被停止信号打断。
    """
    from arknights_mower.scheduler.graph import build_default_graph
    from arknights_mower.scheduler.infra.pc_device_port import PCDevicePort
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.scheduler.navigator import Navigator
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.recognize import Recognizer
    from arknights_mower.utils.scene import SceneComment

    device = Device()
    pause = ThreadPauseController()
    recognizer = Recognizer(device)
    navigator = Navigator(
        PCDevicePort(device, pause),
        build_default_graph(),
        lambda: _recognize(recognizer),
        pause,
        recognizer,
    )

    for i in range(20):
        recog_scene = _recognize(recognizer)
        comment = SceneComment.get(recog_scene, "UNKNOWN")
        print(f"[{i}] scene={recog_scene} ({comment})")
        navigator.wait_scene_stable()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test-scene":
        test_scene()
    elif len(sys.argv) > 1 and sys.argv[1] == "test-arrange":
        run(start_type="test")
    else:
        run()