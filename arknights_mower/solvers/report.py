from __future__ import annotations

import csv
import os
import datetime

import numpy as np
import pandas as pd
import cv2

from ..utils import rapidocr
from ..utils.device import Device
from ..data import __rootdir__
from ..utils.digit_reader import DigitReader
from ..utils.log import logger
from ..utils.path import get_path
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


def remove_blank(target: str):
    if target is None or target is "":
        return target

    target.strip()
    target.replace(" ", "")
    target.replace("\u3000", "")
    return target


class ReportSolver(BaseSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.record_path = get_path("@app/tmp/report.csv")
        self.low_range_gray = (100, 100, 100)
        self.high_range_gray = (255, 255, 255)
        self.date = (datetime.datetime.now() - datetime.timedelta(hours=4)).date().__str__()
        self.digitReader = DigitReader()
        self.report_res = {
            "作战录像": None,
            "赤金": None,
            "赤金数量": 0,
            "龙门币订单": None,
            "龙门币订单数": None,
            "合成玉": None,
            "合成玉订单数量": None,
        }

    def run(self):
        if self.has_record():
            logger.info("今天的基报看过了")
            return True
        logger.info("康康大基报")
        try:
            super().run()
        except:
            return False
        return True

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_themed_element('index_infrastructure')
        elif self.scene() == Scene.SKIP:
            self.tap_element('skip')
        elif self.scene() == Scene.INFRA_MAIN:
            self.tap_element('control_central')
        elif self.scene() == Scene.CTRLCENTER_ASSISTANT:
            self.tap_element('control_central_assistants')
        elif self.scene() == Scene.RIIC_REPORT:
            logger.info("找到基报了")
            return self.read_report()
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_infrastructure')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')

    def read_report(self):
        try:
            img = cv2.cvtColor(self.recog.img[0:1080, 1280:1920], cv2.COLOR_BGR2RGB)
            p0, p1 = self.locate_report(img, 'riic_exp')
            p2, p3 = self.locate_report(img, 'riic_exp_text')
            self.report_res['作战录像'] = self.digitReader.get_report_number(img[p2[1]:p1[1], p1[0]:p2[0]])

            p0, p1 = self.locate_report(img, 'riic_iron')
            p2, p3 = self.locate_report(img, 'riic_iron_text')
            self.report_res['赤金'] = self.digitReader.get_report_number(img[p2[1]:p1[1], p1[0]:p2[0]])

            p0, p1 = self.locate_report(img, 'riic_iron_order')
            p2, p3 = self.locate_report(img, 'riic_order')
            self.report_res['龙门币订单'] = self.digitReader.get_report_number(img[p2[1]:p1[1], p1[0]:p2[0]])
            self.report_res['龙门币订单数'] = self.digitReader.get_report_number_white(
                img[p2[1]:p3[1], p3[0]:img.shape[1] - 20])

            img = img[p3[1]:img.shape[0], 0:img.shape[1] - 20]
            p0, p1 = self.locate_report(img, 'riic_orundum')
            p2, p3 = self.locate_report(img, 'riic_order')
            self.report_res['合成玉'] = self.digitReader.get_report_number(img[p2[1]:p1[1], p1[0]:p2[0]])
            self.report_res['合成玉订单数量'] = self.digitReader.get_report_number_white(
                img[p2[1]:p3[1], p3[0]:img.shape[1]])

            self.record_report()
        except:
            logger.info("基报识别失败 润")
        return True

    def locate_report(self, img, template_name):
        try:
            template_path = "{}/resources/{}.png".format(__rootdir__, template_name)
            logger.debug("待匹配模板图片{}的路径为{}".format(template_name, template_path))
            template = cv2.imdecode(np.fromfile(template_path.__str__(), dtype=np.uint8), cv2.IMREAD_COLOR)
            logger.debug("待匹配模板图片{}读取成功".format(template_name))
            res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            h, w = template.shape[:-1]
            top_left = max_loc
            logger.debug("{}的max_val:{}".format(template_name, max_val))
            bottom_right = (top_left[0] + w, top_left[1] + h)
            if max_val > 0.7:
                return top_left, bottom_right
            return None
        except:
            logger.error("{}匹配失败".format(template_name))

    def record_report(self):
        logger.info(f"存入{self.date}的数据{self.report_res}")
        res_df = pd.DataFrame(self.report_res, index=[self.date])
        res_df.to_csv(self.record_path, mode='a', header=not os.path.exists(self.record_path), encoding='gbk')

    def has_record(self):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("基报不存在")
                return False
            df = pd.read_csv(self.record_path, encoding='gbk')
            for item in df.iloc:
                if item[0] == self.date:
                    return True
            return False
        except PermissionError:
            logger.info("report.csv正在被占用")
