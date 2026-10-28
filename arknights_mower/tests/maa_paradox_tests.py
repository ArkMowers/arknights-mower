import io
import json
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, record
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils import maa_copilot as library
from arknights_mower.utils.config.conf import Conf

files = helpers.files
scheduler = helpers.scheduler

SCRIPT = {"stage_name": "mem_test_1", "actions": [], "doc": {"title": "悖论作业"}}


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
