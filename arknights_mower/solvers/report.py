from __future__ import annotations

import csv
import os
import datetime

import pandas as pd
import cv2

from ..utils import rapidocr
from ..utils.device import Device

from ..utils.log import logger
from ..utils.path import get_path
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class ReportSolver(BaseSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.template_root = get_path("@app/arknights_mower/resources").__str__()
        self.record_path = get_path("@app/tmp/report.csv")
        self.low_range_gray = (100, 100, 100)
        self.high_range_gray = (255, 255, 255)
        self.date = (datetime.datetime.now() - datetime.timedelta(hours=4)).date().__str__()
        self.report_res = {
            "作战录像": None,
            "赤金": None,
            "龙门币订单": None,
            "龙门币订单数": None,
            "合成玉": None,
            "合成玉订单数量": None,
        }

    def run(self):
        # logger.info(f'目标干员：{priority if priority else "无，高稀有度优先"}')\
        if self.has_record():
            return True

        super().run()

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
            logger.info("RIIC_REPORT")
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
            self.report_res['作战录像'] = \
                rapidocr.engine(img[p2[1]:p1[1], p1[0]:p2[0]], use_det=False, use_cls=False, use_rec=True)[0][0][0]

            p0, p1 = self.locate_report(img, 'riic_iron')
            p2, p3 = self.locate_report(img, 'riic_iron_text')
            self.report_res['赤金'] = \
                rapidocr.engine(img[p2[1]:p1[1], p1[0]:p2[0]], use_det=False, use_cls=False, use_rec=True)[0][0][0]

            p0, p1 = self.locate_report(img, 'riic_iron_order')
            p2, p3 = self.locate_report(img, 'riic_order')
            self.report_res['龙门币订单'] = \
                rapidocr.engine(img[p2[1]:p1[1], p1[0]:p2[0]], use_det=False, use_cls=False, use_rec=True)[0][0][0]
            iron_threshold_gray = cv2.inRange(img[p2[1]:p3[1], p3[0]:img.shape[1] - 40], self.low_range_gray,
                                              self.high_range_gray)
            iron_padded_img = cv2.resize(iron_threshold_gray,
                                         [iron_threshold_gray.shape[0] * 3, iron_threshold_gray.shape[1] * 2])
            self.report_res['龙门币订单数'] = \
                rapidocr.engine(iron_padded_img, use_det=False, use_cls=False, use_rec=True)[0][0][0]

            img = img[p3[1]:img.shape[0], 0:img.shape[1] - 40]
            p0, p1 = self.locate_report(img, 'riic_orundum')
            p2, p3 = self.locate_report(img, 'riic_order')
            self.report_res['合成玉'] = \
                rapidocr.engine(img[p2[1]:p1[1], p1[0]:p2[0]], use_det=False, use_cls=False, use_rec=True)[0][0][0]
            if self.report_res['合成玉'] is None or str(self.report_res['合成玉']).isdigit() is False:
                orundum_padded_img = cv2.resize(img[p2[1]:p1[1], p1[0]:p1[0] + 50],
                                                [img[p2[1]:p1[1], p1[0]:p1[0] + 50].shape[0] * 2,
                                                 img[p2[1]:p1[1], p1[0]:p1[0] + 50].shape[1] * 2])
                self.report_res['合成玉'] = \
                    rapidocr.engine(orundum_padded_img, use_det=False, use_cls=False, use_rec=True)[0][0][0]
            orundum_threshold_gray = cv2.inRange(img[p2[1]:p3[1], p3[0]:img.shape[1] - 40], self.low_range_gray,
                                                 self.high_range_gray)
            orundum_padded_img = cv2.resize(orundum_threshold_gray,
                                            [orundum_threshold_gray.shape[0] * 3, iron_threshold_gray.shape[1] * 2])
            self.report_res['合成玉订单数量'] = \
                rapidocr.engine(orundum_padded_img, use_det=False, use_cls=False, use_rec=True)[0][0][0]

            self.adjust_result()
            self.record_report()
        except:
            logger.info("基报识别失败 润")
        return True

    def locate_report(self, img, template_name):
        try:
            template = cv2.imread("{}/{}.png".format(self.template_root, template_name))
            res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            h, w = template.shape[:-1]
            top_left = max_loc
            logger.debug("{}的max_val:{}".format(template_name, max_val))
            bottom_right = (top_left[0] + w, top_left[1] + h)

            if max_val > 0.8:
                return top_left, bottom_right
            return None
        except:
            logger.error("{}匹配失败".format(template_name))

    def adjust_result(self):
        logger.debug("adjust_report_result{}".format(self.report_res))
        for key in self.report_res:
            if self.report_res[key] == "o" or self.report_res[key] == "O":
                self.report_res[key] = 0
            if str(self.report_res[key]).isdigit() is False:
                self.report_res[key] = None

    def record_report(self):
        logger.debug(f"存入数据{self.report_res}")
        res_df = pd.DataFrame(self.report_res, index=[self.date])
        res_df.to_csv(self.record_path, mode='a', header=not os.path.exists(self.record_path))

    def has_record(self):
        if os.path.exists(self.record_path) is False:
            return False
        df = pd.read_csv(self.record_path)
        for item in df.iloc:
            if item[0] == (datetime.datetime.now() - datetime.timedelta(hours=4)).date().__str__():
                return True
        return False
