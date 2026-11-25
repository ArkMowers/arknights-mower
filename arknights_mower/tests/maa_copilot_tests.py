import hashlib
import io
import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import maa_copilot as library  # noqa: E402
from arknights_mower.utils.config.conf import Conf, CopilotConf  # noqa: E402
from arknights_mower.utils.maa_callback import MaaCallbackLog  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402

SCRIPT = {
    "stage_name": "1-7",
    "doc": {"title": "离线作业", "details": "使用前确认练度"},
    "opers": [{"name": "棘刺", "skill": 3}],
    "actions": [{"type": "Deploy", "name": "棘刺"}],
}


@pytest.fixture
def files(monkeypatch, tmp_path):
    monkeypatch.setattr(library, "get_path", lambda _: tmp_path / "copilots")
    return tmp_path / "copilots"


def upload(data=SCRIPT):
    return library.store_script(json.dumps(data).encode())


def test_import_deduplicates_and_queue_preserves_order_raid_and_navigation(
    files, tmp_path
):
    info = upload()
    assert upload()["id"] == info["id"]
    other = upload({**SCRIPT, "stage_name": "CE-6"})
    assert len(library.list_scripts()) == 2
    conf = CopilotConf(
        scripts=[
            {"id": other["id"], "is_raid": True, "nav_name_override": " CE-6 "},
            {"id": info["id"]},
        ]
    )
    params = library.build_copilot_params(conf, tmp_path)
    assert params == {
        "formation": False,
        "use_sanity_potion": False,
        "copilot_list": [
            {
                "filename": str(files / (other["id"] + ".json")),
                "is_raid": True,
                "nav_name_override": "CE-6",
            },
        ],
    }
    second = library.build_copilot_params(conf, tmp_path, index=1)
    assert second["copilot_list"] == [
        {"filename": str(files / (info["id"] + ".json")), "is_raid": False}
    ]
    restored = Conf(
        **Conf(copilot=conf, maa_rg_enable=1, maa_long_task_type="copilot").model_dump()
    )
    assert restored.COPILOT and restored.has_maa_tasks
    assert restored.copilot == conf


@pytest.mark.parametrize("difficulty", [0, 1, 2, 3])
def test_import_and_existing_library_report_declared_difficulty(files, difficulty):
    info = upload({**SCRIPT, "difficulty": difficulty})
    assert info["difficulty"] == difficulty
    assert library.list_scripts() == [info]


def test_existing_script_without_difficulty_defaults_to_unspecified(files):
    assert upload()["difficulty"] == 0
    assert library.list_scripts()[0]["difficulty"] == 0


def test_formation_parameters_only_forward_when_enabled(files, tmp_path):
    info = upload()
    conf = CopilotConf(
        scripts=[{"id": info["id"]}],
        formation=True,
        formation_index=4,
        use_sanity_potion=True,
        add_trust=True,
        ignore_requirements=True,
        support_unit_usage=2,
        support_unit_name=" 维什戴尔 ",
        user_additional=[{"name": "桃金娘", "skill": 1}, {"name": ""}],
    )
    params = library.build_copilot_params(conf, tmp_path)
    assert params["formation_index"] == 4
    assert (
        params["use_sanity_potion"]
        and params["add_trust"]
        and params["ignore_requirements"]
    )
    assert params["support_unit_usage"] == 2
    assert params["support_unit_name"] == "维什戴尔"
    assert params["user_additional"] == [{"name": "桃金娘", "skill": 1}]
    conf.formation = False
    assert set(library.build_copilot_params(conf, tmp_path)) == {
        "copilot_list",
        "formation",
        "use_sanity_potion",
    }
    conf.formation = True
    conf.support_unit_usage = 1
    assert "support_unit_name" not in library.build_copilot_params(conf, tmp_path)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {**SCRIPT, "type": "SSS"},
        {**SCRIPT, "stage_name": ""},
        {**SCRIPT, "actions": "bad"},
        {**SCRIPT, "actions": [3]},
        {**SCRIPT, "opers": [None]},
    ],
)
def test_invalid_import_never_writes(files, data):
    with pytest.raises(ValueError):
        upload(data)
    assert not files.exists()


@pytest.mark.parametrize(
    "script_id", ["../sss", "/tmp/other", "A" * 64, "a" * 63, None]
)
def test_ids_cannot_select_arbitrary_files(files, script_id):
    with pytest.raises(ValueError):
        library.script_path(script_id)
    assert not files.exists()


def test_oversized_and_exhausted_storage_preserve_existing_script(files, monkeypatch):
    info = upload()
    path = library.script_path(info["id"])
    before = path.read_bytes()
    with pytest.raises(ValueError):
        library.store_script(b" " * (library.MAX_SCRIPT_BYTES + 1))
    monkeypatch.setattr(library, "MAX_TOTAL_BYTES", len(before))
    with pytest.raises(ValueError):
        upload({**SCRIPT, "stage_name": "CE-6"})
    assert path.read_bytes() == before
    assert upload()["id"] == info["id"]


def test_missing_or_changed_script_fails_before_params_are_returned(files, tmp_path):
    info = upload()
    conf = CopilotConf(scripts=[{"id": info["id"]}])
    library.script_path(info["id"]).write_text("{}")
    with pytest.raises(ValueError):
        library.build_copilot_params(conf, tmp_path)
    library.script_path(info["id"]).unlink()
    with pytest.raises(OSError):
        library.build_copilot_params(conf, tmp_path)
    with pytest.raises(ValueError):
        library.build_copilot_params(CopilotConf(), tmp_path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"formation_index": 5},
        {"support_unit_usage": 4},
        {"user_additional": [{"name": "棘刺", "skill": 4}]},
    ],
)
def test_invalid_task_options_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        CopilotConf(**kwargs)


@pytest.mark.parametrize("kind", ["copilot", "sss", "paradox"])
def test_saved_config_round_trips_large_script_queues(kind):
    ids = [f"{i % 3:064x}" for i in range(100)]
    conf = Conf.model_validate({kind: {"scripts": [{"id": id_} for id_ in ids]}})
    restored = Conf.model_validate_json(conf.model_dump_json())
    assert [entry.id for entry in getattr(restored, kind).scripts] == ids


