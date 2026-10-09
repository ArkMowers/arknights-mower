"""Expand generation-only font subsets from the original game fonts."""

import copy
import hashlib
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROOM_SOURCE_SHA256 = "25033438cfa41f1873d4902b8555956557b765117756bcef96406e023e49578c"
MASTERY_SOURCE_SHA256 = (
    "f09e7abc149f1079ea73ab8dffd31d4f5f9dc30c1d7716d4770f87d84be3b6c9"
)


def source_font(filename):
    return (
        Path(os.environ.get("MOWERFONTS_DIR", ROOT / "ArknightsGameResource/fonts"))
        / filename
    )


def ensure_font_characters(text, font_path, charset_path, source_path, source_sha256):
    """Preserve existing glyphs and fail before writes when source coverage is incomplete."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font_path, charset_path, source_path = map(
        Path, (font_path, charset_path, source_path)
    )
    required = {ord(char) for char in text}
    with TTFont(font_path, recalcTimestamp=False) as current:
        available = current.getBestCmap()
        missing = required - available.keys()
        if not missing:
            recorded = (
                set(charset_path.read_text(encoding="utf-8"))
                if charset_path.exists()
                else set()
            )
            if not set(text) <= recorded:
                charset_path.write_text(
                    "".join(chr(code) for code in sorted(available)) + "\n",
                    encoding="utf-8",
                )
            return
        characters = "".join(chr(code) for code in sorted(missing))
        if not source_path.is_file():
            raise ValueError(f"字体子集缺字：{characters}；缺少原字体 {source_path}")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_sha256:
            raise ValueError(f"原字体指纹不匹配：{source_path}")
        with TTFont(source_path, recalcTimestamp=False) as source:
            source_cmap = source.getBestCmap()
            absent = missing - source_cmap.keys()
            if absent:
                raise ValueError(
                    "原字体缺字：" + "".join(chr(code) for code in sorted(absent))
                )
            if current["head"].unitsPerEm != source["head"].unitsPerEm:
                raise ValueError("原字体与子集字宽单位不一致")
            if "glyf" in current and "glyf" in source:
                # Import only new glyphs; the bundled mastery font has calibrated glyphs.
                imported = {}

                def import_glyph(name):
                    if name in imported:
                        return imported[name]
                    new_name = f"mower_added_{len(imported)}"
                    while new_name in current.getGlyphOrder():
                        new_name += "_"
                    imported[name] = new_name
                    glyph = copy.deepcopy(source["glyf"][name])
                    if glyph.isComposite():
                        for component in glyph.components:
                            component.glyphName = import_glyph(component.glyphName)
                    order = list(current.getGlyphOrder())
                    current["glyf"][new_name] = glyph
                    current["hmtx"][new_name] = source["hmtx"][name]
                    if "vmtx" in current:
                        current["vmtx"][new_name] = source["vmtx"][name]
                    current.setGlyphOrder([*order, new_name])
                    return new_name

                for code in sorted(missing):
                    name = import_glyph(source_cmap[code])
                    for table in current["cmap"].tables:
                        if table.isUnicode() and (
                            code <= 0xFFFF or table.format in (12, 13)
                        ):
                            table.cmap[code] = name
                expanded = current
            elif "CFF " in current and "CFF " in source:
                options = subset.Options()
                options.glyph_names = True
                subsetter = subset.Subsetter(options=options)
                subsetter.populate(unicodes=set(available) | required)
                subsetter.subset(source)
                expanded = source
            else:
                raise ValueError("原字体与子集轮廓格式不一致")
            coverage = expanded.getBestCmap()
            if not (set(available) | required) <= coverage.keys():
                raise ValueError("扩充后的字体字符映射不完整")
            # Stage and verify the font before publishing its matching character list.
            with tempfile.TemporaryDirectory(dir=font_path.parent) as staging:
                staged_font = Path(staging) / font_path.name
                expanded.save(staged_font)
                with TTFont(staged_font) as verified:
                    if not required <= verified.getBestCmap().keys():
                        raise ValueError("保存后的字体缺少所需字符")
                staged_charset = Path(staging) / charset_path.name
                staged_charset.write_text(
                    "".join(chr(code) for code in sorted(coverage)) + "\n",
                    encoding="utf-8",
                )
                staged_font.replace(font_path)
                staged_charset.replace(charset_path)
            print(f"字体子集自动补字（{font_path.name}）：{characters}")
