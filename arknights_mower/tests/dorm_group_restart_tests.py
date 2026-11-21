"""Cold observation restores fixed dormitory positions across every binding."""

from copy import deepcopy
from datetime import datetime

import pytest

from arknights_mower.tests import dorm_group_tests
from arknights_mower.tests.multi_group_shift_tests import A, B
from arknights_mower.tests.multi_group_shift_tests import dorm_solver as dorm_solver
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

DORM = "dormitory_1"


@pytest.fixture
def single_solver(monkeypatch):
    return dorm_group_tests.solver.__wrapped__(monkeypatch)


def observe_after_cache_clear(solver, plan):
    data = Operators(solver.global_plan)
    assert data.init_and_validate() is None
    solver.op_data = data
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name:
                op = data.operators[name]
                op._current_room, op.current_index = room, index
                op.mood, op.time_stamp = 8, datetime.now()
    return data


@pytest.mark.parametrize("resident", ["塑心", "红", "黑角", ""])
def test_cold_secondary_rest_restores_its_dorm_cover(dorm_solver, resident):
    data = observe_after_cache_clear(
        dorm_solver,
        {"meeting": [A, "初雪"], DORM: [resident, "冰酿", B, "", ""]},
    )
    before = deepcopy(data.group_shift_state)
    positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    plan = dorm_solver.agent_get_mood(
        skip_dorm=True, read_rooms=False, return_plan=True
    )
    assert plan == (
        {DORM: ["黑角", "Current", "Current", "Current", "Current"]}
        if resident != "黑角"
        else {}
    )
    assert data.group_shift_state == before
    assert positions == {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    dorm_solver.enter_room.assert_not_called()


@pytest.mark.parametrize("resident", ["红", "黑角", ""])
def test_cold_working_groups_restore_dorm_primary(dorm_solver, resident):
    observe_after_cache_clear(
        dorm_solver, {"meeting": [A, B], DORM: [resident, "冰酿", "", "", ""]}
    )
    assert dorm_solver.agent_get_mood(
        skip_dorm=True, read_rooms=False, return_plan=True
    ) == {DORM: ["塑心", "Current", "Current", "Current", "Current"]}


def test_cold_secondary_rest_accepts_its_working_primary_as_dorm_cover(dorm_solver):
    slot = dorm_solver.global_plan["default_plan"].plan[DORM][0]
    slot.group_bindings[0]["replacement"] = [B]
    observe_after_cache_clear(
        dorm_solver, {"meeting": [A, "初雪"], DORM: ["塑心", "冰酿", B, "", ""]}
    )
    assert dorm_solver.agent_get_mood(read_rooms=False, return_plan=True) == {
        DORM: [B, "Current", "Current", "Current", "Current"]
    }


@pytest.mark.parametrize("compatible", [False, True])
def test_cold_concurrent_rest_requires_common_dorm_cover(dorm_solver, compatible):
    if compatible:
        dorm_solver.global_plan["default_plan"].plan[DORM][0].group_bindings[0][
            "replacement"
        ] = ["红"]
    data = observe_after_cache_clear(
        dorm_solver,
        {"meeting": ["陈", "初雪"], DORM: ["塑心", "冰酿", A, B, ""]},
    )
    assert dorm_solver.agent_get_mood(read_rooms=False, return_plan=True) == (
        {DORM: ["红", "Current", "Current", "Current", "Current"]} if compatible else {}
    )
    assert data.group_shift_state == {}
    assert data.get_current_operator(DORM, 0).name == "塑心"


def test_cold_secondary_free_binding_opens_fixed_dorm_position(dorm_solver):
    dorm_solver.global_plan["default_plan"].plan[DORM][0].group_bindings[0][
        "replacement"
    ] = ["Free"]
    observe_after_cache_clear(
        dorm_solver, {"meeting": [A, "初雪"], DORM: ["塑心", "冰酿", B, "", ""]}
    )
    assert dorm_solver.agent_get_mood(read_rooms=False, return_plan=True) == {
        DORM: ["Free", "Current", "Current", "Current", "Current"]
    }


@pytest.mark.parametrize("blocked", ["busy", "working", "reserved"])
def test_cold_dorm_correction_preserves_unavailable_secondary_cover(
    dorm_solver, monkeypatch, blocked
):
    from arknights_mower.solvers import base_schedule

    data = observe_after_cache_clear(
        dorm_solver, {"meeting": [A, "初雪"], DORM: ["塑心", "冰酿", B, "", ""]}
    )
    if blocked == "busy":
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == "黑角"
        )
    elif blocked == "working":
        data.operators["黑角"]._current_room, data.operators["黑角"].current_index = (
            "central",
            0,
        )
    else:
        data.reserved_product_replacements.add("黑角")
    assert dorm_solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    assert data.group_shift_state == {}
    assert data.get_current_operator(DORM, 0).name == "塑心"


