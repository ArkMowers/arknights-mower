"""测试跑单准入：卖玉或订单暂停不跑单，正常扫描与换班继续。"""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config, scheduler_task  # noqa: E402
from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.recognize import RecognizeError, Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    config.conf.enable_mastery = False
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "room_1_1": [Room("鸿雪", "", ["但书", "孑"])],
                    "room_2_2": [Room("图耶", "", ["龙舌兰", "锏"])],
                    "dormitory_1": [Room("杜林", "", []), Room("蜜莓", "", [])]
                    + [Room("Free", "", []) for _ in range(3)],
                },
                PlanConfig("", "", ""),
                products={"room_1_1": "lmd", "room_2_2": "lmd"},
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression("1", "==", "1"),
                    products={"room_1_1": "orundum"},
                )
            ],
        }
    )
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.time_stamp = datetime.now()
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = data
    instance.tasks = []
    instance.task = None
    instance.get_run_order_time = MagicMock(
        return_value=datetime.now() + timedelta(hours=1)
    )
    instance.queue_product_switches = MagicMock()
    instance._suppress_train_correction = MagicMock()
    return instance


@pytest.mark.parametrize("source", ["plan", "observed"])
def test_orundum_does_not_create_run_order_even_with_trade_agents(solver, source):
    if source == "plan":
        solver.op_data.products["room_1_1"] = "orundum"
    else:
        solver.op_data.update_facility_state("room_1_1", "trade", "orundum")
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    solver.get_run_order_time.assert_not_called()
    assert set(solver.op_data.run_order_rooms) == {"room_2_2"}


@pytest.mark.parametrize("has_order", [True, False])
def test_reading_actual_orundum_cancels_new_run_order(solver, has_order):
    def read_order(room):
        solver.op_data.update_facility_state(room, "trade", "orundum")
        return datetime.now() - timedelta(minutes=1) if has_order else None

    solver.get_run_order_time.side_effect = read_order
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    assert "room_1_1" not in solver.op_data.run_order_rooms


def test_swap_rebuilds_rooms_after_removing_trade_replacements(solver):
    data = solver.op_data
    backup = data.backup_plans[0]
    backup.products = {}
    backup.plan = {"room_1_1": [Room("鸿雪", "", ["孑"])]}
    assert data.swap_plan([True], refresh=True) is None
    assert set(data.run_order_rooms) == {"room_2_2"}
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    solver.get_run_order_time.assert_not_called()
    assert data.swap_plan([False], refresh=True) is None
    assert set(data.run_order_rooms) == {"room_1_1", "room_2_2"}


def test_sync_removes_only_invalid_order_and_order_refresh_tasks(solver):
    removed = [
        SchedulerTask(task_type=kind, meta_data="room_1_1")
        for kind in (TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME)
    ]
    kept = [
        SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_2_2"),
        SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data="room_2_2"),
        SchedulerTask(task_type=TaskTypes.RUN_ORDER, task_plan={"room_1_1": ["鸿雪"]}),
        *[
            SchedulerTask(task_type=kind, meta_data="room_1_1")
            for kind in (
                TaskTypes.SHIFT_ON,
                TaskTypes.SHIFT_OFF,
                TaskTypes.EXHAUST_OFF,
                TaskTypes.SELF_CORRECTION,
                TaskTypes.NOT_SPECIFIC,
            )
        ],
    ]
    solver.tasks = removed + kept
    solver.op_data.products["room_1_1"] = "orundum"
    timestamps = {name: op.time_stamp for name, op in solver.op_data.operators.items()}

    solver._sync_run_order_tasks()

    assert solver.tasks == kept
    assert {
        name: op.time_stamp for name, op in solver.op_data.operators.items()
    } == timestamps


def test_backup_convergence_removes_queued_orders_immediately(solver):
    stale = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_1_1")
    other = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_2_2")
    solver.tasks = [stale, other]
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert all(task is not stale for task in solver.tasks)
    assert any(task is other for task in solver.tasks)
    assert set(solver.op_data.run_order_rooms) == {"room_2_2"}


def test_returning_to_lmd_waits_for_actual_product_and_resumes(solver):
    data = solver.op_data
    data.update_facility_state("room_1_1", "trade", "orundum")
    assert data.swap_plan([True], refresh=True) is None
    assert data.swap_plan([False], refresh=True) is None
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    data.update_facility_state("room_1_1", "trade", "lmd")
    solver.plan_run_order("room_1_1")
    assert len(solver.tasks) == 1
    assert solver.tasks[0].plan == {"room_1_1": ["但书"]}
    assert solver.tasks[0].time == solver.get_run_order_time.return_value


