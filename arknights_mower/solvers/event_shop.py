"""Open a selected activity shop before handing its purchase dialog to MAA."""

from arknights_mower.solvers.activity_navigation import ActivityNavigation
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.utils import rapidocr
from arknights_mower.utils.log import logger
from arknights_mower.utils.maa_event_shop import shop_identity

SHOP_ENTRANCE_POINTS = {
    ("act55side", 1793487600): (1461, 255),
    ("act46sre", 1795291200): (229, 826),
}


class EventShopNavigation(NavigationSolver):
    def run(self, shop):
        point = SHOP_ENTRANCE_POINTS.get(shop_identity(shop))
        if point is None:
            logger.info(
                "活动「%s」缺少商店入口坐标",
                shop["activity"],
                extra={"log_group": "maa-integration"},
            )
            return False
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
        return ActivityNavigation(self, shop).open_shop(point)
