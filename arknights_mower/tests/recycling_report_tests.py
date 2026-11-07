"""Offline history backfill, persistent progress and recycling HTTP requests."""

import json
import sys
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from arknights_mower import __version__
from arknights_mower.solvers import record
from arknights_mower.utils import recycling_report as report


@pytest.fixture
def transport(tmp_path, monkeypatch, income_db):
    monkeypatch.setattr(report, "_running", False)
    monkeypatch.setattr(report, "_dirty", False)
    worker = Mock()
    monkeypatch.setattr(report, "Thread", worker)
    directory = tmp_path / "instance-a"
    monkeypatch.setattr(report, "get_path", lambda _: directory)
    calls, statuses = [], []

    class Response:
        def __init__(self):
            value = statuses.pop(0) if statuses else (200, b"")
            if isinstance(value, BaseException):
                raise value
            self.status_code, body = value
            self.raw = BytesIO(body)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Session:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            assert not self.trust_env
            calls.append((url, deepcopy(kwargs)))
            return Response()

    monkeypatch.setattr(report.requests, "Session", Session)
    return SimpleNamespace(
        calls=calls, statuses=statuses, worker=worker, directory=directory
    )


def save(event_id="event", at=1759400000, materials=None, names=None):
    record.save_recycling_collection(event_id, at, names, materials or {"装置": 1})
    assert report.report_recycling_collection(event_id)


def old(event_id="old", at=1759400000, materials=None, names=None):
    with record._conn() as connection:
        connection.execute(
            "INSERT INTO recycling_collection VALUES (?, ?, ?, ?)",
            (event_id, at, json.dumps(names), json.dumps(materials or {})),
        )
        connection.commit()


def progress(event_id):
    with record._conn() as connection:
        return connection.execute(
            "SELECT status, next_unit, base_ms FROM recycling_report_progress WHERE event_id = ?",
            (event_id,),
        ).fetchone()


def resume(transport):
    assert report.start_recycling_reports()
    report._drain(transport.directory)


def test_report_uses_observed_items_current_version_and_actual_operator_ids(transport):
    names = ["旅骨", "阿米娅"]
    materials = {"装置": 2, "固源岩": 1}
    save(materials=materials, names=names)
    names.clear()
    materials.clear()
    assert not transport.calls
    transport.worker.assert_called_once()
    report._drain(transport.directory)
    url, request = transport.calls[0]
    assert url == "https://backend.yituliu.cn/report/recycleDrop"
    assert request["json"] == {
        "server": "CN",
        "source": "mower",
        "version": __version__,
        "drops": [
            {
                "itemId": "30062",
                "dropTime": 1759400000000,
                "operators": ["char_4232_hbound", "char_002_amiya"],
            },
            {
                "itemId": "30062",
                "dropTime": 1759400000001,
                "operators": ["char_4232_hbound", "char_002_amiya"],
            },
            {
                "itemId": "30012",
                "dropTime": 1759400000002,
                "operators": ["char_4232_hbound", "char_002_amiya"],
            },
        ],
    }
    assert request["timeout"] == (3, 15)
    assert request["allow_redirects"] is False
    assert request["stream"] is True
    assert progress("event")[:2] == ("submitted", 3)


@pytest.mark.parametrize("names", [None, [], ["未确认干员"], ["旅骨", "未确认干员"]])
def test_missing_or_uncertain_staff_does_not_suppress_drops(transport, names):
    save(names=names)
    report._drain(transport.directory)
    assert transport.calls[0][1]["json"]["drops"] == [
        {"itemId": "30062", "dropTime": 1759400000000}
    ]


def test_unavailable_operator_catalog_only_omits_operators(transport, monkeypatch):
    monkeypatch.setattr(report, "get_skill_data", Mock(side_effect=OSError))
    save(names=["旅骨"])
    report._drain(transport.directory)
    assert "operators" not in transport.calls[0][1]["json"]["drops"][0]


