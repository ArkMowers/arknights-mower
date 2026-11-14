"""本地刷理智调度的实时日志：用户关心的结果用中文叙述，参数行留在 DEBUG。"""

import logging
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, local_operation  # noqa: E402

LOGGER = "arknights_mower.utils.log"
STAGE_COST = {"1-7": 6, "CE-6": 36}


def user_lines(caplog):
    """WebUI 实时日志只接收 INFO 及以上，返回这些行的级别和正文。"""
    return [
        (record.levelname, record.getMessage())
        for record in caplog.records
        if record.levelno >= logging.INFO
    ]


def debug_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]


def result(**fields):
    """OperationSolver.run 的返回值，未给出的字段取默认值。"""
    return {
        "executed_runs": 0,
        "sanity_drain": False,
        "annihilation_reward_full": False,
        "annihilation_agency_locked": False,
        "next_threshold_time": None,
        "stopped_by_deadline": False,
        "stopped_by_inventory": False,
        "inventory_unconfirmed": False,
        "last_batch_duration_seconds": None,
        "simulated_current_ap": None,
        "remaining_runs": None,
        **fields,
    }


def battles(**kwargs):
    """打完目标次数；没有目标时打一轮 6 次，理智按每次消耗扣减。"""
    target = kwargs["target_total_runs"]
    runs = 6 if target is None else target
    ap, cost = kwargs["simulated_current_ap"], kwargs["ap_cost"]
    return result(
        executed_runs=runs,
        simulated_current_ap=None if ap is None or cost is None else ap - runs * cost,
        remaining_runs=None if target is None else 0,
    )


@pytest.fixture
def local(monkeypatch):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.device = MagicMock()
    solver.recog = MagicMock()
    solver.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(hours=2), meta_data="")
    ]
    solver.local_operation_followup_time = None
    solver.last_execution = {"maa": None}
    solver.back_to_index = MagicMock()
    solver.maybe_switch_expired_activity_plan = MagicMock()
    solver.check_current_focus = MagicMock()
    solver.mower_stage_ap_cost = MagicMock(side_effect=STAGE_COST.get)
    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: 0)
    for name in (
        "scheduling",
        "send_message",
        "save_exception",
        "MissionSolver",
        "cultivateDepotSolver",
    ):
        monkeypatch.setattr(base_schedule, name, MagicMock())
    # 离下个游戏日还有 10 小时，理智推算只受日常任务间隔（4 小时）限制。
    monkeypatch.setattr(
        local_operation,
        "get_next_server_day_local",
        lambda: (600, datetime.now() + timedelta(hours=10)),
    )
    player = MagicMock()
    monkeypatch.setattr(base_schedule, "PlayerInfoClient", player)
    navigation = MagicMock()
    navigation.return_value.run.return_value = True
    monkeypatch.setattr(base_schedule, "NavigationSolver", navigation)
    operation = MagicMock()
    operation.return_value.run.side_effect = battles
    monkeypatch.setattr(base_schedule, "OperationSolver", operation)

    def plan(*stages, ap=None, threshold=100):
        conf = SimpleNamespace(
            maa_gap=4,
            maa_stage_inventory_enable=False,
            maa_weekly_plan=[
                SimpleNamespace(stage=list(stages), sanity_threshold=threshold)
            ],
        )
        monkeypatch.setattr(base_schedule.config, "conf", conf)
        snapshot = None if ap is None else SimpleNamespace(current_ap=ap)
        player.return_value.get_first_available_snapshot.return_value = snapshot

    return SimpleNamespace(
        solver=solver, plan=plan, navigation=navigation, operation=operation
    )


