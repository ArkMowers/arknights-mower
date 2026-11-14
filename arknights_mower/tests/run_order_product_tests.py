"""测试订单准入、精零孑收单及卖玉贸易站的无人机加速限制。"""

import pickle
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import (  # noqa: E402
    config,
    mastery_recommendation,  # noqa: E402
    scheduler_task,
)
from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.recognize import RecognizeError, Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(mastery_recommendation, "get_cultivate_characters", lambda: {})
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


def place_jaye(solver, monkeypatch, phase=0, product="orundum"):
    data = solver.op_data
    data.operators["鸿雪"].current_room = ""
    data.operators["孑"].current_room = "room_1_1"
    data.operators["孑"].current_index = 0
    data.products["room_1_1"] = product
    data.plan["room_1_1"][0].replacement = []
    monkeypatch.setattr(
        mastery_recommendation,
        "get_cultivate_characters",
        lambda: {"char_272_strong": {"evolvePhase": phase}},
    )


@pytest.mark.parametrize("phase", [0, 1, 2, None, False])
@pytest.mark.parametrize("product", ["lmd", "orundum"])
@pytest.mark.parametrize("with_replacements", [False, True])
@pytest.mark.parametrize("source", ["plan", "observed"])
def test_only_observed_elite_zero_jaye_creates_collection(
    solver, monkeypatch, phase, product, with_replacements, source
):
    place_jaye(solver, monkeypatch, phase, product if source == "plan" else "lmd")
    if source == "observed":
        solver.op_data.update_facility_state("room_1_1", "trade", product)
    if with_replacements:
        solver.op_data.plan["room_1_1"][0].replacement = ["但书"]
    solver.plan_run_order("room_1_1")
    if product == "orundum" and type(phase) is int and phase == 0:
        assert len(solver.tasks) == 1
        task = solver.tasks[0]
        assert task.type == TaskTypes.RUN_ORDER
        assert task.run_order_collect_only
        assert task.plan == {"room_1_1": ["Current"]}
        assert task.time == solver.get_run_order_time.return_value
        solver.plan_run_order("room_1_1")
        assert solver.tasks == [task]
    elif product == "lmd" and with_replacements:
        assert len(solver.tasks) == 1
        task = solver.tasks[0]
        assert task.type == TaskTypes.RUN_ORDER
        assert not task.run_order_collect_only
        assert task.plan == {"room_1_1": ["但书"]}
    else:
        assert solver.tasks == []
        solver.get_run_order_time.assert_not_called()


def test_collection_requires_actual_jaye_and_stops_when_he_leaves(solver, monkeypatch):
    place_jaye(solver, monkeypatch)
    solver.plan_run_order("room_1_1")
    assert len(solver.tasks) == 1
    solver.op_data.operators["孑"].current_room = "dormitory_1"
    solver._sync_run_order_tasks()
    assert solver.tasks == []
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []


@pytest.mark.parametrize("source", ["plan", "observed"])
@pytest.mark.parametrize("order", ["first", "second", "both"])
def test_conflict_adjustment_never_accelerates_orundum(solver, source, order):
    rooms = ("room_1_1", "room_2_2")
    excluded = rooms if order == "both" else (rooms[order == "second"],)
    for room in excluded:
        if source == "plan":
            solver.op_data.products[room] = "orundum"
        else:
            solver.op_data.update_facility_state(room, "trade", "orundum")
    solver.drone_room = excluded[0]
    tasks = [
        SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data=room) for room in rooms
    ]
    expected = next((room for room in rooms if room not in excluded), None)
    assert solver.get_run_order_adjust_room(tasks) == expected


@pytest.mark.parametrize("adjust_time", [True, False])
def test_drone_entry_rejects_orundum_without_navigation(solver, adjust_time):
    solver.op_data.products["room_1_1"] = "orundum"
    solver.enter_room = MagicMock()
    solver.tap = MagicMock()
    assert solver.drone("room_1_1", adjust_time=adjust_time) is False
    solver.enter_room.assert_not_called()
    solver.tap.assert_not_called()


