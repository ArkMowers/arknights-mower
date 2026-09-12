"""Mastery assistant swap regressions."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery_support_swap as swap
from arknights_mower.tests.mastery_support_fixtures import (
    swap_case as swap_case,
)
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support as support


@pytest.mark.parametrize(
    "names,expected_alerts", [(("艾丽妮", "逻各斯"), 1), (("艾丽妮",), 1), ((), 0)]
)
def test_swap_insufficient_training_retains_current_and_alerts_only_if_reducers_exist(
    names, expected_alerts
):
    plan, panel, solver, options = swap_case(names)
    panel.countdown = datetime.now() + timedelta(hours=1)
    with (
        patch.object(swap, "candidates", return_value=(options, 0)),
        patch.object(swap, "schedule_context", return_value=({}, 0)),
        patch.object(swap, "confirm_training_panel", return_value=panel),
        patch.object(swap, "notify_support_failure") as warn,
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("快教官", "学员", None, True),
        ),
        patch("arknights_mower.solvers.mastery._schedule_collect_after_swap"),
        patch.object(db, "update_plan_status") as update,
    ):
        swap.perform_swap(solver, plan, panel, "快教官")
    assert warn.call_count == expected_alerts
    solver.choose_train.assert_not_called()
    assert update.call_args.kwargs["swap_frozen"] == 1


def test_delayed_alternate_is_persisted_and_queue_preserves_dispatch_task():
    plan, panel, solver, options = swap_case(names=("逻各斯",))
    with (
        patch.object(swap, "candidates", return_value=(options, 0)),
        patch.object(swap, "schedule_context", return_value=({}, 0)),
        patch.object(swap, "confirm_training_panel", return_value=panel),
        patch.object(swap, "save_runtime") as persist,
        patch.object(swap, "enqueue_support_swap") as enqueue,
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("快教官", "学员", None, True),
        ),
    ):
        swap.perform_swap(solver, plan, panel, "快教官")
    assert persist.call_args.args[1]["swap_target"] == "逻各斯"
    assert enqueue.call_args.args[2] > datetime.now()
    solver.choose_train.assert_not_called()
    from arknights_mower.utils.scheduler_task import TaskTypes

    task = SimpleNamespace(
        type=TaskTypes.SWAP_SUPPORT, plan_key="1", time=datetime.now()
    )
    solver.task, solver.tasks = task, [task]
    swap.enqueue_support_swap(solver, plan, datetime.now(), "逻各斯")
    assert len(solver.tasks) == 2 and solver.tasks[0] is task


def test_placing_support_allows_scheduled_trainee_but_not_scheduled_assistant():
    solver = MagicMock()
    plan = {"char_name": "学员"}
    panel = SimpleNamespace(countdown=datetime.now() + timedelta(hours=6))
    with (
        patch.object(
            swap, "schedule_context", return_value=({"学员": {"room_1_1"}}, 0)
        ),
        patch.object(swap, "confirm_training_panel", return_value=panel),
        patch.object(swap, "record_work"),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("教官", "学员", None, True),
        ),
    ):
        assert swap.place_support(solver, plan, 1, "教官") is panel
    solver.choose_train.assert_called_once_with(["教官", "Current"])
    solver.choose_train.reset_mock()
    with patch.object(
        swap,
        "schedule_context",
        return_value=({"学员": {"room_1_1"}, "教官": {"central"}}, 0),
    ):
        with pytest.raises(support.SupportPlanError, match="不能作为专精协助者"):
            swap.place_support(solver, plan, 1, "教官")
    solver.choose_train.assert_not_called()
