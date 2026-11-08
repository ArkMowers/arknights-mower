"""任务预告只读解释既有意图，保留共享成员和完整岗位。"""

import logging
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.idle_scene_watchdog_tests import (
    idle_scheduler as idle_scheduler,
)
from arknights_mower.tests.idle_scene_watchdog_tests import (
    production_idle_scheduler as production_idle_scheduler,
)
from arknights_mower.tests.multi_group_shift_tests import SHARED, A, B
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.task_presentation import (
    build_task_presentation,
    format_task_log_message,
    remember_backup_changes,
)


def test_facilities_use_observations_then_effective_plan_without_losing_positions():
    plan = {
        "room_3_3": ["甲"],
        "room_2_1": ["Current", "乙", "Free"],
        "dormitory_2": ["Current"],
    }
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.SELF_CORRECTION)
    data = SimpleNamespace(
        facility_states={"room_3_3": {"facility": "power"}},
        plan={
            "room_3_3": [SimpleNamespace(facility="制造站")],
            "room_2_1": [SimpleNamespace(facility="贸易站")],
        },
    )
    result = build_task_presentation(task, data)
    assert result["rooms"] == [
        {"id": "room_3_3", "label": "发电站 B303", "agents": ["甲"]},
        {"id": "room_2_1", "label": "贸易站 B201", "agents": ["Current", "乙", "Free"]},
        {"id": "dormitory_2", "label": "宿舍2", "agents": ["Current"]},
    ]
    plan["room_3_3"][0] = "丙"
    data.facility_states["room_3_3"]["facility"] = "trade"
    assert result["rooms"][0] == {
        "id": "room_3_3",
        "label": "发电站 B303",
        "agents": ["甲"],
    }


def test_mixed_groups_keep_one_description_and_shared_operator_is_not_a_second_action(
    solver,
):
    data = solver.op_data
    data.group_shift_state = {"甲": False, "乙": True}
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["陈", B]}
    )
    task.group_shift_transitions = {"甲": True, "乙": False}
    before = (
        dict(data.group_shift_state),
        deepcopy(data.groups),
        data.operators[SHARED].group,
        deepcopy(task.plan),
    )
    result = build_task_presentation(task, data)
    assert result["title"] == "甲下班；乙、陈上班"
    assert SHARED not in result["title"]
    assert before == (
        data.group_shift_state,
        data.groups,
        data.operators[SHARED].group,
        task.plan,
    )


def test_group_with_shared_follower_is_not_mistaken_for_single_person(solver):
    data = solver.op_data
    data.group_shift_state = {"甲": False}
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.group_shift_transitions = {"甲": True}
    assert build_task_presentation(task, data)["title"] == "甲下班"


def test_group_member_snapshots_cover_all_bindings_without_replacement_names(solver):
    data = solver.op_data
    data.group_shift_state = {"甲": True, "乙": True}
    data.groups["甲"].append(A)
    data.operators[SHARED].group = "乙"
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, B], "contact": [SHARED]},
    )
    task.group_shift_transitions = {"甲": False, "乙": False}
    before = deepcopy(
        (data.groups, data.operators[SHARED].group_bindings, data.group_shift_state)
    )

    result = build_task_presentation(task, data)

    assert result["actions"] == [
        {
            "kind": "group",
            "subject": "甲",
            "action": "上班",
            "members": [A, SHARED],
        },
        {
            "kind": "group",
            "subject": "乙",
            "action": "上班",
            "members": [B, SHARED],
        },
    ]
    assert before == (
        data.groups,
        data.operators[SHARED].group_bindings,
        data.group_shift_state,
    )


