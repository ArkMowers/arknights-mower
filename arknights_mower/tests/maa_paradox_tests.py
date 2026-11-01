import io
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule, record
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils import maa_copilot as library
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver

files = helpers.files
copilot_scheduler = helpers.scheduler

SCRIPT = {"stage_name": "mem_test_1", "actions": [], "doc": {"title": "悖论作业"}}


@pytest.fixture
def scheduler(copilot_scheduler, monkeypatch):
    monkeypatch.setattr(
        copilot_scheduler, "to_operator_list", MagicMock(return_value=True)
    )
    return copilot_scheduler


def upload(stage="mem_test_1"):
    return library.store_script(
        json.dumps({**SCRIPT, "stage_name": stage}).encode(), paradox=True
    )


def test_separate_library_and_integer_id_recognition_mode(files, monkeypatch):
    monkeypatch.setattr(
        library, "get_path", lambda value: files / value.rsplit("/", 1)[-1]
    )
    info = upload()
    assert upload() == info
    conf = Conf(paradox={"scripts": [{"id": info["id"]}]}).paradox
    assert library.build_paradox_params(conf.scripts[0], 2) == {
        "list": [
            {
                "id": 2,
                "filename": str(files / "paradox-copilots" / (info["id"] + ".json")),
            }
        ]
    }
    assert library.list_scripts() == []
    assert library.list_scripts(paradox=True) == [info]
    with pytest.raises(ValueError):
        library.store_script(json.dumps(SCRIPT).encode())
    with pytest.raises(ValueError):
        library.store_script(b'{"stage_name":"1-7","actions":[]}', paradox=True)


def test_queue_resumption_persists_separately_and_completed_run_stays_finished(
    scheduler,
):
    conf = base_schedule.config.conf
    conf.maa_long_task_type = "paradox"
    one, two = upload(), upload("mem_other_2")
    conf.paradox = Conf(
        paradox={"scripts": [{"id": one["id"]}, {"id": two["id"]}]}
    ).paradox

    def emit(message, chain="ParadoxCopilot"):
        scheduler.on_maa_callback(
            message,
            json.dumps(
                {"taskchain": chain, "taskid": scheduler.MAA.append_task.call_count}
            ).encode(),
            None,
        )

    def finish_then_interrupt():
        emit(10002 if scheduler.MAA.append_task.call_count == 1 else 10004)
        return False

    scheduler.MAA.running.side_effect = finish_then_interrupt
    scheduler.maa_plan_solver()
    assert record.load_maa_paradox_progress()["next"] == 1
    assert record.load_maa_copilot_progress() == {}
    scheduler.maa_paradox_progress = {}
    scheduler.MAA.running.side_effect = lambda: emit(10002) or False
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 3
    assert scheduler.MAA.append_task.call_args.args[0] == "ParadoxCopilot"
    assert scheduler.MAA.append_task.call_args.args[1]["list"][0]["id"] == 1
    for _ in range(3):
        scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 3
    assert record.load_maa_paradox_progress()["next"] == 2
    conf.paradox.run_id = "manual-new-round"
    scheduler.MAA.running.side_effect = None
    scheduler.MAA.running.return_value = False
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 4
    emit(20003)
    emit(10002, chain="Copilot")
    assert scheduler.maa_paradox_progress["next"] == 0
    emit(10000)
    for _ in range(3):
        scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 4
    conf.paradox.run_id = "retry"
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 5


@pytest.mark.parametrize(
    "texts,ready",
    [
        ([("等级", 0.95)], True),
        ([("稀有度", 0.8)], True),
        ([("获取时间", 0.9)], True),
        ([("等级", 0.79)], False),
        ([("干员等级提升", 0.99)], False),
        ([], False),
    ],
)
def test_operator_navigation_uses_existing_bar_and_confirms_sort_tab(
    monkeypatch, texts, ready
):
    from arknights_mower.utils import rapidocr

    solver = object.__new__(BaseSolver)
    solver.scene = MagicMock(side_effect=[Scene.INDEX, Scene.NAVIGATION_BAR])
    solver.tap_element = MagicMock(return_value=True)
    solver.ctap = MagicMock()
    solver.wait_for_scene_stable = MagicMock(return_value=True)
    solver.find = MagicMock(return_value=None)
    solver.recog = MagicMock()
    solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    engine = MagicMock(
        return_value=([[[], text, score] for text, score in texts], None)
    )
    monkeypatch.setattr(rapidocr, "engine", engine)

    assert solver.to_operator_list() is ready
    solver.tap_element.assert_called_once_with("nav_button")
    solver.ctap.assert_called_once_with((460, 365))
    assert engine.call_args.args[0].shape == (204, 262, 3)


