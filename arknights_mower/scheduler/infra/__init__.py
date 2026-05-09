from __future__ import annotations

from dataclasses import dataclass, field

from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController


@dataclass
class InfraKit:
    device: DevicePort
    state: object = None
    navigator: object = None
    agent_selector: object = None
    pause: PauseController = field(default_factory=ThreadPauseController)
