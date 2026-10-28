import io
import json
import sys
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
from arknights_mower.solvers import base_schedule, record  # noqa: E402
from arknights_mower.utils import maa_copilot as library  # noqa: E402
from arknights_mower.utils import maa_sss  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402

SCRIPT = {
    "type": "SSS",
    "stage_name": "保全关卡一",
    "tool_men": {},
    "doc": {"title": "保全作业一"},
    "stages": [
        {
            "stage_name": "第一关",
            "draw_as_possible": True,
            "strategies": [],
            "actions": [],
        }
    ],
}


@pytest.fixture
def storage(monkeypatch, tmp_path):
    def path(value):
        return tmp_path / value[5:]

    monkeypatch.setattr(library, "get_path", path)
    monkeypatch.setattr(maa_sss, "get_path", path)
    monkeypatch.setattr(record, "get_path", path)
    monkeypatch.setattr(record, "_tables_created", False)
    return tmp_path


def upload(data=None):
    return library.store_script(
        json.dumps(SCRIPT if data is None else data).encode(), sss=True
    )


def test_libraries_are_separate_and_sss_dispatch_is_single_round(storage):
    first = upload()
    assert upload() == first
    normal = library.store_script(b'{"stage_name":"1-7","actions":[]}')
    assert library.list_scripts(sss=True) == [first]
    assert library.list_scripts() == [normal]
    conf = Conf(sss={"scripts": [{"id": first["id"], "type": 2, "ec": 3, "times": 4}]})
    assert maa_sss.build_sss_params(conf.sss.scripts[0]) == {
        "filename": str(storage / "config/sss-copilots" / (first["id"] + ".json")),
        "loop_times": 1,
    }


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"stage_name": "1-7", "actions": []},
        {**SCRIPT, "stages": []},
        {**SCRIPT, "tool_men": []},
        {**SCRIPT, "stages": [None]},
        {**SCRIPT, "opers": [1]},
    ],
)
def test_invalid_sss_cannot_write(storage, data):
    with pytest.raises(ValueError):
        upload(data)
    assert not (storage / "config/sss-copilots").exists()


@pytest.mark.parametrize(
    "item",
    [
        {"times": 0},
        {"times": -1},
        {"times": 10000},
        {"times": True},
        {"times": 1.5},
        {"type": 3},
        {"ec": 4},
        {"id": "../sss"},
    ],
)
def test_invalid_queue_options_are_rejected(item):
    with pytest.raises(ValidationError):
        Conf(sss={"scripts": [{"id": "a" * 64, **item}]})


def test_legacy_migration_preserves_navigation_and_does_not_restore_removed_queue(
    storage,
):
    legacy = storage / "sss.json"
    legacy.write_text(json.dumps(SCRIPT))
    conf = Conf(sss={"type": 2, "ec": 3})
    assert maa_sss.migrate_legacy(conf.sss)
    assert conf.sss.scripts[0].model_dump() == {
        "id": upload()["id"],
        "type": 2,
        "ec": 3,
        "times": 1,
    }
    assert legacy.exists()
    restored = Conf(**conf.model_dump(exclude_unset=True))
    restored.sss.scripts = []
    assert not maa_sss.migrate_legacy(restored.sss)
    assert restored.sss.scripts == []


def test_real_config_load_persists_legacy_import_once(storage, monkeypatch):
    import yaml

    from arknights_mower.utils import config

    path = storage / "config/conf.yml"
    path.parent.mkdir()
    path.write_text("sss:\n  type: 2\n  ec: 3\n")
    (storage / "sss.json").write_text(json.dumps(SCRIPT))
    monkeypatch.setattr(config, "conf_path", path)
    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(config, "_load_rescue_plan", MagicMock())
    config.load_conf()
    saved = yaml.safe_load(path.read_text())
    assert saved["sss"]["scripts"][0]["type"] == 2
    assert saved["sss"]["scripts"][0]["ec"] == 3
    assert Conf(**saved).sss.scripts[0].times == 1
    config.load_conf()
    assert len(config.conf.sss.scripts) == 1


