import itertools
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.rapidocr import create_engine

with pytest.MonkeyPatch.context() as import_context:
    import_context.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule

from arknights_mower.solvers import clue_credit
from arknights_mower.solvers.shop import CreditShop
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils import datetime as server_datetime
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.image import bytes2img
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

CONFIGURATIONS = list(itertools.product([False, True], repeat=5))


def credit_conf(options):
    enabled, visits, native_visits, shopping, native_shop = options
    return Conf(
        clue_credit_on_demand=enabled,
        visit_friend_enable=visits,
        visit_friend_mode="mower" if native_visits else "maa",
        maa_mall_enable=shopping,
        maa_mall_mode="mower" if native_shop else "maa",
        maa_mall_buy="招聘许可",
        maa_mall_blacklist="碳",
    )


@pytest.mark.parametrize("options", CONFIGURATIONS)
def test_feature_requires_every_selection(options):
    conf = credit_conf(options)
    assert conf.should_defer_clue_credit is (options == (True,) * 5)
    restored = Conf(**conf.model_dump(exclude_unset=True))
    assert restored.clue_credit_on_demand == options[0]
    assert Conf().clue_credit_on_demand is False


@pytest.mark.parametrize("options", CONFIGURATIONS)
def test_shop_admission_preserves_other_configurations(shopping, monkeypatch, options):
    scheduler, _, state = shopping
    monkeypatch.setattr(config, "conf", credit_conf(options))
    scheduler.daily_visit_friend_attempt = None
    state.balance = 120
    state.products = [product()]
    shop = MagicMock()
    monkeypatch.setattr(base_schedule, "CreditShop", shop)
    monkeypatch.setattr(clue_credit, "CreditShop", shop)

    scheduler._run_clue_shop()

    if options == (True,) * 5 or not options[3] or not options[4]:
        shop.assert_not_called()
    else:
        shop.return_value.run.assert_called_once_with()
        scheduler.scene_graph_navigation.assert_called_once_with(Scene.INFRA_MAIN)
    scheduler.visit_friend_plan_solver.assert_not_called()


@pytest.mark.parametrize(
    "attempted,completed,buys",
    [(False, False, False), (True, False, True), (False, True, True)],
)
def test_shop_requires_actual_visit_or_existing_success(
    shopping, attempted, completed, buys
):
    scheduler, _, state = shopping
    today = server_datetime.get_server_time().date()
    scheduler.daily_visit_friend_attempt = today if attempted else None
    scheduler.daily_visit_friend = today if completed else date.min
    state.balance = 120
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.purchased == (["招聘许可"] if buys else [])
    assert state.visits == []
    scheduler.visit_friend_plan_solver.assert_not_called()
    assert not hasattr(scheduler, "_clue_shop_pending")


@pytest.mark.parametrize("active", [False, True])
def test_exact_balance_purchase_only_changes_when_feature_is_active(shopping, active):
    scheduler, _, state = shopping
    config.conf.clue_credit_on_demand = active
    state.balance = 120
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.purchased == (["招聘许可"] if active else [])
    assert state.balance == (0 if active else 120)
    assert state.visits == []


@pytest.mark.parametrize("options", CONFIGURATIONS)
@pytest.mark.parametrize("outcome", [True, None, "error"])
def test_visit_record_does_not_change_visit_results_or_dispatch(
    shopping, monkeypatch, options, outcome
):
    scheduler, _, state = shopping
    monkeypatch.setattr(config, "conf", credit_conf(options))
    scheduler.daily_visit_friend_attempt = None
    runner = MagicMock()
    failure = RuntimeError("visit failed")
    if outcome == "error":
        runner.run.side_effect = failure
    else:
        runner.run.return_value = outcome
    constructor = MagicMock(return_value=runner)
    monkeypatch.setattr(base_schedule, "CreditSolver", constructor)
    scheduler._run_clue_shop = MagicMock()
    visits = options[1] and options[2]

    if visits and outcome == "error":
        with pytest.raises(RuntimeError) as raised:
            base_schedule.BaseSchedulerSolver.visit_friend_plan_solver(scheduler)
        assert raised.value is failure
    else:
        result = base_schedule.BaseSchedulerSolver.visit_friend_plan_solver(scheduler)
        assert result is (outcome if visits else None)

    assert constructor.call_count == int(visits)
    assert scheduler.daily_visit_friend == date.min
    assert scheduler.daily_visit_friend_attempt == (
        server_datetime.get_server_time().date() if options == (True,) * 5 else None
    )
    assert base_schedule.save_current_state.call_count == int(options == (True,) * 5)
    scheduler._run_clue_shop.assert_not_called()


def test_attempt_stays_on_starting_game_day(shopping, monkeypatch):
    scheduler, _, state = shopping
    scheduler.daily_visit_friend_attempt = None
    state.now = datetime.fromisoformat("2026-10-14T03:59:59+08:00")
    runner = MagicMock()

    def visit():
        state.now += timedelta(seconds=2)
        return True

    runner.run.side_effect = visit
    monkeypatch.setattr(base_schedule, "CreditSolver", MagicMock(return_value=runner))
    assert base_schedule.BaseSchedulerSolver.visit_friend_plan_solver(scheduler) is True
    assert scheduler.daily_visit_friend_attempt == date(2026, 10, 13)
    state.balance = 120
    state.products = [product()]
    scheduler._run_clue_shop()
    assert state.purchased == []


def test_stop_before_visit_is_not_an_attempt(shopping, monkeypatch):
    scheduler, _, _ = shopping
    scheduler.daily_visit_friend_attempt = None
    runner = MagicMock()
    monkeypatch.setattr(base_schedule, "CreditSolver", runner)
    config.stop_mower.set()
    with pytest.raises(MowerExit):
        base_schedule.BaseSchedulerSolver.visit_friend_plan_solver(scheduler)
    runner.assert_not_called()
    assert scheduler.daily_visit_friend_attempt is None


@pytest.mark.parametrize("result", [True, False])
def test_expiry_attempt_is_not_repeated_during_shopping(shopping, result):
    scheduler, _, state = shopping
    state.products = [product()]
    scheduler._run_clue_shop(settlement_checked=result)
    assert state.visits == ([True] if result else [])


def test_new_run_does_not_reuse_old_deficit(shopping):
    _, shop, state = shopping
    state.products = [product()]
    shop.run(on_demand=True)
    assert shop.credit_deficit == 120
    shop.find = lambda name: name == "shop_credit_not_enough"
    state.scene = Scene.SHOP_CREDIT_CONFIRM
    shop.back = MagicMock()
    shop.run(on_demand=True)
    assert shop.credit_deficit is None


