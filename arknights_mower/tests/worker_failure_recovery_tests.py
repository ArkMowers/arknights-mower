"""工作线程故障先恢复，重复同一故障时保留任务并停止重试。"""

from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from arknights_mower.utils import config, crash_recovery
from arknights_mower.utils import update_runtime as runtime


@pytest.fixture
def worker_notice(monkeypatch, tmp_path):
    monkeypatch.setenv("MOWER_SUPERVISOR_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("MOWER_RECOVERY_RUN", "1")
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    monkeypatch.setattr(config, "stop_mower", Event())
    path = tmp_path / "recovery.json"
    runtime.write_json(path, {"active": False, "phase": "resolved"})
    return path


def raised_error(message="读取失败"):
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


def test_ordinary_failure_reuses_saved_tasks_and_requests_game_restart(worker_notice):
    task = object()
    saved = {"tasks": [task], "operators": {"夕": object()}}

    assert crash_recovery.worker_failed(raised_error()) == "restart_game"

    current = crash_recovery.status()
    assert current["automatic"] and current["reason"] == "worker_recovery"
    assert current["phase"] == "waiting" and current["resume_requested"]
    prepared = crash_recovery.prepare_resume(saved)
    assert prepared["_restart_game"] and prepared["_process_crash_recovery"]
    assert prepared["tasks"][0] is task
    assert prepared["operators"] is saved["operators"]


def test_memory_failure_restarts_process_without_game_restart(worker_notice):
    assert (
        crash_recovery.worker_failed(MemoryError("无法分配数组")) == "restart_process"
    )
    assert crash_recovery.status()["automatic"]
    assert not crash_recovery.prepare_resume({})["_restart_game"]


def test_new_worker_failure_does_not_inherit_resolved_process_exit_code(worker_notice):
    runtime.write_json(
        worker_notice,
        {
            "active": False,
            "phase": "resolved",
            "reason": "process_exit",
            "exit_code": 23,
            "trigger_message": "已经恢复的旧进程故障",
        },
    )
    assert crash_recovery.worker_failed(raised_error()) == "restart_game"
    current = crash_recovery.status()
    assert current["reason"] == "worker_recovery"
    assert "exit_code" not in current
    assert current["trigger_message"] == "工作线程发生异常：读取失败"


def test_memory_failure_is_detected_in_cause_and_context_chains():
    cause = RuntimeError("截图后端包装异常")
    cause.__cause__ = MemoryError("数组内存不足")
    context = RuntimeError("截图后端包装异常")
    context.__context__ = cause
    assert crash_recovery.is_memory_error(context)
    cause.__context__ = context
    assert crash_recovery.is_memory_error(cause)
    assert not crash_recovery.is_memory_error(RuntimeError("普通识别失败"))


def test_opencv_allocation_failure_needs_no_cv2_import():
    allocation_error = type("error", (Exception,), {"__module__": "cv2", "code": -4})
    assert crash_recovery.is_memory_error(allocation_error("Insufficient memory"))
    assert not crash_recovery.is_memory_error(
        type("OtherError", (Exception,), {"code": -4})()
    )


def test_worker_failure_preserves_native_first_fault(worker_notice):
    first = {
        "active": True,
        "startup": True,
        "reason": "process_exit",
        "occurred_at": "2026-10-30T00:00:00+00:00",
        "trigger_message": "首次原生崩溃",
        "exit_code": 23,
    }
    runtime.write_json(worker_notice, first)

    assert crash_recovery.worker_failed(raised_error()) == "restart_game"

    current = crash_recovery.status()
    for key in ("reason", "occurred_at", "trigger_message", "exit_code"):
        assert current[key] == first[key]
    assert current["last_failure_reason"] == "worker_recovery"
    assert "读取失败" in current["last_failure_message"]


def test_legacy_native_recovery_does_not_invent_missing_first_reason(worker_notice):
    runtime.write_json(
        worker_notice,
        {"active": True, "occurred_at": "2026-10-30T00:00:00+00:00"},
    )
    assert crash_recovery.worker_failed(raised_error()) == "restart_game"
    current = crash_recovery.status()
    assert current.get("reason") is None
    assert current["last_failure_reason"] == "worker_recovery"
    assert current["automatic"]


@pytest.mark.parametrize("mode", ["1", "2", "3"])
def test_pending_start_mode_survives_worker_failure(worker_notice, mode):
    runtime.write_json(
        worker_notice,
        {
            "active": False,
            "phase": "resolved",
            "pending_start_type": mode,
            "reset_observation_pending": mode == "2",
        },
    )

    assert crash_recovery.worker_failed(raised_error()) == "restart_game"
    current = crash_recovery.status()
    assert current["start_type"] == mode
    assert current["pending_start_type"] == mode
    assert current["reset_observation_pending"] == (mode == "2")


def test_same_failure_stops_after_three_recoveries_even_after_completion(worker_notice):
    for index in range(3):
        assert (
            crash_recovery.worker_failed(raised_error(f"动态内容 {index}"))
            == "restart_game"
        )
        crash_recovery.complete()

    assert crash_recovery.worker_failed(raised_error("动态内容 4")) == "stop"
    current = crash_recovery.status()
    assert current["active"] and current["phase"] == "failed"
    assert not current["automatic"] and not current["resume_requested"]
    crash_recovery.failed()
    assert crash_recovery.status()["phase"] == "failed"


def test_changed_failure_source_starts_new_recovery_budget(worker_notice):
    for _ in range(3):
        assert crash_recovery.worker_failed(raised_error()) == "restart_game"
    try:
        raise RuntimeError("另一个来源")
    except RuntimeError as exc:
        assert crash_recovery.worker_failed(exc) == "restart_game"


def test_old_same_failure_starts_new_recovery_budget(worker_notice):
    for _ in range(3):
        crash_recovery.worker_failed(raised_error())
    raw = runtime.read_json(worker_notice)
    raw["worker_failure_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=16)
    ).isoformat()
    runtime.write_json(worker_notice, raw)

    assert crash_recovery.worker_failed(raised_error()) == "restart_game"


def test_explicit_start_resets_repeated_failure_budget(worker_notice):
    for _ in range(4):
        crash_recovery.worker_failed(raised_error())
    crash_recovery.request_resume()

    assert crash_recovery.worker_failed(raised_error()) == "restart_game"


def test_process_restart_keeps_exhausted_recovery_paused(worker_notice):
    for _ in range(4):
        crash_recovery.worker_failed(raised_error())
    raw = runtime.read_json(worker_notice)
    raw.update(reason="process_exit", phase="waiting", resume_requested=True)
    runtime.write_json(worker_notice, raw)

    assert crash_recovery.initialize_intent(True)
    current = crash_recovery.status()
    assert current["phase"] == "failed" and not current["automatic"]
    assert not current["resume_requested"]
    crash_recovery.request_resume()
    assert crash_recovery.status()["automatic"]


def test_stop_keeps_exhaustion_diagnostic(worker_notice):
    for _ in range(4):
        crash_recovery.worker_failed(raised_error())
    message = crash_recovery.status()["message"]
    crash_recovery.cancel()
    assert crash_recovery.status()["phase"] == "failed"
    assert crash_recovery.status()["message"] == message


def test_stop_prevents_worker_failure_recovery(worker_notice):
    crash_recovery.cancel()
    original = worker_notice.read_bytes()
    assert crash_recovery.worker_failed(raised_error()) is None
    assert worker_notice.read_bytes() == original


def test_stop_event_prevents_worker_failure_recovery(worker_notice):
    config.stop_mower.set()
    original = worker_notice.read_bytes()
    assert crash_recovery.worker_failed(raised_error()) is None
    assert worker_notice.read_bytes() == original


def test_no_supervision_does_not_create_a_recovery(worker_notice, monkeypatch):
    monkeypatch.delenv("MOWER_SUPERVISOR_DIRECTORY")
    assert crash_recovery.worker_failed(raised_error()) is None


def test_first_worker_failure_creates_supervised_recovery(worker_notice):
    worker_notice.unlink()
    assert crash_recovery.worker_failed(raised_error()) == "restart_game"
    assert crash_recovery.status()["automatic"]


def test_corrupt_recovery_record_is_preserved(worker_notice):
    worker_notice.write_text("{broken", encoding="utf-8")
    original = worker_notice.read_bytes()
    assert crash_recovery.worker_failed(raised_error()) is None
    assert worker_notice.read_bytes() == original


def test_legacy_worker_notice_remains_retired_until_new_failure(worker_notice):
    runtime.write_json(
        worker_notice,
        {"active": True, "phase": "waiting", "reason": "worker_exception"},
    )
    assert not crash_recovery.status()["automatic"]

    assert crash_recovery.worker_failed(raised_error()) == "restart_game"
    assert crash_recovery.status()["reason"] == "worker_recovery"