@pytest.fixture
def client(monkeypatch, files):
    import server

    monkeypatch.setattr(server.app, "token", "copilot-test-token", raising=False)
    monkeypatch.setattr(server.config, "conf", Conf())
    monkeypatch.setattr(server, "_maa_busy_response", lambda: None)
    return server.app.test_client()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/maa-copilot"),
        ("HEAD", "/maa-copilot"),
        ("POST", "/maa-copilot"),
        ("DELETE", "/maa-copilot/" + "a" * 64),
    ],
)
@pytest.mark.parametrize("token", [None, "invalid"])
def test_every_library_method_rejects_unauthenticated_work(
    client, monkeypatch, method, path, token
):
    from arknights_mower.utils import config_backup

    calls = []
    monkeypatch.setattr(
        config_backup, "backup_entry_warning", lambda: calls.append("backup")
    )
    for name in ("get_path", "list_scripts", "store_script", "script_path"):
        monkeypatch.setattr(library, name, lambda *a: calls.append(a))
    response = client.open(
        path, method=method, headers={} if token is None else {"token": token}
    )
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize(
    "endpoint,script",
    [
        ("/maa-copilot", SCRIPT),
        ("/maa-paradox", {"stage_name": "mem_test_1", "actions": []}),
        (
            "/sss-copilot",
            {
                "type": "SSS",
                "stage_name": "SSS",
                "tool_men": {},
                "stages": [
                    {
                        "stage_name": "SSS-1",
                        "draw_as_possible": True,
                        "strategies": [],
                        "actions": [],
                    }
                ],
            },
        ),
    ],
)
def test_library_imports_and_lists_more_than_64_distinct_files(
    client, monkeypatch, tmp_path, endpoint, script
):
    from arknights_mower.utils import config_backup

    def instance_path(name):
        return tmp_path / name.removeprefix("@app/")

    monkeypatch.setattr(library, "get_path", instance_path)
    monkeypatch.setattr(config_backup, "get_path", instance_path)
    monkeypatch.setattr(
        config_backup.config, "conf_path", instance_path("@app/config/conf.yml")
    )
    monkeypatch.setattr(config_backup, "MAX_ARCHIVE_ENTRIES", 70)
    warning = MagicMock(wraps=config_backup.backup_entry_warning)
    monkeypatch.setattr(config_backup, "backup_entry_warning", warning)
    headers = {"token": "copilot-test-token"}
    ids = set()
    for index in range(65):
        raw = json.dumps({**script, "doc": {"title": str(index)}}).encode()
        response = client.post(
            endpoint,
            headers=headers,
            data={"copilot": (io.BytesIO(raw), "script.json")},
        )
        assert response.status_code == 200
        ids.add(response.get_json()["id"])
    assert len(ids) == 65
    warning.assert_not_called()
    response = client.get(endpoint, headers=headers)
    assert response.status_code == 200
    assert "共需备份 65 个文件" in response.get_json()["backup_warning"]
    assert [entry["id"] for entry in response.get_json()["scripts"]] == sorted(ids)


def test_authorized_upload_list_and_delete_and_selected_guard(
    client, monkeypatch, files
):
    import server

    headers = {"token": "copilot-test-token"}
    response = client.post(
        "/maa-copilot",
        headers=headers,
        data={
            "copilot": (io.BytesIO(json.dumps(SCRIPT).encode()), "ignored-name.json")
        },
    )
    assert response.status_code == 200
    info = response.get_json()
    assert info["title"] == "离线作业"
    assert client.head("/maa-copilot", headers=headers).status_code == 200
    assert client.get("/maa-copilot", headers=headers).get_json()["scripts"] == [info]
    server.config.conf = Conf(copilot={"scripts": [{"id": info["id"]}]})
    path = "/maa-copilot/" + info["id"]
    assert client.delete(path, headers=headers).status_code == 409
    server.config.conf = Conf()
    monkeypatch.setattr(server, "_maa_busy_response", lambda: {"ok": False})
    assert client.delete(path, headers=headers).status_code == 409
    monkeypatch.setattr(server, "_maa_busy_response", lambda: None)
    assert client.delete(path, headers=headers).get_json() == {"ok": True}
    assert client.get("/maa-copilot", headers=headers).get_json() == {"scripts": []}


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("token", [None, "invalid"])
def test_queue_save_requires_token_before_reading_script_files(
    client, monkeypatch, method, token
):
    read = MagicMock()
    monkeypatch.setattr(library, "script_path", read)
    response = client.open(
        "/conf",
        method=method,
        headers={"token": token} if token else {},
        json={"copilot": {"scripts": [{"id": "a" * 64}]}},
    )
    assert response.status_code == 403
    read.assert_not_called()


@pytest.fixture
def queue_config_path(client, monkeypatch, tmp_path):
    import server
    from arknights_mower.utils import workshop_config
    from arknights_mower.utils.config import weekly_plan_loader

    def temp_path(name):
        return tmp_path / name.removeprefix("@app/")

    monkeypatch.setattr(library, "get_path", temp_path)
    monkeypatch.setattr(workshop_config, "get_path", temp_path)
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", MagicMock())
    conf_path = tmp_path / "conf.yaml"
    monkeypatch.setattr(server.config, "conf_path", conf_path)
    return conf_path


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_queue_save_and_cross_client_script_deletion(client, queue_config_path, method):
    import server

    legacy = "f" * 64
    server.config.conf = Conf(copilot={"scripts": [{"id": legacy}]})
    server.config.save_conf()
    original = queue_config_path.read_bytes()
    deleted = upload()["id"]
    kept = upload({**SCRIPT, "stage_name": "CE-6"})["id"]
    headers = {"token": "copilot-test-token"}
    other = server.app.test_client()
    assert other.delete("/maa-copilot/" + deleted, headers=headers).status_code == 200

    response = client.open(
        "/conf",
        method=method,
        headers=headers,
        json={
            "copilot": {
                "scripts": [{"id": id_} for id_ in [legacy, deleted, deleted, kept]]
            },
            "sss": {"scripts": [{"id": kept}]},
            "paradox": {"scripts": [{"id": deleted}]},
        },
    )
    assert response.status_code == 409
    assert response.json["code"] == "copilot_scripts_missing"
    assert response.json["missing_scripts"] == {
        "copilot": [deleted],
        "sss": [kept],
        "paradox": [deleted],
    }
    assert queue_config_path.read_bytes() == original
    assert [item.id for item in server.config.conf.copilot.scripts] == [legacy]

    scripts = [{"id": kept}, {"id": legacy, "is_raid": True}]
    response = client.open(
        "/conf", method=method, headers=headers, json={"copilot": {"scripts": scripts}}
    )
    assert response.status_code == 200
    assert [(item.id, item.is_raid) for item in server.config.conf.copilot.scripts] == [
        (kept, False),
        (legacy, True),
    ]
    assert other.delete("/maa-copilot/" + kept, headers=headers).status_code == 409
    response = client.open(
        "/conf", method=method, headers=headers, json={"copilot": {"scripts": []}}
    )
    assert response.status_code == 200
    assert other.delete("/maa-copilot/" + kept, headers=headers).status_code == 200