@pytest.mark.parametrize("buffer", [0, 1])
def test_jaye_order_runs_at_completion_and_collects_without_staffing_or_drones(
    solver, monkeypatch, buffer
):
    place_jaye(solver, monkeypatch)
    use_order_pages(solver, {"room_1_1": "active"})
    use_mood_pages(solver, monkeypatch, {"room_1_1": ["孑"]})
    config.conf.run_order_grandet_mode.enable = bool(buffer)
    config.conf.run_order_grandet_mode.buffer_time = buffer
    before = datetime.now()
    solver.plan_run_order("room_1_1")
    after = datetime.now()
    task = solver.tasks[0]
    assert before + timedelta(hours=1) <= task.time <= after + timedelta(hours=1)
    solver.task = task
    solver.accept_order = MagicMock()
    solver.agent_arrange_room = MagicMock(side_effect=AssertionError("收单不能换人"))
    solver.drone = MagicMock(side_effect=AssertionError("收单不能加速"))

    assert solver.agent_arrange(task.plan)

    solver.accept_order.assert_called_once_with()
    solver.agent_arrange_room.assert_not_called()
    solver.drone.assert_not_called()
    assert solver.op_data.get_current_room("room_1_1", True) == ["孑"]
    assert task.plan == {}
    assert not hasattr(task, "run_order_original_roster")


@pytest.mark.parametrize("buffer", [0, 1])
def test_elite_zero_jaye_in_lmd_room_keeps_run_order_entry_delay(
    solver, monkeypatch, buffer
):
    place_jaye(solver, monkeypatch, product="lmd")
    solver.op_data.plan["room_1_1"][0].replacement = ["但书"]
    use_order_pages(solver, {"room_1_1": "active"})
    config.conf.run_order_grandet_mode.enable = bool(buffer)
    before = datetime.now()
    solver.plan_run_order("room_1_1")
    after = datetime.now()
    task = solver.tasks[0]
    expected = timedelta(hours=1, minutes=-config.conf.run_order_delay)
    assert before + expected <= task.time <= after + expected
    assert not task.run_order_collect_only
    assert task.plan == {"room_1_1": ["但书"]}


@pytest.mark.parametrize("product", ["lmd", "orundum"])
@pytest.mark.parametrize("persisted", [False, True])
def test_jaye_product_change_rebuilds_order_task_mode(
    solver, monkeypatch, product, persisted
):
    previous = "orundum" if product == "lmd" else "lmd"
    place_jaye(solver, monkeypatch, product=previous)
    solver.op_data.plan["room_1_1"][0].replacement = ["但书"]
    solver.plan_run_order("room_1_1")
    if persisted:
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    old = solver.tasks[0]
    solver.op_data.products["room_1_1"] = product
    solver.op_data.update_facility_state("room_1_1", "trade", product)
    solver.plan_run_order("room_1_1")
    assert len(solver.tasks) == 1
    task = solver.tasks[0]
    assert task is not old
    assert task.run_order_collect_only == (product == "orundum")
    assert task.plan == {"room_1_1": ["Current"] if product == "orundum" else ["但书"]}


