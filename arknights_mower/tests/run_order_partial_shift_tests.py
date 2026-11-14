"""普通换班让行后保留实际离岗状态，完成尚未执行的入宿安排。"""

import pickle
from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import run_order_staffing_admission_tests as admission

staffed_order = admission.staffed_order


@pytest.fixture
def ordinary_shift(staffed_order, monkeypatch):
    from arknights_mower.utils.plan import Plan, PlanConfig, Room

    ui = staffed_order
    s = ui.solver
    s.op_data = ui.operators(
        {
            "default_plan": Plan(
                {
                    "room_1_1": [Room("鸿雪", "", ["但书", "孑"])],
                    "room_2_2": [Room("图耶", "", ["龙舌兰", "锏"])],
                    "central": [Room("白面鸮", "轮休", ["香草"])],
                    "contact": [Room("讯使", "轮休", ["红"])],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("蜜莓", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", ""),
                products={"room_1_1": "lmd", "room_2_2": "lmd"},
            ),
            "backup_plans": [],
        }
    )
    assert s.op_data.init_and_validate() is None
    s.op_data.first_init = False
    ui.occupants.update(
        {
            "room_1_1": ["鸿雪"],
            "room_2_2": ["图耶"],
            "central": ["白面鸮"],
            "contact": ["讯使"],
            "dormitory_1": ["杜林", "蜜莓", "", "", ""],
        }
    )
    ui.states.update({"room_1_1": "active", "room_2_2": "active"})
    ui.durations.update({"central": 20, "contact": 20})
    ui.config.conf.group_rest_in_full_on_mood_gap = False
    ui.config.conf.rescue_threshold = 0
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = "", -1
        op.mood, op.time_stamp, op.mood_is_prediction = 24, ui.clock.now(), False
    for name in ("白面鸮", "讯使"):
        s.op_data.operators[name].mood = 0

    def read_room(room, *args, **kwargs):
        result = []
        for index, name in enumerate(ui.occupants[room]):
            if name:
                op = s.op_data.operators[name]
                op.current_room, op.current_index = room, index
                op.time_stamp = ui.clock.now()
            result.append(
                {
                    "agent": name,
                    "mood": s.op_data.operators[name].mood if name else -1,
                    "time": ui.clock.now() + timedelta(hours=4),
                }
            )
        s._reconcile_room_observation(room, result)
        if room.startswith("dorm"):
            for index in s.op_data.get_refresh_index(
                room,
                ui.occupants[room],
                group_transitions=s._execution_group_transitions(),
            ):
                s.op_data.refresh_dorm_time(
                    room,
                    index,
                    result[index],
                    group_transitions=s._execution_group_transitions(),
                )
        return result

    def confirm(room, new_plan):
        chosen = s.choose_agent.call_args.args[0]
        actual = ui.occupants[room].copy()
        for index, name in enumerate(chosen):
            if name == "Current":
                continue
            if name in ("Free", ""):
                actual[index] = ""
                continue
            for other_room, row in ui.occupants.items():
                for other_index, occupant in enumerate(row):
                    if occupant == name:
                        row[other_index] = ""
            actual[index] = name
        ui.occupants[room] = actual
        ui.clock.current += timedelta(seconds=ui.durations[room])
        ui.events.append(("staffed", room, ui.clock.now()))

    s.get_agent_from_room = MagicMock(side_effect=read_room)
    s.tap_confirm.side_effect = confirm
    s._suppress_train_correction = MagicMock()
    s.check_fia = MagicMock(return_value=([], None))
    s.find_next_task = MagicMock(return_value=None)
    s.plan_metadata = ui.base.BaseSchedulerSolver.plan_metadata.__get__(s)
    for room in ui.occupants:
        read_room(room)
    s.op_data.commit_group_shifts({"轮休": False})
    return ui


@pytest.mark.parametrize("kind", ["SHIFT_OFF", "EXHAUST_OFF"])
@pytest.mark.parametrize("restart", [False, True])
def test_departed_zero_mood_group_enters_reserved_beds_after_run_order(
    ordinary_shift, monkeypatch, kind, restart
):
    ui = ordinary_shift
    s = ui.solver
    task = ui.task(
        time=ui.clock.now() - timedelta(minutes=1),
        task_type=getattr(ui.task_type, kind),
        task_plan={
            "central": ["香草"],
            "contact": ["红"],
            "dormitory_1": ["Current", "Current", "白面鸮", "讯使", "Current"],
        },
    )
    original_time = task.time
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=10)
    ui.durations["contact"] = 360
    s.tasks = [task]
    s.plan_run_order("room_1_1")
    order = next(t for t in s.tasks if t.type == ui.task_type.RUN_ORDER)
    s.task = task

    s.infra_main()

    assert task.plan == {
        "dormitory_1": ["Current", "Current", "白面鸮", "讯使", "Current"]
    }
    assert ui.occupants["central"] == ["香草"]
    assert ui.occupants["contact"] == ["红"]
    assert s.op_data.operators["白面鸮"].current_room == ""
    assert s.op_data.operators["讯使"].current_room == ""
    assert not s.op_data.group_is_resting("轮休")
    assert task.retains_execution and task.time == original_time
    remaining = deepcopy(task.plan)
    reserved_names, reserved_slots = ui.base.dorm_task_reservations(s.op_data, s.tasks)
    assert reserved_names >= {"白面鸮", "讯使"}
    assert reserved_slots >= {("dormitory_1", 2), ("dormitory_1", 3)}

    if restart:
        transitions = dict(task.group_shift_transitions)
        expected = dict(task.group_shift_expected)
        s.op_data, s.tasks = pickle.loads(pickle.dumps((s.op_data, s.tasks)))
        task = next(t for t in s.tasks if t.type == getattr(ui.task_type, kind))
        order = next(t for t in s.tasks if t.type == ui.task_type.RUN_ORDER)
        s.task = task
        monkeypatch.setattr(
            ui.operators, "current_room_changed_callback", s.current_room_changed
        )
        assert task.retains_execution and task.plan == remaining
        assert task.time == original_time
        assert task.group_shift_transitions == transitions
        assert task.group_shift_expected == expected
        assert not s.op_data.group_is_resting("轮休")
        assert ui.base.dorm_task_reservations(s.op_data, s.tasks) == (
            reserved_names,
            reserved_slots,
        )

    ui.clock.current = max(ui.clock.now(), order.time)
    s.task = order
    s.infra_main()

    assert s.accept_order.call_count == 1
    assert ui.occupants["room_1_1"] == ["鸿雪"]
    assert task.plan == remaining and task.time == original_time
    assert all(s.op_data.operators[name].mood == 0 for name in ("白面鸮", "讯使"))
    s.task = task
    s.infra_main()

    assert task.plan == {} and all(t is not task for t in s.tasks)
    assert task.time == original_time
    assert s.op_data.group_is_resting("轮休")
    for name in ("白面鸮", "讯使"):
        op = s.op_data.operators[name]
        assert op.is_resting() and op.mood == 0
        assert s.op_data.get_dorm_by_name(name)[1].position == (
            op.current_room,
            op.current_index,
        )
    arranged = [event[1] for event in ui.events if event[0] == "staffed"]
    assert arranged.count("central") == arranged.count("contact") == 1
    assert not getattr(task, "execution_failure", None)
    returns = [pending for pending in s.tasks if pending.type == ui.task_type.SHIFT_ON]
    assert len(returns) == 1
    assert returns[0].time > ui.clock.now()
    assert returns[0].plan == {"central": ["白面鸮"], "contact": ["讯使"]}


def test_partially_departed_group_finishes_work_before_reserved_dorm(ordinary_shift):
    ui = ordinary_shift
    s = ui.solver
    task = ui.task(
        time=ui.clock.now(),
        task_type=ui.task_type.SHIFT_OFF,
        task_plan={
            "central": ["香草"],
            "contact": ["红"],
            "dormitory_1": ["Current", "Current", "白面鸮", "讯使", "Current"],
        },
    )
    original_time = task.time
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=10)
    ui.durations["central"] = 380
    s.tasks, s.task = [task], task
    s.plan_run_order("room_1_1")

    s.infra_main()

    assert set(task.plan) == {"contact", "dormitory_1"}
    assert s.op_data.operators["白面鸮"].current_room == ""
    assert s.op_data.operators["讯使"].current_room == "contact"
    assert not s.op_data.group_is_resting("轮休")
    order = next(t for t in s.tasks if t.type == ui.task_type.RUN_ORDER)
    ui.clock.current = max(ui.clock.now(), order.time)
    s.task = order
    s.infra_main()
    s.task = task
    s.infra_main()

    assert task.plan == {} and all(t is not task for t in s.tasks)
    assert task.time == original_time
    assert s.op_data.group_is_resting("轮休")
    for name in ("白面鸮", "讯使"):
        assert s.op_data.operators[name].is_resting()
        assert s.op_data.operators[name].mood == 0
    arranged = [event[1] for event in ui.events if event[0] == "staffed"]
    assert arranged.count("central") == arranged.count("contact") == 1


