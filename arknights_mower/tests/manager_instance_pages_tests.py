import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from arknights_mower.utils import manager_common as common
from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import update_runtime as runtime
from manager import Api


@pytest.fixture
def pages(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    api = Api(tmp_path / "instances.json")
    for name in ("one", "two", "three"):
        api.add(name, str(tmp_path / name))
    records = [
        dict(
            id=str(idx),
            pid=12345,
            kind="instance",
            space=row["path"],
            managed=True,
            ready=True,
        )
        for idx, row in enumerate(api.instances)
    ]
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: copy.deepcopy(records))
    return api, records


def commands():
    return sorted(
        (file.parent.name, json.loads(file.read_text())["action"])
        for file in (runtime.state_dir() / "commands").glob("*/*.json")
    )


@pytest.mark.parametrize("bulk", [False, True])
def test_first_page_open_requires_a_choice_without_side_effects(pages, bulk):
    api, records = pages
    result = (
        api.open_instance_pages(api.instances.copy())
        if bulk
        else api.open_instance_page(0, api.instances[0].copy())
    )
    assert result["needs_mode"] and not result["ok"]
    assert not api._common_path.exists()
    assert commands() == []


@pytest.mark.parametrize("version", [0, 1])
@pytest.mark.parametrize("mode,action", [("browser", "browser"), ("webview", "show")])
def test_page_choice_preserves_other_common_values_and_is_reused(
    pages, version, mode, action
):
    api, records = pages
    original = {"account": "sender", "startup_mode": "background"}
    if version:
        original = dict(
            version=1,
            values={**api.get_common_settings()["values"], **original},
            independent_instances={common.policy_key(api.instances[1]["path"]): True},
        )
    runtime.write_json(api._common_path, original)
    assert api.open_instance_page(0, api.instances[0].copy(), mode, True) == {
        "ok": True
    }
    expected = copy.deepcopy(original)
    (expected["values"] if version else expected)["instance_page_mode"] = mode
    assert json.loads(api._common_path.read_text()) == expected
    reopened = Api(api._storage_path)
    assert reopened.open_instance_page(1, reopened.instances[1].copy()) == {"ok": True}
    assert commands() == [("0", action), ("1", action)]
    assert all(not Path(row["path"]).exists() for row in api.instances)


@pytest.mark.parametrize("mode", ["invalid", "", True, 1, [], {}])
@pytest.mark.parametrize("bulk", [False, True])
def test_invalid_page_choice_never_saves_or_dispatches(pages, mode, bulk):
    api, records = pages
    result = (
        api.open_instance_pages(api.instances.copy(), mode)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), mode)
    )
    assert not result["ok"] and not result.get("needs_mode")
    assert not api._common_path.exists()
    assert commands() == []


@pytest.mark.parametrize("bulk", [False, True])
def test_changed_page_target_never_remembers_choice(pages, bulk):
    api, records = pages
    targets = copy.deepcopy(api.instances)
    runtime.write_json(
        api._storage_path, [{**row, "name": "changed"} for row in api.instances]
    )
    result = (
        api.open_instance_pages(targets, "webview", True)
        if bulk
        else api.open_instance_page(0, targets[0], "webview", True)
    )
    assert not result["ok"]
    assert not api._common_path.exists()
    assert commands() == []


def test_bulk_page_open_skips_unavailable_targets_and_saves_once(pages, monkeypatch):
    api, records = pages
    records[1]["ready"] = False
    records[2]["managed"] = False
    write = Mock(wraps=runtime.write_json)
    monkeypatch.setattr(runtime, "write_json", write)
    result = api.open_instance_pages(api.instances.copy(), "webview", True)
    assert result["ok"]
    assert [row["status"] for row in result["results"]] == [
        "opened",
        "skipped",
        "skipped",
    ]
    assert commands() == [("0", "show")]
    assert sum(call.args[0] == api._common_path for call in write.call_args_list) == 1


@pytest.mark.parametrize("mode", [None, "browser"])
def test_bulk_without_ready_instances_never_asks_or_remembers(pages, mode):
    api, records = pages
    for row in records:
        row["ready"] = False
    result = api.open_instance_pages(
        api.instances.copy(), mode, remember=mode is not None
    )
    assert result["ok"] and not result.get("needs_mode")
    assert [row["status"] for row in result["results"]] == ["skipped"] * 3
    assert not api._common_path.exists()
    assert commands() == []


