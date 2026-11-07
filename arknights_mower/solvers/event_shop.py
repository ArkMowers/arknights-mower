"""Open a selected activity shop before handing its purchase dialog to MAA."""

from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.utils import rapidocr
from arknights_mower.utils.scene import Scene


class EventShopNavigation(NavigationSolver):
    def find_stage_banner(self, zone_name, scope=None):
        found = super().find_stage_banner(zone_name, scope=scope)
        if found:
            return found
        result, _ = rapidocr.engine(
            self.recog.img, use_det=True, use_cls=False, use_rec=True
        )
        matches = [
            item
            for item in result or []
            if str(item[1]).strip() == zone_name and float(item[2]) >= 0.8
        ]
        if len(matches) != 1:
            return None
        box = matches[0][0]
        center = (
            int(sum(point[0] for point in box) / len(box)),
            int(sum(point[1] for point in box) / len(box)),
        )
        return center, center

    def run(self, shop):
        if rapidocr.engine is None:
            rapidocr.initialize_ocr()
        self.name = shop["activity"]
        self.stage_meta = {"zoneNameSecond": self.name}
        self.stageType = "ACTIVITY"
        self.nav_steps = []
        self._suppress_nav_recording = True
        self.scene_graph_navigation(Scene.TERMINAL_MAIN)
        if not self.enter_activity_from_terminal():
            self.scene_graph_navigation(Scene.TERMINAL_MAIN)
            self.tap((490, 1014), interval=0.2)
            self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
            if not self.open_activity_overview_until_ready(max_taps=8):
                return False
            if not self.find_stage_image_and_enter(self.name, max_swipes=10):
                return False
        self.tap((shop["x"], shop["y"]))
        self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2)
        for attempt in range(3):
            self.recog.update()
            result, _ = rapidocr.engine(
                self.recog.img, use_det=True, use_cls=False, use_rec=True
            )
            if any(
                str(item[1]).strip() == shop["confirm_text"] and float(item[2]) >= 0.8
                for item in result or []
            ):
                return True
            if attempt < 2:
                self.sleep(0.2)
        return False