def test_delete_waits_for_inflight_queue_save(client, queue_config_path, monkeypatch):
    import yaml
    from flask import request
    from yamlcore import CoreLoader

    import server
    from arknights_mower.utils.config import weekly_plan_loader

    saving = threading.Event()
    resume = threading.Event()
    delete_blocked = threading.Event()

    def get_active_plan_key():
        saving.set()
        assert resume.wait(10)
        return ""

    manager = weekly_plan_loader.get_weekly_plan_manager()
    manager.get_active_plan_key.side_effect = get_active_plan_key
    lock = server.backup_lock

    def acquire():
        if lock.acquire(blocking=False):
            return True
        if request.method == "DELETE":
            delete_blocked.set()
        return lock.acquire()

    observed_lock = MagicMock(wraps=lock)
    observed_lock.acquire.side_effect = acquire
    observed_lock.__enter__.side_effect = lock.__enter__
    observed_lock.__exit__.side_effect = lock.__exit__
    monkeypatch.setattr(server, "backup_lock", observed_lock)
    other = server.app.test_client()
    script_id = upload()["id"]
    scripts = [{"id": script_id, "is_raid": True}]
    headers = {"token": "copilot-test-token"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        save = pool.submit(
            client.patch,
            "/conf",
            headers=headers,
            json={"copilot": {"scripts": scripts}},
        )
        try:
            assert saving.wait(5)
            delete = pool.submit(
                other.delete, "/maa-copilot/" + script_id, headers=headers
            )
            assert delete_blocked.wait(5)
            assert not delete.done()
        finally:
            resume.set()
        assert save.result(timeout=5).status_code == 200
        assert delete.result(timeout=5).status_code == 409

    persisted = yaml.load(queue_config_path.read_text("utf-8"), Loader=CoreLoader)
    assert persisted["copilot"]["scripts"] == scripts
    assert server.config.conf.copilot.scripts[0].id == script_id
    assert library.script_path(script_id).is_file()


@pytest.fixture
def scheduler(monkeypatch, files, tmp_path):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "get_path", lambda value: tmp_path / value[5:])
    monkeypatch.setattr(record, "_tables_created", False)
    info = upload()
    conf = Conf(
        maa_rg_enable=1,
        maa_long_task_type="copilot",
        stage_plan_enable=False,
        maa_credit_fight=False,
        maa_mall_enable=False,
        visit_friend_enable=False,
        copilot={"scripts": [{"id": info["id"]}]},
    )
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = MagicMock()
    solver.MAA.append_task.side_effect = range(1, 100)
    solver.MAA.running.return_value = False
    solver.maa_callback = None
    solver.recog = MagicMock()
    solver.device = MagicMock()
    solver.scene = MagicMock(
        side_effect=lambda: (
            base_schedule.Scene.OPERATOR_CHOOSE_LEVEL
            if base_schedule.config.conf.maa_long_task_type == "copilot"
            else base_schedule.Scene.TERMINAL_MAIN
        )
    )
    monkeypatch.setattr(base_schedule, "NavigationSolver", MagicMock())
    base_schedule.NavigationSolver.return_value.run.return_value = True
    solver.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=2))]
    solver.last_execution = {"maa": None}
    solver.emergency_state = None
    for method in (
        "back_to_index",
        "scene_graph_navigation",
        "initialize_maa",
        "release_maa",
        "append_maa_theme_task",
        "rest_until_next_task",
        "maa_stop",
        "_idle_sleep",
    ):
        monkeypatch.setattr(solver, method, MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(base_schedule, "save_current_state", MagicMock())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    return solver


@pytest.fixture
def roster_cache(scheduler, tmp_path, monkeypatch):
    from arknights_mower.utils import mastery_recommendation

    root = tmp_path / "当前实例" / "tmp"
    root.mkdir(parents=True)
    cache = root / "cultivate.json"
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: cache)
    original = library.get_path
    monkeypatch.setattr(
        library, "get_path", lambda key: root if key == "@app/tmp" else original(key)
    )
    installation = tmp_path / "maa"
    resource = installation / "resource"
    resource.mkdir(parents=True)
    (resource / "battle_data.json").write_text(
        json.dumps(
            {
                "chars": {
                    "char_2012_typhon": {
                        "name": "提丰",
                        "profession": "SNIPER",
                        "rarity": 6,
                    },
                    "char_293_thorns": {
                        "name": "棘刺",
                        "profession": "WARRIOR",
                        "rarity": 6,
                    },
                }
            }
        )
    )
    base_schedule.config.conf.maa_path = str(installation)
    settings = base_schedule.config.conf.copilot
    settings.formation = settings.operbox_assist = True
    scheduler.MAA.get_version.return_value = "v6.23.0"
    roster = {
        "id": "char_2012_typhon",
        "evolvePhase": 2,
        "level": 85,
        "potentialRank": 2,
        "mainSkillLevel": 7,
        "private": "secret",
        "skills": [{"level": 0}, {"level": 2}, {"level": 3}],
        "equips": [
            {"id": "uniequip_001_typhon", "level": 1},
            {"id": "uniequip_002_typhon", "level": 2},
            {"id": "uniequip_003_typhon", "level": 0},
        ],
    }
    cache.write_text(
        json.dumps(
            {
                "_mower_player": {"uid": "secret", "nickName": "secret"},
                "data": {"characters": [roster], "items": [{"id": "secret"}]},
            }
        )
    )
    return cache


@pytest.mark.parametrize("core_rejects", [True, False])
def test_worker_receives_private_instance_formation_data_during_append(
    scheduler, roster_cache, core_rejects
):
    received = []

    def append(task, params):
        assert task == "Copilot" and params["formation"]
        path = Path(params["operbox_data_path"])
        assert path.is_absolute() and path.parent.parent == roster_cache.parent
        received.append(json.loads(path.read_text("utf-8")))
        if core_rejects:
            raise ValueError("MAA 拒绝编队")
        return 1

    scheduler.MAA.append_task.side_effect = append
    scheduler.maa_plan_solver()
    assert received == [
        {
            "own_opers": [
                {
                    "id": "char_2012_typhon",
                    "name": "提丰",
                    "elite": 2,
                    "level": 85,
                    "potential": 3,
                    "mainSkillLevel": 7,
                    "rarity": 6,
                    "own": True,
                    "skills": [{"level": 0}, {"level": 2}, {"level": 3}],
                    "equips": [{"id": "uniequip_002_typhon", "type": "X", "level": 2}],
                }
            ]
        }
    ]
    assert list(roster_cache.parent.iterdir()) == [roster_cache]
    assert scheduler.MAA.start.called is not core_rejects


