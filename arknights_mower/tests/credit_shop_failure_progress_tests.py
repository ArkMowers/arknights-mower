"""购物观测失败保留原流程，只在相关成功观测后继续剩余购物。"""

import pickle
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.shop import CreditShop, CreditShopIncomplete
from arknights_mower.tests.clue_credit_tests import (
    prepare_clue_dispatch,
    prepare_empty_clue_workflow,
)
from arknights_mower.tests.clue_credit_tests import shopping as shopping
from arknights_mower.utils import config
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

FIXTURES = Path(__file__).parent / "fixtures" / "credit_shop"


def shop_frame(filename, scene=Scene.SHOP_CREDIT):
    recog = Recognizer(None, (FIXTURES / filename).read_bytes())
    recog.get_scene = MagicMock(return_value=scene)
    return recog


def incomplete():
    return CreditShopIncomplete(
        "信用商店物资领取尚未确认完成",
        pending_reward={
            "kind": "collect",
            "dismissed": True,
            "touch": None,
            "before_balance": 490,
            "price": None,
        },
        observation={
            "scene": Scene.SHOP_CREDIT,
            "balance": 582,
            "products": None,
            "collectable": False,
        },
    )


@pytest.fixture
def dispatch(shopping, monkeypatch):
    scheduler, shop, state = shopping
    clock = prepare_clue_dispatch(scheduler, state, monkeypatch)
    monkeypatch.setattr(base_schedule, "CreditShop", CreditShop)
    config.conf.clue_credit_on_demand = False
    scheduler.task = None
    scheduler.tasks = []
    scheduler.skip = MagicMock()
    scheduler.handle_error = MagicMock()
    scheduler.planned = True
    scheduler.todo_task = True
    scheduler.collect_notification = True
    scheduler.last_clue = clock.now() - timedelta(hours=2)
    scheduler.recog = shop_frame("shop_particles_20261031_071524.jpg")
    return scheduler, shop, state, clock


@pytest.mark.parametrize("kind", [TaskTypes.CLUE, TaskTypes.CLUE_PARTY])
def test_dispatch_retains_original_clue_work_and_releases_only_for_readable_shop(
    dispatch, monkeypatch, kind
):
    scheduler, _, state, clock = dispatch
    task = SchedulerTask(time=clock.now() - timedelta(minutes=20), task_type=kind)
    original_time = task.time
    previous_check = scheduler.last_clue
    scheduler.task = task
    scheduler.tasks = [task]
    scheduler.clue_new = MagicMock(side_effect=incomplete())
    run_shop = MagicMock(return_value=True)
    monkeypatch.setattr(CreditShop, "run", run_shop)

    scheduler.infra_main()

    assert scheduler.tasks == [task]
    assert scheduler.tasks[0] is task
    assert task.time == original_time
    assert scheduler.last_clue == previous_check
    assert task.execution_failure["dependency"] is True
    assert not getattr(task, "clue_access_record_pending", False)
    assert task.credit_shop_continuation["reward"] is task.credit_shop_pending["reward"]
    run_shop.assert_not_called()

    for _ in range(2):
        state.now += timedelta(minutes=5)
        scheduler.task = task
        scheduler.infra_main()
        assert task.execution_failure
        assert task.time == original_time
        assert scheduler.last_clue == previous_check
        assert scheduler.tasks == [task]
    scheduler.clue_new.assert_called_once_with()
    run_shop.assert_not_called()

    independent = SchedulerTask(time=clock.now(), task_type=TaskTypes.NOT_SPECIFIC)
    scheduler.tasks.append(independent)
    scheduler.task = independent
    scheduler.infra_main()
    assert scheduler.tasks == [task]
    assert task.execution_failure

    scheduler.recog = shop_frame("shop_ready_20261031_071521.jpg")
    scheduler._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert scheduler.tasks[0] is task
    assert task.time == original_time
    reward = task.credit_shop_continuation["reward"]
    scheduler.task = task
    scheduler.infra_main()

    run_shop.assert_called_once_with(resume=reward)
    scheduler.clue_new.assert_called_once_with()
    assert scheduler.tasks == []
    assert scheduler.last_clue == clock.now()
    assert not hasattr(task, "credit_shop_pending")
    assert not hasattr(task, "credit_shop_continuation")
    assert not config.stop_mower.is_set()


def test_retained_shop_context_survives_task_persistence(dispatch):
    scheduler, _, _, clock = dispatch
    task = SchedulerTask(time=clock.now(), task_type=TaskTypes.DAILY)
    task.manual_steps = [
        TaskTypes.CREDIT_SHOP.display_value,
        TaskTypes.MISSION.display_value,
    ]
    scheduler._retain_credit_shop_failure(task, incomplete())

    restored = pickle.loads(pickle.dumps(task))
    scheduler.tasks = [restored]
    scheduler._resume_failed_tasks()

    assert restored.time == task.time
    assert restored.manual_steps == task.manual_steps
    assert restored.execution_failure == task.execution_failure
    assert restored.credit_shop_pending == task.credit_shop_pending
    assert (
        restored.credit_shop_continuation["reward"]
        is restored.credit_shop_pending["reward"]
    )
    scheduler.recog = shop_frame("shop_ready_20261031_071521.jpg")
    scheduler._resume_failed_tasks()
    assert not getattr(restored, "execution_failure", None)
    assert restored.manual_steps == task.manual_steps


