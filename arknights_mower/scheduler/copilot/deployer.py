import logging

from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.infra.pause_controller import PauseController

logger = logging.getLogger(__name__)


class Deployer:
    def __init__(
        self, device: DevicePort, pause_controller: PauseController
    ) -> None:
        self._device = device
        self._pause = pause_controller

    def deploy(self, row: int, col: int, direction: str = "Right") -> None:
        raise NotImplementedError(
            "Step 6: 部署操作 (待从战斗截图识别实现)"
        )

    def retreat(self, row: int, col: int) -> None:
        raise NotImplementedError(
            "Step 6: 撤退操作 (待从战斗截图识别实现)"
        )

    def activate_skill(self, skill: int) -> None:
        raise NotImplementedError(
            "Step 6: 技能释放 (待从战斗截图识别实现)"
        )