def dispatch(local, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        local.solver.mower_plan_solver()
    local.solver.device.exit.assert_not_called()
    return user_lines(caplog)


def recheck_line(solver):
    run_at = solver.local_operation_followup_time
    return ("INFO", f"本地刷关阈值复查安排在 {run_at:%m-%d %H:%M}")


def test_threshold_run_and_recheck(local, caplog):
    # 理智 120，4 小时后推算为 160，超过阈值 100 的 60 点要打 10 次 1-7。
    local.plan("1-7", ap=120)
    lines = dispatch(local, caplog)
    assert lines == [
        ("INFO", "开始刷理智：1-7"),
        ("INFO", "前往 1-7，计划打 10 次"),
        recheck_line(local.solver),
    ]
    # 开发者排查用的英文参数行仍写入 runtime.log，措辞不变。
    debug = debug_lines(caplog)
    for prefix in (
        "start mower_plan_solver",
        "local operation plan: ['1-7']",
        "local operation scheduling window",
        "loaded local operation sanity context",
        "enter local operation stage loop",
        "local operation threshold evaluation",
        "start navigation before operation",
        "navigation succeeded, start operation",
        "local operation stage result",
        "computed local operation follow-up time",
        "schedule local operation follow-up task",
        "run mission solver after local operation",
        "record local task execution time",
    ):
        assert any(m.startswith(prefix) for m in debug), prefix


def test_stage_skip_reasons(local, caplog):
    local.plan("CE-6", "1-7", ap=30)
    assert dispatch(local, caplog) == [
        ("INFO", "开始刷理智：CE-6、1-7"),
        ("INFO", "估算剩余理智为 30，不够打一次 CE-6（每次消耗 36 理智），跳过这一关"),
        ("INFO", "预计 4 小时内理智不会超过体力阈值 100，跳过 1-7"),
        recheck_line(local.solver),
    ]
    local.navigation.return_value.run.assert_not_called()
    assert "local operation finished without executing any stage" in debug_lines(caplog)


def test_missing_sanity_reading(local, caplog):
    local.plan("1-7")
    local.solver.tasks.append(
        SimpleNamespace(
            time=datetime.now() + timedelta(hours=3),
            meta_data=base_schedule.FOLLOWUP_TASK_META,
        )
    )
    assert dispatch(local, caplog) == [
        ("INFO", "开始刷理智：1-7"),
        ("WARNING", "没有读取到森空岛的理智，这次不按体力阈值计算作战次数"),
        ("INFO", "前往 1-7，打一轮"),
    ]
    # 清除旧的阈值复查只写入 runtime.log。
    assert "clear local operation follow-up tasks | count=1" in debug_lines(caplog)


def test_zero_threshold_drains_current_sanity(local, caplog):
    local.plan("1-7", ap=40, threshold=0)
    assert dispatch(local, caplog) == [
        ("INFO", "开始刷理智：1-7"),
        ("INFO", "今天的体力阈值为 0，这次把当前理智刷完"),
        ("INFO", "前往 1-7，计划打 6 次"),
    ]


def test_missing_stage_cost(local, caplog):
    local.plan("X-1", ap=40)
    assert dispatch(local, caplog) == [
        ("INFO", "开始刷理智：X-1"),
        (
            "ERROR",
            "关卡信息未找到，无法获取体力消耗: ['X-1']，"
            "请在「刷理智周计划」中设置 AP fallback（关卡体力消耗默认值）",
        ),
        ("WARNING", "有关卡缺少体力消耗，这次不按体力阈值计算作战次数"),
        ("INFO", "前往 X-1，打一轮"),
    ]


def test_reselected_stage_without_cost(local, caplog):
    local.plan("1-7", ap=90)
    # 打完 1-7 后，库存规则放出没有体力消耗数据的 X-1。
    local.solver.mower_stage_plan = MagicMock(
        side_effect=[["1-7"], ["1-7"], ["X-1"], [], ["1-7"]]
    )
    assert dispatch(local, caplog) == [
        ("INFO", "开始刷理智：1-7"),
        ("INFO", "前往 1-7，计划打 5 次"),
        ("WARNING", "X-1 缺少体力消耗，接下来不按体力阈值计算作战次数"),
        ("INFO", "前往 X-1，打一轮"),
    ]


def test_empty_plan(local, caplog):
    local.plan()
    assert dispatch(local, caplog) == [("INFO", "今天没有需要刷的关卡，跳过刷理智")]


def test_next_task_too_close(local, caplog):
    local.plan("1-7", ap=120)
    local.solver.tasks[0].time = datetime.now() + timedelta(minutes=3)
    assert dispatch(local, caplog) == [
        ("INFO", "开始刷理智：1-7"),
        ("INFO", "离下一个任务开始不到 5 分钟，结束本次刷关"),
        recheck_line(local.solver),
    ]
    local.navigation.return_value.run.assert_not_called()


def test_waits_for_daily_task_interval(local, caplog):
    local.plan("1-7", ap=120)
    # 距上次刷理智约 1 小时 30 分钟，日常任务间隔为 4 小时。
    local.solver.last_execution["maa"] = datetime.now() - timedelta(
        hours=1, minutes=29, seconds=30
    )
    assert dispatch(local, caplog) == [("INFO", "2 小时 30 分钟后开始刷理智")]


def run_stage(local, caplog, **options):
    kwargs = {
        "stage": "1-7",
        "next_task_time": datetime.now() + timedelta(hours=2),
        "simulated_current_ap": 100,
        "ap_cost": 6,
        "target_total_runs": 10,
        "mode": "threshold",
        "threshold": 100,
        **options,
    }
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        outcome = local.solver.run_local_operation_stage(**kwargs)
    return outcome, user_lines(caplog)


def test_rerun_then_skip_without_progress(local, caplog):
    # 第一次打完 6 次后作战失败，重新进入后一次也没打完。
    local.operation.return_value.run.side_effect = [
        result(executed_runs=6, simulated_current_ap=64, remaining_runs=4),
        result(executed_runs=0, simulated_current_ap=64, remaining_runs=4),
    ]
    outcome, lines = run_stage(local, caplog)
    assert lines == [
        ("INFO", "前往 1-7，计划打 10 次"),
        ("INFO", "重新前往 1-7，还要打 4 次"),
        ("INFO", "前往 1-7，计划打 4 次"),
        ("WARNING", "跳过 1-7 剩下的 4 次作战"),
    ]
    assert outcome["executed_any"] and not outcome["should_break"]


def test_navigation_failure(local, caplog):
    local.navigation.return_value.run.return_value = False
    outcome, lines = run_stage(local, caplog)
    assert lines == [
        ("INFO", "前往 1-7，计划打 10 次"),
        ("WARNING", "导航到 1-7 失败，跳过这一关"),
    ]
    assert not outcome["executed_any"] and not outcome["should_break"]
    local.operation.return_value.run.assert_not_called()


def test_sanity_drain_reason_comes_from_operation(local, caplog):
    # 理智不足的原因由 OperationSolver 写出，调度这里不再重复。
    local.operation.return_value.run.side_effect = [
        result(
            executed_runs=6, sanity_drain=True, simulated_current_ap=4, remaining_runs=4
        )
    ]
    outcome, lines = run_stage(local, caplog)
    assert lines == [("INFO", "前往 1-7，计划打 10 次")]
    assert outcome["should_break"]


def test_stage_deadline(local, caplog):
    outcome, lines = run_stage(
        local, caplog, next_task_time=datetime.now() + timedelta(minutes=3)
    )
    assert lines == [("INFO", "离下一个任务开始不到 5 分钟，结束本次刷关")]
    assert outcome["should_break"]


def test_followup_bookkeeping_stays_at_debug(local, caplog):
    local.solver.tasks.append(
        SimpleNamespace(
            time=datetime.now() + timedelta(hours=3),
            meta_data=base_schedule.FOLLOWUP_TASK_META,
        )
    )
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        local.solver.upsert_local_operation_followup(None)
    assert user_lines(caplog) == []
    assert debug_lines(caplog) == [
        "clear local operation follow-up tasks | count=1",
        "skip local operation follow-up insert because run_at is empty",
    ]