@pytest.mark.parametrize("corrected", [False, True])
def test_purchase_rejection_requires_confirmed_shortage(shopping, corrected):
    scheduler, shop, state = shopping
    state.balance = 100
    state.products = [product()]
    state.previous = 300
    readings = 0

    def credit_remain():
        nonlocal readings
        readings += 1
        return state.balance if corrected and readings > 1 else 200

    shop.credit_remain = credit_remain
    shop.find = lambda name: name == "shop_credit_not_enough" and state.balance < 120
    shop.back = lambda: setattr(state, "scene", Scene.SHOP_CREDIT)
    scheduler._run_clue_shop()
    assert state.visits == ([False] if corrected else [])
    assert state.purchased == (["招聘许可"] if corrected else [])
    assert readings <= 5


def prepare_empty_clue_workflow(scheduler, *, party_time=None):
    scheduler.tasks = []
    scheduler.op_data = SimpleNamespace(party_time=None)
    scheduler.leifeng_mode = False
    scheduler.clue_count = scheduler.clue_count_limit = 0
    scheduler._party_time = None
    for name in (
        "tap",
        "ctap",
        "tap_element",
        "back",
        "sleep",
        "backup_plan_solver",
        "wait_product_complete",
        "enter_room",
    ):
        setattr(scheduler, name, MagicMock())
    scheduler.read_party_time = MagicMock(return_value=party_time)
    scheduler._read_placed_clue_numbers = MagicMock(return_value=frozenset())
    scheduler.find = MagicMock(return_value=None)
    scheduler._open_clue_message_board = MagicMock(return_value=False)
    scenes = iter(
        [
            Scene.INFRA_DETAILS,
            *[Scene.INFRA_CONFIDENTIAL] * 4,
            Scene.CLUE_GIVE_AWAY,
            Scene.INFRA_CONFIDENTIAL,
            Scene.INFRA_DETAILS,
        ]
    )
    scheduler.scene = lambda: next(scenes)


def run_empty_clue_workflow(scheduler, state, monkeypatch, *, party_time=None):
    prepare_empty_clue_workflow(scheduler, party_time=party_time)
    scheduler.clue_new()
    scheduler.read_party_time.assert_called_once()


