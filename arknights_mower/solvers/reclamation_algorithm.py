from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


class ReclamationAlgorithm(BaseSolver):
    def run(self) -> None:
        logger.info("Start: 生息演算")
        super().run()

    def transition(self) -> bool:
        if (scene := self.ra_scene()) == Scene.INDEX:
            self.tap_themed_element("index_terminal")
        elif scene == Scene.TERMINAL_MAIN:
            self.tap_element("terminal_button_longterm")
        elif scene == Scene.TERMINAL_LONGTERM:
            self.tap_element("terminal_longterm_reclamation_algorithm")
        elif scene == Scene.RA_MAIN:
            self.tap_element("ra_start_button")
        elif scene == Scene.RA_GUIDE_1:
            self.tap_element("ra_guide_1")
        else:
            self.sleep(3)
