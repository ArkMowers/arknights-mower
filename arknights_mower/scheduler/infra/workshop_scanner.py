from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from arknights_mower.utils import rapidocr
from arknights_mower.scheduler.constants import (
    SCREEN_H,
    SCREEN_W,
    WORKSHOP_FORMULA_SAMPLE_COUNT,
    WORKSHOP_FORMULA_SAMPLE_OFFSET,
    WORKSHOP_FORMULA_SAMPLE_X_STEP,
    WORKSHOP_FORMULA_SCAN_REGION,
    WORKSHOP_FORMULA_VALID_COLOR_HIGH,
    WORKSHOP_FORMULA_VALID_COLOR_LOW,
    WORKSHOP_FURNITURE_FORMULA_KEYS,
    WORKSHOP_FURNITURE_PREFIX,
    WORKSHOP_ITEM_VALID_DISTANCE,
    WORKSHOP_ITEM_VALID_REGION,
    WORKSHOP_ITEM_VALID_TARGET_COLOR,
)


@dataclass(frozen=True)
class FormulaScanItem:
    name: str
    box: list[list[float]]
    valid: bool


def scan_formula_items(recognizer) -> list[FormulaScanItem]:
    from arknights_mower.data import workshop_formula

    img = recognizer.img
    x1, y1, x2, y2 = WORKSHOP_FORMULA_SCAN_REGION
    cropped = img[y1:y2, x1:x2]
    ocr_result = rapidocr.engine(cropped, use_det=True, use_cls=False, use_rec=True)
    rows = ocr_result[0] if ocr_result else []
    result: list[FormulaScanItem] = []
    furniture_start_index = -1
    furniture_idx = 0
    for row in rows:
        if len(row) < 2:
            continue
        text = row[1]
        if text == WORKSHOP_FURNITURE_PREFIX and furniture_start_index == -1:
            furniture_start_index = furniture_idx
        if text not in workshop_formula and text != WORKSHOP_FURNITURE_PREFIX:
            continue
        name = _formula_name(text, furniture_start_index, furniture_idx)
        if name not in workshop_formula:
            continue
        valid = formula_item_valid(cropped, row[0], name)
        if valid is not None:
            box = [[x + x1, y + y1] for x, y in row[0]]
            result.append(FormulaScanItem(name=name, box=box, valid=valid))
        if furniture_idx < len(WORKSHOP_FURNITURE_FORMULA_KEYS) - 1:
            furniture_idx += 1
    return result


def _formula_name(text: str, furniture_start_index: int, furniture_idx: int) -> str:
    if text != WORKSHOP_FURNITURE_PREFIX:
        return text
    if furniture_start_index in range(len(WORKSHOP_FURNITURE_FORMULA_KEYS)):
        return WORKSHOP_FURNITURE_FORMULA_KEYS[furniture_idx]
    return text


def formula_item_valid(img, box, name: str) -> bool | None:
    from arknights_mower.data import workshop_formula

    base_x = int(box[0][0]) + WORKSHOP_FORMULA_SAMPLE_OFFSET[0]
    base_y = int(box[0][1]) + WORKSHOP_FORMULA_SAMPLE_OFFSET[1]
    sample_count = 0
    for idx in range(WORKSHOP_FORMULA_SAMPLE_COUNT):
        px = base_x + idx * WORKSHOP_FORMULA_SAMPLE_X_STEP
        py = base_y
        if not (0 <= py < img.shape[0] and 0 <= px < img.shape[1]):
            continue
        sample_count += 1
        color = img[py, px]
        if not np.all(
            (color >= WORKSHOP_FORMULA_VALID_COLOR_LOW)
            & (color <= WORKSHOP_FORMULA_VALID_COLOR_HIGH)
        ):
            if idx < len(workshop_formula[name]["items"]):
                save_child_inventory_zero(workshop_formula[name]["items"][idx])
            return False
    if sample_count == 0:
        return None
    return True


def save_child_inventory_zero(name: str) -> None:
    from arknights_mower.solvers.record import save_inventory_counts

    save_inventory_counts({name: 0})


def formula_item_center(box) -> tuple[float, float]:
    center_x = ((box[0][0] + box[1][0]) / 2) / SCREEN_W
    center_y = ((box[0][1] + box[2][1]) / 2) / SCREEN_H
    return center_x, center_y


def dashboard_item_valid(recognizer) -> bool:
    img = recognizer.img
    x1r, y1r, x2r, y2r = WORKSHOP_ITEM_VALID_REGION
    region = img[
        int(y1r * SCREEN_H): int(y2r * SCREEN_H),
        int(x1r * SCREEN_W): int(x2r * SCREEN_W),
    ]
    avg_color = np.mean(region.reshape(-1, 3), axis=0)
    distance = np.linalg.norm(avg_color - np.array(WORKSHOP_ITEM_VALID_TARGET_COLOR))
    return bool(distance < WORKSHOP_ITEM_VALID_DISTANCE)


def read_number(recognizer, region: tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = region
    img = recognizer.img[y1:y2, x1:x2]
    ocr_result = rapidocr.engine(img, use_det=True, use_cls=False, use_rec=True)
    text = ocr_result[0][0][1]
    return int(str(text).split("/")[0])
