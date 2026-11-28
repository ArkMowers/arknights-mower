"""共用活动首页、章节地图与商店的导航。"""

import re
from pathlib import Path
from time import monotonic

import cv2
import numpy as np

from arknights_mower.data import stage_data_full
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.device.io_budget import device_io_budget, io_timeout
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.path import resolve_config_path
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.stage_map_labels import read_map_stage_labels


def normalize_activity_text(text):
    return re.sub(r"\s+", "", str(text))


def chapter_kind(stage):
    parts = stage.upper().split("-")
    return "ex" if "EX" in parts else "s" if "S" in parts else "normal"


def activity_shop(activity):
    from time import time

    from arknights_mower.utils.maa_event_shop import activity_shops

    return next(
        (shop for shop in activity_shops(time()) if shop["activity"] == activity), {}
    )


def resolve_activity_stage(target):
    stages = list(stage_data_full)
    exact = next((s for s in stages if target in (s.get("id"), s.get("name"))), None)
    if exact is not None:
        return exact
    match = re.fullmatch(r"([A-Z0-9]+)-(EX|S)-\d+", target)
    if match is None:
        return None
    related = [
        s
        for s in stages
        if s.get("stageType") == "ACTIVITY"
        and (s.get("id") or "").startswith(match[1] + "-")
    ]
    activities = {s.get("zoneNameSecond") for s in related}
    if len(activities) != 1:
        return None
    activity = next(iter(activities))
    title = activity_shop(activity).get("chapters", {}).get(chapter_kind(target))
    if not title:
        return None
    return {
        "id": target,
        "name": target,
        "stageType": "ACTIVITY",
        "zoneNameSecond": activity,
        "subTitle": title,
        "endTs": related[0].get("endTs"),
    }