def test_group_member_snapshot_survives_later_renaming_and_rebinding(solver):
    data = solver.op_data
    data.group_shift_state["甲"] = True
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"], "contact": [SHARED]},
    )
    task.group_shift_transitions = {"甲": False}
    snapshot = build_task_presentation(task, data)

    data.groups["改名后的甲"] = data.groups.pop("甲")
    data.groups["改名后的甲"].clear()
    data.operators[A].group = "改名后的甲"
    data.operators[SHARED].group_bindings[0]["group"] = "改名后的甲"

    assert data.shift_group_members("甲") == []
    assert snapshot["title"] == "甲上班"
    assert snapshot["actions"] == [
        {
            "kind": "group",
            "subject": "甲",
            "action": "上班",
            "members": [A, SHARED],
        }
    ]


def test_explicit_group_intent_is_not_overwritten_by_current_slot_ownership(solver):
    data = solver.op_data
    data.group_shift_state = {"甲": False}
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": [A]})
    task.group_shift_transitions = {"甲": True}
    assert build_task_presentation(task, data)["title"] == "甲下班"
    assert task.group_shift_transitions == {"甲": True}
    task.group_shift_transitions = {}
    assert build_task_presentation(task, data)["title"] == "安排干员"


def test_true_single_person_group_uses_the_person_name(solver):
    data = solver.op_data
    data.groups["单人"] = [A]
    data.operators[A].group = "单人"
    data.group_shift_state["单人"] = False
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.group_shift_transitions = {"单人": True}
    assert build_task_presentation(task, data)["title"] == f"{A}下班"


@pytest.mark.parametrize("returning", [False, True])
def test_individual_shift_requires_confirmed_source_and_primary_identity(
    solver, returning
):
    data = solver.op_data
    op = data.operators[A]
    op.group = ""
    if returning:
        op._current_room, op.current_index = "dormitory_1", 2
        plan = {op.room: [op.name]}
    else:
        plan = {"dormitory_1": ["塑心", "冰酿", op.name]}
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON if returning else TaskTypes.SHIFT_OFF,
        task_plan=plan,
    )
    assert (
        build_task_presentation(task, data)["title"]
        == f"{A}{'上班' if returning else '休息'}"
    )
    op._current_room, op.current_index = None, -1
    assert build_task_presentation(task, data)["title"] == "安排干员"


def test_internal_task_type_does_not_claim_everyone_is_going_off_shift():
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_2_1": ["Current", "甲"]}
    )
    assert build_task_presentation(task, None)["title"] == "安排干员"


@pytest.fixture
def dorm_takeover():
    operators = {
        name: Operator(name, "", current_room=room, current_index=index)
        for room, names in (
            ("dormitory_1", ["杜林", "闪灵", "砾", "爱丽丝", "兰"]),
            ("dormitory_2", ["塑心", "冰酿", "黑角", "夜刀", "米格鲁"]),
            ("meeting", ["鸿雪", "红"]),
        )
        for index, name in enumerate(names)
    }
    operators.update(
        {name: Operator(name, "", current_room="") for name in ("桑葚", "夜莺", "陈")}
    )
    data = SimpleNamespace(
        operators=operators,
        plan={
            "dormitory_1": [None] * 5,
            "dormitory_2": [None] * 5,
            "meeting": [None] * 2,
        },
        groups={},
        group_shift_state={},
        project_arrangements=Mock(side_effect=AssertionError("任务展示不得投影驻员")),
    )
    task = SchedulerTask(
        task_type=TaskTypes.NOT_SPECIFIC,
        task_plan={"dormitory_1": ["Current", "Current", "桑葚", "Current", "Current"]},
    )
    return data, task


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.SHIFT_ON,
        TaskTypes.SHIFT_OFF,
        TaskTypes.EXHAUST_OFF,
        TaskTypes.SELF_CORRECTION,
        TaskTypes.RE_ORDER,
        TaskTypes.FILL_DORM,
        TaskTypes.RELEASE_DORM,
        TaskTypes.NOT_SPECIFIC,
    ],
)
def test_explicit_dorm_takeover_rest_precedes_the_departing_resident_idle_action(
    dorm_takeover, kind
):
    data, task = dorm_takeover
    task.type = kind
    before = deepcopy(
        (vars(task), {name: vars(op) for name, op in data.operators.items()})
    )

    result = build_task_presentation(task, data)

    assert result["title"] == "桑葚休息；砾转为空闲"
    assert result["actions"] == [
        {"kind": "operator", "subject": "桑葚", "action": "休息"},
        {"kind": "operator", "subject": "砾", "action": "转为空闲"},
    ]
    assert before == (
        vars(task),
        {name: vars(op) for name, op in data.operators.items()},
    )
    data.project_arrangements.assert_not_called()