def test_saved_lmd_collection_task_does_not_collect_and_replans_normal_order(
    solver, monkeypatch
):
    place_jaye(solver, monkeypatch, product="lmd")
    solver.op_data.plan["room_1_1"][0].replacement = ["但书"]
    task = SchedulerTask(
        task_plan={"room_1_1": ["Current"]},
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    task.run_order_collect_only = True
    solver.task = pickle.loads(pickle.dumps(task))
    use_order_pages(solver, {"room_1_1": "active"})
    use_mood_pages(solver, monkeypatch, {"room_1_1": ["孑"]})
    solver.accept_order = MagicMock()
    assert solver.agent_arrange(solver.task.plan)
    solver.accept_order.assert_not_called()
    assert solver.task.plan == {}
    solver.task = None
    solver.plan_run_order("room_1_1")
    assert len(solver.tasks) == 1
    assert not solver.tasks[0].run_order_collect_only
    assert solver.tasks[0].plan == {"room_1_1": ["但书"]}


@pytest.mark.parametrize("phase", [1, 2, None])
def test_jaye_collection_rechecks_progression_at_execution(solver, monkeypatch, phase):
    place_jaye(solver, monkeypatch)
    solver.plan_run_order("room_1_1")
    solver.task = solver.tasks[0]
    place_jaye(solver, monkeypatch, phase=phase)
    use_order_pages(solver, {"room_1_1": "active"})
    use_mood_pages(solver, monkeypatch, {"room_1_1": ["孑"]})
    solver.accept_order = MagicMock()
    solver.agent_arrange_room = MagicMock()
    solver.drone = MagicMock()
    assert solver.agent_arrange(solver.task.plan)
    solver.accept_order.assert_not_called()
    solver.agent_arrange_room.assert_not_called()
    solver.drone.assert_not_called()


def test_startup_publishes_jaye_collection_without_advancing_for_maintenance(
    solver, monkeypatch
):
    place_jaye(solver, monkeypatch)
    use_order_pages(solver, {"room_1_1": "active", "room_2_2": "active"})
    solver.read_time.return_value = 120
    solver._startup_run_order_check_pending = True
    solver._check_startup_run_orders()
    task = next(task for task in solver.tasks if task.meta_data == "room_1_1")
    assert task.run_order_collect_only
    assert task.plan == {"room_1_1": ["Current"]}
    original_time = task.time
    monkeypatch.setattr(
        scheduler_task.NewsChecker,
        "get_update_time",
        lambda: (
            original_time + timedelta(minutes=1),
            original_time + timedelta(hours=1),
        ),
    )
    assert scheduler_task.adjust_run_order_for_maintenance([task]) == []
    assert task.time == original_time
    assert not task.adjusted


def test_drone_rejects_actual_orundum_discovered_on_order_page(solver):
    use_order_pages(solver, {"room_1_1": "active"})
    config.conf.product_switching.enable = False
    solver._read_trade_product_card = MagicMock(return_value=("orundum", True))
    solver._tap_drone_accelerate = MagicMock()
    solver.adjust_order_time = MagicMock()
    assert solver.drone("room_1_1", adjust_time=True) is False
    solver._tap_drone_accelerate.assert_not_called()
    solver.adjust_order_time.assert_not_called()


def test_jaye_collection_survives_saved_queue_and_rechecks_actual_occupants(
    solver, monkeypatch
):
    place_jaye(solver, monkeypatch)
    solver.plan_run_order("room_1_1")
    task = pickle.loads(pickle.dumps(solver.tasks[0]))
    assert task.run_order_collect_only
    assert task.plan == {"room_1_1": ["Current"]}
    use_order_pages(solver, {"room_1_1": "active"})
    use_mood_pages(solver, monkeypatch, {"room_1_1": ["鸿雪"]})
    solver.task = task
    solver.accept_order = MagicMock()
    solver.agent_arrange_room = MagicMock()
    solver.drone = MagicMock()
    assert solver.agent_arrange(task.plan)
    solver.accept_order.assert_not_called()
    solver.agent_arrange_room.assert_not_called()
    solver.drone.assert_not_called()
    assert task.plan == {}


def test_collection_does_not_advance_for_network_adaptation(solver, monkeypatch):
    from arknights_mower.utils.network_adaptation import get_network_adaptation
    from arknights_mower.utils.run_order_network import (
        bind_run_order_network,
        run_order_buffer_seconds,
        run_order_entry_seconds,
    )

    place_jaye(solver, monkeypatch)
    solver.plan_run_order("room_1_1")
    task = solver.tasks[0]
    config.conf.run_order_network_adaptive = True
    config.conf.run_order_grandet_mode.enable = True
    config.conf.run_order_grandet_mode.buffer_time = 15
    now = datetime.now()
    task.time = now + timedelta(minutes=2)
    original_time = task.time
    owner = SimpleNamespace()
    get_network_adaptation(owner).record(
        "CONNECTING",
        elapsed_seconds=30,
        base_seconds=30,
        observed_at=now,
        timed_out=True,
    )
    # 复用正常绑定入口；收单任务不能获得临时提前时间。
    bind_run_order_network([task], owner, config.conf, now, op_data=solver.op_data)
    assert task.time == original_time
    assert not hasattr(task, "run_order_network_timing")
    assert run_order_entry_seconds(task, config.conf) == 0
    assert run_order_buffer_seconds(task, config.conf) == 0


def test_jaye_collection_keeps_maintenance_pause(solver, monkeypatch):
    place_jaye(solver, monkeypatch)
    solver.op_data.maintenance_primary_slots = {("room_1_1", 0)}
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    solver.get_run_order_time.assert_not_called()


def test_collection_respects_pending_original_roster_restoration(solver, monkeypatch):
    place_jaye(solver, monkeypatch)
    solver.plan_run_order("room_1_1")
    collection = solver.tasks[0]
    restoration = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={"room_1_1": ["鸿雪"]}
    )
    restoration.run_order_original_roster = {"room_1_1": ["鸿雪"]}
    restoration.run_order_restore_pending = True
    solver.tasks.append(restoration)
    solver.task = collection
    solver.enter_room = MagicMock()
    original_time = collection.time
    assert solver.agent_arrange(collection.plan) is False
    solver.enter_room.assert_not_called()
    assert collection.time == original_time
    assert collection.plan == {"room_1_1": ["Current"]}
    assert solver.tasks == [collection, restoration]


