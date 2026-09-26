"""Offline generator and version fingerprint for training-panel templates."""

import hashlib
import json
import lzma
import pickle
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

FONT_SIZE = 37
PIXEL_THRESHOLD = 200
MIDDLE_DOT_FONT = (
    Path(__file__).resolve().parents[1] / "fonts/NotoSansHans-Medium-room.otf"
)


@lru_cache(maxsize=1)
def _middle_dot_font():
    from PIL import ImageFont

    return ImageFont.truetype(str(MIDDLE_DOT_FONT), FONT_SIZE)


def _game_text_width(text, font):
    if "·" not in text:
        return font.getlength(text)
    dot = _middle_dot_font()
    return sum((dot if char == "·" else font).getlength(char) for char in text)


def skill_roster_digest(data):
    """Hash only fields that affect the panel model, excluding generated timestamps."""
    chars = data.get("characters", {})
    roster = [
        (
            cid,
            char.get("name"),
            char.get("rarity"),
            [s.get("name") for s in char.get("skills", [])],
        )
        for cid, char in sorted(chars.items())
        if char.get("rarity") in (4, 5, 6)
    ]
    encoded = json.dumps(roster, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def render_template(text, font):
    """Render and crop a binary template; called only by the offline generator."""
    from PIL import Image, ImageDraw

    canvas = Image.new("L", (max(200, len(text) * 45 + 20), 80))
    draw = ImageDraw.Draw(canvas)
    if "·" in text:
        # Unity uses NotoSansHans-Medium for this panel. Its middle dot has a
        # narrower advance than SourceHanSansCN, which moves the suffix left.
        x = 10
        dot = _middle_dot_font()
        for char in text:
            glyph_font = dot if char == "·" else font
            draw.text((x, 2), char, font=glyph_font, fill=255)
            x += glyph_font.getlength(char)
    else:
        draw.text((10, 2), text, font=font, fill=255)
    binary = cv2.threshold(np.asarray(canvas), PIXEL_THRESHOLD, 255, cv2.THRESH_BINARY)[
        1
    ]
    x, y, width, height = cv2.boundingRect(binary)
    if not width or not height:
        raise ValueError(f"无法生成训练室文字模板：{text!r}")
    return binary[y : y + height, x : x + width].copy()


def pack_template(image):
    """Store pixels as built-in types, independent of the build NumPy version."""
    height, width = image.shape
    return height, width, image.tobytes()


def unpack_template(packed):
    """Rebuild an image only after the model has been loaded at runtime."""
    height, width, pixels = packed
    if height <= 0 or width <= 0 or len(pixels) != height * width:
        raise ValueError("训练室文字模板尺寸不正确")
    return np.frombuffer(pixels, dtype=np.uint8).reshape(height, width)


def build_model(data, font_path, output_path, charset_path=None):
    """Rebuild all named 4–6 star skills from current skill_data.json."""
    from PIL import ImageFont

    chars = data.get("characters", {})
    text = "".join(
        "["
        + char.get("name", "")
        + "]"
        + "".join(s.get("name") or "" for s in char.get("skills", []))
        for char in chars.values()
        if char.get("rarity") in (4, 5, 6)
    )
    if charset_path is not None:
        available = set(Path(charset_path).read_text(encoding="utf-8"))
        missing = sorted(set(text) - available)
        if missing:
            raise ValueError(
                "训练室字体子集缺字："
                + "".join(missing)
                + "；请从当前游戏字体重新生成子集"
            )
    font_path = Path(font_path)
    font = ImageFont.truetype(str(font_path), FONT_SIZE)
    entries = {}
    for cid, char in sorted(chars.items()):
        if char.get("rarity") not in (4, 5, 6) or not char.get("name"):
            continue
        skills = [
            (index, skill["name"], pack_template(render_template(skill["name"], font)))
            for index, skill in enumerate(char.get("skills", []))
            if skill.get("name")
        ]
        if not skills:
            continue
        name = char["name"]
        entries[cid] = {
            "name": name,
            "prefix_width": round(_game_text_width(f"[{name}]", font)),
            "name_template": pack_template(render_template(f"[{name}]", font)),
            "skills": skills,
        }
    model = {
        "schema": 2,
        "roster_sha256": skill_roster_digest(data),
        "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
        "middle_dot_font_sha256": hashlib.sha256(
            MIDDLE_DOT_FONT.read_bytes()
        ).hexdigest(),
        "font_size": FONT_SIZE,
        "pixel_threshold": PIXEL_THRESHOLD,
        "entries": entries,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with lzma.open(output_path, "wb") as stream:
        pickle.dump(model, stream, protocol=5)
    return model
