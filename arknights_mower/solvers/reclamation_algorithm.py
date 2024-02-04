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
            if pos := self.find("ra/start_action"):
                self.tap(pos, interval=3)
            else:
                self.tap_element("ra/continue_button", interval=3)
        elif scene == Scene.RA_GUIDE_ENTRANCE:
            self.tap_element("ra/guide_entrance")
        elif scene == Scene.RA_BATTLE_ENTRANCE:
            self.tap_element("ra/start_action")
        elif scene == Scene.RA_GUIDE_DIALOG:
            self.tap((1631, 675))
        elif scene == Scene.RA_BATTLE:
            self.tap_element("ra/battle_exit")
        elif scene == Scene.RA_BATTLE_EXIT_CONFIRM:
            self.tap_element("ra/battle_exit_confirm")
        elif scene == Scene.RA_GUIDE_NOTE_ENTRANCE:
            self.tap_element("ra/guide_note_entrance")
        elif scene == Scene.RA_GUIDE_NOTE_DIALOG:
            self.tap((1743, 620))
        elif scene == Scene.RA_MAP:
            self.tap_element("ra/map_back")
        elif scene == Scene.RA_MAP_CENTRAL_BASE:
            if pos := self.find("ra/battle_wood_entrance"):
                self.tap(pos)
        else:
            self.recog.update()
