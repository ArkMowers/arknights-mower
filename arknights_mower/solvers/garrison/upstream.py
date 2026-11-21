"""Load the pinned GarrisonFarm gameplay functions into an instance-local session."""

import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.request import urlopen

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils.device.io_budget import touch_release_budget
from arknights_mower.utils.log import logger, save_screenshot_frame
from arknights_mower.utils.path import get_path

from .model import GarrisonError

REVISION = "fd373c9b1ab1e8fbb52ad78b8da4c461ab325abb"
BUNDLED_DIR = __rootdir__ / "data" / "garrisonfarm" / REVISION


def read_resource(name, remaining):
    if name not in ("garrison_farm.py", "tiles.json"):
        raise ValueError("未知的 GarrisonFarm 文件")
    bundled = BUNDLED_DIR / name
    if bundled.is_file():
        return bundled.read_bytes()
    directory = get_path(f"@app/downloads/garrisonfarm/{REVISION}", space="")
    path = directory / name
    if path.is_file():
        return path.read_bytes()
    directory.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/ALEXsun0/GarrisonFarm/{REVISION}/{name}"
    with urlopen(url, timeout=min(10, remaining())) as response:
        buffer = bytearray()
        while len(buffer) <= 512 * 1024:
            remaining()
            chunk = response.read1(64 * 1024)
            if not chunk:
                break
            buffer.extend(chunk)
        data = bytes(buffer)
    remaining()
    if len(data) > 512 * 1024:
        raise GarrisonError(f"GarrisonFarm 文件超过下载大小上限：{name}")
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return data


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
        script = read_resource("garrison_farm.py", owner.remaining).decode("utf-8-sig")
        layout = json.loads(read_resource("tiles.json", owner.remaining))
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
