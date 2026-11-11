from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from arknights_mower.utils.image import loadres
from arknights_mower.utils.path import get_path

from ..solvers.record import save_log, save_trading_info
from .email import send_message
from .log import logger


class TradingOrder:
    templates = {
        1000: loadres("price_1000", True),
        1500: loadres("price_1500", True),
        2000: loadres("price_2000", True),
        2500: loadres("price_2500", True),
        1200: loadres("price_1200", True),
    }

    BUFF_PRICES = {
        "佩佩": 1000,
        "但书": None,
        "可露希尔": 1200,
        "龙舌兰": 2500,
        "源石": 20,
    }
    TAG_BUFFS = ("佩佩", "但书", "可露希尔")
    BUFF_THRESHOLD = 40

    def __init__(self):
        self.price = None
        self.buff = None
        self.time = None

    def get_buff_scores(self, img):
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (0, 0, 200), (180, 100, 255))
        if np.count_nonzero(mask[675:700, 550:580]):
            areas = {
                "佩佩": mask[224:257, 610:640],
                "但书": mask[224:257, 582:608],
                "可露希尔": mask[220:269, 561:581],
                "龙舌兰": mask[741:773, 694:717],
                "源石": mask[755:764, 653:660],
            }
            return {buff: float(np.mean(region)) for buff, region in areas.items()}
        return None

    def has_distinct_buff(self, scores):
        return bool(scores and max(scores.values()) > self.BUFF_THRESHOLD)

    def is_stable(self, prev_scores, curr_scores, threshold=2.5):
        if not (prev_scores and curr_scores):
            return False
        return (
            max(abs(curr_scores[k] - prev_scores[k]) for k in curr_scores) < threshold
        )

    def _match_price(self, img):
        # 标准帧与历史回放均为 RGB
        gray = cv2.cvtColor(img[705:790, 575:735], cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        match_results = {}
        for name, template in self.templates.items():
            result = cv2.matchTemplate(thresh, template, cv2.TM_SQDIFF_NORMED)
            min_val, _, _, _ = cv2.minMaxLoc(result)
            match_results[name] = min_val
        best_match = min(match_results, key=match_results.get)
        logger.debug(f"Best match score:{match_results}")
        return best_match

    @save_trading_info
    def save(self, img, time=None, *, room=None, screenshot_source=None):
        try:
            self.price = None
            # 手动加入时间为载入历史数据
            self.time = time if time else datetime.now()
            self.buff = "漏单"
            scores = self.get_buff_scores(img)
            # 判断是否有“可交付”
            if scores is not None:
                logger.debug(f"亮度均值: {scores}")
                tag_candidates = {
                    k: scores[k]
                    for k in self.TAG_BUFFS
                    if scores.get(k, 0) > self.BUFF_THRESHOLD
                }
                if tag_candidates:
                    best_tag = max(tag_candidates, key=tag_candidates.get)
                    self.buff = best_tag
                    if best_tag == "但书":
                        self.price = self._match_price(img)
                    else:
                        self.price = self.BUFF_PRICES[best_tag]
                elif scores.get("源石", 0) > self.BUFF_THRESHOLD:
                    self.buff = "源石"
                    self.price = self.BUFF_PRICES["源石"]
                else:
                    matched_price = self._match_price(img)
                    # 金额未定格时，龙舌兰订单旁的箭头标记仍可判定类型
                    if (
                        matched_price == self.BUFF_PRICES["龙舌兰"]
                        or scores.get("龙舌兰", 0) > self.BUFF_THRESHOLD
                    ):
                        self.buff = "龙舌兰"
                        self.price = self.BUFF_PRICES["龙舌兰"]
                    else:
                        self.buff = "漏单"
                        self.price = matched_price
                if self.buff == "漏单" and not time:
                    message = (
                        f"检测到上一个订单漏单：{room}。"
                        if room
                        else "检测到上一个订单漏单！"
                    )
                    save_log(message, level="ERROR")
                    if screenshot_source is not None:
                        send_message(
                            message,
                            subject="贸易站漏单提醒",
                            level="WARNING",
                            archive_screenshots=True,
                            screenshot_source=screenshot_source,
                        )
                    else:
                        send_message(message, subject="贸易站漏单提醒", level="WARNING")
                return self
        except Exception as e:
            logger.exception(e)

    def restore_history(self):
        try:
            folder = Path(get_path("@app/screenshot/run_order"))
            count = 0
            for file_path in folder.iterdir():
                if file_path.is_file():
                    try:
                        if len(file_path.name) > 19:
                            dt = datetime.fromtimestamp(
                                int(file_path.name[:-4]) // 1_000_000_000
                            )
                        else:
                            dt = datetime.strptime(file_path.name[:-4], "%Y%m%d%H%M%S")
                        logger.debug(f"截图时间为{dt}")
                        # OpenCV 以 BGR 读取历史截图，先转为标准 RGB 帧
                        img = cv2.imread(str(file_path))
                        self.save(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), dt)
                        count += 1
                    except Exception as e:
                        logger.exception(f"Error processing file {file_path}: {e}")
            return f"分析{count}个订单历史记录完成"
        except Exception as e:
            logger.exception(e)
            return "分析订单历史记录失败，请反馈问题"
