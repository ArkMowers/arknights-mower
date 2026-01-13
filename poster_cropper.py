"""
从明日方舟乐章整页截图中自动检测 & 裁剪海报的小工具（阈值 + 边缘双通道版）。

使用方式：
1. 把乐章节面的整页截图放入 INPUT_DIR；
2. 运行本脚本；
3. 在 OUTPUT_DIR 中得到裁剪好的海报小图；
4. 在 INPUT_DIR/posters_debug 中查看带绿框的大图效果。
"""

import json
from pathlib import Path

import cv2
import numpy as np

# ============ 可配置区域 ============

# 原始大截图所在目录
INPUT_DIR = r"F:\Git\arknights-mower\img"

# 裁剪后海报输出目录
OUTPUT_DIR = r"F:\Git\arknights-mower\img\posters"
METADATA_FILE = Path(r"F:\Git\arknights-mower\arknights_mower\data\stage_order.json")
# 截图的实际分辨率（MuMu12 全屏）
SCREEN_W = 1920
SCREEN_H = 1080

# 乐章海报 roughly 会出现的区域（避免顶部/左侧 UI 干扰）
CONTENT_LEFT = 150
CONTENT_RIGHT = SCREEN_W - 150
CONTENT_TOP = 120
CONTENT_BOTTOM = SCREEN_H - 80

# 面积比例过滤（相对 ROI）
MIN_AREA_RATIO = 0.002  # 小于 0.2% 的轮廓忽略
MAX_AREA_RATIO = 0.45  # 大于 45% 的轮廓忽略

# 宽高比限制
MIN_ASPECT = 0.7  # w / h
MAX_ASPECT = 4.0

# 绝对最小宽高（像素），再小就当成 EP / 头像等噪声
MIN_WIDTH_PX = 180
MIN_HEIGHT_PX = 110

# 内缩与顶部裁剪（避开 NEW / EP 角标）
INNER_MARGIN = 6  # 四周各内缩 6px
TOP_CROP_RATIO = 0.10  # 从顶部再裁掉 10%

# NMS 参数
IOU_THRESHOLD = 0.4  # IoU 超过视为重复
COVER_THRESHOLD = 0.7  # 交集 / 小框面积，大于视为“包含关系”

# 调试图
SAVE_DEBUG = True
DEBUG_DIR = "posters_debug"


# ============ 工具函数 ============
def sort_boxes_by_rows(boxes):
    """
    把海报框按“行”排序：
    1. 先按 y 中心从上到下排；
    2. 近似同一行的归为一组；
    3. 每一行再按 x 中心从左到右排；
    4. 返回排好序的 boxes 列表。
    """
    if not boxes:
        return []

    # 计算每个框的中心和高度
    info = []
    for b in boxes:
        x1, y1, x2, y2 = b
        h = y2 - y1
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        info.append((b, cx, cy, h))

    # 用高度的中位数估一个“行高”，作为是否同一行的阈值
    heights = [it[3] for it in info]
    median_h = float(np.median(heights)) if heights else 0.0
    # 同一行的 y 中心差异不应太大，这里取 0.6 * 行高 做阈值
    row_thresh = median_h * 0.6 if median_h > 0 else 50.0

    # 先按 y 中心从上到下排
    info.sort(key=lambda it: it[2])

    rows = []  # 每个元素是 {"cy_ref": float, "items": [(box, cx), ...]}
    for b, cx, cy, h in info:
        if not rows:
            rows.append({"cy_ref": cy, "items": [(b, cx)]})
        else:
            # 如果和上一行参考中心的差距很小，就视为同一行
            if abs(cy - rows[-1]["cy_ref"]) <= row_thresh:
                rows[-1]["items"].append((b, cx))
                # 更新这一行的参考 y（取平均会稍微稳一点）
                rows[-1]["cy_ref"] = (
                    rows[-1]["cy_ref"] * (len(rows[-1]["items"]) - 1) + cy
                ) / len(rows[-1]["items"])
            else:
                # 开一行新行
                rows.append({"cy_ref": cy, "items": [(b, cx)]})

    # 每一行内部从左到右排，然后按行拼起来
    ordered = []
    for row in rows:
        row["items"].sort(key=lambda it: it[1])  # 按 cx
        ordered.extend([it[0] for it in row["items"]])

    return ordered


def slugify(name: str) -> str:
    """把文件名里不能用的字符替掉，防止 Windows 报错。"""
    invalid = '\\/:*?"<>|'
    for ch in invalid:
        name = name.replace(ch, "_")
    return name


