"""Verify the bundled room templates without importing the scheduler or OCR."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import get_args

import pytest
from PIL import Image, ImageFont

import build_room_templates as builder
from arknights_mower.utils.typealias.res import Res

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "arknights_mower"
ROOM = PACKAGE / "resources/room"
GENERATED = {
    "product_gold",
    "product_detail_gold",
    "product_exp3",
    "product_detail_exp3",
    "strategy_locked",
    "station_filter_glyphs",
}


def test_room_png_names_are_registered_for_the_bundled_files():
    room_names = GENERATED | {
        "occupancy_digits",
        "resident_timer_glyphs",
        "strategy_lmd",
        "strategy_orundum",
    }
    names = {"dorm_remove_resident", *(f"room/{name}" for name in room_names)}
    assert names <= set(get_args(Res))
    assert all((PACKAGE / "resources" / f"{name}.png").is_file() for name in names)


def test_bundled_font_subsets_reproduce_gold_menu_item_and_capture_arrows():
    # The public subsets cover 赤金 and 全部. Full coverage uses the original fonts.
    fonts = PACKAGE / "fonts"
    product_font = ImageFont.truetype(str(fonts / "NotoSansHans-Medium-room.otf"), 180)
    templates = builder._product_templates(product_font)
    for name in ("product_gold", "product_detail_gold"):
        with Image.open(ROOM / f"{name}.png") as stored:
            assert templates[name].size == stored.size
            assert templates[name].tobytes() == stored.tobytes()

    filter_font = ImageFont.truetype(
        str(fonts / "SourceHanSansCN-Medium-mastery.ttf"), 22
    )
    atlas = builder._station_filter_atlas(filter_font)
    with Image.open(ROOM / "station_filter_glyphs.png") as stored:
        assert atlas.size == stored.size == (104, 156)
        assert atlas.crop((0, 78, 104, 156)) == stored.crop((0, 78, 104, 156))


@pytest.mark.parametrize("wrong_font", [False, True])
def test_missing_or_wrong_original_font_creates_no_output(
    tmp_path, monkeypatch, wrong_font
):
    monkeypatch.setenv("MOWERFONTS_DIR", str(tmp_path))
    if wrong_font:
        shutil.copyfile(
            PACKAGE / "fonts/NotoSansHans-Medium-room.otf",
            tmp_path / "NotoSansHans-Medium.otf",
        )
    output = tmp_path / "output"
    with pytest.raises(
        ValueError if wrong_font else FileNotFoundError, match="NotoSansHans-Medium"
    ):
        builder.build_room_templates(output, check=False)
    assert not output.exists()


def test_original_fonts_rebuild_six_pngs_without_existing_templates(tmp_path):
    font_dir = builder.source_font("NotoSansHans-Medium.otf").parent.resolve()
    if not os.environ.get("MOWERFONTS_DIR") and not all(
        (font_dir / name).is_file()
        for name in ("NotoSansHans-Medium.otf", "SourceHanSansCN-Medium.ttf")
    ):
        pytest.skip("Set MOWERFONTS_DIR to run the comparison with both original fonts")

    for source in (
        ROOT / "build_room_templates.py",
        ROOT / "build_font_subsets.py",
        builder.FILTER_CAPTURE,
    ):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    command = [sys.executable, str(tmp_path / "build_room_templates.py")]
    env = {**os.environ, "MOWERFONTS_DIR": str(font_dir)}
    output = tmp_path / "rendered"
    subprocess.run(
        [*command, "--output-dir", output], cwd=tmp_path, env=env, check=True
    )
    assert {p.name for p in output.iterdir()} == {f"{name}.png" for name in GENERATED}
    for path in output.iterdir():
        with Image.open(path) as rendered, Image.open(ROOM / path.name) as stored:
            assert rendered.format == stored.format == "PNG"
            assert rendered.mode == stored.mode == "L"
            assert rendered.size == stored.size
            assert rendered.tobytes() == stored.tobytes(), path.name

    subprocess.run([*command, "--check", output], cwd=tmp_path, env=env, check=True)
    path = output / "strategy_locked.png"
    with Image.open(path) as stored:
        damaged = stored.copy()
    damaged.putpixel((0, 0), 255 - damaged.getpixel((0, 0)))
    damaged.save(path)
    before = path.read_bytes()
    result = subprocess.run(
        [*command, "--check", output], cwd=tmp_path, env=env, capture_output=True
    )
    assert result.returncode != 0 and b"strategy_locked.png" in result.stderr
    assert path.read_bytes() == before