def test_partial_return_resumes_remaining_station_after_order(ordinary_shift):
    ui = ordinary_shift
    s = ui.solver
    ui.occupants.update(
        {
            "central": ["香草"],
            "contact": ["红"],
            "dormitory_1": ["杜林", "蜜莓", "白面鸮", "讯使", ""],
        }
    )
    for name in ("白面鸮", "讯使"):
        op = s.op_data.operators[name]
        op.mood, op.time_stamp, op.rest_in_full = 24, ui.clock.now(), True
    for room in ("central", "contact", "dormitory_1"):
        s.get_agent_from_room(room)
    s.op_data.commit_group_shifts({"轮休": True})
    task = ui.task(
        time=ui.clock.now(),
        task_type=ui.task_type.SHIFT_ON,
        task_plan={"central": ["白面鸮"], "contact": ["讯使"]},
    )
    original_time = task.time
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=10)
    ui.durations["central"] = 380
    s.tasks = [task]
    s._refresh_observed_recovery_tasks()
    task = next(t for t in s.tasks if t.type == ui.task_type.SHIFT_ON)
    assert task.time == original_time
    assert task.plan == {"central": ["白面鸮"], "contact": ["讯使"]}
    s.task = task
    s.plan_run_order("room_1_1")

    s.infra_main()

    assert "central" not in task.plan and task.plan["contact"] == ["讯使"]
    assert ui.occupants["central"] == ["白面鸮"]
    assert ui.occupants["contact"] == ["红"]
    assert s.op_data.group_is_resting("轮休")
    order = next(t for t in s.tasks if t.type == ui.task_type.RUN_ORDER)
    ui.clock.current = max(ui.clock.now(), order.time)
    s.task = order
    s.infra_main()
    s.task = task
    s.infra_main()

    assert task.plan == {} and all(t is not task for t in s.tasks)
    assert task.time == original_time
    assert not s.op_data.group_is_resting("轮休")
    for name in ("白面鸮", "讯使"):
        assert s.op_data.operators[name].is_working()
    arranged = [event[1] for event in ui.events if event[0] == "staffed"]
    assert arranged.count("central") == arranged.count("contact") == 1
