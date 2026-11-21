"""公开招募只在页面报告已识别的标签、已确认的操作和实际结果。"""

import logging
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, call

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import recruit
from arknights_mower.utils.recognize import Recognizer, Scene

LOGGER = "arknights_mower.utils.log"


def recruit_records(caplog, minimum=logging.INFO):
    return [
        record
        for record in caplog.records
        if Path(record.pathname).name == "recruit.py" and record.levelno >= minimum
    ]


def user_lines(caplog):
    return [record.getMessage() for record in recruit_records(caplog)]


def debug_lines(caplog):
    return [
        record.getMessage()
        for record in recruit_records(caplog, logging.DEBUG)
        if record.levelno == logging.DEBUG
    ]


@pytest.fixture
def solver(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    monkeypatch.setattr(recruit.config.conf, "recruitment_permit", 5)
    recog = Mock()
    recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    result = recruit.RecruitSolver(Mock(), recog)
    result.scene = Mock(return_value=Scene.RECRUIT_TAGS)
    result.find = Mock(return_value=None)
    result.get_ticket_number = Mock(return_value=10)
    result.tag_not_choosed = Mock(return_value=False)
    result.tap = Mock()
    result.tap_element = Mock()
    result.back = Mock()
    result.choose_time = Mock()
    result.wait_for_scene_stable = Mock(return_value=True)
    return result


def choice(tags, level=4, choosed=False):
    return {
        "tags": tags,
        "result": [{"id": "char_120_hibiscus", "name": "芙蓉", "star": level}],
        "level": level,
        "choosed": choosed,
    }


def prepare_selection(solver, tags, level=4):
    solver.tags = {
        1: {name: (100 + index * 300, 100) for index, name in enumerate(tags)}
    }
    solver.agent_choose = {1: choice(tags, level)}
    times = {"hour": 3 if level == 1 else 9, "minute": 50 if level == 1 else 0}
    solver.get_recruit_time = Mock(side_effect=times.__getitem__)


def show_recruiting_slot(solver):
    solver.scene.return_value = Scene.RECRUIT_MAIN
    solver.find.side_effect = lambda name, **_: (
        ((100, 100), (200, 200)) if name == "recruit/job_requirements" else None
    )
    solver.recruit_index = 1
    solver.transition()


def test_recognized_tags_hide_coordinates_without_changing_selection(solver, caplog):
    tags = {"治疗": (560, 550), "费用回复": (816, 550)}
    solver.get_recruit_tag = Mock(return_value=tags)
    solver.recruit_tags = Mock()

    solver.transition()

    assert user_lines(caplog) == ["1号招募位：识别标签：治疗、费用回复"]
    assert recruit_records(caplog)[0].log_recruitment == {
        "event": "tags",
        "tags": ["治疗", "费用回复"],
        "rarity": None,
    }
    assert any(str(tags) in message for message in debug_lines(caplog))
    assert solver.tags == {1: tags}
    assert solver.refresh is False
    solver.recruit_tags.assert_called_once_with(tags)
    solver.tap.assert_not_called()


@pytest.mark.parametrize("stable", [True, False], ids=["confirmed", "later-confirmed"])
@pytest.mark.parametrize(
    ("tags", "level", "expected"),
    [
        (["治疗", "费用回复"], 4, "选择标签：治疗、费用回复，时长：9小时"),
        ([], 3, "不选标签，时长：9小时"),
        (["支援机械"], 1, "选择标签：支援机械，时长：3小时50分"),
    ],
)
def test_start_is_reported_once_after_confirmation(
    solver, caplog, stable, tags, level, expected
):
    prepare_selection(solver, tags, level)
    solver.wait_for_scene_stable.return_value = stable

    solver.transition()

    message = f"1号招募位：开始招募，{expected}"
    assert user_lines(caplog) == ([message] if stable else [])
    assert solver.agent_choose[1]["choosed"] is stable
    assert solver.recruit_index == (2 if stable else 1)
    assert solver.ticket_number == (9 if stable else 10)
    solver.tap_element.assert_called_once_with("recruit/start_recruit")
    solver.wait_for_scene_stable.assert_called_once_with(Scene.RECRUIT_MAIN)
    solver.choose_time.assert_not_called()

    show_recruiting_slot(solver)
    show_recruiting_slot(solver)

    assert user_lines(caplog) == [message]
    if tags:
        assert recruit_records(caplog)[0].log_recruitment == {
            "event": "start",
            "tags": tags,
            "rarity": level,
        }
    else:
        assert not hasattr(recruit_records(caplog)[0], "log_recruitment")
    assert solver.agent_choose[1]["choosed"] is True
    assert solver.recruit_index == 2
    assert solver.ticket_number == (9 if stable else 10)
    solver.tap_element.assert_called_once()


def test_pending_tag_click_does_not_report_recruitment_started(solver, caplog):
    prepare_selection(solver, ["治疗"])
    solver.tag_not_choosed.return_value = True

    solver.transition()

    assert user_lines(caplog) == []
    assert solver.agent_choose[1]["choosed"] is False
    assert solver.recruit_index == 1
    solver.tap.assert_called_once_with((100, 100))
    solver.tap_element.assert_not_called()
    solver.get_recruit_time.assert_not_called()
    solver.wait_for_scene_stable.assert_not_called()


@pytest.mark.parametrize(
    ("times", "adjustment"),
    [
        ({"hour": 9, "minute": 10}, call(10, 0, mode="minute")),
        ({"hour": 8, "minute": 0}, call(8, 9, mode="hour")),
    ],
)
def test_pending_time_adjustment_does_not_report_started(
    solver, caplog, times, adjustment
):
    prepare_selection(solver, ["治疗"])
    solver.get_recruit_time.side_effect = times.__getitem__

    solver.transition()

    assert user_lines(caplog) == []
    assert solver.agent_choose[1]["choosed"] is False
    assert solver.recruit_index == 1
    assert solver.ticket_number == 10
    assert solver.choose_time.call_args_list == [adjustment]
    solver.tap_element.assert_not_called()
    solver.wait_for_scene_stable.assert_not_called()


def test_three_star_permit_threshold_reports_why_slot_is_skipped(
    solver, caplog, monkeypatch
):
    prepare_selection(solver, [], level=3)
    solver.get_ticket_number.return_value = 3
    monkeypatch.setattr(recruit.config.conf, "recruitment_permit", 5)

    solver.transition()

    assert user_lines(caplog) == ["1号招募位：招募券3张，低于三星招募阈值5张，本次跳过"]
    assert solver.agent_choose[1]["choosed"] is False
    assert solver.recruit_index == 2
    assert solver.ticket_number == 3
    solver.back.assert_called_once_with()
    solver.tap_element.assert_not_called()
    solver.get_recruit_time.assert_not_called()


def test_recognized_slot_scopes_scenes_before_the_result_and_across_same_slot_actions(
    solver, caplog
):
    prepare_selection(solver, [], level=3)
    solver.get_ticket_number.return_value = 3
    position = ((100, 100), (200, 200))
    crop = cv2.imread(
        str(Path(__file__).parent / "fixtures/recruit_result_lava_ready_20261002.png"),
        cv2.IMREAD_GRAYSCALE,
    )
    assert crop is not None
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.recog.gray[730:860, 750:1920] = crop
    solver.get_recruit_tag = Mock(return_value={"治疗": (560, 550)})
    solver.recruit_tags = Mock()

    def run_transition(scene, message, button=None):
        def observe():
            recruit.logger.info(message, extra={"log_group": "recognition"})
            return scene

        solver.scene.side_effect = observe
        solver.find.side_effect = lambda name, **_: position if name == button else None
        solver.transition()

    run_transition(Scene.RECRUIT_MAIN, "返回公招主界面", "recruit/begin_recruit")
    run_transition(Scene.RECRUIT_TAGS, "挑选1号位标签")
    assert solver.recruit_index == 2
    run_transition(Scene.RECRUIT_MAIN, "返回后检查下一槽位", "recruit/recruit_done")
    run_transition(Scene.SKIP, "跳过开包动画")
    run_transition(Scene.RECRUIT_AGENT, "开包干员展示", recruit.job_list[0])
    run_transition(Scene.RECRUIT_MAIN, "领取后检查原槽位", "recruit/begin_recruit")
    run_transition(Scene.RECRUIT_TAGS, "挑选2号位标签")
    solver.agent_choose[2] = choice(["治疗"])
    run_transition(Scene.RECRUIT_MAIN, "确认2号位正在招募", "recruit/job_requirements")
    recruit.logger.info("公招操作之外的独立记录")

    records = {record.getMessage(): record for record in caplog.records}
    first = records["1号招募位：检查招募标签"]
    second = records["2号招募位：准备领取干员"]
    assert first.log_event == {**first.log_parent, "phase": "started"}
    assert second.log_event == {**second.log_parent, "phase": "started"}
    assert first.log_parent["slot"] == 1
    assert second.log_parent["slot"] == 2
    assert first.log_parent["id"] != second.log_parent["id"]
    assert records["挑选1号位标签"].log_parent == first.log_parent
    skipped = records["1号招募位：招募券3张，低于三星招募阈值5张，本次跳过"]
    assert skipped.log_parent == first.log_parent
    assert not hasattr(records["返回公招主界面"], "log_parent")
    assert not hasattr(records["返回后检查下一槽位"], "log_parent")
    assert not hasattr(records["公招操作之外的独立记录"], "log_parent")
    for message in (
        "跳过开包动画",
        "开包干员展示",
        "2号招募位：招募获得：炎熔",
        "领取后检查原槽位",
        "挑选2号位标签",
        "2号招募位：识别标签：治疗",
        "2号招募位：开始招募，选择标签：治疗，时长：9小时",
    ):
        assert records[message].log_parent == second.log_parent
    assert [
        record.log_event for record in caplog.records if hasattr(record, "log_event")
    ] == [
        first.log_event,
        {**first.log_parent, "phase": "completed"},
        second.log_event,
        {**second.log_parent, "phase": "completed"},
    ]
    assert solver.result_agent == {2: "炎熔"}


def test_unreadable_result_closes_the_slot_without_reporting_a_recruitment(
    solver, caplog
):
    solver.check_current_focus = Mock()
    solver.sleep = Mock()
    solver.scene.side_effect = [Scene.RECRUIT_MAIN, Scene.RECRUIT_AGENT]
    position = ((100, 100), (200, 200))
    solver.find.side_effect = lambda name, **_: (
        position if name == "recruit/recruit_done" else None
    )

    assert solver.run() == ({}, {})

    started, warning, failed = recruit_records(caplog)
    assert started.getMessage() == "1号招募位：准备领取干员"
    assert started.log_event == {**started.log_parent, "phase": "started"}
    assert warning.getMessage() == "公招干员职业图标连续5次未识别，结束本次公招"
    assert warning.levelno == logging.WARNING
    assert warning.log_parent == started.log_parent
    assert failed.getMessage() == "1号招募位：检查未完成"
    assert failed.log_event == {**started.log_parent, "phase": "failed"}
    assert solver.recruit_index == 1


@pytest.mark.parametrize(
    ("error", "phase", "message"),
    [
        (recruit.MowerExit, "stopped", "1号招募位：已停止检查"),
        (RuntimeError, "failed", "1号招募位：检查未完成"),
    ],
)
def test_interrupted_run_closes_the_same_pending_slot(
    solver, caplog, error, phase, message
):
    solver.check_current_focus = Mock()
    solver.scene.return_value = Scene.RECRUIT_MAIN
    position = ((100, 100), (200, 200))
    solver.find.side_effect = lambda name, **_: (
        position if name == "recruit/recruit_done" else None
    )
    solver.tap.side_effect = error

    with pytest.raises(error):
        solver.run()

    started, terminal = recruit_records(caplog)
    assert started.log_event == {**started.log_parent, "phase": "started"}
    assert terminal.getMessage() == message
    assert terminal.log_event == {**started.log_parent, "phase": phase}
    assert not solver.result_agent
    assert solver.recruit_index == 1


def test_obtained_result_is_reported_once_and_run_keeps_summary_private(
    caplog, monkeypatch
):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    crop = cv2.imread(
        str(Path(__file__).parent / "fixtures/recruit_result_lava_ready_20261002.png"),
        cv2.IMREAD_GRAYSCALE,
    )
    assert crop is not None
    recog = Recognizer(Mock())
    recog._gray = np.zeros((1080, 1920), dtype=np.uint8)
    recog._gray[730:860, 750:1920] = crop
    solver = recruit.RecruitSolver(Mock(), recog)
    solver.scene = Mock(return_value=Scene.RECRUIT_AGENT)
    solver.tap = Mock()

    solver.transition()
    solver.transition()

    assert solver.result_agent == {1: "炎熔"}
    assert user_lines(caplog) == ["1号招募位：招募获得：炎熔"]
    obtained = recruit_records(caplog)[0]
    assert obtained.log_agents == ["炎熔"]
    assert solver.tap.call_args_list == [call((500, 500)), call((950, 150))]

    selected = choice(["治疗"], choosed=True)
    unconfirmed = choice(["费用回复"], choosed=False)
    solver.agent_choose = {2: selected, 3: unconfirmed}
    choices_before = deepcopy(solver.agent_choose)
    solver.recruit_index = 5
    solver.scene.return_value = Scene.RECRUIT_MAIN
    solver.check_current_focus = Mock()
    solver.add_recruit_param = Mock()
    notify = Mock()
    template = Mock()
    template.render.return_value = "rendered summary"
    monkeypatch.setattr(recruit, "send_message", notify)
    monkeypatch.setattr(recruit, "recruit_template", template)

    assert solver.run() == ({2: selected}, {1: "炎熔"})

    assert solver.agent_choose == choices_before
    assert user_lines(caplog) == ["1号招募位：招募获得：炎熔", "结束公招"]
    assert any(str(solver.result_agent) in message for message in debug_lines(caplog))
    assert any(str({2: selected}) in message for message in debug_lines(caplog))
    assert "本轮公招领取结果：{1: '炎熔'}" in debug_lines(caplog)
    assert sum("本轮公招已确认安排：" in line for line in debug_lines(caplog)) == 1
    assert not any(line.startswith("2:[") for line in debug_lines(caplog))
    template.render.assert_called_once_with(
        recruit_results={2: selected},
        recruit_get_agent={1: "炎熔"},
        permit_count=None,
        title_text="公招汇总",
    )
    notify.assert_called_once_with(
        "rendered summary", "公招汇总通知", "INFO", body_is_html=True
    )


@pytest.mark.parametrize(
    ("level", "mode", "manual"),
    [(6, 1, True), (1, 1, True), (5, 2, True), (5, 1, False)],
)
def test_rare_tag_logs_preserve_manual_selection_and_notification(
    solver, caplog, monkeypatch, level, mode, manual
):
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_5", mode)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_only5", False)
    candidates = {star: [] for star in range(1, 7)}
    candidates[level] = [
        {
            "tag": ("输出",),
            "result": [{"id": "candidate", "name": "候选干员", "star": level}],
        }
    ]
    solver.recruit_cal = Mock(return_value=candidates)
    notify = Mock()
    monkeypatch.setattr(recruit, "send_message", notify)

    solver.recruit_tags({"输出": (100, 100)})

    expected = ["1号招募位：发现稀有标签：输出"]
    if manual:
        expected.append("1号招募位：保留标签，等待手动选择")
    assert user_lines(caplog) == expected
    assert recruit_records(caplog)[0].log_recruitment == {
        "event": "rare",
        "combinations": [{"tags": ["输出"], "rarity": level}],
        "rarity": level,
    }
    notify.assert_called_once()
    assert notify.call_args.args[1:] == ("公招出现稀有标签", "WARNING")
    assert notify.call_args.kwargs == {"body_is_html": True}
    if level in (6, 1) or manual:
        assert solver.agent_choose == {}
        assert solver.recruit_index == 2
        solver.back.assert_called_once_with()
    else:
        assert solver.agent_choose[1] == {
            "tags": ["输出"],
            "result": candidates[level][0]["result"],
            "level": level,
            "choosed": False,
        }
        assert solver.recruit_index == 1
        solver.back.assert_not_called()