def test_orundum_room_still_gets_normal_mood_scan(solver, monkeypatch):
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *args, **kwargs: mastery_reader.RoomState(state="empty"),
    )
    data = solver.op_data
    data.products["room_1_1"] = "orundum"
    target = data.operators["鸿雪"]
    target.time_stamp = datetime.now() - timedelta(hours=3)
    solver._sync_run_order_tasks()
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.get_agent_from_room = MagicMock(return_value=[{"agent": "鸿雪", "mood": 10}])

    solver.agent_get_mood(return_plan=True)

    # 常规巡检还会检查训练室；这里约束卖玉房间仍被正常扫描一次。
    assert solver.enter_room.call_args_list.count(call("room_1_1")) == 1
    assert solver.get_agent_from_room.call_args_list.count(call("room_1_1", None)) == 1


def use_order_pages(solver, order_states):
    page = {"room": None, "open": False}
    marker = ((404, 137), (556, 195))

    def enter_room(room):
        page.update(room=room, open=False)

    def open_orders(*args, **kwargs):
        page["open"] = True

    def return_to_base(scene):
        assert scene == Scene.INFRA_MAIN
        page.update(room=None, open=False)

    def find(resource):
        if resource == "control_central" and page["room"] is None:
            return marker
        if not page["open"]:
            return None
        state = order_states[page["room"]]
        if resource == "order_label" and state != "unrecognized":
            return marker
        if resource == "bill_accelerate" and state == "active":
            return marker
        return None

    solver.get_run_order_time = BaseSchedulerSolver.get_run_order_time.__get__(solver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver.enter_room = MagicMock(side_effect=enter_room)
    solver.tap = MagicMock(side_effect=open_orders)
    solver.sleep = MagicMock()
    solver.find = MagicMock(side_effect=find)
    solver.scene_graph_navigation = MagicMock(side_effect=return_to_base)
    solver._cache_facility_state_from_current_page = MagicMock()
    solver._product_ocr_text = MagicMock(
        side_effect=lambda scope: (
            "订单暂停获取中"
            if order_states[page["room"]] in ("empty", "paused")
            else "获取订单中..."
            if order_states[page["room"]] in ("active", "active_without_button")
            else ""
        )
    )
    solver.read_time = MagicMock(
        return_value=3600,
        side_effect=lambda *args, **kwargs: (
            None
            if order_states[page["room"]] in ("empty", "paused")
            else solver.read_time.return_value
        ),
    )
    solver.double_read_time = MagicMock(
        return_value=datetime.now() + timedelta(hours=1)
    )
    solver.get_agent_from_room = MagicMock(
        side_effect=lambda room, *args, **kwargs: [
            {"agent": name, "mood": 24}
            for name in solver.op_data.get_current_room(room, True)
        ]
    )


def use_mood_pages(solver, monkeypatch, occupants):
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", True)
    monkeypatch.setattr(base_schedule, "try_workshop_tasks", MagicMock())
    solver.back = MagicMock()
    solver._plan_dorm_recovery = MagicMock(return_value=True)

    def read_room(room, *args, **kwargs):
        result = []
        for index, name in enumerate(occupants[room]):
            if name:
                operator = solver.op_data.operators[name]
                operator.current_room, operator.current_index = room, index
                operator.mood, operator.time_stamp = 24, datetime.now()
            result.append({"agent": name, "mood": 24 if name else -1})
        return result

    solver.get_agent_from_room = MagicMock(side_effect=read_room)
    solver.planned = False
    solver.error = False


@pytest.mark.parametrize("state", ["empty", "paused"])
def test_inactive_order_page_returns_no_run_order_time(solver, state):
    use_order_pages(solver, {"room_1_1": state})

    assert solver.get_run_order_time("room_1_1") is None

    solver.read_time.assert_called_once_with(
        solver._run_order_time_region(), None, use_digit_reader=True
    )
    solver._product_ocr_text.assert_called_once()
    solver.double_read_time.assert_not_called()
    solver.scene_graph_navigation.assert_called_once_with(Scene.INFRA_MAIN)


def test_no_run_order_time_does_not_create_an_immediate_task(solver):
    shift = SchedulerTask(
        time=datetime.now() + timedelta(hours=2), task_type=TaskTypes.SHIFT_ON
    )
    solver.tasks = [shift]
    solver.get_run_order_time.return_value = None

    solver.plan_run_order("room_1_1")

    assert solver.tasks == [shift]


@pytest.mark.parametrize("state", ["empty", "paused"])
def test_inactive_order_does_not_block_other_orders_or_normal_planning(solver, state):
    use_order_pages(solver, {"room_1_1": state, "room_2_2": "active"})
    shift = SchedulerTask(
        time=datetime.now() + timedelta(hours=2), task_type=TaskTypes.SHIFT_ON
    )
    solver.tasks = [shift]
    solver.planned = False
    solver.error = False
    solver.agent_get_mood = MagicMock(return_value=None)
    solver.plan_solver = MagicMock()

    solver.infra_main()

    orders = [task for task in solver.tasks if task.type == TaskTypes.RUN_ORDER]
    assert len(orders) == 1
    assert orders[0].meta_data == "room_2_2"
    assert shift in solver.tasks
    assert solver.read_time.call_count == 2
    solver._product_ocr_text.assert_called_once()
    solver.double_read_time.assert_not_called()
    solver.plan_solver.assert_called_once()
    assert solver.planned
    assert not solver.error


def test_order_resumes_after_an_inactive_page_without_losing_room_eligibility(solver):
    states = {"room_1_1": "paused"}
    use_order_pages(solver, states)

    solver.plan_run_order("room_1_1")

    assert solver.tasks == []
    assert "room_1_1" in solver.op_data.run_order_rooms
    solver.read_time.assert_called_once()
    solver._product_ocr_text.assert_called_once()
    solver.double_read_time.assert_not_called()

    states["room_1_1"] = "active"
    before = datetime.now()
    solver.plan_run_order("room_1_1")
    after = datetime.now()

    assert len(solver.tasks) == 1
    assert solver.tasks[0].meta_data == "room_1_1"
    offset = timedelta(seconds=3600, minutes=-config.conf.run_order_delay)
    assert before + offset <= solver.tasks[0].time <= after + offset
    assert solver.read_time.call_count == 2
    solver._product_ocr_text.assert_called_once()
    solver.double_read_time.assert_not_called()


@pytest.mark.parametrize("state", ["active", "active_without_button", "unknown"])
def test_valid_countdown_admits_order_without_requiring_accelerate_button(
    solver, state
):
    use_order_pages(solver, {"room_1_1": state})
    before = datetime.now()

    solver.plan_run_order("room_1_1")

    after = datetime.now()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].meta_data == "room_1_1"
    offset = timedelta(seconds=3600, minutes=-config.conf.run_order_delay)
    assert before + offset <= solver.tasks[0].time <= after + offset
    solver.read_time.assert_called_once_with(
        solver._run_order_time_region(), None, use_digit_reader=True
    )
    solver._product_ocr_text.assert_not_called()
    solver.double_read_time.assert_not_called()


