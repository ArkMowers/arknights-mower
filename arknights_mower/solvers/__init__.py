from mower.solvers.shop import CreditShop
from mower.utils.log import logger

from .daily import DailySolver
from .get_clue_count import GetClueCountSolver
from .give_away import GiveAwaySolver
from .party_time import PartyTimeSolver
from .place import PlaceSolver
from .receive import ReceiveSolver


class ClueManager:
    solver_name = "线索交流"

    def run(self):
        logger.info("基建：线索")

        clue_count = GetClueCountSolver().run()
        if clue_count <= 9:
            DailySolver().run()

        ReceiveSolver().run()

        PlaceSolver().run()

        GiveAwaySolver().run(clue_count)

        DailySolver().run()

        self.party_time = PartyTimeSolver().run()

        CreditShop().run()

        return True
