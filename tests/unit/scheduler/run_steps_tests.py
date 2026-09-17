"""S2 的 `run_steps()` 运行时行为回归测试。

本文件与 `steps_tests.py` 同属 S2，拆分只为满足 §10.1 的「触碰文件 ≤300 行」。
拆分点按性质划分：`steps_tests.py` 放**静态**断言（AST / 源码 / 对象同一性），
本文件放**行为**断言（真正驱动 `AbstractExecutor.run_steps` 的队列循环）。

覆盖：
- `StepRetry` 原地重试、`StepRestart` 整队重放
- `enter()` 返回 False 时队列不推进
- `start` 场景不匹配时先 `navigate` 再执行
- `act()` 返回的追加步骤插到队首
- 非控制流异常必须继续向上抛（删除 `safe_execute` 后的语义守卫）
- `LEAVE_INFRASTRUCTURE` 场景下点击的就是 `TapPosition` 常量坐标

不使用真实设备：`MockDevicePort` + `MockRecognizer` 驱动，
`ThreadPauseController` 的 Event 默认已 set，因此不产生任何真实等待。
"""

import unittest

from arknights_mower.scheduler.constants import TapPosition
from arknights_mower.scheduler.executors.base import (
    AbstractExecutor,
    Step,
    StepRestart,
    StepRetry,
)
from arknights_mower.scheduler.infra import InfraKit
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer


class FakeNavigator:
    """`run_steps` 只需要 navigator 的这两个成员，用桩即可。"""

    def __init__(self, recognizer) -> None:
        self._recognizer = recognizer
        self.navigated: list[int] = []

    def navigate(self, scene) -> None:
        self.navigated.append(scene)

    def wait_scene_stable(self, **kwargs) -> None:
        return None


class ProbeExecutor(AbstractExecutor):
    """最小可实例化的执行器：只用来驱动 `run_steps`。"""

    def execute(self, task) -> None:
        return None


def build_executor(scenes, device=None):
    """构造一个不接真机的执行器，返回 (executor, device, navigator)。"""
    recognizer = MockRecognizer(scenes=scenes)
    navigator = FakeNavigator(recognizer)
    device = device or MockDevicePort()
    infra = InfraKit(
        device=device,
        pause=ThreadPauseController(),
        state=None,
        navigator=navigator,
    )
    return ProbeExecutor(infra), device, navigator


class LeaveInfrastructureTapTests(unittest.TestCase):
    """标准 5（行为部分）：离开基建时点击的是 `TapPosition` 常量坐标。"""

    def test_run_steps_taps_the_constant_position(self):
        # Arrange: 第一帧是"离开基建"弹窗，第二帧进入可执行场景
        executor, device, _ = build_executor(
            [Scene.LEAVE_INFRASTRUCTURE, Scene.INFRA_MAIN]
        )
        done = []

        # Act
        executor.run_steps(
            [
                Step(
                    "only",
                    lambda scene: scene == Scene.INFRA_MAIN,
                    lambda: done.append(True),
                    start=Scene.INFRA_MAIN,
                )
            ]
        )

        # Assert: 点击坐标严格等于常量值（不是"约等于某个手写数字"）
        self.assertEqual([TapPosition.LEAVE_INFRASTRUCTURE.value], device.taps)
        self.assertEqual([True], done)


class RunStepsControlFlowTests(unittest.TestCase):
    """`run_steps` 的异常控制流与队列语义。"""

    def test_step_retry_retries_same_step_then_completes(self):
        # Arrange: act 第一次 raise StepRetry，第二次成功
        executor, _, _ = build_executor([Scene.INFRA_MAIN])
        attempts = []
        done = []

        def act():
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise StepRetry
            done.append(True)

        # Act
        executor.run_steps(
            [
                Step(
                    "flaky",
                    lambda scene: scene == Scene.INFRA_MAIN,
                    act,
                    start=Scene.INFRA_MAIN,
                )
            ]
        )

        # Assert: 该步骤被调用了两次（原地重试），且最终完成一次
        self.assertEqual([1, 2], attempts)
        self.assertEqual(1, len(done))

    def test_step_restart_replays_queue_from_the_beginning(self):
        # Arrange: 首步第一次 raise StepRestart，之后成功；队列应从头重放
        executor, _, _ = build_executor([Scene.INFRA_MAIN])
        order = []
        first_calls = []

        def first_act():
            first_calls.append(len(first_calls) + 1)
            order.append("first")
            if len(first_calls) == 1:
                raise StepRestart

        def second_act():
            order.append("second")

        # Act
        executor.run_steps(
            [
                Step("first", lambda scene: True, first_act),
                Step("second", lambda scene: True, second_act),
            ]
        )

        # Assert: 重启后第一步重跑，第二步只在其后各跑一次
        self.assertEqual(["first", "first", "second"], order)

    def test_enter_returning_false_holds_the_queue(self):
        # Arrange: enter 前两次为 False，第三次为 True
        executor, _, _ = build_executor([Scene.INFRA_MAIN])
        seen = []
        done = []

        def enter(scene):
            seen.append(scene)
            return len(seen) >= 3

        # Act
        executor.run_steps([Step("gate", enter, lambda: done.append(True))])

        # Assert
        self.assertEqual(3, len(seen))
        self.assertEqual(1, len(done))

    def test_start_mismatch_navigates_before_acting(self):
        # Arrange: 当前场景不是期望起始场景，应先 navigate 而非执行
        executor, _, navigator = build_executor([Scene.INDEX, Scene.INFRA_MAIN])
        done = []

        # Act
        executor.run_steps(
            [
                Step(
                    "go",
                    lambda scene: scene == Scene.INFRA_MAIN,
                    lambda: done.append(True),
                    start=Scene.INFRA_MAIN,
                )
            ]
        )

        # Assert
        self.assertEqual([Scene.INFRA_MAIN], navigator.navigated)
        self.assertEqual([True], done)

    def test_extra_steps_returned_by_act_are_queued_front(self):
        # Arrange: act 返回一个追加步骤，应在剩余队列之前执行
        executor, _, _ = build_executor([Scene.INFRA_MAIN])
        order = []

        def main_act():
            order.append("main")
            return [Step("extra", lambda scene: True, lambda: order.append("extra"))]

        # Act
        executor.run_steps(
            [
                Step("main", lambda scene: True, main_act),
                Step("tail", lambda scene: True, lambda: order.append("tail")),
            ]
        )

        # Assert: 追加步骤插到队首，先于 tail
        self.assertEqual(["main", "extra", "tail"], order)

    def test_loading_scene_does_not_advance_the_queue(self):
        # Arrange: 连续两帧 LOADING，之后进入目标场景
        executor, _, _ = build_executor(
            [Scene.LOADING, Scene.LOADING, Scene.INFRA_MAIN]
        )
        done = []

        # Act
        executor.run_steps([Step("wait", lambda scene: True, lambda: done.append(True))])

        # Assert: LOADING 期间既不执行也不出队
        self.assertEqual(1, len(done))

    def test_unexpected_exception_propagates_to_caller(self):
        """标准 4 的语义守卫：删掉 `safe_execute` 后异常不再被该方法吞掉。

        异常隔离的职责已归属 `dispatch.TaskDispatch.execute`（自带 try/except），
        `run_steps` 对**非控制流**异常必须继续向上抛，不得静默吞掉。
        """
        # Arrange
        executor, _, _ = build_executor([Scene.INFRA_MAIN])

        def act():
            raise ValueError("boom")

        # Act / Assert
        with self.assertRaises(ValueError):
            executor.run_steps([Step("bad", lambda scene: True, act)])


if __name__ == "__main__":
    unittest.main()