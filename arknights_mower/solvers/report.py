import datetime
import os

import cv2

from arknights_mower.models import noto_sans
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.email import report_template, send_message
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.recognize import Recognizer, Scene, tp


def match_digit(digit, template) -> float | None:
    """Score a digit against a contained template; incompatible shapes are unread."""
    if digit.shape[0] < template.shape[0] or digit.shape[1] < template.shape[1]:
        return None
    try:
        result = cv2.matchTemplate(digit, template, cv2.TM_SQDIFF_NORMED)
    except cv2.error:
        return None
    return cv2.minMaxLoc(result)[0]


class ReportSolver(SceneGraphSolver):
    # Bound both per-run reads and scheduler retries for the current date.
    MAX_READ_ATTEMPTS = 3
    attempts = 0
    last_attempt_date: str | None = None

    def __init__(
        self,
        device: Device = None,
        recog: Recognizer = None,
    ) -> None:
        super().__init__(device, recog)
        self.record_path = get_path("@app/tmp/report.csv")
        self.low_range_gray = (100, 100, 100)
        self.high_range_gray = (255, 255, 255)
        self.date = get_server_time().date().__str__()
        self.report_res = {
            "作战录像": None,
            "赤金": None,
            "龙门币订单": None,
            "龙门币订单数": None,
            "合成玉": None,
            "合成玉订单数量": None,
        }
        self.reload_time = 0
        self._stored = False

    def run(self):
        if self.has_record():
            logger.info("今天的基报看过了")
            return True
        if type(self).last_attempt_date != self.date:
            type(self).last_attempt_date = self.date
            type(self).attempts = 0
        if type(self).attempts >= self.MAX_READ_ATTEMPTS:
            logger.warning("基报连续读取失败，本次启动不再重试")
            return False
        logger.info("康康大基报捏~")
        type(self).attempts += 1
        try:
            super().run()
        except (MowerExit, DeviceRecoveryError):
            type(self).attempts -= 1
            raise
        except Exception as e:
            logger.exception(e)
        if self._stored:
            type(self).attempts = 0
            return True
        logger.warning("基报没有记录，稍后重试")
        return False

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.RIIC_REPORT:
            self.sleep(2)
            self.recog.update()
            return self.read_report()
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.RIIC_REPORT)

    def read_report(self):
        if self._stored:
            return True
        # A falsy transition repeats inside BaseSolver.run().
        if self.reload_time >= self.MAX_READ_ATTEMPTS:
            logger.info("基报未读出，本次尝试结束")
            return True
        self.reload_time += 1
        try:
            if self.find("riic/manufacture"):
                self.crop_report()
                logger.info(self.report_res)
                return self.record_report()
            logger.info("未加载出基报")
            self.sleep(1)
            return False
        except (MowerExit, DeviceRecoveryError):
            self.reload_time -= 1
            raise
        except Exception as e:
            logger.exception(f"基报读取失败:{e}")
            return self._stored

    def add_order_detail(self):
        try:
            current_date = str((get_server_time() - datetime.timedelta(days=1)).date())
            from arknights_mower.solvers import record

            order_history = record.get_trading_history(current_date, current_date)
            total = 0
            if len(order_history) == 1:
                for k, count in order_history[0].items():
                    if k == "日期":
                        continue
                    key = ""
                    value = 0
                    if k == "龙舌兰":
                        key = "龙舌兰" + "(2500)"
                        value = 2500 * count
                    elif k == "可露希尔":
                        key = "可露希尔" + "(1200)"
                        value = 1200 * count
                    else:
                        parts = k.split("_")
                        key = parts[0] + "(" + parts[1] + ")"
                        value = int(parts[1]) * count
                    self.report_res[key] = value
                    total += value
            if (
                self.report_res["龙门币订单"] is not None
                and total != self.report_res["龙门币订单"]
            ):
                self.report_res["未知订单"] = self.report_res["龙门币订单"] - total
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception as e:
            logger.exception(f"处理交易历史记录时出错：{e}")

    def record_report(self):
        """Store independent fields before claiming; no readings or failed writes retry."""
        if all(value is None for value in self.report_res.values()):
            logger.warning(f"{self.date}的基建报告没有读到任何数据，不记录")
            return False
        logger.info(f"存入{self.date}的数据{self.report_res}")
        try:
            from arknights_mower.utils.csv_utils import append_dated_row

            append_dated_row(
                self.record_path,
                self.date,
                self.report_res,
                header=True,
                encoding="gbk",
            )
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception as e:
            logger.exception(f"存入数据失败：{e}")
            return False
        self._stored = True
        self.tap((1253, 81), interval=2)
        try:
            self.add_order_detail()
            send_message(
                report_template.render(
                    report_data=self.report_res, title_text="基建报告"
                ),
                "基建报告",
                "INFO",
                attach_image=self.recog.img,
            )
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception as e:
            logger.exception(f"基报邮件发送失败：{e}")
        self.tap((40, 80), interval=2)
        return True

    def has_record(self):
        try:
            if os.path.exists(self.record_path) is False:
                logger.debug("基报不存在")
                return False
            _, rows = read_csv_rows(self.record_path, encoding="gbk")
            for item in rows:
                if item[0] == self.date:
                    return True
            return False
        except PermissionError:
            logger.info("report.csv正在被占用")
        except EmptyDataError:
            return False

    def crop_report(self):
        exp_area = [[1625, 200], [1800, 230]]
        iron_pos = self.find("riic/iron")
        iron_area = (
            [[iron_pos[1][0], iron_pos[0][1]], [1800, iron_pos[1][1]]]
            if iron_pos
            else None
        )
        trade_pt = self.find("riic/trade")
        assist_pt = self.find("riic/assistants")
        area = dict.fromkeys(
            ["iron_order", "iron_order_number", "orundum", "orundum_number"]
        )
        if trade_pt and assist_pt:
            area = {
                "iron_order": [
                    [1620, trade_pt[1][1] + 10],
                    [1740, assist_pt[0][1] - 50],
                ],
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
        self,
        img,
        scope: tp.Scope | None,
        height: int | None = 18,
        thres: int | None = 100,
    ) -> int | None:
        """Read a complete field; absent crops or unscorable digits return None."""
        if scope is None:
            return None
        img = cropimg(img, scope)
        if img.size == 0:
            return None

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
                matched = match_digit(digit, noto_sans[i])
                if matched is not None:
                    score.append((matched, i))
            if not score:
                return None
            value = value * 10 + min(score)[1]
        return value