def parse_year_from_filename(path: Path) -> int:
    """
    从整页截图文件名解析 year。
    你说「sortByYear = filename」，所以默认直接把 stem 当整数。
    比如  '1.png' → 1
          '01.png' → 1
    """
    stem = path.stem
    return int(stem)  # 如果你文件名不是纯数字，这里再改一下逻辑


def load_meta_by_year(meta_file: str | Path):
    """
    读取 JSON metadata，按 year 分组 & sortWithinYear 降序排好：
    year -> [ {name, sortByYear, sortWithinYear}, ... ]
    """
    p = Path(meta_file)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    meta_by_year: dict[int, list[dict]] = {}
    for item in data:
        year = int(item["sortByYear"])
        meta_by_year.setdefault(year, []).append(item)

    # 同一年内部按 sortWithinYear 降序
    for year, lst in meta_by_year.items():
        lst.sort(key=lambda x: -int(x["sortWithinYear"]))

    return meta_by_year


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def iou(box1, box2) -> float:
    """IoU：交并比。"""
    x11, y11, x12, y12 = box1
    x21, y21, x22, y22 = box2

    xi1 = max(x11, x21)
    yi1 = max(y11, y21)
    xi2 = min(x12, x22)
    yi2 = min(y12, y22)

    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0

    inter = (xi2 - xi1) * (yi2 - yi1)
    area1 = (x12 - x11) * (y12 - y11)
    area2 = (x22 - x21) * (y22 - y21)

    union = area1 + area2 - inter
    if union <= 0:
        return 0.0
    return inter / union


def cover_ratio(box1, box2) -> float:
    """交集 / 小框面积，用来判断“小框被大框基本包住”的情况。"""
    x11, y11, x12, y12 = box1
    x21, y21, x22, y22 = box2

    xi1 = max(x11, x21)
    yi1 = max(y11, y21)
    xi2 = min(x12, x22)
    yi2 = min(y12, y22)

    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0

    inter = (xi2 - xi1) * (yi2 - yi1)
    area1 = (x12 - x11) * (y12 - y11)
    area2 = (x22 - x21) * (y22 - y21)
    small = min(area1, area2)

    if small <= 0:
        return 0.0
    return inter / small


def nms(boxes, iou_thresh=IOU_THRESHOLD, cover_thresh=COVER_THRESHOLD):
    """
    非极大值抑制：
    - 按面积从大到小排序，大的优先；
    - IoU 大了 / 小框被几乎完全包含时，丢掉小框。
    """
    if not boxes:
        return []

    boxes = sorted(
        boxes,
        key=lambda b: (b[2] - b[0]) * (b[3] - b[1]),
        reverse=True,
    )
    kept = []

    for b in boxes:
        if not kept:
            kept.append(b)
            continue

        ok = True
        for kb in kept:
            if iou(b, kb) > iou_thresh:
                ok = False
                break
            if cover_ratio(b, kb) > cover_thresh:
                ok = False
                break

        if ok:
            kept.append(b)

    return kept


def add_box_if_valid(
    boxes,
    x,
    y,
    w2,
    h2,
    roi_area,
    x_offset,
    y_offset,
):
    """
    通用矩形过滤入口：
    - 尺寸、面积比、宽高比过滤；
    - 满足条件则映射到全图坐标后加入 boxes。
    """
    if w2 <= 0 or h2 <= 0:
        return

    # 绝对尺寸过滤
    if w2 < MIN_WIDTH_PX or h2 < MIN_HEIGHT_PX:
        return

    area = w2 * h2
    ratio = area / roi_area
    if ratio < MIN_AREA_RATIO or ratio > MAX_AREA_RATIO:
        return

    aspect = w2 / h2
    if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
        return

    gx1 = x_offset + x
    gy1 = y_offset + y
    gx2 = gx1 + w2
    gy2 = gy1 + h2
    boxes.append((gx1, gy1, gx2, gy2))


# ============ 主逻辑 ============


