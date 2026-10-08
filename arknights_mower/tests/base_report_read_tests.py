"""Base report readings retain known fields and require successful storage.

Digit templates differ in size. A padded mark can be taller but narrower than
a template, or shorter but wider, which OpenCV rejects. An unscorable digit
leaves its field unread while other fields remain independently available.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from arknights_mower.models import noto_sans  # noqa: E402
from arknights_mower.solvers import report as report_module  # noqa: E402
from arknights_mower.solvers.report import ReportSolver  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.csv_utils import parse_cell_num, read_dicts  # noqa: E402
from arknights_mower.utils.device.recovery import DeviceRecoveryError  # noqa: E402
from arknights_mower.utils.device.touch_backend import TouchFailure  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402

RES = ROOT / "arknights_mower" / "resources"

# Anchor coordinates measured in runtime logs on both passing and failing runs.
ANCHORS = {
    "riic/iron": (1574, 291),
    "riic/trade": (1331, 397),
    "riic/assistants": (1327, 560),
}
GREY = (110, 110, 110)  # Passes the production order-count HSV mask.


@pytest.fixture(autouse=True)
def reset_report_attempts(monkeypatch):
    monkeypatch.setattr(ReportSolver, "attempts", 0)
    monkeypatch.setattr(ReportSolver, "last_attempt_date", None)


@pytest.fixture
def recording_solver(tmp_path, monkeypatch):
    solver = _detached_solver()
    solver.date = "2026-10-02"
    solver.record_path = tmp_path / "report.csv"
    solver.recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), np.uint8))
    solver.tap = Mock()
    solver.add_order_detail = Mock()
    monkeypatch.setattr(report_module, "send_message", Mock())
    return solver


@pytest.fixture(params=[MowerExit, DeviceRecoveryError, TouchFailure])
def control_failure(request):
    if request.param is TouchFailure:
        return TouchFailure(
            SimpleNamespace(touch_backend="adb"),
            "windows",
            RuntimeError("input interrupted"),
            delivery_unknown=True,
            transport="adb",
        )
    return request.param("control interrupted")


class _StubCapture:
    """Feeds one fixed frame to a real Recognizer."""

    def __init__(self, img):
        self.img = img

    def screencap(self):
        from arknights_mower.utils.image import img2bytes

        return (
            img2bytes(self.img),
            self.img.copy(),
            cv2.cvtColor(self.img, cv2.COLOR_RGB2GRAY),
        )


class _StubDevice:
    def __init__(self):
        self.taps = []

    def tap(self, point, interval=0.5):
        self.taps.append(point)


def _report_frame():
    """A blank frame carrying only the report panel anchors."""
    img = np.zeros((1080, 1920, 3), np.uint8)
    for name, (x, y) in ANCHORS.items():
        patch = cv2.imread(str(RES / f"{name}.png"), cv2.IMREAD_COLOR)
        patch = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
        h, w, _ = patch.shape
        img[y : y + h, x : x + w] = patch
    return img


def _detached_solver():
    """A solver with no device or recognizer, for the pure reading helpers."""
    solver = ReportSolver.__new__(ReportSolver)
    solver.report_res = dict.fromkeys(
        ["作战录像", "赤金", "龙门币订单", "龙门币订单数", "合成玉", "合成玉订单数量"]
    )
    solver.reload_time = 0
    solver._stored = False
    return solver


def _solver_for(img):
    solver = ReportSolver.__new__(ReportSolver)
    solver.recog = Recognizer(device=_StubCapture(img))
    solver.recog.start()
    solver.device = _StubDevice()
    solver.report_res = dict.fromkeys(
        ["作战录像", "赤金", "龙门币订单", "龙门币订单数", "合成玉", "合成玉订单数量"]
    )
    return solver


def _order_count_roi(img):
    """The iron order-count ROI crop_report derives from the anchors."""
    solver = _solver_for(img)
    trade_pt = solver.find("riic/trade")
    assist_pt = solver.find("riic/assistants")
    return ((1820, trade_pt[1][1] + 10), (1870, assist_pt[0][1] - 65))


def test_degenerate_contour_does_not_abort_the_whole_read():
    """A 4x4 speck used to raise cv2.error out of crop_report."""
    img = _report_frame()
    (x0, y0), _ = _order_count_roi(img)
    img[y0 + 5 : y0 + 9, x0 + 5 : x0 + 9] = GREY

    solver = _solver_for(img)
    solver.crop_report()  # must not raise

    # The specked field reports no reading; the untouched field still reports
    # its own blank reading, so the two stay distinguishable.
    assert solver.report_res["龙门币订单数"] is None
    assert solver.report_res["合成玉订单数量"] == 0


@pytest.mark.parametrize("w,h", [(1, 1), (2, 2), (4, 4), (6, 6), (40, 1), (1, 40)])
def test_every_degenerate_contour_shape_is_survivable(w, h):
    """Every under-sized stamp must be skipped, never matched."""
    img = _report_frame()
    (x0, y0), _ = _order_count_roi(img)
    img[y0 + 2 : y0 + 2 + h, x0 + 2 : x0 + 2 + w] = GREY

    solver = _solver_for(img)
    solver.crop_report()  # must not raise


def test_unreadable_digit_is_not_zero():
    """Zero stays reserved for a field that is genuinely blank."""
    solver = _detached_solver()

    blank = np.zeros((41, 50), np.uint8)
    assert solver.get_number(blank, ((0, 0), (50, 41)), height=19, thres=200) == 0

    specked = np.zeros((41, 50), np.uint8)
    specked[10:14, 10:14] = 255
    assert solver.get_number(specked, ((0, 0), (50, 41)), height=19, thres=200) is None


@pytest.mark.parametrize("number", range(10))
def test_shipped_digits_keep_their_value(number):
    template = noto_sans[number]
    height, width = template.shape
    solver = _detached_solver()

    assert solver.get_number(template, ((0, 0), (width, height)), height=None) == number


@pytest.mark.parametrize("unusable_digit", [0, 4])
def test_incompatible_template_does_not_discard_usable_scores(
    monkeypatch, unusable_digit
):
    templates = dict(noto_sans)
    templates[unusable_digit] = cv2.copyMakeBorder(
        templates[unusable_digit], 0, 0, 0, 100, cv2.BORDER_CONSTANT
    )
    monkeypatch.setattr(report_module, "noto_sans", templates)
    template = noto_sans[1]
    height, width = template.shape
    solver = _detached_solver()

    assert solver.get_number(template, ((0, 0), (width, height)), height=None) == 1


def test_unscorable_digit_does_not_truncate_a_number():
    image = np.zeros((50, 80), np.uint8)
    template = noto_sans[2]
    height, width = template.shape
    image[5 : 5 + height, 5 : 5 + width] = template
    image[10:14, 50:54] = 255
    solver = _detached_solver()

    assert solver.get_number(image, ((0, 0), (80, 50)), height=None) is None


@pytest.mark.parametrize("scope", [((0, 0), (0, 41)), ((50, 0), (50, 41))])
def test_empty_crop_is_unread(scope):
    solver = _detached_solver()

    assert solver.get_number(np.zeros((41, 50), np.uint8), scope, height=19) is None


@pytest.mark.parametrize("missing_anchor", ANCHORS)
def test_missing_anchor_preserves_independent_fields(missing_anchor):
    solver = _solver_for(_report_frame())
    find = solver.find
    solver.find = lambda name: None if name == missing_anchor else find(name)

    solver.crop_report()

    assert solver.report_res["作战录像"] == 0
    assert solver.report_res["赤金"] == (None if missing_anchor == "riic/iron" else 0)
    for field in ("龙门币订单", "龙门币订单数", "合成玉", "合成玉订单数量"):
        assert solver.report_res[field] == (
            0 if missing_anchor == "riic/iron" else None
        )


def test_report_without_any_reading_is_not_stored(recording_solver):
    """A blank row would mark the day read, so the day must stay retryable."""
    solver = recording_solver

    assert solver.record_report() is False
    assert not solver.record_path.exists()
    assert solver._stored is False
    solver.tap.assert_not_called()
    report_module.send_message.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("龙门币订单", 44500),
        ("龙门币订单数", 29),
        ("合成玉", 100),
        ("合成玉订单数量", 1),
    ],
)
def test_single_read_order_field_is_stored(recording_solver, field, value):
    solver = recording_solver
    solver.report_res[field] = value

    assert solver.record_report() is True

    row = read_dicts(solver.record_path, encoding="gbk")[0]
    assert row["Unnamed: 0"] == solver.date
    for key, expected in solver.report_res.items():
        assert parse_cell_num(row[key]) == expected
    assert solver._stored is True


def test_fully_read_order_fields_are_stored(recording_solver):
    solver = recording_solver
    solver.report_res["龙门币订单"] = 44500
    solver.report_res["龙门币订单数"] = 29
    solver.report_res["合成玉"] = 100
    solver.report_res["合成玉订单数量"] = 1

    assert solver.record_report() is True

    row = read_dicts(solver.record_path, encoding="gbk")[0]
    for key, expected in solver.report_res.items():
        assert parse_cell_num(row[key]) == expected


def test_partial_report_stores_zero_and_unread_independently(recording_solver):
    solver = recording_solver
    solver.report_res["作战录像"] = 42
    solver.report_res["赤金"] = 0

    assert solver.record_report() is True

    row = read_dicts(solver.record_path, encoding="gbk")[0]
    assert row["作战录像"] == "42"
    assert row["赤金"] == "0"
    assert row["龙门币订单数"] == ""


def test_storage_failure_is_retryable_without_panel_input_or_email(
    recording_solver, monkeypatch
):
    solver = recording_solver
    solver.report_res["赤金"] = 17
    append = Mock(side_effect=PermissionError("report.csv is occupied"))
    with monkeypatch.context() as patch:
        patch.setattr("arknights_mower.utils.csv_utils.append_dated_row", append)
        patch.setattr(
            report_module.SceneGraphSolver, "run", lambda self: self.record_report()
        )

        assert solver.run() is False
        assert solver._stored is False
        assert ReportSolver.attempts == 1
        solver.tap.assert_not_called()
        report_module.send_message.assert_not_called()

    assert solver.record_report() is True
    assert solver.has_record() is True


def test_post_storage_error_does_not_unset_success(recording_solver, monkeypatch):
    solver = recording_solver
    solver.report_res["赤金"] = 17
    solver.tap.side_effect = RuntimeError("report panel unavailable")
    monkeypatch.setattr(
        report_module.SceneGraphSolver, "run", lambda self: self.record_report()
    )

    assert solver.run() is True
    assert solver._stored is True
    assert solver.has_record() is True
    assert ReportSolver.attempts == 0


def test_run_propagates_control_failure_without_spending_attempt(
    monkeypatch, control_failure
):
    solver = _detached_solver()
    solver.date = "2026-10-02"
    solver.has_record = lambda: False
    error = control_failure
    monkeypatch.setattr(report_module.SceneGraphSolver, "run", Mock(side_effect=error))

    with pytest.raises(type(error)) as raised:
        solver.run()

    assert raised.value is error
    assert ReportSolver.attempts == 0


def test_read_report_propagates_control_failure(recording_solver, control_failure):
    solver = recording_solver
    solver.report_res["赤金"] = 17
    solver.find = lambda name: True
    solver.crop_report = Mock()
    error = control_failure
    solver.tap.side_effect = error

    with pytest.raises(type(error)) as raised:
        solver.read_report()

    assert raised.value is error
    assert solver._stored is True
    assert solver.reload_time == 0
    assert len(read_dicts(solver.record_path, encoding="gbk")) == 1
    assert solver.tap.call_count == 1


def test_notification_does_not_swallow_control_failure(
    recording_solver, control_failure
):
    solver = recording_solver
    solver.report_res["赤金"] = 17
    error = control_failure
    solver.add_order_detail.side_effect = error

    with pytest.raises(type(error)) as raised:
        solver.record_report()

    assert raised.value is error
    assert solver._stored is True
    assert solver.tap.call_count == 1


def test_read_report_does_not_repeat_storage_after_post_write_error(recording_solver):
    solver = recording_solver
    solver.report_res["赤金"] = 17
    solver.find = lambda name: True
    solver.crop_report = Mock()
    solver.tap.side_effect = RuntimeError("report panel unavailable")

    assert solver.read_report() is True
    assert solver._stored is True
    assert len(read_dicts(solver.record_path, encoding="gbk")) == 1


def test_read_report_stops_retrying_inside_one_run():
    """Solver.run() retries falsy transitions, so the budget must end here."""
    solver = _detached_solver()
    solver.reload_time = ReportSolver.MAX_READ_ATTEMPTS
    # Past the budget, no capture or navigation may happen at all.
    solver.find = lambda res: pytest.fail("budget exhausted, must not search")

    assert solver.read_report() is True


def test_read_report_retries_while_under_budget():
    solver = _detached_solver()
    solver.reload_time = 0
    solver.find = lambda res: None
    solver.sleep = lambda *a, **k: None
    solver.report_res = dict.fromkeys(solver.report_res)

    assert solver.read_report() is False  # panel not loaded yet
    assert solver.reload_time == 1


def test_repeated_failures_stop_retrying_for_this_process():
    """The scheduler owns the outer retry loop, so that budget is bounded too."""
    saved_attempts = ReportSolver.attempts
    saved_date = ReportSolver.last_attempt_date
    try:
        ReportSolver.attempts = ReportSolver.MAX_READ_ATTEMPTS
        ReportSolver.last_attempt_date = "2026-10-02"
        solver = _detached_solver()
        solver.date = "2026-10-02"
        solver.has_record = lambda: False
        assert solver.run() is False  # leaves the day's report unrecorded
    finally:
        ReportSolver.attempts = saved_attempts
        ReportSolver.last_attempt_date = saved_date


def test_new_date_resets_process_attempts(monkeypatch):
    """A new day resets attempts so today's failure does not block tomorrow."""
    saved_attempts = ReportSolver.attempts
    saved_date = ReportSolver.last_attempt_date
    try:
        ReportSolver.attempts = ReportSolver.MAX_READ_ATTEMPTS
        ReportSolver.last_attempt_date = "2026-10-01"
        solver = _detached_solver()
        solver.date = "2026-10-02"
        solver.has_record = lambda: False

        def _fake_super_run():
            solver._stored = True

        monkeypatch.setattr(
            "arknights_mower.utils.graph.SceneGraphSolver.run",
            lambda self: _fake_super_run(),
        )
        assert solver.run() is True
        assert ReportSolver.attempts == 0
        assert ReportSolver.last_attempt_date == "2026-10-02"
    finally:
        ReportSolver.attempts = saved_attempts
        ReportSolver.last_attempt_date = saved_date


def test_successful_read_resets_process_attempts(monkeypatch):
    """A successful storage clears any accumulated attempt count."""
    saved_attempts = ReportSolver.attempts
    saved_date = ReportSolver.last_attempt_date
    try:
        ReportSolver.attempts = 2
        ReportSolver.last_attempt_date = "2026-10-02"
        solver = _detached_solver()
        solver.date = "2026-10-02"
        solver.has_record = lambda: False

        def _fake_super_run():
            solver._stored = True

        monkeypatch.setattr(
            "arknights_mower.utils.graph.SceneGraphSolver.run",
            lambda self: _fake_super_run(),
        )
        assert solver.run() is True
        assert ReportSolver.attempts == 0
    finally:
        ReportSolver.attempts = saved_attempts
        ReportSolver.last_attempt_date = saved_date
