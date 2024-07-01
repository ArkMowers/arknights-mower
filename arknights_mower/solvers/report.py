from __future__ import annotations

import datetime
import lzma
import os
import pickle
import time

import cv2
import numpy as np
import pandas as pd

from arknights_mower.data import __rootdir__
from arknights_mower.utils.device import Device
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.email import report_template
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.recognize import Recognizer, Scene
from arknights_mower.utils.vector import va

number = {}
with lzma.open(f"{__rootdir__}/models/report.pkl", "rb") as f:
    number = pickle.load(f)


def remove_blank(target: str):
    if target is None or target == "":
        return target

    target.strip()
    target.replace(" ", "")
    target.replace("\u3000", "")
    return target


class ReportSolver(SceneGraphSolver):
    def __init__(
        self,
        device: Device = None,
        recog: Recognizer = None,
        send_message_config={},
        send_report: bool = False,
    ) -> None:
        super().__init__(device, recog)
        self.record_path = get_path("@app/tmp/report.csv")
        self.low_range_gray = (100, 100, 100)
        self.high_range_gray = (255, 255, 255)
        self.date = (datetime.datetime.now() - datetime.timedelta(hours=4)).date().__str__()
        self.digitReader = DigitReader()
        self.send_message_config = send_message_config
        self.send_report = send_report
        self.report_res = {
            "作战录像": None,
            "赤金": None,
            "龙门币订单": None,
            "龙门币订单数": None,
            "合成玉": None,
            "合成玉订单数量": None,
        }
        self.reload_time = 0

    def run(self):
        if self.has_record():
            logger.info("今天的基报看过了")
            return True
        logger.info("康康大基报捏~")
        try:
            super().run()
            return True
        except Exception as e:
            logger.error(e)
        except Exception:
            pass
        return False

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.RIIC_REPORT:
            return self.read_report()
        elif scene in [Scene.UNKNOWN, Scene.LOADING, Scene.CONNECTING, Scene.RIIC_REPORT_LOADING]:
            self.waiting_solver(scene, sleep_time=1)
        else:
            self.scene_graph_navigation(Scene.RIIC_REPORT)

    def read_report(self):
        if self.find("riic/manufacture"):
            try:
                self.manu_pt = self.find("riic/manufacture")
                self.trade_pt = self.find("riic/trade")
                self.assist_pt = self.find("riic/assistants")

                self.crop_report("iron")
                self.crop_report("exp")
                self.crop_report("iron_order")
                self.crop_report("orundum")
                self.record_report()
            except Exception as e:
                logger.info("基报读取失败:{}".format(e))
            return True
        else:
            if self.reload_time > 3:
                return True
            self.reload_time += 1
            self.csleep(1)
            return

    def record_report(self):
        logger.info(f"存入{self.date}的数据{self.report_res}")
        try:
            res_df = pd.DataFrame(self.report_res, index=[self.date])
            res_df.to_csv(
                self.record_path,
                mode="a",
                header=not os.path.exists(self.record_path),
                encoding="gbk",
            )
        except Exception as e:
            logger.error(f"存入数据失败：{e}")
        if self.send_report:
            self.tap((1253, 81), interval=2)
            try:
                self.send_message(
                    report_template.render(
                        report_data=self.report_res,
                        title_text="基建报告",
                    ),
                    "基建报告",
                    "html",
                    attach_image=self.recog.img,
                )
            except Exception as e:
                logger.error(f"基报邮件发送失败：{e}")
            self.tap((40, 80), interval=2)

    def has_record(self):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("基报不存在")
                return False
            df = pd.read_csv(self.record_path, encoding="gbk", on_bad_lines="skip")
            for item in df.iloc:
                if item[0] == self.date:
                    return True
            return False
        except PermissionError:
            logger.info("report.csv正在被占用")
        except pd.errors.EmptyDataError:
            return False

    def crop_report(self, type: str):
        area = {
            "iron_order": [[self.trade_pt[1][0], self.trade_pt[1][1]], [1920, int(self.assist_pt[0][1] - 50)]],
            "orundum": [[self.trade_pt[1][0], self.trade_pt[1][1] + 45], [1920, int(self.assist_pt[0][1])]],
        }
        if type in ["iron", "exp"]:
            pt_0 = self.find(f"riic/{type}")
            pt_1 = self.find(f"riic/{type}_text")
            scope = [[pt_0[1][0], pt_0[0][1]], [pt_1[0][0], pt_1[1][1]]]
            if type in ["iron"]:
                self.report_res["赤金"] = self.get_number(cropimg(self.recog.gray, scope))
            elif type in ["exp"]:
                self.report_res["作战录像"] = self.get_number(cropimg(self.recog.gray, scope))
        elif type in ["iron_order", "orundum"]:
            logger.debug(f"{type} reading")
            pt_0 = self.find(f"riic/{type}")

            pt_order = []
            res_order = loadres("riic/order", True)
            w, h = res_order.shape
            img = cropimg(self.recog.gray, area[type])
            result = cv2.matchTemplate(img, res_order, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            top_left = va(max_loc, area[type][0])
            print(f"{top_left=} {max_val=}")
            if max_val >= 0.7:
                pt_order = [top_left, va(top_left, (w, h + 5))]
            logger.debug(f"pt_order value:{pt_order} ")
            scope_1 = [[pt_0[1][0], pt_0[0][1]], [pt_order[0][0], pt_0[1][1]]]
            scope_2 = [[pt_order[1][0], pt_order[0][1]], [1900, pt_order[1][1]]]

            if type in ["iron_order"]:
                self.report_res["龙门币订单"] = self.get_number(cropimg(self.recog.gray, scope_1))
                self.report_res["龙门币订单数"] = self.get_number(cropimg(self.recog.gray, scope_2))
            elif type in ["orundum"]:
                self.report_res["合成玉"] = self.get_number(cropimg(self.recog.gray, scope_1))
                self.report_res["合成玉订单数量"] = self.get_number(cropimg(self.recog.gray, scope_2))
        # #return cropimg(recog.gray,area[type])

    def get_number(self, img):
        thres = 100
        img = thres2(img, thres)
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        rect.sort(key=lambda c: c[0])

        value = 0

        for x, y, w, h in rect:
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            digit = cv2.copyMakeBorder(digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
            score = []
            for i in range(10):
                im = number[i]
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                score.append(min_val)
            value = value * 10 + score.index(min(score))
        return value


def get_report_data():
    record_path = get_path("@app/tmp/report.csv")
    try:
        data = {}
        if os.path.exists(record_path) is False:
            logger.debug("基报不存在")
            return False
        df = pd.read_csv(record_path, encoding="gbk")
        data = df.to_dict("dict")
        print(data)
    except PermissionError:
        logger.info("report.csv正在被占用")