def test_bulk_uses_the_saved_choice_without_requesting_another_choice(pages):
    api, records = pages
    runtime.write_json(api._common_path, {"instance_page_mode": "webview"})
    result = api.open_instance_pages(api.instances.copy())
    assert result["ok"]
    assert [row["status"] for row in result["results"]] == ["opened"] * 3
    assert commands() == [(str(idx), "show") for idx in range(3)]


@pytest.mark.parametrize("bulk", [False, True])
def test_unready_targets_do_not_remember_an_explicit_choice(pages, monkeypatch, bulk):
    api, records = pages
    unready = [{**row, "ready": False} for row in records]
    monkeypatch.setattr(
        runtime,
        "instances",
        Mock(side_effect=[records, unready, unready, unready])
        if bulk
        else lambda **kwargs: unready,
    )
    result = (
        api.open_instance_pages(api.instances.copy(), "browser", True)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), "browser", True)
    )
    assert not result.get("needs_mode")
    assert not api._common_path.exists()
    assert commands() == []


@pytest.mark.parametrize("bulk", [False, True])
def test_failed_choice_save_preserves_existing_configuration_bytes(
    pages, monkeypatch, bulk
):
    api, records = pages
    runtime.write_json(api._common_path, {"account": "sender"})
    before = api._common_path.read_bytes()
    monkeypatch.setattr(
        runtime, "replace_with_retry", Mock(side_effect=OSError("locked"))
    )
    result = (
        api.open_instance_pages(api.instances.copy(), "webview", True)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), "webview", True)
    )
    assert not result["ok"]
    assert api._common_path.read_bytes() == before
    assert commands() == []


def test_bulk_requires_a_captured_list(pages):
    api, records = pages
    assert not api.open_instance_pages(None, "browser")["ok"]
    assert not api._common_path.exists()
    assert commands() == []


def test_bulk_initial_scan_failure_never_remembers_or_dispatches(pages, monkeypatch):
    api, records = pages
    scan = Mock(side_effect=runtime.InstanceScanError("unreadable"))
    monkeypatch.setattr(runtime, "instances", scan)
    assert not api.open_instance_pages(api.instances.copy(), "browser", True)["ok"]
    scan.assert_called_once()
    assert not api._common_path.exists()
    assert commands() == []


def test_bulk_expired_save_budget_does_not_dispatch_or_retry(pages, monkeypatch):
    api, records = pages
    now = [0]
    write = runtime.write_json

    def slow_save(*args, **kwargs):
        write(*args, **kwargs)
        now[0] = 11

    monkeypatch.setattr(controls, "monotonic", lambda: now[0])
    monkeypatch.setattr(runtime, "write_json", slow_save)
    result = api.open_instance_pages(api.instances.copy(), "browser", True)
    assert not result["ok"]
    assert [row["status"] for row in result["results"]] == ["failed"] * 3
    assert common.read_settings(api._common_path)["instance_page_mode"] == "browser"
    assert commands() == []


def test_bulk_rechecks_readiness_and_shutdown_before_each_dispatch(pages, monkeypatch):
    api, records = pages
    observations = []
    for idx in range(4):
        current = copy.deepcopy(records)
        if idx >= 2:
            current[1]["ready"] = False
        observations.append(current)
    runtime.send_instance_command(records[2], "exit")
    monkeypatch.setattr(runtime, "instances", Mock(side_effect=observations))
    result = api.open_instance_pages(api.instances.copy(), "browser")
    assert [row["status"] for row in result["results"]] == [
        "opened",
        "skipped",
        "skipped",
    ]
    assert commands() == [("0", "browser")]


def test_bulk_retains_partial_success_without_retrying_failed_dispatch(
    pages, monkeypatch
):
    api, records = pages
    send = Mock(side_effect=[None, OSError("locked"), None])
    monkeypatch.setattr(runtime, "send_instance_command", send)
    result = api.open_instance_pages(api.instances.copy(), "browser")
    assert not result["ok"]
    assert [row["status"] for row in result["results"]] == [
        "opened",
        "failed",
        "opened",
    ]
    assert send.call_count == 3


def test_bulk_scan_failure_stops_remaining_dispatch_without_retry(pages, monkeypatch):
    api, records = pages
    scan = Mock(
        side_effect=[
            copy.deepcopy(records),
            copy.deepcopy(records),
            runtime.InstanceScanError("unreadable"),
        ]
    )
    monkeypatch.setattr(runtime, "instances", scan)
    result = api.open_instance_pages(api.instances.copy(), "browser")
    assert not result["ok"]
    assert [row["status"] for row in result["results"]] == [
        "opened",
        "failed",
        "failed",
    ]
    assert scan.call_count == 3
    assert commands() == [("0", "browser")]


