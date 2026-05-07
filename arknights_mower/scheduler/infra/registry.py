from arknights_mower.scheduler.device_port import DevicePort


class InfraRegistry:
    def __init__(self, device: DevicePort) -> None:
        self._device = device
