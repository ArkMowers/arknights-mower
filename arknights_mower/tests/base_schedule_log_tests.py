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
    ("facility", "room_label", "previous", "observed", "reading", "subject"),
    [
        ("manufacture", "制造站 B102", "gold", "exp3", "中级作战记录", "产物"),
        ("trade", "贸易站 B101", "lmd", "orundum", "开采协力", "订单类型"),
    ],
    ids=["manufacture", "trade"],
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
    instance._wait_drone_interface = MagicMock()
    instance._product_ocr_text = MagicMock(
        return_value="无法识别的文字" if outcome == "unknown_product" else reading
    )
    instance.scene_graph_navigation = MagicMock(
        side_effect=lambda _: base.logger.info("进入设施详情")
    )
    instance._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    instance.turn_on_room_detail = MagicMock()
    instance.wait_product_complete = MagicMock()
    instance.find = MagicMock(return_value=None)
    instance.read_screen = MagicMock(return_value=name)

    def measure(_):
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

    start, navigation, end = records(caplog, logging.INFO)
    assert start.log_event["id"] == end.log_event["id"]
    parent = {"type": "facility-observation", "id": start.log_event["id"]}
    assert start.log_parent == navigation.log_parent == end.log_parent == parent
    assert navigation.getMessage() == "进入设施详情"
    assert not hasattr(navigation, "log_event")
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
    assert start.getMessage() == f"{room_label}：{state}，正在读取干员心情"
    expected_detail = {
        "cached_mood": f"[[operator:{name}]]（心情未实读）",
        "interrupted": "干员心情读取未完成",
    }.get(outcome, f"[[operator:{name}]]（心情16.124）")
    assert end.getMessage() == f"{room_label}：{state}，{expected_detail}"
    assert end.log_event["phase"] == (
        "failed" if outcome == "interrupted" else "completed"
    )
    assert (
        end.log_agents
        == end.log_event["agents"]
        == ([] if outcome == "interrupted" else [name])
    )
    assert instance.op_data.facility_states[room]["product"] == (
        previous if outcome == "unknown_product" else observed
    )
    if outcome == "cached_mood":
        instance.read_accurate_mood.assert_not_called()


def test_selected_card_order_is_visible_but_still_awaits_sorting_before_confirmation(
    monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    instance, selected = selection_solver(monkeypatch)
    instance.tap_confirm = MagicMock()
    requested = RESIDENTS + ["伊芙利特"]

    instance.choose_agent(requested, "dormitory_1")

    observations = [
        record for record in caplog.records if "选人页当前选中：" in record.getMessage()
    ]
    assert len(observations) == 1
    assert observations[0].levelno == logging.INFO
    assert observations[0].getMessage().startswith("宿舍1：选人页当前选中：")
    assert observations[0].getMessage().endswith("，待排序核对")
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


@pytest.mark.parametrize("placeholders_only", [False, True])
def test_retry_reports_freshly_confirmed_names_without_repeating_selection(
    dorm_solver, caplog, placeholders_only
):
    caplog.set_level(logging.DEBUG)
    room = dorm_recovery_tests.ROOM
    dorm_solver.task.arrangement_retry_room = room
    dorm_solver.task.arrangement_retry_count = 3
    dorm_solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    dorm_solver.physical = dorm_recovery_tests.FINAL.copy()
    if placeholders_only:
        dorm_solver.task.plan[room] = ["Free"] * 5
        dorm_solver._prepare_group_shift_execution_targets = MagicMock()
        dorm_solver.prepare_dorm_selection = MagicMock(return_value=[])
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
        if placeholders_only
        else "重试时重新读取宿舍1：[[operator:杜林]]、[[operator:琴柳]]、[[operator:红]]、[[operator:银灰]]、[[operator:陈]]已在计划位置，跳过重复选人"
    )
    assert verified[0].log_room == room
    assert verified[0].log_agents == (
        [] if placeholders_only else dorm_recovery_tests.FINAL
    )
    assert any(
        "重试复核计划：" in record.getMessage()
        for record in records(caplog, logging.DEBUG)
    )
    assert dorm_solver.get_agent_from_room.call_count > reads_before
    dorm_solver.choose_agent.assert_not_called()
    dorm_solver.tap_confirm.assert_not_called()
