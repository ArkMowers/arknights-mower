"""业务包装日志按实际任务分组，不改变任务执行与技术日志来源。"""

import importlib
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

NOW = datetime(2026, 11, 5, 12)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture
def base(monkeypatch, caplog):
    # 导入链中的森空岛初始化会联网；这些测试控制业务入口的外部输入。
    if "arknights_mower.utils.skland" not in sys.modules:
        monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    module = importlib.import_module("arknights_mower.solvers.base_schedule")
    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module, "send_message", Mock())
    monkeypatch.setattr(module, "save_exception", Mock())
    monkeypatch.setattr(module, "save_log", Mock())
    monkeypatch.setattr(module, "save_current_state", Mock())
    monkeypatch.setattr(
        importlib.import_module("arknights_mower.utils.depot"),
        "restore_cached_inventory",
        Mock(),
    )
    monkeypatch.setattr(module, "battle_inventory_active", Event())
    monkeypatch.setattr(module.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(module.logger, "propagate", False)
    caplog.set_level(logging.INFO, logger=module.logger.name)
    return module


@pytest.fixture
def solver(base, monkeypatch):
    from arknights_mower.utils.config.conf import Conf
    from arknights_mower.utils.scheduler_task import SchedulerTask

    monkeypatch.setattr(base.config, "conf", Conf(maa_gap=4, recruit_gap=3))
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.device = Mock()
    instance.recog = Mock()
    instance.MAA = None
    instance.last_execution = {"maa": NOW, "recruit": None, "todo": None}
    instance.tasks = [SchedulerTask(time=NOW + timedelta(hours=1))]
    instance.local_operation_followup_time = None
    instance.initialize_maa = Mock()
    instance.back_to_index = Mock()
    instance.rest_until_next_task = Mock()
    instance._refresh_workshop_inventory = Mock()
    return instance


def live(record):
    from arknights_mower.utils.log import _build_log_record

    logging.Formatter("%(asctime)s").format(record)
    return _build_log_record(record, record.getMessage())


def matching(caplog, text):
    return [record for record in caplog.records if text in record.getMessage()]


def test_recruit_forecast_keeps_the_interval_and_execution_record(
    base, solver, monkeypatch, caplog
):
    recruit = Mock()
    monkeypatch.setattr(base, "RecruitSolver", recruit)
    pending = solver.tasks.copy()
    deadline = pending[0].time

    solver.recruit_plan_solver()
    solver.recruit_plan_solver()

    recruit.assert_called_once_with(solver.device, solver.recog)
    recruit.return_value.run.assert_called_once_with()
    assert solver.last_execution["recruit"] == NOW
    assert solver.tasks == pending
    assert pending[0].time == deadline
    records = matching(caplog, "下一次公开招募执行时间在3.0小时之后")
    assert len(records) == 1
    assert live(records[0])["group"] == "recruitment"


@pytest.mark.parametrize("near_task", [False, True])
def test_maa_daily_interval_and_admission_log_under_maa_without_starting_it(
    base, solver, caplog, near_task
):
    if near_task:
        solver.tasks[0].time = NOW + timedelta(minutes=4)
    task = solver.tasks[0]
    deadline = task.time

    result = solver.maa_plan_solver()
    assert result is (None if near_task else True)

    text = "距离下次基建任务不足5分钟" if near_task else "后开始做日常任务"
    records = matching(caplog, text)
    assert len(records) == 1
    assert live(records[0])["group"] == "maa-integration"
    solver.initialize_maa.assert_not_called()
    solver.back_to_index.assert_not_called()
    assert solver.device.mock_calls == []
    assert solver.tasks == [task]
    assert task.time == deadline
    assert solver.last_execution["maa"] == NOW
    if near_task:
        solver.rest_until_next_task.assert_not_called()
    else:
        solver.rest_until_next_task.assert_called_once_with()


def test_local_operation_interval_keeps_its_task_and_execution_time(
    base, solver, caplog
):
    task = solver.tasks[0]
    deadline = task.time

    solver.mower_plan_solver()

    records = matching(caplog, "后开始刷理智")
    assert len(records) == 1
    assert live(records[0])["group"] == "local-operation"
    assert solver.tasks == [task]
    assert task.time == deadline
    assert solver.last_execution["maa"] == NOW
    assert solver.local_operation_followup_time is None
    assert solver.device.mock_calls == []
    solver.rest_until_next_task.assert_not_called()


def test_maa_callback_and_heartbeat_keep_their_interval_and_business_group(
    base, solver, caplog
):
    from arknights_mower.utils.maa_callback import MaaCallbackLog

    seconds = [0]
    solver.maa_callback = MaaCallbackLog(clock=lambda: seconds[0])
    solver.on_maa_callback(10001, json.dumps({"taskchain": "Award"}).encode(), None)
    seconds[0] = 60
    solver.report_maa_progress()
    solver.report_maa_progress()

    assert [record.getMessage() for record in caplog.records] == [
        "开始任务：领取奖励",
        "MAA 运行中：领取奖励（已运行 01:00）",
    ]
    assert [live(record)["group"] for record in caplog.records] == [
        "maa-integration",
        "maa-integration",
    ]
    assert solver.device.mock_calls == []


@pytest.mark.parametrize(
    ("source", "level", "group"),
    [
        ("recognize.py", logging.WARNING, "recognition"),
        ("device/device.py", logging.ERROR, "device-control"),
    ],
)
def test_technical_record_inside_recruitment_keeps_its_source_and_level(
    base, solver, monkeypatch, caplog, source, level, group
):
    pathname = str(Path(base.__file__).parents[1] / "utils" / source)
    record = base.logger.makeRecord(
        base.logger.name, level, pathname, 17, "离线技术来源记录", (), None
    )
    recruit = Mock()
    recruit.return_value.run.side_effect = lambda: base.logger.handle(record)
    monkeypatch.setattr(base, "RecruitSolver", recruit)

    solver.recruit_plan_solver()

    technical = matching(caplog, "离线技术来源记录")
    assert technical == [record]
    assert record.pathname == pathname
    assert record.levelno == level
    assert live(record)["group"] == group
    forecast = matching(caplog, "下一次公开招募执行时间")
    assert len(forecast) == 1
    assert live(forecast[0])["group"] == "recruitment"


def test_depot_sync_failure_keeps_inventory_and_skips_scanning(
    base, solver, monkeypatch, caplog
):
    sync = Mock()
    sync.return_value.start.return_value = False
    scan = Mock()
    monkeypatch.setattr(base, "cultivateDepotSolver", sync)
    monkeypatch.setattr(base, "DepotSolver", scan)
    solver._auto_schedule_mastery_after_scan = Mock()

    assert solver.仓库扫描() is False

    sync.return_value.start.assert_called_once_with(force_inventory=True)
    scan.assert_not_called()
    solver._auto_schedule_mastery_after_scan.assert_not_called()
    records = matching(caplog, "森空岛同步未成功")
    assert len(records) == 1
    assert live(records[0])["group"] == "depot-recognition"
    assert records[0].levelno == logging.WARNING
    assert not hasattr(records[0], "archive_screenshots")
    assert solver.device.mock_calls == []


def test_depot_exception_keeps_failure_result_and_archive_policy(
    base, solver, monkeypatch, caplog
):
    from arknights_mower.utils.log import should_archive_record

    failure = RuntimeError("离线扫描失败")
    sync = Mock()
    sync.return_value.start.return_value = True
    scan = Mock()
    scan.return_value.run.side_effect = failure
    monkeypatch.setattr(base, "cultivateDepotSolver", sync)
    monkeypatch.setattr(base, "DepotSolver", scan)

    assert solver.仓库扫描() is False

    base.save_exception.assert_called_once_with(failure)
    records = matching(caplog, "离线扫描失败")
    assert len(records) == 1
    assert live(records[0])["group"] == "depot-recognition"
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info[1] is failure
    assert not hasattr(records[0], "archive_screenshots")
    assert should_archive_record(records[0]) is True


def test_skland_sign_failure_keeps_redaction_and_no_screenshot_override(
    base, solver, monkeypatch, caplog
):
    from arknights_mower.utils.log import should_archive_record

    skland = Mock()
    skland.return_value._log_secrets = ("secret-token",)
    skland.return_value.start.side_effect = RuntimeError("令牌 secret-token 无效")
    monkeypatch.setattr(base, "SKLand", skland)

    result = solver.skland_plan_solver()

    assert result == (NOW - timedelta(hours=4)).date()
    records = matching(caplog, "森空岛签到失败")
    assert len(records) == 1
    assert live(records[0])["group"] == "local-operation"
    assert "secret-token" not in records[0].getMessage()
    assert records[0].archive_screenshots is False
    assert should_archive_record(records[0]) is False
    base.save_exception.assert_not_called()
    base.send_message.assert_called_once_with(
        records[0].getMessage(), subject="森空岛签到失败", level="ERROR"
    )


def test_maa_worker_close_failure_retains_cleanup_and_runtime_group(
    base, solver, caplog
):
    worker = Mock()
    worker.close.side_effect = RuntimeError("工作进程已断开")
    solver.MAA = worker

    solver.release_maa()

    worker.close.assert_called_once_with()
    assert solver.MAA is None
    assert solver.maa_copilot_task is None
    assert solver.maa_sss_task is None
    records = matching(caplog, "关闭 MAA 工作进程失败")
    assert len(records) == 1
    assert live(records[0])["group"] == "maa-runtime"
    assert records[0].levelno == logging.ERROR


def test_scan_followup_failure_is_growth_planning_and_keeps_archive_override(
    base, solver, monkeypatch, caplog
):
    from arknights_mower.utils import mastery_db
    from arknights_mower.utils.log import should_archive_record

    retry = Mock(side_effect=RuntimeError("离线计划读取失败"))
    monkeypatch.setattr(mastery_db, "retry_failed_plans", retry)

    solver._auto_schedule_mastery_after_scan()

    retry.assert_called_once_with()
    records = matching(caplog, "自动安排专精/合成配置失败")
    assert len(records) == 1
    assert live(records[0])["group"] == "growth-planning"
    assert records[0].archive_screenshots is False
    assert should_archive_record(records[0]) is False


def test_round_rest_keeps_base_group_after_an_maa_interval_notice(
    base, solver, monkeypatch, caplog
):
    solver._refresh_observed_recovery_tasks = Mock()
    solver._schedule_maintenance_backup_check = Mock()
    solver.handle_idle_action = Mock()
    solver._stop_after_round = Mock()
    solver._idle_sleep = Mock()
    solver.check_current_focus = Mock()
    solver.task_count = 0
    solver.find_next_task = Mock(return_value=solver.tasks[0])
    solver.rest_until_next_task = base.BaseSchedulerSolver.rest_until_next_task.__get__(
        solver
    )
    monkeypatch.setattr(
        base, "task_template", SimpleNamespace(render=Mock(return_value=""))
    )
    task = solver.tasks[0]
    deadline = task.time

    assert solver.maa_plan_solver()

    notices = matching(caplog, "后开始做日常任务")
    forecasts = [record for record in caplog.records if hasattr(record, "log_task")]
    assert len(notices) == len(forecasts) == 1
    assert live(notices[0])["group"] == "maa-integration"
    assert live(forecasts[0])["group"] == "base-scheduler"
    assert forecasts[0].log_task["wait_seconds"] == 3600
    solver._idle_sleep.assert_called_once_with(3600, round_end=True)
    assert solver.tasks == [task]
    assert task.time == deadline
    assert solver.last_execution["maa"] == NOW
