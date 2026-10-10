import lzma
import pickle
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import cv2
import numpy as np

from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.operation_timing import timed_step
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
)

kernel = np.ones((10, 10), np.uint8)


def estimate_agent_mood(img, scope):
    """绿色笑脸为 24、红色为 0；其余卡片按白条粗估，裁切返回未知。"""
    if (
        not isinstance(img, np.ndarray)
        or img.ndim != 3
        or img.shape[2] != 3
        or scope is None
    ):
        return None
    (left, top), (right, bottom) = scope
    if (
        left < 0
        or top < 28
        or right > img.shape[1]
        or bottom > img.shape[0]
        or not 180 <= right - left <= 210
    ):
        return None
    # 姓名框左侧定位固定的笑脸及白条，避开选中边框和技能图标。
    icon = img[top - 28 : top - 2, left + 16 : left + 43]
    hsv = cv2.cvtColor(icon, cv2.COLOR_RGB2HSV)
    colored = (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 150)
    mood_color = (hsv[:, :, 0] < 85) | (hsv[:, :, 0] > 170)
    if np.count_nonzero(colored & mood_color) < 15:
        return None
    # 只在笑脸圆内分类，避免立绘、技能和选中边框的颜色干扰。
    yy, xx = np.ogrid[:26, :27]
    face = ((xx - 13) ** 2 + (yy - 13) ** 2 <= 11**2) & colored
    hue = hsv[:, :, 0]
    votes = (
        np.count_nonzero(face & ((hue < 10) | (hue > 170))),
        np.count_nonzero(face & (hue >= 16) & (hue < 37)),
        np.count_nonzero(face & (hue >= 37) & (hue < 85)),
    )
    ranked = sorted(votes)
    if ranked[-1] >= 15 and ranked[-1] >= 2 * ranked[-2]:
        if votes[0] == ranked[-1]:
            return 0.0
        if votes[2] == ranked[-1]:
            return 24.0
    bar = img[top - 17 : top - 13, left + 45 : left + 171]
    bright = bar.min(axis=2) > 185
    neutral = np.ptp(bar, axis=2) < 45
    filled = (bright & neutral).mean(axis=0) >= 0.5
    visible = (bar.max(axis=2) > 30).mean(axis=0) >= 0.5
    if visible.mean() < 0.9:
        return None
    # 白条连续地从左向右延伸；不把立绘反光或遮挡当心情。
    indices = np.flatnonzero(filled)
    if indices.size and (indices[0] > 4 or np.any(np.diff(indices) > 3)):
        return None
    # 黄色笑脸未回满，条长误差不能使其被筛成满心情。
    return max(0.1, min(23.9, round(float(filled.mean() * 24), 1)))


def _load_models():
    with lzma.open(
        str(resource_pkg_path("arknights_mower/models/operator_select.model")), "rb"
    ) as f:
        select = pickle.loads(f.read())
    with lzma.open(
        str(resource_pkg_path("arknights_mower/models/operator_train.model")), "rb"
    ) as f:
        train = pickle.loads(f.read())
    if not isinstance(select, dict) or not isinstance(train, dict):
        raise ValueError("干员选择识别模型格式错误")
    return select, train


OP_SELECT, OP_TRAIN = _load_models()


@register_resource_reload
def reload_resource_models() -> None:
    select, train = _load_models()
    OP_SELECT.clear()
    OP_SELECT.update(select)
    OP_TRAIN.clear()
    OP_TRAIN.update(train)
    _match_name_template.cache_clear()


@lru_cache(maxsize=256)
def _match_name_template(train, shape, pixels, *, right_align=False):
    """仅复用完全相同的归一化名字像素；卡片坐标每帧重新分割。"""
    tpl = np.frombuffer(pixels, dtype=np.uint8).reshape(shape)
    max_score = 0
    best_operator = ""
    for operator, template in (OP_TRAIN if train else OP_SELECT).items():
        if train and right_align:
            columns = np.flatnonzero(template.any(axis=0))
            if columns.size:
                # 与归一化姓名相同，文字右侧保留膨胀产生的五像素边距。
                template = np.roll(
                    template, template.shape[1] - columns[-1] - 6, axis=1
                )
        result = cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        if max_val > max_score:
            max_score = max_val
            best_operator = operator
    return best_operator if max_score > 0.6 else ""