@pytest.mark.parametrize(
    "problem", ["inventory", "no_skills", "invalid", "duplicate", "old_core", "missing"]
)
def test_enabled_formation_assistance_requires_usable_roster_and_core(
    scheduler, roster_cache, problem
):
    payload = json.loads(roster_cache.read_text())
    if problem == "inventory":
        del payload["data"]["characters"]
    elif problem == "no_skills":
        payload["data"]["characters"][0]["skills"] = []
    elif problem == "invalid":
        payload["data"]["characters"][0]["skills"][0]["level"] = "2"
    elif problem == "duplicate":
        payload["data"]["characters"] *= 2
    elif problem == "old_core":
        scheduler.MAA.get_version.return_value = "v6.18.0"
    roster_cache.write_text(json.dumps(payload))
    if problem == "missing":
        roster_cache.unlink()
    scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_not_called()
    scheduler.MAA.start.assert_not_called()
    assert scheduler.maa_copilot_progress["failed"]
    assert scheduler.maa_copilot_progress["next"] == 0
    assert not list(roster_cache.parent.glob("copilot-*"))


def test_older_core_receives_only_owned_operators_in_its_battle_table(
    scheduler, roster_cache
):
    scheduler.MAA.get_version.return_value = "v6.19.0"
    data = json.loads(roster_cache.read_text())
    data["data"]["characters"].append(
        {
            **data["data"]["characters"][0],
            "id": "char_4244_tocka",
        }
    )
    roster_cache.write_text(json.dumps(data))

    def append(_, params):
        rows = json.loads(Path(params["operbox_data_path"]).read_bytes())["own_opers"]
        assert [op["id"] for op in rows] == ["char_2012_typhon"]
        return 1

    scheduler.MAA.append_task.side_effect = append
    scheduler.maa_plan_solver()
    scheduler.MAA.start.assert_called_once()


def test_roster_refresh_resumes_failed_item_without_replaying_completed_prefix(
    scheduler, roster_cache, monkeypatch
):
    from arknights_mower.solvers import record

    queue_pair()
    contents = roster_cache.read_bytes()

    def complete_first():
        emit(scheduler, 10002, 1)
        roster_cache.unlink()
        return False

    scheduler.MAA.running.side_effect = complete_first
    scheduler.maa_plan_solver()
    assert scheduler.MAA.start.call_count == 1
    assert scheduler.maa_copilot_progress["next"] == 1
    assert record.load_maa_copilot_progress()["waiting_for_roster"]
    assert scheduler.maa_copilot_progress["failed"]

    monkeypatch.delattr(scheduler, "_maa_copilot_progress_loaded")
    scheduler.maa_copilot_progress = {}
    scheduler.MAA.running.side_effect = None
    navigation = base_schedule.NavigationSolver.return_value.run
    navigation.reset_mock()
    for broken in (None, b"{}", b'{"data":{"characters":[]}}'):
        if broken:
            roster_cache.write_bytes(broken)
        scheduler.maa_plan_solver()
        navigation.assert_not_called()
        assert scheduler.MAA.start.call_count == 1
        assert scheduler.maa_copilot_progress["next"] == 1

    roster_cache.write_bytes(contents)
    scheduler.maa_plan_solver()
    navigation.assert_called_once_with("CE-6")
    params = scheduler.MAA.append_task.call_args.args[1]
    assert params["copilot_list"][0]["nav_name_override"] == "CE-6"
    assert scheduler.MAA.start.call_count == 2
    assert not scheduler.maa_copilot_progress["failed"]
    assert "waiting_for_roster" not in record.load_maa_copilot_progress()


def test_roster_refresh_does_not_retry_native_formation_failure(
    scheduler, roster_cache
):
    scheduler.MAA.append_task.side_effect = ValueError("核心拒绝作业")
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["failed"]
    assert "waiting_for_roster" not in scheduler.maa_copilot_progress
    payload = json.loads(roster_cache.read_bytes())
    payload["data"]["characters"][0]["level"] += 1
    roster_cache.write_text(json.dumps(payload))
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 1


def test_formation_deadline_still_checked_after_roster_preparation(
    scheduler, roster_cache, monkeypatch
):
    read_roster = library.copilot_operators

    def read_at_deadline():
        rows = read_roster()
        scheduler.tasks[0].time = datetime.now() + timedelta(seconds=10)
        return rows

    monkeypatch.setattr(library, "copilot_operators", read_at_deadline)
    scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_not_called()
    scheduler.MAA.start.assert_not_called()
    assert not scheduler.maa_copilot_progress["failed"]
    assert scheduler.maa_copilot_progress["next"] == 0
    assert list(roster_cache.parent.iterdir()) == [roster_cache]