@pytest.mark.parametrize("target", ["Free", "", "_"])
def test_any_unresolved_selection_in_the_plan_prevents_idle_inference(
    dorm_takeover, target
):
    data, task = dorm_takeover
    task.plan["meeting"] = [target, "红"]
    assert not any(
        action["action"] == "转为空闲"
        for action in build_task_presentation(task, data)["actions"]
    )


@pytest.mark.parametrize("destination", ["same_dorm", "other_dorm", "work"])
def test_an_explicit_resident_destination_is_not_misreported_as_idle(
    dorm_takeover, destination
):
    data, task = dorm_takeover
    if destination == "same_dorm":
        task.plan["dormitory_1"][3] = "砾"
    elif destination == "other_dorm":
        task.plan["dormitory_2"] = ["Current", "Current", "砾", "Current", "Current"]
    else:
        task.plan["meeting"] = ["砾", "Current"]
    assert {
        "kind": "operator",
        "subject": "砾",
        "action": "转为空闲",
    } not in build_task_presentation(task, data)["actions"]


@pytest.mark.parametrize(
    "condition",
    [
        "unknown_current",
        "ambiguous_current",
        "current_is_moved",
        "ambiguous_resident",
        "short_plan",
    ],
)
def test_unknown_or_moved_preserved_positions_do_not_prove_a_resident_becomes_idle(
    dorm_takeover, condition
):
    data, task = dorm_takeover
    if condition == "unknown_current":
        data.operators["杜林"].current_room = None
    elif condition == "ambiguous_current":
        data.operators["阿米娅"] = Operator(
            "阿米娅", "", current_room="dormitory_1", current_index=0
        )
    elif condition == "current_is_moved":
        task.plan["dormitory_2"] = ["Current", "Current", "杜林", "Current", "Current"]
    elif condition == "ambiguous_resident":
        data.operators["阿米娅"] = Operator(
            "阿米娅", "", current_room="dormitory_1", current_index=2
        )
    else:
        task.plan["dormitory_1"] = ["Current", "桑葚"]
    assert not any(
        action["subject"] == "砾" and action["action"] == "转为空闲"
        for action in build_task_presentation(task, data)["actions"]
    )


@pytest.mark.parametrize(
    "room,index",
    [
        ("dormitory_1", -1),
        ("dormitory_1", 5),
        ("dormitory_1", None),
        ("dormitory_1", True),
        ("dormitory_5", 2),
        (None, 2),
    ],
)
def test_unknown_or_illegal_resident_positions_are_not_idle_actions(
    dorm_takeover, room, index
):
    data, task = dorm_takeover
    data.operators["砾"].current_room, data.operators["砾"].current_index = room, index
    assert not any(
        action["subject"] == "砾" and action["action"] == "转为空闲"
        for action in build_task_presentation(task, data)["actions"]
    )


@pytest.mark.parametrize(
    "pre_plan",
    [
        {"meeting": ["砾", "Current"]},
        {"dormitory_2": ["杜林"]},
        {"dormitory_1": ["Free"]},
        {"meeting": ["陈", "Current"]},
    ],
)
def test_predecessors_do_not_predict_future_idle_or_current_occupants(
    dorm_takeover, pre_plan
):
    data, task = dorm_takeover
    predecessor = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=pre_plan)
    result = build_task_presentation(task, data, predecessors=(predecessor,))
    assert result["title"] == "桑葚休息"
    assert not any(action["action"] == "转为空闲" for action in result["actions"])
    data.project_arrangements.assert_not_called()