def test_drone_unreadable_trade_type_cannot_open_acceleration(solver):
    use_order_pages(solver, {"room_1_1": "active"})
    solver._read_trade_product_card = MagicMock(
        side_effect=RecognizeError("订单类型未确认")
    )
    solver._tap_drone_accelerate = MagicMock()
    with pytest.raises(RecognizeError, match="订单类型未确认"):
        solver.drone("room_1_1")
    solver._tap_drone_accelerate.assert_not_called()


def test_collection_accepts_ready_order_without_run_order_buff_or_missed_report(
    solver, monkeypatch
):
    place_jaye(solver, monkeypatch)
    solver.plan_run_order("room_1_1")
    solver.task = solver.tasks[0]
    solver.recog = SimpleNamespace(
        w=1920, h=1080, update=MagicMock(), save_screencap=MagicMock()
    )
    solver._cache_facility_state_from_current_page = MagicMock()
    solver.find = MagicMock(side_effect=[True, True, None])
    solver.tap = MagicMock()
    solver.order_reader = MagicMock()

    solver.accept_order()

    solver.tap.assert_called_once_with((480, 270), interval=0.5)
    solver.order_reader.get_buff_scores.assert_not_called()
    solver.order_reader.save.assert_not_called()
    solver.recog.save_screencap.assert_not_called()


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
    read_args = [entry.args for entry in solver.get_agent_from_room.call_args_list]
    assert read_args.count(("room_1_1", None)) == 1


