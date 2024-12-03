from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from arknights_mower.utils.image import loadres
from arknights_mower.utils.path import get_path

from ..solvers.record import save_trading_info
from .email import send_message
from .log import logger


class TradingOrder:
    templates = {
        1000: loadres("price_1000", True),
        1500: loadres("price_1500", True),
        2000: loadres("price_2000", True),
        2500: loadres("price_2500", True),
    }

    def __init__(self):
        self.price = None
        self.buff = None
        self.time = None

    @save_trading_info
    def save(self, img, time=None):
        try:
            self.price = None
            # 手动加入时间为载入历史数据
            self.time = time if time else datetime.now()
            self.buff = "漏单"
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            mask = cv2.inRange(hsv, (0, 0, 200), (180, 100, 255))
            # 判断是否有“可交付”
            if np.count_nonzero(mask[675:700, 550:580]):
                if np.count_nonzero(mask[225:260, 620:655]):
                    self.price = 1000
                    self.buff = "佩佩"
                elif np.count_nonzero(mask[225:260, 570:605]):
                    self.buff = "但书"
                elif np.count_nonzero(mask[725:780, 700:740]):
                    self.price = 2500
                    self.buff = "龙舌兰"
                elif not np.count_nonzero(mask[225:260, 540:560]):
                    self.price = 20
                    self.buff = "源石"
                if self.buff in ["漏单", "但书"]:
                    gray = cv2.cvtColor(img[705:790, 575:735], cv2.COLOR_BGR2GRAY)
                    _, img = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
                    match_results = {}
                    for name, template in self.templates.items():
                        result = cv2.matchTemplate(img, template, cv2.TM_SQDIFF_NORMED)
                        min_val, _, _, _ = cv2.minMaxLoc(result)
                        match_results[name] = min_val
                    best_match = min(match_results, key=match_results.get)
                    logger.debug(f"Best match score:{match_results}")
                    self.price = best_match
                if self.buff == "漏单" and not time:
                    send_message("检测到上一个订单漏单！", level="WARNING")
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
                        self.save(cv2.imread(str(file_path)), dt)
                        count += 1
                    except Exception as e:
                        logger.exception(f"Error processing file {file_path}: {e}")
            return f"分析{count}个订单历史记录完成"
        except Exception as e:
            logger.exception(e)
            return "分析订单历史记录失败，请反馈问题"
