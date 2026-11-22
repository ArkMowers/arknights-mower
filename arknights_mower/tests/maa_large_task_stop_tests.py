import sys
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import maa_control  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit, csleep  # noqa: E402
from arknights_mower.utils.device.device import Device  # noqa: E402
from arknights_mower.utils.device.io_budget import io_timeout  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402


@pytest.mark.parametrize("kind", ["rogue", "sss", "rcl"])
@pytest.mark.parametrize(
    ("handoff", "failure"),
    [
        (False, None),
        (False, "stop"),
        (True, None),
        (True, "stop"),
        (True, "rejected"),
        (True, "release"),
        (True, "android_stopped"),
        (True, "android_running"),
        (True, "android_query_error"),
    ],
)
def test_mower_stop_cancels_large_task_and_hands_off_only_after_cleanup(
    monkeypatch, tmp_path, kind, handoff, failure
):
    conf = Conf(maa_rg_enable=1, maa_long_task_type=kind)
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    keep_game = threading.Event()
    if handoff:
        keep_game.set()
    monkeypatch.setattr(
        base_schedule.config, "keep_game_on_stop", keep_game, raising=False
    )
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = MagicMock()
    solver.device = MagicMock()
    solver.recog = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.TERMINAL_MAIN)
    solver.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=2))]
    solver.last_execution = {"maa": None}
    for method in (
        "back_to_index",
        "scene_graph_navigation",
        "initialize_maa",
        "release_maa",
        "maa_stop",
        "append_maa_theme_task",
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
    solver.maa_stop.return_value = True
    solver.release_maa.return_value = True
    if failure == "stop":
        solver.maa_stop.side_effect = RuntimeError("stop failed")
    if failure == "rejected":
        solver.maa_stop.return_value = 0
    if failure == "release":
        solver.release_maa.return_value = False
    android = bool(failure and failure.startswith("android_"))
    monkeypatch.setenv("MOWER_ANDROID", "1" if android else "0")
    order = MagicMock()
    order.attach_mock(solver.maa_stop, "stop")
    order.attach_mock(solver.device.exit_after_task_stop, "close_game")
    order.attach_mock(solver.release_maa, "release")
    if android:
        now = 0.0

        def sleep(seconds):
            nonlocal now
            now += seconds

        monkeypatch.setattr(maa_control, "monotonic", lambda: now, raising=False)
        monkeypatch.setattr(maa_control, "sleep", sleep, raising=False)

        class Bridge:
            def call(self, method, *, socket_timeout=None, **params):
                return order.query_running(
                    method, socket_timeout=socket_timeout, **params
                )

        bridge = order.query_running
        monkeypatch.setitem(
            sys.modules, "mower_android.bridge", SimpleNamespace(Bridge=Bridge)
        )
        if failure == "android_stopped":
            bridge.side_effect = [True, False]
        elif failure == "android_query_error":
            bridge.side_effect = TimeoutError("bridge did not answer")
        else:
            bridge.return_value = True
    with pytest.raises(
        RuntimeError if not handoff and failure == "stop" else MowerExit
    ):
        solver.maa_plan_solver([])
    if handoff:
        expected = [call.stop()]
        if android:
            queries = bridge.call_args_list
            assert queries
            budget = queries[0].kwargs["socket_timeout"]
            assert 0 < budget <= 5
            assert all(
                args == ("maa_running",) and 0 < kwargs["socket_timeout"] <= budget
                for args, kwargs in queries
            )
            assert now <= budget
            if failure == "android_stopped":
                assert len(queries) == 2
            elif failure == "android_running":
                assert now == pytest.approx(budget)
            expected.extend(
                call.query_running(*args, **kwargs) for args, kwargs in queries
            )
        expected.append(call.release())
        if failure and failure != "android_stopped":
            expected.append(call.close_game())
            solver.device.exit_after_task_stop.assert_called_once_with()
        else:
            solver.device.exit_after_task_stop.assert_not_called()
    else:
        expected = [call.stop(), call.close_game(), call.release()]
    assert order.mock_calls[1 : 1 + len(expected)] == expected
    solver.sleep.assert_not_called()
    solver.append_maa_theme_task.assert_not_called()
    solver.rest_until_next_task.assert_not_called()
    solver.device.check_current_focus.assert_not_called()
    assert len(solver.tasks) == 1
    assert base_schedule.config.stop_mower.is_set()


@pytest.mark.parametrize(
    ("bounded_query", "bounded_exit"), [(False, False), (False, True), (True, False)]
)
def test_android_handoff_requires_both_host_capabilities(
    monkeypatch, caplog, bounded_query, bounded_exit
):
    query = MagicMock(
        side_effect=AssertionError("unsupported host must not be queried")
    )

    class LegacyBridge:
        def call(self, method, **params):
            return query(method, **params)

    class CurrentBridge:
        def call(self, method, *, socket_timeout=None, **params):
            return query(method, socket_timeout=socket_timeout, **params)

    stop = threading.Event()
    stop.set()
    monkeypatch.setenv("MOWER_ANDROID", "1")
    monkeypatch.setattr(base_schedule.config, "stop_mower", stop)
    monkeypatch.setattr(base_schedule.config, "keep_game_on_stop", stop)
    monkeypatch.setitem(
        sys.modules,
        "mower_android.bridge",
        SimpleNamespace(Bridge=CurrentBridge if bounded_query else LegacyBridge),
    )
    exit_game = MagicMock()
    device = (
        SimpleNamespace(exit_after_task_stop=exit_game)
        if bounded_exit
        else SimpleNamespace()
    )
    solver = SimpleNamespace(
        MAA=object(),
        device=device,
        maa_stop=MagicMock(return_value=True),
        release_maa=MagicMock(return_value=True),
    )

    maa_control.stop_for_mower_exit(solver, True, False)

    solver.maa_stop.assert_called_once_with()
    solver.release_maa.assert_called_once_with()
    query.assert_not_called()
    exit_game.assert_not_called()
    assert "更新 APK" in caplog.text
    assert "保留当前游戏" not in caplog.text


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
