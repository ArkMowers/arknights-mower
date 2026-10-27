import json
import logging
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.maa_callback import MaaCallbackLog  # noqa: E402


@pytest.fixture
def dispatch(monkeypatch, tmp_path):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.recog = MagicMock()
    solver.MAA = MagicMock()
    maa = solver.MAA
    maa.running.return_value = False
    solver.last_execution = {"maa": None}
    solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(days=1))]
    for method in (
        "back_to_index",
        "initialize_maa",
        "release_maa",
        "rest_until_next_task",
        "to_reclamation",
        "restore_maa_theme",
    ):
        monkeypatch.setattr(solver, method, MagicMock())
    monkeypatch.setattr(solver, "to_sss", MagicMock(return_value=False))
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())

    def run(kind="rogue", **kwargs):
        conf = Conf(maa_rg_enable=1, maa_long_task_type=kind, **kwargs)
        monkeypatch.setattr(base_schedule.config, "conf", conf)
        maa.reset_mock()
        solver.maa_plan_solver([])
        return maa.append_task.call_args.args

    return run


def test_ordered_recruitment_and_sami_switches_reach_real_dispatch(dispatch):
    chain, params = dispatch(
        maa_rg_theme="Sami",
        rogue={
            "mode": 0,
            "core_char": "棘刺",
            "core_char_list": [
                {"name": "维什戴尔", "use_support": True},
                {"name": "桃金娘", "use_support": False},
            ],
            "first_floor_foldartal": "远见",
            "use_foldartal": False,
            "check_collapsal_paradigms": True,
            "double_check_collapsal_paradigms": False,
        },
    )
    assert chain == "Roguelike"
    assert params["core_char_list"] == [
        {"name": "维什戴尔", "use_support": True},
        {"name": "桃金娘", "use_support": False},
    ]
    assert "first_floor_foldartal" not in params
    assert params["use_foldartal"] is False
    assert params["check_collapsal_paradigms"] is True
    assert params["double_check_collapsal_paradigms"] is False
    _, params = dispatch(maa_rg_theme="Sami", rogue={"mode": 5})
    assert (
        not {
            "core_char_list",
            "use_foldartal",
            "check_collapsal_paradigms",
            "double_check_collapsal_paradigms",
        }
        & params.keys()
    )
    _, params = dispatch(
        maa_rg_theme="Sami", rogue={"mode": 0, "double_check_collapsal_paradigms": True}
    )
    assert "double_check_collapsal_paradigms" not in params


@pytest.mark.parametrize(
    "theme,mode,squad,sent",
    [
        ("Sarkaz", 1, "点刺成锭分队", True),
        ("Sarkaz", 1, "后勤分队", True),
        ("Sarkaz", 0, "点刺成锭分队", False),
        ("Sarkaz", 1, "指挥分队", False),
        ("Sami", 1, "后勤分队", False),
    ],
)
def test_seed_is_only_sent_for_supported_investment(dispatch, theme, mode, squad, sent):
    _, params = dispatch(
        maa_rg_theme=theme,
        rogue={
            "mode": mode,
            "squad": squad,
            "start_with_seed": "固定种子",
            "use_foldartal": True,
        },
    )
    assert (params.get("start_with_seed") == "固定种子") is sent
    if theme != "Sami":
        assert "use_foldartal" not in params


def test_blackflow_preparation_and_target_parameters(dispatch):
    _, params = dispatch(
        maa_rg_theme="BlackFlow",
        rogue={
            "mode": 30003,
            "blackflow_start_animals": ["swaddled_cat", "swaddled_cat"],
            "blackflow_start_rewards": 3,
            "collectible_mode_squad": "特勤分队",
            "collectible_mode_roles": "坚不可摧",
            "collectible_mode_core_char_list": [{"name": "机械师"}],
            "blackflow_start_utopia": True,
            "difficulty": 6,
            "blackflow_start_reward_priority": ["survey_advance", "unnumbered_item"],
        },
    )
    assert params["blackflow_start_animals"] == ["swaddled_cat", "swaddled_cat"]
    assert params["blackflow_start_rewards"] == 3
    assert params["collectible_mode_squad"] == "特勤分队"
    assert params["collectible_mode_roles"] == "坚不可摧"
    assert params["collectible_mode_core_char_list"] == [
        {"name": "机械师", "use_support": False}
    ]
    assert params["blackflow_start_reward_priority"] == [
        "survey_advance",
        "unnumbered_item",
    ]
    assert "blackflow_strategy" not in params
    _, params = dispatch(
        maa_rg_theme="BlackFlow", rogue={"mode": 0, "blackflow_strategy": "ending3"}
    )
    assert params["blackflow_strategy"] == "ending3"
    assert "blackflow_start_animals" not in params


