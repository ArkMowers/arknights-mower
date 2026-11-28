"""Read the swap slot and preserve follow-up work on unreadable scenes."""

from arknights_mower.utils.mastery_support_types import TrainingObservationError

from .mastery_support_swap import _matches_training, perform_swap


def run_planned_swap(solver, plan, panel):
    from arknights_mower.solvers.mastery_reader import _read_slots_checked
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.recovery import DeviceRecoveryError

    try:
        support = None
        if _matches_training(plan, panel):
            support, trainee, _, reliable = _read_slots_checked(solver)
            if not reliable or trainee != plan.get("char_name"):
                raise TrainingObservationError("训练室驻员读取失败，保留换人任务")
        perform_swap(solver, plan, panel, support)
    except (MowerExit, DeviceRecoveryError, TrainingObservationError):
        raise
    except Exception as exc:
        raise TrainingObservationError("训练室换人尚未确认，保留换人任务") from exc