def test_all_old_records_that_fit_share_one_request_and_preserve_dates(transport):
    for index in range(100):
        old(
            str(index),
            at=1759400000 + index,
            materials={"装置": 1},
            names=["旅骨"] if index == 0 else None,
        )
    assert report.start_recycling_reports()
    resume(transport)
    assert len(transport.calls) == 1
    drops = transport.calls[0][1]["json"]["drops"]
    assert len(drops) == 100
    assert drops[0]["dropTime"] == 1759400000000
    assert drops[-1]["dropTime"] == 1759400099000
    assert drops[0]["operators"] == ["char_4232_hbound"]
    assert "operators" not in drops[-1]
    assert report.start_recycling_reports()
    resume(transport)
    assert len(transport.calls) == 1


def test_batches_combine_old_and_new_records_without_success_delays(transport):
    old(materials={"装置": 101})
    save(at=1759400100, materials={"固源岩": 100})
    report._drain(transport.directory)
    assert [len(call[1]["json"]["drops"]) for call in transport.calls] == [100, 100, 1]
    drops = [drop for call in transport.calls for drop in call[1]["json"]["drops"]]
    assert len({(drop["itemId"], drop["dropTime"]) for drop in drops}) == 201
    assert drops[100]["dropTime"] == 1759400000100
    assert drops[101]["dropTime"] == 1759400100000


def test_completion_log_requires_persisted_progress(transport, monkeypatch):
    for index in range(11):
        old(str(index), at=1759400000 + index, materials={"装置": 1})
    messages = []

    def info(message, *args):
        assert all(progress(str(index))[:2] == ("submitted", 1) for index in range(11))
        messages.append(message % args)

    monkeypatch.setattr(report.logger, "info", info)
    resume(transport)
    resume(transport)
    assert len(transport.calls) == 1
    assert len(transport.calls[0][1]["json"]["drops"]) == 11
    assert messages == ["回收站材料上报完成：11 份材料，11 条收取记录"]


