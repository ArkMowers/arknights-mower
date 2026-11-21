"""Load the pinned GarrisonFarm gameplay functions into an instance-local session."""

import json
import re
import time
import unicodedata
from types import ModuleType, SimpleNamespace

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils.device.io_budget import touch_release_budget
from arknights_mower.utils.log import logger, save_screenshot_frame

from .model import GarrisonError

REVISION = "fd373c9b1ab1e8fbb52ad78b8da4c461ab325abb"
BUNDLED_DIR = __rootdir__ / "data" / "garrisonfarm" / REVISION


def panel_open(items):
    return any("初始生命值" in text.replace(" ", "") for _, _, text in items)


def strategy_panel(items):
    """Read the clear count only from the completion banner of an opened panel."""
    texts = [
        (y, unicodedata.normalize("NFKC", t).replace(" ", "")) for _, y, t in items
    ]
    if not panel_open(items):
        return None
    banner = "".join(t for y, t in texts if y < 350)
    if "通过" not in banner:
        return 0
    match = re.search(r"通过(?:模拟)?([0-9]+)次", banner)
    return int(match[1]) if match else None


class FarmSession:
    def __init__(self, owner):
        self.owner = owner
        self.held = None
        try:
            script = (BUNDLED_DIR / "garrison_farm.py").read_text(encoding="utf-8-sig")
            layout = json.loads(
                (BUNDLED_DIR / "tiles.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise GarrisonError(
                f"缺少内置卫戍文件，请重新安装 Mower：{exc.filename}"
            ) from exc
        # The pinned standalone script has no importable gameplay entry point. Its
        # OCR and gameplay section precedes main() and has no host startup steps.
        start = script.index("def ocr(img, box=None):")
        end = script.index("def main():", start)
        farm = ModuleType("garrison_farm")
        farm.cv2, farm.np = cv2, np
        exec(compile(script[start:end], "garrison_farm.py", "exec"), vars(farm))
        farm.shot = self.shot
        farm.ocr_engine = owner.vision.engine
        farm.tap = self.tap
        farm.swipe = self.swipe
        farm.touch = self.touch
        farm.drag_path = self.drag
        farm.time = SimpleNamespace(sleep=owner.sleep, time=time.monotonic)
        farm.log = lambda *parts: logger.info(" ".join(map(str, parts)))
        farm.save = lambda image, tag: save_screenshot_frame(
            cv2.cvtColor(image, cv2.COLOR_BGR2RGB), "garrison"
        )
        farm.LAYOUT = layout
        farm.TARGET = owner.target_wins
        farm.set_profile("low")
        self.game = farm

    def shot(self):
        self.owner.remaining()
        self.owner.recog.update()
        image = self.owner.recog.img
        if image.shape != (1080, 1920, 3):
            raise GarrisonError("卫戍协议需要 1920×1080 标准画面")
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    def tap(self, x, y, wait=0.6):
        self.owner.remaining()
        self.owner.device.tap((int(x), int(y)))
        self.owner.sleep(wait)

    def swipe(self, x1, y1, x2, y2, ms=500, wait=0.8):
        self.owner.remaining()
        self.owner.device.swipe(
            (int(x1), int(y1)), (int(x2), int(y2)), duration=int(ms)
        )
        self.owner.sleep(wait)

    def touch(self, kind, x, y):
        self.owner.remaining()
        point = (int(x), int(y))
        if kind == "DOWN":
            self.held = point
        self.owner.device.motion_events(kind, [point])
        if kind == "UP":
            self.held = None

    def drag(self, x1, y1, x2, y2, steps=12):
        self.owner.remaining()
        points = [
            (int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
            for i in range(1, steps + 1)
        ]
        self.held = points[-1]
        self.owner.device.motion_events("MOVE", points)

    def release(self):
        if self.held is not None:
            with touch_release_budget():
                self.owner.device.motion_events("UP", [self.held])
            self.held = None
