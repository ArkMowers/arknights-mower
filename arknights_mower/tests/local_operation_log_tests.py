"""本地作战的实时日志：用户关心的结果用中文叙述，过程参数留在 DEBUG。"""

import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import operation
from arknights_mower.utils.recognize import Scene

LOGGER = "arknights_mower.utils.log"


def user_lines(caplog):
    """WebUI 实时日志只接收 INFO 及以上，返回这些行的级别和正文。"""
    return [
        (record.levelname, record.getMessage())
        for record in caplog.records
        if record.levelno >= logging.INFO
    ]


def loop_solver(monkeypatch, batches):
    """保留 run() 的循环判断，每批场景处理的结果由 batches 依次给出。"""
    solver = object.__new__(operation.OperationSolver)
    solver._inventory_limit_reached = MagicMock(return_value=False)
    solver._should_stop_for_deadline = MagicMock(return_value=False)
    solver.current_batch_started_at = None
    solver.current_batch_finished_at = None

    def prepare():
        solver.desired_repeat_times = 6
        solver.current_batch_repeat_count = 0
        solver.current_batch_success = False

    def run_batch(self):
        success, repeat = batches.pop(0)
        solver.current_batch_success = success
        solver.current_batch_repeat_count = repeat
        solver.current_batch_duration_seconds = 60.0

    solver._prepare_batch_state = prepare
    monkeypatch.setattr(operation.SceneGraphSolver, "run", run_batch)
    return solver


def run_loop(solver, caplog, **options):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        return solver.run(
            stage_id="1-7",
            next_task_time=datetime.now() + timedelta(hours=1),
            stage_duration_seconds=120,
            **options,
        )


def test_batch_progress_and_sanity_stop(monkeypatch, caplog):
    solver = loop_solver(monkeypatch, [(True, 6)])
    result = run_loop(
        solver, caplog, target_total_runs=18, simulated_current_ap=40, ap_cost=6
    )
    assert result["executed_runs"] == 6 and result["sanity_drain"]
    assert user_lines(caplog) == [
        ("INFO", "Start: 代理作战"),
        ("INFO", "1-7 本轮完成 6 次作战，还剩 12 次"),
        ("INFO", "估算剩余理智为 4，不够再打一次 1-7（每次消耗 6 理智），结束本次刷关"),
    ]
    # 开发者排查用的英文参数行仍写入 runtime.log。
    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(m.startswith("operation batch success") for m in debug)
    assert any(m.startswith("operation finished") for m in debug)


def test_deadline_stop(monkeypatch, caplog):
    solver = loop_solver(monkeypatch, [])
    solver._should_stop_for_deadline.return_value = True
    run_loop(solver, caplog, target_total_runs=18, simulated_current_ap=40, ap_cost=6)
    assert user_lines(caplog) == [
        ("INFO", "Start: 代理作战"),
        ("INFO", "离下一个任务开始的时间不够再打一次 1-7，结束本次刷关"),
    ]


def test_single_batch_without_run_target(monkeypatch, caplog):
    solver = loop_solver(monkeypatch, [(True, 6)])
    run_loop(solver, caplog)
    assert user_lines(caplog) == [
        ("INFO", "Start: 代理作战"),
        ("INFO", "1-7 本轮完成 6 次作战"),
    ]


def scene_solver(monkeypatch, scene):
    monkeypatch.setattr(
        operation.config, "conf", SimpleNamespace(medicine_expire_days=0)
    )
    solver = object.__new__(operation.OperationSolver)
    solver.stage_id = "1-7"
    solver.desired_repeat_times = 6
    solver.current_batch_repeat_count = 6
    solver.current_batch_started_at = datetime.now()
    solver.sanity_drain = False
    solver.annihilation_agency_locked = False
    solver.annihilation_reward_full = False
    solver.waiting_scene = []
    solver.scene = MagicMock(return_value=scene)
    solver.find = MagicMock(return_value=None)
    for name in (
        "tap",
        "tap_element",
        "_finish_batch",
        "_record_batch_drops",
        "_mark_battle_started",
    ):
        setattr(solver, name, MagicMock())
    return solver


@pytest.mark.parametrize(
    "scene, expected",
    [
        (Scene.OPERATOR_FINISH, []),
        (Scene.OPERATOR_FAILED, [("WARNING", "1-7 代理作战失败")]),
        (Scene.OPERATOR_GIVEUP, [("WARNING", "1-7 放弃行动")]),
        (
            Scene.OPERATOR_RECOVER_POTION,
            [("INFO", "理智不足，不使用理智药，结束本次刷关")],
        ),
        (
            Scene.OPERATOR_RECOVER_ORIGINITE,
            [("INFO", "理智不足，不使用源石恢复理智，结束本次刷关")],
        ),
        (Scene.OPERATOR_ELIMINATE, []),
        (Scene.OPERATOR_ELIMINATE_AGENCY, []),
        (Scene.UNKNOWN, [("WARNING", "代理作战时遇到无法处理的界面")]),
    ],
)
def test_scene_results(monkeypatch, caplog, scene, expected):
    solver = scene_solver(monkeypatch, scene)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        solver.transition()
    assert user_lines(caplog) == expected


@pytest.mark.parametrize(
    "repeat, expected",
    [
        (3, ("INFO", "选择连战次数：目标 6，实际 3")),
        (1, ("INFO", "没有找到连战次数选项，本轮只打 1 次（目标 6 次）")),
    ],
)
def test_repeat_without_selector(monkeypatch, caplog, repeat, expected):
    solver = scene_solver(monkeypatch, Scene.OPERATOR_BEFORE)
    solver.recog = SimpleNamespace(gray=np.full((1080, 1920), 255, dtype=np.uint8))
    solver.auto_repeat = True
    solver.repeat_button_attempts = 1
    solver.number = MagicMock(return_value=repeat)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        solver.transition()
    assert user_lines(caplog) == [expected]
    assert solver.current_batch_repeat_count == repeat