def use_order_pages(solver, order_states):
    page = {"room": None, "open": False}
    marker = ((404, 137), (556, 195))

    def enter_room(room):
        page.update(room=room, open=False)

    def open_orders(*args, **kwargs):
        page["open"] = True

    def return_to_base(scene):
        if scene == Scene.INFRA_DETAILS:
            page["open"] = False
            return
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

    def get_agent(room, *args, **kwargs):
        assert not page["open"], (
            "进入房间读取干员心情前，必须先退出订单详情界面返回房间视图"
        )
        return [
            {"agent": name, "mood": 24}
            for name in solver.op_data.get_current_room(room, True)
        ]

    solver._page = page
    solver.get_run_order_time = BaseSchedulerSolver.get_run_order_time.__get__(solver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver.enter_room = MagicMock(side_effect=enter_room)
    solver.tap = MagicMock(side_effect=open_orders)
    solver.sleep = MagicMock()
    solver.find = MagicMock(side_effect=find)
    solver.scene_graph_navigation = MagicMock(side_effect=return_to_base)
    solver._cache_facility_state_from_current_page = MagicMock(return_value=None)
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
    solver.get_agent_from_room = MagicMock(side_effect=get_agent)


def use_mood_pages(solver, monkeypatch, occupants):
    solver.op_data.facility_levels["train"] = 0
    monkeypatch.setattr(base_schedule, "try_workshop_tasks", MagicMock())
    solver.back = MagicMock()
    solver._plan_dorm_recovery = MagicMock(return_value=True)

    def read_room(room, *args, **kwargs):
        if hasattr(solver, "_page"):
            assert not solver._page["open"], (
                "进入房间读取干员心情前，必须先退出订单详情界面返回房间视图"
            )
        result = []
        for index, name in enumerate(occupants[room]):
            if name:
                operator = solver.op_data.operators[name]
                operator.current_room, operator.current_index = room, index
                operator.mood, operator.time_stamp = 24, datetime.now()
            result.append({"agent": name, "mood": 24 if name else -1})
        solver._reconcile_room_observation(room, result)
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
    assert solver.scene_graph_navigation.call_args_list == [
        call(Scene.INFRA_DETAILS),
        call(Scene.INFRA_MAIN),
    ]


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

    refresh = None
    if trigger == "refresh":
        refresh = SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data="room_1_1")
        solver.tasks = [refresh]
        solver.task = refresh
        solver.infra_main()
        assert any(task is refresh for task in solver.tasks)
        assert refresh.execution_failure
        assert not solver.planned

    solver.infra_main()

    assert solver.op_data.get_current_room("room_1_1", True) == [""]
    corrections = [
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    ]
    assert len(corrections) == 1
    assert corrections[0].plan["room_1_1"] == ["鸿雪"]
    waiting = next(
        task
        for task in solver.tasks
        if task.type == TaskTypes.REFRESH_TIME and task.meta_data == "room_1_1"
    )
    assert waiting.execution_failure
    if refresh is not None:
        assert waiting is refresh
    original_time = waiting.time
    assert not any(
        task.type == TaskTypes.RUN_ORDER and task.meta_data == "room_1_1"
        for task in solver.tasks
    )
    assert not solver.error

    # 通过真实房间安排执行纠错，确认入驻后立即读取订单。
    correction = corrections[0]
    solver.task = correction
    solver.waiting_scene = []
    order_find = solver.find
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
        arrangement.setattr(
            solver,
            "find",
            MagicMock(
                side_effect=lambda resource: (
                    True if resource == "confirm_blue" else order_find(resource)
                )
            ),
        )
        arrangement.setattr(solver, "scene", MagicMock(return_value=Scene.INFRA_MAIN))
        arrangement.setattr(solver.recog, "update", MagicMock(), raising=False)
        arrangement.setattr(solver, "choose_agent", MagicMock())

        def confirm_staffing(room, new_plan):
            occupants[room] = solver.choose_agent.call_args.args[0].copy()
            states[room] = "active"

        arrangement.setattr(
            solver, "tap_confirm", MagicMock(side_effect=confirm_staffing)
        )
        solver.agent_arrange(correction.plan)

    assert solver.op_data.get_current_room("room_1_1", True) == ["鸿雪"]
    assert correction.plan == {}
    solver.tasks.remove(correction)
    assert waiting.time == original_time
    assert waiting not in solver.tasks
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
    solver.get_agent_from_room.assert_called_once()
    read = solver.get_agent_from_room.call_args
    assert read.args == ("room_1_1", None)
    assert read.kwargs["force_mood"] is True
    assert solver.scene_graph_navigation.call_args_list == [
        call(Scene.INFRA_DETAILS),
        call(Scene.INFRA_MAIN),
    ]


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


def test_two_paused_empty_rooms_keep_independent_refresh_responsibilities(
    solver, monkeypatch
):
    rooms = ("room_1_1", "room_2_2")
    use_order_pages(solver, dict.fromkeys(rooms, "paused"))
    use_mood_pages(solver, monkeypatch, {room: [""] for room in rooms})
    for room in rooms:
        solver.plan_run_order(room)
    waiting = {
        task.meta_data: task
        for task in solver.tasks
        if task.type == TaskTypes.REFRESH_TIME
    }
    assert set(waiting) == set(rooms)
    original_times = {room: task.time for room, task in waiting.items()}
    assert all(task.execution_failure for task in waiting.values())
    assert any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
    for _ in range(3):
        solver._resume_failed_tasks()
        solver._queue_missing_run_order_reads()
        for room in rooms:
            solver.plan_run_order(room)
        pending = [task for task in solver.tasks if task.type == TaskTypes.REFRESH_TIME]
        assert len(pending) == 2
        assert all(task is waiting[task.meta_data] for task in pending)
        assert all(task.time == original_times[task.meta_data] for task in pending)
        assert all(task.execution_failure for task in pending)
    assert solver.read_time.call_count == 2
