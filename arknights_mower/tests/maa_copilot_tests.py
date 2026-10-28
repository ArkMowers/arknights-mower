import io
import json
import logging
import sys
import threading
from datetime import date, datetime, timedelta
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


def test_import_deduplicates_and_queue_preserves_order_raid_and_navigation(files):
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
    params = library.build_copilot_params(conf)
    assert params == {
        "formation": False,
        "use_sanity_potion": False,
        "copilot_list": [
            {
                "filename": str(files / (other["id"] + ".json")),
                "is_raid": True,
                "nav_name_override": "CE-6",
            },
            {"filename": str(files / (info["id"] + ".json")), "is_raid": False},
        ],
    }
    restored = Conf(
        **Conf(copilot=conf, maa_rg_enable=1, maa_long_task_type="copilot").model_dump()
    )
    assert restored.COPILOT and restored.has_maa_tasks
    assert restored.copilot == conf


def test_formation_parameters_only_forward_when_enabled(files):
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
    params = library.build_copilot_params(conf)
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
    assert set(library.build_copilot_params(conf)) == {
        "copilot_list",
        "formation",
        "use_sanity_potion",
    }
    conf.formation = True
    conf.support_unit_usage = 1
    assert "support_unit_name" not in library.build_copilot_params(conf)


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
    monkeypatch.setattr(library, "MAX_SCRIPTS", 1)
    with pytest.raises(ValueError):
        upload({**SCRIPT, "stage_name": "CE-6"})
    assert path.read_bytes() == before
    assert upload()["id"] == info["id"]


def test_missing_or_changed_script_fails_before_params_are_returned(files):
    info = upload()
    conf = CopilotConf(scripts=[{"id": info["id"]}])
    library.script_path(info["id"]).write_text("{}")
    with pytest.raises(ValueError):
        library.build_copilot_params(conf)
    library.script_path(info["id"]).unlink()
    with pytest.raises(OSError):
        library.build_copilot_params(conf)
    with pytest.raises(ValueError):
        library.build_copilot_params(CopilotConf())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"formation_index": 5},
        {"support_unit_usage": 4},
        {"scripts": [{"id": "a" * 64}] * 33},
        {"user_additional": [{"name": "棘刺", "skill": 4}]},
    ],
)
def test_invalid_task_options_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        CopilotConf(**kwargs)


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
        ("POST", "/maa-copilot"),
        ("DELETE", "/maa-copilot/" + "a" * 64),
    ],
)
@pytest.mark.parametrize("token", [None, "invalid"])
def test_every_library_method_rejects_unauthenticated_work(
    client, monkeypatch, method, path, token
):
    calls = []
    for name in ("get_path", "list_scripts", "store_script", "script_path"):
        monkeypatch.setattr(library, name, lambda *a: calls.append(a))
    response = client.open(
        path, method=method, headers={} if token is None else {"token": token}
    )
    assert response.status_code == 403
    assert calls == []


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
    solver.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=2))]
    solver.last_execution = {"maa": None}
    solver.emergency_state = None
    for method in (
        "back_to_index",
        "initialize_maa",
        "release_maa",
        "restore_maa_theme",
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
    assert scheduler.maa_copilot_progress["next"] == 1

    def finish_remaining():
        emit(scheduler, 10002, scheduler.MAA.append_task.call_count)
        return False

    scheduler.MAA.running.side_effect = finish_remaining
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_count == 3
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
        "save_maa_copilot_progress",
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
        "save_maa_copilot_progress",
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
    scheduler.restore_maa_theme.assert_not_called()


def test_scheduled_preemption_stops_and_restores_without_losing_task(
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
    scheduler.restore_maa_theme.assert_called_once_with()
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
    scheduler.restore_maa_theme.assert_not_called()
    scheduler.rest_until_next_task.assert_not_called()
    scheduler.sleep.assert_not_called()
