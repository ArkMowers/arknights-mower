"""Conservative runtime recognition of training-room names and skills."""

import lzma
import pickle
from typing import NamedTuple

import cv2

from arknights_mower.utils.mastery_panel_model import (
    PIXEL_THRESHOLD,
    skill_roster_digest,
    unpack_template,
)
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
)

MODEL_PATH = "arknights_mower/models/mastery_panel.model"
NAME_MIN_SCORE = 0.70
NAME_MIN_MARGIN = 0.10
NAME_BRACKET_WIDTH = 8
NAME_BRACKET_MIN_SCORE = 0.80
SKILL_MIN_SCORE = 0.70
SKILL_MIN_MARGIN = 0.10
_model = None
_model_loaded = False


class SkillMatch(NamedTuple):
    index: int
    name: str
    name_score: float
    skill_score: float
    margin: float


def _load_model():
    global _model, _model_loaded
    if not _model_loaded:
        _model_loaded = True
        try:
            with lzma.open(resource_pkg_path(MODEL_PATH), "rb") as stream:
                candidate = pickle.load(stream)
            if isinstance(candidate, dict) and candidate.get("schema") == 2:
                for entry in candidate["entries"].values():
                    entry["name_template"] = unpack_template(entry["name_template"])
                    entry["skills"] = [
                        (index, name, unpack_template(template))
                        for index, name, template in entry["skills"]
                    ]
                _model = candidate
        except (
            OSError,
            EOFError,
            ImportError,
            KeyError,
            TypeError,
            ValueError,
            pickle.UnpicklingError,
        ):
            _model = None
    return _model


@register_resource_reload
def reload_mastery_panel_model():
    global _model, _model_loaded
    _model = None
    _model_loaded = False


def _score(region, template):
    if (
        region.size == 0
        or template.size == 0
        or template.shape[0] > region.shape[0]
        or template.shape[1] > region.shape[1]
    ):
        return 0.0
    return float(
        cv2.minMaxLoc(cv2.matchTemplate(region, template, cv2.TM_CCORR_NORMED))[1]
    )


def _name_score(region, template):
    if (
        template.size == 0
        or template.shape[0] > region.shape[0]
        or template.shape[1] > region.shape[1]
    ):
        return 0.0
    response = cv2.matchTemplate(region, template, cv2.TM_CCORR_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(response)
    height, width = template.shape
    # The closing bracket must align at the full-name boundary. A shorter name
    # such as 凯尔希 cannot consume only the prefix of 凯尔希·思衡托.
    boundary = region[y : y + height, x + width - NAME_BRACKET_WIDTH : x + width]
    if _score(boundary, template[:, -NAME_BRACKET_WIDTH:]) < NAME_BRACKET_MIN_SCORE:
        return 0.0
    return float(score)


def recognize_operator(img, data):
    """Match the full bracketed name against the roster, independently of OCR."""
    model = _load_model()
    if not model or model.get("roster_sha256") != skill_roster_digest(data):
        return None
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(img, PIXEL_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
    scores = {}
    for cid, entry in model["entries"].items():
        char = data.get("characters", {}).get(cid, {})
        name = entry["name"]
        if char.get("name") != name or char.get("rarity") not in (4, 5, 6):
            continue
        score = _name_score(
            binary[:, : entry["prefix_width"] + 10], entry["name_template"]
        )
        # Alternate forms share an operator name and do not compete as identities.
        scores[name] = max(scores.get(name, 0.0), score)
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
    name, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if score < NAME_MIN_SCORE or score - runner_up < NAME_MIN_MARGIN:
        return None
    return name


def recognize_skill(img, operator_name, data):
    """Return the confirmed skill match, or None.

    A low score means *unknown*, never proof that the selected skill differs.
    """
    model = _load_model()
    if not model or model.get("roster_sha256") != skill_roster_digest(data):
        return None
    matching_ids = [
        cid
        for cid, char in data.get("characters", {}).items()
        if char.get("rarity") in (4, 5, 6) and char.get("name") == operator_name
    ]
    if not matching_ids:
        return None
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(img, PIXEL_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
    scores = []
    for cid in matching_ids:
        entry = model["entries"].get(cid)
        if entry is None or entry["name"] != operator_name:
            continue
        prefix_width = entry["prefix_width"]
        name_score = _score(binary[:, : prefix_width + 10], entry["name_template"])
        if name_score < NAME_MIN_SCORE:
            continue
        skill_region = binary[:, max(0, prefix_width - 10) :]
        scores.extend(
            (index, name, name_score, _score(skill_region, template))
            for index, name, template in entry["skills"]
        )
    if not scores:
        return None
    scores.sort(key=lambda row: row[3], reverse=True)
    index, name, name_score, score = scores[0]
    runner_up = scores[1][3] if len(scores) > 1 else 0.0
    margin = score - runner_up
    if score < SKILL_MIN_SCORE or margin < SKILL_MIN_MARGIN:
        return None
    return SkillMatch(index, name, name_score, score, margin)