def test_group_coverage_does_not_repeat_a_member_as_becoming_idle(dorm_takeover):
    data, task = dorm_takeover
    data.operators["砾"].group = "轮换"
    data.operators["年"] = Operator("年", "", current_room="", group="轮换")
    data.groups["轮换"] = ["砾", "年"]
    data.group_shift_state["轮换"] = False
    task.group_shift_transitions = {"轮换": True}
    result = build_task_presentation(task, data)
    assert result["title"] == "轮换下班；桑葚休息"
    assert not any(action["action"] == "转为空闲" for action in result["actions"])


def test_rests_and_idle_residents_merge_by_action_after_existing_work_departures(
    dorm_takeover,
):
    data, task = dorm_takeover
    task.plan["dormitory_1"][3] = "夜莺"
    task.plan["meeting"] = ["陈", "Current"]
    result = build_task_presentation(task, data)
    assert result["title"] == "陈上班；鸿雪下班；桑葚、夜莺休息；砾、爱丽丝转为空闲"


def test_specialized_task_and_refresh_target_keep_their_real_purpose():
    data = SimpleNamespace(facility_states={"room_2_1": {"facility": "trade"}})
    task = SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data="room_2_1")
    result = build_task_presentation(task, data)
    assert result["title"] == "刷新跑单时间"
    assert result["targets"] == [{"id": "room_2_1", "label": "贸易站 B201"}]
    assert result["rooms"] == []
    task.type = TaskTypes.RUN_ORDER
    task.plan = {"room_2_1": ["Current", "甲"]}
    assert build_task_presentation(task, data)["title"] == "跑单"


def test_fiammetta_title_uses_the_explicit_beneficiary_without_changing_the_roster():
    task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={"dormitory_2": ["伊内丝", "菲亚梅塔"]},
        meta_data="伊内丝",
    )
    before = deepcopy(vars(task))

    result = build_task_presentation(task, None)

    assert result["title"] == "肥鸭 充 伊内丝"
    assert result["rooms"] == [
        {
            "id": "dormitory_2",
            "label": "宿舍2",
            "agents": ["伊内丝", "菲亚梅塔"],
        }
    ]
    assert result["actions"] == []
    assert vars(task) == before


@pytest.mark.parametrize(
    ("plan", "target"),
    [
        ({}, ""),
        ({"dormitory_2": ["伊内丝", "菲亚梅塔"]}, ""),
        ({"dormitory_2": ["塑心", "冰酿", "泥岩", "菲亚梅塔", "年"]}, ""),
        ({"dormitory_2": ["伊内丝", "菲亚梅塔"]}, "年"),
        ({"dormitory_2": ["伊内丝"]}, "伊内丝"),
        ({"dormitory_2": ["伊内丝"], "dormitory_3": ["菲亚梅塔"]}, "伊内丝"),
        ({"meeting": ["伊内丝", "菲亚梅塔"]}, "伊内丝"),
        ({"dormitory_2": ["Current", "菲亚梅塔"]}, "Current"),
        ({"dormitory_2": ["菲亚梅塔"]}, "菲亚梅塔"),
    ],
)
def test_fiammetta_reservations_and_restorations_do_not_guess_a_beneficiary(
    plan, target
):
    task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, task_plan=plan, meta_data=target
    )

    assert build_task_presentation(task, None)["title"] == "肥鸭"


@pytest.mark.parametrize(
    ("task_type", "title"),
    [
        (TaskTypes.SWAP_SUPPORT, "自动专精换协助位"),
        (TaskTypes.SKILL_UPGRADE, "自动专精"),
    ],
)
def test_mastery_task_presentation_names_the_automatic_action_without_changing_dispatch(
    task_type, title
):
    task = SchedulerTask(
        task_type=task_type, meta_data="阿米娅 三技能·奇美拉 专二 → 专三"
    )
    assert build_task_presentation(task, None)["title"] == title
    assert task.type is task_type
    assert task.meta_data == "阿米娅 三技能·奇美拉 专二 → 专三"


