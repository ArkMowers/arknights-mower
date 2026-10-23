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
    waits = Mock()
    monkeypatch.setattr(report, "sleep", waits)
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
        calls=calls, statuses=statuses, waits=waits, worker=worker, directory=directory
    )


def save(event_id="event", at=1759400000, materials=None, names=None):
    record.save_recycling_collection(event_id, at, names, materials or {"装置": 1})
    assert report.report_recycling_collection(event_id)


def old(event_id="old", at=1759400000, materials=None, names=None):
    with record._conn() as connection:
        connection.execute(
            "INSERT INTO recycling_collection VALUES (?, ?, ?, ?)",
            (event_id, at, json.dumps(names), json.dumps(materials)),
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
    transport.waits.assert_not_called()
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
    transport.waits.assert_not_called()


def test_backfill_does_not_move_old_dates_past_previously_submitted_new_records(
    transport,
):
    save(at=1759500000)
    report._drain(transport.directory)
    old(at=1759400000, materials={"装置": 1})
    resume(transport)
    assert transport.calls[1][1]["json"]["drops"][0]["dropTime"] == 1759400000000


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


def test_failed_requests_retry_with_identical_details_and_wait_only_after_failure(
    transport,
):
    old(materials={"装置": 1})
    transport.statuses[:] = [requests.ConnectionError(), (503, b""), (200, b"")]
    resume(transport)
    assert len(transport.calls) == 3
    assert transport.calls[0][1] == transport.calls[1][1] == transport.calls[2][1]
    assert [call.args[0] for call in transport.waits.call_args_list] == [5, 30]
    assert progress("old")[:2] == ("submitted", 1)


def test_exhausted_batch_preserves_progress_while_other_records_continue(transport):
    old("first", materials={"装置": 100})
    old("second", at=1759400010, materials={"固源岩": 1})
    transport.statuses[:] = [requests.Timeout(), requests.Timeout(), requests.Timeout()]
    resume(transport)
    assert len(transport.calls) == 4
    assert progress("first")[:2] == ("failed", 0)
    assert progress("second")[:2] == ("submitted", 1)
    report._drain(transport.directory)
    assert len(transport.calls) == 4
    resume(transport)
    assert len(transport.calls) == 5
    assert transport.calls[0][1] == transport.calls[-1][1]


@pytest.mark.parametrize("response", [(200, b'{"code":500}'), (302, b""), (400, b"")])
def test_unexpected_responses_keep_the_cursor_for_the_next_start(transport, response):
    old(materials={"装置": 1})
    transport.statuses.append(response)
    resume(transport)
    assert progress("old")[:2] == ("failed", 0)
    transport.waits.assert_not_called()
    resume(transport)
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


def test_unmapped_items_remain_pending_for_a_resource_change(transport, monkeypatch):
    old("future", materials={"新材料": 1})
    old("known", at=1759400010, materials={"装置": 1})
    resume(transport)
    assert progress("future")[:2] == ("failed", 0)
    assert progress("known")[:2] == ("submitted", 1)
    monkeypatch.setitem(report.key_mapping, "新材料", ["future_item"])
    resume(transport)
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
