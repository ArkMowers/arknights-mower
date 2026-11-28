"""普通选人 ROI 灰度处理须与改动前整图路径产生相同的模板像素。"""

import hashlib
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest

from arknights_mower.utils import character_recognize as recognition
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger

kernel = recognition.kernel


def _match_name_template(train, shape, pixels):
    return recognition._match_name_template(train, shape, pixels)


# 固定改动前的整图路径作独立对照，不能跟着被测 ROI 实现改写。
def _full_frame_reference(img, draw=False, full_scan=True):
    name_y = ((488, 520), (909, 941))
    line1 = cropimg(img, tuple(zip((600, 1860 if not full_scan else 1920), name_y[0])))
    hsv = cv2.cvtColor(line1, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (98, 140, 200), (102, 255, 255))
    line1 = cv2.cvtColor(line1, cv2.COLOR_RGB2GRAY)
    line1[mask > 0] = (255,)
    line1 = thres2(line1, 140)

    last_line = line1[-1]
    prev = last_line[0]
    start = None
    name_x = []
    for i in range(1, line1.shape[1]):
        curr = last_line[i]
        if prev == 0 and curr == 255 and start and i - start > 186:
            name_x.append((start + 600, i + 598))
        elif prev == 255 and curr == 0:
            start = i
        prev = curr

    name_p = []
    for x in name_x:
        for y in name_y:
            name_p.append(tuple(zip(x, y)))

    logger.debug(name_p)

    op_name = []
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    def process_name_region(p):
        im = cropimg(gray, p)
        im = thres2(im, 140)
        im = cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(im, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = map(lambda c: cv2.boundingRect(c), contours)
        x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
        im = im[y : y + h, x : x + w]
        tpl = np.zeros((42, 200), dtype=np.uint8)
        tpl[: im.shape[0], : im.shape[1]] = im
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        return _match_name_template(False, tpl.shape, tpl.tobytes())

    with ThreadPoolExecutor() as executor:
        op_name = list(executor.map(process_name_region, name_p))
        logger.debug(op_name)

    if draw:
        display = img.copy()
        for p in name_p:
            cv2.rectangle(display, p[0], p[1], (255, 0, 0), 3)
        display = cv2.cvtColor(display, cv2.COLOR_RGB2BGR)
        cv2.imshow("Image", display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return tuple(zip(op_name, name_p))


def name_frame(seed, noncontiguous=False):
    rng = np.random.default_rng(seed)
    storage = np.full((1080, 3840 if noncontiguous else 1920, 3), 255, np.uint8)
    frame = storage[:, ::2] if noncontiguous else storage
    choices = np.array(
        [
            [0, 0, 0],
            [139, 139, 139],
            [140, 140, 140],
            [141, 141, 141],
            [142, 139, 138],
            [138, 141, 142],
            [255, 255, 255],
            [0, 170, 255],
        ],
        dtype=np.uint8,
    )
    for y0, y1 in ((488, 520), (909, 941)):
        frame[y0:y1, 600:] = choices[rng.integers(len(choices), size=(y1 - y0, 1320))]
    frame[519] = 255
    for x in (631, 847, 1063, 1280, 1496, 1712):
        frame[519, x : x + 190] = 0
    return frame


def template_fingerprint(train, shape, pixels):
    assert train is False
    return str(shape) + hashlib.sha256(pixels).hexdigest()


@pytest.mark.parametrize("full_scan", [False, True])
@pytest.mark.parametrize("noncontiguous", [False, True])
@pytest.mark.parametrize("seed", [1, 40, 91])
def test_roi_matches_full_frame_templates_positions_and_does_not_modify_input(
    monkeypatch, full_scan, noncontiguous, seed
):
    monkeypatch.setattr(recognition, "_match_name_template", template_fingerprint)
    frame = name_frame(seed, noncontiguous)
    original = frame.copy()
    expected = _full_frame_reference(frame, full_scan=full_scan)
    actual = recognition.operator_list(frame, full_scan=full_scan)
    assert len(actual) == (12 if full_scan else 10)
    assert actual == expected
    np.testing.assert_array_equal(frame, original)


@pytest.mark.parametrize("full_scan", [False, True])
def test_no_cards_preserves_empty_result(monkeypatch, full_scan):
    frame = np.full((1080, 1920, 3), 255, np.uint8)
    monkeypatch.setattr(recognition, "_match_name_template", template_fingerprint)
    assert recognition.operator_list(frame, full_scan=full_scan) == ()
    assert _full_frame_reference(frame, full_scan=full_scan) == ()


@pytest.mark.parametrize("full_scan", [False, True])
def test_grayscale_conversion_only_reads_the_existing_name_strips(
    monkeypatch, full_scan
):
    frame = name_frame(11)
    converted = []
    convert = cv2.cvtColor

    def record(image, code, *args, **kwargs):
        if code == cv2.COLOR_RGB2GRAY:
            converted.append(image.shape)
        return convert(image, code, *args, **kwargs)

    monkeypatch.setattr(recognition, "_match_name_template", template_fingerprint)
    monkeypatch.setattr(cv2, "cvtColor", record)
    recognition.operator_list(frame, full_scan=full_scan)
    assert converted == [(32, 1320 if full_scan else 1260, 3)] * 3
