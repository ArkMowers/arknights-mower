"""加工站共用的归一化页签与导航坐标；坐标以完整游戏画面为基准。"""

FORMULA_TABS = {
    "基建材料": (0.1, 0.18),
    "精英材料": (0.1, 0.31),
    "技巧概要": (0.1, 0.45),
    "芯片": (0.1, 0.57),
    "家具": (0.1, 0.71),
}
CONFIRM_OPERATOR = (0.25, 0.95)
OPEN_FORMULA = (0.45, 0.65)
OPEN_WORKSHOP = (0.1, 0.95)


def scale_point(recognizer, point):
    return point[0] * recognizer.w, point[1] * recognizer.h


def furniture_formula_name(image, name_box):
    """Distinguish same-named furniture recipes by their visible cost header."""
    import cv2

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import rapidocr

    if image.shape != (1080, 1920, 3):
        return None
    left = 1120 if min(point[0] for point in name_box) > 1100 else 376
    top = int(min(point[1] for point in name_box))
    if top < 125 or top + 36 > 1040:
        return None
    values = []
    for start, end in ((left + 50, left + 90), (left + 590, left + 725)):
        region = image[top - 8 : top + 36, start:end]
        result, _ = rapidocr.engine(region, use_det=False, use_cls=False, use_rec=True)
        if result and len(result) == 1:
            text, confidence = result[0]
            if (
                0.9 <= confidence <= 1
                and text.strip().isascii()
                and text.strip().isdecimal()
            ):
                values.append(int(text.strip()))
                continue
        mask = cv2.inRange(region, (180, 180, 180), (255, 255, 255))
        x, y, width, height = cv2.boundingRect(mask)
        if not width or not height:
            return None
        # The game's slashed zero is often read as a Chinese square. Confirm
        # that one glyph against the existing base-number templates instead.
        import numpy as np

        from arknights_mower.models import riic_base_digits

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) != 1:
            return None
        candidate = cv2.resize(mask[y : y + height, x : x + width], (32, 48))
        scores = []
        for digit in range(10):
            template = riic_base_digits[digit]
            tx, ty, tw, th = cv2.boundingRect(template)
            normalized = cv2.resize(template[ty : ty + th, tx : tx + tw], (32, 48))
            scores.append(
                (
                    float(
                        np.mean(
                            np.abs(candidate.astype(float) - normalized.astype(float))
                        )
                    )
                    / 255,
                    digit,
                )
            )
        scores.sort()
        if (
            scores[0][1] != 0
            or scores[0][0] > 0.18
            or scores[1][0] - scores[0][0] < 0.08
        ):
            return None
        values.append(0)
    matches = [
        name
        for name, recipe in workshop_formula.items()
        if name.startswith("家具零件_")
        and recipe["apCost"] == values[0]
        and recipe["goldCost"] == values[1]
    ]
    return matches[0] if len(matches) == 1 else None