def test_formation_disabled_ignores_saved_assistance_and_legacy_key_is_preserved(
    scheduler,
):
    conf = base_schedule.config.conf.copilot
    old = conf.model_dump(exclude={"operbox_assist"})
    old_key = hashlib.sha256(
        json.dumps(old, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert library.run_key(conf) == old_key
    conf.operbox_assist = True
    scheduler.maa_plan_solver()
    scheduler.MAA.get_version.assert_not_called()
    assert "operbox_data_path" not in scheduler.MAA.append_task.call_args.args[1]


@pytest.mark.parametrize("start_error", [False, True])
def test_legacy_execution_copy_lives_until_maa_finishes(scheduler, start_error):
    old = json.dumps(SCRIPT, ensure_ascii=False).encode()
    old_id = hashlib.sha256(old).hexdigest()
    path = library.script_path(old_id)
    path.write_bytes(old)
    conf = base_schedule.config.conf.copilot
    conf.scripts[0].id = old_id
    opened = []

    def start():
        entry = scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0]
        filename = Path(entry["filename"])
        opened.append((filename, json.loads(filename.read_bytes())))
        if start_error:
            raise RuntimeError("作业启动失败")

    scheduler.MAA.start.side_effect = start
    scheduler.maa_plan_solver()
    assert len(opened) == 1
    filename, script = opened[0]
    assert filename != path
    assert script["opers"][0]["requirements"] == {"elite": 2}
    assert not filename.parent.exists()
    assert path.read_bytes() == old
    assert conf.scripts[0].id == old_id


def emit(solver, event, taskid, **kwargs):
    solver.on_maa_callback(
        event,
        json.dumps({"taskchain": "Copilot", "taskid": taskid, **kwargs}).encode(),
        None,
    )


def queue_pair():
    info = upload({**SCRIPT, "stage_name": "CE-6"})
    base_schedule.config.conf.copilot.scripts.append(
        base_schedule.config.conf.copilot.scripts[0].model_copy(
            update={"id": info["id"]}
        )
    )


def test_resume_skips_completed_item_and_whole_run_waits_for_manual_restart(
    scheduler,
):
    queue_pair()
    original = scheduler.tasks[0]

    def finish_first_then_interrupt_second():
        taskid = scheduler.MAA.append_task.call_count
        emit(scheduler, 10002 if taskid == 1 else 10004, taskid)
        return False

    scheduler.MAA.running.side_effect = finish_first_then_interrupt_second
    scheduler.maa_plan_solver()
    calls = scheduler.MAA.append_task.call_args_list
    assert len(calls) == 2
    first = calls[0].args[1]["copilot_list"][0]["filename"]
    second = calls[1].args[1]["copilot_list"][0]["filename"]
    assert first != second
    assert [
        call.args[0]
        for call in base_schedule.NavigationSolver.return_value.run.call_args_list
    ] == ["1-7", "CE-6"]
    assert [call.args[1]["copilot_list"][0]["nav_name_override"] for call in calls] == [
        "1-7",
        "CE-6",
    ]
    assert scheduler.maa_copilot_progress["next"] == 1

    def finish_remaining():
        emit(scheduler, 10002, scheduler.MAA.append_task.call_count)
        return False

    scheduler.MAA.running.side_effect = finish_remaining
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 3
    base_schedule.NavigationSolver.return_value.run.assert_called_with("CE-6")
    assert (
        scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0]["filename"]
        == second
    )
    for _ in range(3):
        scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 3
    assert scheduler.tasks == [original]
    assert scheduler.rest_until_next_task.call_count == 5

    base_schedule.config.conf.copilot.run_id = "manual-new-round"
    scheduler.MAA.running.side_effect = None
    scheduler.MAA.running.return_value = False
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 4
    assert (
        scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0]["filename"]
        == first
    )


def test_failed_item_retains_progress_and_releases_dispatch_until_settings_change(
    scheduler,
):
    queue_pair()
    original = scheduler.tasks[0]

    def fail():
        emit(scheduler, 10000, 1)
        return False

    scheduler.MAA.running.side_effect = fail
    for _ in range(3):
        scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 1
    assert scheduler.maa_copilot_progress["next"] == 0
    assert scheduler.tasks == [original]
    assert scheduler.rest_until_next_task.call_count == 3
    base_schedule.config.conf.copilot.formation = True
    scheduler.MAA.running.side_effect = None
    scheduler.MAA.running.return_value = False
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 2


@pytest.mark.parametrize("taskid", [None, True, [], 999])
def test_loading_or_unmatched_callbacks_cannot_advance_queue(scheduler, taskid):
    scheduler.maa_plan_solver()
    emit(scheduler, 20003, 1, what="CopilotListLoadTaskFileSuccess")
    emit(scheduler, 10002, taskid)
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == 0
    assert scheduler.MAA.append_task.call_count == 2


@pytest.mark.parametrize("clear_cache", [False, True])
@pytest.mark.parametrize("complete_queue", [False, True])
def test_progress_survives_real_startup_with_or_without_runtime_cache(
    scheduler, monkeypatch, tmp_path, clear_cache, complete_queue
):
    from arknights_mower import __main__ as mower
    from arknights_mower.solvers import record

    queue_pair()
    scheduler.maa_plan_solver()
    monkeypatch.setattr(base_schedule, "save_current_state", record.save_current_state)
    scheduler.tasks = []
    scheduler.daily_visit_friend = date.min
    scheduler.daily_report = scheduler.daily_skland = scheduler.daily_mail = date.min
    scheduler.task_count = 0
    scheduler.op_data = SimpleNamespace(
        mood_calculation_enabled=False,
        backup_plans=[],
        all_dorms=lambda: [],
        operators={},
        party_time=None,
        validate_backup_plans=MagicMock(return_value={"success": True}),
        restore_group_shift_state=MagicMock(),
        restore_dorm_state=MagicMock(),
    )
    monkeypatch.setattr(mower, "base_scheduler", scheduler)
    monkeypatch.setattr(record, "get_path", lambda value: tmp_path / value[5:])
    monkeypatch.setattr(record, "_tables_created", False)
    emit(scheduler, 10002, 1)
    if complete_queue:
        scheduler.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=2))]
        scheduler.maa_plan_solver()
        emit(scheduler, 10002, 2)
        scheduler.tasks = []
    record.save_current_state()
    saved = record.load_state()
    scheduler.maa_copilot_progress = {}
    monkeypatch.delattr(scheduler, "_maa_copilot_progress_loaded", raising=False)
    scheduler.initialize_operators = MagicMock(return_value=None)
    scheduler.run = MagicMock(side_effect=base_schedule.MowerExit)
    scheduler._request_run_order_restoration_observations = MagicMock()
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: scheduler)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(mower.NewsChecker, "get_effective_maintenance", lambda: None)
    monkeypatch.setattr(mower.NewsChecker, "get_major_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", MagicMock())
    mower.simulate({} if clear_cache else saved)
    assert scheduler.run.called
    scheduler.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=2))]
    calls = scheduler.MAA.append_task.call_count
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == (2 if complete_queue else 1)
    assert scheduler.MAA.append_task.call_count == calls + (0 if complete_queue else 1)
    if not complete_queue:
        assert scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0][
            "filename"
        ].endswith(base_schedule.config.conf.copilot.scripts[1].id + ".json")


def test_cleared_runtime_and_execution_options_keep_completed_queue(
    scheduler, monkeypatch
):
    scheduler.maa_plan_solver()
    emit(scheduler, 10002, 1)
    scheduler.maa_copilot_progress = {}
    monkeypatch.delattr(scheduler, "_maa_copilot_progress_loaded", raising=False)
    conf = base_schedule.config.conf.copilot
    conf.formation = True
    conf.use_sanity_potion = True
    for _ in range(3):
        scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == 1
    assert scheduler.MAA.append_task.call_count == 1
    conf.run_id = "manual-new-round"
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 2