class ActivityNavigation:
    def __init__(self, solver, shop=None):
        self.solver = solver
        self.meta = solver.stage_meta or {}
        self.activity = self.meta.get("zoneNameSecond", "")
        self.shop = shop if shop is not None else activity_shop(self.activity)

    def entry_names(self):
        names = {
            self.activity,
            *self.meta.get("entryNames", []),
            *self.shop.get("entry_names", []),
            *self.shop.get("chapters", {}).values(),
        }
        names.update(
            s.get("subTitle")
            for s in stage_data_full
            if s.get("stageType") == "ACTIVITY"
            and s.get("zoneNameSecond") == self.activity
        )
        return {normalize_activity_text(name) for name in names if name}

    def matches_name(self, text):
        text = normalize_activity_text(text)
        return any(name in text for name in self.entry_names())

    def token_entry(self):
        tokens = set(self.shop.get("token_ids", [])) | {
            drop["id"]
            for stage in stage_data_full
            if stage.get("stageType") == "ACTIVITY"
            and stage.get("zoneNameSecond") == self.activity
            for drop in stage.get("drop") or []
            if drop.get("type") == "ACTIVITY_ITEM"
            and re.fullmatch(r"[A-Za-z0-9_]+", drop.get("id", ""))
        }
        tokens.update(self.shop.get("token_icon_ids", []))
        installation = Path(resolve_config_path(config.conf.maa_path))
        roots = [
            installation / "cache/resource/template/items",
            installation / "resource/template/items",
        ]
        x0, y0, x1, y1 = 0, 100, 800, 950
        frame = self.solver.recog.img[y0:y1, x0:x1]
        matches = []
        for token in sorted(tokens):
            path = next(
                (
                    root / f"{token}.png"
                    for root in roots
                    if (root / f"{token}.png").is_file()
                ),
                None,
            )
            if path is None:
                continue
            try:
                template = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 1)
            except (OSError, cv2.error):
                continue
            if template is None or min(template.shape[:2]) < 8:
                continue
            template = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)
            h, w = template.shape[:2]
            # 物品模板外围的圆框在终端中不存在，只匹配中央图案。
            template = template[h // 4 : h * 3 // 4, w // 4 : w * 3 // 4]
            if np.std(template) < 1:
                continue
            best = (0, None)
            for scale in np.arange(0.8, 2.01, 0.05):
                scaled = cv2.resize(template, None, fx=scale, fy=scale)
                if any(a > b for a, b in zip(scaled.shape[:2], frame.shape[:2])):
                    continue
                _, score, _, point = cv2.minMaxLoc(
                    cv2.matchTemplate(frame, scaled, cv2.TM_CCOEFF_NORMED)
                )
                if score > best[0]:
                    best = (
                        score,
                        (
                            point[0] + scaled.shape[1] // 2 + x0,
                            point[1] + scaled.shape[0] // 2 + y0,
                        ),
                    )
            score, point = best
            if score >= 0.9:
                matches.append(point)
        return matches[0] if len(matches) == 1 else None

    def enter_from_terminal(self, *, confirm_entry=None):
        solver = self.solver
        if solver.scene() != Scene.TERMINAL_MAIN:
            return False
        point = self.token_entry()
        label = self.activity
        if point is None:
            matches = [
                c
                for c in solver.collect_terminal_ocr_candidates()
                if c["score"] >= 0.8
                and 0 <= c["center"][0] < 700
                and 750 <= c["center"][1] < 950
                and self.matches_name(c["text"])
            ]
            if len(matches) != 1:
                return False
            point, label = matches[0]["center"], matches[0]["text"]
        if confirm_entry is not None:
            solver.tap(point, interval=0.2)
            return confirm_entry()
        return solver.tap_and_detect_page_move(point, label, record_step=False)

    def read(self):
        self.solver.recog.update()
        result, _ = rapidocr.engine(
            self.solver.recog.img, use_det=True, use_cls=False, use_rec=True
        )
        return [item for item in result or [] if float(item[2]) >= 0.8]

    def find_banner(self, scope=None):
        matches = []
        for item in self.read():
            if not self.matches_name(str(item[1])):
                continue
            box = item[0]
            point = tuple(int(sum(p[i] for p in box) / len(box)) for i in (0, 1))
            if scope and not all(
                scope[0][i] <= point[i] <= scope[1][i] for i in (0, 1)
            ):
                continue
            matches.append(point)
        return (matches[0], matches[0]) if len(matches) == 1 else None

    def confirm(self, predicate):
        for attempt in range(3):
            if any(predicate(str(item[1]).strip()) for item in self.read()):
                return True
            if attempt < 2:
                self.solver.sleep(0.2)
        return False

    def confirm_activity_home(self):
        deadline = monotonic() + 5

        def remaining():
            seconds = deadline - monotonic()
            if seconds <= 0:
                raise TimeoutError("活动首页确认超时")
            return seconds

        try:
            with device_io_budget(remaining):
                while True:
                    io_timeout(0)
                    texts = [normalize_activity_text(item[1]) for item in self.read()]
                    io_timeout(0)
                    if any("作战结束时间" in text for text in texts) and any(
                        self.matches_name(text) for text in texts
                    ):
                        return True
                    self.solver.sleep(min(0.2, remaining()))
        except (TimeoutError, DeviceRecoveryError):
            if monotonic() < deadline:
                raise
            return False

    def open_page(self, *, confirm_entry=None):
        solver = self.solver
        solver.scene_graph_navigation(Scene.TERMINAL_MAIN)
        if confirm_entry is None:
            entered = self.enter_from_terminal() and self.confirm(self.matches_name)
        else:
            entered = self.enter_from_terminal(confirm_entry=confirm_entry)
        if entered:
            return True
        solver.scene_graph_navigation(Scene.TERMINAL_MAIN)
        solver.tap((490, 1014), interval=0.2)
        solver.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
        if not solver.open_activity_overview_until_ready(max_taps=8):
            return False
        if confirm_entry is not None:
            return solver.find_stage_image_and_enter(
                self.activity, max_swipes=10, confirm_entry=confirm_entry
            )
        return solver.find_stage_image_and_enter(
            self.activity, max_swipes=10
        ) and self.confirm(self.matches_name)

    def open_chapter(self, title, target):
        matches = [
            item
            for item in self.read()
            if normalize_activity_text(title) in normalize_activity_text(item[1])
        ]
        if len(matches) != 1:
            return False
        box = matches[0][0]
        point = tuple(int(sum(p[i] for p in box) / len(box)) for i in (0, 1))
        if not self.solver.tap_and_detect_page_move(point, title, record_step=False):
            return False
        stem = self.solver.stage_pattern_stem(target)

        def in_chapter(text):
            return (
                self.solver.is_stage_code(text)
                and self.solver.stage_pattern_stem(text) == stem
            )

        if any(
            in_chapter(code) for code, _ in read_map_stage_labels(self.solver.recog.img)
        ):
            return True
        return self.confirm(in_chapter)

    def open_stage(self, target):
        title = self.meta.get("subTitle")
        if not title or not self.open_page() or not self.open_chapter(title, target):
            return False
        return self.solver.find_target_stage_after_entry(target, max_swipes=6)

    def confirm_shop(self):
        for attempt in range(3):
            texts = [re.sub(r"\s+", "", str(item[1])) for item in self.read()]
            deadline = any(
                any(word in text for word in ("关闭时间", "兑换截止", "兑换结束时间"))
                for text in texts
            )
            goods = any(
                "售罄" in text
                or "已拥有" in text
                or re.fullmatch(r"剩余\d+(?:/\d+)?(?:个|件|张|份)?", text)
                for text in texts
            )
            if deadline and goods:
                return True
            if attempt < 2:
                self.solver.sleep(0.2)
        return False

    def open_shop(self, point):
        if not self.open_page(confirm_entry=self.confirm_activity_home):
            return False
        self.solver.tap(point)
        self.solver.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
        return self.confirm_shop()