def test_initial_clue_flow_rethrows_shop_failure(dispatch):
    scheduler, _, _, _ = dispatch
    prepare_empty_clue_workflow(scheduler)
    scheduler._run_clue_shop = MagicMock(side_effect=incomplete())
    with pytest.raises(CreditShopIncomplete):
        scheduler.clue_new()


def test_periodic_clue_keeps_one_original_shopping_continuation(dispatch):
    scheduler, _, state, clock = dispatch
    scheduler.op_data = SimpleNamespace(run_order_rooms={})
    scheduler.enable_party = True
    scheduler.todo_task = False
    scheduler.drone_room = None
    scheduler.drone_time = None
    scheduler.reload_time = clock.now()
    scheduler.no_pending_task = MagicMock(return_value=True)
    scheduler._clue_flow_resume_time = MagicMock(return_value=None)
    scheduler.clue_new = MagicMock(side_effect=incomplete())
    previous_check = scheduler.last_clue
    started_at = clock.now()

    scheduler.infra_main()

    assert len(scheduler.tasks) == 1
    task = scheduler.tasks[0]
    assert task.type == TaskTypes.CLUE
    assert task.time == started_at
    assert task.credit_shop_continuation["on_demand"] is False
    assert task.execution_failure
    assert scheduler.last_clue == previous_check

    for _ in range(2):
        state.now += timedelta(minutes=5)
        scheduler.todo_task = False
        scheduler.reload_time = clock.now()
        scheduler.infra_main()
    scheduler.clue_new.assert_called_once_with()
    assert scheduler.tasks == [task]
    assert task.time == started_at
    assert scheduler.last_clue == previous_check


def test_started_shop_continuation_keeps_time_during_new_flow_exclusion(
    dispatch, monkeypatch
):
    scheduler, _, _, clock = dispatch
    task = SchedulerTask(
        time=clock.now() - timedelta(minutes=20), task_type=TaskTypes.CLUE
    )
    scheduler._retain_credit_shop_failure(task, incomplete())
    scheduler.tasks = [task]
    scheduler.recog = shop_frame("shop_ready_20261031_071521.jpg")
    scheduler._resume_failed_tasks()
    original_time = task.time
    scheduler.task = task
    scheduler._clue_flow_resume_time = MagicMock(
        return_value=clock.now() + timedelta(minutes=15)
    )
    run_shop = MagicMock(return_value=True)
    monkeypatch.setattr(CreditShop, "run", run_shop)

    scheduler.infra_main()

    run_shop.assert_called_once()
    assert task.time == original_time
    assert scheduler.tasks == []
    scheduler._clue_flow_resume_time.assert_not_called()


@pytest.mark.parametrize("kind", [TaskTypes.CREDIT_SHOP, TaskTypes.DAILY])
def test_manual_dispatch_does_not_consume_unfinished_shopping_step(
    dispatch, monkeypatch, kind
):
    scheduler, _, _, clock = dispatch
    task = SchedulerTask(time=clock.now() - timedelta(minutes=20), task_type=kind)
    task.manual_steps = [
        TaskTypes.CREDIT_SHOP.display_value,
        TaskTypes.MISSION.display_value,
    ]
    original_steps = list(task.manual_steps)
    original_time = task.time
    scheduler.task = task
    scheduler.tasks = [task]
    previous_check = scheduler.last_clue
    monkeypatch.setattr(CreditShop, "run", MagicMock(side_effect=incomplete()))

    scheduler.infra_main()

    assert scheduler.tasks == [task]
    assert task.time == original_time
    assert task.manual_steps == original_steps
    assert task.execution_failure["dependency"] is True
    assert task.credit_shop_continuation["on_demand"] is False
    assert not getattr(task, "clue_access_record_pending", False)
    assert scheduler.last_clue == previous_check
    assert not config.stop_mower.is_set()


def test_resumed_shop_board_failure_uses_access_record_dependency(dispatch):
    scheduler, _, _, clock = dispatch
    task = SchedulerTask(time=clock.now(), task_type=TaskTypes.CLUE)
    error = incomplete()
    error.continuation = {"on_demand": True, "stage": 1, "settlement_checked": True}
    scheduler._retain_credit_shop_failure(task, error)
    del task.execution_failure
    scheduler.task = task
    scheduler.tasks = [task]
    scheduler._run_clue_shop = MagicMock(return_value=False)
    scheduler._clue_access_record_visible = MagicMock(return_value=True)
    scheduler._clue_access_record_cleared = MagicMock(return_value=False)
    previous_check = scheduler.last_clue

    assert scheduler._run_clue_flow() is False

    assert task.clue_access_record_pending is True
    assert not hasattr(task, "credit_shop_pending")
    assert task.credit_shop_continuation["stage"] == 1
    assert task.execution_failure["snapshot"] == {"access_record_visible": True}
    scheduler._resume_failed_tasks()
    assert task.execution_failure

    scheduler._clue_access_record_cleared.return_value = True
    scheduler._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert not getattr(task, "clue_access_record_pending", False)
    assert task.credit_shop_continuation["stage"] == 1
    assert scheduler.last_clue == previous_check
