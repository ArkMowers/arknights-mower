"""连续换班中的已确认页面转换推进场景停留计时。"""

from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_mixin, base_schedule
from arknights_mower.tests import dorm_recovery_tests
from arknights_mower.utils import config, recognize
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver

solver = dorm_recovery_tests.solver
ROOM = dorm_recovery_tests.ROOM

# 原日志中 14 次房间结束观测的时刻，覆盖 273.255 秒。
ROOM_CHECK_TIMES = (
    "08:44:37.301",
    "08:44:48.235",
    "08:44:59.081",
    "08:45:10.385",
    "08:45:30.669",
    "08:45:46.125",
    "08:46:18.467",
    "08:46:36.413",
    "08:46:48.842",
    "08:47:09.794",
    "08:47:18.533",
    "08:47:38.929",
    "08:48:13.626",
    "08:49:10.556",
)


@pytest.fixture
def shift_observation(solver, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 13, 8, 44, 37, 301000)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(recognize, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(config, "stop_mower", Event())
    config.conf.run_order_delay = 3
    solver.device = MagicMock()
    solver.recog = Recognizer(solver.device)
    solver.recog.scene = solver.recog.last_scene = Scene.INFRA_DETAILS
    solver.recog.last_scene_time = Clock.now()
    solver.page = "details"

    def find(resource, *args, **kwargs):
        visible = {
            "map": {"control_central", "infra_overview"},
            "details": {"arrange_check_in_on", "room_detail"},
            "selection": {"confirm_blue", "arrange_order_options_scene"},
            "login": {"login_logo", "hypergryph", "login_awake"},
        }
        return ((0, 0), (8, 8)) if resource in visible[solver.page] else None

    solver.recog.find = MagicMock(side_effect=find)
    solver.find = BaseSolver.find.__get__(solver)
    solver.scene = BaseSolver.scene.__get__(solver)
    solver.enter_room = base_mixin.BaseMixin.enter_room.__get__(solver)
    solver.detect_room = lambda: ROOM if solver.page == "details" else ""
    solver.recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.device.screencap.return_value = (
        None,
        solver.recog._img,
        np.zeros((1080, 1920), dtype=np.uint8),
    )
    monkeypatch.setattr(
        base_mixin.segment,
        "base",
        lambda *args, **kwargs: {ROOM: ((10, 10), (20, 10), (20, 20), (10, 20))},
    )

    def change_page(page):
        solver.page = page
        solver.recog.update()

    solver.device.exit.side_effect = lambda: change_page("login")

    def tap(*args, **kwargs):
        change_page("details" if solver.page == "map" else "selection")

    def sleep(seconds=1):
        Clock.current += timedelta(seconds=seconds)
        solver.recog.update()

    solver.tap = MagicMock(side_effect=tap)
    solver.sleep = MagicMock(side_effect=sleep)
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.prepare_dorm_selection = MagicMock(return_value=[])
    original_confirm = solver.tap_confirm.side_effect

    def confirm(*args, **kwargs):
        original_confirm(*args, **kwargs)
        change_page("details")

    solver.tap_confirm.side_effect = confirm
    return solver, Clock, change_page


@pytest.mark.parametrize("selection_required", [False, True])
def test_consecutive_room_arrangements_do_not_exit_game(
    shift_observation, selection_required
):
    solver, clock, change_page = shift_observation
    target = solver.physical.copy()
    original_choose = solver.choose_agent.side_effect
    for timestamp in ROOM_CHECK_TIMES[1:]:
        completed_at = datetime.fromisoformat(f"2026-10-13T{timestamp}")
        clock.current += timedelta(seconds=0.6)
        change_page("map")
        if selection_required:
            # 交换两个岗位，确保经过真实选人入口及安排后驻员核验。
            target[-2:] = reversed(target[-2:])
        solver.task.plan = {ROOM: target.copy()}

        def room_detail(*args):
            if not selection_required:
                clock.current = completed_at

        def choose(*args, **kwargs):
            original_choose(*args, **kwargs)
            clock.current = completed_at

        solver.turn_on_room_detail.side_effect = room_detail
        solver.choose_agent.side_effect = choose
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
        assert solver.physical == target
        assert solver.task.plan == {}
        solver.device.exit.assert_not_called()

    assert solver.choose_agent.call_count == (13 if selection_required else 0)
    assert clock.now() - datetime(2026, 10, 13, 8, 44, 37, 301000) == timedelta(
        seconds=273.255
    )


def test_confirmed_selection_page_restarts_room_timeout(shift_observation):
    solver, clock, change_page = shift_observation
    change_page("details")
    clock.current += timedelta(seconds=269)
    target = dorm_recovery_tests.FINAL.copy()
    solver.task.plan = {ROOM: target}
    original_choose = solver.choose_agent.side_effect

    def choose(*args, **kwargs):
        assert solver.recog.last_scene == Scene.INFRA_ARRANGE_ORDER
        assert solver.recog.last_scene_time == clock.now()
        original_choose(*args, **kwargs)
        clock.current += timedelta(seconds=2)

    solver.choose_agent.side_effect = choose
    solver.agent_arrange_room({}, ROOM, solver.task.plan, skip_enter=True)
    assert solver.physical == target
    assert solver.recog.last_scene == Scene.INFRA_DETAILS
    observed_at = solver.recog.last_scene_time
    clock.current = observed_at + timedelta(seconds=270)
    solver.sleep(0)
    assert solver.scene() == Scene.INFRA_DETAILS
    solver.device.exit.assert_not_called()
    clock.current += timedelta(seconds=1)
    solver.sleep(0)
    assert solver.scene() == Scene.UNDEFINED
    solver.device.exit.assert_called_once_with()


def test_repeated_map_entry_attempts_preserve_timeout(shift_observation):
    solver, clock, change_page = shift_observation
    change_page("map")
    assert solver.scene() == Scene.INFRA_MAIN
    solver.tap.side_effect = lambda *args, **kwargs: None
    solver.back_to_index = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    clock.current += timedelta(seconds=271)
    with pytest.raises(RuntimeError, match="未成功进入房间"):
        solver.enter_room(ROOM, max_attempts=1)
    solver.device.exit.assert_called_once_with()
    solver.tap.assert_not_called()
