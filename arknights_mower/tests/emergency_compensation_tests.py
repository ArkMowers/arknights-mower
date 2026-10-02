"""专项临时换人通过实际选人路径恢复智能救急的空岗位。"""

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, emergency
from arknights_mower.tests.automatic_rescue_tests import make_episode
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "room_1_1"


def selection_harness(solver, monkeypatch):
    """替换屏幕操作，保留房间安排及选人对空岗位的实际处理。"""
    solver.op_data.plan[ROOM].append(Room("Free", "", []))
    solver.op_data.operators[PRIMARY[0]]._current_room = ""
    solver.op_data.add(Operator("但书", ""))
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False
    )
    solver.recog = SimpleNamespace(w=1920, h=1080, img=object(), update=MagicMock())
    solver.last_room = ""
    solver.choose_error = set()
    solver.waiting_scene = []
    solver.scene = MagicMock(return_value=Scene.INFRA_MAIN)
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.find = MagicMock(return_value=True)
    solver.tap = MagicMock()
    solver.back = MagicMock()
    solver.profession_filter = MagicMock()
    solver.detect_arrange_order = MagicMock(return_value=("技能", False))
    solver.switch_arrange_order = MagicMock()
    solver.prepare_dorm_selection = MagicMock(return_value=None)
    solver.get_free_list = MagicMock(return_value=[COVERS[1]])
    solver.swipe_left = MagicMock(return_value=0)
    solver.wait_for_arranged_agents = MagicMock(side_effect=lambda names, **k: names)
    solver.verify_agent = MagicMock(return_value=True)
    solver.record_selection_success = MagicMock()
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver.drone = MagicMock()
    solver.skip = MagicMock()
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *a: False
    )
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())

    def scan(names, **kwargs):
        selected = list(names)
        names.clear()
        return selected, []

    solver.scan_agent = MagicMock(side_effect=scan)

    def place(row):
        for op in solver.op_data.operators.values():
            if op.current_room == ROOM:
                op._current_room, op.current_index = "", -1
        for index, name in enumerate(n for n in row if n):
            op = solver.op_data.operators[name]
            op._current_room, op.current_index = ROOM, index

    solver.refresh_current_room = MagicMock(
        side_effect=lambda room, *a: solver.op_data.get_current_room(room, True)
    )
    solver.get_agent_from_room = MagicMock(
        side_effect=lambda room, *a, **k: [
            {"agent": name} for name in solver.op_data.get_current_room(room, True)
        ]
    )
    chosen = {}
    choose_agent = solver.choose_agent

    def choose(row, room, **kwargs):
        choose_agent(row, room, **kwargs)
        chosen[room] = row.copy()

    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap_confirm = MagicMock(
        side_effect=lambda room, new_plan: place(chosen[room])
    )
    return place


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
@pytest.mark.parametrize("original", [[COVERS[0], ""], ["", ""]])
def test_emergency_compensation_preserves_vacancies_through_real_selection(
    solver, monkeypatch, kind, original
):
    make_episode(solver)
    place = selection_harness(solver, monkeypatch)
    place(["但书", COVERS[1]])
    task = SchedulerTask(task_type=kind, task_plan={ROOM: original.copy()})
    if kind == TaskTypes.RUN_ORDER:
        task.emergency_original_roster = {ROOM: original.copy()}
    solver.task = task
    solver.tasks = [task]

    solver.agent_arrange_room({}, ROOM, task.plan)

    assert solver.op_data.get_current_room(ROOM, True) == original
    solver.get_free_list.assert_not_called()
    assert not getattr(task, "emergency_staffing", False)
    assert task.plan == {}


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
@pytest.mark.parametrize("recovering", [False, True])
def test_specialized_arrangement_retains_ordinary_and_explicit_free_filling(
    solver, monkeypatch, kind, recovering
):
    if recovering:
        make_episode(solver)
    place = selection_harness(solver, monkeypatch)
    place(["但书", COVERS[1]])
    task = SchedulerTask(
        task_type=kind, task_plan={ROOM: [COVERS[0], "Free" if recovering else ""]}
    )
    solver.task = task
    solver.tasks = [task]

    solver.agent_arrange_room({}, ROOM, task.plan)

    assert solver.op_data.get_current_room(ROOM, True) == [COVERS[0], COVERS[1]]
    solver.get_free_list.assert_called_once()


@pytest.mark.parametrize("buffer", [0, 1])
@pytest.mark.parametrize("original", [[COVERS[0], ""], ["", ""]])
def test_run_order_immediate_and_queued_compensation_restore_observed_vacancies(
    solver, monkeypatch, buffer, original
):
    make_episode(solver)
    place = selection_harness(solver, monkeypatch)
    place(original)
    config.conf.run_order_grandet_mode.enable = bool(buffer)
    config.conf.run_order_grandet_mode.buffer_time = buffer
    order = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER,
        task_plan={ROOM: ["但书", COVERS[1]]},
        meta_data=ROOM,
    )
    order.adjusted = True
    solver.task = order
    solver.tasks = [SchedulerTask(time=NOW, meta_data=emergency.CHECK_META)]
    arrange_room = solver.agent_arrange_room

    def perform_swap(new_plan, room, plan, **kwargs):
        if "但书" in plan[room]:
            swapped = copy.deepcopy(plan[room])
            place(swapped)
            del plan[room]
            return {room: swapped}
        return arrange_room(new_plan, room, plan, **kwargs)

    solver.agent_arrange_room = perform_swap
    solver.agent_arrange(order.plan)
    assert order.emergency_original_roster == {ROOM: original}
    if buffer == 0:
        restore = next(t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER)
        assert restore.plan == {ROOM: original}
        solver.task = restore
        solver.agent_arrange(restore.plan)
        assert not getattr(restore, "emergency_staffing", False)

    assert solver.op_data.get_current_room(ROOM, True) == original
    solver.get_free_list.assert_not_called()