@pytest.mark.parametrize("failure", ["bar", "unstable", "overlay", "connecting"])
def test_unconfirmed_operator_navigation_never_accepts_page(monkeypatch, failure):
    from arknights_mower.utils import rapidocr

    solver = object.__new__(BaseSolver)
    solver.get_navigation = MagicMock(return_value=failure != "bar")
    solver.tap_nav_element = MagicMock()
    solver.wait_for_scene_stable = MagicMock(return_value=failure != "unstable")
    solver.find = lambda name: (
        name == {"overlay": "nav_bar", "connecting": "connecting"}.get(failure)
    )
    engine = MagicMock()
    monkeypatch.setattr(rapidocr, "engine", engine)
    assert not solver.to_operator_list()
    engine.assert_not_called()
    if failure == "bar":
        solver.tap_nav_element.assert_not_called()


def test_paradox_dispatch_navigates_before_native_admission(scheduler):
    conf = base_schedule.config.conf
    conf.maa_long_task_type = "paradox"
    conf.paradox.scripts = Conf(
        paradox={"scripts": [{"id": upload()["id"]}]}
    ).paradox.scripts
    calls = MagicMock()
    for name in ("release_maa", "back_to_index", "to_operator_list", "initialize_maa"):
        calls.attach_mock(getattr(scheduler, name), name)
    calls.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.maa_plan_solver()
    names = [call[0] for call in calls.mock_calls]
    assert names.index("release_maa") < names.index("back_to_index")
    assert names.index("back_to_index") < names.index("to_operator_list")
    assert (
        names.index("to_operator_list")
        < names.index("initialize_maa")
        < names.index("append")
    )


@pytest.mark.parametrize("outcome", [False, TimeoutError("timeout")])
def test_failed_navigation_preserves_queue_and_blocks_unchanged_dispatch(
    scheduler, outcome
):
    conf = base_schedule.config.conf
    conf.maa_long_task_type = "paradox"
    conf.paradox.scripts = Conf(
        paradox={"scripts": [{"id": upload()["id"]}]}
    ).paradox.scripts
    if isinstance(outcome, Exception):
        scheduler.to_operator_list.side_effect = outcome
    else:
        scheduler.to_operator_list.return_value = outcome
    original = scheduler.tasks[0]
    for attempt in range(1, 4):
        scheduler.maa_plan_solver()
        assert scheduler.rest_until_next_task.call_count == attempt
    scheduler.to_operator_list.assert_called_once_with()
    scheduler.initialize_maa.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
    assert record.load_maa_paradox_progress()["next"] == 0
    assert record.load_maa_paradox_progress()["failed"] is True
    assert scheduler.tasks == [original]
    scheduler.to_operator_list.side_effect = None
    scheduler.to_operator_list.return_value = True
    conf.paradox.run_id = "manual-retry"
    scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_called_once()


@pytest.mark.parametrize("reason", ["stop_maa", "stop_mower", "deadline"])
def test_navigation_cancellation_retains_unfinished_queue(scheduler, reason):
    conf = base_schedule.config.conf
    conf.maa_long_task_type = "paradox"
    conf.paradox.scripts = Conf(
        paradox={"scripts": [{"id": upload()["id"]}]}
    ).paradox.scripts
    scheduler.device = MagicMock()

    def cancel():
        if reason == "deadline":
            scheduler.tasks[0].time = datetime.now() + timedelta(seconds=20)
        else:
            getattr(base_schedule.config, reason).set()
        return False

    scheduler.to_operator_list.side_effect = cancel
    if reason == "stop_mower":
        with pytest.raises(base_schedule.MowerExit):
            scheduler.maa_plan_solver()
        scheduler.device.exit_after_task_stop.assert_called_once_with()
    else:
        scheduler.maa_plan_solver()
        scheduler.device.exit_after_task_stop.assert_not_called()
    scheduler.initialize_maa.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
    assert record.load_maa_paradox_progress()["next"] == 0
    assert record.load_maa_paradox_progress()["failed"] is False


