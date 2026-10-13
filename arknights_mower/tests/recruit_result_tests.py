from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import recruit
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene


def result_frame(state):
    # 日志调度-20261002-065219.zip 的错误截图，保留职业、姓名与信物区域。
    # animation: 1790895139359432800.jpg; ready: 1790895140736340800.jpg。
    path = Path(__file__).parent / f"fixtures/recruit_result_lava_{state}_20261002.png"
    crop = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert crop is not None
    frame = np.zeros((1080, 1920), dtype=np.uint8)
    frame[730:860, 750:1920] = crop
    return frame


def make_solver(state="animation"):
    device = Mock()
    recog = Recognizer(device)
    recog._gray = result_frame(state)
    solver = recruit.RecruitSolver(device, recog)
    solver.scene = Mock(return_value=Scene.RECRUIT_AGENT)
    solver.tap = Mock()
    return solver


def test_result_without_profession_keeps_display_open():
    solver = make_solver()
    assert solver.find("recruit/agent_token") is not None
    assert all(solver.find(name) is None for name in recruit.job_list)

    with pytest.raises(RecognizeError, match="职业"):
        solver.transition()

    assert solver.result_agent == {}
    assert solver.recruit_index == 1
    solver.tap.assert_not_called()


def test_ready_result_is_recorded_before_one_dismissal():
    solver = make_solver("ready")
    records_at_tap = []
    solver.tap.side_effect = lambda *_: records_at_tap.append(dict(solver.result_agent))

    solver.transition()

    assert solver.result_agent == {1: "炎熔"}
    assert records_at_tap == [{1: "炎熔"}]
    solver.tap.assert_called_once_with((500, 500))


def test_recorded_integer_slot_is_not_recognized_again():
    solver = make_solver()
    solver.result_agent = {1: "炎熔"}
    solver.find = Mock(side_effect=AssertionError("已记录的结果不应重新识别"))

    solver.transition()

    solver.find.assert_not_called()
    assert solver.result_agent == {1: "炎熔"}
    solver.tap.assert_called_once()


@pytest.mark.parametrize("error", [MowerExit(), RuntimeError("截图失败")])
def test_recognition_failure_propagates_without_dismissal(error):
    solver = make_solver()
    solver.find = Mock(side_effect=error)

    with pytest.raises(type(error)) as caught:
        solver.transition()

    assert caught.value is error
    assert solver.result_agent == {}
    solver.tap.assert_not_called()


def test_name_matching_failure_does_not_dismiss(monkeypatch):
    solver = make_solver("ready")
    monkeypatch.setattr(
        recruit, "cropimg", Mock(side_effect=ValueError("姓名裁剪失败"))
    )

    with pytest.raises(ValueError, match="姓名裁剪失败"):
        solver.transition()

    assert solver.result_agent == {}
    solver.tap.assert_not_called()


def prepare_run(monkeypatch, solver, scenes):
    solver.scene = Mock(side_effect=scenes)
    find = solver.find
    solver.find = Mock(
        side_effect=lambda name, *args, **kwargs: (
            ((400, 120), (540, 220))
            if name == "recruit/recruit_lock"
            else find(name, *args, **kwargs)
        )
    )
    solver.check_current_focus = Mock()
    solver.add_recruit_param = Mock()
    solver.recog.update = Mock()
    notify = Mock()
    monkeypatch.setattr(recruit, "send_message", notify)
    return notify


def test_run_retries_animation_then_records_ready_frame(monkeypatch):
    solver = make_solver()
    notify = prepare_run(
        monkeypatch,
        solver,
        [Scene.RECRUIT_AGENT, Scene.RECRUIT_AGENT, Scene.RECRUIT_MAIN],
    )
    observations = []

    def next_frame(interval):
        observations.append(
            (interval, dict(solver.result_agent), solver.tap.call_count)
        )
        solver.recog._gray = result_frame("ready")

    solver.sleep = Mock(side_effect=next_frame)

    assert solver.run() == ({}, {1: "炎熔"})

    assert observations == [(3, {}, 0)]
    solver.tap.assert_called_once_with((500, 500))
    notify.assert_called_once()


def test_run_stops_after_existing_recognition_budget(monkeypatch):
    solver = make_solver()
    budget = recruit.config.MAX_RETRYTIME
    notify = prepare_run(
        monkeypatch,
        solver,
        [Scene.RECRUIT_AGENT] * budget + [Scene.RECRUIT_MAIN],
    )
    solver.sleep = Mock()

    assert solver.run() == ({}, {})

    assert solver.scene.call_count == budget
    assert solver.sleep.call_count == budget
    assert solver.recruit_index == 1
    solver.tap.assert_not_called()
    notify.assert_not_called()
