"""Bundled operator definitions have matching display and recognition resources."""

import json
import lzma
import pickle
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def test_bundled_catalog_has_decodable_avatars_and_skill_icons():
    catalog = json.loads(
        (ROOT / "arknights_mower/data/riic/operators.json").read_text("utf-8")
    )
    icons = set()
    for operator in catalog["operators"]:
        with Image.open(
            ROOT / "ui/public/avatar" / f"{operator['name']}.webp"
        ) as image:
            image.load()
            assert image.format == "WEBP"
            assert image.size == (96, 96)
        icons.update(
            skill["skillIcon"] for slot in operator["skillSlots"] for skill in slot
        )
    for icon in icons:
        with Image.open(ROOT / "ui/public/building_skill" / f"{icon}.webp") as image:
            image.load()
            assert image.format == "WEBP"
            assert image.width > 0 and image.height > 0


def test_bundled_operator_names_are_in_every_name_model():
    names = set(
        json.loads((ROOT / "arknights_mower/data/agent.json").read_text("utf-8"))
    )
    for filename in (
        "operator_room.model",
        "operator_select.model",
        "operator_train.model",
    ):
        with lzma.open(ROOT / "arknights_mower/models" / filename, "rb") as stream:
            model = pickle.load(stream)
        assert names <= model.keys(), (filename, names - model.keys())