def test_navigation_deadline_prevents_native_admission(scheduler, monkeypatch):
    conf = base_schedule.config.conf
    conf.maa_long_task_type = "paradox"
    conf.paradox.scripts = Conf(
        paradox={"scripts": [{"id": upload()["id"]}]}
    ).paradox.scripts
    clock = [0.0]
    monkeypatch.setattr(base_schedule, "monotonic", lambda: clock[0])

    def slow_navigation():
        clock[0] = 60.1
        return True

    scheduler.to_operator_list.side_effect = slow_navigation
    scheduler.maa_plan_solver()
    scheduler.initialize_maa.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
    assert record.load_maa_paradox_progress()["next"] == 0
    assert record.load_maa_paradox_progress()["failed"] is True


@pytest.mark.parametrize("reason", ["stop_maa", "stop_mower"])
def test_stop_during_initialization_does_not_submit_paradox_task(scheduler, reason):
    conf = base_schedule.config.conf
    conf.maa_long_task_type = "paradox"
    conf.paradox.scripts = Conf(
        paradox={"scripts": [{"id": upload()["id"]}]}
    ).paradox.scripts
    scheduler.device = MagicMock()
    scheduler.initialize_maa.side_effect = getattr(base_schedule.config, reason).set
    if reason == "stop_mower":
        with pytest.raises(base_schedule.MowerExit):
            scheduler.maa_plan_solver()
        scheduler.device.exit_after_task_stop.assert_called_once_with()
    else:
        scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_not_called()
    assert record.load_maa_paradox_progress()["failed"] is False


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/maa-paradox"),
        ("HEAD", "/maa-paradox"),
        ("POST", "/maa-paradox"),
        ("DELETE", "/maa-paradox/" + "a" * 64),
    ],
)
@pytest.mark.parametrize("token", [None, "invalid"])
def test_library_auth_rejects_before_file_access(
    files, monkeypatch, method, path, token
):
    import server

    monkeypatch.setattr(server.app, "token", "test-paradox", raising=False)
    read = MagicMock()
    monkeypatch.setattr(library, "list_scripts", read)
    monkeypatch.setattr(library, "store_script", read)
    monkeypatch.setattr(library, "script_path", read)
    response = server.app.test_client().open(
        path, method=method, headers={} if token is None else {"token": token}
    )
    assert response.status_code == 403
    read.assert_not_called()


def test_authorized_paradox_library_upload_selection_guard_and_delete(
    files, monkeypatch
):
    import server

    monkeypatch.setattr(server.app, "token", "test-paradox", raising=False)
    monkeypatch.setattr(server.config, "conf", Conf())
    monkeypatch.setattr(server, "_maa_busy_response", lambda: None)
    client = server.app.test_client()
    headers = {"token": "test-paradox"}
    response = client.post(
        "/maa-paradox",
        headers=headers,
        data={"copilot": (io.BytesIO(json.dumps(SCRIPT).encode()), "operation.json")},
    )
    assert response.status_code == 200
    assert client.head("/maa-paradox", headers=headers).status_code == 200
    info = response.get_json()
    assert client.get("/maa-paradox", headers=headers).get_json() == {"scripts": [info]}
    server.config.conf.paradox.scripts = Conf(
        paradox={"scripts": [{"id": info["id"]}]}
    ).paradox.scripts
    assert (
        client.delete("/maa-paradox/" + info["id"], headers=headers).status_code == 409
    )
    server.config.conf.paradox.scripts = []
    assert client.delete("/maa-paradox/" + info["id"], headers=headers).get_json() == {
        "ok": True
    }
