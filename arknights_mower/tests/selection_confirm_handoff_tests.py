"""迟到的撤换确认中断筛选，房间实读决定是否恢复目标阵容。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers.base_mixin import AgentSelectionPageChanged, BaseMixin
from arknights_mower.tests import dorm_recovery_tests
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import Recognizer

solver = dorm_recovery_tests.solver
ROOM = dorm_recovery_tests.ROOM
FINAL = dorm_recovery_tests.FINAL
PROMPT = (
    Path(__file__).parent / "fixtures/selection/staffing_secondary_confirm_20261024.jpg"
)


def captured_prompt():
    device = MagicMock()
    device.screencap.side_effect = AssertionError("离线重放不得请求设备截图")
    return Recognizer(device, PROMPT.read_bytes())


@pytest.mark.parametrize("mode", ["medium", "high", "xhigh"])
def test_secondary_prompt_stops_filter_without_input_or_wait(monkeypatch, mode):
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    obj = BaseMixin()
    obj.recog = captured_prompt()
    obj.find = obj.recog.find
    obj.tap = MagicMock()
    obj.sleep = MagicMock()

    with pytest.raises(AgentSelectionPageChanged, match="二次确认"):
        obj.profession_filter("ALL")

    obj.tap.assert_not_called()
    obj.sleep.assert_not_called()
    obj.recog.device.screencap.assert_not_called()


@pytest.mark.parametrize("phase", ["opening", "label"])
def test_prompt_arriving_during_filter_prevents_further_input(phase):
    obj = BaseMixin()
    prompt = captured_prompt()
    state = {"popup": False}

    def find(name):
        if state["popup"]:
            return prompt.find(name)
        if name == "confirm_blue":
            x = 1724 if phase == "opening" else 1609
            return ((x, 990), (x + 89, 1041))
        return None

    obj.find = find
    obj.get_color = MagicMock(return_value=(0, 0, 0))
    obj.tap = MagicMock(side_effect=lambda *a, **k: state.update(popup=True))
    obj.sleep = MagicMock()

    with pytest.raises(AgentSelectionPageChanged, match="二次确认"):
        obj.profession_filter("ALL")

    obj.tap.assert_called_once_with(
        (1860, 60) if phase == "opening" else (1918, 135), interval=0.1
    )
    obj.sleep.assert_not_called()


@pytest.mark.parametrize("already_completed", [False, True])
def test_late_prompt_recovery_reads_actual_roster_before_confirming_target(
    solver, already_completed
):
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    original_task = solver.task
    original_plan = solver.task.plan
    original_time = solver.task.time
    initial = solver.physical.copy()
    prompt = captured_prompt()
    state = {"popup": False}
    observed = []
    choose = solver.choose_agent.side_effect
    read = solver.get_agent_from_room.side_effect

    def find(name, **kwargs):
        return prompt.find(name, **kwargs) if state["popup"] else True

    def select(*args, **kwargs):
        if solver.choose_agent.call_count == 1:
            state["reads_before_popup"] = len(observed)
            state["popup"] = True
            solver.profession_filter("ALL")
        assert len(observed) > state["reads_before_popup"]
        choose(*args, **kwargs)

    def back(*args, **kwargs):
        if state["popup"]:
            assert solver.task is original_task
            assert solver.task.plan is original_plan
            assert original_plan == {ROOM: FINAL}
            assert solver.confirms == []
            state["popup"] = False
            if already_completed:
                solver.physical = FINAL.copy()

    def observe(*args, **kwargs):
        assert not state["popup"]
        observed.append(solver.physical.copy())
        return read(*args, **kwargs)

    solver.find.side_effect = find
    solver.scene.side_effect = lambda: (
        base.Scene.DOUBLE_CONFIRM if state["popup"] else base.Scene.INFRA_MAIN
    )
    solver.choose_agent.side_effect = select
    solver.back.side_effect = back
    solver.get_agent_from_room.side_effect = observe
    solver.tap = MagicMock(side_effect=AssertionError("不得在迟到弹窗下继续选人"))
    solver.sleep = MagicMock()

    solver.agent_arrange_room({}, ROOM, original_plan)

    assert observed[state["reads_before_popup"]] == (
        FINAL if already_completed else initial
    )
    assert solver.confirms == ([] if already_completed else [FINAL])
    assert solver.physical == FINAL
    assert solver.choose_agent.call_count == (1 if already_completed else 2)
    assert solver.task is original_task
    assert solver.task.time == original_time
    assert solver.task.plan is original_plan and original_plan == {}
    assert not state["popup"]
    solver.tap.assert_not_called()
    solver.sleep.assert_not_called()
    prompt.device.screencap.assert_not_called()


def test_stop_prevents_filter_input_even_with_secondary_prompt(monkeypatch):
    obj = BaseMixin()
    obj.recog = captured_prompt()
    obj.find = MagicMock(wraps=obj.recog.find)
    obj.tap = MagicMock()
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: True))

    with pytest.raises(MowerExit):
        obj.profession_filter("ALL")

    obj.find.assert_not_called()
    obj.tap.assert_not_called()