def test_backup_names_are_captured_for_pending_changes_not_inferred_from_current_config():
    data = SimpleNamespace(
        plan_condition=[True, False],
        backup_plans=[SimpleNamespace(name="白班"), SimpleNamespace(name="夜班")],
    )
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"central": ["甲"]}
    )
    task.backup_shift_conditions = [False, True]
    remember_backup_changes(task, data, [True, False], [False, True])
    data.backup_plans[0].name = "改名后的白班"
    snapshot = build_task_presentation(task, data)
    assert snapshot["backups"] == [
        {"name": "白班", "active": False},
        {"name": "夜班", "active": True},
    ]
    text = format_task_log_message(snapshot, "休息至 19:42:00")
    assert "预计激活的副表：夜班" in text
    assert "预计停用的副表：白班" in text
    assert "已激活" not in text
    task.backup_shift_active = True
    assert build_task_presentation(task, data)["backups"] == []


def test_another_task_activating_the_same_backup_removes_the_pending_announcement():
    data = SimpleNamespace(
        plan_condition=[False], backup_plans=[SimpleNamespace(name="夜班")]
    )
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    task.backup_shift_conditions = [True]
    remember_backup_changes(task, data, [False], [True])
    data.plan_condition = [True]
    assert build_task_presentation(task, data)["backups"] == []
    assert task.log_backup_changes == [{"name": "夜班", "active": True}]
    assert data.plan_condition == [True]


def test_rest_announces_one_complete_snapshot_after_round_end(
    production_idle_scheduler, caplog
):
    state = production_idle_scheduler
    instance = state.solver
    instance.tasks[0].plan = {"room_3_3": ["埃癸斯"]}
    instance.op_data.facility_states = {"room_3_3": {"facility": "power"}}
    instance._idle_sleep = Mock()
    instance.handle_idle_action = Mock()
    before = deepcopy(instance.tasks[0].plan)
    with caplog.at_level(logging.INFO):
        instance.rest_until_next_task()
    forecasts = [record for record in caplog.records if hasattr(record, "log_task")]
    assert len(forecasts) == 1
    snapshot = forecasts[0].log_task
    assert (
        snapshot["header"]
        == f"休息 10 分，至 {instance.tasks[0].time:%H:%M:%S}，随后执行「安排干员」"
    )
    assert snapshot["rooms"] == [
        {"id": "room_3_3", "label": "发电站 B303", "agents": ["埃癸斯"]}
    ]
    assert "发电站 B303：埃癸斯" in forecasts[0].getMessage()
    assert not any(
        record.getMessage().startswith("下一次任务:") for record in caplog.records
    )
    assert instance.task_count == 1
    assert instance.tasks[0].plan == before
    instance._idle_sleep.assert_called_once()


def test_rest_forecast_keeps_a_real_unplanned_exhaust_task_after_the_wait(
    production_idle_scheduler, caplog
):
    instance = production_idle_scheduler.solver
    first = instance.tasks[0]
    first.type = TaskTypes.EXHAUST_OFF
    first.meta_data = "陈"
    clock = production_idle_scheduler.clock
    clock.current = clock.current.replace(
        month=11, day=5, hour=12, minute=2, second=38, microsecond=0
    )
    first.time = clock.now() + timedelta(minutes=28, seconds=55)
    instance.tasks = [first]
    instance._idle_sleep = Mock()
    instance.handle_idle_action = Mock()
    before = deepcopy(vars(first))

    with caplog.at_level(logging.INFO):
        instance.rest_until_next_task()

    forecasts = [record for record in caplog.records if hasattr(record, "log_task")]
    assert len(forecasts) == 1
    assert forecasts[0].log_task["title"] == "用尽下班"
    assert forecasts[0].log_agents == ["陈"]
    assert (
        forecasts[0].getMessage()
        == "休息 28 分 55 秒，至 12:31:33，随后执行「用尽下班」，目标干员：[[operator:陈]]"
    )
    assert forecasts[0].log_task["wait_seconds"] == 1735
    assert forecasts[0].log_task["rooms"] == []
    assert vars(first) == before
    instance._idle_sleep.assert_called_once()


