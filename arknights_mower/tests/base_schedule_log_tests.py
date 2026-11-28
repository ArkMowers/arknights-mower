"""副表预演与设施观察在页面保留摘要，内部安排和重复读数留在 DEBUG。"""

import logging
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import (
    backup_snapshot_tests,
    dorm_recovery_tests,
    training_observation_retry_tests,
)
from arknights_mower.tests.choose_agent_filter_tests import RESIDENTS, selection_solver
from arknights_mower.tests.dorm_admission_priority_tests import op_data as op_data
from arknights_mower.tests.dorm_admission_priority_tests import residents as residents
from arknights_mower.tests.manufacture_product_switch_tests import (
    product_plan,
    trade_plan,
)
from arknights_mower.tests.shift_backup_convergence_tests import downshift, positions
from arknights_mower.tests.shift_backup_convergence_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.scheduler_task import rebalance_plan_swap_dorms

pytestmark = pytest.mark.usefixtures("offline_maintenance")
backup_solver = backup_snapshot_tests.solver
dorm_solver = dorm_recovery_tests.solver
training_mood_solver = training_observation_retry_tests.solver


def records(caplog, level):
    return [record for record in caplog.records if record.levelno == level]


@pytest.mark.parametrize(
    ("facility", "label"),
    [
        ("manufacture", "制造站 B202"),
        ("trade", "贸易站 B202"),
        ("power", "发电站 B202"),
    ],
)
def test_room_mood_observation_keeps_names_and_readings_without_a_python_list(
    caplog, facility, label
):
    caplog.set_level(logging.INFO)
    room = "room_2_2"
    observed = [
        {"agent": "砾", "mood": 18.968123},
        {"agent": "斑点", "mood": 0},
        {"agent": "清流", "mood": 24.0},
    ]
    original = deepcopy(observed)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        plan={room: [None] * 3},
        true_exhaust_room={room},
        facility_states={room: {"facility": facility}},
    )
    instance.get_agent_from_room = MagicMock(return_value=observed)

    result = instance._read_room_mood(room, force_mood=True, strict_observation=True)

    assert result is observed
    assert observed == original
    instance.get_agent_from_room.assert_called_once_with(
        room, [0, 1, 2], force_mood=True, strict_observation=True
    )
    messages = records(caplog, logging.INFO)
    assert len(messages) == 1
    assert messages[0].getMessage() == (
        f"{label}：[[operator:砾]]（心情18.968）、"
        "[[operator:斑点]]（心情0）、[[operator:清流]]（心情24.0）"
    )
    assert messages[0].log_room == room
    assert messages[0].log_agents == ["砾", "斑点", "清流"]


def test_room_mood_observation_distinguishes_vacancy_from_unrecognized_slots(caplog):
    caplog.set_level(logging.INFO)
    room = "dormitory_1"
    observed = [
        {"agent": "砾", "mood": 18.968},
        {"agent": "", "mood": 24},
        {"agent": "", "mood": 24, "observed": False},
    ]
    original = deepcopy(observed)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(plan={room: [None] * 3}, true_exhaust_room={})
    instance.get_agent_from_room = MagicMock(return_value=observed)

    assert instance._read_room_mood(room) is observed

    assert observed == original
    instance.get_agent_from_room.assert_called_once_with(room, None)
    messages = records(caplog, logging.INFO)
    assert len(messages) == 1
    assert messages[0].getMessage() == (
        "宿舍1：[[operator:砾]]（心情18.968）、第2位空位、第3位干员未识别"
    )
    assert messages[0].log_agents == ["砾"]
    assert messages[0].log_room == room


