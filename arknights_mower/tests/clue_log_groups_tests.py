"""线索分组限于具名调用；普通基建、购物和技术故障保留各自来源。"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.tests import clue_credit_tests as credit
from arknights_mower.tests import clue_gift_tests as gifts
from arknights_mower.utils import log
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

gift_ui = gifts.gift_ui
clue_workflow = gifts.clue_workflow
shopping = credit.shopping


@pytest.fixture
def captured(monkeypatch, caplog):
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    caplog.set_level(logging.DEBUG, logger=log.logger.name)
    return caplog


def live(record):
    logging.Formatter("%(asctime)s").format(record)
    return log._build_log_record(record, record.getMessage())


def test_real_clue_workflow_keeps_its_base_module_messages_in_clue_group(
    clue_workflow, captured
):
    instance, state = clue_workflow
    instance.leifeng_mode = True
    state.after_fast = 9

    instance.clue_new()

    records = [
        record
        for record in captured.records
        if record.pathname == base.__file__ and record.levelno >= logging.INFO
    ]
    assert any(record.getMessage() == "基建：线索" for record in records)
    assert all(live(record)["group"] == "clue" for record in records)
    assert state.fast_taps == [(300, 1030)]
    assert len(state.sent) == 1
    assert all(
        call.kwargs == {"log_group": "clue"}
        for call in instance.enter_room.call_args_list
    )
    assert instance.wait_product_complete.call_count >= 1
    assert all(
        call.kwargs == {"log_group": "clue"}
        for call in instance.wait_product_complete.call_args_list
    )


@pytest.mark.parametrize("cleared", [False, True])
def test_product_notice_group_does_not_change_the_original_wait_budget(
    captured, cleared
):
    instance = SimpleNamespace(
        detect_product_complete=Mock(side_effect=[True, False] if cleared else None),
        sleep=Mock(),
    )
    if not cleared:
        instance.detect_product_complete.return_value = True

    assert BaseMixin.wait_product_complete(instance, 3, log_group="clue") is cleared

    assert instance.sleep.call_count == (1 if cleared else 3)
    assert all(call.args == (1,) for call in instance.sleep.call_args_list)
    assert instance.detect_product_complete.call_count == (2 if cleared else 4)
    records = [record for record in captured.records if record.levelno >= logging.INFO]
    assert all(live(record)["group"] == "clue" for record in records)
    assert [record.levelname for record in records] == (
        ["INFO"] if cleared else ["INFO", "INFO", "INFO", "WARNING"]
    )


def test_technical_records_inside_clue_wait_keep_their_source_and_archive_policy(
    captured,
):
    package = Path(base.__file__).parents[1]
    technical = [
        log.logger.makeRecord(
            log.logger.name,
            level,
            str(package / "utils" / source),
            23,
            "离线技术故障",
            (),
            None,
        )
        for source, level in [
            ("device/device.py", logging.ERROR),
            ("recognize.py", logging.WARNING),
        ]
    ]
    observations = iter([True, False])

    def detect():
        result = next(observations)
        if result:
            for record in technical:
                log.logger.handle(record)
        return result

    instance = SimpleNamespace(detect_product_complete=detect, sleep=Mock())

    assert BaseMixin.wait_product_complete(instance, log_group="clue")

    assert live(technical[0])["group"] == "device-control"
    assert live(technical[1])["group"] == "recognition"
    assert [record.levelno for record in technical] == [logging.ERROR, logging.WARNING]
    assert log.should_archive_record(technical[0]) is True
    assert log.should_archive_record(technical[1]) is False
    clue = next(
        record for record in captured.records if "产物收取提示" in record.getMessage()
    )
    assert live(clue)["group"] == "clue"

    # 后续未指定业务的调用恢复模块兜底，不继承上次线索分组。
    default = SimpleNamespace(
        detect_product_complete=Mock(side_effect=[True, False]), sleep=Mock()
    )
    assert BaseMixin.wait_product_complete(default)
    assert live(captured.records[-1])["group"] == "base-scheduler"


@pytest.mark.parametrize("group", [None, "clue"])
def test_meeting_room_navigation_uses_only_the_callers_explicit_group(captured, group):
    instance = SimpleNamespace(
        performance_profile=SimpleNamespace(
            screenshot_interval=50, transition_timeout=1
        ),
        find=Mock(side_effect=[False, True, False, False, False]),
        detect_room=Mock(return_value="meeting"),
        back_to_infrastructure=Mock(),
    )

    BaseMixin.enter_room(instance, "meeting", max_attempts=1, log_group=group)

    instance.back_to_infrastructure.assert_called_once_with()
    records = [record for record in captured.records if record.levelno == logging.INFO]
    assert len(records) == 1
    assert live(records[0])["group"] == (group or "base-scheduler")


def test_clue_access_failure_sets_only_its_own_business_group(captured):
    instance = object.__new__(base.BaseSchedulerSolver)
    task = SchedulerTask(task_type=TaskTypes.CLUE)
    instance.task = task
    instance.clue_new = Mock(return_value=False)
    instance._task_failure_snapshot = Mock(return_value={"observations": {}})

    assert instance._run_clue_flow() is False

    assert task.execution_failure["dependency"] is True
    assert task.clue_access_record_pending is True
    assert live(captured.records[-1])["group"] == "clue"


def test_clue_reset_notice_preserves_the_existing_deadline_and_task(
    shopping, captured, monkeypatch
):
    instance, _, state = shopping
    state.now = datetime.fromisoformat("2026-10-14T03:50:00+08:00")
    clock = credit.prepare_clue_dispatch(instance, state, monkeypatch)
    task = SchedulerTask(
        time=clock.now() - timedelta(minutes=20), task_type=TaskTypes.CLUE
    )
    instance.task, instance.tasks = task, [task]
    instance.last_clue = previous_check = clock.now() - timedelta(hours=2)
    instance.party_time = party_end = task.time
    instance.clue_new = Mock()

    instance.infra_main()

    assert instance.tasks == [task]
    assert task.time == datetime.fromisoformat(
        "2026-10-14T04:00:00+08:00"
    ).astimezone().replace(tzinfo=None)
    assert instance.last_clue == previous_check and instance.party_time == party_end
    instance.clue_new.assert_not_called()
    record = next(
        record for record in captured.records if "线索任务延后" in record.getMessage()
    )
    assert live(record)["group"] == "clue"


@pytest.mark.parametrize(
    ("kind", "group"),
    [
        (TaskTypes.CLUE, "clue"),
        (TaskTypes.CLUE_PARTY, "clue"),
        (TaskTypes.CREDIT_SHOP, "credit-shop"),
        (TaskTypes.MAA_MALL, "credit-shop"),
    ],
)
def test_clue_task_recovery_keeps_its_original_time_and_business_group(
    captured, kind, group
):
    task = SchedulerTask(time=datetime(2026, 11, 5, 12, 30, 1, 123456), task_type=kind)
    task.execution_failure = {
        "rooms": (),
        "snapshot": {"observations": {}, "reservations": (), "room_observations": {}},
    }
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(operators={})
    instance.tasks = [task]
    instance._discard_legacy_recovery_checks = Mock()
    instance._discard_legacy_run_order_waits = Mock()
    instance._refresh_derived_correction = Mock(return_value=True)
    instance._task_failure_snapshot = Mock(
        return_value={
            "observations": {},
            "reservations": (),
            "room_observations": {},
            "correction_groups": {},
            "revision": 2,
        }
    )
    deadline = task.time

    instance._resume_failed_tasks()

    assert instance.tasks == [task] and task.time == deadline
    assert not hasattr(task, "execution_failure")
    record = captured.records[-1]
    assert str(deadline) in record.getMessage()
    assert live(record)["group"] == group


def test_credit_shop_failure_does_not_inherit_its_parent_clue_task_group(captured):
    from arknights_mower.solvers.shop import CreditShopIncomplete

    instance = object.__new__(base.BaseSchedulerSolver)
    instance._task_failure_snapshot = Mock(return_value={"observations": {}})
    task = SchedulerTask(task_type=TaskTypes.CLUE)
    error = CreditShopIncomplete("购物物资领取未确认", {"kind": "reward"}, {"scene": 1})

    instance._retain_credit_shop_failure(task, error)

    assert task.credit_shop_pending["reward"] == {"kind": "reward"}
    assert task.execution_failure["dependency"] is True
    assert live(captured.records[-1])["group"] == "credit-shop"


def test_real_credit_shop_start_uses_the_shop_modules_own_group(captured, monkeypatch):
    from arknights_mower.solvers.shop import CreditShop
    from arknights_mower.utils.graph import SceneGraphSolver

    monkeypatch.setattr(SceneGraphSolver, "run", lambda self: True)
    instance = object.__new__(CreditShop)

    assert instance.run()

    records = [record for record in captured.records if record.levelno == logging.INFO]
    assert len(records) == 1
    assert records[0].getMessage() == "Start: 信用商店购物"
    assert live(records[0])["group"] == "credit-shop"
