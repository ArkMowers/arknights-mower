"""Offline recycling evidence, probability model and collection boundaries."""

import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call
from zipfile import ZipFile

import cv2
import numpy as np
import pytest

with pytest.MonkeyPatch.context() as import_patch:
    import_patch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    from arknights_mower.solvers import base_mixin, base_schedule, record
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import recycling
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene


@pytest.fixture(autouse=True)
def report_submission(monkeypatch):
    from arknights_mower.utils import recycling_report

    submit = Mock()
    monkeypatch.setattr(recycling_report, "report_recycling_collection", submit)
    return submit


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "data.db"
    monkeypatch.setattr(record, "_tables_created", False)
    with sqlite3.connect(path) as connection:
        record._ensure_tables(connection)

    @contextmanager
    def connect():
        with sqlite3.connect(path) as connection:
            yield connection

    monkeypatch.setattr(record, "_conn", connect)
    return path


def at(day, hour=0):
    return datetime(2026, 10, day, hour).timestamp()


def test_collection_identity_and_immutable_roster(db):
    names = ["旅骨", "阿米娅"]
    assert record.save_recycling_collection("one", at(10), names, {"装置": 2})
    names.clear()
    assert not record.save_recycling_collection("one", at(10), [], {"装置": 2})
    assert record.save_recycling_collection("two", at(10), [], {"装置": 2})
    record.update_recycling_operators("one", ["能天使"])
    result = record.get_recycling_history("2026-10-10", "2026-10-10")
    assert result["total"] == 2
    assert result["materials"][0]["count"] == 4
    assert result["records"][1]["operators"] == ["旅骨", "阿米娅"]
    assert result["records"][0]["operators"] == []


def test_unknown_roster_and_failed_material_observation_remain_unknown(db):
    record.save_recycling_collection("unknown", at(10), None, None)
    result = record.get_recycling_history("2026-10-10", "2026-10-10")
    assert result["records"][0]["materials"] is None
    assert result["records"][0]["operators"] is None
    assert result["comparison"]["actual_sanity"] is None
    assert result["comparison"]["unknown_collections"] == 1
    record.update_recycling_operators("unknown", [])
    assert (
        record.get_recycling_history("2026-10-10", "2026-10-10")["records"][0][
            "operators"
        ]
        == []
    )


@pytest.mark.parametrize(
    "materials",
    [{}, {"装置": 0}, {"装置": -1}, {"装置": True}, {"装置": 1.2}, {"": 1}, []],
)
def test_invalid_quantities_reject_with_structured_error(db, materials):
    with pytest.raises(ValueError, match="回收站收取记录"):
        record.save_recycling_collection("bad", at(10), None, materials)
    assert record.get_recycling_history("2026-10-10", "2026-10-10")["total"] == 0


def test_calendar_bounds_pagination_and_totals_are_independent(db):
    for index, timestamp in enumerate([at(9, 23), at(10), at(10, 23), at(11)]):
        record.save_recycling_collection(str(index), timestamp, [], {"装置": 1})
    result = record.get_recycling_history(
        "2026-10-10", "2026-10-10", page=2, page_size=1
    )
    assert result["total"] == 2
    assert len(result["records"]) == 1
    assert result["records"][0]["collected_at"] == at(10)
    assert result["materials"][0]["count"] == 2


@pytest.mark.parametrize(
    "start,end,page,size",
    [
        ("bad", "2026-10-10", 1, 50),
        ("2026-10-11", "2026-10-10", 1, 50),
        ("2026-10-10", "2026-10-10", 0, 50),
        ("2026-10-10", "2026-10-10", 1, 201),
    ],
)
def test_history_rejects_invalid_parameters(db, start, end, page, size):
    with pytest.raises(ValueError):
        record.get_recycling_history(start, end, page, size)


def test_probability_snapshot_reconciles_with_calculation_sheet():
    model = recycling.recycling_model()
    assert sum(row["weight"] for row in model["ordinary"]) == 10000
    assert sum(row["weight"] for row in model["extra"]) == 10000
    from arknights_mower.utils.recycling_valuation import default_valuation

    valuation = default_valuation()
    valuation["prices"] = {
        row["name"]: row["sanity"] for row in model["ordinary"] + model["extra"]
    }
    stats = recycling.recycling_expectation(
        [{"name": "装置", "count": 2}], valuation=valuation
    )
    assert stats["ordinary_sanity"] == pytest.approx(19.60789962777894)
    assert stats["extra_sanity"] == pytest.approx(76.77420071774533)
    assert stats["extra_rate"] == pytest.approx(0.052613)
    assert stats["actual_sanity"] == pytest.approx(2 * 8.159184154709665)
    expected = (19.60789962777894 + 0.052613 * 76.77420071774533) / 1.052613
    assert stats["expected_sanity"] == pytest.approx(2 * expected)
    assert sum(row["probability"] for row in stats["qualities"]) == pytest.approx(1)
    assert sum(row["expected_count"] for row in stats["qualities"]) == pytest.approx(2)


def test_unvalued_material_never_becomes_zero_value():
    stats = recycling.recycling_expectation([{"name": "未知材料", "count": 1}])
    assert stats["actual_sanity"] is None
    assert stats["expected_sanity"] is None
    assert stats["unknown_materials"] == ["未知材料"]


