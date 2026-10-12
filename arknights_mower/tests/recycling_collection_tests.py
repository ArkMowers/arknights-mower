"""Offline recycling evidence, probability model and collection boundaries."""

import sqlite3
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import record
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import recycling
from arknights_mower.utils.scene import Scene


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
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(text_score=0.3)


def reward_frame():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = cv2.imread(str(Path(__file__).parent / "fixtures/recycling/device.png"))
    image[415:705, 820:1100] = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return image


def test_supplied_device_reward_name_icon_and_quantity(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


def test_multiple_rewards_require_every_label(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = reward_frame()[415:705, 820:1100]
    image[415:705, 640:920] = crop
    image[415:705, 1000:1280] = crop
    assert recycling.read_recycling_materials(image) == {"装置": 2}
    image[640:705, 1000:1280] = 0
    assert recycling.read_recycling_materials(image) is None


def test_wrong_icon_does_not_confirm_ocr_name(real_ocr, monkeypatch):
    monkeypatch.setattr(recycling.rapidocr, "engine", real_ocr)
    image = reward_frame()
    image[415:570] = 0
    assert recycling.read_recycling_materials(image) is None


def test_unknown_name_and_inexact_quantity_reject(monkeypatch):
    box = [[925, 12], [997, 12], [997, 48], [925, 48]]
    monkeypatch.setattr(recycling, "_ocr", Mock(return_value=[(box, "不明物品", 1)]))
    assert recycling.read_recycling_materials(reward_frame()) is None
    monkeypatch.setattr(
        recycling, "_ocr", Mock(side_effect=[[(box, "装置", 1)], [(box, "1.2万", 1)]])
    )
    assert recycling.read_recycling_materials(reward_frame()) is None


def collection_solver():
    solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    solver.recog = SimpleNamespace(
        img=np.zeros((1080, 1920, 3), dtype=np.uint8), save_screencap=Mock()
    )
    solver.tap = Mock()
    solver.sleep = Mock()
    solver.scene_graph_navigation = Mock()
    solver._read_recycling_operators = Mock(return_value=["旅骨"])
    return solver


def test_popup_retry_records_once_before_dismissal_and_reads_actual_staff(
    db, monkeypatch
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
    solver._finish_recycling_collection()
    assert solver._recycling_pending is None
    result = record.get_recycling_history("2000-01-01", "2100-01-01")
    assert result["total"] == 1
    assert result["records"][0]["operators"] == ["旅骨"]
    assert result["materials"][0]["count"] == 1


def test_archived_borderline_quantity_is_recorded_after_two_matching_frames(
    db, real_ocr, monkeypatch
):
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
    solver.sleep.assert_called_once_with(0.3)
    solver.recog.save_screencap.assert_not_called()


@pytest.mark.parametrize(
    "name_score,count_score,icon_score,expected",
    [
        (0.90, 0.90, 0.95, {"装置": 1}),
        (0.89, 1.0, 1.0, None),
        (1.0, 0.89, 1.0, None),
        (1.0, 1.0, 0.94, None),
    ],
)
def test_relaxed_confidence_requires_name_icon_and_quantity(
    monkeypatch, name_score, count_score, icon_score, expected
):
    box = [[925, 12], [997, 12], [997, 48], [925, 48]]
    monkeypatch.setattr(
        recycling,
        "_ocr",
        Mock(side_effect=[[(box, "装置", name_score)], [(box, "1", count_score)]]),
    )
    monkeypatch.setattr(
        recycling.cv2, "minMaxLoc", Mock(return_value=(0.0, icon_score, (0, 0), (0, 0)))
    )
    assert recycling.read_recycling_materials(reward_frame()) == expected


def test_other_material_sources_are_not_recorded():
    solver = collection_solver()
    solver.scene = Mock(return_value=Scene.MATERIEL)
    solver.last_room = "room_1_1"
    solver.transition()
    solver._read_recycling_operators.assert_not_called()
    solver.scene_graph_navigation.assert_called_once_with(Scene.INFRA_MAIN)


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
