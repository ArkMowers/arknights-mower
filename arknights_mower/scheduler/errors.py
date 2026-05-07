from __future__ import annotations


class SchedulerError(Exception):
    pass


class TaskNotFoundError(SchedulerError):
    pass


class DeviceError(SchedulerError):
    pass


class NavigationError(SchedulerError):
    pass


class ConfigError(SchedulerError):
    pass


class AgentSelectionError(SchedulerError):
    pass