@pytest.mark.parametrize(
    "rogue",
    [
        {"blackflow_start_animals": ["swaddled_feathered_serpent"] * 2},
        {"blackflow_start_animals": ["swaddled_cat"] * 3},
        {"blackflow_start_rewards": 4096},
        {"core_char_list": [{"name": "棘刺"}] * 4},
        {"blackflow_start_reward_priority": ["unnumbered_item"] * 2},
        {"mode": 30003, "blackflow_start_utopia": True},
        {
            "mode": 30003,
            "blackflow_start_utopia": True,
            "difficulty": 5,
            "blackflow_start_reward_priority": ["unnumbered_item"],
        },
    ],
)
def test_invalid_rogue_options_are_rejected_before_execution(rogue):
    with pytest.raises(ValidationError):
        Conf(rogue=rogue)


@pytest.mark.parametrize(
    "theme,mode,clear,craft",
    [
        ("Tales", 0, True, False),
        ("Tales", 1, False, True),
        ("RelaunchAnchor", 16, False, False),
        ("RelaunchAnchor", 32, False, False),
        ("RelaunchAnchor", 48, False, False),
    ],
)
def test_reclamation_parameters_follow_theme_and_mode(
    dispatch, theme, mode, clear, craft
):
    chain, params = dispatch(
        "rcl", maa_rcl_theme=theme, rcl={"mode": mode, "clear_store": True}
    )
    assert chain == "Reclamation"
    assert params["mode"] == mode
    assert (params.get("clear_store") is True) is clear
    assert ("tools_to_craft" in params) is craft


@pytest.mark.parametrize(
    "status,level,text",
    [
        ("preparing", logging.INFO, "准备局开始"),
        ("target_run", logging.INFO, "目标局开始"),
        ("reward_missed", logging.INFO, "未命中期望奖励"),
        ("reward_picked", logging.INFO, "检查第一层实托邦"),
        ("completed", logging.INFO, "已保留目标局"),
        ("reward_unrecognized", logging.WARNING, "无法识别奖励"),
        ("reward_page_missing", logging.WARNING, "未出现选择支援页"),
        ("reward_recognition_failed", logging.WARNING, "选择奖励失败"),
    ],
)
def test_blackflow_callbacks_reach_scheduler_log(monkeypatch, status, level, text):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.maa_callback = MaaCallbackLog()
    logger = MagicMock()
    monkeypatch.setattr(base_schedule, "logger", logger)
    solver.on_maa_callback(
        20003,
        json.dumps(
            {
                "taskchain": "Roguelike",
                "what": "BlackFlowStartRun",
                "details": {"status": status, "rewards": ["空间租赁"]},
            }
        ).encode(),
        None,
    )
    args = logger.log.call_args.args
    assert args[0] == level
    assert text in args[1]
    assert "空间租赁" in args[1]


def test_blackflow_malformed_and_trade_callbacks():
    log = MaaCallbackLog()
    for inner in (None, [], {"status": []}, {"status": "future_status"}):
        assert (
            log.describe(20003, {"what": "BlackFlowStartRun", "details": inner}) is None
        )
    line = log.describe(
        20003,
        {
            "what": "BlackFlowScrapTradeAborted",
            "details": {"reason": "recognition_failed", "item": "零件"},
        },
    )
    assert line.level == logging.WARNING
    assert "零件" in line.text
