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


def strategy_grid_shift(before, after):
    """Measure signed grid travel using a textured strip still visible in both frames."""
    top, bottom = 250, 1050
    old, new = (
        cv2.cvtColor(img[top:bottom, 600:1400:4], cv2.COLOR_BGR2GRAY)
        for img in (before, after)
    )
    if np.array_equal(old, new):
        return 0
    # A two-row swipe can carry the middle strip entirely out of the viewport.
    shifts = []
    for y in (80, 300, 550):
        strip = old[y : y + 128]
        if strip.std() < 10:
            continue
        scores = cv2.matchTemplate(new, strip, cv2.TM_CCOEFF_NORMED).ravel()
        best = int(scores.argmax())
        score = scores[best]
        if score < 0.85:
            continue
        scores[max(0, best - 8) : best + 9] = -1
        if scores.max() < score - 0.05:
            shifts.append(y - best)
    if shifts and max(shifts) - min(shifts) <= 4:
        return round(sum(shifts) / len(shifts))
    return None


def framed_strategy_cells(image, columns):
    """Map tap points to the visible vertical extent of each framed card."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cells = {}
    for x in columns:
        sides = []
        for direction in (-1, 1):
            edge = x + direction * 94
            outer = edge + direction * 9
            rim = gray[:, edge - 3 : edge + 4].max(axis=1)
            background = gray[:, outer - 3 : outer + 4].mean(axis=1)
            sides.append(rim - background > 17)
        vertical = (sides[0] & sides[1]).astype(np.uint8)
        vertical = cv2.morphologyEx(
            vertical[:, None], cv2.MORPH_CLOSE, np.ones((7, 1), np.uint8)
        ).ravel()
        ends = np.flatnonzero(np.diff(np.r_[0, vertical, 0]))
        for top, bottom in zip(ends[::2], ends[1::2]):
            if 125 <= bottom - top <= 205:
                cells[x, int((top + bottom) // 2)] = (int(top), int(bottom - 1))
    return cells


def strategy_portrait_present(image, x, y):
    """Apply the portrait row detector's contrast and run length inside one card."""
    portrait = image[y - 80 : y + 80, x - 60 : x + 60]
    gray = cv2.cvtColor(portrait, cv2.COLOR_BGR2GRAY)
    textured = gray.std(axis=1) > 18
    ends = np.flatnonzero(np.diff(np.r_[False, textured, False]))
    return bool(np.any(ends[1::2] - ends[::2] >= 60))


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
        farm.framed_cells = lambda page: framed_strategy_cells(page, farm.GRID_X)
        farm.has_portrait = strategy_portrait_present
        farm.grid_shift = strategy_grid_shift
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