def prepare_clue_dispatch(scheduler, state, monkeypatch):
    class LocalClock(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return state.now.astimezone(tz)
            return state.now.astimezone().replace(tzinfo=None)

    monkeypatch.setattr(base_schedule, "datetime", LocalClock)
    scheduler.op_data = None
    scheduler.find = MagicMock(return_value=True)
    scheduler._refresh_deferred_product_reservations = MagicMock()
    return LocalClock


@pytest.mark.parametrize("kind", [TaskTypes.CLUE_PARTY, TaskTypes.CLUE])
@pytest.mark.parametrize(
    "now,deferred",
    [
        ("2026-10-14T03:44:59+08:00", False),
        ("2026-10-14T03:45:00+08:00", True),
        ("2026-10-14T03:59:59+08:00", True),
        ("2026-10-14T04:00:00+08:00", False),
        ("2026-10-13T19:50:00+00:00", True),
    ],
)
def test_clue_dispatch_defers_until_reset(shopping, monkeypatch, kind, now, deferred):
    scheduler, _, state = shopping
    state.now = datetime.fromisoformat(now)
    clock = prepare_clue_dispatch(scheduler, state, monkeypatch)
    # 包含此前已到期、因其他任务或重连拖到避让时段的任务。
    task = SchedulerTask(time=clock.now() - timedelta(minutes=20), task_type=kind)
    scheduler.task = task
    scheduler.tasks = [task]
    scheduler.last_clue = previous_check = clock.now() - timedelta(hours=2)
    scheduler.party_time = party_end = task.time
    scheduler.clue_new = MagicMock()

    scheduler.infra_main()

    if deferred:
        assert scheduler.tasks == [task]
        assert task.time == datetime.fromisoformat(
            "2026-10-14T04:00:00+08:00"
        ).astimezone().replace(tzinfo=None)
        assert scheduler.task is None
        assert scheduler.last_clue == previous_check
        assert scheduler.party_time == party_end
        scheduler.clue_new.assert_not_called()
        # 在避让时段重新派发不会重复执行或每天顺延。
        scheduler.task = task
        scheduler.infra_main()
        assert scheduler.tasks == [task]
        scheduler.clue_new.assert_not_called()
        state.now = datetime.fromisoformat("2026-10-14T04:00:00+08:00")
        scheduler.task = task
        scheduler.infra_main()

    scheduler.clue_new.assert_called_once_with()
    assert scheduler.tasks == []
    assert scheduler.last_clue == clock.now()


@pytest.mark.parametrize("options", CONFIGURATIONS)
def test_reset_deferral_only_applies_to_active_feature(shopping, monkeypatch, options):
    scheduler, _, state = shopping
    monkeypatch.setattr(config, "conf", credit_conf(options))
    state.now = datetime.fromisoformat("2026-10-14T03:50:00+08:00")
    clock = prepare_clue_dispatch(scheduler, state, monkeypatch)
    scheduler.task = SchedulerTask(time=clock.now(), task_type=TaskTypes.CLUE)
    scheduler.tasks = [scheduler.task]
    scheduler.clue_new = MagicMock()

    scheduler.infra_main()

    assert scheduler.clue_new.call_count == int(options != (True,) * 5)
    assert bool(scheduler.tasks) is (options == (True,) * 5)


@pytest.mark.parametrize("active", [False, True])
def test_periodic_clue_skip_preserves_interval_and_other_work(
    shopping, monkeypatch, active
):
    scheduler, _, state = shopping
    config.conf.clue_credit_on_demand = active
    state.now = datetime.fromisoformat("2026-10-14T03:50:00+08:00")
    clock = prepare_clue_dispatch(scheduler, state, monkeypatch)
    scheduler.task = None
    scheduler.tasks = []
    scheduler.op_data = SimpleNamespace(run_order_rooms={})
    scheduler.planned = True
    scheduler.todo_task = False
    scheduler.enable_party = True
    scheduler.last_clue = previous_check = clock.now() - timedelta(hours=2)
    scheduler.drone_room = "room_1_1"
    scheduler.drone_time = scheduler.reload_time = None
    scheduler.drone = MagicMock()
    scheduler.reload = MagicMock()
    scheduler.clue_new = MagicMock()

    scheduler.infra_main()

    assert scheduler.last_clue == (previous_check if active else clock.now())
    assert scheduler.clue_new.call_count == int(not active)
    scheduler.drone.assert_called_once_with("room_1_1")
    scheduler.reload.assert_called_once_with()
    assert scheduler.todo_task is True
    state.now = datetime.fromisoformat("2026-10-14T04:00:00+08:00")
    scheduler.todo_task = False
    scheduler.infra_main()
    scheduler.clue_new.assert_called_once_with()
    assert scheduler.last_clue == (
        clock.now() if active else previous_check + timedelta(hours=2)
    )


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize(
    "end",
    [
        "2026-10-14T03:44:59+08:00",
        "2026-10-14T03:45:00+08:00",
        "2026-10-14T03:59:59+08:00",
        "2026-10-14T04:00:00+08:00",
    ],
)
def test_new_party_task_avoids_reset_without_changing_party_end(
    shopping, monkeypatch, active, end
):
    scheduler, _, state = shopping
    config.conf.clue_credit_on_demand = active
    prepare_clue_dispatch(scheduler, state, monkeypatch)
    party_end = datetime.fromisoformat(end).astimezone().replace(tzinfo=None)
    scheduler._run_clue_shop = MagicMock()

    run_empty_clue_workflow(scheduler, state, monkeypatch, party_time=party_end)

    assert scheduler.party_time == scheduler.op_data.party_time == party_end
    assert len(scheduler.tasks) == 1
    task = scheduler.tasks[0]
    assert task.type == TaskTypes.CLUE_PARTY
    if active and end in ("2026-10-14T03:45:00+08:00", "2026-10-14T03:59:59+08:00"):
        assert task.time == datetime.fromisoformat(
            "2026-10-14T04:00:00+08:00"
        ).astimezone().replace(tzinfo=None)
    else:
        assert task.time == party_end - timedelta(milliseconds=1)


def test_started_clue_workflow_continues_into_exclusion_interval(shopping, monkeypatch):
    scheduler, _, state = shopping
    state.now = datetime.fromisoformat("2026-10-14T03:44:59+08:00")
    state.balance = 120
    state.products = [product()]
    clock = prepare_clue_dispatch(scheduler, state, monkeypatch)
    prepare_empty_clue_workflow(scheduler)
    # 在实际房间导航期间跨过 03:45，线索整理及购物仍继续完成。
    scheduler.enter_room.side_effect = lambda *_: setattr(
        state, "now", datetime.fromisoformat("2026-10-14T03:50:00+08:00")
    )
    scheduler.find.side_effect = lambda name, **_: (
        True if name == "control_central" else None
    )
    scheduler.task = SchedulerTask(time=clock.now(), task_type=TaskTypes.CLUE)
    scheduler.tasks = [scheduler.task]

    scheduler.infra_main()

    scheduler.read_party_time.assert_called_once_with()
    assert state.purchased == ["招聘许可"]
    assert scheduler.tasks == []
    assert scheduler.last_clue == clock.now()


@pytest.mark.parametrize("options", CONFIGURATIONS)
def test_clue_workflow_preserves_legacy_board_and_shop(shopping, monkeypatch, options):
    scheduler, _, state = shopping
    monkeypatch.setattr(config, "conf", credit_conf(options))
    scheduler.daily_visit_friend_attempt = None
    state.balance = 121
    state.products = [product()]
    scheduler._collect_clue_message_board = MagicMock()
    run_empty_clue_workflow(scheduler, state, monkeypatch)
    scheduler._collect_clue_message_board.assert_not_called()
    if options == (True,) * 5:
        scheduler._open_clue_message_board.assert_not_called()
        assert state.purchased == []
        assert "clue/message_board" not in [
            c.args[0] for c in scheduler.find.call_args_list
        ]
    else:
        scheduler._open_clue_message_board.assert_called_once_with()
        assert state.purchased == (["招聘许可"] if options[3] and options[4] else [])


@pytest.mark.parametrize(
    "now,expired",
    [
        ("2026-10-18T03:59:59+08:00", False),
        ("2026-10-18T04:00:00+08:00", True),
        ("2026-10-19T03:59:59+08:00", True),
        ("2026-10-19T04:00:00+08:00", False),
    ],
)
def test_expiry_collection_precedes_visit_gate(shopping, monkeypatch, now, expired):
    scheduler, _, state = shopping
    state.now = datetime.fromisoformat(now)
    scheduler.daily_visit_friend_attempt = None
    state.previous = 300
    state.products = [product()]

    def collect(*, collect_current):
        assert collect_current is False
        state.balance += state.previous
        state.previous = 0
        return True

    scheduler._collect_clue_message_board = MagicMock(side_effect=collect)
    run_empty_clue_workflow(scheduler, state, monkeypatch)
    assert scheduler._collect_clue_message_board.call_count == int(expired)
    assert state.balance == (300 if expired else 0)
    assert state.current == 300
    assert state.purchased == []


def main_runtime(monkeypatch):
    from arknights_mower import __main__ as main

    runtime = MagicMock()
    runtime.initialize_operators.return_value = None
    runtime.op_data.validate_backup_plans.return_value = {"success": True}
    runtime.op_data.mood_calculation_enabled = False
    runtime.op_data.mood_model = None
    runtime.op_data.operators = {}
    runtime.op_data.backup_plans = []
    runtime.op_data.all_dorms.return_value = []
    runtime.op_data.facility_states = {}
    runtime.op_data.room_observations = {}
    runtime.op_data.recall_recovery_rates = {}
    runtime.op_data.group_shift_state = {}
    runtime.op_data.group_recovery_full_members = {}
    runtime.op_data.group_recovery_return_time = {}
    runtime.op_data.urgent_recovery_supporters = {}
    runtime.op_data.idle_dorm_search_exhausted = False
    runtime.op_data.idle_dorm_search_stopped_at = None
    runtime.op_data.party_time = None
    runtime.waiting_group_shifts = []
    runtime._initial_mood_refresh_rooms = set()
    runtime.emergency_state = None
    runtime.tasks = []
    runtime.task_count = 0
    runtime.daily_visit_friend = runtime.daily_report = date.min
    runtime.daily_skland = runtime.daily_mail = date.min
    runtime.daily_visit_friend_attempt = None
    runtime.find_next_task.return_value = None
    runtime.has_maa_tasks.return_value = False
    runtime.rest_until_next_task.side_effect = MowerExit
    runtime._clue_credit_enabled = (
        base_schedule.BaseSchedulerSolver._clue_credit_enabled
    )
    runtime.visit_friend_plan_solver = (
        base_schedule.BaseSchedulerSolver.visit_friend_plan_solver.__get__(runtime)
    )
    monkeypatch.setattr(main, "initialize", MagicMock(return_value=runtime))
    monkeypatch.setattr(main, "base_scheduler", runtime)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", MagicMock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(
        "arknights_mower.solvers.trust_rotation.run_trust_rotation", MagicMock()
    )
    return main, runtime


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("cross_reset", [False, True])
def test_real_main_keeps_visit_entry_without_shopping(
    shopping, monkeypatch, active, cross_reset
):
    _, _, state = shopping
    config.conf.clue_credit_on_demand = active
    config.conf.maa_depot_enable = False
    config.conf.stage_plan_enable = False
    state.now = datetime.fromisoformat("2026-10-14T03:59:59+08:00")
    main, runtime = main_runtime(monkeypatch)

    def schedule():
        runtime.tasks = [
            base_schedule.SchedulerTask(time=datetime.now() + timedelta(minutes=20))
        ]

    runtime.run.side_effect = schedule
    runner = MagicMock()

    def visit():
        if cross_reset:
            state.now += timedelta(seconds=2)
        return True

    runner.run.side_effect = visit
    monkeypatch.setattr(base_schedule, "CreditSolver", MagicMock(return_value=runner))
    main.simulate(None)
    runner.run.assert_called_once_with()
    runtime._run_clue_shop.assert_not_called()
    runtime.rest_until_next_task.assert_called_once()
    assert runtime.daily_visit_friend == (
        date(2026, 10, 14) if cross_reset and not active else date(2026, 10, 13)
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_visit_attempt_round_trips_through_saved_state(
    shopping, monkeypatch, tmp_path, legacy
):
    import sqlite3

    from arknights_mower.solvers import record

    _, _, _ = shopping
    main, runtime = main_runtime(monkeypatch)
    runtime.daily_visit_friend_attempt = date(2026, 10, 13)
    runtime.defer_backup_plan_until_mood_read = False
    database = tmp_path / "saved.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE saved_state (time TEXT, state BLOB)")
    monkeypatch.setattr(record, "_conn", lambda: sqlite3.connect(database))
    assert record.save_current_state()
    saved = record.load_state()
    assert saved["daily_visit_friend_attempt"] == date(2026, 10, 13)
    if legacy:
        saved.pop("daily_visit_friend_attempt")
    runtime.daily_visit_friend_attempt = None

    class ReachedScheduling(BaseException):
        pass

    monkeypatch.setattr(
        main, "refresh_resource_at_boundary", MagicMock(side_effect=ReachedScheduling)
    )
    with pytest.raises(ReachedScheduling):
        main.simulate(saved)
    assert runtime.daily_visit_friend_attempt == (
        None if legacy else date(2026, 10, 13)
    )


