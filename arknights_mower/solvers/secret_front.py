import lzma
import pickle
from datetime import datetime, timedelta
from typing import Optional

import cv2

from arknights_mower import __rootdir__
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.matcher import Matcher
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.solver import BaseSolver, MowerExit

with lzma.open(f"{__rootdir__}/models/secret_front.pkl", "rb") as f:
    templates = pickle.load(f)


def exp(card):
    data = card[:3]
    p = card[3]
    return [i * p for i in data]


def va(a, b):
    return [a[0] + b[0], a[1] + b[1]]


def sa(scope, vector):
    return [va(scope[0], vector), va(scope[1], vector)]


class SecretFront(BaseSolver):
    target = {
        "1A": [20, 20, 20],
        "2A": [60, 55, 45],
        "2B": [45, 55, 65],
        "3A": [200, 155, 155],
        "3B": [150, 220, 250],
        "3C": [155, 255, 240],
        "结局A": [510, 350, 350],
        "结局B": [440, 440, 350],
        "结局C": [350, 550, 350],
        "结局D": [365, 475, 495],
        "结局E": [370, 385, 620],
    }
    routes = {
        "结局A": ["1A", "2A", "3A", "结局A"],
        "结局B": ["1A", "2A", "3A", "结局B"],
        "结局C": ["1A", "2A", "3B", "结局C"],
        "结局D": ["1A", "2B", "3C", "结局D"],
        "结局E": ["1A", "2B", "3C", "结局E"],
    }
    teams = {
        "结局A": "management",
        "结局B": "management",
        "结局C": "intelligence",
        "结局D": "medicine",
        "结局E": "medicine",
    }

    @property
    def route(self):
        return self.routes[config.conf["secret_front"]["target"]]

    @property
    def team(self):
        return self.teams[config.conf["secret_front"]["target"]]

    def run(
        self,
        duration: Optional[timedelta] = None,
        timeout: timedelta = timedelta(seconds=30),
    ):
        logger.info("Start: 隐秘战线")

        self.timeout = timeout
        self.deadline = datetime.now() + duration - timeout if duration else None
        self.unknown_time = None

        self.properties = None
        self.route_matcher = None

        self.event = False  # 支援作战平台、游侠、诡影迷踪

        self.reset_actions()

        super().run()

    def reset_actions(self):
        self.actions = {}
        for page in range(3):
            self.actions[page] = {}

    def number(self, scope: tp.Scope, height: Optional[int] = None):
        img = cropimg(self.recog.gray, scope)
        if height:
            scale = 25 / height
            img = cv2.resize(img, None, None, scale, scale)
        img = thres2(img, 127)
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
                im = templates[i]
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                score.append(min_val)
            value = value * 10 + score.index(min(score))

        return value

    def card_pos(self, total, idx):
        if total == 3:
            return [(301, 466), (830, 466), (1360, 466)][idx]
        elif total == 2:
            return [(565, 466), (1095, 466)][idx]
        else:
            return (830, 466)

    def stage_card(self, total, idx):
        pos = self.card_pos(total, idx)

        scope = sa(((10, 380), (140, 430)), pos)
        img = cropimg(self.recog.gray, scope)
        img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        score = []
        for i in self.target:
            result = cv2.matchTemplate(img, templates[i], cv2.TM_SQDIFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            score.append(min_val)
        name = list(self.target)[score.index(min(score))]

        x, y = va(pos, (350, 460))
        hsv = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        hue = hsv[y][x][0]

        logger.debug(f"{name=} {hue=}")
        return name, hue > 18

    def card(self, total, idx):
        pos = self.card_pos(total, idx)

        materiel = sa(((84, 70), (180, 102)), pos)
        intelligence = sa(((249, 70), (343, 102)), pos)
        medicine = sa(((414, 70), (470, 102)), pos)
        percentage = sa([[10, 440], [130, 473]], pos)

        materiel = self.number(materiel)
        intelligence = self.number(intelligence)
        medicine = self.number(medicine)

        min_val, min_loc = self.template_match(
            "sf/percentage", percentage, cv2.TM_SQDIFF_NORMED
        )
        percentage[1][0] = min_loc[0][0]
        percentage = self.number(percentage, 28) / 100

        logger.debug(f"{materiel=} {intelligence=} {medicine=} {percentage=}")

        return materiel, intelligence, medicine, percentage

    def page_number(self):
        title = cropimg(self.recog.gray, ((1020, 230), (1210, 280)))
        if self.route_matcher is None:
            return None
        pos = self.route_matcher.match(title)
        if not pos:
            return None
        pos_x = pos[0][0]
        if pos_x < 800:
            page_number = 0
        elif pos_x < 1330:
            page_number = 1
        else:
            page_number = 2
        logger.debug(f"{page_number=}")
        return page_number

    def card_total(self):
        p3 = self.card_pos(3, 0)
        p2 = self.card_pos(2, 0)
        up_scope = ((0, 0), (473, 120))
        down_scope = ((0, 432), (150, 474))
        s3u = sa(up_scope, p3)
        s3d = sa(down_scope, p3)
        s2u = sa(up_scope, p2)
        s2d = sa(down_scope, p2)
        if (pos := self.find("sf/card", scope=s3u)) and pos[0][0] < 350:
            total = 3
        elif self.find("sf/available", scope=s3d):
            total = 3
        elif (pos := self.find("sf/card", scope=s2u)) and pos[0][0] < 610:
            total = 2
        elif self.find("sf/available", scope=s2d):
            total = 2
        else:
            total = 1
        logger.debug(f"{total=}")
        return total

    def max_card(self):
        max_page = -1
        max_card = -1
        max_score = -1

        logger.debug(f"{self.properties=}")

        # 根据目标计算
        for page, page_action in self.actions.items():
            for card, action in page_action.items():
                for stage in self.route:
                    target = self.target[stage]
                    if all(p < t for p, t in zip(self.properties, target)):
                        break
                distance = [max(t - p, 0) for p, t in zip(self.properties, target)]
                if sum(distance) == 0:
                    return 0, 0
                total_score = 0
                for i in range(3):
                    score = action[i] * distance[i] / sum(distance)
                    total_score += score
                logger.debug(f"{page=} {card=} {stage=} {total_score=}")
                if total_score > max_score:
                    max_score = total_score
                    max_page = page
                    max_card = card
        logger.debug(f"{max_page=} {max_card=}")
        return max_page, max_card

    def choose_card(self, total, idx):
        self.route_matcher = None
        self.properties = None
        self.reset_actions()

        if total == 3:
            start = 545
        elif total == 2:
            start = 805
        else:
            start = 1075
        self.tap((start + idx * 530, 900), interval=0.5)
        self.tap((start + idx * 530, 900), interval=2)

    def move_forward(self, scene):
        # 从首页进入隐秘战线
        if scene == Scene.INDEX:
            self.tap_index_element("terminal")
        elif scene == Scene.TERMINAL_MAIN:
            self.tap_element("main_theme_small")
        elif scene == Scene.TERMINAL_MAIN_THEME:
            self.tap_element("main_14")
        elif scene == Scene.SF_ENTRANCE:
            self.tap_element("sf/entrance")

        # 选择小队
        elif scene == Scene.SF_SELECT_TEAM:
            self.tap_element(f"sf/team_{self.team}")
            self.tap_element("sf/select_team_ok")

        # 继续前进
        elif scene == Scene.SF_CONTINUE:
            self.tap_element("sf/continue")

        # 选择路线时识别已有属性值
        elif scene == Scene.SF_SELECT:
            self.event = False

            if self.properties is None:
                self.properties = [
                    self.number(((105, 490), (180, 525)), 23),
                    self.number(((105, 580), (180, 615)), 23),
                    self.number(((105, 675), (180, 705)), 23),
                ]
                logger.debug(f"{self.properties=}")

            if self.route_matcher is None:
                self.route_matcher = Matcher(self.recog.gray)

            self.series = None
            if (
                (pos := self.find("sf/support_battle_platform"))
                or (pos := self.find("sf/ranger"))
                or (
                    self.route[-1] == "结局E"
                    and (pos := self.find("sf/lost_in_the_trick"))
                )
            ):
                if (pos_x := pos[0][0]) < 800:
                    self.series = 0
                elif pos_x < 1330:
                    self.series = 1
                else:
                    self.series = 2
                logger.debug(f"{self.series=}")

                self.tap((545 + 530 * self.series, 640), interval=1.5)
                return

            self.tap((545, 640), interval=1.5)

        # 行动列表
        elif scene == Scene.SF_ACTIONS:
            total = self.card_total()

            if self.event:
                name_list = [self.stage_card(total, i) for i in range(total)]
                for idx, data in enumerate(name_list):
                    name, available = data
                    if name in self.route:
                        if available:
                            self.choose_card(total, idx)
                        else:
                            self.exit = "restart"
                            self.tap_element("sf/exit_button")
                        return
                self.exit = "restart"
                self.tap_element("sf/exit_button")
                return

            if (page_number := self.page_number()) is None:
                self.sleep()
                return

            target = self.target[self.route[-1]]
            distance = [max(t - p, 0) for p, t in zip(self.properties, target)]
            if sum(distance) == 0:
                self.choose_card(total, 0)
                self.sleep(3)
                return

            if self.series is not None:
                card_data = [self.card(total, idx) for idx in range(total)]
                for idx in range(total):
                    self.actions[page_number][idx] = exp(card_data[idx])
                if all(card[3] < 0.8 for card in card_data):
                    logger.debug("成功概率太低")
                    self.series = None
                    return

            elif not all(self.actions.values()):
                # 先看一遍所有行动，找到还没看过的页。
                target_number = next(i for i in range(3) if not self.actions[i])
                if target_number == page_number:
                    # 如果要读的是当前页，读取并计算分数
                    for idx in range(total):
                        self.actions[page_number][idx] = exp(self.card(total, idx))
                elif (page_number + 1) % 3 == target_number:
                    self.tap((1785, 225))  # 下一页
                else:
                    self.tap((350, 225))  # 上一页
                return

            max_page, max_card = self.max_card()

            if max_page == page_number:
                self.choose_card(len(self.actions[max_page]), max_card)
                self.sleep(3)
            elif (page_number + 1) % 3 == max_page:
                self.tap((1785, 225))  # 下一页
            else:
                self.tap((350, 225))  # 上一页

        # 行动结果
        elif scene == Scene.SF_RESULT:
            if pos := self.find("sf/continue_result"):
                self.tap(pos)
            else:
                self.sleep()

        elif scene == Scene.SF_EVENT:
            self.event = True
            self.tap_element("sf/continue_event", interval=1.5)

        elif scene in [Scene.SF_TEAM_PASS, Scene.SF_CLICK_ANYWHERE, Scene.SF_END]:
            self.tap((960, 980), interval=2)

            if scene == Scene.SF_END and hasattr(self, "send_message_config"):
                self.send_message(
                    f'隐秘战线成功完成{config.conf["secret_front"]["target"]}'
                )

        # 关闭说明
        elif scene == Scene.SF_INFO:
            self.tap_element("sf/info", x_rate=0.17, y_rate=0.46)

        elif scene == Scene.SF_EXIT:
            if self.exit == "restart":
                self.properties = None
                self.route_matcher = None
                self.event = False

                self.tap_element("sf/restart")
                self.tap_element("sf/confirm")
            elif self.exit == "exit":
                self.tap_element("sf/confirm")
            else:
                self.tap((480, 590))

        else:
            self.sleep()

    def back_to_index(self, scene):
        if scene in [Scene.TERMINAL_MAIN, Scene.TERMINAL_MAIN_THEME, Scene.SF_ENTRANCE]:
            self.back()
        elif scene == Scene.SF_EXIT:
            self.move_forward(scene)
        else:
            self.exit = "exit"
            self.tap_element("sf/exit_button")

    def transition(self):
        now = datetime.now()

        if (scene := self.sf_scene()) == Scene.UNKNOWN:
            if not self.unknown_time:
                self.unknown_time = now
            elif now - self.unknown_time > self.timeout:
                logger.warning("连续识别到未知场景")
                try:
                    self.properties = None
                    self.route_matcher = None
                    self.event = False
                    self.reset_actions()
                    super().back_to_index()
                except MowerExit:
                    raise
                except Exception:
                    self.device.exit()
                    if self.device.check_current_focus():
                        self.recog.update()
        else:
            self.unknown_time = None

        if self.deadline and self.deadline < datetime.now():
            if scene == Scene.INDEX:
                return True
            else:
                self.back_to_index(scene)
        else:
            self.move_forward(scene)
