import csv
import datetime
import os
import re

import cv2

from arknights_mower.utils import rapidocr
from arknights_mower.utils.device import Device
from arknights_mower.utils.image import cropimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Recognizer, RecognizeError
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver
from arknights_mower.data import __rootdir__
from ..utils.path import get_path


class ReportSolver(BaseSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.low_range_blue = (0, 120, 100)
        self.high_range_blue = (100, 255, 255)
        self.low_range_gray = (100, 100, 100)
        self.high_range_gray = (255, 255, 255)
        self.record_path = get_path('@app/tmp/record.csv')
        # 结算数据
        self.report_res = {
        }
        self.riic_key_str = {
            'riic_date': "日期",

            'riic_exp': "作战录像",
            'riic_iron': "生产赤金价值",
            'riic_iron_number': "生产赤金数量",

            'riic_trade_iron': "贸易站龙门币收入",
            'riic_iron_order': "贸易站赤金订单",

            'riic_trade_orundum': "贸易站合成玉收入",
            'riic_orundum_order': "贸易站合成玉订单",
        }

    def run(self) -> None:
        if self.is_today_recorded():
            return
        try:
            super().run()
        except TypeError:
            logger.error("基报识别失败 润！")

    def is_today_recorded(self) -> bool:
        if os.path.exists(self.record_path) is not True:
            return False
        try:
            now = datetime.datetime.now()
            report_date = now - datetime.timedelta(days=1)

            with open(self.record_path, 'r+') as f:
                csv_reader = csv.reader(f)
                next(csv_reader)
                for line in csv_reader:
                    if len(line) > 0:
                        record_date = datetime.datetime.strptime(line[0], "%m.%d")
                        if record_date.month == report_date.month and record_date.day == report_date.day:
                            return True
            return False
        except RuntimeError:
            logger.error("查询基建报告记录失败")

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_themed_element('index_infrastructure')
        elif self.scene() == Scene.INFRA_MAIN:
            self.tap_element('control_central')
        elif self.scene() == Scene.CTRLCENTER_ASSISTANT:
            self.tap_element('control_central_assistants')
        elif self.scene() == Scene.RIIC_REPORT:
            self.read_report()
            return True
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
        logger.info("读取基建报告")
        # 制造作战记录
        threshold_blue = cv2.inRange(self.recog.img, self.low_range_blue, self.high_range_blue)
        threshold_gray = cv2.inRange(self.recog.img, self.low_range_gray, self.high_range_gray)

        date_res = rapidocr.engine(
            self.recog.img[15:60, 1550:1680],
            use_det=False, use_cls=False, use_rec=True)[0][0][0]
        self.report_res['riic_date'] = re.sub("\D{2}.\D{2}", "", date_res)

        riic_exp = self.find('riic_exp')
        self.report_res['riic_exp'] = rapidocr.engine(
            threshold_blue[riic_exp[0][1]:riic_exp[1][1], riic_exp[1][0]:riic_exp[1][0] + 100],
            use_det=False, use_cls=False, use_rec=True)[0][0][0]
        # 制造赤金
        riic_iron = self.find('riic_lmb')
        self.report_res['riic_iron'] = rapidocr.engine(
            threshold_blue[riic_iron[0][1]:riic_iron[1][1], riic_iron[1][0]:riic_iron[1][0] + 100],
            use_det=False, use_cls=False, use_rec=True)[0][0][0]

        # 贸易赤金
        riic_trade_iron = self.find('riic_lmb_2')
        self.report_res['riic_trade_iron'] = rapidocr.engine(
            threshold_blue[riic_trade_iron[0][1]:riic_trade_iron[1][1],
            riic_trade_iron[1][0]:riic_trade_iron[1][0] + 100],
            use_det=False, use_cls=False, use_rec=True)[0][0][0]

        # 贸易站赤金单数
        iron_threshold_gray = threshold_gray[riic_trade_iron[0][1]:riic_trade_iron[1][1], 1810:1860]
        iron_padded_img = cv2.resize(iron_threshold_gray,
                                     [iron_threshold_gray.shape[0] * 2, iron_threshold_gray.shape[1] * 2])
        self.report_res['riic_iron_order'] = rapidocr.engine(iron_padded_img,
                                                             use_det=False, use_cls=False, use_rec=True)[0][0][0]

        # 贸易站合成玉
        riic_trade_orundum = self.find('riic_orundum')
        self.report_res['riic_trade_orundum'] = rapidocr.engine(
            threshold_blue[riic_trade_orundum[0][1]:riic_trade_orundum[1][1],
            riic_trade_orundum[1][0]:riic_trade_orundum[1][0] + 100],
            use_det=False, use_cls=False,
            use_rec=True)[0][0][0]
        # 贸易站合成玉单数
        orundum_threshold_gray = threshold_gray[riic_trade_orundum[0][1]:riic_trade_orundum[1][1], 1810:1860]
        orundum_padded_img = cv2.resize(orundum_threshold_gray,
                                        [orundum_threshold_gray.shape[0] * 2, orundum_threshold_gray.shape[1] * 2])
        self.report_res['riic_orundum_order'] = rapidocr.engine(orundum_padded_img,
                                                                use_det=False, use_cls=False, use_rec=True)[0][0][0]

        # 整理数据
        for item in self.report_res:
            if self.report_res[item] == 'o' or self.report_res[item] == 'O':
                self.report_res[item] = '0'
            if item != 'riic_date':
                res = re.sub("\D", "", self.report_res[item])
                if str(res).isdigit():
                    self.report_res[item] = res

        self.report_res['riic_iron_number'] = int(int(self.report_res['riic_iron']) / 500)
        self.record_report()

    def record_report(self):
        logger.info(f"存入数据{self.report_res}")
        write_header = True
        if os.path.exists(self.record_path):
            write_header = False
        file = open(self.record_path, 'a+', newline='')

        csv_writer = csv.DictWriter(file, fieldnames=list(self.riic_key_str.keys()))
        if write_header:
            csv_writer.writerow(self.riic_key_str)
        csv_writer.writerow(self.report_res)
        file.close()
