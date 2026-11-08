"""Open a selected activity shop before handing its purchase dialog to MAA."""

from arknights_mower.solvers.activity_navigation import ActivityNavigation
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.utils import rapidocr


class EventShopNavigation(NavigationSolver):
    def run(self, shop):
        if rapidocr.engine is None:
            rapidocr.initialize_ocr()
        self.name = shop["activity"]
        self.stage_meta = {
            "zoneNameSecond": self.name,
            "entryNames": shop.get("entry_names", []),
        }
        self.stageType = "ACTIVITY"
        self.nav_steps = []
        self._suppress_nav_recording = True
        return ActivityNavigation(self, shop).open_shop()