@pytest.mark.parametrize("ignored", [True, False], ids=["ignored", "reverted"])
def test_unpersisted_progress_cannot_repeat_the_request(
    transport, monkeypatch, ignored
):
    old(materials={"装置": 1})
    with record._conn() as connection:
        if ignored:
            connection.execute(
                "CREATE TRIGGER ignore_report_progress BEFORE UPDATE "
                "ON recycling_report_progress WHEN NEW.status = 'submitted' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
        else:
            connection.execute(
                "CREATE TRIGGER revert_report_progress AFTER UPDATE "
                "ON recycling_report_progress WHEN NEW.status = 'submitted' "
                "BEGIN UPDATE recycling_report_progress "
                "SET next_unit = OLD.next_unit, status = OLD.status "
                "WHERE event_id = OLD.event_id; END"
            )
        connection.commit()
    info = Mock()
    exception = Mock()
    monkeypatch.setattr(report.logger, "info", info)
    monkeypatch.setattr(report.logger, "exception", exception)
    submit = report._submit

    def submit_while_woken(*args):
        submit(*args)
        report._dirty = True

    monkeypatch.setattr(report, "_submit", submit_while_woken)
    # Bound the broken implementation without making a second real HTTP request.
    transport.statuses[:] = [(200, b""), SystemExit("repeated submission")]
    resume(transport)
    assert len(transport.calls) == 1
    assert progress("old")[:2] == ("failed", 0)
    info.assert_not_called()
    exception.assert_called_once()
    transport.worker.assert_called_once()
    assert not report._running
    assert not report._dirty
    resume(transport)
    assert len(transport.calls) == 1
    assert progress("old")[:2] == ("failed", 0)


def test_backfill_does_not_move_old_dates_past_previously_submitted_new_records(
    transport,
):
    save(at=1759500000)
    report._drain(transport.directory)
    old(at=1759400000, materials={"装置": 1})
    resume(transport)
    assert transport.calls[1][1]["json"]["drops"][0]["dropTime"] == 1759400000000


@pytest.mark.parametrize("ignored", [True, False], ids=["ignored", "reverted"])
def test_unpersisted_failure_state_stops_without_repeating_http(
    transport, monkeypatch, ignored
):
    old(materials={"装置": 1})
    with record._conn() as connection:
        if ignored:
            connection.execute(
                "CREATE TRIGGER ignore_report_failure BEFORE UPDATE "
                "ON recycling_report_progress WHEN NEW.status = 'failed' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
        else:
            connection.execute(
                "CREATE TRIGGER revert_report_failure AFTER UPDATE "
                "ON recycling_report_progress WHEN NEW.status = 'failed' "
                "BEGIN UPDATE recycling_report_progress SET status = OLD.status "
                "WHERE event_id = OLD.event_id; END"
            )
        connection.commit()
    submit = report._submit

    def submit_while_woken(*args):
        try:
            submit(*args)
        finally:
            report._dirty = True

    monkeypatch.setattr(report, "_submit", submit_while_woken)
    exception = Mock()
    monkeypatch.setattr(report.logger, "exception", exception)
    transport.statuses[:] = [requests.Timeout(), SystemExit("repeated submission")]
    resume(transport)
    assert len(transport.calls) == 1
    assert progress("old")[:2] == ("pending", 0)
    exception.assert_called_once_with(
        "回收站上报处理失败，已保存的记录和发送进度保持不变"
    )
    transport.worker.assert_called_once()
    assert not report._running
    assert not report._dirty


def test_overlapping_collection_timestamps_are_allocated_once(transport):
    old("a", materials={"装置": 2})
    old("b", materials={"装置": 1})
    resume(transport)
    drops = transport.calls[0][1]["json"]["drops"]
    assert [drop["dropTime"] for drop in drops] == [
        1759400000000,
        1759400000001,
        1759400000002,
    ]
    assert progress("a")[2] == 1759400000000
    assert progress("b")[2] == 1759400000002


def test_progress_survives_interruption_between_batches(transport):
    old(materials={"装置": 201})
    transport.statuses[:] = [(200, b""), SystemExit()]
    with pytest.raises(SystemExit):
        resume(transport)
    assert progress("old")[:2] == ("pending", 100)
    resume(transport)
    assert [len(call[1]["json"]["drops"]) for call in transport.calls] == [
        100,
        100,
        100,
        1,
    ]
    assert transport.calls[1][1]["json"] == transport.calls[2][1]["json"]
    assert progress("old")[:2] == ("submitted", 201)


@pytest.mark.parametrize(
    "failure", [requests.ConnectionError(), requests.Timeout(), (503, b"")]
)
def test_failed_requests_only_retry_after_user_action(transport, failure):
    old(materials={"装置": 1})
    transport.statuses[:] = [failure]
    resume(transport)
    assert len(transport.calls) == 1
    assert progress("old")[:2] == ("failed", 0)
    save("new", at=1759400010)
    report._drain(transport.directory)
    resume(transport)
    assert len(transport.calls) == 2
    assert progress("old")[:2] == ("failed", 0)
    assert progress("new")[:2] == ("submitted", 1)
    assert report.retry_recycling_report("old")
    report._drain(transport.directory)
    assert len(transport.calls) == 3
    assert transport.calls[0][1] == transport.calls[2][1]
    assert progress("old")[:2] == ("submitted", 1)


def test_failed_batch_preserves_progress_while_other_records_continue(transport):
    old("first", materials={"装置": 100})
    old("second", at=1759400010, materials={"固源岩": 1})
    transport.statuses[:] = [requests.Timeout()]
    resume(transport)
    assert len(transport.calls) == 2
    assert progress("first")[:2] == ("failed", 0)
    assert progress("second")[:2] == ("submitted", 1)
    report._drain(transport.directory)
    assert len(transport.calls) == 2
    resume(transport)
    assert len(transport.calls) == 2
    assert report.retry_recycling_report("first")
    report._drain(transport.directory)
    assert len(transport.calls) == 3
    assert transport.calls[0][1] == transport.calls[-1][1]


@pytest.mark.parametrize("response", [(200, b'{"code":500}'), (302, b""), (400, b"")])
def test_unexpected_responses_keep_the_cursor_for_manual_retry(transport, response):
    old(materials={"装置": 1})
    transport.statuses.append(response)
    resume(transport)
    assert progress("old")[:2] == ("failed", 0)
    resume(transport)
    assert len(transport.calls) == 1
    assert progress("old")[:2] == ("failed", 0)
    assert report.retry_recycling_report("old")
    report._drain(transport.directory)
    assert progress("old")[:2] == ("submitted", 1)


def test_identity_persists_and_instances_have_different_uids(transport, monkeypatch):
    save()
    report._drain(transport.directory)
    save("second", at=1759400100)
    report._drain(transport.directory)
    assert transport.calls[0][1]["headers"] == transport.calls[1][1]["headers"]
    state = json.loads((transport.directory / "state.json").read_text())
    assert len(state["uid"]) == 32
    other = transport.directory.with_name("instance-b")
    monkeypatch.setattr(report, "get_path", lambda _: other)
    save("third", at=1759400200)
    report._drain(other)
    assert transport.calls[2][1]["headers"] != transport.calls[0][1]["headers"]


def test_unknown_materials_do_not_block_other_history_or_split_a_fitting_batch(
    transport,
):
    old("unknown", materials=None)
    for index in range(100):
        old(str(index), at=1759400001 + index, materials={"装置": 1})
    resume(transport)
    assert progress("unknown")[:2] == ("skipped", 0)
    assert len(transport.calls) == 1
    assert len(transport.calls[0][1]["json"]["drops"]) == 100


def test_unmapped_items_need_manual_retry_after_a_resource_change(
    transport, monkeypatch
):
    old("future", materials={"新材料": 1})
    old("known", at=1759400010, materials={"装置": 1})
    resume(transport)
    assert progress("future")[:2] == ("failed", 0)
    assert progress("known")[:2] == ("submitted", 1)
    monkeypatch.setitem(report.key_mapping, "新材料", ["future_item"])
    resume(transport)
    assert len(transport.calls) == 1
    assert progress("future")[:2] == ("failed", 0)
    assert report.retry_recycling_report("future")
    report._drain(transport.directory)
    assert transport.calls[-1][1]["json"]["drops"][0]["itemId"] == "future_item"


def test_waiting_roster_is_not_reported_until_read_finishes_or_next_start(transport):
    record.save_recycling_collection("unfinished", 1759400000, None, {"装置": 1})
    report._drain(transport.directory)
    assert not transport.calls
    record.update_recycling_operators("unfinished", ["旅骨"])
    assert report.report_recycling_collection("unfinished")
    report._drain(transport.directory)
    assert transport.calls[0][1]["json"]["drops"][0]["operators"] == [
        "char_4232_hbound"
    ]
    assert report.report_recycling_collection("unfinished")
    report._drain(transport.directory)
    assert len(transport.calls) == 1
    record.save_recycling_collection("crashed", 1759400010, None, {"装置": 1})
    resume(transport)
    assert "operators" not in transport.calls[-1][1]["json"]["drops"][0]


def test_worker_start_failure_retains_pending_history(transport):
    transport.worker.return_value.start.side_effect = RuntimeError()
    record.save_recycling_collection("event", 1759400000, None, {"装置": 1})
    assert not report.report_recycling_collection("event")
    assert progress("event")[:2] == ("pending", 0)
    assert not report._running


def test_corrupt_identity_is_not_replaced_or_marked_as_submitted(transport):
    transport.directory.mkdir()
    path = transport.directory / "state.json"
    path.write_text('{"uid": null}')
    old(materials={"装置": 1})
    resume(transport)
    assert not transport.calls
    assert path.read_text() == '{"uid": null}'
    assert progress("old")[:2] == ("failed", 0)


def test_automation_start_kicks_backfill_without_device_collection(
    transport, monkeypatch
):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    from arknights_mower import __main__ as main

    old(materials={"装置": 1})
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main.rapidocr, "initialize_ocr", Mock())
    simulate = Mock()
    monkeypatch.setattr(main, "simulate", simulate)
    main._main({})
    transport.worker.assert_called_once()
    simulate.assert_called_once_with(None)
    resume(transport)
    assert len(transport.calls) == 1


def test_actual_collection_records_before_dismissal_and_reports_once(
    transport, monkeypatch
):
    from arknights_mower.tests.recycling_collection_tests import collection_solver
    from arknights_mower.utils import recycling
    from arknights_mower.utils.scene import Scene

    solver = collection_solver()
    solver._recycling_pending = {"id": "actual-report", "at": 1759400000}
    solver.scene = Mock(
        side_effect=[Scene.MATERIEL, Scene.MATERIEL, Scene.MATERIEL, Scene.INFRA_MAIN]
    )
    monkeypatch.setattr(
        recycling, "read_recycling_materials", Mock(return_value={"装置": 2})
    )
    solver._finish_recycling_collection()
    assert progress("actual-report")[:2] == ("waiting", 0)
    solver._finish_recycling_collection()
    assert progress("actual-report")[:2] == ("pending", 0)
    report._drain(transport.directory)
    assert len(transport.calls) == 1
    assert len(transport.calls[0][1]["json"]["drops"]) == 2
    assert progress("actual-report")[:2] == ("submitted", 2)


def test_existing_database_gains_progress_without_replacing_old_evidence(
    transport, monkeypatch
):
    old(materials={"装置": 2}, names=["旅骨"])
    with record._conn() as connection:
        connection.execute("DROP TABLE recycling_report_progress")
        connection.commit()
    monkeypatch.setattr(record, "_tables_created", False)
    with record._conn() as connection:
        record._ensure_tables(connection)
    assert report.start_recycling_reports()
    report._drain(transport.directory)
    assert progress("old")[:2] == ("submitted", 2)
    with record._conn() as connection:
        row = connection.execute(
            "SELECT collected_at, operators, materials FROM recycling_collection WHERE event_id = 'old'"
        ).fetchone()
    assert row == (1759400000, json.dumps(["旅骨"]), json.dumps({"装置": 2}))


def test_background_network_never_blocks_new_collection_or_creates_another_worker(
    transport, monkeypatch
):
    from threading import Event, Thread

    started, release = Event(), Event()
    threads = []
    original_submit = report._submit

    def submit(*args):
        started.set()
        assert release.wait(3)
        original_submit(*args)

    def worker(**kwargs):
        thread = Thread(**kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setattr(report, "Thread", worker)
    monkeypatch.setattr(report, "_submit", submit)
    try:
        save()
        assert started.wait(3)
        save("second", at=1759400010)
        assert len(threads) == 1
        assert not transport.calls
    finally:
        release.set()
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
    assert len(transport.calls) == 2
    assert not report._running


def test_collection_arriving_as_worker_finishes_is_not_lost(transport, monkeypatch):
    original_next = report._next_batch
    delivered = []

    def next_batch():
        batch, offsets = original_next()
        if not batch["drops"] and not delivered:
            delivered.append(True)
            save("late")
        return batch, offsets

    monkeypatch.setattr(report, "_next_batch", next_batch)
    assert report.start_recycling_reports()
    report._drain(transport.directory)
    assert transport.worker.call_count == 2
    report._drain(transport.directory)
    assert len(transport.calls) == 1
    assert progress("late")[:2] == ("submitted", 1)


def test_history_exposes_persistent_upload_states_without_marking_partial_submission_done(
    transport,
):
    record.save_recycling_collection("waiting", 1759400010, None, {"装置": 1})
    old("legacy", at=1759400020, materials={"装置": 1})
    old("unknown", at=1759400030, materials=None)
    save("partial", materials={"装置": 101})
    transport.statuses[:] = [(200, b""), (400, b"")]
    report._drain(transport.directory)
    old("unprocessed", at=1759400040, materials={"装置": 1})
    old("unread", at=1759400050, materials=None)

    rows = {
        row["id"]: row
        for row in record.get_recycling_history("2000-01-01", "2100-01-01")["records"]
    }
    assert {key: row["upload_status"] for key, row in rows.items()} == {
        "waiting": "waiting",
        "legacy": "failed",
        "unknown": "skipped",
        "partial": "failed",
        "unprocessed": "pending",
        "unread": "skipped",
    }
    assert progress("partial")[:2] == ("failed", 100)
    assert rows["partial"]["materials"] == {"装置": 101}


def test_unknown_collection_is_never_uploaded_or_exposed_as_retryable(transport):
    record.save_recycling_collection("unknown", 1759400000, None, None)
    before = record.get_recycling_history("2000-01-01", "2100-01-01")["records"][0]
    assert before["materials"] is None
    assert before["upload_status"] == "skipped"
    assert report.report_recycling_collection("unknown")
    report._drain(transport.directory)
    assert not transport.calls
    assert progress("unknown")[:2] == ("skipped", 0)
    with pytest.raises(ValueError, match="只有上传失败"):
        report.retry_recycling_report("unknown")
    resume(transport)
    assert not transport.calls


def test_manual_retry_route_requires_token_before_changing_progress_or_starting_worker(
    transport,
    monkeypatch,
):
    import server

    old(materials={"装置": 1})
    transport.statuses[:] = [(400, b"")]
    resume(transport)
    before = progress("old")
    transport.worker.reset_mock()
    transport.calls.clear()
    monkeypatch.setattr(server.app, "token", "recycling-test", raising=False)
    client = server.app.test_client()
    for headers in ({}, {"token": "wrong"}):
        assert (
            client.post(
                "/report/recycling_history/old/retry", headers=headers
            ).status_code
            == 403
        )
        assert (
            client.get("/report/recycling_history", headers=headers).status_code == 403
        )
    assert progress("old") == before
    transport.worker.assert_not_called()
    assert not transport.calls


def test_manual_retry_resumes_only_failed_units_and_does_not_admit_duplicate_clicks(
    transport,
    monkeypatch,
):
    import server

    old("old/collection", materials={"装置": 201})
    transport.statuses[:] = [(200, b""), (400, b"")]
    resume(transport)
    assert progress("old/collection")[:2] == ("failed", 100)
    base_ms = progress("old/collection")[2]
    transport.worker.reset_mock()
    monkeypatch.setattr(server.app, "token", "recycling-test", raising=False)
    client = server.app.test_client()
    headers = {"token": "recycling-test"}

    accepted = client.post(
        "/report/recycling_history/old%2Fcollection/retry", headers=headers
    )
    assert accepted.status_code == 202
    assert accepted.json == {"upload_status": "pending"}
    assert progress("old/collection") == ("pending", 100, base_ms)
    assert (
        client.post(
            "/report/recycling_history/old%2Fcollection/retry", headers=headers
        ).status_code
        == 409
    )
    transport.worker.assert_called_once()
    assert len(transport.calls) == 2
    transport.statuses[:] = [requests.Timeout()]
    report._drain(transport.directory)
    assert len(transport.calls) == 3
    assert progress("old/collection") == ("failed", 100, base_ms)
    resume(transport)
    assert len(transport.calls) == 3
    assert (
        client.post(
            "/report/recycling_history/old%2Fcollection/retry", headers=headers
        ).status_code
        == 202
    )
    report._drain(transport.directory)
    assert [len(call[1]["json"]["drops"]) for call in transport.calls] == [
        100,
        100,
        100,
        100,
        1,
    ]
    assert transport.calls[1][1] == transport.calls[2][1]
    assert progress("old/collection") == ("submitted", 201, base_ms)
    history = client.get(
        "/report/recycling_history?startDate=2000-01-01&endDate=2100-01-01",
        headers=headers,
    )
    assert history.json["records"][0]["upload_status"] == "submitted"
    assert (
        client.post(
            "/report/recycling_history/old%2Fcollection/retry", headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/report/recycling_history/missing/retry", headers=headers
        ).status_code
        == 404
    )
    assert len(transport.calls) == 5


@pytest.mark.parametrize("retry_timing", ["before", "after", "between_batches"])
@pytest.mark.parametrize("retry_fails", [False, True])
def test_manual_retry_survives_other_batches_progress_failure(
    transport, monkeypatch, retry_fails, retry_timing
):
    from threading import Event, Thread

    import server

    between_batches = retry_timing == "between_batches"
    old(materials={"装置": 201 if between_batches else 1})
    old("other", at=1759400010, materials={"固源岩": 1})
    with record._conn() as connection:
        connection.execute(
            "INSERT INTO recycling_report_progress (event_id, status) "
            "VALUES ('other', 'failed')"
        )
        connection.execute(
            "CREATE TRIGGER ignore_report_progress BEFORE UPDATE "
            "ON recycling_report_progress WHEN NEW.event_id = 'old' "
            + (
                "AND NEW.next_unit = 200 "
                if between_batches
                else "AND NEW.status = 'submitted' "
            )
            + "BEGIN SELECT RAISE(IGNORE); END"
        )
        connection.commit()
    paused, release = Event(), Event()
    threads = []
    submit = report._submit

    def worker(**kwargs):
        thread = Thread(**kwargs)
        threads.append(thread)
        return thread

    def pause():
        if not paused.is_set():
            paused.set()
            assert release.wait(3)

    def submit_then_pause(*args):
        submit(*args)
        if retry_timing != "after":
            pause()

    def pause_after_failed_commit(*args):
        if retry_timing == "after":
            pause()

    monkeypatch.setattr(report, "Thread", worker)
    monkeypatch.setattr(report, "_submit", submit_then_pause)
    monkeypatch.setattr(report.logger, "exception", pause_after_failed_commit)
    monkeypatch.setattr(server.app, "token", "recycling-test", raising=False)
    client = server.app.test_client()
    headers = {"token": "recycling-test"}
    if retry_fails:
        transport.statuses[:] = [(200, b"")] * (2 if between_batches else 1)
        transport.statuses.append(requests.Timeout())
    retry_id = "old" if retry_timing == "after" else "other"
    untouched_id = "other" if retry_timing == "after" else "old"
    retry_url = f"/report/recycling_history/{retry_id}/retry"
    try:
        assert report.start_recycling_reports()
        assert paused.wait(3)
        assert progress(retry_id)[:2] == ("failed", 0)
        if retry_timing == "after":
            with record._conn() as connection:
                connection.execute("DROP TRIGGER ignore_report_progress")
                connection.commit()
        response = client.post(retry_url, headers=headers)
        assert response.status_code == 202
        assert client.post(retry_url, headers=headers).status_code == 409
    finally:
        release.set()
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
    assert [len(call[1]["json"]["drops"]) for call in transport.calls] == (
        [100, 100, 1] if between_batches else [1, 1]
    )
    assert progress(retry_id)[:2] == (
        ("failed", 0) if retry_fails else ("submitted", 1)
    )
    assert progress(untouched_id)[:2] == ("failed", 100 if between_batches else 0)
    assert len(threads) == 1
    assert not report._running


@pytest.mark.parametrize("status", ["waiting", "pending", "submitted", "skipped"])
def test_manual_retry_cannot_release_unfinished_roster_or_resend_other_states(
    transport,
    status,
):
    record.save_recycling_collection("event", 1759400000, None, {"装置": 1})
    with record._conn() as connection:
        connection.execute("UPDATE recycling_report_progress SET status = ?", (status,))
        connection.commit()
    with pytest.raises(ValueError, match="只有上传失败"):
        report.retry_recycling_report("event")
    assert progress("event")[:2] == (status, 0)
    transport.worker.assert_not_called()
    assert not transport.calls


def test_manual_retry_worker_launch_failure_keeps_record_retryable(
    transport, monkeypatch
):
    import server

    old(materials={"装置": 1})
    transport.statuses[:] = [(400, b"")]
    resume(transport)
    before = progress("old")
    transport.worker.return_value.start.side_effect = RuntimeError()
    monkeypatch.setattr(server.app, "token", "recycling-test", raising=False)
    client = server.app.test_client()
    headers = {"token": "recycling-test"}
    assert (
        client.post("/report/recycling_history/old/retry", headers=headers).status_code
        == 503
    )
    assert progress("old") == before
    transport.worker.return_value.start.side_effect = None
    assert (
        client.post("/report/recycling_history/old/retry", headers=headers).status_code
        == 202
    )
    report._drain(transport.directory)
    assert progress("old")[:2] == ("submitted", 1)
