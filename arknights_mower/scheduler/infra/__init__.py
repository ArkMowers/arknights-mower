from __future__ import annotations

from dataclasses import dataclass

from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.infra.pause_controller import PauseController


@dataclass
class InfraKit:
    device: DevicePort
    pause: PauseController
    state: object = None
    navigator: object = None