def test_fixing_failed_item_options_retries_it_without_replaying_completed_prefix(
    scheduler,
):
    queue_pair()

    def finish_then_fail():
        taskid = scheduler.MAA.append_task.call_count
        emit(scheduler, 10002 if taskid == 1 else 10000, taskid)
        return False

    scheduler.MAA.running.side_effect = finish_then_fail
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == 1
    base_schedule.config.conf.copilot.formation = True
    scheduler.MAA.running.side_effect = None
    scheduler.MAA.running.return_value = False
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 3
    assert scheduler.maa_copilot_progress["next"] == 1
    assert scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0][
        "filename"
    ].endswith(base_schedule.config.conf.copilot.scripts[1].id + ".json")


@pytest.mark.parametrize("edit", ["order", "navigation", "raid", "remove"])
def test_editing_execution_queue_starts_new_round(scheduler, edit):
    queue_pair()
    scheduler.maa_plan_solver()
    emit(scheduler, 10002, 1)
    scripts = base_schedule.config.conf.copilot.scripts
    if edit == "order":
        scripts.reverse()
    elif edit == "navigation":
        scripts[0].nav_name_override = "1-7"
    elif edit == "raid":
        scripts[0].is_raid = True
    else:
        scripts.pop()
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == 0
    assert scheduler.MAA.append_task.call_count == 2
    assert scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0][
        "filename"
    ].endswith(scripts[0].id + ".json")


def test_independent_progress_overrides_stale_snapshot_and_migrates_legacy(
    scheduler, monkeypatch
):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf.copilot
    scheduler.maa_copilot_progress = {
        "key": library.run_key(conf),
        "next": 1,
        "failed": False,
    }
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 0
    assert record.load_maa_copilot_progress()["next"] == 1
    scheduler.maa_copilot_progress = {
        "key": library.run_key(conf),
        "next": 0,
        "failed": False,
    }
    monkeypatch.delattr(scheduler, "_maa_copilot_progress_loaded")
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == 1
    assert scheduler.MAA.append_task.call_count == 0


def test_progress_write_failure_does_not_skip_maa_error_cleanup(scheduler, monkeypatch):
    scheduler._maa_copilot_run(base_schedule.config.conf.copilot)
    failure = RuntimeError("MAA submission failed")
    scheduler.MAA.append_task.side_effect = failure
    monkeypatch.setattr(
        base_schedule,
        "finish_copilot_item",
        MagicMock(side_effect=OSError("disk full")),
    )
    scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["failed"] is True
    scheduler.MAA.stop.assert_called_once()
    assert scheduler.release_maa.called
    base_schedule.save_exception.assert_called_once_with(failure)
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 1


def test_callback_progress_write_failure_is_logged_and_callback_remains_readable(
    scheduler, monkeypatch, caplog
):
    scheduler.maa_plan_solver()
    scheduler.maa_callback = MaaCallbackLog()
    monkeypatch.setattr(
        base_schedule,
        "finish_copilot_item",
        MagicMock(side_effect=OSError("disk full")),
    )
    emit(scheduler, 10002, 1)
    assert "保存 MAA 自动战斗作业进度失败" in caplog.text
    assert "完成任务" in caplog.text
    assert scheduler.maa_copilot_progress["next"] == 1


def test_large_task_real_dispatch_has_no_daily_or_repeat_parameters(scheduler):
    scheduler.maa_plan_solver()
    chain, params = scheduler.MAA.append_task.call_args.args
    assert chain == "Copilot"
    assert "loop_times" not in params
    assert "filename" not in params
    assert len(params["copilot_list"]) == 1
    assert scheduler.last_execution["maa"] is None
    scheduler.rest_until_next_task.assert_called_once()
    scheduler.append_maa_theme_task.assert_not_called()


def test_idle_copilot_reads_only_the_current_queue_entry(scheduler):
    queue_pair()
    conf = base_schedule.config.conf.copilot
    first, second = conf.scripts
    raid = first.model_copy(update={"is_raid": True})
    missing = second.model_copy(update={"id": "f" * 64})
    conf.scripts = [second] * 98 + [raid, missing]
    from arknights_mower.solvers import record

    record.save_maa_copilot_progress({**scheduler._maa_copilot_run(conf), "next": 98})
    scheduler.MAA.start.side_effect = lambda: emit(scheduler, 10002, 1)

    scheduler.maa_plan_solver([])

    scheduler.MAA.append_task.assert_called_once()
    _, params = scheduler.MAA.append_task.call_args.args
    assert params["copilot_list"] == [
        {
            "filename": str(library.script_path(raid.id)),
            "is_raid": True,
            "nav_name_override": "1-7",
        }
    ]
    assert scheduler.maa_copilot_progress["next"] == 99
    assert scheduler.maa_copilot_progress["failed"] is True


def test_scheduled_preemption_stops_without_theme_restoration_or_lost_task(
    scheduler, monkeypatch
):
    original = scheduler.tasks[0]
    scheduler.MAA.running.return_value = True
    monkeypatch.setattr(
        base_schedule,
        "csleep",
        lambda _: setattr(original, "time", datetime.now() + timedelta(seconds=25)),
    )
    scheduler.maa_plan_solver()
    scheduler.maa_stop.assert_called_once_with()
    scheduler.append_maa_theme_task.assert_not_called()
    assert scheduler.tasks[0] is original


def test_outside_time_window_does_not_submit(scheduler):
    conf = base_schedule.config.conf
    conf.maa_rg_sleep_max = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
    conf.maa_rg_sleep_min = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
    scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_not_called()


@pytest.mark.parametrize(
    "what,inner,text",
    [
        (
            "CopilotAction",
            {"action": "SetUnitLocation", "target": "装置", "elapsed_time": 123},
            "设置单位坐标 装置（已用时 123 毫秒）",
        ),
        (
            "BattleFormationSelected",
            {"selected": "棘刺", "group_name": "近卫"},
            "近卫 → 棘刺",
        ),
        ("CopilotListLoadTaskFileSuccess", {"stage_name": "1-7"}, "1-7"),
        (
            "BattleFormationOperbox1Unmatched",
            {"group_name": "狙击", "may_borrow_oper": "维什戴尔"},
            "维什戴尔",
        ),
    ],
)
def test_current_copilot_callbacks_have_readable_progress(what, inner, text):
    line = MaaCallbackLog().describe(20003, {"what": what, "details": inner})
    assert text in line.text