@pytest.mark.parametrize("enabled", [False, True])
def test_training_patrol_uses_the_same_readable_mood_observation(
    training_mood_solver, monkeypatch, caplog, enabled
):
    from arknights_mower.solvers import mastery_reader

    caplog.set_level(logging.INFO)
    instance = training_mood_solver
    monkeypatch.setattr(config.conf, "enable_mastery", enabled)
    observed = [{"agent": "艾丽妮", "mood": 17.12654}, {"agent": "", "mood": -1}]
    original = deepcopy(observed)
    state = mastery_reader.RoomState("empty", slots_read=True, slots_reliable=True)
    reader = MagicMock(return_value=(state, observed) if enabled else state)
    monkeypatch.setattr(mastery_reader, "read_room_state", reader)
    instance.get_agent_from_room = MagicMock(return_value=observed)

    instance._read_agent_mood()

    assert observed == original
    reader.assert_called_once_with(
        instance, enter=False, **({"want_mood": True} if enabled else {})
    )
    if enabled:
        instance.get_agent_from_room.assert_not_called()
        mastery_reader.reconcile_short.assert_called_once_with(
            instance, state, defer_collect=False
        )
    else:
        instance.get_agent_from_room.assert_called_once_with("train", None)
        mastery_reader.reconcile_short.assert_not_called()
    instance.enter_room.assert_called_once_with("train", max_attempts=1)
    instance.back.assert_called_once_with()
    messages = records(caplog, logging.INFO)
    assert len(messages) == 1
    assert messages[0].getMessage() == (
        "训练室：[[operator:艾丽妮]]（心情17.127）、第2位空位"
    )
    assert messages[0].log_agents == ["艾丽妮"]
    assert messages[0].log_room == "train"


@pytest.mark.parametrize("complete", [False, True])
def test_converged_plan_logs_a_complete_snapshot_without_claiming_execution(
    solver, caplog, complete
):
    caplog.set_level(logging.DEBUG)
    solver.op_data.backup_plans[0].name = "夜班"
    task = downshift(solver)
    before = positions(solver.op_data)
    deadline = task.time

    if complete:
        solver._prepare_shift_cycle(task)
        prefix = "完整换班计划已确定"
        raw = "完整换班收敛："
    else:
        solver._prepare_shift_backup(task)
        prefix = "上下班副表预演已收敛"
        raw = "上下班副表预演收敛："

    summaries = [
        record
        for record in records(caplog, logging.INFO)
        if record.getMessage().startswith(prefix)
    ]
    assert len(summaries) == 1
    summary = summaries[0]
    assert (
        summary.getMessage().splitlines()[0] == f"{prefix}，涉及{len(task.plan)}处设施"
    )
    snapshot = deepcopy(summary.log_task)
    assert snapshot["header"] == summary.getMessage().splitlines()[0]
    assert [(room["id"], room["agents"]) for room in snapshot["rooms"]] == list(
        task.plan.items()
    )
    assert any("Current" in room["agents"] for room in snapshot["rooms"])
    assert snapshot["backups"] == [{"name": "夜班", "active": True}]
    assert "actions" in snapshot and "targets" in snapshot
    for room in snapshot["rooms"]:
        assert f"{room['label']}：{'、'.join(room['agents'])}" in summary.getMessage()
    assert positions(solver.op_data) == before
    assert solver.op_data.plan_condition == [False]
    assert task.time == deadline
    assert any(
        record.getMessage().startswith(raw) for record in records(caplog, logging.DEBUG)
    )
    assert not any(
        record.getMessage().startswith(raw) for record in records(caplog, logging.INFO)
    )
    assert (
        len(
            [
                record
                for record in records(caplog, logging.INFO)
                if "副表收敛演算耗时" in record.getMessage()
            ]
        )
        == 1
    )

    solver.op_data.backup_plans[0].name = "改名后的副表"
    task.plan.clear()
    assert summary.log_task == snapshot


def test_dorm_rebalance_keeps_its_intermediate_lists_at_debug(residents, caplog):
    caplog.set_level(logging.DEBUG)

    assert rebalance_plan_swap_dorms(residents) == {}

    messages = [
        record
        for record in caplog.records
        if record.getMessage().startswith("副表切换后重排宿舍：")
    ]
    assert len(messages) == 1
    assert messages[0].levelno == logging.DEBUG
    assert "银灰" in messages[0].getMessage()


