"""恢复重试保留首次故障，最新失败另行报告。"""

from unittest.mock import Mock

import pytest

from arknights_mower.tests import instance_supervisor_tests as processes
from arknights_mower.tests import process_crash_recovery_tests as recovery
from arknights_mower.utils import crash_recovery, instance_supervisor, update_runtime

isolated_runtime = processes.isolated_runtime
offline = recovery.offline
notice = recovery.notice


def test_worker_retry_preserves_first_trigger_after_progress_and_finally(
    offline, notice, monkeypatch
):
    update_runtime.write_json(
        notice,
        {
            "active": True,
            "reason": "process_exit",
            "exit_code": 23,
            "occurred_at": "2026-10-20T12:00:00+00:00",
            "trigger_message": "首次进程故障",
        },
    )
    first = crash_recovery.status()
    crash_recovery.begin()
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("训练室读取失败"))
    )

    offline.server._run_mower_worker({"_process_crash_recovery": True})

    current = crash_recovery.status()
    assert current["occurred_at"] == first["occurred_at"]
    assert current["trigger_message"] == "首次进程故障"
    assert current["reason"] == "process_exit" and current["exit_code"] == 23
    assert current["automatic"]
    assert "训练室读取失败" in current["last_failure_message"]
    assert current["last_failure_reason"] == "worker_recovery"
    assert current["phase"] == "waiting"
    offline.io.assert_not_called()


def test_supervisor_repeated_exit_preserves_first_event_and_reports_last_exit(
    isolated_runtime,
):
    directory = isolated_runtime
    command = processes.child_script(
        directory,
        "if len(events) == 1: os._exit(23)\n"
        "if len(events) == 2:\n"
        " runtime.write_json(trace.parent/'first.json',runtime.read_json(trace.parent/'recovery.json'))\n"
        " os._exit(24)\n"
        "child_exit('window')\n",
    )

    assert (
        instance_supervisor.supervise(
            command, directory, delays=(0,), cooldowns=(0,), poll_interval=0.01
        )
        == 0
    )

    first = update_runtime.read_json(directory / "first.json")
    current = update_runtime.read_json(directory / "recovery.json")
    assert current["occurred_at"] == first["occurred_at"]
    assert current["reason"] == first["reason"] == "process_exit"
    assert current["exit_code"] == 23
    assert current["last_exit_code"] == 24
    assert current["attempt"] == 2


def test_worker_failure_keeps_native_trigger_and_cannot_open_another_episode(
    offline,
    notice,
):
    update_runtime.write_json(
        notice,
        {
            "active": True,
            "reason": "http_unresponsive",
            "occurred_at": "2026-10-20T12:00:00+00:00",
            "exit_code": 23,
            "message": "服务持续无响应",
        },
    )

    crash_recovery.activate("后续观察失败")
    current = crash_recovery.status()
    assert current["reason"] == "http_unresponsive"
    assert current["occurred_at"] == "2026-10-20T12:00:00+00:00"
    assert current["exit_code"] == 23
    assert current["last_failure_reason"] == "worker_exception"
    assert current["last_failure_message"] == "后续观察失败"

    crash_recovery.complete()
    completed = notice.read_bytes()
    crash_recovery.activate("新的独立故障")
    current = crash_recovery.status()
    assert not current["active"] and not current["automatic"]
    assert notice.read_bytes() == completed


def test_failed_explicit_start_within_native_episode_preserves_original_fault(
    offline, notice
):
    update_runtime.write_json(
        notice,
        {
            "active": True,
            "startup": True,
            "occurred_at": "2026-10-20T12:00:00+00:00",
            "reason": "process_exit",
            "trigger_message": "上一次启动前的故障",
            "exit_code": 23,
        },
    )

    crash_recovery.activate("本次启动期间发生异常")

    current = crash_recovery.status()
    assert current["occurred_at"] == "2026-10-20T12:00:00+00:00"
    assert current["trigger_message"] == "上一次启动前的故障"
    assert current["reason"] == "process_exit" and current["exit_code"] == 23
    assert current["last_failure_message"] == "本次启动期间发生异常"
    assert current["automatic"]


def test_reasonless_legacy_process_failure_keeps_retry_permission(offline, notice):
    original = update_runtime.read_json(notice)

    crash_recovery.activate("后续观察失败")

    current = crash_recovery.status()
    assert current["automatic"] and current["active"]
    assert current.get("reason") is None
    assert current["exit_code"] == original["exit_code"]
    assert current["occurred_at"] == original["occurred_at"]
    assert current["last_failure_reason"] == "worker_exception"


@pytest.mark.parametrize(
    "reason",
    ["process_exit", "process_creation", "startup_timeout", "http_unresponsive"],
)
def test_supervisor_fault_replaces_only_legacy_worker_origin(reason):
    original = {
        "active": True,
        "reason": "worker_exception",
        "occurred_at": "2026-10-20T12:00:00+00:00",
        "trigger_message": "旧工作线程异常",
    }

    current = update_runtime.recovery_failure_details(
        original, reason=reason, message="新的进程故障", exit_code=23
    )

    assert current["reason"] == reason
    assert current["occurred_at"] != original["occurred_at"]
    assert current["trigger_message"] == "新的进程故障"
    assert current["exit_code"] == 23


def test_supervisor_native_exit_after_legacy_worker_failure_starts_fresh_episode(
    isolated_runtime,
):
    directory = isolated_runtime
    update_runtime.write_json(
        directory / "recovery.json",
        {
            "active": True,
            "reason": "worker_exception",
            "occurred_at": "2026-10-20T12:00:00+00:00",
            "trigger_message": "旧工作线程异常",
        },
    )
    command = processes.child_script(
        directory, "if len(events) == 1: os._exit(23)\nchild_exit('window')\n"
    )

    assert (
        instance_supervisor.supervise(
            command, directory, delays=(0,), cooldowns=(0,), poll_interval=0.01
        )
        == 0
    )

    current = update_runtime.read_json(directory / "recovery.json")
    assert current["active"] and current["reason"] == "process_exit"
    assert current["occurred_at"] != "2026-10-20T12:00:00+00:00"
    assert current["exit_code"] == 23


@pytest.mark.parametrize("progress", ["正在重新观察设备和驻员", "设备观察尚未完成"])
def test_old_progress_is_not_reconstructed_as_the_first_fault(
    offline, notice, progress
):
    update_runtime.write_json(
        notice,
        {
            "active": True,
            "reason": "process_exit",
            "occurred_at": "2026-10-20T12:00:00+00:00",
            "exit_code": 23,
            "message": progress,
        },
    )

    crash_recovery.activate("后续房间读取失败")

    current = crash_recovery.status()
    assert current["reason"] == "process_exit" and current["exit_code"] == 23
    assert current["occurred_at"] == "2026-10-20T12:00:00+00:00"
    assert current.get("trigger_message") is None
    assert current["last_failure_message"] == "后续房间读取失败"