@timed_step("names")
def operator_list(img, draw=False, full_scan=True):
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

    right_clipped_name_left = None
    if full_scan and img.shape[1] == 1920 and prev == 0 and start is not None:
        name_left = start + 600
        # 选中边框扩宽姓名条后可能没有结束像素；只接纳右缘少量裁切。
        # 沿用普通卡片的 225 像素宽度和 95% 可见要求，缩小扫描不补尾列。
        if name_left + 203 > 1920 and 1920 - (name_left - 22) >= 225 * 0.95:
            right_clipped_name_left = name_left
            name_x.append((name_left, 1918))

    name_p = []
    for x in name_x:
        for y in name_y:
            name_p.append(tuple(zip(x, y)))

    logger.debug(name_p)

    op_name = []
    # 名字只占两条横带；遮罩分割后的 line1 不可用于名字识别。
    gray_rows = (
        {
            y0: cv2.cvtColor(
                img[y0:y1, 600 : 1920 if full_scan else 1860], cv2.COLOR_RGB2GRAY
            )
            for y0, y1 in name_y
        }
        if name_p
        else {}
    )

    def process_name_region(p):
        (x0, y0), (x1, _) = p
        im = gray_rows[y0][:, x0 - 600 : x1 - 600]
        im = thres2(im, 140)
        im = cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(im, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            # 空白或裁切卡片只保留位置，不阻断同页其他干员的识别。
            return ""
        rect = map(lambda c: cv2.boundingRect(c), contours)
        x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
        if x0 == right_clipped_name_left and x + w >= im.shape[1] - 10:
            # 姓名轮廓触及裁切边界时不能按残字猜身份。
            return ""
        im = im[y : y + h, x : x + w]
        tpl = np.zeros((42, 200), dtype=np.uint8)
        if im.shape[0] > tpl.shape[0] or im.shape[1] > tpl.shape[1]:
            # 异常轮廓不能截断后猜名字，也不能让模板赋值失败拖累整页。
            return ""
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


@timed_step("names")
def operator_list_train(img, draw=False, full_scan=True):
    name_y = ((479, 506), (895, 922))
    name_p_row = [[], []]
    for yi in range(2):
        line1 = cropimg(img, tuple(zip((545, 1920), name_y[yi])))
        hsv = cv2.cvtColor(line1, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (98, 140, 200), (102, 255, 255))
        line1 = cv2.cvtColor(line1, cv2.COLOR_RGB2GRAY)
        line1[mask > 0] = (255,)
        line1 = thres2(line1, 85)

        last_line = line1[0]
        prev = last_line[0]
        front_edge = None
        back_edge = None
        name_x = []

        def color_streak_right(start, length, color):
            """检查从 start 位置开始，向右长度为 length 的像素是否全为color，包括start"""
            end = min(start + length, len(last_line))
            return all(last_line[j] == color for j in range(start, end))

        def color_streak_left(start, length, color):
            """检查从 start 位置开始，向左长度为 length 的像素是否全为color，不包括start"""
            start_idx = max(0, start - length)
            return all(last_line[j] == color for j in range(start_idx, start))

        for i in range(1, line1.shape[1]):
            curr = last_line[i]
            # 当从白色像素变为黑色像素时
            if prev == 255 and curr == 0:
                if color_streak_right(i, 20, 0) and color_streak_left(i, 10, 255):
                    # 若前边缘未记录或当前位置与前边缘距离超过 200 像素，则更新前边缘
                    should_update_front_edge = (
                        front_edge is None or i - front_edge > 200
                    )
                    if should_update_front_edge:
                        front_edge = i
            # 当从黑色像素变为白色像素时
            elif prev == 0 and curr == 255:
                if color_streak_right(i, 10, 255) and color_streak_left(i, 10, 0):
                    # 检查前边缘是否已记录且当前位置与前边缘距离超过 160 像素
                    front_edge_valid = (
                        front_edge is not None and 160 < i - front_edge < 200
                    )
                    # 检查后边缘是否未记录或当前位置与后边缘距离超过 200 像素
                    should_update_back_edge = back_edge is None or i - back_edge > 200

                    if front_edge_valid and should_update_back_edge:
                        back_edge = i
                        # 记录检测到的名称区域
                        name_x.append((back_edge + 543 - 175, back_edge + 543))
            prev = curr

        for x in name_x:
            name_p_row[yi].append(tuple(zip(x, name_y[yi])))

    name_p = []
    max_length = max(len(row) for row in name_p_row)
    for col_index in range(max_length):
        for row in name_p_row:
            if col_index < len(row):
                name_p.append(row[col_index])
    logger.debug(name_p)

    op_name = []
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    def process_name_region(p):
        im = cropimg(gray, p)
        im = thres2(im, 140)
        im = cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        leading = cv2.cvtColor(cropimg(img, p)[:, :12], cv2.COLOR_RGB2HSV)
        yellow = cv2.inRange(leading, (15, 100, 140), (40, 255, 255))
        special_focus = cv2.countNonZero(yellow) >= 12
        if special_focus:
            # 特别关注图案仅在与完整姓名分离时清除，不能沿中点或连字符截断。
            upper = im[: 10 + (p[1][1] - p[0][1]) // 2]
            contours, _ = cv2.findContours(
                cv2.dilate(upper, kernel), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            text_regions = [
                rect
                for contour in contours
                if (rect := cv2.boundingRect(contour))[2] > 30
            ]
            if (
                len(text_regions) == 2
                and min(text_regions, key=lambda rect: rect[0])[2] <= 45
            ):
                im[:, : max(text_regions, key=lambda rect: rect[0])[0]] = 0
        dilation = cv2.dilate(im, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = map(lambda c: cv2.boundingRect(c), contours)
        rect_list = list(rect)
        filtered_rects = [rect for rect in rect_list if len(rect) >= 3 and rect[2] > 30]
        if filtered_rects:
            # 取第一个元素最大的元组
            x, y, w, h = max(filtered_rects, key=lambda rect: rect[0])
        else:
            # 处理没有符合条件元素的情况
            x, y, w, h = 0, 0, 0, 0
        h = h if h <= 42 else 42
        w = w if w <= 200 else 200
        im = im[y : y + h, x : x + w]
        tpl = np.zeros((42, 200), dtype=np.uint8)
        left = tpl.shape[1] - im.shape[1] if special_focus else 0
        tpl[: im.shape[0], left : left + im.shape[1]] = im
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        """cv2.imshow("tpl", tpl)
        cv2.waitKey(0)
        cv2.destroyAllWindows()"""
        return _match_name_template(
            True, tpl.shape, tpl.tobytes(), right_align=special_focus
        )

    with ThreadPoolExecutor() as executor:
        op_name = list(executor.map(process_name_region, name_p))
    logger.debug(op_name)
    """for p in name_p:
        op_name.append(process_name_region(p))
    logger.debug(op_name)"""
    if draw:
        display = img.copy()
        for p in name_p:
            cv2.rectangle(display, p[0], p[1], (255, 0, 0), 3)
        display = cv2.cvtColor(display, cv2.COLOR_RGB2BGR)
        cv2.imwrite("train.png", display)
        scale_percent = 66.67  # 缩放比例
        width = int(display.shape[1] * scale_percent / 100)
        height = int(display.shape[0] * scale_percent / 100)
        dim = (width, height)
        display = cv2.resize(display, dim, interpolation=cv2.INTER_AREA)
        cv2.imshow("Image", display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    logger.debug(tuple(zip(op_name, name_p)))
    return tuple(zip(op_name, name_p))
