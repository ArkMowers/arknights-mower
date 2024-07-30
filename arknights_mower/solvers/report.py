import datetime
import os

import cv2
import pandas as pd

from arknights_mower.models import noto_sans
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.email import report_template, send_message
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.recognize import Recognizer, Scene, tp


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
    ) -> None:
        super().__init__(device, recog)
        self.record_path = get_path("@app/tmp/report.csv")
        self.low_range_gray = (100, 100, 100)
        self.high_range_gray = (255, 255, 255)
        self.date = (
            (datetime.datetime.now() - datetime.timedelta(hours=4)).date().__str__()
        )
        self.digitReader = DigitReader()
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
            logger.exception(e)
        return False

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.RIIC_REPORT:
            return self.read_report()
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.RIIC_REPORT)

    def read_report(self):
        if self.find("riic/manufacture"):
            try:
                self.crop_report()
                logger.info(self.report_res)
                self.record_report()
            except Exception as e:
                logger.exception("基报读取失败:{}".format(e))
            return True
        else:
            if self.reload_time > 3:
                logger.info("未加载出基报")
                return True
            self.reload_time += 1
            self.sleep(1)
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
            logger.exception(f"存入数据失败：{e}")
        self.tap((1253, 81), interval=2)
        try:
            send_message(
                report_template.render(
                    report_data=self.report_res, title_text="基建报告"
                ),
                "基建报告",
                "INFO",
                attach_image=self.recog.img,
            )
        except Exception as e:
            logger.exception(f"基报邮件发送失败：{e}")
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

    def crop_report(self):
        exp_area = [[1625, 200], [1800, 230]]
        iron_pos = self.find("riic/iron")
        iron_area = [
            [iron_pos[1][0], iron_pos[0][1]],
            [1800, iron_pos[1][1]],
        ]
        trade_pt = self.find("riic/trade")
        assist_pt = self.find("riic/assistants")
        area = {
            "iron_order": [[1620, trade_pt[1][1] + 10], [1740, assist_pt[0][1] - 50]],
            "iron_order_number": [
                [1820, trade_pt[1][1] + 10],
                [1870, assist_pt[0][1] - 65],
            ],
            "orundum": [[1620, trade_pt[1][1] + 45], [1870, assist_pt[0][1]]],
            "orundum_number": [
                [1820, trade_pt[1][1] + 55],
                [1860, assist_pt[0][1] - 20],
            ],
        }

        img = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        img = cv2.inRange(img, (98, 0, 150), (102, 255, 255))
        self.report_res["作战录像"] = self.get_number(img, exp_area, height=19)
        self.report_res["赤金"] = self.get_number(img, iron_area, height=19)
        self.report_res["龙门币订单"] = self.get_number(
            img, area["iron_order"], height=19
        )
        self.report_res["合成玉"] = self.get_number(img, area["orundum"], height=19)
        logger.info("蓝字读取完成")

        img = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        img = cv2.inRange(img, (0, 0, 50), (100, 100, 170))
        self.report_res["龙门币订单数"] = self.get_number(
            img, area["iron_order_number"], height=19, thres=200
        )
        self.report_res["合成玉订单数量"] = self.get_number(
            img, area["orundum_number"], height=19, thres=200
        )
        logger.info("订单数读取完成")

    def get_number(
        self, img, scope: tp.Scope, height: int | None = 18, thres: int | None = 100
    ):
        img = cropimg(img, scope)

        default_height = 29
        if height and height != default_height:
            scale = default_height / height
            img = cv2.resize(img, None, None, scale, scale)
        img = thres2(img, thres)
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        rect.sort(key=lambda c: c[0])
        value = 0
        for x, y, w, h in rect:
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            digit = cv2.copyMakeBorder(
                digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,)
            )

            score = []
            for i in range(10):
                im = noto_sans[i]
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
