"""Read the swap slot and preserve follow-up work on unreadable scenes."""

from arknights_mower.utils.mastery_support import SupportPlanError

from .mastery_support_state import stop_support_swap
from .mastery_support_swap import _matches_training, perform_swap


def run_planned_swap(solver, plan, panel):
    from arknights_mower.solvers.mastery_reader import _read_slots_checked
    from arknights_mower.utils.csleep import MowerExit

    try:
        support = None
        if _matches_training(plan, panel):
            support, _, _, reliable = _read_slots_checked(solver)
            if not reliable:
                raise SupportPlanError("协助位读取失败，停止换人并安排收取检查")
        perform_swap(solver, plan, panel, support)
    except MowerExit:
        raise
    except Exception as exc:
        stop_support_swap(solver, plan, getattr(panel, "mastery_tier", None), str(exc))