@pytest.mark.parametrize("same_results", [False, True])
@pytest.mark.parametrize("only_unique", [False, True])
def test_all_rare_combinations_are_visible_before_equivalent_results_collapse(
    solver, caplog, monkeypatch, same_results, only_unique
):
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_5", 2)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_only5", only_unique)
    first_pool = [{"id": "a", "name": "甲", "star": 5}]
    second_pool = first_pool if same_results else [{"id": "b", "name": "乙", "star": 5}]
    candidates = {star: [] for star in range(1, 7)}
    candidates[5] = [
        {"tag": ("先锋干员", "支援"), "result": first_pool},
        {"tag": ("近战位", "控场"), "result": second_pool},
    ]
    before = deepcopy(candidates)
    solver.recruit_cal = Mock(return_value=candidates)
    notify = Mock()
    template = Mock()
    monkeypatch.setattr(recruit, "send_message", notify)
    monkeypatch.setattr(recruit, "recruit_rarity", template)

    solver.recruit_tags({"先锋干员": (100, 100), "支援": (400, 100)})

    expected = ["1号招募位：发现稀有标签：先锋干员＋支援；近战位＋控场"]
    automatic = same_results and only_unique
    if not automatic:
        expected.append("1号招募位：保留标签，等待手动选择")
    assert user_lines(caplog) == expected
    assert recruit_records(caplog)[0].log_recruitment == {
        "event": "rare",
        "combinations": [
            {"tags": ["先锋干员", "支援"], "rarity": 5},
            {"tags": ["近战位", "控场"], "rarity": 5},
        ],
        "rarity": 5,
    }
    assert candidates == before
    solver.recruit_cal.assert_called_once()
    template.render.assert_called_once_with(
        recruit_results=candidates[5][-1:] if same_results else candidates[5],
        title_text="稀有tag通知",
    )
    notify.assert_called_once()
    if automatic:
        assert solver.agent_choose[1]["tags"] == ["近战位", "控场"]
        assert solver.recruit_index == 1
        solver.back.assert_not_called()
    else:
        assert solver.agent_choose == {}
        assert solver.recruit_index == 2
        solver.back.assert_called_once_with()