@pytest.fixture
def client(monkeypatch, storage):
    import server

    monkeypatch.setattr(server.app, "token", "sss-test", raising=False)
    monkeypatch.setattr(server.config, "conf", Conf())
    monkeypatch.setattr(server, "_maa_busy_response", lambda: None)
    return server.app.test_client()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/sss-copilot"),
        ("POST", "/sss-copilot"),
        ("DELETE", "/sss-copilot/" + "a" * 64),
    ],
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_library_authentication_precedes_all_work(
    client, monkeypatch, method, path, token
):
    calls = []
    for name in ("get_path", "list_scripts", "store_script", "script_path"):
        monkeypatch.setattr(library, name, lambda *a, **kw: calls.append((a, kw)))
    response = client.open(
        path, method=method, headers={} if token is None else {"token": token}
    )
    assert response.status_code == 403
    assert calls == []


def test_authorized_library_upload_validation_selection_busy_and_deletion(
    client, monkeypatch, storage
):
    import server

    headers = {"token": "sss-test"}

    def post(data):
        return client.post(
            "/sss-copilot",
            headers=headers,
            data={"copilot": (io.BytesIO(json.dumps(data).encode()), "sss.json")},
        )

    assert post({"stage_name": "1-7", "actions": []}).status_code == 400
    response = post(SCRIPT)
    assert response.status_code == 200
    info = response.get_json()
    assert client.get("/sss-copilot", headers=headers).get_json() == {"scripts": [info]}
    path = "/sss-copilot/" + info["id"]
    server.config.conf = Conf(sss={"scripts": [{"id": info["id"]}]})
    assert client.delete(path, headers=headers).status_code == 409
    server.config.conf.sss.scripts = []
    monkeypatch.setattr(server, "_maa_busy_response", lambda: {"busy": True})
    assert client.delete(path, headers=headers).status_code == 409
    monkeypatch.setattr(server, "_maa_busy_response", lambda: None)
    assert client.delete(path, headers=headers).get_json() == {"ok": True}
    assert library.list_scripts(sss=True) == []


@pytest.fixture
def scheduler(monkeypatch, storage):
    first = upload()
    second = upload({**SCRIPT, "stage_name": "保全关卡二"})
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            maa_rg_enable=1,
            maa_long_task_type="sss",
            sss={
                "scripts": [
                    {"id": first["id"], "times": 2},
                    {"id": second["id"], "type": 2, "ec": 3, "times": 1},
                ]
            },
        ),
    )
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = MagicMock()
    solver.MAA.append_task.side_effect = range(1, 100)
    solver.MAA.running.return_value = False
    solver.maa_callback = None
    solver.recog = MagicMock()
    solver.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=2))]
    solver.last_execution = {"maa": None}
    for method in (
        "back_to_index",
        "initialize_maa",
        "release_maa",
        "restore_maa_theme",
        "rest_until_next_task",
        "maa_stop",
        "_idle_sleep",
        "to_sss",
    ):
        monkeypatch.setattr(solver, method, MagicMock(return_value=None))
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    return solver


def emit(solver, msg, taskid, **kwargs):
    solver.on_maa_callback(
        msg,
        json.dumps({"taskchain": "SSSCopilot", "taskid": taskid, **kwargs}).encode(),
        None,
    )


def complete(solver):
    taskid = solver.MAA.append_task.call_count
    emit(solver, 20003, taskid, what="SSSGamePass")
    emit(solver, 10002, taskid)
    return False


def test_queue_repeats_each_item_then_waits_for_manual_restart(scheduler):
    original = scheduler.tasks[0]
    scheduler.MAA.running.side_effect = lambda: complete(scheduler)
    scheduler.maa_plan_solver([])
    calls = scheduler.MAA.append_task.call_args_list
    assert len(calls) == 3
    assert [call.args[0] for call in calls] == ["SSSCopilot"] * 3
    assert [call.args[1]["loop_times"] for call in calls] == [1, 1, 1]
    assert calls[0].args[1] == calls[1].args[1]
    assert calls[2].args[1] != calls[1].args[1]
    assert [call.args for call in scheduler.to_sss.call_args_list] == [
        (1, 1),
        (1, 1),
        (2, 3),
    ]
    for _ in range(3):
        scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 3
    assert scheduler.tasks == [original]
    assert scheduler.rest_until_next_task.call_count == 4
    base_schedule.config.conf.sss.run_id = "manual-restart"
    scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 6