@pytest.mark.parametrize("state", ["active", "active_without_button", "unknown"])
def test_unreadable_countdown_is_not_inactivity_or_an_immediate_order(solver, state):
    use_order_pages(solver, {"room_1_1": state})
    solver.read_time.return_value = None
    shift = SchedulerTask(
        time=datetime.now() + timedelta(hours=2), task_type=TaskTypes.SHIFT_ON
    )
    solver.tasks = [shift]

    with pytest.raises(RecognizeError, match="无法读取贸易站订单倒计时"):
        solver.plan_run_order("room_1_1")

    assert solver.tasks == [shift]
    assert "room_1_1" in solver.op_data.run_order_rooms
    solver._product_ocr_text.assert_called_once()
    solver.double_read_time.assert_not_called()


def test_confirmed_zero_countdown_can_still_create_a_due_order(solver):
    use_order_pages(solver, {"room_1_1": "active_without_button"})
    solver.read_time.return_value = 0

    solver.plan_run_order("room_1_1")

    assert len(solver.tasks) == 1
    assert solver.tasks[0].meta_data == "room_1_1"
    assert solver.tasks[0].time <= datetime.now()
    solver.read_time.assert_called_once()
    solver._product_ocr_text.assert_not_called()
    solver.double_read_time.assert_not_called()


def test_missing_order_page_still_raises_and_preserves_existing_tasks(solver):
    use_order_pages(solver, {"room_1_1": "unrecognized"})
    shift = SchedulerTask(
        time=datetime.now() + timedelta(hours=2), task_type=TaskTypes.SHIFT_ON
    )
    solver.tasks = [shift]

    with pytest.raises(RecognizeError, match="未成功进入订单或制造详情界面"):
        solver.plan_run_order("room_1_1")

    assert solver.tasks == [shift]
    solver.read_time.assert_not_called()
    solver.double_read_time.assert_not_called()


def test_cleared_cache_startup_corrects_empty_trade_room_before_reading_orders(
    solver, monkeypatch
):
    use_order_pages(solver, {"room_1_1": "empty", "room_2_2": "active"})
    use_mood_pages(
        solver,
        monkeypatch,
        {
            "room_1_1": [""],
            "room_2_2": ["图耶"],
            "dormitory_1": ["杜林", "蜜莓", "", "", ""],
        },
    )
    for operator in solver.op_data.operators.values():
        operator.current_room, operator.current_index = "", -1
        operator.time_stamp = None
    solver.defer_backup_plan_until_mood_read = True
    solver._read_initial_card_mood = MagicMock()
    solver._queue_initial_fia = MagicMock(return_value=False)
    solver.backup_plan_solver = MagicMock()

    solver.infra_main()

    corrections = [
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    ]
    assert len(corrections) == 1
    assert corrections[0].plan["room_1_1"] == ["鸿雪"]
    assert solver.op_data.get_current_room("room_1_1", True) == [""]
    solver._product_ocr_text.assert_not_called()
    solver.read_time.assert_not_called()
    assert not solver.error