@pytest.mark.parametrize("standalone", [False, True])
def test_successful_backup_activation_records_the_names_as_a_snapshot(
    solver, backup_solver, caplog, standalone
):
    caplog.set_level(logging.INFO)
    instance = backup_solver if standalone else solver
    instance.op_data.backup_plans[0].name = "夜班"
    if standalone:
        instance.op_data.operators["伊内丝"].mood = 5
        instance.backup_plan_solver()
    else:
        task = downshift(instance)
        instance._prepare_shift_backup(task)
        instance._activate_shift_backup(task)

    events = [record for record in caplog.records if hasattr(record, "log_backups")]
    assert len(events) == 1
    assert events[0].getMessage() == "已激活的副表：夜班"
    assert events[0].log_backups == [{"name": "夜班", "active": True}]
    instance.op_data.backup_plans[0].name = "改名后的副表"
    assert events[0].log_backups == [{"name": "夜班", "active": True}]


@pytest.mark.parametrize(
    ("facility", "readings", "product", "description"),
    [
        ("manufacture", ["赤金"], "gold", "识别产物为赤金，已更新设施状态记录"),
        (
            "manufacture",
            ["中级作战记录"],
            "exp3",
            "识别产物为中级作战记录，已更新设施状态记录",
        ),
        (
            "manufacture",
            ["源石碎片", "固源岩"],
            "orirock",
            "识别产物为源石碎片（固源岩），已更新设施状态记录",
        ),
        (
            "manufacture",
            ["源石碎片", "装置"],
            "orirock_device",
            "识别产物为源石碎片（装置），已更新设施状态记录",
        ),
        ("trade", ["龙门商法"], "lmd", "识别订单类型为龙门商法，已更新设施状态记录"),
        (
            "trade",
            ["开采协力"],
            "orundum",
            "识别订单类型为开采协力，已更新设施状态记录",
        ),
        ("trade", ["3级后可切换"], "lmd", "识别订单类型为龙门商法，已更新设施状态记录"),
    ],
)
def test_current_page_observation_has_one_facility_info_and_debug_readings(
    monkeypatch, caplog, facility, readings, product, description
):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    room, plan = product_plan() if facility == "manufacture" else trade_plan()
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = Operators(plan)
    instance.recog = SimpleNamespace(w=1920, h=1080)
    instance._product_ocr_text = MagicMock(side_effect=readings * 2)
    instance.scene_graph_navigation = MagicMock()
    instance.enter_room = MagicMock()

    instance._cache_facility_state_from_current_page(room, facility)

    observed = records(caplog, logging.INFO)
    assert len(observed) == 1
    label = "制造站 B102" if facility == "manufacture" else "贸易站 B101"
    assert observed[0].getMessage() == f"{label}：{description}"
    assert observed[0].log_room == room
    assert instance.op_data.facility_product(room) == product
    assert any(
        "识别到当前" in record.getMessage() for record in records(caplog, logging.DEBUG)
    )
    instance.scene_graph_navigation.assert_not_called()
    instance.enter_room.assert_not_called()

    instance._cache_facility_state_from_current_page(room, facility)
    assert len(records(caplog, logging.INFO)) == 2