def test_empty_slot_with_no_permits_logs_the_actual_count_and_original_slot(
    solver, caplog
):
    solver.scene.return_value = Scene.RECRUIT_MAIN
    solver.find.side_effect = lambda name, **_: (
        ((100, 100), (200, 200)) if name == "recruit/begin_recruit" else None
    )
    solver.get_ticket_number.return_value = 0

    solver.transition()

    assert user_lines(caplog) == []
    assert debug_lines(caplog) == ["1号招募位：招募券0张，跳过空闲栏位"]
    assert solver.recruit_index == 2
    assert solver.ticket_number == 0
    solver.tap.assert_not_called()
    solver.wait_for_scene_stable.assert_not_called()


def test_invalid_tag_results_keep_raw_data_at_debug_and_raise(solver, caplog):
    candidates = {star: [] for star in range(1, 7)}
    solver.recruit_cal = Mock(return_value=candidates)

    with pytest.raises(ValueError, match="筛选tag失败"):
        solver.recruit_tags({"输出": (100, 100)})

    assert user_lines(caplog) == ["1号招募位：标签筛选失败"]
    assert recruit_records(caplog)[0].levelno == logging.ERROR
    assert any(str(candidates) in message for message in debug_lines(caplog))
    assert solver.agent_choose == {}
    assert solver.recruit_index == 1
    solver.tap.assert_not_called()
    solver.back.assert_not_called()