def crop_posters_from_file(path: Path, out_dir: Path, meta_by_year) -> None:
    img = cv2.imread(str(path))
    if img is None:
        print(f"[WARN] cannot read {path}")
        return

    h, w = img.shape[:2]
    if (w, h) != (SCREEN_W, SCREEN_H):
        print(
            f"[WARN] {path.name} resolution {w}x{h}, expected {SCREEN_W}x{SCREEN_H}，按实际尺寸继续处理"
        )

    try:
        year = parse_year_from_filename(path)
    except ValueError:
        print(f"[WARN] 无法从文件名解析 year: {path.name}，该图使用默认命名")
        year = None

    meta_list = meta_by_year.get(year, []) if year is not None else []

    # 1. 取中间内容区域 ROI
    x0, y0, x1, y1 = CONTENT_LEFT, CONTENT_TOP, CONTENT_RIGHT, CONTENT_BOTTOM
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(w, x1)
    y1 = min(h, y1)
    roi = img[y0:y1, x0:x1]

    roi_h, roi_w = roi.shape[:2]
    roi_area = roi_h * roi_w

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    raw_boxes = []

    # === 通道 1：阈值 + 闭运算 ===
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_close, iterations=1)

    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.dilate(closed, kernel_dilate, iterations=1)

    contours1, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours1:
        x, y, w2, h2 = cv2.boundingRect(cnt)
        add_box_if_valid(raw_boxes, x, y, w2, h2, roi_area, x0, y0)

    # === 通道 2：Canny 边缘 + 膨胀 ===
    edges = cv2.Canny(blur, 50, 150)
    kernel_edge = np.ones((5, 5), np.uint8)
    edges_dilated = cv2.dilate(edges, kernel_edge, iterations=2)

    contours2, _ = cv2.findContours(
        edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    for cnt in contours2:
        x, y, w2, h2 = cv2.boundingRect(cnt)
        add_box_if_valid(raw_boxes, x, y, w2, h2, roi_area, x0, y0)

    # 2. NMS 去重
    boxes = nms(raw_boxes, IOU_THRESHOLD, COVER_THRESHOLD)

    # 再按从上到下、左到右排序
    boxes = sort_boxes_by_rows(boxes)

    base = path.stem
    saved = 0

    for idx, (gx1, gy1, gx2, gy2) in enumerate(boxes, start=1):
        # 内缩边缘
        gx1 += INNER_MARGIN
        gy1 += INNER_MARGIN
        gx2 -= INNER_MARGIN
        gy2 -= INNER_MARGIN
        # 再在绿色框的基础上：
        # 顶部再往下剪 75px（去掉 NEW）
        gy1 += 75

        # 右边再往左收 50px（防止右侧超出）
        gx2 -= 50
        # 顶部再裁掉一截
        box_h = gy2 - gy1
        gy1 += int(box_h * TOP_CROP_RATIO)

        gx1 = max(0, gx1)
        gy1 = max(0, gy1)
        gx2 = min(w, gx2)
        gy2 = min(h, gy2)
        if gx2 <= gx1 or gy2 <= gy1:
            continue

        crop = img[gy1:gy2, gx1:gx2]
        if 0 <= (idx - 1) < len(meta_list):
            poster_name_raw = str(meta_list[idx - 1]["name"])
            poster_name = slugify(poster_name_raw)
            out_name = f"{poster_name}.png"
        else:
            # 没有 metadata 或数量对不上时，退回原来的命名
            out_name = f"{base}_p{idx}.png"

        out_path = out_dir / out_name

        # 用 OpenCV 把图像编码成 PNG 的二进制
        success, encoded = cv2.imencode(".png", crop)
        if not success:
            print(f"[WARN] failed to encode image {out_name}")
        else:
            # 用 Python 自己写文件名（支持完整 Unicode，不会乱码）
            out_path.write_bytes(encoded.tobytes())
        saved += 1

    # 3. 保存调试图
    if SAVE_DEBUG:
        debug_dir = Path(INPUT_DIR) / DEBUG_DIR
        ensure_dir(debug_dir)
        dbg = img.copy()
        for gx1, gy1, gx2, gy2 in boxes:
            cv2.rectangle(dbg, (gx1, gy1), (gx2, gy2), (0, 255, 0), 2)
        cv2.imwrite(str(debug_dir / f"{base}_debug.png"), dbg)

    print(
        f"{path.name}: 原始候选 {len(raw_boxes)} 个，"
        f"NMS 后 {len(boxes)} 个，保存 {saved} 张海报"
    )


def main() -> None:
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    ensure_dir(out_dir)
    meta_by_year = load_meta_by_year(METADATA_FILE)
    files = sorted(list(in_dir.glob("*.png")) + list(in_dir.glob("*.jpg")))
    if not files:
        print(f"在 {in_dir} 里没找到截图文件（png/jpg）")
        return

    for f in files:
        crop_posters_from_file(f, out_dir, meta_by_year)


if __name__ == "__main__":
    main()
