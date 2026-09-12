import lzma
import pickle
from datetime import datetime, timedelta
from time import perf_counter

import cv2
import numpy as np

from arknights_mower.data import workshop_formula
from arknights_mower.solvers.record import save_inventory_counts
from arknights_mower.utils import rapidocr, segment
from arknights_mower.utils.character_recognize import operator_list, operator_list_train
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.operation_timing import timed_step
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
)


def _load_operator_room_model():
    with lzma.open(
        str(resource_pkg_path("arknights_mower/models/operator_room.model")), "rb"
    ) as f:
        model = pickle.loads(f.read())
    if not isinstance(model, dict):
        raise ValueError("基建干员识别模型格式错误")
    return model


OP_ROOM = _load_operator_room_model()

kernel = np.ones((12, 12), np.uint8)
PREFIX_NAME_SCORE_RATIO = 0.9
PREFIX_NAME_WIDTH_RATIO = 0.75
PREFIX_NAME_WIDTH_MARGIN = 30


class AgentSelectionNotReady(RuntimeError):
    """当前页面不足以继续选人；交由排班原有重试恢复，不结束任务线程。"""


# #85：排序列→x 坐标单一来源（detect_arrange_order / switch_arrange_order 共用；
# 2026-08-16 实机校准取读坐标，工作房 5 列、宿舍/中枢 4 列无「效率」）
_ARRANGE_ORDER_X = {
    "工作状态": 935,
    "效率": 1070,
    "技能": 1210,
    "心情": 1355,
    "信赖值": 1490,
}
_ARRANGE_ORDER_X_DORM = {
    "工作状态": 1070,
    "技能": 1217,
    "心情": 1352,
    "信赖值": 1490,
}


def _foreground_width(img):
    points = cv2.findNonZero(img)
    if points is None:
        return 0
    return cv2.boundingRect(points)[2]


OP_ROOM_WIDTH = {
    operator: _foreground_width(template) for operator, template in OP_ROOM.items()
}


@register_resource_reload
def reload_resource_models() -> None:
    model = _load_operator_room_model()
    widths = {
        operator: _foreground_width(template) for operator, template in model.items()
    }
    OP_ROOM.clear()
    OP_ROOM.update(model)
    OP_ROOM_WIDTH.clear()
    OP_ROOM_WIDTH.update(widths)


def _resolve_operator_room_prefix(
    best_operator, best_score, scores, sample_width, template_widths=None
):
    if best_operator is None:
        return best_operator
    template_widths = template_widths or OP_ROOM_WIDTH
    best_width = template_widths.get(best_operator, 0)
    if sample_width <= best_width + PREFIX_NAME_WIDTH_MARGIN:
        return best_operator
    prefix = f"{best_operator}·"
    prefix_operator = None
    prefix_score = 0
    for operator, score in scores.items():
        if not operator.startswith(prefix):
            continue
        operator_width = template_widths.get(operator, 0)
        if sample_width < operator_width * PREFIX_NAME_WIDTH_RATIO:
            continue
        if score < best_score * PREFIX_NAME_SCORE_RATIO:
            continue
        if score > prefix_score:
            prefix_operator = operator
            prefix_score = score
    if prefix_operator is not None:
        logger.debug(
            f"房间干员名{best_operator}存在长名前缀匹配，改判为{prefix_operator}"
        )
        return prefix_operator
    return best_operator


