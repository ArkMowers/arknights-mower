"""Offline regression tests for generated font coverage and glyph preservation."""

import ast
import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

pytest.importorskip("fontTools")
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from build_font_subsets import ensure_font_characters

ROOT = Path(__file__).resolve().parents[2]


def _font(path, characters, cff=False, width=600):
    builder = FontBuilder(1000, isTTF=not cff)
    names = {ord(char): f"uni{ord(char):04X}" for char in characters}
    order = [".notdef", *names.values()]
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(names)
    glyphs = {}
    for index, name in enumerate(order):
        pen = T2CharStringPen(width, None) if cff else TTGlyphPen(None)
        pen.moveTo((50, 0))
        pen.lineTo((width - 50, 0))
        pen.lineTo((width - 50, 650 + index * 10))
        pen.lineTo((50, 650 + index * 10))
        pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF("TestFont", {}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (width, 50) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "TestFont", "styleName": "Regular"})
    builder.setupOS2(
        sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200
    )
    builder.setupPost()
    builder.save(path)


def _render(path, text):
    font = ImageFont.truetype(str(path), 37)
    image = Image.new("L", (200, 80))
    ImageDraw.Draw(image).text((5, 5), text, font=font, fill=255)
    return font.getlength(text), image.tobytes()


@pytest.mark.parametrize("cff", (False, True))
def test_expansion_preserves_existing_pixels_and_imports_real_glyphs(tmp_path, cff):
    font, source, charset = (
        tmp_path / name for name in ("font.otf", "source.otf", "chars.txt")
    )
    _font(source, "阿旅门骨", cff)
    # CFF rebuilding uses the same source; TTF retains a calibrated existing glyph.
    if cff:
        from fontTools import subset

        with TTFont(source) as initial:
            subsetter = subset.Subsetter()
            subsetter.populate(text="阿")
            subsetter.subset(initial)
            initial.save(font)
    else:
        _font(font, "阿", width=500)
    charset.write_text("阿")
    before = _render(font, "阿")
    source_bytes = source.read_bytes()
    ensure_font_characters(
        "阿旅门骨", font, charset, source, hashlib.sha256(source_bytes).hexdigest()
    )
    assert _render(font, "阿") == before
    for char in "旅门骨":
        assert _render(font, char) == _render(source, char)
    with TTFont(font) as result:
        assert set(map(ord, "阿旅门骨")) <= result.getBestCmap().keys()
    assert source.read_bytes() == source_bytes
    previous = font.read_bytes(), charset.read_bytes()
    ensure_font_characters("阿旅门骨", font, charset, tmp_path / "absent.otf", "unused")
    assert (font.read_bytes(), charset.read_bytes()) == previous


@pytest.mark.parametrize("failure", ("file", "glyph", "fingerprint"))
def test_unavailable_source_keeps_font_and_charset_unchanged(tmp_path, failure):
    font, source, charset = (
        tmp_path / name for name in ("font.ttf", "source.ttf", "chars.txt")
    )
    _font(font, "阿")
    _font(source, "阿" if failure == "glyph" else "阿旅")
    # A stale character list cannot disguise an absent glyph.
    charset.write_text("阿旅")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if failure == "file":
        source.unlink()
    elif failure == "fingerprint":
        digest = "incorrect"
    before = font.read_bytes(), charset.read_bytes()
    with pytest.raises(
        ValueError,
        match={
            "file": "缺少原字体",
            "glyph": "原字体缺字",
            "fingerprint": "指纹不匹配",
        }[failure],
    ):
        ensure_font_characters("阿旅", font, charset, source, digest)
    assert (font.read_bytes(), charset.read_bytes()) == before


def test_existing_glyph_repairs_stale_charset_without_source(tmp_path):
    font, charset = tmp_path / "font.ttf", tmp_path / "chars.txt"
    _font(font, "阿旅")
    charset.write_text("阿")
    before = font.read_bytes()
    ensure_font_characters("旅", font, charset, tmp_path / "absent.ttf", "unused")
    assert font.read_bytes() == before
    assert "旅" in charset.read_text()


def test_room_models_validate_before_loading_font():
    tree = ast.parse((ROOT / "auto_get_res_new.py").read_text())
    names = {
        "训练在房间内的干员名的模型",
        "训练选中的干员名的模型",
        "训练训练室干员名的模型",
    }
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert len(functions) == 3
    for function in functions:
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        validation = next(
            node.lineno
            for node in calls
            if isinstance(node.func, ast.Name) and node.func.id == "校验房间字体字符"
        )
        assert all(
            validation < node.lineno
            for node in calls
            if isinstance(node.func, ast.Attribute) and node.func.attr == "truetype"
        )


def test_mastery_builder_expands_before_rendering(tmp_path, monkeypatch):
    import json

    import build_mastery_panel_model as builder

    font, source, charset = (
        tmp_path / name for name in ("font.ttf", "source.ttf", "chars.txt")
    )
    _font(font, "[阿]技能")
    _font(source, "[阿旅]技能新")
    charset.write_text("[阿]技能")
    monkeypatch.setattr(builder, "DEFAULT_FONT", font)
    monkeypatch.setattr(builder, "DEFAULT_CHARSET", charset)
    monkeypatch.setattr(
        builder,
        "MASTERY_SOURCE_SHA256",
        hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(builder, "source_font", lambda name: source)
    data = tmp_path / "skill_data.json"
    data.write_text(
        json.dumps(
            {
                "characters": {
                    "char_test": {
                        "name": "阿旅",
                        "rarity": 4,
                        "skills": [{"name": "新技能"}],
                    }
                }
            }
        )
    )
    output = tmp_path / "model"
    result = builder.build_default_model(data, output)
    assert result["entries"]["char_test"]["name"] == "阿旅"
    assert output.is_file()


def test_bundled_room_font_covers_reported_new_name_characters(tmp_path):
    with TTFont(ROOT / "arknights_mower/fonts/NotoSansHans-Medium-room.otf") as font:
        assert set(map(ord, "旅门骨")) <= font.getBestCmap().keys()