@pytest.fixture
def shopping(monkeypatch):
    monkeypatch.setattr(
        config,
        "conf",
        Conf(
            maa_mall_enable=True,
            maa_mall_mode="mower",
            visit_friend_enable=True,
            visit_friend_mode="mower",
            clue_credit_on_demand=True,
            maa_mall_buy="招聘许可",
            maa_mall_blacklist="碳",
        ),
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(base_schedule, "save_current_state", MagicMock())
    state = SimpleNamespace(
        now=datetime.fromisoformat("2026-10-13T12:00:00+08:00"),
        balance=0,
        previous=0,
        current=300,
        daily=0,
        products=[],
        purchased=[],
        visits=[],
        scene=Scene.SHOP_CREDIT,
        selected=None,
    )

    class Clock:
        @staticmethod
        def now(tz):
            return state.now.astimezone(tz)

    monkeypatch.setattr(server_datetime, "datetime", Clock)
    shop = object.__new__(CreditShop)
    shop.recog = MagicMock()
    shop.check_current_focus = MagicMock()
    shop.scene = lambda: state.scene
    shop.credit_remain = lambda: state.balance
    shop.find = lambda name: (1, 1) if name == "shop_collect" and state.daily else None

    def product_info():
        shop.products = [
            product
            for product in state.products
            if product["name"] not in state.purchased
        ]

    def tap(position):
        if position == (1, 1):
            state.balance += state.daily
            state.daily = 0
        else:
            state.selected = next(p for p in state.products if p["touch"] == position)
            state.scene = Scene.SHOP_CREDIT_CONFIRM

    def confirm(name):
        assert name == "shop_cart"
        assert state.balance >= state.selected["price"]
        state.balance -= state.selected["price"]
        state.purchased.append(state.selected["name"])
        state.scene = Scene.SHOP_CREDIT

    shop.product_info = product_info
    shop.tap = tap
    shop.tap_element = confirm
    monkeypatch.setattr(base_schedule, "CreditShop", lambda *_: shop)
    monkeypatch.setattr(clue_credit, "CreditShop", lambda *_: shop)
    scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
    scheduler.daily_visit_friend = date.min
    scheduler.daily_visit_friend_attempt = server_datetime.get_server_time().date()
    scheduler._party_time = None
    scheduler.device = MagicMock()
    scheduler.recog = shop.recog
    scheduler.scene_graph_navigation = MagicMock()
    scheduler.visit_friend_plan_solver = MagicMock(
        side_effect=AssertionError("shopping cannot visit friends")
    )

    def visit(*, collect_current):
        state.visits.append(collect_current)
        state.balance += state.previous
        state.previous = 0
        if collect_current:
            state.balance += state.current
            state.current = 0
        return True

    scheduler._visit_clue_message_board = visit
    return scheduler, shop, state


def product(name="招聘许可", price=120, touch=(50, 100)):
    return {"name": name, "price": price, "touch": touch}


@pytest.fixture
def party_shopping(shopping, monkeypatch):
    scheduler, _, state = shopping
    state.now = datetime.fromisoformat("2026-10-13T12:00:00+08:00")
    scheduler._party_time = datetime.fromisoformat("2026-10-13T22:00:00+08:00")

    class Clock:
        @staticmethod
        def now(tz):
            return state.now.astimezone(tz)

    monkeypatch.setattr(server_datetime, "datetime", Clock)
    monkeypatch.setattr(
        base_schedule, "get_server_time", server_datetime.get_server_time
    )
    monkeypatch.setattr(
        base_schedule, "get_server_weekday", server_datetime.get_server_weekday
    )
    return shopping


def test_today_party_credit_covers_all_remaining_goods_without_claiming(party_shopping):
    scheduler, shop, state = party_shopping
    state.balance = 50
    state.products = [
        product(price=120),
        product("龙门币", 140, (100, 100)),
        product("碳", 500, (150, 100)),
    ]

    scheduler._run_clue_shop()

    assert state.visits == []
    assert state.purchased == []
    assert state.balance == 50
    assert state.current == 300
    assert shop.credit_deficit == 210

    # 交流实际结束、信用到账后，用真实余额买完剩余商品。
    scheduler._party_time = None
    state.now = state.now.replace(hour=22)
    state.balance += 210
    scheduler._run_clue_shop()

    assert state.purchased == ["招聘许可", "龙门币"]
    assert state.balance == 0
    assert state.visits == []
    assert shop.credit_deficit == 0


def test_party_credit_is_rechecked_after_collecting_old_credit(party_shopping):
    scheduler, _, state = party_shopping
    state.products = [product(price=400)]
    state.previous = 200

    scheduler._run_clue_shop()

    assert state.visits == [False]
    assert state.balance == 200
    assert state.current == 300
    assert state.purchased == []


@pytest.mark.parametrize(
    "end,expected_visits",
    [
        ("2026-10-14T03:44:59+08:00", []),
        ("2026-10-14T03:45:00+08:00", [False, True]),
        ("2026-10-14T03:45:01+08:00", [False, True]),
        ("2026-10-14T03:59:59+08:00", [False, True]),
        ("2026-10-14T04:00:00+08:00", [False, True]),
        ("2026-10-14T12:00:00+08:00", [False, True]),
        ("2026-10-13T11:59:59+08:00", [False, True]),
        ("2026-10-13T12:00:00+08:00", [False, True]),
        ("2026-10-13T19:45:00+00:00", [False, True]),
        ("2026-10-13T19:45:01+00:00", [False, True]),
        (None, [False, True]),
    ],
)
def test_party_income_requires_fifteen_minutes_before_next_reset(
    party_shopping, end, expected_visits
):
    scheduler, _, state = party_shopping
    scheduler._party_time = datetime.fromisoformat(end) if end else None
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.visits == expected_visits
    assert state.purchased == (["招聘许可"] if expected_visits else [])


@pytest.mark.parametrize(
    "now,end,wait_for_party",
    [
        ("2026-10-14T01:00:00+08:00", "2026-10-14T03:44:59+08:00", True),
        ("2026-10-14T03:50:00+08:00", "2026-10-14T03:55:00+08:00", False),
        ("2026-10-14T03:59:59+08:00", "2026-10-14T12:00:00+08:00", False),
        ("2026-10-14T04:00:00+08:00", "2026-10-14T12:00:00+08:00", True),
    ],
)
def test_party_income_uses_game_day_instead_of_calendar_date(
    party_shopping, now, end, wait_for_party
):
    scheduler, _, state = party_shopping
    state.now = datetime.fromisoformat(now)
    scheduler._party_time = datetime.fromisoformat(end)
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.visits == ([] if wait_for_party else [False, True])


def test_party_end_from_local_clock_is_compared_in_server_timezone(party_shopping):
    scheduler, _, state = party_shopping
    # read_party_time 返回本机时区的无时区时间。
    scheduler._party_time = scheduler._party_time.astimezone().replace(tzinfo=None)
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.visits == []
    assert state.purchased == []


def test_party_income_must_cover_the_sum_of_remaining_goods(party_shopping):
    scheduler, _, state = party_shopping
    state.balance = 50
    state.products = [product(price=120), product("龙门币", 141, (100, 100))]

    scheduler._run_clue_shop()

    # 缺口 211，虽然 210 能补足任意单件商品，却不能买完两件。
    assert state.visits == [False, True]
    assert state.purchased == ["招聘许可", "龙门币"]
    assert state.balance == 89


def test_waiting_for_party_still_buys_affordable_goods_now(party_shopping):
    scheduler, shop, state = party_shopping
    state.balance = 140
    state.products = [product(price=120), product("龙门币", 230, (100, 100))]

    scheduler._run_clue_shop()

    assert state.purchased == ["招聘许可"]
    assert state.balance == 20
    assert shop.credit_deficit == 210
    assert state.visits == []


def test_expired_party_time_cannot_defer_claims_forever(party_shopping):
    scheduler, _, state = party_shopping
    state.products = [product()]

    scheduler._run_clue_shop()
    assert state.visits == []

    # 到期后没有观察到新增余额，不把缓存的交流重复算作未来收入。
    state.now = state.now.replace(hour=22, minute=1)
    scheduler._run_clue_shop()

    assert state.visits == [False, True]
    assert state.purchased == ["招聘许可"]


def test_daily_shop_credit_is_spent_before_board_credit(shopping):
    scheduler, _, state = shopping
    state.daily = 120
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.purchased == ["招聘许可"]
    assert state.balance == 0
    assert state.visits == []


@pytest.mark.parametrize("priority", ["招聘许可", "碳"])
def test_blacklisted_product_never_triggers_claim(shopping, priority):
    scheduler, _, state = shopping
    config.conf.maa_mall_buy = priority
    config.conf.maa_mall_ignore_blacklist_when_full = True
    state.products = [product("碳")]

    scheduler._run_clue_shop()

    assert state.purchased == []
    assert state.visits == []


@pytest.mark.parametrize(
    "previous,current,expected_visits,expected_balance,expected_purchased",
    [
        (300, 300, [False], 180, ["招聘许可"]),
        (0, 300, [False, True], 180, ["招聘许可"]),
        (30, 300, [False, True], 210, ["招聘许可"]),
        (0, 0, [False, True], 0, []),
    ],
)
def test_shortage_uses_old_credit_before_current_and_stops(
    shopping, previous, current, expected_visits, expected_balance, expected_purchased
):
    scheduler, _, state = shopping
    state.previous, state.current = previous, current
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.visits == expected_visits
    assert state.balance == expected_balance
    assert state.purchased == expected_purchased
    assert state.current == (current if expected_visits == [False] else 0)
    scheduler.scene_graph_navigation.assert_called_with(Scene.INFRA_MAIN)


def test_failed_board_visit_is_not_retried_in_same_workflow(shopping):
    scheduler, _, state = shopping
    state.products = [product()]
    scheduler._visit_clue_message_board = MagicMock(return_value=False)

    scheduler._run_clue_shop()

    scheduler._visit_clue_message_board.assert_called_once_with(collect_current=False)
    assert state.purchased == []


@pytest.mark.parametrize("collect_current", [False, True])
def test_board_visit_only_presses_current_collection_when_requested(
    board_navigation, collect_current
):
    scheduler, _, state, ui, _ = board_navigation
    assert (
        scheduler._collect_clue_message_board(collect_current=collect_current) is True
    )

    assert ("claim" in ui.events) is collect_current
    assert state.current == (0 if collect_current else 300)
    scheduler.back.assert_called_once()


@pytest.mark.parametrize("opened", [False, True])
def test_unfinished_board_navigation_reports_failure(board_navigation, opened):
    scheduler, _, _, ui, warning = board_navigation
    ui.unknown_on_open = not opened
    ui.return_works = False

    assert scheduler._collect_clue_message_board(collect_current=False) is False

    assert [c.args[0] for c in scheduler.tap.call_args_list] == [
        (680, 1000),
        (500, 500),
    ]
    assert scheduler.back.call_count == int(opened)
    assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


@pytest.fixture
def board_navigation(shopping, monkeypatch):
    scheduler, shop, state = shopping
    del scheduler._visit_clue_message_board
    ui = SimpleNamespace(
        panel="room",
        automatic_popup=False,
        access_record=False,
        record_auto_closes=False,
        record_stuck=False,
        record_words=[
            ("访问记录", 0.99),
            ("ACCESS RECORDS", 0.99),
            ("2026.08.10——2026.08.17", 0.99),
            ("会客室上周共接待了32人", 0.99),
            ("总计获得300信用", 0.99),
        ],
        unknown_on_open=False,
        popup_stuck=False,
        claim_works=True,
        return_works=True,
        activation_works=True,
        activation_count=0,
        require_activation=False,
        entry_visible=True,
        open_failures=0,
        entry_actions=[],
        events=[],
    )

    def show(panel):
        ui.panel = panel
        state.scene = {
            "room": Scene.INFRA_DETAILS,
            "board": Scene.CLUE_MESSAGE_BOARD,
            "reward": Scene.MATERIEL,
            "record": Scene.UNKNOWN,
            "unknown": Scene.UNKNOWN,
        }[panel]

    def navigate(scene):
        state.scene = scene

    scheduler.scene_graph_navigation = MagicMock(side_effect=navigate)
    shop.scene_graph_navigation = navigate
    scheduler.enter_room = MagicMock(side_effect=lambda _: show("room"))
    scheduler.scene = lambda: state.scene
    scheduler.wait_product_complete = MagicMock()
    scheduler.sleep = MagicMock(
        side_effect=lambda _: (
            show("board") if ui.panel == "record" and ui.record_auto_closes else None
        )
    )
    scheduler.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)

    def ocr(_image, **_kwargs):
        words = ui.record_words if ui.panel == "record" else []
        return [[[], text, confidence] for text, confidence in words], None

    monkeypatch.setattr(base_schedule.rapidocr, "engine", ocr)

    def find(name):
        if name == "clue/message_board" and ui.panel == "room" and ui.entry_visible:
            return (500, 500)
        if name == "materiel_ico" and ui.panel == "reward":
            return (960, 80)
        if (
            name == "clue/message_board_collect"
            and ui.panel == "board"
            and state.current
        ):
            return (800, 800)
        return None

    def tap(position):
        if position == (500, 500):
            ui.events.append("open")
            ui.entry_actions.append("open")
            if ui.open_failures:
                ui.open_failures -= 1
                ui.entry_visible = False
                return
            if ui.require_activation and not ui.activation_count:
                return
            state.balance += state.previous
            state.previous = 0
            show(
                "unknown"
                if ui.unknown_on_open
                else "record"
                if ui.access_record
                else "reward"
                if ui.automatic_popup
                else "board"
            )
        elif position == (800, 800):
            ui.events.append("claim")
            if ui.claim_works:
                state.balance += state.current
                state.current = 0
                show("reward")
        elif position == (680, 1000) and ui.panel == "room":
            ui.entry_actions.append("activate")
            ui.activation_count += 1
            if ui.activation_works:
                ui.entry_visible = True
        elif position in ((680, 1000), (960, 960)):
            assert ui.panel == "reward"
            ui.events.append("dismiss")
            if not ui.popup_stuck:
                show("board")
        elif position == (960, 540):
            assert ui.panel == "record"
            ui.events.append("dismiss_record")
            if not ui.record_stuck:
                show("reward" if ui.automatic_popup else "board")
        else:
            pytest.fail(f"Unexpected board input: {position}")

    def back():
        ui.events.append("back")
        if ui.return_works:
            show("room")

    scheduler.find = find
    scheduler.tap = MagicMock(side_effect=tap)
    scheduler.back = MagicMock(side_effect=back)
    warning = MagicMock()
    monkeypatch.setattr(base_schedule.logger, "warning", warning)
    show("room")
    return scheduler, shop, state, ui, warning