@pytest.mark.parametrize("trigger", ["planning", "refresh"])
def test_paused_order_reconciles_empty_room_despite_recent_occupancy_cache(
    solver, monkeypatch, trigger
):
    states = {"room_1_1": "paused", "room_2_2": "active"}
    occupants = {"room_1_1": [""]}
    use_order_pages(solver, states)
    use_mood_pages(solver, monkeypatch, occupants)
    assert solver.op_data.get_current_room("room_1_1", True) == ["鸿雪"]
    assert not solver.op_data.operators["鸿雪"].need_to_refresh()

    if trigger == "refresh":
        refresh = SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data="room_1_1")
        solver.tasks = [refresh]
        solver.task = refresh
        solver.infra_main()
        assert refresh not in solver.tasks
        assert not solver.planned

    solver.infra_main()

    assert solver.op_data.get_current_room("room_1_1", True) == [""]
    corrections = [
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    ]
    assert len(corrections) == 1
    assert corrections[0].plan["room_1_1"] == ["鸿雪"]
    assert not any(
        task.type == TaskTypes.RUN_ORDER and task.meta_data == "room_1_1"
        for task in solver.tasks
    )
    assert not solver.error

    # 通过真实房间安排执行纠错，再执行其生成的订单时间刷新任务。
    correction = corrections[0]
    solver.task = correction
    solver.waiting_scene = []
    with monkeypatch.context() as arrangement:
        for name in (
            "turn_on_room_detail",
            "record_selection_success",
            "_track_idle_dorm_shift",
            "_finish_idle_dorm_shift",
        ):
            arrangement.setattr(solver, name, MagicMock(), raising=False)
        arrangement.setattr(
            solver, "ensure_dorm_recovery_order", MagicMock(return_value=False)
        )
        arrangement.setattr(
            solver, "_can_refresh_idle_dorm_search", MagicMock(return_value=False)
        )
        arrangement.setattr(solver, "find", MagicMock(return_value=True))
        arrangement.setattr(solver, "scene", MagicMock(return_value=Scene.INFRA_MAIN))
        arrangement.setattr(solver, "choose_agent", MagicMock())
        arrangement.setattr(
            solver,
            "tap_confirm",
            MagicMock(
                side_effect=lambda room, new_plan: occupants.update(
                    {room: solver.choose_agent.call_args.args[0].copy()}
                )
            ),
        )
        solver.agent_arrange(correction.plan)

    assert solver.op_data.get_current_room("room_1_1", True) == ["鸿雪"]
    assert correction.plan == {}
    solver.tasks.remove(correction)
    refresh = next(
        task
        for task in solver.tasks
        if task.type == TaskTypes.REFRESH_TIME and task.meta_data == "room_1_1"
    )
    states["room_1_1"] = "active"
    solver.scene_graph_navigation(Scene.INFRA_MAIN)
    solver.task = refresh

    solver.infra_main()

    assert refresh not in solver.tasks
    assert any(
        task.type == TaskTypes.RUN_ORDER and task.meta_data == "room_1_1"
        for task in solver.tasks
    )
    assert not solver.error


def test_paused_order_with_observed_staff_does_not_force_an_empty_room_correction(
    solver,
):
    use_order_pages(solver, {"room_1_1": "paused"})

    solver.plan_run_order("room_1_1")

    assert solver.tasks == []
    assert solver.op_data.get_current_room("room_1_1", True) == ["鸿雪"]
    solver.get_agent_from_room.assert_called_once_with(
        "room_1_1", None, force_mood=True
    )


def test_failed_paused_room_read_preserves_cache_and_existing_tasks(solver):
    use_order_pages(solver, {"room_1_1": "paused"})
    solver.get_agent_from_room.side_effect = RecognizeError("驻员读取失败")
    shift = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
    solver.tasks = [shift]
    timestamp = solver.op_data.operators["鸿雪"].time_stamp

    with pytest.raises(RecognizeError, match="驻员读取失败"):
        solver.plan_run_order("room_1_1")

    assert solver.tasks == [shift]
    assert solver.op_data.get_current_room("room_1_1", True) == ["鸿雪"]
    assert solver.op_data.operators["鸿雪"].time_stamp == timestamp
