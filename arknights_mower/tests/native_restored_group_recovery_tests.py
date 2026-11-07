"""副表退出重新纳入主班的恢复期限参与原组正常回班。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import dorm_group_tests as native
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = native.solver


@pytest.fixture
def restored_group(monkeypatch, offline_maintenance, solver):
    now = datetime(2026, 11, 4, 12)

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_threshold_minutes = 90
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("令", "G", ["红"])],
                    "room_1_2": [Room("结城理", "G", ["空爆"])],
                    "dormitory_1": [
                        Room(name, "", [])
                        for name in ["杜林", "闪灵", "Free", "Free", "Free"]
                    ],
                },
                PlanConfig("", "", "", ling_xi=2),
            ),
            "backup_plans": [
                Plan(
                    {"room_1_2": [Room("空爆", "", ["翎羽"])]},
                    PlanConfig("", "", "", ling_xi=2),
                    trigger=LogicExpression(
                        "op_data.operators['令'].is_working()", "!=", "True"
                    ),
                )
            ],
        }
    )
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) is None
    data._projection_now = now
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, now
    for name, index, mood, hours in [("令", 2, 24, 0), ("结城理", 3, 18, 3)]:
        op = data.operators[name]
        op._current_room, op.current_index, op.mood = "dormitory_1", index, mood
        bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", index))
        bed.name, bed.time = name, now + timedelta(hours=hours)
    data.operators["红"]._current_room, data.operators["红"].current_index = (
        "central",
        0,
    )
    data.commit_group_shifts({"G": True})
    solver.op_data, solver.waiting_group_shifts = data, []
    solver.global_plan = data.global_plan
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    task = SchedulerTask(now, {"central": ["令"]}, TaskTypes.SHIFT_ON)
    solver.tasks, solver.task = [task], task
    return solver, task, now


@pytest.mark.parametrize(
    "kind", ["gap", "disabled", "excluded", "short-gap", "explicit", "complete"]
)
def test_final_restored_members_use_the_existing_group_recovery_policy(
    restored_group, kind
):
    solver, task, now = restored_group
    data = solver.op_data
    if kind == "disabled":
        config.conf.group_rest_in_full_on_mood_gap = False
    elif kind == "excluded":
        config.conf.group_mood_gap_exclusions = ["G"]
    elif kind == "short-gap":
        config.conf.group_mood_gap_threshold_minutes = 240
    elif kind == "explicit":
        task.backup_explicit_slots = {("room_1_2", 0)}
    elif kind == "complete":
        data.operators["结城理"].mood = 24
    solver._prepare_shift_cycle(task)
    assert task.time == now + timedelta(hours=3 if kind == "gap" else 0)
    assert data.operators["结城理"].current_room == "dormitory_1"
    assert data.operators["结城理"].mood == (24 if kind == "complete" else 18)
    assert any(queued is task for queued in solver.tasks)


def test_final_members_keep_the_absolute_existing_gap_cap(restored_group):
    solver, task, now = restored_group
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    for elapsed in [0, 0.1, 0.2]:
        solver.op_data._projection_now = now + timedelta(hours=elapsed)
        solver._prepare_shift_cycle(task)
        assert task.time == now + timedelta(hours=0.5)
        assert sum(queued is task for queued in solver.tasks) == 1


@pytest.mark.parametrize(
    "kind",
    [
        "separate",
        "same-room",
        "shared-cover",
        "working-source-cover",
        "ungrouped-prerequisite",
        "later-coalesced",
        "ungrouped-only",
        "third-group",
    ],
)
def test_merged_independent_return_keeps_its_own_date(restored_group, kind):
    solver, task, now = restored_group
    data = solver.op_data
    common_room = kind == "same-room"
    group = "" if kind.startswith("ungrouped-") else "H"
    room, index = ("central", 1) if common_room else ("meeting", 0)
    row = [Room("银灰", group, ["初雪"])]
    if common_room:
        data.global_plan["default_plan"].plan[room].extend(row)
        data.plan[room].extend(row)
        task.plan[room] = ["令", "银灰"]
    else:
        data.global_plan["default_plan"].plan[room] = row
        data.plan[room] = list(row)
        task.plan[room] = ["银灰"]
    data.add(
        Operator(
            "银灰",
            room,
            index,
            group,
            ["初雪"],
            resting_priority="high",
            current_room="dormitory_1",
            current_index=4,
            operator_type="high",
            mood=24,
            time_stamp=now,
        )
    )
    data.add(
        Operator(
            "初雪", "", current_room=room, current_index=index, mood=24, time_stamp=now
        )
    )
    if group:
        data.groups["H"], data.group_shift_state["H"] = ["银灰"], True
    bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 4))
    bed.name, bed.time = "银灰", now
    if kind == "third-group":
        for name, own_group, cover, primary_room in [
            ("令", "G", "红", "central"),
            ("银灰", "H", "初雪", room),
        ]:
            bindings = [
                {"group": own_group, "replacement": [cover]},
                {"group": "J", "replacement": [cover]},
            ]
            data.operators[name].group_bindings = bindings
            data.operators[name].shift_group = own_group
            data.global_plan["default_plan"].plan[primary_room][
                0
            ].group_bindings = bindings[1:]
        shared = [Room("伊内丝", "J", ["令"]), Room("讯使", "J", ["银灰"])]
        data.global_plan["default_plan"].plan["room_2_1"] = shared
        data.plan["room_2_1"] = shared
        for position, entry in enumerate(shared):
            data.add(
                Operator(
                    entry.agent,
                    "room_2_1",
                    position,
                    "J",
                    entry.replacement,
                    current_room="room_2_1",
                    current_index=position,
                    operator_type="high",
                    mood=24,
                    time_stamp=now,
                )
            )
        data.groups["J"], data.group_shift_state["J"] = ["伊内丝", "讯使"], False
    if kind == "later-coalesced":
        del task.plan[room]
        config.conf.group_mood_gap_threshold_minutes = 30
        data._projection_now = now + timedelta(hours=2)
        solver.tasks.append(
            SchedulerTask(
                now + timedelta(hours=2), {room: ["银灰"]}, TaskTypes.SHIFT_ON
            )
        )
    if kind in {"shared-cover", "working-source-cover"}:
        data.operators["红"]._current_room, data.operators["红"].current_index = "", -1
        data.operators["银灰"]._current_room, data.operators["银灰"].current_index = (
            "central",
            0,
        )
        data.operators["令"].replacement = ["银灰"]
        data.plan["central"][0].replacement = ["银灰"]
        data.global_plan["default_plan"].plan["central"][0].replacement = ["银灰"]
        bindings = [
            {"group": "G", "replacement": ["初雪"]},
            {"group": "H", "replacement": ["初雪"]},
        ]
        data.operators["银灰"].group_bindings = bindings
        data.operators["银灰"].shift_group = "H"
        row[0].group_bindings = bindings[:1]
        bed.reset()
        if kind == "working-source-cover":
            data.commit_group_shifts({"H": False})
            assert data.group_is_resting("H") is False
            assert data.operators["银灰"].group == "H"
    if kind.startswith("ungrouped-"):
        data.backup_plans[0].trigger = LogicExpression(
            "op_data.operators['银灰'].is_working()", "!=", "True"
        )
        data.backup_plans[0].group_tasks = [
            {"group": "G", "action": "off", "mode": "forced"}
        ]
    if kind == "ungrouped-only":
        task.plan = {room: ["银灰"]}
    for _ in range(3):
        solver._prepare_shift_cycle(task)
        returning = [
            queued
            for queued in solver.tasks
            if queued.plan.get(room, [])[index : index + 1] == ["银灰"]
        ]
        assert len(returning) == 1
        assert returning[0].time == now + timedelta(
            hours=3
            if kind in {"shared-cover", "working-source-cover"}
            else 2
            if kind == "later-coalesced"
            else 0
        )
        assert task.time == now + timedelta(hours=0 if kind == "ungrouped-only" else 3)
        assert data.operators["银灰"].current_room == (
            "central"
            if kind in {"shared-cover", "working-source-cover"}
            else "dormitory_1"
        )

    if kind == "ungrouped-prerequisite":
        sibling = next(
            queued
            for queued in solver.tasks
            if queued.time == now and queued.plan.get(room) == ["银灰"]
        )
        observed = data.project_arrangements([sibling.plan])
        assert observed.swap_plan(sibling.backup_shift_conditions, refresh=True) is None
        observed.commit_group_shifts(sibling.group_shift_transitions)
        observed._projection_now = now + timedelta(hours=3)
        observed.operators["结城理"].mood = 24
        observed.operators["结城理"].time_stamp = observed._projection_now
        solver.op_data = observed
        solver.tasks = [queued for queued in solver.tasks if queued is not sibling]
        solver._prepare_shift_cycle(task)
        assert task.time == now + timedelta(hours=3)
        assert task.plan["central"] == ["令"]
        assert not any(queued.plan.get(room) == ["银灰"] for queued in solver.tasks)


@pytest.mark.parametrize("kind", ["started", "backup", "retained", "product"])
def test_prepared_and_explicit_execution_keeps_its_existing_date(restored_group, kind):
    solver, task, now = restored_group
    if kind == "started":
        task.group_shift_expected = {("central", 0): "令"}
    elif kind == "backup":
        task.backup_shift_active = True
    elif kind == "retained":
        task.execution_retained = True
    elif kind == "product":
        task.product_shift_locked = True
    solver._prepare_shift_cycle(task)
    assert task.time == now
    assert solver.op_data.operators["结城理"].current_room == "dormitory_1"


def test_valid_personal_cap_completion_survives_restored_membership(restored_group):
    solver, task, now = restored_group
    data = solver.op_data
    for plan in [data.global_plan["default_plan"], *data.backup_plans]:
        plan.config.operator_mood_limits = {"令": {"lower": 0, "upper": 12}}
    data.config.operator_mood_limits = {"令": {"lower": 0, "upper": 12}}
    op = data.operators["令"]
    data.get_dorm_by_name("令")[1].reset()
    op.upper_limit, op.lower_limit = 12, 0
    op._current_room, op.current_index = "", -1
    op.mood, op.rest_mood_release_limit = 11.925, 12
    data.operators["结城理"].mood = 24
    solver._prepare_shift_cycle(task)
    assert task.time == now
    assert task.plan["central"] == ["令"]
    assert op.mood == 11.925


def test_recalculated_return_releases_dispatch_before_product_or_room_actions(
    restored_group, monkeypatch
):
    solver, task, now = restored_group
    independent = SchedulerTask(now, task_type=TaskTypes.NOT_SPECIFIC)
    solver.tasks.append(independent)
    monkeypatch.setattr(solver, "find", MagicMock(return_value=True))
    monkeypatch.setattr(solver, "skip", MagicMock())
    monkeypatch.setattr(solver, "agent_arrange", MagicMock(side_effect=AssertionError))
    monkeypatch.setattr(
        solver,
        "_switch_products_before_arrangement",
        MagicMock(side_effect=AssertionError),
    )
    solver.infra_main()
    assert task.time == now + timedelta(hours=3)
    assert solver.tasks[0] is independent
    assert any(queued is task for queued in solver.tasks)
    assert solver.task is None
    solver.agent_arrange.assert_not_called()
    solver._switch_products_before_arrangement.assert_not_called()
