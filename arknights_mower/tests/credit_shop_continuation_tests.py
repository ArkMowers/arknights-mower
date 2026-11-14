import json
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import clue_credit, manual_tasks
from arknights_mower.solvers import shop as shop_module
from arknights_mower.solvers.shop import CreditShopIncomplete
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def credit_continuation(monkeypatch):
    monkeypatch.setattr(
        config,
        "conf",
        Conf(
            visit_friend_enable=True,
            visit_friend_mode="mower",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            clue_credit_on_demand=True,
        ),
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    now = datetime(2026, 10, 15, 8, tzinfo=timezone(timedelta(hours=4)))
    monkeypatch.setattr(clue_credit, "get_server_time", lambda: now)
    scheduler = clue_credit.ClueCreditMixin()
    scheduler.device = Mock()
    scheduler.recog = Mock()
    scheduler.daily_visit_friend_attempt = now.date()
    scheduler.party_time = None
    scheduler.scene_graph_navigation = Mock()
    scheduler._visit_clue_message_board = Mock(return_value=True)
    shopping = SimpleNamespace(credit_deficit=None, run=Mock())
    monkeypatch.setattr(clue_credit, "CreditShop", lambda *_: shopping)
    reward = {
        "kind": "purchase",
        "dismissed": False,
        "touch": [[25, 222], [377, 576]],
        "slot": 0,
        "before_balance": 632,
        "price": 50,
    }
    return SimpleNamespace(scheduler=scheduler, shop=shopping, now=now, reward=reward)


def shopping_results(credit_continuation, outcomes):
    remaining = iter(outcomes)

    def run(**kwargs):
        result = next(remaining)
        if isinstance(result, Exception):
            raise result
        credit_continuation.shop.credit_deficit = result

    credit_continuation.shop.run.side_effect = run


def incomplete(reward=None):
    return CreditShopIncomplete(
        "信用商店交易未确认",
        pending_reward=reward,
        observation={"scene": 702, "balance": None, "products": None},
    )


def test_first_unknown_does_not_collect_board_credit(credit_continuation):
    case = credit_continuation
    failure = incomplete()
    shopping_results(case, [failure])

    with pytest.raises(CreditShopIncomplete) as raised:
        case.scheduler._run_on_demand_clue_shop()

    assert raised.value is failure
    assert failure.continuation == {
        "on_demand": True,
        "stage": 0,
        "settlement_checked": None,
        "reward": None,
    }
    assert case.shop.credit_deficit is None
    case.scheduler._visit_clue_message_board.assert_not_called()
    case.scheduler.scene_graph_navigation.assert_not_called()


@pytest.mark.parametrize("stage", [1, 2])
def test_completed_board_phases_are_not_repeated_after_shop_failure(
    credit_continuation, stage
):
    case = credit_continuation
    failure = incomplete(case.reward)
    shopping_results(case, [360] * stage + [failure])

    with pytest.raises(CreditShopIncomplete):
        case.scheduler._run_on_demand_clue_shop()

    continuation = json.loads(json.dumps(failure.continuation))
    assert continuation == {
        "on_demand": True,
        "stage": stage,
        "settlement_checked": True,
        "reward": case.reward,
    }
    expected_claims = [False] if stage == 1 else [False, True]
    assert [
        call.kwargs["collect_current"]
        for call in case.scheduler._visit_clue_message_board.call_args_list
    ] == expected_claims
    shopping_results(case, [0])

    case.scheduler._run_on_demand_clue_shop(resume=continuation)

    case.shop.run.assert_called_with(on_demand=True, resume=case.reward)
    assert [
        call.kwargs["collect_current"]
        for call in case.scheduler._visit_clue_message_board.call_args_list
    ] == expected_claims
    assert continuation["reward"] is None
    case.scheduler.scene_graph_navigation.assert_called_once_with(
        clue_credit.Scene.INFRA_MAIN
    )


def test_previous_week_resume_can_collect_current_week_once(credit_continuation):
    case = credit_continuation
    context = {
        "on_demand": True,
        "stage": 1,
        "settlement_checked": True,
        "reward": case.reward,
    }
    shopping_results(case, [360, 0])

    case.scheduler._run_on_demand_clue_shop(resume=context)

    case.scheduler._visit_clue_message_board.assert_called_once_with(
        collect_current=True
    )
    assert case.shop.run.call_args_list[0].kwargs == {
        "on_demand": True,
        "resume": case.reward,
    }
    assert case.shop.run.call_args_list[1].kwargs == {"on_demand": True}
    assert context["stage"] == 2
    assert context["reward"] is None


def test_resumed_current_week_stage_never_collects_board_again(credit_continuation):
    case = credit_continuation
    shopping_results(case, [360])

    case.scheduler._run_on_demand_clue_shop(
        resume={
            "stage": 2,
            "settlement_checked": True,
            "reward": case.reward,
        }
    )

    case.scheduler._visit_clue_message_board.assert_not_called()
    assert case.shop.credit_deficit == 360


def test_resumed_previous_week_stage_preserves_unconfirmed_settlement(
    credit_continuation,
):
    case = credit_continuation
    shopping_results(case, [360])

    case.scheduler._run_on_demand_clue_shop(
        resume={"stage": 1, "settlement_checked": False, "reward": case.reward}
    )

    case.scheduler._visit_clue_message_board.assert_not_called()


def test_resumed_previous_week_stage_rechecks_party_income(credit_continuation):
    case = credit_continuation
    case.scheduler.party_time = case.now + timedelta(hours=1)
    shopping_results(case, [210])

    case.scheduler._run_on_demand_clue_shop(
        resume={"stage": 1, "settlement_checked": True, "reward": case.reward}
    )

    case.scheduler._visit_clue_message_board.assert_not_called()
    assert case.shop.credit_deficit == 210


def test_admitted_shop_continues_after_game_day_changes(credit_continuation):
    case = credit_continuation
    case.scheduler.daily_visit_friend_attempt = case.now.date() - timedelta(days=1)
    shopping_results(case, [0])

    case.scheduler._run_on_demand_clue_shop(
        resume={"stage": 1, "settlement_checked": True, "reward": case.reward}
    )

    case.shop.run.assert_called_once_with(on_demand=True, resume=case.reward)
    case.scheduler._visit_clue_message_board.assert_not_called()


@pytest.mark.parametrize("stage", [0, 1])
def test_access_record_failure_retains_advanced_phase_for_resume(
    credit_continuation, stage
):
    case = credit_continuation
    context = {
        "stage": stage,
        "settlement_checked": True if stage else None,
        "reward": case.reward,
    }
    shopping_results(case, [360])

    def collect(*, collect_current):
        assert collect_current is (stage == 1)
        case.scheduler._clue_access_record_exhausted = True
        return True

    case.scheduler._visit_clue_message_board.side_effect = collect
    case.scheduler._clue_access_record_cleared = Mock(return_value=False)

    assert case.scheduler._run_on_demand_clue_shop(resume=context) is False

    assert context == {
        "on_demand": True,
        "stage": stage + 1,
        "settlement_checked": True,
        "reward": None,
    }
    case.scheduler._clue_access_record_cleared.return_value = True
    shopping_results(case, [0])

    case.scheduler._run_on_demand_clue_shop(resume=context)

    case.scheduler._visit_clue_message_board.assert_called_once_with(
        collect_current=stage == 1
    )
    assert case.shop.run.call_args_list[1].kwargs == {"on_demand": True}
    assert case.scheduler._clue_access_record_exhausted is False


def test_manual_shop_failure_retains_step_and_resumes_transaction(
    credit_continuation, monkeypatch
):
    from arknights_mower.solvers import mission

    case = credit_continuation
    task = SchedulerTask(datetime(2026, 10, 15, 12), task_type=TaskTypes.DAILY)
    original_time = task.time
    task.manual_steps = [
        TaskTypes.CREDIT_SHOP.display_value,
        TaskTypes.MISSION.display_value,
    ]
    scheduler = SimpleNamespace(task=task, device=Mock(), recog=Mock())
    monkeypatch.setattr(
        manual_tasks,
        "manual_task_deadline",
        lambda _: datetime.now() + timedelta(hours=1),
    )
    wait_for_tasks = Mock(side_effect=AssertionError("购物异常不能改成任务依赖"))
    monkeypatch.setattr(manual_tasks, "_wait_for_tasks", wait_for_tasks)
    failure = incomplete(case.reward)
    case.shop.run.side_effect = [failure, None]
    monkeypatch.setattr(shop_module, "CreditShop", lambda *_: case.shop)
    mission_solver = Mock()
    monkeypatch.setattr(mission, "MissionSolver", mission_solver)

    with pytest.raises(CreditShopIncomplete) as raised:
        manual_tasks.run_manual_task(scheduler, task)

    assert raised.value is failure
    assert task.manual_steps == [
        TaskTypes.CREDIT_SHOP.display_value,
        TaskTypes.MISSION.display_value,
    ]
    assert task.time == original_time
    assert failure.continuation == {
        "on_demand": False,
        "stage": 0,
        "settlement_checked": None,
        "reward": case.reward,
    }
    task.credit_shop_continuation = json.loads(json.dumps(failure.continuation))
    task.credit_shop_pending = {"observation": failure.observation}

    assert manual_tasks.run_manual_task(scheduler, task) is True

    assert case.shop.run.call_args_list[0].kwargs == {}
    assert case.shop.run.call_args_list[1].kwargs == {"resume": case.reward}
    assert task.manual_steps == []
    assert task.time == original_time
    assert not hasattr(task, "credit_shop_pending")
    assert not hasattr(task, "credit_shop_continuation")
    mission_solver.return_value.run.assert_called_once_with()
    wait_for_tasks.assert_not_called()