def test_cold_correction_dispatch_revalidates_secondary_binding(dorm_solver):
    data = observe_after_cache_clear(
        dorm_solver, {"meeting": [A, "初雪"], DORM: ["塑心", "冰酿", B, "", ""]}
    )
    assert (
        dorm_solver.agent_get_mood(skip_dorm=True, read_rooms=False)
        == "self_correction"
    )
    task = dorm_solver.tasks[0]
    assert task.type == TaskTypes.SELF_CORRECTION
    dorm_solver._prepare_group_shift(task, remember_targets=True)
    assert data.group_shift_state == {"甲": False, "乙": True}
    assert data.operators["塑心"].group == "乙"
    assert task.plan[DORM][0] == "黑角"
    data = data.project_arrangements([task.plan])
    dorm_solver.op_data = data
    assert data.get_current_operator(DORM, 0).name == "黑角"
    assert dorm_solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    assert dorm_solver._complete_group_shift(task)
    assert data.group_is_resting("乙")


@pytest.mark.parametrize("resting", [False, True])
def test_single_group_cold_start_restores_fixed_dorm_position(single_solver, resting):
    data = observe_after_cache_clear(
        single_solver,
        {
            "meeting": ["陈", "初雪"] if resting else [A, B],
            "contact": ["红"] if resting else ["讯使"],
            DORM: [
                "塑心" if resting else "黑角",
                "冰酿",
                A if resting else "塑心",
                B if resting else "",
                "讯使" if resting else "",
            ],
        },
    )
    plan = single_solver.agent_get_mood(
        skip_dorm=True, read_rooms=False, return_plan=True
    )
    assert plan[DORM][0] == ("黑角" if resting else "塑心")
    projected = data.project_arrangements([plan])
    assert projected.get_current_operator(DORM, 0).name == plan[DORM][0]
    assert data.group_shift_state == {}


def test_first_planning_pass_after_cache_clear_queues_secondary_dorm_correction(
    dorm_solver,
):
    from unittest.mock import MagicMock

    observe_after_cache_clear(
        dorm_solver, {"meeting": [A, "初雪"], DORM: ["塑心", "冰酿", B, "", ""]}
    )
    dorm_solver.task = None
    dorm_solver.find = MagicMock(return_value=True)
    dorm_solver.planned = False
    dorm_solver.defer_backup_plan_until_mood_read = True
    dorm_solver.no_pending_task = MagicMock(return_value=True)
    dorm_solver._read_agent_mood = MagicMock()
    dorm_solver._read_initial_card_mood = MagicMock()
    dorm_solver._queue_initial_fia = MagicMock(return_value=False)
    dorm_solver.backup_plan_solver = MagicMock()
    dorm_solver.queue_product_switches = MagicMock()
    dorm_solver.skip = MagicMock()
    dorm_solver.run_order_solver = MagicMock()
    dorm_solver.plan_solver = MagicMock()
    assert dorm_solver.infra_main()
    dorm_solver._read_agent_mood.assert_called_once()
    dorm_solver._read_initial_card_mood.assert_called_once()
    assert not dorm_solver.defer_backup_plan_until_mood_read
    assert dorm_solver.tasks[0].type == TaskTypes.SELF_CORRECTION
    assert dorm_solver.tasks[0].plan[DORM][0] == "黑角"
    dorm_solver.run_order_solver.assert_not_called()
    dorm_solver.plan_solver.assert_not_called()


@pytest.mark.parametrize("first", [0, 1])
def test_cold_common_cover_returns_only_after_final_group_confirmation(
    dorm_solver, first
):
    dorm_solver.global_plan["default_plan"].plan[DORM][0].group_bindings[0][
        "replacement"
    ] = ["红"]
    data = observe_after_cache_clear(
        dorm_solver, {"meeting": ["陈", "初雪"], DORM: ["红", "冰酿", A, B, ""]}
    )
    data.restore_group_shift_state()
    assert data.group_shift_state == {"甲": True, "乙": True}
    for turn, index in enumerate([first, 1 - first]):
        row = ["Current", "Current"]
        row[index] = [A, B][index]
        task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": row})
        dorm_solver.tasks = [task]
        dorm_solver._prepare_group_shift(task, remember_targets=True)
        assert not dorm_solver._complete_group_shift(task)
        assert data.group_is_resting(["甲", "乙"][index])
        dorm_solver.op_data = data = data.project_arrangements([task.plan])
        assert dorm_solver._complete_group_shift(task)
        assert data.get_current_operator(DORM, 0).name == (
            "红" if turn == 0 else "塑心"
        )
    assert data.group_shift_state == {"甲": False, "乙": False}
