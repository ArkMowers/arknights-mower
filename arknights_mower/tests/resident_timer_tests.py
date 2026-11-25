"""重放进驻干员的原始倒计时，分别核对字模直读、OCR 回退和未知读数。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from PIL import Image

from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import rapidocr, resident_timer

CASES = {
    "full-running": (0, 690),
    "empty-running": (1, 690),
    "last-second": (2, 460),
    "after-last-second": (3, 460),
    "work": (4, 270),
    "half-line": (5, 480),
    "card-edge": (6, 668),
    "subpixel": (7, 690),
    "shaded-fourth": (8, 898),
    "shaded-half": (9, 898),
}


@pytest.fixture(scope="module")
def tiles():
    path = Path(__file__).parent / "fixtures/resident_timers_20261125.png"
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def saved(tiles, name):
    index, y = CASES[name]
    block = tiles[index * 36 : (index + 1) * 36]
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[y : y + 35, 1650:1780] = block[:35, :130]
    return frame, ((1650, y), (1780, y + 35)), block[35:, :, 1]


def ocr_result(text):
    return ([[text, 1.0]], None)


@pytest.mark.parametrize(
    ("name", "value", "mood_pixels"),
    [
        ("full-running", "00:00:24", 310),
        ("empty-running", "10:06:34", 0),
        ("work", "03:01:29", None),
    ],
)
def test_clear_resident_reads_exact_seconds_without_ocr(
    tiles, monkeypatch, name, value, mood_pixels
):
    frame, scope, bar = saved(tiles, name)
    engine = Mock()
    monkeypatch.setattr(rapidocr, "engine", engine)
    reader = BaseMixin()
    if mood_pixels is not None:
        assert round(reader.read_accurate_mood(bar) * 310 / 24) == mood_pixels
    assert reader.read_screen(frame, type="time", cord=scope) == value
    engine.assert_not_called()


@pytest.mark.parametrize(
    ("name", "value", "earlier", "later"),
    [
        ("last-second", "00:00:01", "00:00:00", "00:00:02"),
        ("card-edge", "03:20:27", "03:20:26", "03:20:28"),
        ("shaded-fourth", "03:19:01", "03:19:00", "03:19:02"),
        ("subpixel", "02:07:36", "02:07:35", "02:07:37"),
    ],
)
def test_complete_ocr_value_requires_agreement_on_the_seconds(
    tiles, monkeypatch, name, value, earlier, later
):
    frame, scope, bar = saved(tiles, name)
    if name == "last-second":
        assert BaseMixin().read_accurate_mood(bar) == 24
    engine = Mock(
        side_effect=[ocr_result(reported) for reported in (value, earlier, later)]
    )
    monkeypatch.setattr(rapidocr, "engine", engine)
    reader = BaseMixin()
    assert reader.read_screen(frame, type="time", cord=scope) == value
    for _ in (earlier, later):
        with pytest.raises(ValueError):
            reader._time_seconds(reader.read_screen(frame, type="time", cord=scope))
    assert engine.call_count == 3


@pytest.fixture(scope="module")
def local_ocr():
    return rapidocr.create_engine(0.8, threads=2)


@pytest.mark.parametrize(
    ("filename", "top", "clock"),
    [
        ("selection/room_empty_top_20261020.jpg", 690, "00:05:37"),
        ("selection/room_empty_bottom_20261020.jpg", 460, "00:05:35"),
        ("selection/room_crownslayer_20261103.jpg", 898, "00:19:50"),
        ("clue/clue_reception_residents_20261019.jpg", 270, "08:03:56"),
    ],
)
def test_recorded_jpeg_timer_confirms_exact_ocr_on_first_frame(
    filename, top, clock, local_ocr, monkeypatch
):
    path = Path(__file__).parent / "fixtures" / filename
    with Image.open(path) as image:
        frame = np.array(image.convert("RGB"))
    reader = BaseMixin()
    reader.recog = SimpleNamespace(img=frame, update=Mock())
    scope = ((1650, top), (1780, top + 35))
    monkeypatch.setattr(rapidocr, "engine", local_ocr)
    hours, minutes, seconds = map(int, clock.split(":"))
    assert reader.read_time(scope, None) == hours * 3600 + minutes * 60 + seconds
    reader.recog.update.assert_called_once_with()

    for wrong_second in (seconds - 1, seconds + 1):
        wrong = f"{hours:02}:{minutes:02}:{wrong_second:02}"
        monkeypatch.setattr(rapidocr, "engine", Mock(return_value=ocr_result(wrong)))
        with pytest.raises(ValueError):
            reader._time_seconds(reader.read_screen(frame, type="time", cord=scope))


@pytest.mark.parametrize(
    ("name", "hallucinated"),
    [
        ("half-line", "60:25:00"),
        ("shaded-half", "65:24:20"),
        ("after-last-second", "00:00:00"),
    ],
)
def test_incomplete_or_disappeared_timer_does_not_supply_seconds(
    tiles, monkeypatch, name, hallucinated
):
    frame, scope, _ = saved(tiles, name)
    monkeypatch.setattr(rapidocr, "engine", Mock(return_value=ocr_result(hallucinated)))
    reader = BaseMixin()
    with pytest.raises(ValueError):
        reader._time_seconds(reader.read_screen(frame, type="time", cord=scope))


@pytest.mark.parametrize(
    "damage", ["dot", "digit", "ghost-x", "ghost-y", "blur", "fade"]
)
def test_damaged_clock_rejects_plausible_ocr(tiles, monkeypatch, damage):
    frame, scope, _ = saved(tiles, "empty-running")
    tile = frame[690:725, 1650:1780]
    if damage == "dot":
        tile[:19, 46:51] = tile[0, 0]
    elif damage == "digit":
        tile[:, 107:124] = tile[0, 0]
    elif damage.startswith("ghost"):
        axis = 1 if damage == "ghost-x" else 0
        tile[:] = cv2.addWeighted(tile, 0.7, np.roll(tile, 3, axis=axis), 0.3, 0)
    elif damage == "blur":
        tile[:] = cv2.GaussianBlur(tile, (3, 3), 0)
    else:
        tile[:] = (tile * 0.72).astype(np.uint8)
    monkeypatch.setattr(rapidocr, "engine", Mock(return_value=ocr_result("10:06:34")))
    reader = BaseMixin()
    with pytest.raises(ValueError):
        reader._time_seconds(reader.read_screen(frame, type="time", cord=scope))


@pytest.mark.parametrize("image_kind", ["calibrated", "rgba", "other-dtype"])
def test_unvalidated_image_formats_keep_original_ocr(tiles, monkeypatch, image_kind):
    from arknights_mower.solvers import base_mixin

    glyph = Mock(side_effect=AssertionError("unexpected resident field"))
    monkeypatch.setattr(base_mixin, "read_resident_timer", glyph)
    frame, scope, _ = saved(tiles, "card-edge")
    if image_kind == "calibrated":
        frame[672:707, 1650:1780] = frame[668:703, 1650:1780].copy()
        frame = frame[4:]
    elif image_kind == "rgba":
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2RGBA)
    else:
        frame = frame.astype(np.float32)
    engine = Mock(return_value=ocr_result("03:20:27"))
    monkeypatch.setattr(rapidocr, "engine", engine)
    assert BaseMixin().read_screen(frame, type="time", cord=scope) == "03:20:27"
    engine.assert_called_once()
    glyph.assert_not_called()


def synth_clock(text):
    # 用原始字模拼接未拍到的时刻，独立原图见上面的回放用例。
    path = Path(resident_timer.__rootdir__) / "resources/room/resident_timer_glyphs.png"
    with Image.open(path) as im:
        atlas = np.array(im.convert("L"))
    cells = {c: atlas[:, i * 17 : (i + 1) * 17] for i, c in enumerate("0123456789")}
    cells[":"] = atlas[:, -5:]
    field = np.full((35, 130), 137, dtype=np.uint8)
    field[5:29, 12:124] = np.concatenate([cells[c] for c in text], axis=1)
    return field


@pytest.mark.parametrize(
    ("clock", "seconds"),
    [("00:00:00", 0), ("00:01:00", 60), ("00:00:59", 59), ("12:59:59", 46799)],
)
def test_complete_synthetic_clock_preserves_all_digits(monkeypatch, clock, seconds):
    frame = np.zeros((1080, 1920), dtype=np.uint8)
    frame[270:305, 1650:1780] = synth_clock(clock)
    engine = Mock()
    monkeypatch.setattr(rapidocr, "engine", engine)
    reader = BaseMixin()
    assert (
        reader._time_seconds(
            reader.read_screen(frame, type="time", cord=((1650, 270), (1780, 305)))
        )
        == seconds
    )
    engine.assert_not_called()


@pytest.mark.parametrize("clock", ["00:60:00", "01:00:61"])
def test_both_readers_reject_impossible_clock_digits(monkeypatch, clock):
    frame = np.zeros((1080, 1920), dtype=np.uint8)
    frame[270:305, 1650:1780] = synth_clock(clock)
    monkeypatch.setattr(rapidocr, "engine", Mock(return_value=ocr_result(clock)))
    reader = BaseMixin()
    with pytest.raises(ValueError):
        reader._time_seconds(
            reader.read_screen(frame, type="time", cord=((1650, 270), (1780, 305)))
        )


def test_missing_glyph_asset_uses_original_ocr_on_complete_card(
    tiles, monkeypatch, tmp_path
):
    frame, scope, _ = saved(tiles, "work")
    with monkeypatch.context() as scoped:
        scoped.setattr(resident_timer, "__rootdir__", tmp_path)
        resident_timer._glyphs.cache_clear()
        try:
            engine = Mock(return_value=ocr_result("03.01.29"))
            scoped.setattr(rapidocr, "engine", engine)
            assert BaseMixin().read_screen(frame, type="time", cord=scope) == "03:01:29"
            engine.assert_called_once()
        finally:
            resident_timer._glyphs.cache_clear()


@pytest.mark.parametrize(
    ("type_", "scope", "width"),
    [
        ("time", None, 1920),
        ("time", ((236, 978), (380, 1020)), 1920),
        ("text", ((1650, 270), (1780, 305)), 1920),
        ("time", ((1650, 270), (1780, 305)), 1940),
    ],
    ids=["already-cropped", "mastery-timer", "trust-text", "other-width"],
)
def test_other_fields_keep_their_existing_reader(
    tiles, monkeypatch, type_, scope, width
):
    from arknights_mower.solvers import base_mixin

    frame, _, _ = saved(tiles, "work")
    if width != 1920:
        frame = np.pad(frame, ((0, 0), (0, width - 1920), (0, 0)))
    if scope is None:
        frame = frame[270:305, 1650:1780]
    glyph = Mock(side_effect=AssertionError("unexpected resident field"))
    monkeypatch.setattr(base_mixin, "read_resident_timer", glyph)
    value = "200%" if type_ == "text" else "01:02:03"
    monkeypatch.setattr(rapidocr, "engine", Mock(return_value=ocr_result(value)))
    assert BaseMixin().read_screen(frame, type=type_, cord=scope) == value
    glyph.assert_not_called()


def test_unreadable_frame_can_recover_on_next_capture(tiles, monkeypatch):
    partial, scope, _ = saved(tiles, "half-line")
    healthy, _, _ = saved(tiles, "work")
    healthy[480:515, 1650:1780] = healthy[270:305, 1650:1780]
    reader = BaseMixin()
    images = iter((partial, healthy))
    reader.recog = SimpleNamespace(img=None)
    reader.recog.update = Mock(
        side_effect=lambda: setattr(reader.recog, "img", next(images))
    )
    engine = Mock(return_value=ocr_result("60:25:00"))
    monkeypatch.setattr(rapidocr, "engine", engine)
    assert reader.read_time(scope, None) == 3 * 3600 + 60 + 29
    assert reader.recog.update.call_count == 2
    engine.assert_called_once()