@pytest.mark.parametrize(
    ("kind", "metadata", "title"),
    [
        (TaskTypes.SHIFT_ON, "", "上班"),
        (TaskTypes.SHIFT_OFF, "", "下班"),
        (TaskTypes.EXHAUST_OFF, "陈,阿米娅", "用尽下班"),
        (TaskTypes.NOT_SPECIFIC, "本地刷关阈值复查", "本地刷关阈值复查"),
    ],
)
def test_unplanned_task_keeps_its_real_label_without_inventing_movements(
    kind, metadata, title
):
    task = SchedulerTask(task_type=kind, meta_data=metadata)
    before = deepcopy(vars(task))
    snapshot = build_task_presentation(task, None)
    assert snapshot["title"] == title
    assert snapshot["rooms"] == []
    assert snapshot["actions"] == []
    assert vars(task) == before


def test_rest_keeps_the_named_group_action_inside_the_next_task_forecast(
    production_idle_scheduler, caplog
):
    instance = production_idle_scheduler.solver
    first = instance.tasks[0]
    first.plan = {"central": ["阿米娅", "凯尔希"]}
    first.group_shift_transitions = {"红松": False}
    data = instance.op_data
    data.groups = {"红松": ["阿米娅", "凯尔希"]}
    data.group_shift_state = {"红松": True}
    data.operators = {
        name: Operator(
            name,
            "central",
            group="红松",
            index=index,
            current_room="dormitory_1",
            current_index=index,
        )
        for index, name in enumerate(("阿米娅", "凯尔希"))
    }
    before = deepcopy(
        (first.plan, first.group_shift_transitions, data.group_shift_state)
    )
    instance._idle_sleep = Mock()
    instance.handle_idle_action = Mock()

    with caplog.at_level(logging.INFO):
        instance.rest_until_next_task()

    forecasts = [record for record in caplog.records if hasattr(record, "log_task")]
    assert len(forecasts) == 1
    snapshot = forecasts[0].log_task
    assert (
        snapshot["header"]
        == f"休息 10 分，至 {first.time:%H:%M:%S}，随后执行「红松上班」"
    )
    assert snapshot["actions"] == [
        {
            "kind": "group",
            "subject": "红松",
            "action": "上班",
            "members": ["阿米娅", "凯尔希"],
        }
    ]
    assert forecasts[0].getMessage().splitlines() == [
        snapshot["header"],
        "控制中枢：阿米娅、凯尔希",
    ]
    assert not any(record.getMessage() == "红松上班" for record in caplog.records)
    assert before == (first.plan, first.group_shift_transitions, data.group_shift_state)
    instance._idle_sleep.assert_called_once()


def test_cross_day_forecast_uses_the_task_table_time_and_preserves_email_offset(
    production_idle_scheduler, monkeypatch, caplog
):
    from arknights_mower.solvers import base_schedule as base

    state = production_idle_scheduler
    instance = state.solver
    first = instance.tasks[0]
    state.clock.current = state.clock.now().replace(hour=23, minute=59, second=50)
    first.time = state.clock.now() + timedelta(seconds=20)
    instance.tasks = [first]
    instance._idle_sleep = Mock()
    instance.handle_idle_action = Mock(
        side_effect=lambda _: setattr(
            state.clock, "current", state.clock.now() + timedelta(seconds=6)
        )
    )
    monkeypatch.setattr(base.config.conf, "timezone_offset", 3)
    with caplog.at_level(logging.INFO):
        instance.rest_until_next_task()
    snapshot = next(
        record.log_task for record in caplog.records if hasattr(record, "log_task")
    )
    assert (
        snapshot["header"]
        == f"休息 14 秒，至 {first.time:%m-%d %H:%M:%S}，随后执行「上班」"
    )
    assert snapshot["wait_seconds"] == (first.time - state.clock.now()).total_seconds()
    assert (
        first.format(3).time.strftime("%H:%M:%S") in base.send_message.call_args.args[1]
    )