def test_visible_board_entry_is_activated_before_click(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    ui.require_activation = True

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert ui.entry_actions == ["activate", "open"]
    assert state.current == 300


@pytest.mark.parametrize("failures", [0, 1, 2])
def test_legacy_workflow_uses_real_board_open_and_preserves_claim_policy(
    board_navigation, failures
):
    scheduler, _, state, ui, _ = board_navigation
    board_io = {
        name: getattr(scheduler, name)
        for name in ("scene", "find", "tap", "back", "sleep", "enter_room")
    }
    prepare_empty_clue_workflow(scheduler)
    del scheduler._open_clue_message_board
    for name, method in board_io.items():
        setattr(scheduler, name, method)
    scheduler._clue_credit_enabled = MagicMock(return_value=False)
    ui.open_failures = failures
    original_tap = scheduler.tap.side_effect

    def tap(position):
        if position == (330, 1000):
            # 进入后续线索整理前结束观测，信息板打开与领取均走真实调用路径。
            raise MowerExit
        original_tap(position)

    scheduler.tap.side_effect = tap
    with pytest.raises(MowerExit):
        scheduler.clue_new()

    opened = failures < 2
    assert ui.activation_count == min(failures + 1, 2)
    assert ui.events == ["open"] * min(failures + 1, 2) + (
        ["claim", "dismiss", "back"] if opened else []
    )
    assert state.current == (0 if opened else 300)


def test_already_open_board_is_not_activated_again(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    ui.panel = "board"
    state.scene = Scene.CLUE_MESSAGE_BOARD

    assert scheduler._collect_clue_message_board(collect_current=False) is True
    assert ui.entry_actions == []
    assert ui.events == ["back"]


def test_failed_board_click_is_recovered_after_fresh_activation(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    ui.open_failures = 1
    state.previous = 300

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert ui.entry_actions == ["activate", "open", "activate", "open"]
    assert ui.events == ["open", "open", "back"]
    assert state.balance == 300
    assert state.current == 300


def test_recovery_relocates_the_entry_instead_of_reusing_old_coordinates(
    board_navigation,
):
    scheduler, _, _, ui, _ = board_navigation
    ui.open_failures = 1
    original_find = scheduler.find
    original_tap = scheduler.tap.side_effect

    def find(name):
        if name == "clue/message_board" and ui.panel == "room" and ui.entry_visible:
            return (600, 500) if ui.activation_count >= 2 else (500, 500)
        return original_find(name)

    def tap(position):
        if position == (500, 500) and ui.activation_count >= 2:
            pytest.fail("Recovery reused the stale entry coordinates")
        original_tap((500, 500) if position == (600, 500) else position)

    scheduler.find = find
    scheduler.tap.side_effect = tap

    assert scheduler._collect_clue_message_board(collect_current=False) is True
    assert [c.args[0] for c in scheduler.tap.call_args_list] == [
        (680, 1000),
        (500, 500),
        (680, 1000),
        (600, 500),
    ]


def test_board_open_recovery_is_bounded_and_does_not_claim(board_navigation):
    scheduler, _, state, ui, warning = board_navigation
    ui.open_failures = 2

    assert scheduler._collect_clue_message_board(collect_current=True) is False

    assert ui.entry_actions == ["activate", "open", "activate", "open"]
    assert ui.events == ["open", "open"]
    assert state.current == 300
    assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


def test_expired_visible_entry_is_reactivated_before_opening(board_navigation):
    scheduler, _, _, ui, _ = board_navigation
    original_tap = scheduler.tap.side_effect

    def tap(position):
        original_tap(position)
        if position == (680, 1000) and ui.activation_count == 1:
            ui.entry_visible = False

    scheduler.tap.side_effect = tap

    assert scheduler._collect_clue_message_board(collect_current=False) is True
    assert ui.entry_actions == ["activate", "activate", "open"]


def test_missing_entry_without_change_does_not_repeat_activation(board_navigation):
    scheduler, _, _, ui, _ = board_navigation
    ui.entry_visible = False
    ui.activation_works = False

    assert scheduler._collect_clue_message_board(collect_current=False) is False
    assert ui.entry_actions == ["activate"]
    assert ui.events == []


@pytest.mark.parametrize("stuck", [False, True])
@pytest.mark.parametrize("collect_current", [False, True])
def test_residence_panel_closes_before_furniture_activation(
    board_navigation, stuck, collect_current
):
    scheduler, _, state, ui, warning = board_navigation
    # captain 在 2026-10-19 15:44:44 和 15:44:46 保存的侧栏关闭前后原始截图。
    frames = Path(__file__).parent / "fixtures" / "clue"
    panels = {
        True: Recognizer(
            None, (frames / "clue_reception_residents_20261019.jpg").read_bytes()
        ),
        False: Recognizer(
            None, (frames / "clue_reception_room_20261019.jpg").read_bytes()
        ),
    }
    assert panels[True].find("room_detail") is not None
    assert panels[False].find("room_detail") is None
    ui.residents = True
    ui.entry_visible = False
    original_find = scheduler.find
    original_tap = scheduler.tap.side_effect

    def find(name):
        if name == "room_detail" and ui.panel == "room":
            return panels[ui.residents].find(name)
        return original_find(name)

    def tap(position):
        if position == (680, 1000) and ui.residents:
            ui.entry_actions.append("close_residents")
            if not stuck:
                ui.residents = False
            return
        original_tap(position)

    scheduler.find = find
    scheduler.tap.side_effect = tap

    assert scheduler._collect_clue_message_board(collect_current=collect_current) is (
        not stuck
    )
    assert ui.entry_actions == ["close_residents"] + (
        [] if stuck else ["activate", "open"]
    )
    assert state.current == (0 if collect_current and not stuck else 300)
    assert ui.events == (
        []
        if stuck
        else ["open"] + (["claim", "dismiss"] if collect_current else []) + ["back"]
    )
    if stuck:
        assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


@pytest.mark.parametrize("scene", [Scene.UNKNOWN, Scene.MATERIEL, Scene.INFRA_MAIN])
def test_board_open_does_not_activate_outside_room(board_navigation, scene):
    scheduler, _, state, ui, _ = board_navigation
    state.scene = scene

    assert scheduler._collect_clue_message_board(collect_current=False) is False
    assert ui.entry_actions == []


def test_stuck_record_over_room_does_not_trigger_open_recovery(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    ui.access_record = True
    ui.record_stuck = True
    scheduler.scene = lambda: (
        Scene.INFRA_DETAILS if ui.panel == "record" else state.scene
    )

    assert scheduler._collect_clue_message_board(collect_current=False) is False
    assert ui.entry_actions == ["activate", "open"]
    assert ui.events == ["open", "dismiss_record"]


@pytest.mark.parametrize("error", [RuntimeError("input failed"), MowerExit()])
def test_board_open_input_error_propagates_without_recovery(board_navigation, error):
    scheduler, _, _, ui, _ = board_navigation
    original_tap = scheduler.tap.side_effect

    def tap(position):
        original_tap(position)
        raise error

    scheduler.tap.side_effect = tap

    with pytest.raises(type(error)):
        scheduler._collect_clue_message_board(collect_current=False)
    assert ui.entry_actions == ["activate"]


def test_automatic_settlement_popup_is_closed_without_claiming_current(
    board_navigation,
):
    scheduler, _, state, ui, _ = board_navigation
    ui.automatic_popup = True
    state.previous = 300

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert state.balance == 300
    assert state.current == 300
    assert ui.events == ["open", "dismiss", "back"]


def test_settlement_popup_may_cover_a_recognizable_board(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    ui.automatic_popup = True
    scheduler.scene = lambda: (
        Scene.CLUE_MESSAGE_BOARD if ui.panel == "reward" else state.scene
    )

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert ui.events == ["open", "dismiss", "back"]
    assert state.current == 300


@pytest.mark.parametrize(
    "filename,resize,expected",
    [
        ("clue_access_record_video.png", False, True),
        ("clue_access_record_video.png", True, True),
        ("clue_live_room_details.png", False, False),
    ],
)
def test_access_record_real_ocr_on_screenshots(monkeypatch, filename, resize, expected):
    frame = bytes2img(
        (Path(__file__).parent / "fixtures" / "clue" / filename).read_bytes()
    )
    if resize:
        # 视频截帧并非标准画面帧；额外验证缩放到运行时尺寸后的识别。
        frame = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_AREA)
    monkeypatch.setattr(rapidocr, "engine", create_engine())
    scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
    scheduler.recog = SimpleNamespace(img=frame)

    assert scheduler._clue_access_record_visible() is expected


@pytest.mark.parametrize("automatic", [False, True])
def test_access_record_waits_or_dismisses_without_claiming_current(
    board_navigation, automatic
):
    scheduler, _, state, ui, _ = board_navigation
    ui.access_record = True
    ui.record_auto_closes = automatic
    state.previous = 300
    state.current = 60

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert state.balance == 300
    assert state.current == 60
    assert ui.events == (
        ["open", "back"] if automatic else ["open", "dismiss_record", "back"]
    )


def test_access_record_is_checked_before_underlying_board(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    ui.access_record = True
    scheduler.scene = lambda: (
        Scene.CLUE_MESSAGE_BOARD if ui.panel == "record" else state.scene
    )

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert ui.events == ["open", "dismiss_record", "back"]


@pytest.mark.parametrize("title", ["访 问 记 录", "Access Records"])
def test_access_record_does_not_depend_on_date_or_credit_amount(
    board_navigation, title
):
    scheduler, _, _, ui, _ = board_navigation
    ui.access_record = True
    ui.record_words = [
        (title, 0.95),
        ("2027.01.04——2027.01.11", 0.9),
        ("会客室 上周 共接待了 99 人", 0.95),
        ("总计 获得 600 信用", 0.9),
    ]

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert ui.events == ["open", "dismiss_record", "back"]


def test_access_record_and_material_reward_can_both_be_closed(board_navigation):
    scheduler, _, _, ui, _ = board_navigation
    ui.access_record = True
    ui.automatic_popup = True

    assert scheduler._collect_clue_message_board(collect_current=False) is True

    assert ui.events == ["open", "dismiss_record", "dismiss", "back"]


def test_unchanged_access_record_is_dismissed_only_once(board_navigation):
    scheduler, _, _, ui, warning = board_navigation
    ui.access_record = True
    ui.record_stuck = True

    assert scheduler._collect_clue_message_board(collect_current=False) is False

    assert ui.events == ["open", "dismiss_record"]
    assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


def test_shopping_uses_credit_after_access_record_without_claiming_current(
    board_navigation,
):
    scheduler, _, state, ui, _ = board_navigation
    ui.access_record = True
    state.previous = 300
    state.current = 60
    state.products = [product()]

    scheduler._run_clue_shop()

    assert state.balance == 180
    assert state.current == 60
    assert state.purchased == ["招聘许可"]
    assert ui.events == ["open", "dismiss_record", "back"]


@pytest.mark.parametrize(
    "words",
    [
        [("访问记录", 0.99)],
        [("会客室上周共接待了32人", 0.99), ("总计获得300信用", 0.99)],
        [("访问人次 本周2 本日2", 0.99), ("每周可获取访客信用0/300", 0.99)],
        [("访问记录", 0.99), ("一个人访问你，就能攒30信用点每周上限是300", 0.99)],
        [
            ("访问记录", 0.4),
            ("会客室上周共接待了32人", 0.99),
            ("总计获得300信用", 0.99),
        ],
    ],
)
def test_incomplete_or_uncertain_access_record_text_does_not_trigger_clicks(
    board_navigation, words
):
    scheduler, _, _, ui, _ = board_navigation
    ui.access_record = True
    ui.record_words = words

    assert scheduler._collect_clue_message_board(collect_current=False) is False

    assert ui.events == ["open"]


@pytest.mark.parametrize("collect_current", [False, True])
def test_real_board_navigation_returns_to_infra(board_navigation, collect_current):
    scheduler, _, state, ui, _ = board_navigation

    assert scheduler._visit_clue_message_board(collect_current=collect_current) is True

    assert state.scene == Scene.INFRA_MAIN
    assert ui.events == (
        ["open", "claim", "dismiss", "back"] if collect_current else ["open", "back"]
    )


def test_unchanged_collect_button_is_not_reported_as_success(board_navigation):
    scheduler, _, state, ui, warning = board_navigation
    ui.claim_works = False

    assert scheduler._collect_clue_message_board(collect_current=True) is False

    assert state.current == 300
    assert state.balance == 0
    assert ui.events == ["open", "claim", "back"]
    assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


def test_one_missing_button_frame_does_not_confirm_collection(board_navigation):
    scheduler, _, _, ui, _ = board_navigation
    ui.claim_works = False
    original_find = scheduler.find
    missing_frame = False

    def find(name):
        nonlocal missing_frame
        if name == "clue/message_board_collect" and "claim" in ui.events:
            if not missing_frame:
                missing_frame = True
                return None
        return original_find(name)

    scheduler.find = find

    assert scheduler._collect_clue_message_board(collect_current=True) is False
    assert ui.events == ["open", "claim", "back"]


@pytest.mark.parametrize("collect_current", [False, True])
def test_stuck_reward_does_not_repeat_dismissal_or_report_success(
    board_navigation, collect_current
):
    scheduler, _, _, ui, warning = board_navigation
    ui.automatic_popup = not collect_current
    ui.popup_stuck = True

    assert (
        scheduler._collect_clue_message_board(collect_current=collect_current) is False
    )

    assert ui.events == (
        ["open", "claim", "dismiss"] if collect_current else ["open", "dismiss"]
    )
    assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


def test_unknown_settlement_page_archives_without_clicking_claim(board_navigation):
    scheduler, _, _, ui, warning = board_navigation
    ui.unknown_on_open = True

    assert scheduler._collect_clue_message_board(collect_current=False) is False

    assert ui.events == ["open"]
    assert warning.call_args.kwargs["extra"]["archive_screenshots"] is True


@pytest.mark.parametrize("unknown", [False, True])
def test_automatic_credit_is_spent_even_if_board_page_is_unrecognized(
    board_navigation, unknown
):
    scheduler, _, state, ui, _ = board_navigation
    state.previous = 300
    state.products = [product()]
    ui.automatic_popup = True
    ui.unknown_on_open = unknown

    scheduler._run_clue_shop()

    assert state.purchased == ["招聘许可"]
    assert state.balance == 180
    assert state.current == 300
    assert ui.events.count("open") == 1
    assert "claim" not in ui.events


def test_unknown_settlement_page_cannot_trigger_current_week_claim(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    state.previous = 30
    state.products = [product()]
    ui.unknown_on_open = True

    scheduler._run_clue_shop()

    assert state.purchased == []
    assert state.balance == 30
    assert state.current == 300
    assert ui.events == ["open"]


def test_unconfirmed_current_claim_still_rechecks_actual_shop_balance(board_navigation):
    scheduler, _, state, ui, _ = board_navigation
    state.products = [product()]
    ui.popup_stuck = True

    scheduler._run_clue_shop()

    assert state.purchased == ["招聘许可"]
    assert state.balance == 180
    assert state.current == 0
    assert ui.events == ["open", "back", "open", "claim", "dismiss"]