class BaseMixin:
    profession_labels = [
        "ALL",
        "PIONEER",
        "WARRIOR",
        "TANK",
        "SNIPER",
        "CASTER",
        "MEDIC",
        "SUPPORT",
        "SPECIAL",
    ]

    def _arrange_order_x(self, current_room):
        """排序列→x 坐标单一来源（#85：detect/switch 共用，取实机校准的读坐标）。"""
        if current_room.startswith("dormitory") or current_room == "central":
            return _ARRANGE_ORDER_X_DORM
        return _ARRANGE_ORDER_X

    def detect_arrange_order(self, current_room):
        y = 70
        hsv = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (95, 100, 100), (105, 255, 255))
        for name, x in self._arrange_order_x(current_room).items():
            if np.count_nonzero(mask[y : y + 3, x : x + 5]):
                return (name, False)
            if np.count_nonzero(mask[y + 10 : y + 13, x : x + 5]):
                return (name, True)

    def switch_arrange_order(self, name, current_room, ascending=False):
        if isinstance(ascending, str):
            ascending = ascending == "true"
        name_y = 60
        x = self._arrange_order_x(current_room)[name]
        before = None
        for attempt in range(6):
            if attempt:
                self.sleep(0.5)
            else:
                self.recog.update()
            before = self.detect_arrange_order(current_room)
            if before is not None:
                break
        if before is None:
            raise AgentSelectionNotReady("无法读取干员排序状态，返回房间重试")
        # 即使排序方式相同，也要刷新已选干员置顶；每次点击必须等到
        # 箭头实际变化后才能继续，不能把点击前的同方向旧帧当作完成。
        for _ in range(2):
            self.tap((x, name_y), interval=0.5)
            previous = None
            for attempt in range(6):
                if attempt:
                    self.sleep(0.5)
                # tap(interval=0.5) 和 sleep 已刷新截图，不重复截同一帧。
                actual = self.detect_arrange_order(current_room)
                logger.debug(
                    f"排序复核：点击前{before}，当前{actual}，目标{(name, ascending)}"
                )
                if actual is not None and actual != before and actual == previous:
                    break
                previous = actual
            else:
                raise AgentSelectionNotReady(
                    "干员排序点击后尚未确认画面变化，返回房间重试"
                )
            if actual == (name, ascending):
                return
            before = actual
        raise AgentSelectionNotReady("干员排序未到达目标状态，返回房间重试")

    @staticmethod
    def same_agent_page(left, right):
        """比较整页名字及卡片位置，允许识别边界的少量像素抖动。"""
        if not left or not right or len(left) != len(right):
            return False
        for (name, scope), (old_name, old_scope) in zip(left, right):
            if not name or name != old_name or scope is None or old_scope is None:
                return False
            if any(
                abs(value - old_value) > 3
                for point, old_point in zip(scope, old_scope)
                for value, old_value in zip(point, old_point)
            ):
                return False
        return True

    @staticmethod
    def agent_page_reader(*, full_scan=True, train=False):
        """同一次等待内，名字区域像素完全相同则复用模板匹配结果。"""
        previous_key = None
        previous_ret = None

        def read(img):
            nonlocal previous_key, previous_ret
            key = None
            if isinstance(img, np.ndarray):
                left, right = (
                    (545, 1920) if train else (600, 1920 if full_scan else 1860)
                )
                rows = ((479, 506), (895, 922)) if train else ((488, 520), (909, 941))
                key = tuple(img[y1:y2, left:right].tobytes() for y1, y2 in rows)
            if key is not None and key == previous_key:
                logger.debug("选人名字区域未变化，复用本次等待中的识别结果")
                return previous_ret
            started = perf_counter()
            ret = (
                operator_list_train(img)
                if train
                else operator_list(img, full_scan=full_scan)
            )
            logger.debug(
                f"选人模板匹配耗时：{(perf_counter() - started) * 1000:.0f} ms"
            )
            previous_key, previous_ret = key, ret
            return ret

        return read

    def wait_for_agent_page(self, *, full_scan=True, train=False, before=None):
        """先复核当前页；滑动后不把连续两张相同的旧画面当成新页。"""
        read = self.agent_page_reader(full_scan=full_scan, train=train)
        previous = None
        stable = False
        ret = []
        for attempt in range(6):
            started = perf_counter()
            if attempt:
                self.sleep(0.5)
            else:
                self.recog.update()
            connecting = self.find("connecting")
            logger.debug(
                f"选人等待及截图检查耗时：{(perf_counter() - started) * 1000:.0f} ms"
            )
            if connecting:
                previous = None
                stable = False
                continue
            try:
                ret = read(self.recog.img)
            except MowerExit:
                raise
            except Exception as e:
                logger.debug(f"翻页名单读取失败，原地复核：{e}")
                previous = None
                stable = False
                continue
            stable = self.same_agent_page(ret, previous)
            if stable and (before is None or not self.same_agent_page(ret, before)):
                logger.debug(f"确认当前干员页：{ret}")
                return ret
            previous = ret
        if stable:
            # 滑动后仍是旧页：交给调用方确认手势未推进，不能当成新页跳过。
            return ret
        raise AgentSelectionNotReady("干员页面仍在移动或名字识别不全，返回房间重试")

    def swipe_agent_page(self, page, agent, *, full_scan=True, train=False):
        """保留两列重叠，确认翻页生效；未推进时只做一次短距离复核。"""
        columns = sorted({scope[0][0] for _, scope in page})
        if len(columns) < 2:
            raise AgentSelectionNotReady("可识别干员列不足，返回房间重试")
        start_x = columns[-2] if len(columns) > 2 else columns[-1]
        y = page[0][1][0][1]
        for attempt in range(2):
            # 第二次只移动一列，防止第一次延迟完成时又跨过一整页。
            distance = columns[0] - (start_x if attempt == 0 else columns[1])
            self.swipe_noinertia((start_x, y), (distance, 0))
            actual = self.wait_for_agent_page(
                full_scan=full_scan, train=train, before=page
            )
            if not self.same_agent_page(actual, page):
                return attempt + 1
            logger.debug(f"翻页第{attempt + 1}次未确认推进，仍需查找：{agent}")
        raise AgentSelectionNotReady(
            f"两次滑动后整页干员及位置均未变化，可能已到末尾或手势未生效；"
            f"返回房间重试，仍需查找：{agent}"
        )

    def scan_agent(
        self,
        agent: list[str],
        error_count=0,
        max_agent_count=-1,
        full_scan=True,
        train=False,
    ):
        # 无目标时仍返回已复核的页面供调用方判断，但不进行点击。
        ret = self.wait_for_agent_page(full_scan=full_scan, train=train)
        select_name = []
        while True:
            target = next(((name, scope) for name, scope in ret if name in agent), None)
            if target is None:
                return select_name, ret
            name, scope = target
            self.tap(scope, interval=0.2)
            select_name.append(name)
            agent.remove(name)
            if not agent or (
                max_agent_count != -1 and len(select_name) >= max_agent_count
            ):
                return select_name, ret
            # 点击可能改变卡片位置；下一名必须从新页面重新定位。
            ret = self.wait_for_agent_page(full_scan=full_scan, train=train)

    @timed_step("verify")
    def wait_for_arranged_agents(
        self, agent, *, ordered=True, full_scan=True, train=False
    ):
        """等待排序后的名单连续两帧符合预期，不在旧画面上继续点击。"""
        if not agent:
            return []
        read = self.agent_page_reader(full_scan=full_scan, train=train)
        previous = None
        stable = False
        actual = []
        for attempt in range(6):
            if attempt:
                self.sleep(0.5)
            else:
                self.recog.update()
            if self.find("connecting"):
                previous = None
                stable = False
                continue
            try:
                ret = read(self.recog.img)
            except MowerExit:
                raise
            except Exception as e:
                logger.debug(f"选人名单读取失败，等待下一帧：{e}")
                previous = None
                stable = False
                continue
            if not train and ret and ret[0][1] is not None and ret[0][1][0][0] > 650:
                logger.debug(
                    "选人列表左侧仍被裁切，原地等待，不读取后续卡片作为已选名单"
                )
                previous = None
                stable = False
                actual = []
                continue
            selected = ret[: len(agent)]
            actual = [name for name, _ in selected]
            logger.debug(f"选人校验第{attempt + 1}次读取：{actual}")
            stable = len(actual) == len(agent) and self.same_agent_page(
                selected, previous
            )
            matches = actual == agent if ordered else sorted(actual) == sorted(agent)
            if matches and stable:
                return actual
            previous = selected
        if stable:
            logger.warning(f"干员名单已稳定但不符合预期：预期{agent}，实际{actual}")
            return None
        raise AgentSelectionNotReady(
            f"干员名单或位置仍在变化、左侧裁切或识别不全，返回房间重试："
            f"预期{agent}，最后读取{actual}"
        )

    def verify_agent(
        self,
        agent: list[str],
        room,
        error_count=0,
        max_agent_count=-1,
        full_scan=True,
        train=False,
    ):
        try:
            return (
                self.wait_for_arranged_agents(agent, full_scan=full_scan, train=train)
                is not None
            )
        except (MowerExit, AgentSelectionNotReady):
            raise
        except Exception as e:
            error_count += 1
            if room != "train":
                self.switch_arrange_order("技能", room)
            if error_count < 3:
                return self.verify_agent(
                    agent,
                    room,
                    error_count,
                    max_agent_count,
                    full_scan=False,
                    train=train,
                )
            else:
                logger.exception(e)
                raise e

    @timed_step("rewind")
    def swipe_left(self, right_swipe, special_filter, *, train=False):
        # 2500 像素的屏外拖动在 Android 会被裁到边缘，不能按请求距离或
        # “右移三次只回拉两次”推算归零。回拉使用屏内路径，并读取实际结果。
        full_scan = special_filter in (None, "ALL")
        # 回拉途中不用逐页找人。计数只用于减少中途识别，不能作为到头凭据；
        # 保留至少一次末端实测，短滑、排序后计数归零仍按实际页面处理。
        bulk = min(max(right_swipe - 1, 0), 8)
        for _ in range(bulk):
            self.swipe_noinertia((650, 540), (1100, 0), interval=0)
        page = self.wait_for_agent_page(full_scan=full_scan, train=train)
        # 排序/筛选可能将计数归零却保留列表偏移；完整卡片也可能恰好
        # 对齐在中间页。因此即使计数为零，也必须实际回拉确认。
        for attempt in range(12 - bulk):
            self.swipe_noinertia((650, 540), (1100, 0))
            actual = self.wait_for_agent_page(
                full_scan=full_scan, train=train, before=page
            )
            if self.same_agent_page(actual, page):
                if train or actual[0][1][0][0] <= 650:
                    return 0
                raise AgentSelectionNotReady("回拉后列表仍被裁切且未推进，返回房间重试")
            logger.debug(f"选人列表回拉第{attempt + 1}次，首张完整卡片：{actual[0]}")
            page = actual
        raise AgentSelectionNotReady("未能确认干员列表回到左端，返回房间重试")

    def profession_filter(self, profession=None):
        """
                    confirm_blue	confirm_train
        训练位筛选开	1548 0.89		1554
        训练位筛选关	not				1669
        普通位筛选关	1724			1732 0.7
        普通位筛选开	1609			not
        """
        retry = 0
        open_threshold = 1650
        if profession:
            logger.info(f"打开 {profession} 筛选")
        else:
            logger.info("关闭职业筛选")
            self.profession_filter("ALL")
            while (
                (confirm_btn := self.find("confirm_blue")) is not None
                and confirm_btn[0][0] < open_threshold
            ) or (
                (confirm_btn := self.find("confirm_train")) is not None
                and confirm_btn[0][0] < open_threshold
            ):
                self.tap((1860, 60), 0.1)
                retry += 1
                if retry > 5:
                    raise Exception("关闭职业筛选失败")
            return
        x = 1918
        label_pos = [(x, 135 + i * 110) for i in range(9)]
        label_pos_map = dict(zip(self.profession_labels, label_pos))
        while (
            (confirm_btn := self.find("confirm_blue")) is not None
            and confirm_btn[0][0] > open_threshold
        ) or (
            (confirm_btn := self.find("confirm_train")) is not None
            and confirm_btn[0][0] > open_threshold
        ):
            self.tap((1860, 60), 0.1)
            retry += 1
            if retry > 5:
                raise Exception("打开职业筛选失败")
        retry = 0
        # 点击一次ALL先
        self.tap(label_pos_map["ALL"], 0.1)
        while self.get_color(label_pos_map[profession])[2] < 240:
            logger.debug(f"配色为： {self.get_color(label_pos_map[profession])[2]}")
            self.tap(label_pos_map[profession], 0.1)
            retry += 1
            if retry > 5:
                raise Exception("打开职业筛选失败")

    def detect_room_number(self, img) -> int:
        score = []
        for i in range(1, 5):
            digit = loadres(f"room/{i}")
            result = cv2.matchTemplate(img, digit, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            score.append(max_val)
        return score.index(max(score)) + 1

    def detect_room(self) -> str:
        color_map = {
            "制造站": 25,
            "贸易站": 99,
            "发电站": 36,
            "训练室": 178,
            "加工站": 32,
        }
        img = cropimg(self.recog.img, ((568, 18), (957, 95)))
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        colored_room = None
        for room, color in color_map.items():
            mask = cv2.inRange(hsv, (color - 1, 0, 0), (color + 2, 255, 255))
            if cv2.countNonZero(mask) > 1000:
                colored_room = room
                break
        if colored_room in ["制造站", "贸易站", "发电站"]:
            digit_1 = cropimg(img, ((211, 24), (232, 54)))
            digit_2 = cropimg(img, ((253, 24), (274, 54)))
            digit_1 = self.detect_room_number(digit_1)
            digit_2 = self.detect_room_number(digit_2)
            logger.debug(f"{colored_room}B{digit_1}0{digit_2}")
            return f"room_{digit_1}_{digit_2}"
        elif colored_room == "训练室":
            logger.debug("训练室B305")
            return "train"
        elif colored_room == "加工站":
            logger.debug("加工站B105")
            return "factory"
        white_room = ["central", "dormitory", "meeting", "contact"]
        score = []
        for room in white_room:
            tpl = loadres(f"room/{room}")
            result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            score.append(max_val)
        room = white_room[score.index(max(score))]
        if room == "central":
            logger.debug("控制中枢")
        elif room == "dormitory":
            digit = cropimg(img, ((174, 24), (195, 54)))
            digit = self.detect_room_number(digit)
            if digit == 4:
                logger.debug("宿舍B401")
            else:
                logger.debug(f"宿舍B{digit}04")
            return f"dormitory_{digit}"
        elif room == "meeting":
            logger.debug("会客室1F02")
        else:
            logger.debug("办公室B205")
        return room

    def adjust_room(self, _room):
        # 定义屏幕范围
        screen_min_x = 0
        screen_max_x = 1920

        # 检查是否有点在屏幕范围内
        any_point_in_view = any(screen_min_x <= p[0] <= screen_max_x for p in _room)

        if any_point_in_view:
            logger.debug(
                f"At least one point of {_room} is within screen range [0, 1920]. No movement needed."
            )
            for i in range(4):
                _room[i, 0] = max(_room[i, 0], 0)
                _room[i, 0] = min(_room[i, 0], self.recog.w)
                _room[i, 1] = max(_room[i, 1], 0)
                _room[i, 1] = min(_room[i, 1], self.recog.h)
            return _room

        # 如果所有点都超出屏幕范围，则计算需要的移动距离
        min_x = min(p[0] for p in _room)
        max_x = max(p[0] for p in _room)

        dx = 0
        start = (960, 540)
        if min_x < screen_min_x:
            # 左边超出，向右移动
            dx = screen_min_x - min_x
            logger.debug(f"Moving right by {dx} to bring room into view.")
        elif max_x > screen_max_x:
            # 右边超出，向左移动
            dx = screen_max_x - max_x
            logger.debug(f"Moving left by {-dx} to bring room into view.")

        # 如果需要移动，则移动视图
        if dx != 0:
            movement = (dx, 0)  # 仅水平移动
            self.swipe_noinertia(start, movement, interval=0.5)
            # 更新 _room 的所有点位置
            for i in range(len(_room)):
                _room[i][0] += dx

        # 返回修正后的 _room
        return _room

    def enter_room(self, room):
        """从基建首页进入房间"""

        for enter_times in range(3):
            for retry_times in range(5):
                if self.find("connecting"):
                    self.sleep()
                elif pos := self.find("control_central"):
                    _room = segment.base(self.recog.img, pos)[room]
                    logger.debug(
                        f"进入房间 {room}，第{enter_times + 1}轮第{retry_times + 1}次点击"
                    )
                    self.tap(self.adjust_room(_room))
                elif self.detect_room() == room:
                    return
                else:
                    self.sleep()
            # 最后一次点击也可能成功，检查其刷新后的画面再决定是否重试。
            if (
                not self.find("connecting")
                and not self.find("control_central")
                and self.detect_room() == room
            ):
                return
            if enter_times < 2:
                # 仍停在全局视角时，原逻辑会一直点击同一位置；退出基建
                # 再重新进入，重新定位房间。此处不重启或关闭游戏。
                logger.warning(
                    f"未确认进入房间 {room}，返回首页后重新定位（{enter_times + 1}/2）"
                )
                self.back_to_index()
                self.back_to_infrastructure()
        raise RuntimeError(f"未成功进入房间 {room}：重新定位后仍未确认房间画面")

    def double_read_time(self, cord, upperLimit=None, use_digit_reader=False):
        self.recog.update()
        time_in_seconds = self.read_time(
            cord, upperLimit, use_digit_reader=use_digit_reader
        )
        if time_in_seconds is None:
            logger.warning(
                "订单/设施倒计时识别失败，回退为当前时间；不能据此确认实际订单完成时间"
            )
            return datetime.now()
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds))
        return execute_time

    def read_accurate_mood(self, img):
        try:
            img = thres2(img, 200)
            return cv2.countNonZero(img) * 24 / 310
        except Exception as e:
            logger.exception(e)
            return 24

    def detect_product_complete(self):
        for product in ["gold", "exp", "lmd", "ori", "oru", "trust"]:
            if pos := self.find(
                f"infra_{product}_complete",
                scope=((1230, 0), (1920, 1080)),
                score=0.1,
            ):
                return pos

    def read_operator_in_room(self, img):
        img = thres2(img, 200)
        img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(img, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        x0 = min(x for x, y, w, h in rect)
        y0 = min(y for x, y, w, h in rect)
        x1 = max(x + w for x, y, w, h in rect)
        y1 = max(y + h for x, y, w, h in rect)
        img = img[y0:y1, x0:x1]
        tpl = np.zeros((46, 265), dtype=np.uint8)
        h = min(img.shape[0], tpl.shape[0])
        w = min(img.shape[1], tpl.shape[1])
        tpl[:h, :w] = img[:h, :w]
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        sample_width = _foreground_width(tpl)
        max_score = 0
        best_operator = None
        scores = {}
        for operator, template in OP_ROOM.items():
            result = cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            scores[operator] = max_val
            if max_val > max_score:
                max_score = max_val
                best_operator = operator
        return _resolve_operator_room_prefix(
            best_operator, max_score, scores, sample_width
        )

    @timed_step("room_read")
    def read_screen(self, img, type="mood", limit=24, cord=None):
        if cord is not None:
            img = cropimg(img, cord)
        if type == "name":
            img = cropimg(img, ((169, 22), (513, 80)))
            return self.read_operator_in_room(img)
        try:
            ret = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)[0]
            logger.debug(ret)
            if not ret or not ret[0][0]:
                raise Exception("识别失败")
            ret = ret[0][0]
            if "mood" in type:
                if (f"/{limit}") in ret:
                    ret = ret.replace(f"/{limit}", "")
                if len(ret) > 0:
                    if "." in ret:
                        ret = ret.replace(".", "")
                    return int(ret)
                else:
                    return -1
            elif "time" in type:
                if "." in ret:
                    ret = ret.replace(".", ":")
                return ret.strip()
            else:
                return ret
        except Exception:
            return limit + 1

    def item_valid(self):
        img = self.recog.img

        region = img[
            int(0.83 * self.recog.h) : int(0.92 * self.recog.h),
            int(0.77 * self.recog.w) : int(0.96 * self.recog.w),
        ]

        avg_color = np.mean(region.reshape(-1, 3), axis=0)
        logger.debug(f"平均颜色: {avg_color}")

        target_color = np.array([189.2, 163.8, 23.7])

        distance = np.linalg.norm(avg_color - target_color)

        return distance < 30

    def item_list(self):
        try:
            offset_x = 370
            offset_y = 125
            img = self.recog.img[offset_y:1040, offset_x:1860]
            ocr_result = rapidocr.engine(
                img,
                use_det=True,
                use_cls=False,
                use_rec=True,
            )
            res = []
            furniture_start_index = -1
            furniture_keys = [
                "家具零件_碳素",
                "家具零件_碳素组",
                "家具零件_基础加固建材",
                "家具零件_进阶加固建材",
                "家具零件_高级加固建材",
                "家具零件_碳",
            ]
            base_idx = 0
            for idx, item in enumerate(ocr_result[0]):
                if item[1] == "家具零件" and furniture_start_index == -1:
                    furniture_start_index = base_idx
                if (
                    len(item) > 2
                    and item[1] in workshop_formula.keys()
                    or item[1] == "家具零件"
                ):
                    name = item[1]
                    if name == "家具零件" and furniture_start_index in range(6):
                        name = furniture_keys[base_idx]
                    box = item[0]
                    base_px = int(box[0][0]) + 15
                    base_py = int(box[0][1]) + 75
                    sample_points = [(base_px + i * 155, base_py) for i in range(3)]
                    valid = 0
                    for _idx, (px, py) in enumerate(sample_points):
                        # 加入75px为边界
                        if 0 <= py < img.shape[0] - 75 and 0 <= px < img.shape[1]:
                            color = img[py, px]
                            valid += 1
                            logger.debug(
                                f"检测到{item[1]} 颜色 {_idx + 1} ({px}, {py}): {color}"
                            )
                            if not np.all((color >= 40) & (color <= 80)):
                                valid = float("-inf ")
                                if _idx < len(workshop_formula[name]["items"]):
                                    logger.debug(f"更新{name}数量为0")
                                    save_inventory_counts(
                                        {workshop_formula[name]["items"][_idx]: 0}
                                    )
                                break
                    box_global = [[x + offset_x, y + offset_y] for (x, y) in box]
                    # 等于 0 则出界了
                    if valid != 0:
                        res.append((name, box_global, valid > 0))
                    if base_idx < 5:
                        base_idx += 1
            return res
        except Exception as e:
            logger.exception(e)

    def get_number(self, cord, error_count=0):
        # (290, 335, 95, 200) 九色鹿
        # (1740,620 , 1600,500 ) 合成次数 不准
        if error_count > 3:
            return -1
        try:
            self.recog.update()
            y1, y2, x1, x2 = cord
            img = self.recog.img[y1:y2, x1:x2]
            ocr_result = rapidocr.engine(
                img,
                use_det=True,
                use_cls=False,
                use_rec=True,
            )
            text = ocr_result[0][0][1]
            score_str = text.split("/")[0]
            return int(score_str)
        except Exception as e:
            logger.exception(e)
            logger.debug(f"读取失败{error_count}次")
            self.sleep()
            return self.get_number(cord, error_count=error_count + 1)

    def get_craft(self):
        try:
            img = self.recog.img[290:335, 95:200]
            ocr_result = rapidocr.engine(
                img,
                use_det=True,
                use_cls=False,
                use_rec=True,
            )
            text = ocr_result[0][0][1]
            if text.find("/") == -1:
                logger.exception("九色鹿技能识别失败")
                return None
            score_str = text.split("/")[0]
            return int(score_str)
        except Exception as e:
            logger.exception(e)

    def read_time(self, cord, upperlimit, error_count=0, use_digit_reader=False):
        # 刷新图片
        self.recog.update()
        try:
            if use_digit_reader:
                gray = self.recog.gray
                height, width = gray.shape[:2]
                time_str = self.digit_reader.get_time(gray, height, width)
            else:
                time_str = self.read_screen(self.recog.img, type="time", cord=cord)
            logger.debug(time_str)
            h, m, s = str(time_str).split(":")
            if int(m) > 60 or int(s) > 60:
                raise Exception("读取错误")
            res = int(h) * 3600 + int(m) * 60 + int(s)
            if upperlimit is not None and res > upperlimit:
                raise Exception("超过读取上限")
            else:
                return res
        except Exception as exc:
            logger.debug(f"倒计时读取失败（{type(exc).__name__}）：{exc}")
            if error_count > 3:
                logger.debug(f"读取失败{error_count}次超过上限")
                return None
            else:
                logger.debug("读取失败")
                return self.read_time(
                    cord, upperlimit, error_count + 1, use_digit_reader
                )