def test_interrupt_retains_completed_rounds_across_cleared_memory(scheduler):
    def run():
        if scheduler.MAA.append_task.call_count == 1:
            return complete(scheduler)
        emit(scheduler, 10004, 2)
        return False

    scheduler.MAA.running.side_effect = run
    scheduler.maa_plan_solver([])
    assert record.load_maa_sss_progress()["completed"] == 1
    assert record.load_maa_sss_progress()["next"] == 0
    del scheduler.maa_sss_progress
    scheduler.MAA.running.side_effect = lambda: complete(scheduler)
    scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 4
    assert record.load_maa_sss_progress()["next"] == 2
    del scheduler.maa_sss_progress
    scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 4


@pytest.mark.parametrize("outcome", ["settlement", "missing_pass", "error"])
def test_unsuccessful_round_keeps_count_and_releases_other_work(scheduler, outcome):
    def run():
        taskid = scheduler.MAA.append_task.call_count
        if outcome == "settlement":
            emit(scheduler, 20003, taskid, what="SSSSettlement")
        emit(scheduler, 10000 if outcome == "error" else 10002, taskid)
        return False

    scheduler.MAA.running.side_effect = run
    for _ in range(3):
        scheduler.maa_plan_solver([])
    progress = record.load_maa_sss_progress()
    assert progress["completed"] == 0 and progress["next"] == 0 and progress["failed"]
    assert scheduler.MAA.append_task.call_count == 1
    assert scheduler.rest_until_next_task.call_count == 3
    base_schedule.config.conf.sss.scripts[0].times = 3
    scheduler.MAA.running.side_effect = lambda: complete(scheduler)
    scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 5


@pytest.mark.parametrize("taskid", [None, True, [], 999])
def test_unmatched_or_load_callbacks_cannot_count_round(scheduler, taskid):
    scheduler.maa_plan_solver([])
    emit(scheduler, 20003, taskid, what="SSSGamePass")
    emit(scheduler, 10002, taskid)
    assert record.load_maa_sss_progress()["completed"] == 0
    assert scheduler.maa_sss_progress["next"] == 0


def test_stop_immediately_releases_maa_and_closes_game_without_losing_rounds(
    scheduler, monkeypatch
):
    scheduler.device = MagicMock()
    scheduler.MAA.running.side_effect = lambda: True
    monkeypatch.setattr(
        base_schedule, "csleep", lambda _: base_schedule.config.stop_mower.set()
    )
    with pytest.raises(base_schedule.MowerExit):
        scheduler.maa_plan_solver([])
    scheduler.maa_stop.assert_called_once()
    scheduler.device.exit_after_task_stop.assert_called_once()
    assert record.load_maa_sss_progress()["completed"] == 0


@pytest.mark.parametrize(
    "stage_type,ec,stage_position,ec_position",
    [
        (1, 1, (384, 324), (576, 540)),
        (2, 2, (768, 648), (960, 540)),
        (2, 3, (768, 648), (1860, 540)),
    ],
)
def test_real_navigation_uses_queue_choices_without_mutating_global_config(
    scheduler, stage_type, ec, stage_position, ec_position
):
    from arknights_mower.utils.solver import BaseSolver, Scene

    scheduler.sss_scene = MagicMock(
        side_effect=[Scene.SSS_MAIN, Scene.SSS_EC, Scene.SSS_DEPLOY]
    )
    scheduler.tap = MagicMock()
    scheduler.tap_element = MagicMock()
    assert BaseSolver.to_sss(scheduler, stage_type, ec) is None
    assert [call.args[0] for call in scheduler.tap.call_args_list] == [
        stage_position,
        ec_position,
    ]
    assert base_schedule.config.conf.sss.type == 1
    assert base_schedule.config.conf.sss.ec == 1


def test_success_callback_duplicates_and_late_callbacks_cannot_count_twice(scheduler):
    scheduler.maa_plan_solver([])
    complete(scheduler)
    complete(scheduler)
    assert record.load_maa_sss_progress()["completed"] == 1
    emit(scheduler, 20003, 1, what="SSSGamePass")
    emit(scheduler, 10002, 1)
    assert record.load_maa_sss_progress()["completed"] == 1
