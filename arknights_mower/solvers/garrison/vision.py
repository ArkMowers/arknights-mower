"""卫戍协议画面观察；未知数字、地图和棋子不以默认值补全。"""

import re
from dataclasses import dataclass

import cv2
import numpy as np

from arknights_mower.utils.image import loadres

from .model import GarrisonError


@dataclass(frozen=True)
class Text:
    text: str
    x: int
    y: int
    width: int
    height: int
    score: float = 1.0

    @property
    def center(self):
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass
class Frame:
    image: np.ndarray
    texts: list[Text]
    screen: str
    quick: bool

    def find(self, pattern, region=None):
        return next(
            (
                t
                for t in self.texts
                if t.score >= 0.6
                and re.search(pattern, t.text.replace(" ", ""))
                and (
                    region is None
                    or (
                        region[0] <= t.center[0] < region[2]
                        and region[1] <= t.center[1] < region[3]
                    )
                )
            ),
            None,
        )

    def personal_simulation_selected(self):
        if self.screen != "lobby":
            return False
        label = self.find("^个人模拟$", (1050, 730, 1810, 925))
        if label is None or label.width <= 0 or label.height <= 0:
            return False
        # 两个标签一直可见。以文字框定位左侧选项及其右侧相邻选项的底色。
        x, y, w, h = label.x, label.y, label.width, label.height
        other_x = x + 2 * w
        if other_x + w > self.image.shape[1] or y + h > self.image.shape[0]:
            return False
        personal = self.image[y : y + h, x : x + w]
        other = self.image[y : y + h, other_x : other_x + w]
        # 选中的个人模拟为浅底深字。右侧也为浅色时，无法确认选中态。
        return bool(
            np.mean(personal.min(axis=2) >= 155) > 0.50
            and np.mean(personal.max(axis=2) <= 100) > 0.05
            and np.mean(other.max(axis=2) <= 100) > 0.50
        )


def classify(texts):
    strings = [t.text.replace(" ", "") for t in texts if t.score >= 0.6]

    def has(pattern):
        return any(re.search(pattern, s) for s in strings)

    if has("^效果预览$") and has("^[已己]设置$|^设置主题$"):
        return "theme", False
    quick = has("极速模拟")
    message = "".join(
        t.text.replace(" ", "")
        for t in sorted(texts, key=lambda t: t.x)
        if t.score >= 0.6 and 390 <= t.center[1] <= 560
    )
    if re.fullmatch(r"出现超时异常[，,]?战斗将重新进行[。.]?", message):
        return "battle-timeout", False
    if has("^(?:模拟开放中|模拟中)$") and has("卫[戍成]协议|STRONGHOLD"):
        return "terminal-garrison", False
    if has("入门协议|新手教程|教学指引"):
        return "tutorial", False
    if has("暂时离开模拟"):
        return "leave", quick
    if has("确认准备") and has("剩余资金|未使用|指令"):
        return "confirm-ready", quick
    if has("战术决策|选定后将无法更改"):
        return "choice", quick
    if has("选择策略"):
        return "strategy", quick
    if has("确认本局信息") or has("敌方领袖") and has("核心盟约"):
        return "info", quick
    if has("自选编队"):
        return "squad", quick
    if has("返回主页|模拟结束|模拟成功|模拟失败|模拟胜利|模拟完成|模拟中断"):
        return "result", quick
    if any(
        re.search("特质|技能|天赋", t.text) and 520 <= t.y <= 590 and t.x < 650
        for t in texts
    ):
        return "detail", quick
    if has("休息一下") and has("[准淮]备就绪"):
        return "prep", quick
    if has("开始模拟") and (quick or has("请选择模拟难度")):
        return "mode", quick
    if has("个人模拟") and has("协议数据库|联合模拟|同盟模拟"):
        return "lobby", quick
    if has("回合") and not has("[准淮]备就绪"):
        return "battle", quick
    return "unknown", quick


def deployment_cost_visible(image):
    area = cv2.cvtColor(image[887:978, 1720:1820], cv2.COLOR_RGB2GRAY)
    icon = loadres("garrison/deployment_cost", gray=True)
    return cv2.matchTemplate(area, icon, cv2.TM_CCOEFF_NORMED).max() >= 0.85


class Vision:
    def __init__(self, engine):
        self.engine = engine

    def texts(self, image, region=None, *, scale=1, rec_only=False):
        x, y, width, height = region or (0, 0, image.shape[1], image.shape[0])
        crop = image[y : y + height, x : x + width]
        if crop.size == 0:
            raise GarrisonError("OCR 区域超出画面")
        if scale != 1:
            crop = cv2.resize(
                crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
        # 标准帧为 RGB，OCR 接口的 ndarray 输入为 BGR。
        raw = self.engine(
            cv2.cvtColor(crop, cv2.COLOR_RGB2BGR),
            use_det=not rec_only,
            use_cls=False,
            use_rec=True,
        )
        result = raw[0] if isinstance(raw, tuple) else raw
        items = []
        for item in result or []:
            if len(item) < 3 or not isinstance(item[1], str):
                continue
            points = np.asarray(item[0])
            if points.shape != (4, 2):
                continue
            left, top = points.min(axis=0) / scale
            right, bottom = points.max(axis=0) / scale
            items.append(
                Text(
                    item[1],
                    round(x + left),
                    round(y + top),
                    round(right - left),
                    round(bottom - top),
                    float(item[2]),
                )
            )
        return items

    def frame(self, image):
        if image.shape != (1080, 1920, 3):
            raise GarrisonError("卫戍协议需要 1920×1080 标准画面")
        texts = self.texts(image)
        screen, quick = classify(texts)
        cost_visible = screen == "unknown" and deployment_cost_visible(image)
        if not quick and (
            cost_visible or screen in {"info", "strategy", "prep", "battle"}
        ):
            texts += self.texts(image, (140, 20, 300, 80), scale=2)
            screen, quick = classify(texts)
        if screen == "unknown" and cost_visible:
            screen = "battle"
        return Frame(image, texts, screen, quick)