@pytest.fixture(scope="module")
def real_ocr():
    from arknights_mower.utils.rapidocr import create_engine

    return create_engine()


def reward_frame():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = cv2.imread(str(Path(__file__).parent / "fixtures/recycling/device.png"))
    image[415:705, 820:1100] = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return image


def test_supplied_device_reward_name_icon_and_quantity(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


def test_archived_sugar_reward_name_icon_and_quantity(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    path = Path(__file__).parent / "fixtures/recycling/reward_sugar_20261027.jpg"
    image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    assert recycling.read_recycling_materials(image) == {"糖": 1}


def test_multiple_rewards_require_every_icon_and_quantity(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = reward_frame()[415:705, 820:1100]
    image[415:705, 640:920] = crop
    image[415:705, 1000:1280] = crop
    assert recycling.read_recycling_materials(image) == {"装置": 2}
    image[640:705, 1000:1280] = 0
    assert recycling.read_recycling_materials(image) == {"装置": 2}
    image[570:625, 1000:1280] = 0
    assert recycling.read_recycling_materials(image) is None


def test_wrong_icon_does_not_confirm_ocr_name(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    image = reward_frame()
    image[415:570] = 0
    assert recycling.read_recycling_materials(image) is None


def material_ocr_readings(name="装置", count="1", *, name_score=1.0, count_score=1.0):
    box = [[925, 12], [997, 12], [997, 48], [925, 48]]

    def read(image, *, use_det=True):
        if use_det:
            return [(box, name, name_score)]
        assert image.ndim == 2
        return [(None, count, count_score)]

    return Mock(side_effect=read)


def test_unknown_name_uses_the_icon_but_inexact_quantity_rejects(monkeypatch):
    monkeypatch.setattr(recycling, "_ocr", material_ocr_readings(name="不明物品"))
    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}
    monkeypatch.setattr(recycling, "_ocr", material_ocr_readings(count="1.2万"))
    assert recycling.read_recycling_materials(reward_frame()) is None


def collection_solver(monkeypatch=None):
    solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    solver.op_data = SimpleNamespace(recycle_capacity=2)
    solver.recog = SimpleNamespace(
        img=np.zeros((1080, 1920, 3), dtype=np.uint8), save_screencap=Mock()
    )
    solver.tap = Mock()
    solver.sleep = Mock()
    if monkeypatch is not None:
        monkeypatch.setattr(base_mixin.config.conf, "screenshot_interval", 100)
        monkeypatch.setattr(base_mixin.config.conf, "selection_transition_timeout", 2.5)
        monkeypatch.setattr(
            base_mixin,
            "perf_counter",
            lambda: round(
                sum(
                    call.args[0] if call.args else 1
                    for call in solver.sleep.call_args_list
                ),
                6,
            ),
        )
    solver.scene_graph_navigation = Mock()
    solver._read_recycling_operators = Mock(return_value=["旅骨"])
    return solver


def notification_reward_frame():
    path = (
        Path(__file__).parent / "fixtures/recycling/reward_notifications_20261018.jpg"
    )
    return cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)


def test_archived_collection_notifications_require_gold_stripe_and_dark_panel():
    image = notification_reward_frame()
    assert recycling._collection_notifications(image) == [
        (90, 245),
        (275, 430),
        (460, 615),
        (645, 800),
    ]
    without_stripe = image.copy()
    without_stripe[:, 1412:1430] = 0
    assert recycling._collection_notifications(without_stripe) == []
    without_panel = image.copy()
    without_panel[:, 1560:] = 255
    assert recycling._collection_notifications(without_panel) == []


def test_collection_ignores_persistent_notifications_and_records_matching_rewards(
    db, real_ocr, monkeypatch
):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    solver = collection_solver()
    image = notification_reward_frame()
    solver.recog.img = image.copy()
    solver._recycling_pending = {"id": "notification-ignored", "at": at(18, 19)}
    solver.scene = Mock(side_effect=[Scene.MATERIEL, Scene.INFRA_MAIN])
    ocr = Mock(wraps=recycling._ocr)
    circles = Mock(wraps=recycling.cv2.HoughCircles)
    monkeypatch.setattr(recycling, "_ocr", ocr)
    monkeypatch.setattr(recycling.cv2, "HoughCircles", circles)

    def dismiss(_position):
        result = record.get_recycling_history("2026-10-18", "2026-10-18")
        assert result["records"][0]["materials"] == {"凝胶": 1}
        assert result["records"][0]["collected_at"] == at(18, 19)

    solver.tap.side_effect = dismiss
    solver._finish_recycling_collection()

    assert circles.call_count == 1
    assert not np.any(ocr.call_args_list[0].args[0][5:, 1410:])
    assert not np.any(circles.call_args_list[0].args[0][180:335, 1410:])
    assert np.array_equal(solver.recog.img, image)
    solver.sleep.assert_not_called()
    solver.tap.assert_called_once_with((960, 960))
    solver.recog.save_screencap.assert_not_called()
    result = record.get_recycling_history("2026-10-18", "2026-10-18")
    assert result["total"] == 1
    assert result["records"][0]["operators"] == ["旅骨"]
    assert solver._recycling_pending is None


def multiple_reward_frame(centers):
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = reward_frame()[415:705, 820:1100]
    for center in centers:
        image[415:705, center - 140 : center + 140] = crop
    return image


def test_multiple_rewards_remain_complete_beside_notifications(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    image = multiple_reward_frame((780, 1140))
    image[:, 1410:] = notification_reward_frame()[:, 1410:]
    assert recycling.read_recycling_materials(image) == {"装置": 2}
    image[640:705, 1000:1280] = 0
    assert recycling.read_recycling_materials(image) == {"装置": 2}
    image[570:625, 1000:1280] = 0
    assert recycling.read_recycling_materials(image) is None


@pytest.mark.parametrize("centers", [(600, 1320), (360, 1560), (420, 780, 1140, 1500)])
def test_notifications_covering_real_rewards_never_record_only_visible_materials(
    real_ocr, monkeypatch, centers
):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    image = multiple_reward_frame(centers)
    assert recycling._collection_notifications(image) == []
    assert recycling.read_recycling_materials(image) == {"装置": len(centers)}
    image[:, 1410:] = notification_reward_frame()[:, 1410:]
    assert recycling.read_recycling_materials(image) is None


@pytest.mark.parametrize("readable", [True, False])
def test_persistent_notifications_wait_only_for_unknown_rewards_once(
    db, monkeypatch, readable
):
    solver = collection_solver()
    solver.recog.img = notification_reward_frame()
    solver._recycling_pending = {"id": "persistent-notification"}
    solver.scene = Mock(side_effect=[Scene.MATERIEL, Scene.MATERIEL, Scene.INFRA_MAIN])
    reader = Mock(return_value={"凝胶": 1} if readable else None)
    monkeypatch.setattr(recycling, "read_recycling_materials", reader)
    clock = [0.0]
    monkeypatch.setattr(base_schedule, "monotonic", lambda: clock[0])
    solver.sleep.side_effect = lambda interval: clock.__setitem__(
        0, clock[0] + interval
    )

    solver._finish_recycling_collection()
    assert solver._recycling_pending["recorded"]
    assert solver.sleep.call_args_list == (
        [] if readable else [call(0.5)] * 10 + [call(0.3)] * 4
    )
    assert reader.call_count == (1 if readable else 15)
    solver.sleep.reset_mock()
    solver._finish_recycling_collection()
    solver.sleep.assert_not_called()
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["total"] == 1
    assert result["records"][0]["materials"] == ({"凝胶": 1} if readable else None)


@pytest.mark.parametrize("centers", [(600, 1320), (360, 1560), (1560,)])
def test_collection_waits_for_covered_rewards_then_records_the_complete_batch(
    db, real_ocr, monkeypatch, centers
):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    solver = collection_solver()
    clear = multiple_reward_frame(centers)
    solver.recog.img = clear.copy()
    solver.recog.img[:, 1410:] = notification_reward_frame()[:, 1410:]
    event = {"id": "covered-rewards", "at": at(18, 19)}
    solver._recycling_pending = event.copy()
    solver.scene = Mock(side_effect=[Scene.MATERIEL, Scene.INFRA_MAIN])
    clock = [0.0]
    monkeypatch.setattr(base_schedule, "monotonic", lambda: clock[0])

    def refresh(interval):
        clock[0] += interval
        assert record.get_recycling_history("2026-10-18", "2026-10-18")["total"] == 0
        assert solver._recycling_pending == event
        solver.tap.assert_not_called()
        if clock[0] >= 1:
            solver.recog.img = clear.copy()

    solver.sleep.side_effect = refresh

    def dismiss(_position):
        result = record.get_recycling_history("2026-10-18", "2026-10-18")
        assert result["total"] == 1
        assert result["records"][0]["materials"] == {"装置": len(centers)}
        assert result["records"][0]["collected_at"] == event["at"]

    solver.tap.side_effect = dismiss
    solver._finish_recycling_collection()

    assert solver.sleep.call_args_list == [call(0.5), call(0.5)]
    solver.recog.save_screencap.assert_not_called()
    assert solver._recycling_pending is None


@pytest.mark.parametrize("notifications", [False, True])
def test_unknown_rewards_without_notifications_at_reward_height_add_no_wait(
    db, monkeypatch, notifications
):
    solver = collection_solver()
    if notifications:
        solver.recog.img[90:245, 1410:] = notification_reward_frame()[90:245, 1410:]
    solver._recycling_pending = {"id": "unknown-uncovered", "at": at(18, 19)}
    solver.scene = Mock(side_effect=[Scene.MATERIEL, Scene.INFRA_MAIN])
    monkeypatch.setattr(recycling, "read_recycling_materials", Mock(return_value=None))

    solver._finish_recycling_collection()

    assert solver.sleep.call_args_list == [call(0.3)] * 4
    result = record.get_recycling_history("2026-10-18", "2026-10-18")
    assert result["records"][0]["materials"] is None


def test_incomplete_first_reading_retries_on_a_fresh_frame_and_records_success(
    db, monkeypatch
):
    solver = collection_solver()
    solver.recog.img = reward_frame()
    solver._recycling_pending = {"id": "retry-complete", "at": at(18, 19)}
    solver.scene = Mock(side_effect=[Scene.MATERIEL, Scene.INFRA_MAIN])
    reader = Mock(side_effect=[None, {"装置": 1}])
    monkeypatch.setattr(recycling, "read_recycling_materials", reader)
    refreshed = []

    def refresh(interval):
        assert interval == 0.3
        refreshed.append(interval)
        solver.recog.img = reward_frame()

    solver.sleep.side_effect = refresh

    solver._finish_recycling_collection()

    assert reader.call_count == 2
    assert refreshed == [0.3]
    solver.recog.save_screencap.assert_not_called()
    result = record.get_recycling_history("2026-10-18", "2026-10-18")
    assert result["total"] == 1
    assert result["records"][0]["materials"] == {"装置": 1}
    assert solver._recycling_pending is None


def test_cancellation_while_waiting_for_covered_rewards_preserves_event(
    db, monkeypatch
):
    from arknights_mower.utils.csleep import MowerExit

    solver = collection_solver()
    solver.recog.img = notification_reward_frame()
    event = {"id": "cancelled-occlusion", "at": at(18, 19)}
    solver._recycling_pending = event.copy()
    solver.sleep.side_effect = MowerExit
    monkeypatch.setattr(recycling, "read_recycling_materials", Mock(return_value=None))

    with pytest.raises(MowerExit):
        solver._finish_recycling_collection()

    assert solver._recycling_pending == event
    solver.sleep.assert_called_once_with(0.5)
    solver.tap.assert_not_called()
    assert record.get_recycling_history("2026-10-18", "2026-10-18")["total"] == 0


def test_cancellation_during_reward_confirmation_preserves_pending_collection(
    db, monkeypatch
):
    from arknights_mower.utils.csleep import MowerExit

    solver = collection_solver()
    solver.recog.img = reward_frame()
    event = {"id": "cancelled-confirmation", "at": at(18, 19)}
    solver._recycling_pending = event.copy()
    solver.sleep.side_effect = MowerExit
    monkeypatch.setattr(
        recycling, "read_recycling_materials", Mock(side_effect=[None, {"凝胶": 1}])
    )

    with pytest.raises(MowerExit):
        solver._finish_recycling_collection()

    assert solver._recycling_pending == event
    solver.sleep.assert_called_once_with(0.3)
    solver.tap.assert_not_called()
    assert record.get_recycling_history("2026-10-18", "2026-10-18")["total"] == 0


def test_popup_retry_records_once_before_dismissal_and_reads_actual_staff(
    db, monkeypatch, report_submission
):
    solver = collection_solver()
    solver._recycling_pending = {"id": "popup"}
    solver.scene = Mock(
        side_effect=[Scene.MATERIEL, Scene.MATERIEL, Scene.MATERIEL, Scene.INFRA_MAIN]
    )
    monkeypatch.setattr(
        recycling, "read_recycling_materials", Mock(return_value={"装置": 1})
    )
    solver._finish_recycling_collection()
    assert solver._recycling_pending["recorded"]
    report_submission.assert_not_called()
    solver._finish_recycling_collection()
    assert solver._recycling_pending is None
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["total"] == 1
    assert result["records"][0]["operators"] == ["旅骨"]
    assert result["materials"][0]["count"] == 1
    report_submission.assert_called_once_with("popup")


@pytest.mark.parametrize("names", [None, [], ["旅骨"]])
def test_collection_hands_report_the_observed_snapshot(
    db, monkeypatch, report_submission, names
):
    solver = collection_solver()
    solver._recycling_pending = {"id": "report-snapshot", "at": at(18, 19)}
    solver.scene = Mock(return_value=Scene.INFRA_MAIN)
    solver._read_recycling_operators.return_value = names
    monkeypatch.setattr(
        recycling, "read_recycling_materials", Mock(return_value={"装置": 2})
    )
    solver._finish_recycling_collection()
    report_submission.assert_called_once_with("report-snapshot")
    saved = record.get_recycling_history("2026-10-18", "2026-10-18")["records"][0]
    assert saved["materials"] == {"装置": 2}
    assert saved["operators"] == names
    assert solver._recycling_pending is None


def test_archived_borderline_quantity_is_recorded(db, real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    solver = collection_solver()
    path = Path(__file__).parent / "fixtures/recycling/reward_quantity_20261012.jpg"
    solver.recog.img = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    solver._recycling_pending = {"id": "borderline-quantity"}
    solver.scene = Mock(return_value=Scene.INFRA_MAIN)
    solver._finish_recycling_collection()
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["materials"] == [{"name": "装置", "count": 1, "rarity": 2}]
    assert result["comparison"]["unknown_collections"] == 0
    assert result["records"][0]["materials"] == {"装置": 1}
    solver.sleep.assert_not_called()
    solver.recog.save_screencap.assert_not_called()


@pytest.mark.parametrize("icon_folder", ["depot", "材料图标"])
def test_windows_unicode_icon_failure_still_records_archived_reward(
    db, real_ocr, monkeypatch, tmp_path, icon_folder
):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    directory = tmp_path / icon_folder
    directory.mkdir()
    shutil.copyfile(
        recycling._icon_directory() / "固源岩组.webp", directory / "固源岩组.webp"
    )
    monkeypatch.setattr(recycling, "_icon_directory", lambda: directory)
    path = Path(__file__).parent / "fixtures/recycling/reward_orirock_20261013.jpg"
    solver = collection_solver()
    solver.recog.img = cv2.cvtColor(
        cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR),
        cv2.COLOR_BGR2RGB,
    )
    # Simulate OpenCV's narrow-path file loading on Windows, including Chinese
    # filenames beneath an otherwise ASCII installation directory.
    monkeypatch.setattr(recycling.cv2, "imread", Mock(return_value=None))
    recycling._material_icon.cache_clear()
    solver._recycling_pending = {"id": "windows-unicode-icon"}
    solver.scene = Mock(return_value=Scene.INFRA_MAIN)
    with monkeypatch.context() as pool_patch:
        pool_patch.setattr(
            recycling,
            "recycling_model",
            lambda: {"ordinary": [{"name": "固源岩组"}], "extra": []},
        )
        solver._finish_recycling_collection()
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["total"] == 1
    assert result["records"][0]["materials"] == {"固源岩组": 1}
    assert result["comparison"]["unknown_collections"] == 0
    solver.sleep.assert_not_called()
    solver.recog.save_screencap.assert_not_called()


@pytest.mark.parametrize("content", [None, b"", b"invalid image", "rgb"])
def test_unavailable_material_icon_preserves_unknown_collection(
    db, monkeypatch, tmp_path, content
):
    image = reward_frame()
    if content == "rgb":
        cv2.imencode(".webp", np.zeros((220, 220, 3), dtype=np.uint8))[1].tofile(
            tmp_path / "装置.webp"
        )
    elif content is not None:
        (tmp_path / "装置.webp").write_bytes(content)
    monkeypatch.setattr(recycling, "_ocr", material_ocr_readings())
    monkeypatch.setattr(recycling, "_icon_directory", lambda: tmp_path)
    recycling._material_icon.cache_clear()
    solver = collection_solver()
    solver.recog.img = image
    solver._recycling_pending = {"id": "unavailable-icon"}
    solver.scene = Mock(return_value=Scene.INFRA_MAIN)
    solver._finish_recycling_collection()
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["total"] == 1
    assert result["records"][0]["materials"] is None
    assert result["comparison"]["unknown_collections"] == 1
    solver.recog.save_screencap.assert_called_once_with("recycling")


@pytest.mark.parametrize(
    "name_score,count_score,icon_score,expected",
    [
        (0.90, 0.90, 0.91, {"装置": 1}),
        (0.89, 1.0, 1.0, {"装置": 1}),
        (1.0, 0.89, 1.0, None),
        (1.0, 1.0, 0.89, None),
    ],
)
def test_confidence_requires_icon_and_quantity_but_not_name(
    monkeypatch, name_score, count_score, icon_score, expected
):
    monkeypatch.setattr(
        recycling,
        "_ocr",
        material_ocr_readings(name_score=name_score, count_score=count_score),
    )
    monkeypatch.setattr(
        recycling,
        "recycling_model",
        lambda: {"ordinary": [{"name": "装置"}], "extra": []},
    )
    monkeypatch.setattr(
        recycling.cv2,
        "minMaxLoc",
        Mock(return_value=(0.0, icon_score, (0, 0), (30, 5))),
    )
    assert recycling.read_recycling_materials(reward_frame()) == expected


def test_other_material_sources_are_not_recorded():
    solver = collection_solver()
    solver.scene = Mock(return_value=Scene.MATERIEL)
    solver.last_room = "room_1_1"
    solver.transition()
    solver._read_recycling_operators.assert_not_called()
    solver.scene_graph_navigation.assert_called_once_with(Scene.INFRA_MAIN)


@pytest.mark.parametrize(("entry_delay", "dismiss_failures"), [(0, 0), (0, 1), (8, 0)])
def test_room_entry_records_incidental_collection_before_dismissal(
    db, monkeypatch, dismiss_failures, entry_delay
):
    solver = collection_solver(monkeypatch)
    page = ["map"]
    ready = [True]
    dismissals = [0]
    waits = [0]
    solver.scene = lambda: {
        "map": Scene.INFRA_MAIN,
        "connecting": Scene.CONNECTING,
        "reward": Scene.MATERIEL,
        "room": Scene.INFRA_DETAILS,
    }[page[0]]
    solver.find = lambda name: (
        ((100, 100) if name == "control_central" and page[0] == "map" else None)
        or (name == "connecting" and page[0] == "connecting")
    )
    solver.detect_room = lambda: "recycle" if page[0] == "room" else ""
    solver.adjust_room = Mock(return_value=(1278, 937))
    solver.scene_graph_navigation.side_effect = lambda *_: page.__setitem__(0, "map")
    monkeypatch.setattr(
        base_mixin.segment, "base", lambda *_args, **_kw: {"recycle": ()}
    )
    monkeypatch.setattr(
        recycling, "read_recycling_materials", Mock(return_value={"装置": 1})
    )

    def tap(*_args, **_kwargs):
        if page[0] == "map":
            page[0] = (
                ("connecting" if entry_delay else "reward") if ready[0] else "room"
            )
            ready[0] = False
        else:
            result = record.get_recycling_history("2000-01-01", "2100-01-01")
            assert result["total"] == 1
            assert result["records"][0]["materials"] == {"装置": 1}
            dismissals[0] += 1
            if dismissals[0] > dismiss_failures:
                page[0] = "room"

    def sleep(*_args):
        if page[0] == "connecting":
            waits[0] += 1
            if waits[0] == entry_delay:
                page[0] = "reward"

    solver.tap.side_effect = tap
    solver.sleep.side_effect = sleep
    solver.enter_room("recycle", max_attempts=1)

    assert page[0] == "room"
    assert waits[0] == entry_delay
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["total"] == 1
    assert result["records"][0]["operators"] == ["旅骨"]
    assert solver._recycling_pending is None


def test_room_entry_waits_for_connecting_before_recording_reward(db, monkeypatch):
    solver = collection_solver(monkeypatch)
    page = ["map"]
    solver.scene = lambda: Scene.INFRA_MAIN if page[0] == "map" else Scene.CONNECTING
    solver.find = lambda name: (
        ((100, 100) if name == "control_central" and page[0] == "map" else None)
        or (page[0] == "connecting" and name in {"connecting", "materiel_ico"})
    )
    solver.detect_room = Mock(return_value="")
    solver.adjust_room = Mock(return_value=(1278, 937))
    solver.tap.side_effect = lambda *_args, **_kwargs: page.__setitem__(0, "connecting")
    materials = Mock()
    monkeypatch.setattr(recycling, "read_recycling_materials", materials)
    monkeypatch.setattr(
        base_mixin.segment, "base", lambda *_args, **_kw: {"recycle": ()}
    )

    with pytest.raises(RuntimeError, match="未成功进入房间"):
        solver.enter_room("recycle", max_attempts=1)

    assert page[0] == "connecting"
    assert record.get_recycling_history("2000-01-01", "2100-01-01")["total"] == 0
    assert getattr(solver, "_recycling_pending", None) is None
    solver.tap.assert_called_once_with((1278, 937), interval=0.2)
    solver.detect_room.assert_not_called()
    solver._read_recycling_operators.assert_not_called()
    materials.assert_not_called()


@pytest.mark.parametrize(
    "room,initial_page", [("recycle", "reward"), ("contact", "map")]
)
def test_room_entry_does_not_attribute_unrelated_rewards(
    db, monkeypatch, room, initial_page
):
    solver = collection_solver(monkeypatch)
    page = [initial_page]
    solver.scene = lambda: Scene.INFRA_MAIN if page[0] == "map" else Scene.MATERIEL
    solver.find = lambda name: (
        (100, 100) if name == "control_central" and page[0] == "map" else None
    )
    solver.detect_room = lambda: ""
    solver.adjust_room = Mock(return_value=(1278, 937))
    solver.tap.side_effect = lambda *_args, **_kw: page.__setitem__(0, "reward")
    monkeypatch.setattr(base_mixin.segment, "base", lambda *_args, **_kw: {room: ()})

    with pytest.raises(RuntimeError, match="未成功进入房间"):
        solver.enter_room(room, max_attempts=1)

    assert record.get_recycling_history("2000-01-01", "2100-01-01")["total"] == 0
    solver._read_recycling_operators.assert_not_called()


def test_room_entry_without_production_enters_room_without_recording(db, monkeypatch):
    solver = collection_solver(monkeypatch)
    page = ["map"]
    solver.scene = lambda: Scene.INFRA_MAIN if page[0] == "map" else Scene.INFRA_DETAILS
    solver.find = lambda name: (
        (100, 100) if name == "control_central" and page[0] == "map" else None
    )
    solver.detect_room = lambda: "recycle" if page[0] == "room" else ""
    solver.adjust_room = Mock(return_value=(1278, 937))
    solver.tap.side_effect = lambda *_args, **_kwargs: page.__setitem__(0, "room")
    materials = Mock()
    monkeypatch.setattr(recycling, "read_recycling_materials", materials)
    monkeypatch.setattr(
        base_mixin.segment, "base", lambda *_args, **_kw: {"recycle": ()}
    )

    solver.enter_room("recycle", max_attempts=1)

    assert page[0] == "room"
    assert record.get_recycling_history("2000-01-01", "2100-01-01")["total"] == 0
    assert getattr(solver, "_recycling_pending", None) is None
    materials.assert_not_called()
    solver._read_recycling_operators.assert_not_called()


@pytest.mark.parametrize("visible", [True, False])
def test_roster_requires_facility_title_and_uses_two_actual_slots(visible):
    solver = collection_solver()
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.enter_room = Mock()
    solver.find = Mock(side_effect=lambda name, **kwargs: name == "room_detail")
    solver.get_color = Mock(return_value=np.array([255, 255, 255]))
    solver.read_screen = Mock(side_effect=["旅骨", "阿米娅"])
    solver.detect_room = Mock(return_value="recycle" if visible else "factory")
    result = BaseSchedulerSolver._read_recycling_operators(solver)
    assert result == (["旅骨", "阿米娅"] if visible else None)
    assert solver.read_screen.call_count == (2 if visible else 0)
    solver.enter_room.assert_called_once_with("recycle", max_attempts=1)


@pytest.mark.parametrize("empty", [True, False])
def test_verified_empty_roster_differs_from_unreadable_roster(empty):
    solver = collection_solver()
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.enter_room = Mock()
    solver.find = Mock(
        side_effect=lambda name, **kwargs: (
            name == "room_detail" or (empty and name == "infra_no_operator")
        )
    )
    solver.get_color = Mock(return_value=np.array([255, 255, 255]))
    solver.read_screen = Mock(return_value="")
    solver.detect_room = Mock(return_value="recycle")
    result = BaseSchedulerSolver._read_recycling_operators(solver)
    assert result == ([] if empty else None)


def test_roster_leaves_conversion_dashboard_before_reading():
    solver = collection_solver()
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.enter_room = Mock()
    solver.detect_room = Mock(return_value="recycle")
    solver.back = Mock()
    dashboard = iter([True, False])
    solver.find = Mock(
        side_effect=lambda name, **kwargs: (
            next(dashboard) if name == "recycle/dashboard" else name == "room_detail"
        )
    )
    solver.get_color = Mock(return_value=np.array([255, 255, 255]))
    solver.read_screen = Mock(side_effect=["旅骨", "阿米娅"])
    assert BaseSchedulerSolver._read_recycling_operators(solver) == ["旅骨", "阿米娅"]
    solver.back.assert_called_once()


def test_archived_occupants_complete_collection_without_toggling_panel(db, monkeypatch):
    solver = collection_solver()
    del solver._read_recycling_operators
    path = Path(__file__).parent / "fixtures/recycling/occupants_20261012.jpg"
    solver.recog = Recognizer(Mock(), path.read_bytes())
    solver.enter_room = Mock()
    solver.scene = Mock(return_value=Scene.INFRA_MAIN)
    solver._recycling_pending = {"id": "archived-occupants"}
    monkeypatch.setattr(
        recycling, "read_recycling_materials", Mock(return_value={"装置": 1})
    )

    solver._finish_recycling_collection()

    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["records"][0]["operators"] == ["旅骨", "岳羽由加莉"]
    solver.enter_room.assert_called_once_with("recycle", max_attempts=1)
    solver.tap.assert_not_called()
    assert solver._recycling_pending is None


@pytest.mark.parametrize("settles", [True, False])
def test_roster_waits_for_opening_panel_and_checks_last_frame(settles):
    solver = collection_solver()
    solver.enter_room = Mock()
    solver.detect_room = Mock(return_value="recycle")
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    state = {"opened": False, "waits": 0}
    solver.find = Mock(
        side_effect=lambda name, **kwargs: (
            (name == "room_detail" and state["opened"]) or name == "arrange_check_in"
        )
    )
    solver.get_color = Mock(
        side_effect=lambda pos: np.array(
            [255 if settles and state["waits"] == 4 else 10] * 3
        )
    )
    solver.tap.side_effect = lambda *args, **kwargs: state.update(opened=True)
    solver.sleep.side_effect = lambda *args: state.update(waits=state["waits"] + 1)
    solver.read_screen = Mock(side_effect=["旅骨", "岳羽由加莉"])

    result = BaseSchedulerSolver._read_recycling_operators(solver)

    assert result == (["旅骨", "岳羽由加莉"] if settles else None)
    assert solver.read_screen.call_count == (2 if settles else 0)
    solver.tap.assert_called_once()
    assert state["waits"] == 4


@pytest.mark.parametrize("ready", [True, False])
def test_direct_collection_requires_ready_marker(monkeypatch, ready):
    from arknights_mower.solvers import base_schedule

    solver = collection_solver()
    solver.find = Mock(return_value=((200, 100), (300, 150)))
    solver._tap_recycling_collection = Mock(return_value=True)
    monkeypatch.setattr(
        base_schedule.segment,
        "base",
        Mock(
            return_value={
                "recycle": [(1000, 700), (1000, 800), (1200, 800), (1200, 700)]
            }
        ),
    )
    if ready:
        solver.recog.img[690:750, 1160:1210] = [0, 220, 220]
    assert solver.collect_recycling() is ready
    assert solver._tap_recycling_collection.call_count == int(ready)


def test_todo_material_popup_stops_other_collection_inputs(monkeypatch):
    solver = collection_solver()
    solver.last_execution = {"todo": None}
    solver.find = Mock(side_effect=[None, None, None, (350, 1030)])
    solver._tap_recycling_collection = Mock(return_value=True)
    solver.todo_list()
    solver._tap_recycling_collection.assert_called_once_with((350, 1030))
    solver.tap.assert_not_called()


def test_material_route_validates_and_requires_token(db, monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "recycling-test", raising=False)
    client = server.app.test_client()
    assert client.get("/report/recycling_history").status_code == 403
    for query in [
        "page=x",
        "pageSize=201",
        "startDate=invalid",
        "startDate=2026-10-12&endDate=2026-10-10",
    ]:
        assert (
            client.get(
                "/report/recycling_history?" + query,
                headers={"token": "recycling-test"},
            ).status_code
            == 400
        )
    response = client.get(
        "/report/recycling_history", headers={"token": "recycling-test"}
    )
    assert response.status_code == 200
    assert response.json["total"] == 0


def workbook_rows(workbook, sheet):
    with ZipFile(workbook) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = [
        [
            cell.findtext("s:is/s:t", namespaces=namespace)
            if cell.attrib.get("t") == "inlineStr"
            else cell.findtext("s:v", namespaces=namespace)
            for cell in row
        ]
        for row in root.findall("s:sheetData/s:row", namespace)
    ]
    return root, namespace, rows


def test_excel_exports_all_selected_details_and_preserves_unknowns(db):
    for index in range(51):
        record.save_recycling_collection(
            str(index), at(10, 12), ["旅骨", "阿米娅"], {"装置": 2}
        )
    record.save_recycling_collection("unknown", at(10, 13), None, None)
    record.save_recycling_collection("empty", at(10, 14), [], {"装置": 1})
    record.save_recycling_collection("outside", at(11), [], {"装置": 100})
    with record.export_recycling_history("2026-10-10", "2026-10-10") as workbook:
        root, namespace, details = workbook_rows(workbook, 2)
        assert len(details) == 54
        assert details[1][1:4] == ["无人进驻", "装置", "1"]
        assert details[2][1:4] == ["未识别", "未完整识别", "未知"]
        assert details[3][0] == "2026-10-10 12:00:00"
        assert details[3][1:4] == ["旅骨、阿米娅", "装置", "2"]
        assert (
            root.find("s:sheetViews/s:sheetView/s:pane", namespace).attrib["state"]
            == "frozen"
        )
        assert root.find("s:autoFilter", namespace).attrib["ref"] == "A1:E54"
        _, _, totals = workbook_rows(workbook, 3)
        assert totals[1] == ["装置", "绿色材料", "103"]
        _, _, overview = workbook_rows(workbook, 1)
        metrics = {row[0]: row[1] for row in overview[1:]}
        assert metrics["收取次数"] == "53"
        assert metrics["总理智收益"] == "未计算"
        assert metrics["理论期望收益"] == "未计算"
        assert metrics["未完整识别的收取"] == "1"


def test_excel_values_match_report_and_text_never_becomes_formula(db):
    record.save_recycling_collection(
        "a&b", at(10), ["=1+1", "<干员>"], {"装置": 2, "固源岩组": 3}
    )
    report = record.get_recycling_history("2026-10-10", "2026-10-10")
    with record.export_recycling_history("2026-10-10", "2026-10-10") as workbook:
        _, _, overview = workbook_rows(workbook, 1)
        metrics = {row[0]: row[1] for row in overview[1:]}
        assert float(metrics["总理智收益"]) == pytest.approx(
            report["comparison"]["actual_sanity"]
        )
        assert float(metrics["理论期望收益"]) == pytest.approx(
            report["comparison"]["expected_sanity"]
        )
        root, namespace, details = workbook_rows(workbook, 2)
        assert len(details) == 3
        assert details[1][1] == "=1+1、<干员>"
        assert details[1][-1] == "a&b"
        assert not root.findall(".//s:f", namespace)
        quality, namespace, rows = workbook_rows(workbook, 4)
        assert sum(int(row[1]) for row in rows[1:]) == 5
        assert sum(float(row[2]) for row in rows[1:]) == pytest.approx(1)
        assert sum(float(row[3]) for row in rows[1:]) == pytest.approx(1)
        assert (
            quality.find("s:sheetData/s:row[@r='2']/s:c[@r='C2']", namespace).attrib[
                "s"
            ]
            == "3"
        )


def test_excel_download_route_authentication_dates_and_attachment(db, monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "recycling-test", raising=False)
    client = server.app.test_client()
    route = "/report/recycling_history/export"
    assert client.get(route).status_code == 403
    for query in ("startDate=bad", "startDate=2026-10-11&endDate=2026-10-10"):
        assert (
            client.get(
                route + "?" + query, headers={"token": "recycling-test"}
            ).status_code
            == 400
        )
    record.save_recycling_collection("one", at(10), [], {"装置": 1})
    with client.get(
        route + "?startDate=2026-10-10&endDate=2026-10-10&page=2",
        headers={"token": "recycling-test"},
    ) as response:
        assert response.status_code == 200
        assert (
            response.mimetype
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment;" in response.headers["Content-Disposition"]
        assert ".xlsx" in response.headers["Content-Disposition"]
        assert response.data.startswith(b"PK")


@pytest.mark.parametrize(
    "name,count,confidence,reason",
    [
        ("不明物品", "I", 1.0, "材料数量未确认"),
        ("装置", "1", 0.89, "材料数量未确认"),
        ("装置", "I", 1.0, "材料数量未确认"),
    ],
)
def test_rejected_observation_logs_stage_and_ocr_evidence(
    monkeypatch, name, count, confidence, reason
):
    monkeypatch.setattr(
        recycling,
        "_ocr",
        material_ocr_readings(name=name, count=count, count_score=confidence),
    )
    log = Mock()
    monkeypatch.setattr(recycling, "logger", log)
    assert recycling.read_recycling_materials(reward_frame()) is None
    args = log.debug.call_args.args
    assert args[1] == reason
    assert args[2]["name"] == "装置"
    if reason == "材料数量未确认":
        assert args[2]["text"] == count
        assert args[2]["confidence"] == confidence
