"""Offline evidence for explicit selection trials and their production inputs."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import performance_test as module  # noqa: E402
from arknights_mower.solvers.base_mixin import (  # noqa: E402
    AgentSelectionNotReady,
    AgentSelectionPageChanged,
)
from arknights_mower.solvers.performance_test import (  # noqa: E402
    SelectionPerformanceTest,
)
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.csleep import MowerExit, csleep  # noqa: E402
from arknights_mower.utils.device.io_budget import io_timeout  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "stop_mower", module.config.stop_mower.__class__())
    result = SelectionPerformanceTest.__new__(SelectionPerformanceTest)
    result.configuration = config.Conf(performance_mode="auto")
    result.cancelled = MagicMock(return_value=False)
    result.report = MagicMock()
    result.trials = []
    result.entered_room = False
    result.recog = SimpleNamespace(w=1920, h=1080, update=MagicMock())
    result.open_selection = MagicMock()
    result.prepare_round = MagicMock(return_value=([], ["安哲拉", "斯卡蒂"]))
    result.trial = MagicMock()
    result.cancel_selection = MagicMock()
    return result


def test_three_successes_recommend_xhigh_without_changing_conf_or_feedback(solver):
    before = config.conf.model_dump()
    feedback = config.operation_feedback_avg, config.operation_feedback_count
    modes = []
    solver.trial.side_effect = lambda *_: modes.append(solver.performance_profile.mode)
    assert solver.run()["recommended_mode"] == "xhigh"
    assert modes == ["xhigh"] * 3
    assert config.conf.model_dump() == before
    assert feedback == (config.operation_feedback_avg, config.operation_feedback_count)
    solver.cancel_selection.assert_called_once()
    assert not hasattr(solver, "_selection_profile_snapshot")


@pytest.mark.parametrize("failed_round", [1, 2, 3])
def test_first_failure_immediately_restarts_three_rounds_at_lower_mode(
    solver, failed_round
):
    modes = []

    def trial(*_):
        modes.append(solver.performance_profile.mode)
        if len(modes) == failed_round:
            raise AgentSelectionNotReady("检测到干员选择错误")

    solver.trial.side_effect = trial
    result = solver.run()
    assert result["recommended_mode"] == "high"
    assert modes == ["xhigh"] * failed_round + ["high"] * 3
    assert [row["round"] for row in result["trials"] if row["mode"] == "high"] == [
        1,
        2,
        3,
    ]


def test_failure_at_every_mode_never_recommends_low(solver):
    solver.trial.side_effect = AgentSelectionNotReady("误选")
    result = solver.run()
    assert result["status"] == "failed"
    assert result["recommended_mode"] is None
    assert [row["mode"] for row in result["trials"]] == list(module.MODES)
    assert solver.trial.call_count == 4


@pytest.mark.parametrize(
    "error", [MowerExit(), OSError("device lost"), AgentSelectionPageChanged()]
)
def test_cancellation_device_fault_or_page_exit_aborts_without_downgrade(solver, error):
    solver.trial.side_effect = error
    with pytest.raises(type(error)):
        solver.run()
    assert solver.trial.call_count == 1
    assert solver.trials == []
    solver.cancel_selection.assert_called_once()


def test_preparation_failure_and_cleanup_failure_cannot_recommend_mode(solver):
    solver.prepare_round.side_effect = AgentSelectionNotReady("无可用目标")
    with pytest.raises(AgentSelectionNotReady):
        solver.run()
    solver.trial.assert_not_called()
    solver.prepare_round.side_effect = None
    solver.cancel_selection.side_effect = RuntimeError("尚未取消暂选")
    with pytest.raises(RuntimeError, match="尚未取消"):
        solver.run()


def test_deadline_and_explicit_cancellation_bound_io(solver, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    with solver.budget(2):
        assert io_timeout(10) == 2
        clock[0] = 12
        with pytest.raises(module.SelectionTestTimeout):
            io_timeout(10)
        with pytest.raises(module.SelectionTestTimeout):
            csleep(0)
        clock[0] = 11
    solver.cancelled.return_value = True
    with pytest.raises(MowerExit):
        with solver.budget(2):
            pass
    with solver.budget(2, cleanup=True):
        assert io_timeout(10) == 2


@pytest.mark.parametrize(
    "mode,interval,clear",
    [("xhigh", 0, 0.5), ("high", 0.1, 0.3), ("medium", 0.2, 0.5), ("low", 0.2, 0.5)],
)
def test_trial_uses_shared_selection_reorder_and_actual_roster(
    solver, mode, interval, clear
):
    solver.checkpoint = MagicMock()
    solver.swipe_agent_page = MagicMock(return_value=(1, None))
    solver.scan_agent = MagicMock(side_effect=lambda pending, **_: pending.clear())
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock(return_value=(0, None))
    solver.wait_for_arranged_agents = MagicMock(return_value=["斯卡蒂", "安哲拉"])
    solver.tap = MagicMock()
    with solver.profile(mode):
        SelectionPerformanceTest.trial(solver, [], ["安哲拉", "斯卡蒂"])
    assert [call.kwargs["interval"] for call in solver.tap.call_args_list] == [
        clear,
        interval,
        interval,
    ]
    assert solver.tap.call_args_list[1].args == ((1920 * 0.35, 1080 * 0.75),)
    assert solver.wait_for_arranged_agents.call_count == 2


@pytest.mark.parametrize("wrong_after_reorder", [False, True])
def test_stable_wrong_selection_is_failure_even_when_names_were_found(
    solver, wrong_after_reorder
):
    solver.checkpoint = MagicMock()
    solver.swipe_agent_page = MagicMock(return_value=(1, None))
    solver.scan_agent = MagicMock(side_effect=lambda pending, **_: pending.clear())
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock(return_value=(0, None))
    solver.wait_for_arranged_agents = MagicMock(
        side_effect=(["安哲拉", "斯卡蒂"], None) if wrong_after_reorder else [None]
    )
    solver.tap = MagicMock()
    with (
        solver.profile("high"),
        pytest.raises(AgentSelectionNotReady, match="选择错误"),
    ):
        SelectionPerformanceTest.trial(solver, [], ["安哲拉", "斯卡蒂"])


def test_unchanged_page_cannot_pass_when_targets_are_not_selected(solver):
    solver.checkpoint = MagicMock()
    solver.swipe_agent_page = MagicMock(return_value=(1, None))
    solver.scan_agent = MagicMock()
    with (
        solver.profile("xhigh"),
        pytest.raises(AgentSelectionNotReady, match="全部目标"),
    ):
        SelectionPerformanceTest.trial(solver, [], ["安哲拉", "斯卡蒂"])


def test_cleanup_only_uses_back_and_discard_action(solver):
    solver.entered_room = True
    solver.scene = MagicMock(
        side_effect=[
            Scene.INFRA_ARRANGE_ORDER,
            Scene.INFRA_ARRANGE_CONFIRM,
            Scene.INFRA_DETAILS,
        ]
    )
    solver.back = MagicMock()
    solver.tap = MagicMock()
    solver.cancelled.return_value = True
    SelectionPerformanceTest.cancel_selection(solver)
    solver.back.assert_called_once()
    solver.tap.assert_called_once_with((640, 1070), interval=0.5)


def test_wrong_initial_scene_sends_no_input(solver):
    solver.scene = MagicMock(return_value=Scene.INFRA_ARRANGE_ORDER)
    solver.tap = MagicMock()
    solver.enter_room = MagicMock()
    with pytest.raises(RuntimeError, match="基建首页"):
        SelectionPerformanceTest.open_selection(solver)
    solver.tap.assert_not_called()
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("new_names", [["巡林者"], ["斯卡蒂", "安哲拉"]])
def test_preparation_requires_two_new_targets_and_a_restored_first_page(
    solver, monkeypatch, new_names
):
    def page(names):
        return [
            (name, ((630 + index * 215, 488), (818 + index * 215, 520)))
            for index, name in enumerate(names)
        ]

    before = page(["斯卡蒂", "安哲拉"])
    after = page(new_names)
    solver.checkpoint = MagicMock()
    solver.scene = MagicMock(return_value=Scene.INFRA_ARRANGE_ORDER)
    solver.profession_filter = MagicMock()
    solver.tap = MagicMock()
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=before)
    solver.swipe_agent_page = MagicMock(return_value=(1, SimpleNamespace(page=after)))
    solver.recog.img = object()
    monkeypatch.setattr(module, "agent_card_selected", lambda *_: False)
    with pytest.raises(RuntimeError, match="不足两名"):
        SelectionPerformanceTest.prepare_round(solver)


def test_real_fast_scan_and_roster_verification_reject_known_log_misselection(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_mixin

    def page(names):
        return [
            (
                name,
                (
                    (630 + index // 2 * 215, 488 + index % 2 * 421),
                    (818 + index // 2 * 215, 520 + index % 2 * 421),
                ),
            )
            for index, name in enumerate(names)
        ]

    targets = ["乌尔比安", "斯卡蒂"]
    solver.recog.img = page(targets)
    solver.find = MagicMock(return_value=False)
    solver.checkpoint = MagicMock()
    solver.swipe_agent_page = MagicMock(return_value=(1, None))
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock(return_value=(0, None))
    solver.sleep = MagicMock()
    # The recognized coordinates belong to the requested names, but the game
    # selects the wrong first operator before the final roster is read.
    solver.tap = MagicMock(
        side_effect=lambda *_, **__: setattr(
            solver.recog, "img", page(["猎蜂", "斯卡蒂"])
        )
    )
    monkeypatch.setattr(base_mixin, "operator_list", lambda image, **_: image)
    with (
        solver.profile("high"),
        pytest.raises(AgentSelectionNotReady, match="选择错误"),
    ):
        SelectionPerformanceTest.trial(solver, [], targets)
    assert solver.tap.call_count == 2


def test_entry_opens_known_dormitory_and_cleanup_refuses_unknown_dialogs(solver):
    solver.scene = MagicMock(
        side_effect=[Scene.INFRA_MAIN, Scene.INFRA_DETAILS, Scene.INFRA_ARRANGE_ORDER]
    )
    solver.enter_room = MagicMock()
    solver.checkpoint = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.tap = MagicMock()
    SelectionPerformanceTest.open_selection(solver)
    solver.enter_room.assert_called_once_with("dormitory_1", max_attempts=1)
    assert solver.entered_room
    solver.scene = MagicMock(return_value=Scene.DOUBLE_CONFIRM)
    solver.tap.reset_mock()
    with pytest.raises(RuntimeError, match="暂选尚未取消"):
        SelectionPerformanceTest.cancel_selection(solver)
    solver.tap.assert_not_called()
