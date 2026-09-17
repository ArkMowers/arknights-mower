"""假识别器：按预设 `scene` 序列回放，绝不读取真实截图。

与 `utils.recognize.Recognizer` 的**行为契约**（调度器实际用到的部分）：

| 成员 | 语义 |
|---|---|
| `update()` | 推进到序列中的下一个 scene（序列耗尽后保持最后一个） |
| `get_scene()` | 返回当前 scene，**不推进**；受 `set_scene_whitelist` 约束 |
| `img` / `gray` | 当前帧，测试可直接赋值 |
| `find(name, **kw)` | 查 `finds` 表；未命中返回 `None`，并记录查询 |
| `check_announcement()` | 查 `finds` 表，默认 `None` |
| `set_scene_whitelist(scenes)` | 记录白名单；当前 scene 不在白名单内则 `get_scene()` 返回 `UNKNOWN` |

注意：本类**不是** `Recognizer` 的子类。真正的 `Recognizer` 会立刻连设备、
`__init__` 里就要 `screencap()`，把它拖进单测就违反了"离线"这条硬要求。
但 `MockRecognizer` 的**成员名**与真实实现逐一对齐，所以实现里的
`self._recog.img` / `self._recog.update()` 之类调用一旦改名，用例会立刻报
`AttributeError` —— 这是本夹具的防漂移手段（`DevicePort` 那边靠继承达成同一目的）。

用法
----
    from tests.harness.mock_recognizer import MockRecognizer
    from arknights_mower.scheduler.scene import Scene

    recog = MockRecognizer(scenes=[Scene.INFRA_MAIN, Scene.INFRA_DETAILS])
    recog.update()
    assert recog.get_scene() == Scene.INFRA_MAIN
"""

from __future__ import annotations

import numpy as np

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W
from arknights_mower.scheduler.scene import Scene


class MockRecognizer:
    """按序列回放 scene 的假识别器。"""

    def __init__(
        self,
        scenes=None,
        finds=None,
        frames=None,
        repeat_last: bool = True,
    ) -> None:
        """
        Args:
            scenes: scene 序列（`int` 或 `Scene`）。`update()` 每次取下一个。
            finds: `{资源名: 返回值}`，供 `find()` / `check_announcement()` 查表。
            frames: 帧序列或单帧 `np.ndarray`，供 `img` 使用。
            repeat_last: 序列耗尽后是否停在最后一个 scene（默认 True；
                置 False 则耗尽后回到 `Scene.UNKNOWN`）。
        """
        self.scene_sequence = list(scenes or [])
        self.repeat_last = repeat_last
        self.finds = dict(finds or {})
        self.scene_whitelist = None
        # 记录：每次 find 查询了什么，便于断言"探测了哪些资源"
        self.find_calls: list[str] = []
        self.update_count = 0
        self._cursor = -1
        self._frames = self._normalize_frames(frames)
        self._frame_cursor = 0
        self._img = None
        self._gray = None

    # ---------------------------------------------------------------- 帧

    @staticmethod
    def _normalize_frames(frames):
        if frames is None:
            return []
        if isinstance(frames, np.ndarray):
            return [frames]
        return list(frames)

    @property
    def img(self) -> np.ndarray:
        if self._img is None:
            if self._frames:
                idx = min(self._frame_cursor, len(self._frames) - 1)
                self._img = self._frames[idx]
            else:
                # 全黑 1080p：识别层拿它当"什么都没找到"，不会崩
                self._img = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
            self._gray = None
        return self._img

    @img.setter
    def img(self, value: np.ndarray) -> None:
        self._img = value
        self._gray = None

    @property
    def gray(self) -> np.ndarray:
        if self._gray is None:
            gray = (
                0.299 * self.img[:, :, 0]
                + 0.587 * self.img[:, :, 1]
                + 0.114 * self.img[:, :, 2]
            )
            self._gray = gray.astype(np.uint8)
        return self._gray

    def advance_frame(self) -> None:
        """切到下一帧（用例需要"画面变了"时显式调用）。"""
        if self._frames:
            self._frame_cursor = min(self._frame_cursor + 1, len(self._frames) - 1)
            self._img = None
            self._gray = None

    # ------------------------------------------------------------ 识别面

    @property
    def scene(self) -> int:
        return self.get_scene()

    def update(self) -> None:
        """推进到下一个预设 scene。"""
        self.update_count += 1
        if self._cursor + 1 < len(self.scene_sequence):
            self._cursor += 1
        elif not self.repeat_last:
            self._cursor = -1
        self.advance_frame()

    def get_scene(self) -> int:
        if self._cursor < 0:
            current = Scene.UNKNOWN
        else:
            current = self.scene_sequence[self._cursor]
        if self.scene_whitelist is not None and current not in self.scene_whitelist:
            return Scene.UNKNOWN
        return current

    def set_scene_whitelist(self, scenes) -> None:
        self.scene_whitelist = None if scenes is None else list(scenes)

    def check_announcement(self):
        return self.finds.get("check_announcement")

    def find(
        self,
        res,
        draw=False,
        scope=None,
        thres=None,
        judge=True,
        strict=False,
        threshold=0.0,
    ):
        name = str(res)
        self.find_calls.append(name)
        result = self.finds.get(name)
        if strict and result is None:
            raise ValueError(f"MockRecognizer: 未预设资源 {name!r}")
        return result

    # ------------------------------------------------------------ 测试辅助

    def feed(self, *scenes) -> None:
        """追加 scene 到序列尾（序列已耗尽时尤其有用）。"""
        self.scene_sequence.extend(scenes)

    def set_finds(self, **mapping) -> None:
        """设置 `find()` 的返回值，如 `recog.set_finds(infra_no_operator=None)`。"""
        self.finds.update(mapping)

    def reset(self) -> None:
        self._cursor = -1
        self._frame_cursor = 0
        self._img = None
        self._gray = None
        self.update_count = 0
        self.find_calls.clear()
        self.scene_whitelist = None
