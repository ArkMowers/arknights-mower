import sys
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402


@pytest.fixture
def scheduler(monkeypatch):
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.device = MagicMock()
    instance.recog = Recognizer(instance.device)
    instance.MAA = MagicMock()
    instance.MAA.get_version.return_value = "v6.17.3"
    instance.MAA.append_task.return_value = 1
    instance.MAA.running.return_value = False
    instance.last_execution = {"maa": None, "recruit": None, "todo": None}
    instance.credit_fight = None
    instance.stages = []
    instance.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(hours=1), plan={})
    ]
    instance.back_to_index = MagicMock()
    instance.initialize_maa = MagicMock()
    instance.rest_until_next_task = MagicMock()
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    return instance


def test_has_maa_tasks_true_when_maa_stage_plan_enabled(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(stage_plan_enable=True, stage_plan_runner="maa", maa_mall_enable=False),
    )
    assert scheduler.has_maa_tasks() is True


def test_has_maa_tasks_true_when_mall_enabled(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(stage_plan_enable=False, stage_plan_runner="maa", maa_mall_enable=True),
    )
    assert scheduler.has_maa_tasks() is True


def test_has_maa_tasks_false_when_all_maa_tasks_disabled(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=False,
            stage_plan_runner="mower",
            maa_mall_enable=False,
            visit_friend_enable=False,
            maa_mail=False,
            maa_recruit=False,
            maa_orundum=False,
            maa_mining=False,
            maa_specialaccess=False,
        ),
    )
    assert scheduler.has_maa_tasks() is False


def test_maa_plan_solver_omits_fight_when_stage_plan_disabled(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=False,
            stage_plan_runner="maa",
            maa_mall_enable=True,
            visit_friend_enable=False,
        ),
    )
    order = MagicMock()
    order.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.append_maa_task = MagicMock(side_effect=lambda task: order.append(task))

    scheduler.maa_plan_solver()

    assert "Fight" not in [c.args[0] for c in order.append.mock_calls]
    assert "Mall" in [c.args[0] for c in order.append.mock_calls]


def test_maa_plan_solver_omits_fight_when_runner_is_mower(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=True,
            stage_plan_runner="mower",
            maa_mall_enable=True,
            visit_friend_enable=False,
        ),
    )
    order = MagicMock()
    order.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.append_maa_task = MagicMock(side_effect=lambda task: order.append(task))

    scheduler.maa_plan_solver()

    assert "Fight" not in [c.args[0] for c in order.append.mock_calls]


def test_maa_plan_solver_includes_fight_when_runner_is_maa(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(stage_plan_enable=True, stage_plan_runner="maa", maa_mall_enable=True),
    )
    order = MagicMock()
    order.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.append_maa_task = MagicMock(side_effect=lambda task: order.append(task))

    scheduler.maa_plan_solver()

    assert "Fight" in [c.args[0] for c in order.append.mock_calls]


def test_maa_plan_solver_skips_when_has_maa_tasks_is_false(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=False,
            stage_plan_runner="mower",
            maa_mall_enable=False,
            visit_friend_enable=False,
            maa_mail=False,
            maa_recruit=False,
            maa_orundum=False,
            maa_mining=False,
            maa_specialaccess=False,
        ),
    )
    scheduler.maa_plan_solver()
    scheduler.initialize_maa.assert_not_called()


def test_has_maa_tasks_false_when_mall_mode_is_mower_and_others_disabled(
    scheduler, monkeypatch
):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=False,
            stage_plan_runner="mower",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            visit_friend_enable=False,
            maa_mail=False,
            maa_recruit=False,
            maa_orundum=False,
            maa_mining=False,
            maa_specialaccess=False,
        ),
    )
    assert scheduler.has_maa_tasks() is False


def test_has_maa_tasks_true_when_only_visit_friend_mode_is_maa(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=False,
            stage_plan_runner="mower",
            maa_mall_enable=False,
            visit_friend_enable=True,
            visit_friend_mode="maa",
            maa_mail=False,
            maa_recruit=False,
            maa_orundum=False,
            maa_mining=False,
            maa_specialaccess=False,
        ),
    )
    assert scheduler.has_maa_tasks() is True


def test_maa_plan_solver_omits_mall_when_mode_is_mower_and_visit_friend_not_maa(
    scheduler, monkeypatch
):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=True,
            stage_plan_runner="maa",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            visit_friend_mode="mower",
        ),
    )
    order = MagicMock()
    order.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.append_maa_task = MagicMock(side_effect=lambda task: order.append(task))

    scheduler.maa_plan_solver()

    assert "Fight" in [c.args[0] for c in order.append.mock_calls]
    assert "Mall" not in [c.args[0] for c in order.append.mock_calls]


