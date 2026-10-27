import sys
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit, csleep  # noqa: E402
from arknights_mower.utils.device.device import Device  # noqa: E402
from arknights_mower.utils.device.io_budget import io_timeout  # noqa: E402


@pytest.mark.parametrize("kind", ["rogue", "sss", "rcl"])
@pytest.mark.parametrize("stop_failure", [False, True])
def test_mower_stop_cancels_large_task_closes_game_and_releases_without_wait(
    monkeypatch, tmp_path, kind, stop_failure
):
    conf = Conf(maa_rg_enable=1, maa_long_task_type=kind)
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = MagicMock()
    solver.device = MagicMock()
    solver.recog = MagicMock()
    solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(hours=2))]
    solver.last_execution = {"maa": None}
    for method in (
        "back_to_index",
        "initialize_maa",
        "release_maa",
        "maa_stop",
        "restore_maa_theme",
        "rest_until_next_task",
        "sleep",
        "to_reclamation",
    ):
        monkeypatch.setattr(solver, method, MagicMock())
    solver.to_sss = MagicMock(return_value=False)
    if kind == "sss":
        from arknights_mower.solvers import record
        from arknights_mower.utils import maa_copilot

        monkeypatch.setattr(maa_copilot, "get_path", lambda value: tmp_path / value[5:])
        monkeypatch.setattr(record, "get_path", lambda value: tmp_path / value[5:])
        monkeypatch.setattr(record, "_tables_created", False)
        script = maa_copilot.store_script(
            b'{"type":"SSS","stage_name":"SSS","tool_men":{},"stages":[{"stage_name":"one","draw_as_possible":true,"strategies":[],"actions":[]}]}',
            sss=True,
        )
        conf.sss = Conf(sss={"scripts": [{"id": script["id"]}]}).sss
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())

    def stop(_):
        base_schedule.config.stop_mower.set()
        csleep(0)

    monkeypatch.setattr(base_schedule, "csleep", stop)
    if stop_failure:
        solver.maa_stop.side_effect = RuntimeError("stop failed")
    order = MagicMock()
    order.attach_mock(solver.maa_stop, "stop")
    order.attach_mock(solver.device.exit_after_task_stop, "close_game")
    order.attach_mock(solver.release_maa, "release")
    with pytest.raises(RuntimeError if stop_failure else MowerExit):
        solver.maa_plan_solver([])
    assert order.mock_calls[1:4] == [call.stop(), call.close_game(), call.release()]
    solver.sleep.assert_not_called()
    solver.restore_maa_theme.assert_not_called()
    solver.rest_until_next_task.assert_not_called()
    solver.device.check_current_focus.assert_not_called()
    assert len(solver.tasks) == 1
    assert base_schedule.config.stop_mower.is_set()


def test_stop_cleanup_uses_bound_client_once_without_clearing_task_stop(monkeypatch):
    import arknights_mower.utils.device.device as device_module

    event = threading.Event()
    event.set()
    monkeypatch.setattr(base_schedule.config, "stop_mower", event)
    device = object.__new__(Device)
    device._profile = SimpleNamespace(game_package="com.hypergryph.arknights")
    device._check_open = MagicMock()
    device.client = MagicMock()
    device.recover = MagicMock(side_effect=AssertionError("must not recover"))
    now = 100.0
    monkeypatch.setattr(device_module.time, "monotonic", lambda: now)

    def close(command):
        nonlocal now
        assert command == "am force-stop com.hypergryph.arknights"
        csleep(0)
        assert io_timeout(60) == 5
        now += 2
        assert io_timeout(60) == 3

    device.client.run.side_effect = close
    device.exit_after_task_stop()
    device._check_open.assert_called_once_with()
    device.client.run.assert_called_once()
    device.recover.assert_not_called()
    assert event.is_set()
    with pytest.raises(MowerExit):
        csleep(0)


def test_closed_device_does_not_issue_stop_command():
    device = object.__new__(Device)
    device._check_open = MagicMock(side_effect=MowerExit)
    device.client = MagicMock()
    with pytest.raises(MowerExit):
        device.exit_after_task_stop()
    device.client.run.assert_not_called()