@pytest.mark.parametrize(
    ("until_seconds", "idle_seconds", "expected_seconds", "duration"),
    [
        (600, 221, 379, "6 分 19 秒"),
        (600, 601, 0, "0 秒"),
        (61, 0, 61, "1 分 1 秒"),
        (3723, 0, 3723, "1 小时 2 分 3 秒"),
        (3600, 0, 3600, "1 小时"),
    ],
)
def test_visible_wait_duration_uses_log_time_without_changing_sleep_or_notification(
    production_idle_scheduler,
    caplog,
    until_seconds,
    idle_seconds,
    expected_seconds,
    duration,
):
    from arknights_mower.solvers import base_schedule as base

    state = production_idle_scheduler
    instance = state.solver
    first = instance.tasks[0]
    first.time = state.clock.now() + timedelta(seconds=until_seconds)
    instance.tasks = [first]
    first.type = TaskTypes.RUN_ORDER
    instance._idle_sleep = Mock()
    instance.handle_idle_action = Mock(
        side_effect=lambda _: setattr(
            state.clock, "current", state.clock.now() + timedelta(seconds=idle_seconds)
        )
    )

    with caplog.at_level(logging.INFO):
        instance.rest_until_next_task()

    forecasts = [record for record in caplog.records if hasattr(record, "log_task")]
    assert len(forecasts) == 1
    snapshot = forecasts[0].log_task
    assert snapshot["header"] == (
        f"休息 {duration}，至 {first.time:%H:%M:%S}，随后执行「跑单」"
    )
    assert snapshot["wait_seconds"] == expected_seconds
    assert snapshot["wait_seconds"] == max(
        0, (first.time - state.clock.now()).total_seconds()
    )
    assert forecasts[0].getMessage() == snapshot["header"]
    instance.handle_idle_action.assert_called_once_with(until_seconds)
    instance._idle_sleep.assert_called_once_with(until_seconds, round_end=True)
    if until_seconds == 600:
        assert base.send_message.call_args.args[1].startswith("休息 10 分钟，")


def test_round_stop_prevents_any_forecast(production_idle_scheduler, caplog):
    from arknights_mower.utils.csleep import MowerExit

    instance = production_idle_scheduler.solver
    instance._stop_after_round = Mock(side_effect=MowerExit)
    instance.handle_idle_action = Mock()
    with caplog.at_level(logging.INFO), pytest.raises(MowerExit):
        instance.rest_until_next_task()
    assert not any(hasattr(record, "log_task") for record in caplog.records)
    assert not any(record.getMessage().startswith("休息 ") for record in caplog.records)


@pytest.mark.parametrize("failed", [False, True])
def test_backup_completion_message_only_follows_successful_activation(
    monkeypatch, caplog, failed
):
    from arknights_mower.solvers import base_schedule as base

    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        plan_condition=[True, False],
        backup_group="default",
        operators={},
        backup_plans=[SimpleNamespace(name="白班"), SimpleNamespace(name="夜班")],
    )
    instance._initial_mood_read_pending = Mock(return_value=False)
    instance._advance_orders_before_maintenance = Mock(return_value=False)
    instance._exhaust_task_signatures = Mock(return_value={})
    instance._capture_shift_refresh_rules = Mock()
    instance._invalidate_changed_exhaust_tasks = Mock(return_value=False)
    instance._sync_run_order_tasks = Mock()
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    task.backup_shift_conditions = [False, True]

    def swap(conditions, **kwargs):
        if failed and conditions == [False, True]:
            return "不允许切换"
        instance.op_data.plan_condition = list(conditions)
        return None

    instance.op_data.swap_plan = swap
    with caplog.at_level(logging.INFO):
        if failed:
            with pytest.raises(ValueError):
                instance._activate_shift_backup(task)
        else:
            instance._activate_shift_backup(task)
    completed = [
        record.getMessage()
        for record in caplog.records
        if "已激活的副表：" in record.getMessage()
    ]
    assert completed == ([] if failed else ["已激活的副表：夜班；已停用的副表：白班"])