def test_maa_plan_solver_includes_mall_for_visit_friends_when_mall_mode_is_mower(
    scheduler, monkeypatch
):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            stage_plan_enable=True,
            stage_plan_runner="maa",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            visit_friend_enable=True,
            visit_friend_mode="maa",
        ),
    )
    order = MagicMock()
    order.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.append_maa_task = MagicMock(side_effect=lambda task: order.append(task))

    scheduler.maa_plan_solver()

    assert "Fight" in [c.args[0] for c in order.append.mock_calls]
    assert "Mall" in [c.args[0] for c in order.append.mock_calls]


def test_append_maa_task_mall_shopping_flag(scheduler, monkeypatch):
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            maa_mall_enable=True,
            maa_mall_mode="mower",
            visit_friend_enable=False,
        ),
    )
    scheduler.append_maa_task("Mall")
    assert scheduler.MAA.append_task.call_args[0][0] == "Mall"
    assert scheduler.MAA.append_task.call_args[0][1]["shopping"] is False

    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            maa_mall_enable=True,
            maa_mall_mode="maa",
            visit_friend_enable=False,
        ),
    )
    scheduler.append_maa_task("Mall")
    assert scheduler.MAA.append_task.call_args[0][1]["shopping"] is True


def test_run_clue_shop_conditional_execution(scheduler, monkeypatch):
    mock_shop = MagicMock()
    monkeypatch.setattr(base_schedule, "CreditShop", mock_shop)
    scheduler.scene_graph_navigation = MagicMock()

    # 1. enabled + mower -> runs CreditShop
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(maa_mall_enable=True, maa_mall_mode="mower"),
    )
    scheduler._run_clue_shop()
    assert mock_shop.call_count == 1
    scheduler.scene_graph_navigation.assert_called_once_with(Scene.INFRA_MAIN)

    # 2. enabled + maa -> does NOT run CreditShop
    mock_shop.reset_mock()
    scheduler.scene_graph_navigation.reset_mock()
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(maa_mall_enable=True, maa_mall_mode="maa"),
    )
    scheduler._run_clue_shop()
    mock_shop.assert_not_called()
    scheduler.scene_graph_navigation.assert_not_called()

    # 3. disabled + mower -> does NOT run CreditShop
    mock_shop.reset_mock()
    scheduler.scene_graph_navigation.reset_mock()
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(maa_mall_enable=False, maa_mall_mode="mower"),
    )
    scheduler._run_clue_shop()
    mock_shop.assert_not_called()
    scheduler.scene_graph_navigation.assert_not_called()


def test_conf_helper_properties():
    c1 = Conf(stage_plan_enable=True, stage_plan_runner="maa")
    assert c1.should_run_maa_stage_plan is True
    assert c1.should_run_mower_stage_plan is False

    c2 = Conf(stage_plan_enable=True, stage_plan_runner="mower")
    assert c2.should_run_maa_stage_plan is False
    assert c2.should_run_mower_stage_plan is True

    c3 = Conf(stage_plan_enable=False, stage_plan_runner="maa")
    assert c3.should_run_maa_stage_plan is False
    assert c3.should_run_mower_stage_plan is False

    c4 = Conf(maa_mall_enable=True, maa_mall_mode="maa")
    assert c4.should_run_maa_mall is True
    assert c4.should_run_mower_mall is False

    c5 = Conf(maa_mall_enable=True, maa_mall_mode="mower")
    assert c5.should_run_maa_mall is False
    assert c5.should_run_mower_mall is True

    c6 = Conf(maa_mall_enable=False, maa_mall_mode="maa")
    assert c6.should_run_maa_mall is False
    assert c6.should_run_mower_mall is False

    c7 = Conf(
        maa_mall_enable=False,
        visit_friend_enable=True,
        visit_friend_mode="maa",
    )
    assert c7.should_run_maa_visit_friend is True
    assert c7.should_run_maa_mall_task is True

    c8 = Conf(
        maa_mall_enable=False,
        visit_friend_enable=True,
        visit_friend_mode="mower",
    )
    assert c8.should_run_maa_visit_friend is False
    assert c8.should_run_maa_mall_task is False


def test_maa_plan_solver_skips_when_next_task_within_5_minutes(scheduler, monkeypatch):
    scheduler.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(seconds=120), plan={})
    ]
    monkeypatch.setattr(scheduler, "has_maa_daily_tasks", lambda: True)
    scheduler.initialize_maa = MagicMock()
    scheduler.maa_plan_solver()
    scheduler.initialize_maa.assert_not_called()


def test_mower_plan_solver_does_not_rest_until_next_task(scheduler, monkeypatch):
    scheduler.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(minutes=10), plan={})
    ]
    monkeypatch.setattr(
        scheduler,
        "run_local_operation_stage",
        MagicMock(
            return_value={
                "simulated_current_ap": 100,
                "executed_any": False,
                "should_break": True,
            }
        ),
    )
    monkeypatch.setattr(base_schedule, "MissionSolver", MagicMock())
    scheduler.rest_until_next_task = MagicMock()
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(stage_plan_enable=True, stage_plan_runner="mower", maa_gap=4),
    )
    scheduler.mower_plan_solver()
    scheduler.rest_until_next_task.assert_not_called()