def test_copilot_specific_errors_preserve_the_failed_stage_and_missing_group():
    log = MaaCallbackLog()
    line = log.describe(
        20000,
        {
            "subtask": "CopilotTask",
            "what": "CopilotStageNotSupported",
            "details": {"stage_name": "测试关卡"},
        },
    )
    assert line.level == logging.ERROR
    assert "测试关卡" in line.text
    line = log.describe(
        20000,
        {
            "subtask": "BattleFormationTask",
            "why": "OperatorMissing",
            "details": {"opers": {"近卫组": []}},
        },
    )
    assert "缺少干员：近卫组" in line.text


def test_partial_config_save_preserves_independent_formation_choices():
    original = Conf(copilot={"formation_index": 4, "add_trust": True})
    updated = original.updated(
        {"copilot": {"scripts": [{"id": "a" * 64}], "formation": True}}
    )
    assert updated.copilot.formation_index == 4
    assert updated.copilot.add_trust is True
    assert updated.copilot.formation is True
    assert len(updated.copilot.scripts) == 1


def test_mower_stop_closes_game_and_keeps_completed_queue_items(scheduler, monkeypatch):
    queue_pair()
    scheduler.device = MagicMock()
    scheduler.sleep = MagicMock()
    scheduler.MAA.running.side_effect = [False, True]
    scheduler.MAA.start.side_effect = lambda: emit(scheduler, 10002, 1)

    def stop(_):
        base_schedule.config.stop_mower.set()
        raise base_schedule.MowerExit

    monkeypatch.setattr(base_schedule, "csleep", stop)
    with pytest.raises(base_schedule.MowerExit):
        scheduler.maa_plan_solver()
    assert scheduler.maa_copilot_progress["next"] == 1
    scheduler.device.exit_after_task_stop.assert_called_once_with()
    scheduler.maa_stop.assert_called_once_with()
    scheduler.append_maa_theme_task.assert_not_called()
    scheduler.rest_until_next_task.assert_not_called()
    scheduler.sleep.assert_not_called()


@pytest.mark.parametrize(
    "stage,override,expected",
    [
        ("1-7", "", "1-7"),
        ("main_01-07", "", "1-7"),
        ("internal_stage", "TL-10", "TL-10"),
        ("tl-ex-8", "", "TL-EX-8"),
    ],
)
def test_navigation_target_uses_explicit_stage_and_supported_identifiers(
    files, stage, override, expected
):
    info = upload({**SCRIPT, "stage_name": stage})
    item = CopilotConf(
        scripts=[{"id": info["id"], "nav_name_override": override}]
    ).scripts[0]
    assert library.copilot_navigation_target(item) == expected


@pytest.mark.parametrize("incremental", [False, True])
def test_copilot_dispatch_uses_map_code_for_internal_stage_id(
    scheduler, tmp_path, monkeypatch, incremental
):
    conf = base_schedule.config.conf
    installation = tmp_path / "maa"
    conf.maa_path = str(installation)
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(library, "storage_root", lambda _: tmp_path / "runtime")
    root = tmp_path / "runtime/cache" if incremental else installation
    maps = root / "resource/Arknights-Tile-Pos"
    maps.mkdir(parents=True)
    (maps / "overview.json").write_text(
        json.dumps({"map": {"stageId": "act46side_ex08", "code": "OS-EX-8"}})
    )
    info = upload({**SCRIPT, "stage_name": "act46side_ex08"})
    item = conf.copilot.scripts[0]
    item.id = info["id"]
    item.is_raid = True
    scheduler.MAA.start.side_effect = lambda: emit(scheduler, 10002, 1)

    scheduler.maa_plan_solver([])
    base_schedule.NavigationSolver.return_value.run.assert_called_once()
    assert (
        base_schedule.NavigationSolver.return_value.run.call_args.args[0] == "OS-EX-8"
    )
    entry = scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0]
    assert (entry["nav_name_override"], entry["is_raid"]) == ("OS-EX-8", True)
    item.nav_name_override = "1-7"
    assert library.copilot_navigation_target(item) == "1-7"


@pytest.mark.parametrize(
    "stage,other,expected",
    [("高空坠物", "RI-1", "2-5"), ("蔓延", "FC-TR-2", "1-2"), ("突围", "9-16", "0-11")],
)
def test_copilot_navigation_keeps_known_stage_with_duplicate_map_name(
    files, tmp_path, monkeypatch, stage, other, expected
):
    monkeypatch.setattr(base_schedule.config.conf, "maa_path", str(tmp_path))
    maps = tmp_path / "resource/Arknights-Tile-Pos"
    maps.mkdir(parents=True)
    (maps / "overview.json").write_text(
        json.dumps({"map": {"name": stage, "code": other}})
    )
    info = upload({**SCRIPT, "stage_name": stage})
    item = CopilotConf(scripts=[{"id": info["id"]}]).scripts[0]
    assert library.copilot_navigation_target(item) == expected


def test_unknown_internal_navigation_target_requires_stage_override(files):
    info = upload({**SCRIPT, "stage_name": "unmapped_internal_stage"})
    item = CopilotConf(scripts=[{"id": info["id"]}]).scripts[0]
    with pytest.raises(ValueError, match="导航关卡名"):
        library.copilot_navigation_target(item)


@pytest.mark.parametrize("failure", ["route", "missing_detail"])
def test_copilot_does_not_start_without_confirmed_stage_detail(scheduler, failure):
    navigator = base_schedule.NavigationSolver.return_value
    if failure == "route":
        navigator.run.return_value = False
    else:
        navigator.confirm_selected_stage.return_value = False
    scheduler.maa_plan_solver([])
    navigator.back.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
    scheduler.MAA.start.assert_not_called()
    assert scheduler.maa_copilot_progress["failed"] is True


