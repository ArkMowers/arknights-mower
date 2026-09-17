"""换班服务的构造与设备/识别原语。

本文件是拆分后的**基类**：只放"与具体换班语义无关"的东西 ——
依赖注入、场景白名单、步骤队列循环、点击坐标换算、识别器转发。

拆分前这些都在 619 行的 `agent_swap_service.py` 里；拆分的唯一目的是满足
AGENTS.md「一个 class 一个文件、文件 ≤300 行」，**行为必须逐字不变**。
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Callable, Optional

import numpy as np

from arknights_mower.scheduler.constants import (
    AGENT_SELECT_POSITIONS,
    SCREEN_H,
    SCREEN_W,
)
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.scheduler.steps import Step, StepRestart, StepRetry
from arknights_mower.utils.log import logger

if TYPE_CHECKING:
    from arknights_mower.scheduler.state import SchedulerState

_POSITIONS = AGENT_SELECT_POSITIONS


class AgentSwapBase:
    """换班服务的公共依赖与设备原语。

    `state` 为**可选**注入：`ShiftExecutor` 必须传（裁定 14），传了才能拿到
    `operators[...].current_room` 与 `config.free_blacklist` 做真正的空闲判定；
    离线回归网按旧签名构造时留空，此时空闲判定退化为拆分前的行为。
    """

    def __init__(
        self,
        device: DevicePort,
        recognizer: object,
        get_scene: Callable[[], int],
        pause: PauseController,
        wait_scene_stable: Optional[Callable] = None,
        state: Optional["SchedulerState"] = None,
    ) -> None:
        self._device = device
        self._recog = recognizer
        self._get_scene = get_scene
        self._pause = pause
        self._wait_scene_stable = wait_scene_stable or (lambda **kwargs: None)
        self._state = state

        # 跨步骤的会话状态。原先它们只在 run() 里赋值，方法因此**不可单独调用**；
        # 在 __init__ 里给出同样的初值，方法即可独立调用（含单测），
        # 且不改变 run() 的既有语义（run 仍会逐字段重新赋值）。
        self._room = ""
        self._is_dorm = False
        self._is_production = False
        self._agents: list[str] = []
        self._pending: list[str] = []
        self._free_count = 0
        self._selected: list[str] = []
        self._to_uncheck: list[int] = []
        self._last_filter = "ALL"
        self._last_names: Optional[list[str]] = None
        self._page_count = 0
        self._cache: list = []
        self._found_target = False

        from arknights_mower.data import agent_list, agent_profession
        from arknights_mower.utils.character_recognize import operator_list as _op_list

        self._agent_profession = agent_profession
        self._agent_list = set(agent_list)
        self._operator_list_fn = _op_list

        from arknights_mower.data import agent_arrange_order

        self._profession_filter_names = set(agent_arrange_order.get("职介选择开关", []))

    # ─── 步骤队列 ───

    def _scene_check(self, scene: int) -> bool:
        return scene in (Scene.RIIC_OPERATOR_SELECT, Scene.INFRA_ARRANGE_ORDER)

    def _run_steps(self, steps: list[Step]) -> bool:
        """换班专用的步骤队列循环。

        ⚠️ 与 `AbstractExecutor.run_steps` **不是同一套实现**：这里**没有**
        `guard()`、没有超时兜底。因此本队列内**禁止**抛 `StepRetry`/`StepRestart`
        来表示"失败"（见 `AgentSwapError` 的文档）；普通异常会经 `except Exception`
        返回 `False`，交由外层 `AbstractExecutor` 的超时与 `state.error` 上报。
        """
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
                    return False
        return True

    # ─── 设备原语 ───

    def _tap_slot(self, idx: int) -> None:
        self._device.tap(_POSITIONS[idx][0], _POSITIONS[idx][1])

    def _tap_center(self, box) -> None:
        if isinstance(box, (list, tuple)) and len(box) == 2:
            if isinstance(box[0], (list, tuple)):
                x1, y1 = box[0]
                x2, y2 = box[1]
                cx = (x1 + x2) / 2 / SCREEN_W
                cy = (y1 + y2) / 2 / SCREEN_H
                self._device.tap(cx, cy)
            else:
                self._device.tap(box[0] / SCREEN_W, box[1] / SCREEN_H)

    def _back(self) -> None:
        self._device.back()

    def _screencap(self) -> np.ndarray:
        return self._device.screencap()

    def _find(self, name: str):
        if self._recog is None:
            return None
        return self._recog.find(name)