def test_unreadable_product_keeps_the_warning_without_a_success_summary(
    monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    room, plan = product_plan()
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = Operators(plan)
    instance.recog = SimpleNamespace(w=1920, h=1080)
    instance._product_ocr_text = MagicMock(return_value="无法识别的文字")

    instance._cache_facility_state_from_current_page(room, "manufacture")

    assert records(caplog, logging.INFO) == []
    warnings = records(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert "设施状态失败" in warnings[0].getMessage()


@pytest.mark.parametrize(
    "outcome", ["confirmed", "unknown_product", "cached_mood", "interrupted"]
)
@pytest.mark.parametrize(
    ("facility", "room_label", "previous", "observed", "reading", "subject", "panel"),
    [
        ("manufacture", "制造站 B102", "gold", "exp3", "中级作战记录", "产物", None),
        ("manufacture", "制造站 B102", "gold", "exp3", "中级作战记录", "产物", "open"),
        ("trade", "贸易站 B101", "lmd", "orundum", "开采协力", "订单类型", "closed"),
        ("trade", "贸易站 B101", "lmd", "orundum", "开采协力", "订单类型", "open"),
    ],
    ids=["manufacture", "manufacture-open", "trade-closed", "trade-open"],
)
def test_mood_patrol_updates_one_facility_observation(
    monkeypatch,
    caplog,
    outcome,
    facility,
    room_label,
    previous,
    observed,
    reading,
    subject,
    panel,
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    room, plan = product_plan() if facility == "manufacture" else trade_plan()
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.task = None
    instance.tasks = []
    instance.op_data = Operators(plan)
    instance.op_data.update_facility_state(room, facility, previous)
    name = "Lancet-2"
    operator = Operator(name, room, current_room=room, current_index=0, mood=20)
    operator.need_to_refresh = MagicMock(return_value=False)
    instance.op_data.add(operator)
    instance.op_data.update_detail = MagicMock(return_value=None)
    instance.recog = SimpleNamespace(w=1920, h=1080, gray=MagicMock())
    instance.detect_room_type = MagicMock(return_value=room_label.split()[0])
    instance._work_room_panel = MagicMock(return_value=panel)
    instance._visible_manufacture_product = MagicMock(return_value=None)
    instance._wait_drone_interface = MagicMock()
    instance._product_ocr_text = MagicMock(
        return_value="无法识别的文字" if outcome == "unknown_product" else reading
    )
    in_room = False

    def return_to_room(*args, **kwargs):
        nonlocal in_room
        assert not in_room
        in_room = True
        base.logger.info("进入设施详情")

    instance.scene_graph_navigation = MagicMock(side_effect=return_to_room)
    instance.back = MagicMock(side_effect=return_to_room)
    instance.detect_room = MagicMock(
        side_effect=lambda: (
            room
            if in_room
            or (facility == "manufacture" and instance._wait_drone_interface.called)
            else ""
        )
    )
    instance._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    instance.turn_on_room_detail = MagicMock()
    instance.wait_product_complete = MagicMock()
    instance.find = MagicMock(
        side_effect=lambda resource, **_: in_room and resource == "arrange_check_in"
    )
    instance.read_screen = MagicMock(return_value=name)

    def measure(_):
        instance._wait_drone_interface.assert_not_called()
        assert [
            record.log_event["phase"]
            for record in records(caplog, logging.INFO)
            if hasattr(record, "log_event")
        ] == ["started"]
        if outcome == "interrupted":
            raise base.RecognizeError("干员心情读取失败")
        return 16.1236

    instance.read_accurate_mood = MagicMock(side_effect=measure)
    if outcome == "interrupted":
        with pytest.raises(base.RecognizeError, match="干员心情读取失败"):
            instance._read_room_mood(room, force_mood=True)
    else:
        assert (
            instance._read_room_mood(room, force_mood=outcome != "cached_mood")[0][
                "agent"
            ]
            == name
        )

    start, *navigation, end = records(caplog, logging.INFO)
    assert start.log_event["id"] == end.log_event["id"]
    parent = {"type": "facility-observation", "id": start.log_event["id"]}
    assert start.log_parent == end.log_parent == parent
    interrupted_before_product = outcome == "interrupted"
    if interrupted_before_product:
        assert navigation == []
        instance._wait_drone_interface.assert_not_called()
    else:
        assert len(navigation) == 1 and navigation[0].log_parent == parent
        assert navigation[0].getMessage() == "进入设施详情"
        assert not hasattr(navigation[0], "log_event")
        instance._wait_drone_interface.assert_called_once()
    base.logger.info("继续巡检")
    assert not hasattr(records(caplog, logging.INFO)[-1], "log_parent")
    assert start.log_event["anchor"] and not end.log_event["anchor"]
    assert start.log_event["type"] == end.log_event["type"] == "facility-observation"
    assert start.log_event["phase"] == "started"
    assert start.log_event["summary"] == start.getMessage()
    assert end.log_event["summary"] == end.getMessage()
    state = (
        f"{subject}未确认" if outcome == "unknown_product" else f"{subject}为{reading}"
    )
    initial_state = "产物待确认，" if facility == "manufacture" else ""
    assert start.getMessage() == f"{room_label}：{initial_state}正在读取干员心情"
    expected_detail = {
        "cached_mood": f"[[operator:{name}]]（心情未实读）",
        "interrupted": "干员心情读取未完成",
    }.get(outcome, f"[[operator:{name}]]（心情16.124）")
    final_state = initial_state if interrupted_before_product else f"{state}，"
    assert end.getMessage() == f"{room_label}：{final_state}{expected_detail}"
    assert end.log_event["phase"] == (
        "failed" if outcome == "interrupted" else "completed"
    )
    assert (
        end.log_agents
        == end.log_event["agents"]
        == ([] if outcome == "interrupted" else [name])
    )
    assert instance.op_data.facility_states[room]["product"] == (
        previous
        if outcome == "unknown_product" or interrupted_before_product
        else observed
    )
    if outcome == "cached_mood":
        instance.read_accurate_mood.assert_not_called()
    instance._work_room_panel.assert_called_once_with(room)
    assert instance._visible_manufacture_product.call_count == (
        1 if facility == "manufacture" and not interrupted_before_product else 0
    )


@pytest.mark.parametrize(
    ("visible", "next_frame"),
    [("exp3", None), (None, None), (None, "same_room"), (None, "wrong_room")],
)
@pytest.mark.parametrize(
    "task_type", [base.TaskTypes.SELF_CORRECTION, base.TaskTypes.NOT_SPECIFIC]
)
@pytest.mark.parametrize("panel", ["open", "closed"])
def test_staffing_skips_even_visible_product_in_an_empty_factory(
    monkeypatch, visible, next_frame, task_type, panel
):
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = SimpleNamespace(type=task_type)
    solver.tasks = []
    solver.op_data = Operators(plan)
    solver.recog = SimpleNamespace(gray=MagicMock(), capture_started_at=1)
    events = []

    def visible_product():
        events.append("label")
        return visible

    def observe_panel(target):
        assert target == room
        events.append("panel")
        if solver.recog.capture_started_at == 2 and next_frame == "wrong_room":
            raise base.RecognizeError("房号不符")
        return panel if len(events) == 1 else "open"

    def find(resource, **kwargs):
        if resource == "infra_no_operator":
            events.append("slot")
            if next_frame:
                solver.recog.capture_started_at = 2
            return True
        return resource == "arrange_check_in"

    solver._work_room_panel = MagicMock(side_effect=observe_panel)
    solver._visible_manufacture_product = MagicMock(side_effect=visible_product)
    solver.detect_room_type = MagicMock(return_value="制造站")
    solver.detect_room = MagicMock(return_value=room)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.find = MagicMock(side_effect=find)
    solver._wait_drone_interface = MagicMock(
        side_effect=lambda **_: events.append("detail")
    )
    solver.read_manufacture_product = MagicMock(return_value="exp3")
    solver.back = MagicMock()
    observed = set()
    if next_frame == "wrong_room":
        with pytest.raises(base.RecognizeError, match="房号不符"):
            solver.get_agent_from_room(room, observed_facilities=observed)
        assert events == ["panel", "slot", "panel"]
        assert observed == set()
        solver._visible_manufacture_product.assert_not_called()
    else:
        result = solver.get_agent_from_room(room, observed_facilities=observed)
        assert [item["agent"] for item in result] == [""]
        expected = ["panel", "slot"]
        if next_frame:
            expected.append("panel")
        assert events == expected
        assert observed == set()
        assert solver.op_data.facility_states[room]["product"] is None
        solver._wait_drone_interface.assert_not_called()
        solver._visible_manufacture_product.assert_not_called()
    solver.detect_room_type.assert_called_once_with()


@pytest.mark.parametrize("panel", ["open", "closed"])
@pytest.mark.parametrize("level", [1, 3])
def test_mood_patrol_skips_order_type_for_empty_trade_room(
    monkeypatch, caplog, panel, level
):
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    room, plan = trade_plan()
    slots = plan["default_plan"].plan[room]
    slots.extend([slots[0]] * (level - 1))
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = None
    solver.op_data = Operators(plan)
    solver.op_data.facility_levels[room] = level
    if level == 1:
        solver.op_data.products.clear()
    solver.recog = SimpleNamespace(gray=None)
    solver.detect_room_type = MagicMock(return_value="贸易站")
    solver._work_room_panel = MagicMock(return_value=panel)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.find = MagicMock(side_effect=lambda name, **_: name == "infra_no_operator")
    solver._observed_trade_level = MagicMock(return_value=level)
    solver._wait_drone_interface = MagicMock()
    solver._read_trade_product_card = MagicMock(return_value=("orundum", True))
    solver.scene_graph_navigation = MagicMock()
    caplog.set_level(logging.INFO)

    assert [slot["agent"] for slot in solver._read_room_mood(room)] == [""] * level

    assert room in solver._confirmed_empty_work_rooms
    assert solver.op_data.facility_states[room]["product"] is None
    solver._observed_trade_level.assert_not_called()
    solver._wait_drone_interface.assert_not_called()
    solver._read_trade_product_card.assert_not_called()
    assert "订单类型" not in caplog.text
    assert "无人进驻，跳过订单读取" in caplog.text


@pytest.mark.parametrize("occupancy", [(1, 1), (2, 2), (1, 3), None])
def test_verified_trade_capacity_controls_strategy_read(monkeypatch, occupancy):
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    monkeypatch.setattr(base, "read_room_occupancy", lambda _: occupancy)
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = None
    solver.op_data = Operators(plan)
    solver.recog = SimpleNamespace(gray=None)
    solver._work_room_panel = MagicMock(return_value="open")
    solver.detect_room_type = MagicMock(return_value="贸易站")
    solver._read_trade_product_card = MagicMock(return_value=("orundum", True))
    solver._wait_drone_interface = MagicMock()
    solver.scene_graph_navigation = MagicMock()
    fixed_strategy = occupancy is not None and occupancy[1] < 3

    assert solver.refresh_facility_state(room)

    assert solver._wait_drone_interface.call_count == (0 if fixed_strategy else 1)
    assert solver._read_trade_product_card.call_count == (0 if fixed_strategy else 1)
    assert solver.op_data.facility_product(room) == (
        "lmd" if fixed_strategy else "orundum"
    )


@pytest.mark.parametrize("transition", ["open_panel", "retry_name"])
@pytest.mark.parametrize("unexpected", ["foreign_empty", "foreign_operator", "closed"])
def test_changed_panel_frame_cannot_write_another_rooms_slot(
    monkeypatch, transition, unexpected
):
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = SimpleNamespace(type=base.TaskTypes.SELF_CORRECTION)
    solver.tasks = []
    solver.op_data = Operators(plan)
    resident = Operator("Lancet-2", room, current_room=room, current_index=0, mood=18)
    visitor = Operator(
        "夜刀", "room_1_1", current_room="room_1_1", current_index=0, mood=14
    )
    solver.op_data.add(resident)
    solver.op_data.add(visitor)
    solver.op_data.update_detail = MagicMock()
    solver._reconcile_room_observation = MagicMock()
    original = object()
    solver.recog = SimpleNamespace(
        _img=original, gray=MagicMock(), capture_started_at=None
    )

    def change_frame(*_):
        solver.recog._img = object()

    def observe_panel(_):
        if solver.recog._img is original:
            return "open"
        if unexpected == "closed":
            return "closed"
        raise base.RecognizeError("进驻面板属于其它房间")

    solver._work_room_panel = MagicMock(side_effect=observe_panel)
    solver.detect_room_type = MagicMock(return_value="制造站")
    solver._visible_manufacture_product = MagicMock(return_value=None)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.turn_on_room_detail = MagicMock(
        side_effect=change_frame if transition == "open_panel" else None
    )
    solver.wait_product_complete = MagicMock()
    solver.sleep = MagicMock(side_effect=change_frame)
    solver.find = MagicMock(
        side_effect=lambda resource, **_: (
            resource == "infra_no_operator"
            and solver.recog._img is not original
            and unexpected == "foreign_empty"
        )
    )
    solver.read_screen = MagicMock(
        side_effect=lambda *_, **__: "" if solver.recog._img is original else "夜刀"
    )
    solver._wait_drone_interface = MagicMock()
    observed = set()

    with pytest.raises(base.RecognizeError):
        solver.get_agent_from_room(room, observed_facilities=observed)

    assert solver._work_room_panel.call_count == 2
    assert (
        solver.find.call_count
        == solver.read_screen.call_count
        == (1 if transition == "retry_name" else 0)
    )
    solver.op_data.update_detail.assert_not_called()
    solver._reconcile_room_observation.assert_not_called()
    solver._wait_drone_interface.assert_not_called()
    assert resident.current_room == room and resident.mood == 18
    assert visitor.current_room == "room_1_1" and visitor.mood == 14
    assert observed == set()


@pytest.mark.parametrize("different_order", [True, False])
def test_selected_card_order_is_visible_and_reports_whether_sorting_is_pending(
    monkeypatch, caplog, different_order
):
    caplog.set_level(logging.DEBUG)
    instance, selected = selection_solver(monkeypatch)
    instance.tap_confirm = MagicMock()
    requested = (RESIDENTS[::-1] if different_order else RESIDENTS) + ["伊芙利特"]

    instance.choose_agent(requested, "dormitory_1")

    observations = [
        record for record in caplog.records if "选人页当前选中：" in record.getMessage()
    ]
    assert len(observations) == 1
    assert observations[0].levelno == logging.INFO
    assert observations[0].getMessage().startswith("宿舍1：选人页当前选中：")
    assert observations[0].getMessage().endswith("，待排序核对") == different_order
    assert observations[0].log_room == "dormitory_1"
    assert set(observations[0].log_agents) == set(requested)
    assert all(
        f"[[operator:{name}]]" in observations[0].getMessage() for name in requested
    )
    assert selected == requested
    instance.tap_confirm.assert_not_called()
    assert not any(
        record.getMessage().startswith("[") for record in records(caplog, logging.INFO)
    )


def test_temporary_dorm_arrangement_names_the_slot_and_retains_the_full_plan(
    dorm_solver, caplog
):
    caplog.set_level(logging.DEBUG)
    room = dorm_recovery_tests.ROOM
    original = deepcopy(dorm_solver.task.plan)

    assert dorm_solver.ensure_dorm_recovery_order(room, original[room].copy())

    messages = records(caplog, logging.INFO)
    assert [record.getMessage().splitlines()[0] for record in messages] == [
        "宿舍1：准备将[[operator:银灰]]调整到第4位，先安排临时阵容",
        "宿舍1：已确认[[operator:银灰]]位于第4位，继续按最终名单补齐其余位置",
    ]
    for record in messages:
        assert record.log_room == room
        assert record.log_agents == ["银灰"]
    temporary = messages[0].log_task
    assert temporary["header"] == messages[0].getMessage().splitlines()[0]
    assert temporary["rooms"][0]["id"] == room
    assert temporary["rooms"][0]["agents"] == ["杜林", "琴柳", "Free", "银灰"]
    assert "宿舍1：杜林、琴柳、Free、银灰" in messages[0].getMessage()
    assert dorm_solver.task.plan == original
    assert dorm_solver.physical[:2] == ["杜林", "琴柳"]
    assert dorm_solver.physical[3:] == ["银灰", ""]
    assert dorm_solver.op_data.operators[dorm_solver.physical[2]].mood == 24
    assert dorm_solver.tap_confirm.call_count == 1
    assert any(
        "临时阵容：" in record.getMessage() for record in records(caplog, logging.DEBUG)
    )


def test_failed_temporary_dorm_readback_does_not_log_a_confirmed_slot(
    dorm_solver, caplog
):
    caplog.set_level(logging.INFO)
    room = dorm_recovery_tests.ROOM
    original = deepcopy(dorm_solver.task.plan)
    dorm_solver.tap_confirm.side_effect = lambda *_: None

    with pytest.raises(Exception, match="宿舍单回排序确认失败"):
        dorm_solver.ensure_dorm_recovery_order(room, original[room].copy())

    assert not any(
        "已确认[[operator:银灰]]" in record.getMessage() for record in caplog.records
    )
    assert dorm_solver.task.plan == original


def test_room_observation_updates_idle_cache_without_claiming_a_new_departure(
    dorm_solver, caplog
):
    caplog.set_level(logging.DEBUG)
    room = dorm_recovery_tests.ROOM
    physical = dorm_solver.physical.copy()
    observed = [{"agent": "" if name == "陈" else name} for name in physical]

    dorm_solver._reconcile_room_observation(room, observed)

    messages = [
        record
        for record in caplog.records
        if record.getMessage() == "重设 [[operator:陈]] 至空闲"
    ]
    assert len(messages) == 1
    assert messages[0].levelno == logging.INFO
    assert messages[0].log_room == room
    assert messages[0].log_agents == ["陈"]
    assert messages[0].log_event == {"type": "operator-reset-idle"}
    assert dorm_solver.op_data.operators["陈"].current_room == ""
    assert dorm_solver.physical == physical
    dorm_solver.choose_agent.assert_not_called()
    dorm_solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("empty_room", [False, True])
def test_retry_reports_freshly_confirmed_names_without_repeating_selection(
    dorm_solver, caplog, empty_room
):
    caplog.set_level(logging.DEBUG)
    room = dorm_recovery_tests.ROOM
    dorm_solver.task.arrangement_retry_room = room
    dorm_solver.task.arrangement_retry_count = 3
    dorm_solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    dorm_solver.physical = dorm_recovery_tests.FINAL.copy()
    if empty_room:
        dorm_solver.task.emergency_dorm = True
        dorm_solver.physical = [""] * 5
        dorm_solver.task.plan[room] = dorm_solver.physical.copy()
    reads_before = dorm_solver.get_agent_from_room.call_count

    dorm_solver.agent_arrange_room({}, room, dorm_solver.task.plan)

    verified = [
        record
        for record in records(caplog, logging.INFO)
        if "重试时重新读取" in record.getMessage()
    ]
    assert len(verified) == 1
    assert verified[0].getMessage() == (
        "重试时重新读取宿舍1：按当前计划无需重复选人"
        if empty_room
        else "重试时重新读取宿舍1：[[operator:杜林]]、[[operator:琴柳]]、[[operator:红]]、[[operator:银灰]]、[[operator:陈]]已在计划位置，跳过重复选人"
    )
    assert verified[0].log_room == room
    assert verified[0].log_agents == ([] if empty_room else dorm_recovery_tests.FINAL)
    assert any(
        "重试复核计划：" in record.getMessage()
        for record in records(caplog, logging.DEBUG)
    )
    assert dorm_solver.get_agent_from_room.call_count > reads_before
    dorm_solver.choose_agent.assert_not_called()
    dorm_solver.tap_confirm.assert_not_called()