@pytest.mark.parametrize("paradox", [False, True])
def test_queue_dispatch_preserves_other_row_edits_during_execution(
    scheduler, monkeypatch, paradox
):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    if paradox:
        conf.maa_long_task_type = "paradox"
        info = library.store_script(
            b'{"stage_name":"mem_test_1","actions":[]}', paradox=True
        )
        settings = Conf(paradox={"scripts": [{"id": info["id"]}] * 3}).paradox
        conf.paradox = settings
        monkeypatch.setattr(scheduler, "to_operator_list", MagicMock(return_value=True))
    else:
        settings = conf.copilot
        first = settings.scripts[0]
        settings.scripts = [first, first.model_copy(update={"is_raid": True}), first]

    key = library.queue_key(settings)
    load = (
        record.load_maa_paradox_progress
        if paradox
        else record.load_maa_copilot_progress
    )

    def change(index, expected, completed):
        return record.set_copilot_item_completion(
            settings, key, index, expected, completed, paradox=paradox
        )

    assert change(1, "pending", True)
    indexes = []

    def finish():
        statuses = record.copilot_item_statuses(settings, load(), paradox=paradox)
        index = statuses.index("running")
        indexes.append(index)
        assert not change(index, "pending", True)
        if index == 2:
            assert change(0, "completed", False)
        if paradox:
            assert scheduler.MAA.append_task.call_args.args[1]["list"][0]["id"] == index
        else:
            assert not scheduler.MAA.append_task.call_args.args[1]["copilot_list"][0][
                "is_raid"
            ]
        scheduler.on_maa_callback(
            10002,
            json.dumps(
                {
                    "taskchain": "ParadoxCopilot" if paradox else "Copilot",
                    "taskid": len(indexes),
                }
            ).encode(),
            None,
        )
        return False

    scheduler.MAA.running.side_effect = finish
    scheduler.maa_plan_solver()
    assert indexes == [0, 2, 0]
    assert (
        record.copilot_item_statuses(settings, load(), paradox=paradox)
        == ["completed"] * 3
    )
    scheduler.maa_plan_solver()
    assert scheduler.MAA.start.call_count == 3


def _hold_copilot_claim(connection, tmp_path, settings):
    from arknights_mower.solvers import record

    record.get_path = lambda value: tmp_path / value[5:]
    connection.send(
        bool(
            record.claim_copilot_item(
                settings, library.queue_key(settings), "child-process"
            )
        )
    )
    connection.recv()


def test_process_exit_releases_only_the_running_row(scheduler, tmp_path):
    import multiprocessing

    from arknights_mower.solvers import record

    queue_pair()
    settings = base_schedule.config.conf.copilot
    key = library.queue_key(settings)
    scheduler._maa_copilot_run(settings)
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe()
    worker = ctx.Process(target=_hold_copilot_claim, args=(child, tmp_path, settings))
    worker.start()
    child.close()
    try:
        assert parent.poll(15) and parent.recv()
        assert not record.set_copilot_item_completion(settings, key, 0, "pending", True)
        assert record.set_copilot_item_completion(settings, key, 1, "pending", True)
        assert record.claim_copilot_item(settings, key, "duplicate") is None
    finally:
        worker.terminate()
        worker.join(5)
        parent.close()
    assert not worker.is_alive()
    assert record.copilot_item_statuses(
        settings, record.load_maa_copilot_progress()
    ) == ["pending", "completed"]
    scheduler.MAA.start.side_effect = lambda: emit(scheduler, 10002, 1)
    scheduler.maa_plan_solver()
    assert scheduler.MAA.start.call_count == 1
    assert record.load_maa_copilot_progress()["next"] == 2


def test_restoring_running_progress_does_not_restore_its_owner(scheduler):
    from arknights_mower.solvers import record

    settings = base_schedule.config.conf.copilot
    key = scheduler._maa_copilot_run(settings)["key"]
    backup = record.claim_copilot_item(settings, key, "original")
    record.finish_copilot_item(key, "original", "stopped")
    record.save_maa_copilot_progress(backup)
    assert record.copilot_item_statuses(settings, backup) == ["pending"]
    assert record.set_copilot_item_completion(settings, key, 0, "pending", True)
    record.finish_copilot_item(key, "original", "failed")
    assert record.copilot_item_statuses(
        settings, record.load_maa_copilot_progress()
    ) == ["completed"]


def test_next_claim_uses_saved_copilot_options_and_keeps_its_failure(
    client, queue_config_path, scheduler
):
    queue_pair()
    base_schedule.config.conf.copilot.use_sanity_potion = True

    def finish():
        task_id = scheduler.MAA.append_task.call_count
        if task_id == 1:
            changed = client.patch(
                "/conf",
                headers={"token": "copilot-test-token"},
                json={"copilot": {"use_sanity_potion": False, "formation": True}},
            )
            assert changed.status_code == 200
        emit(scheduler, 10002 if task_id == 1 else 10000, task_id)
        return False

    scheduler.MAA.running.side_effect = finish
    scheduler.maa_plan_solver()
    scheduler.maa_plan_solver()
    assert [
        (call.args[1]["use_sanity_potion"], call.args[1]["formation"])
        for call in scheduler.MAA.append_task.call_args_list
    ] == [(True, False), (False, True)]


@pytest.mark.parametrize("paradox", [False, True])
def test_removing_next_item_during_execution_ends_old_queue(
    client, queue_config_path, scheduler, monkeypatch, paradox
):
    config = base_schedule.config.conf
    kind = "paradox" if paradox else "copilot"
    if paradox:
        config.maa_long_task_type = kind
        items = [
            library.store_script(
                json.dumps({"stage_name": stage, "actions": []}).encode(), paradox=True
            )
            for stage in ("mem_test_1", "mem_other_2")
        ]
        config.paradox = Conf(
            paradox={"scripts": [{"id": item["id"]} for item in items]}
        ).paradox
        monkeypatch.setattr(scheduler, "to_operator_list", MagicMock(return_value=True))
    else:
        queue_pair()
    first = getattr(config, kind).scripts[0]

    def finish():
        task_id = scheduler.MAA.append_task.call_count
        if task_id == 1:
            changed = client.patch(
                "/conf",
                headers={"token": "copilot-test-token"},
                json={kind: {"scripts": [first.model_dump()]}},
            )
            assert changed.status_code == 200
        scheduler.on_maa_callback(
            10002,
            json.dumps(
                {
                    "taskchain": "ParadoxCopilot" if paradox else "Copilot",
                    "taskid": task_id,
                }
            ).encode(),
            None,
        )
        return False

    scheduler.MAA.running.side_effect = finish
    scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_called_once()
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 2
    params = scheduler.MAA.append_task.call_args.args[1]
    row = params["list" if paradox else "copilot_list"][0]
    assert Path(row["filename"]).stem == first.id


def test_disabling_scheduled_large_tasks_prevents_the_next_claim(
    client, queue_config_path, scheduler
):
    queue_pair()

    def finish_first():
        changed = client.patch(
            "/conf",
            headers={"token": "copilot-test-token"},
            json={"maa_rg_enable": 0},
        )
        assert changed.status_code == 200
        emit(scheduler, 10002, 1)
        return False

    scheduler.MAA.running.side_effect = finish_first
    scheduler.maa_plan_solver()
    scheduler.MAA.append_task.assert_called_once()
    assert scheduler.maa_copilot_progress["next"] == 1
