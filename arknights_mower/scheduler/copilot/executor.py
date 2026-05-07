import logging

from arknights_mower.scheduler.copilot.battle_state import BattleState
from arknights_mower.scheduler.copilot.combat_plan import Action, ActionType, StageInfo
from arknights_mower.scheduler.copilot.deployer import Deployer
from arknights_mower.scheduler.copilot.skill_mgr import SkillManager
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.infra.pause_controller import PauseController

logger = logging.getLogger(__name__)


class CopilotExecutor:
    def __init__(
        self,
        device: DevicePort,
        pause_controller: PauseController,
    ) -> None:
        self._device = device
        self._pause = pause_controller
        self._deployer = Deployer(device, pause_controller)
        self._skill_mgr = SkillManager()

    def execute(self, plan: StageInfo) -> None:
        self._pause.wait_if_paused()
        state = BattleState()
        for action in plan.actions:
            self._execute_action(action, state)

    def _execute_action(self, action: Action, state: BattleState) -> None:
        self._pause.wait_if_paused()

        match action.type:
            case ActionType.DEPLOY:
                logger.info(f"deploy {action.name} at {action.location}")
                self._deployer.deploy(
                    action.location[0],
                    action.location[1],
                    action.direction.value,
                )

            case ActionType.RETREAT:
                logger.info(f"retreat {action.location}")
                self._deployer.retreat(
                    action.location[0],
                    action.location[1],
                )

            case ActionType.SKILL:
                logger.info(f"skill {action.skill}")
                self._deployer.activate_skill(action.skill)

            case ActionType.SKILL_USAGE:
                logger.info(f"skill_usage {action.skill_usage}")

            case ActionType.SPEED_UP:
                logger.info("speed up")

            case ActionType.SKILL_DAEMON:
                logger.info("skill daemon")

            case ActionType.BULGE:
                logger.info("bulge")

            case ActionType.MOVE_CAMERA:
                logger.info("move camera")

            case ActionType.PRINT:
                logger.info(f"print: {action.doc}")