def test_mixed_primary_return_and_unbound_replacements_rest_together(solver):
    data = solver.op_data
    data.operators[A].group = ""
    data.operators[A]._current_room = "dormitory_3"
    data.operators[A].current_index = 4
    for index, name in enumerate(("白面鸮", "赫默")):
        data.operators[name] = Operator(
            name, "", current_room="room_1_1", current_index=index
        )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            "dormitory_1": ["Current", "Current", "Current", "Current", "白面鸮"],
            "dormitory_2": ["Current", "Current", "Current", "Current", "赫默"],
            "meeting": [A, "Current"],
        },
    )
    task.group_shift_transitions = {}
    result = build_task_presentation(task, data)
    assert result["title"] == f"{A}上班；白面鸮、赫默休息"
    assert result["actions"] == [
        {"kind": "operator", "subject": A, "action": "上班"},
        {"kind": "operator", "subject": "白面鸮", "action": "休息"},
        {"kind": "operator", "subject": "赫默", "action": "休息"},
    ]
    assert "莱茵" not in result["title"]


def test_dorm_moves_stationary_managers_and_unknown_sources_are_not_new_rest(solver):
    data = solver.op_data
    for name, current in (("白面鸮", "dormitory_2"), ("赫默", None)):
        data.operators[name] = Operator(name, "", current_room=current, current_index=4)
    task = SchedulerTask(
        task_type=TaskTypes.RE_ORDER,
        task_plan={"dormitory_1": ["塑心", "Current", "白面鸮", "赫默", "Free"]},
    )
    task.group_shift_transitions = {}
    result = build_task_presentation(task, data)
    assert result["title"] == "宿舍排序"
    assert result["actions"] == []


def test_group_name_is_preserved_and_complete_dorm_entry_is_rest(solver):
    data = solver.op_data
    data.groups["红松"] = [A]
    data.operators[A].group = "红松"
    # 保留一个共享成员，避免把该组误当作单人组。
    data.operators[SHARED].group_bindings[0]["group"] = "红松"
    data.group_shift_state["红松"] = False
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"dormitory_1": ["Current", "Current", A, SHARED, "Free"]},
    )
    task.group_shift_transitions = {"红松": True}
    result = build_task_presentation(task, data)
    assert result["title"] == "红松休息"
    assert result["actions"] == [
        {
            "kind": "group",
            "subject": "红松",
            "action": "休息",
            "members": [A, SHARED],
        }
    ]
    data.group_shift_state["红松"] = True
    task.group_shift_transitions = {"红松": False}
    task.plan = {"meeting": [A, "Current"], "contact": [SHARED]}
    result = build_task_presentation(task, data)
    assert result["title"] == "红松上班"
    assert result["actions"] == [
        {
            "kind": "group",
            "subject": "红松",
            "action": "上班",
            "members": [A, SHARED],
        }
    ]


def test_explicit_workstation_departure_does_not_claim_dorm_rest(solver):
    data = solver.op_data
    data.operators[A].group = ""
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"meeting": ["陈", "Current"]}
    )
    task.group_shift_transitions = {}
    result = build_task_presentation(task, data)
    assert result["title"] == f"陈上班；{A}下班"
    assert result["actions"] == [
        {"kind": "operator", "subject": "陈", "action": "上班"},
        {"kind": "operator", "subject": A, "action": "下班"},
    ]


@pytest.mark.parametrize("target", ["", "_", "Current", "Free"])
def test_unresolved_workstation_target_does_not_claim_departure(solver, target):
    data = solver.op_data
    data.operators[A].group = ""
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"meeting": [target, "Current"]}
    )
    task.group_shift_transitions = {}

    result = build_task_presentation(task, data)

    assert result["title"] == task.display_name
    assert result["actions"] == []
    assert result["rooms"][0]["agents"] == [target, "Current"]