def test_bulk_preference_write_failure_never_dispatches_or_retries(pages, monkeypatch):
    api, records = pages
    write = Mock(side_effect=OSError("locked"))
    monkeypatch.setattr(runtime, "write_json", write)
    result = api.open_instance_pages(api.instances.copy(), "browser", True)
    assert not result["ok"]
    assert [row["status"] for row in result["results"]] == ["failed"] * 3
    write.assert_called_once()
    assert commands() == []


@pytest.mark.parametrize("expired_scan", [False, True])
def test_bulk_page_budget_prevents_remaining_dispatch(pages, monkeypatch, expired_scan):
    api, records = pages
    now = [0]
    scans = [0]

    def scan(**kwargs):
        scans[0] += 1
        if expired_scan and scans[0] == 2:
            now[0] = 11
        return copy.deepcopy(records)

    original = runtime.send_instance_command

    def send(record, action):
        original(record, action)
        now[0] = 11

    monkeypatch.setattr(controls, "monotonic", lambda: now[0])
    monkeypatch.setattr(runtime, "instances", scan)
    monkeypatch.setattr(runtime, "send_instance_command", send)
    result = api.open_instance_pages(api.instances.copy(), "browser", True)
    assert not result["ok"]
    assert [row["status"] for row in result["results"]] == (
        ["failed"] * 3 if expired_scan else ["opened", "failed", "failed"]
    )
    assert commands() == ([] if expired_scan else [("0", "browser")])
    if expired_scan:
        assert not api._common_path.exists()


@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("mode,action", [("browser", "browser"), ("webview", "show")])
def test_temporary_page_choice_dispatches_without_saving_and_asks_again(
    pages, bulk, mode, action
):
    api, records = pages
    result = (
        api.open_instance_pages(api.instances.copy(), mode)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), mode)
    )
    assert result["ok"]
    assert commands() == (
        [(str(idx), action) for idx in range(3)] if bulk else [("0", action)]
    )
    assert not api._common_path.exists()
    reopened = Api(api._storage_path)
    again = (
        reopened.open_instance_pages(reopened.instances.copy())
        if bulk
        else reopened.open_instance_page(0, reopened.instances[0].copy())
    )
    assert again["needs_mode"] and not again["ok"]
    assert not api._common_path.exists()


@pytest.mark.parametrize("bulk", [False, True])
def test_temporary_choice_preserves_an_existing_saved_preference(pages, bulk):
    api, records = pages
    runtime.write_json(
        api._common_path, {"instance_page_mode": "webview", "account": "sender"}
    )
    before = api._common_path.read_bytes()
    result = (
        api.open_instance_pages(api.instances.copy(), "browser", False)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), "browser", False)
    )
    assert result["ok"]
    assert api._common_path.read_bytes() == before
    assert api.open_instance_page(0, api.instances[0].copy())["ok"]
    assert ("0", "show") in commands()


@pytest.mark.parametrize("remember", [None, 0, 1, "true", "false", [], {}])
@pytest.mark.parametrize("bulk", [False, True])
def test_invalid_remember_choice_never_saves_or_dispatches(pages, remember, bulk):
    api, records = pages
    result = (
        api.open_instance_pages(api.instances.copy(), "browser", remember)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), "browser", remember)
    )
    assert not result["ok"] and not result.get("needs_mode")
    assert not api._common_path.exists()
    assert commands() == []


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("bulk", [False, True])
def test_remember_requires_an_explicit_mode_even_with_a_saved_preference(
    pages, saved, bulk
):
    api, records = pages
    if saved:
        runtime.write_json(api._common_path, {"instance_page_mode": "webview"})
    before = api._common_path.read_bytes() if saved else None
    result = (
        api.open_instance_pages(api.instances.copy(), None, True)
        if bulk
        else api.open_instance_page(0, api.instances[0].copy(), None, True)
    )
    assert not result["ok"] and not result.get("needs_mode")
    assert (api._common_path.read_bytes() if saved else None) == before
    if not saved:
        assert not api._common_path.exists()
    assert commands() == []


def test_bulk_remembers_choice_once_for_multiple_ready_instances(pages, monkeypatch):
    api, records = pages
    write = Mock(wraps=runtime.write_json)
    monkeypatch.setattr(runtime, "write_json", write)
    result = api.open_instance_pages(api.instances.copy(), "browser", True)
    assert result["ok"]
    assert [row["status"] for row in result["results"]] == ["opened"] * 3
    assert sum(call.args[0] == api._common_path for call in write.call_args_list) == 1
    assert common.read_settings(api._common_path)["instance_page_mode"] == "browser"
