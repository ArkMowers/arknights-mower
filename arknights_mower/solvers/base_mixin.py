import lzma
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from time import perf_counter

import cv2
import numpy as np

from arknights_mower.data import agent_branch, agent_profession, workshop_formula
from arknights_mower.utils import config, rapidocr, segment
from arknights_mower.utils.character_recognize import (
    estimate_agent_mood,
    operator_list,
    operator_list_train,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.operation_timing import timed_step
from arknights_mower.utils.performance import (
    PERFORMANCE_PRESETS,
    effective_performance_profile,
    lower_performance_mode,
)
from arknights_mower.utils.resident_timer import (
    is_resident_timer_scope,
    read_resident_timer,
    resident_timer_supports_ocr,
)
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
)
from arknights_mower.utils.resting_priority import trade_order_dorm_entry_blocked
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.selection_branch import (
    PROFESSION_LABELS,
    branch_filter_state,
    set_branch_menu_open,
)
from arknights_mower.utils.selection_order import selection_slot
from arknights_mower.utils.station_filter import read_station_filter
from arknights_mower.utils.swipe import NOINERTIA_OFFSET


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
OPERATOR_ROOM_MIN_SCORE = 0.70
ROOM_NAME_TEMPLATE_SHAPE = (46, 265)
ROOM_TITLE_TYPES = {
    "central": "控制中枢",
    "dormitory": "宿舍",
    "meeting": "会客室",
    "contact": "办公室",
    "recycle": "回收站",
    "factory": "加工站",
    "train": "训练室",
    "manufacture": "制造站",
    "trade": "贸易站",
    "power": "发电站",
}


class AgentSelectionNotReady(RuntimeError):
    """当前页面不足以继续选人；交由排班原有重试恢复，不结束任务线程。"""


class AgentCardObservationNotReady(AgentSelectionNotReady):
    """当前页的卡片位置、名字或选中边框尚未确认。"""


class AgentPageNotAdvanced(AgentSelectionNotReady):
    """当前列表无法继续翻页，调用方可以切换职业筛选后查找。"""


class AgentSelectionPageChanged(AgentSelectionNotReady):
    """选人已退出到入住信息页，禁止继续筛选复位或选人输入。"""


def agent_card_selected(img, scope, *, train=False):
    """读取选人卡片四周的青蓝色选中边框。

    scope 是 operator_list/operator_list_train 返回的姓名框。普通列表卡片
    比训练室卡片更宽且略高；只取边缘，避开立绘和技能图标。
    普通卡片右缘少量裁切时使用可见的三条边；证据不足时返回 None。
    """
    if not isinstance(img, np.ndarray) or img.ndim != 3 or scope is None:
        return None
    (name_left, name_top), (name_right, name_bottom) = scope
    if train:
        left, right = name_left - 19, name_right + 10
        top, bottom = name_top - 366, name_bottom + 20
    else:
        # alexsun 归档普通选人页实测：姓名框 (631,488)-(820,520)，
        # 蓝框约 (609,113)-(834,536)。
        # 选中蓝框会扩宽姓名分割区域；普通卡片宽度固定，不能随右边界移动。
        left, right = name_left - 22, name_left + 203
        top, bottom = name_top - 375, name_bottom + 16
    if left < 0 or top < 0 or right > img.shape[1] or bottom > img.shape[0]:
        # 普通卡片仅右缘缺失、至少 95% 宽度可见时仍可判断；其余越界保持未知。
        if (
            train
            or left < 0
            or top < 0
            or bottom > img.shape[0]
            or right <= img.shape[1]
            or img.shape[1] - left < (right - left) * 0.95
        ):
            return None
        frame = cv2.cvtColor(img[top:bottom, left : img.shape[1]], cv2.COLOR_RGB2HSV)
        blue = cv2.inRange(frame, (96, 140, 140), (105, 255, 255)) > 0
        upper = blue[:8, 8:-8].mean()
        lower = blue[-8:, 8:-8].mean()
        left_side = blue[8:-8, :8].mean()
        # 屏幕右缘不是卡片竖边；必须同时看到上、下、左三条真实边框。
        if upper > 0.45 and lower > 0.45 and left_side > 0.45:
            return True
        lower_inner = blue[-8:-5, 8:-8].mean()
        if max(upper, lower) < 0.45 and lower_inner < 0.20 and left_side < 0.20:
            return False
        # 保留相邻蓝框仅擦到一条竖边时的未选中判定。
        if min(upper, lower) < 0.20 and max(upper, lower) < 0.45:
            return False
        return None
    frame = cv2.cvtColor(img[top:bottom, left:right], cv2.COLOR_RGB2HSV)
    # 卡片右侧阴影使蓝框亮度降到约 140，仍须满足色相和饱和度条件。
    blue = cv2.inRange(frame, (96, 140, 160 if train else 140), (105, 255, 255)) > 0
    # 略过角落；完整边框用上下沿及任一侧确认。
    upper = blue[:8, 8:-8].mean()
    lower = blue[-8:, 8:-8].mean()
    left_side = blue[8:-8, :8].mean()
    right_side = blue[8:-8, -8:].mean()
    if upper > 0.45 and lower > 0.45 and max(left_side, right_side) > 0.45:
        return True
    # 滚动通告只遮住上沿时，使用下沿靠上的像素和左右两侧确认。
    # 相邻下排卡片的上沿会落在下沿靠下的像素，不能据此判为选中。
    lower_inner = blue[-8:-5, 8:-8].mean()
    if lower_inner > 0.45 and min(left_side, right_side) > 0.45:
        return True
    # 上沿的青色状态图标与下排蓝框可同时覆盖少量横边。
    # 两条竖边及下沿前段均缺失时，普通卡片明确未选中。
    if (
        not train
        and max(upper, lower) < 0.45
        and lower_inner < 0.20
        and max(left_side, right_side) < 0.20
    ):
        return False
    # 相邻卡片只隔几像素，前一张的边框可能擦到本卡一条边；
    # 另一条边仍明显缺失时判为未选中，避免整页校验一直等待。
    if min(upper, lower) < 0.20 and max(upper, lower) < 0.45:
        return False
    return None


def selection_title_matches(img, room_type):
    if not isinstance(img, np.ndarray) or img.shape != (1080, 1920, 3):
        return False
    title = 255 - cv2.cvtColor(img[140:198, 40:170], cv2.COLOR_RGB2GRAY)
    if np.ptp(title) < 65:
        return False
    try:
        template = loadres(f"room/{room_type}", gray=True)
    except (OSError, cv2.error):
        return False
    if template is None or template.shape != (41, 114) or np.ptp(template) < 32:
        return False
    # 选人页标题为浅底深字，字宽略小于房间详情的同一标题。
    template = cv2.resize(template, (111, 40))
    score = cv2.matchTemplate(title, template, cv2.TM_CCOEFF_NORMED)
    return cv2.minMaxLoc(score)[1] >= 0.92


def selection_shows_power_plant(img):
    return selection_title_matches(img, "power")


def train_card_selected(img, scope):
    """保留训练室调用接口，复用所有选人页的蓝框检测。"""
    return agent_card_selected(img, scope, train=True)


@dataclass
class AgentPageObservation:
    """相邻操作间的一次性稳定观测，消费后仍须读取新画面复核。"""

    page: tuple
    recognizer: object
    image: object
    full_scan: bool
    train: bool
    before: tuple | None = None

    def consume(self, recognizer, *, full_scan, train):
        valid = (
            self.image is not None
            and self.recognizer is recognizer
            and getattr(recognizer, "_img", None) is self.image
            and self.full_scan == full_scan
            and self.train == train
        )
        page = self.page if valid else None
        # 包括模式不符在内，尝试消费即失效，不跨输入或房间保留坐标。
        self.page = ()
        self.recognizer = self.image = None
        self.before = None
        return page


def fixed_selection_profile(function):
    """Keep AUTO's strategy unchanged during one selection operation."""

    @wraps(function)
    def wrapped(self, *args, **kwargs):
        previous = getattr(self, "_selection_profile_snapshot", None)
        if previous is None:
            self._selection_profile_snapshot = self.performance_profile
        try:
            return function(self, *args, **kwargs)
        finally:
            if previous is None:
                del self._selection_profile_snapshot

    return wrapped


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
_ARRANGE_ORDER_X_TRAINEE = {"等级": 1291, "稀有度": 1438, "信赖值": 1585}


def _room_name_mask(gray):
    text = thres2(gray, 200)
    left, _, width, _ = cv2.boundingRect(text)
    if not width:
        return text

    # 从最右侧的白点查找挂锁底色。进驻面板上的橙色方块约为 34×34 像素。
    right = left + width - 1
    seed = (right, int(text[:, right].argmax()))
    area, _, _, (x, y, w, h) = cv2.floodFill(thres2(gray, 100), None, seed, 0)
    if not (30 <= w <= 37 and 30 <= h <= 37):
        return text
    badge = text[y : y + h, x : x + w]
    if area - cv2.countNonZero(badge) > w * h // 2:
        # 底色占方块过半，白色挂锁轮廓内有锁梁和锁孔两处空隙。
        contours, hierarchy = cv2.findContours(
            badge, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )
        if len(contours) == 3 and np.count_nonzero(hierarchy[0, :, 3] >= 0) == 2:
            badge.fill(0)
    return text


def _foreground_width(img):
    points = cv2.findNonZero(img)
    if points is None:
        return 0
    return cv2.boundingRect(points)[2]


OP_ROOM_WIDTH = {
    operator: _foreground_width(template) for operator, template in OP_ROOM.items()
}


@lru_cache(maxsize=1)
def _packed_room_names():
    if not OP_ROOM or any(
        t.shape != ROOM_NAME_TEMPLATE_SHAPE for t in OP_ROOM.values()
    ):
        return None
    pixels = np.stack(list(OP_ROOM.values())).reshape(len(OP_ROOM), -1)
    if np.any((pixels != 0) & (pixels != 255)):
        return None
    return tuple(OP_ROOM), np.packbits(pixels, axis=1), np.count_nonzero(pixels, axis=1)


def _room_name_candidates(sample):
    model = _packed_room_names()
    if model is None:
        return OP_ROOM
    names, templates, template_counts = model
    patches = np.lib.stride_tricks.sliding_window_view(sample, ROOM_NAME_TEMPLATE_SHAPE)
    patches = patches.reshape(-1, np.prod(ROOM_NAME_TEMPLATE_SHAPE))
    patch_counts = np.count_nonzero(patches, axis=1)
    distances, offsets = cv2.batchDistance(
        templates,
        np.packbits(patches, axis=1),
        cv2.CV_32S,
        normType=cv2.NORM_HAMMING,
        K=len(patches),
    )
    # 二值图的归一化相关系数等于共同白点数除以两图白点数的几何平均。
    template_counts = template_counts[:, None]
    sample_counts = patch_counts[offsets]
    overlap_twice = template_counts + sample_counts - distances
    norm = np.sqrt(np.maximum(template_counts * sample_counts, 1))
    scores = (overlap_twice / (2 * norm)).max(axis=1)
    # 留出 OpenCV 浮点误差以及长名字前缀判定的余量，候选仍用原模板核验。
    minimum = scores.max() * PREFIX_NAME_SCORE_RATIO - 1e-5
    return [names[i] for i in np.flatnonzero(scores >= minimum)]


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
    _packed_room_names.cache_clear()


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
    agent_selection_positions = (
        (0.35, 0.35),
        (0.35, 0.75),
        (0.45, 0.35),
        (0.45, 0.75),
        (0.55, 0.35),
    )

    @property
    def performance_profile(self):
        snapshot = getattr(self, "_selection_profile_snapshot", None)
        if snapshot is not None:
            return snapshot
        profile = effective_performance_profile(
            config.conf,
            config.operation_feedback_avg,
            config.operation_feedback_count,
            config.operation_feedback_mode,
            config.operation_feedback_cap,
        )
        if config.conf.performance_mode == "auto":
            config.operation_feedback_mode = profile.mode
        # 未设置档位的旧调用方仍可通过布尔值控制策略；明确选择档位后
        # 布尔兼容字段不再覆盖所选策略，也不改变用户的时间参数。
        if (
            config.conf.performance_mode in PERFORMANCE_PRESETS
            and "performance_mode" not in config.conf.model_fields_set
        ):
            legacy_enabled = config.conf.low_frame_rate_mode
            if legacy_enabled != profile.low_frame_rate:
                from dataclasses import replace

                return replace(
                    profile,
                    mode="medium" if legacy_enabled else "high",
                    low_frame_rate=legacy_enabled,
                )
        return profile

    @staticmethod
    def record_operation_feedback(extra_observations):
        """Track how many additional frames an input needed before feedback."""
        sample = min(max(extra_observations, 0), 3)
        previous = config.operation_feedback_avg
        config.operation_feedback_avg = (
            sample if previous is None else previous * 0.75 + sample * 0.25
        )
        config.operation_feedback_count += 1

    @staticmethod
    def record_selection_failure():
        """Downgrade AUTO after repeated selection failures, not unrelated errors."""
        if getattr(config.conf, "performance_mode", None) != "auto":
            return
        config.operation_failure_streak += 1
        config.operation_recovery_successes = 0
        if config.operation_failure_streak < 2:
            return
        current = (
            config.operation_feedback_mode
            or effective_performance_profile(
                config.conf,
                config.operation_feedback_avg,
                config.operation_feedback_count,
                mode_cap=config.operation_feedback_cap,
            ).mode
        )
        lowered = lower_performance_mode(current)
        config.operation_feedback_cap = lowered
        config.operation_feedback_mode = lowered
        config.operation_failure_streak = 0
        logger.warning(f"选人连续失败，自动性能档位降至 {lowered}")

    @staticmethod
    def record_selection_success():
        """Lift a failure downgrade after three completed selection workflows."""
        if getattr(config.conf, "performance_mode", None) != "auto":
            return
        config.operation_failure_streak = 0
        if config.operation_feedback_cap is None:
            return
        config.operation_recovery_successes += 1
        if config.operation_recovery_successes >= 3:
            config.operation_feedback_cap = None
            config.operation_recovery_successes = 0

    @property
    def low_frame_rate_mode(self):
        return self.performance_profile.low_frame_rate

    def selection_transition_timing(self):
        profile = self.performance_profile
        return profile.poll_interval, profile.transition_attempts

    def selection_observation_timing(self):
        profile = self.performance_profile
        attempts = (
            6
            if not profile.low_frame_rate
            else max(profile.stable_page_matches + 1, profile.transition_attempts)
        )
        return profile.poll_interval, attempts

    def tap_reorder_card(self, scope):
        interval = {"xhigh": 0, "high": 0.1}.get(self.performance_profile.mode, 0.2)
        self.tap(scope, interval=interval)

    def reorder_selected_agents(self, agents, actual, *, confirm_each=False):
        """按清空反馈帧的姓名重新选入。序号不可辨时逐次核对已选集合。"""
        logger.debug(
            f"选人重排清空：性能档位{self.performance_profile.mode}，页面已选{actual}，目标{agents}"
        )
        page = self.clear_agent_selection()
        scopes = dict(page)
        if len(scopes) != len(page):
            raise AgentSelectionNotReady("清空后卡片姓名重复，返回房间重试")
        for index, name in enumerate(agents):
            scope = scopes.get(name)
            if scope is None or scope[1][0] > 1790:
                raise AgentSelectionNotReady(
                    f"重排时未读到可点击的{name}，返回房间重试"
                )
            self.tap_reorder_card(scope)
            if confirm_each:
                scopes = {}
                if (
                    self.wait_for_arranged_agents(
                        agents[: index + 1], ordered=False, card_scopes=scopes
                    )
                    is None
                ):
                    raise AgentSelectionNotReady(
                        f"重排时未确认{name}进入第{index + 1}位"
                    )

    def fill_visible_selection_suffix(self, agents, first, *, wait_for_feedback=False):
        """核实保留岗位的序号和剩余目标的未选状态，再按目标顺序补齐。"""
        scopes, numbers = {}, {}
        self.wait_for_arranged_agents(
            agents[:first],
            ordered=False,
            full_scan=False,
            visible_only=True,
            quick_check=not wait_for_feedback,
            slot_numbers=numbers,
            card_scopes=scopes,
        )
        expected = {name: index for index, name in enumerate(agents, 1)}
        if numbers != {name: expected[name] for name in agents[:first]}:
            return False
        suffix = [scopes.get(name) for name in agents[first:]]
        if any(
            scope is None
            or scope[1][0] > 1790
            or agent_card_selected(self.recog.img, scope) is not False
            for scope in suffix
        ):
            return False
        for scope in suffix:
            self.tap_reorder_card(scope)
        numbers.clear()
        self.wait_for_arranged_agents(
            agents,
            ordered=False,
            full_scan=False,
            visible_only=True,
            quick_check=False,
            slot_numbers=numbers,
        )
        return numbers == expected

    def clear_agent_selection(self, room=None):
        """取消暂选，确认可见卡片的旧蓝框消失后才继续选人。"""
        if room in ("factory", "contact", "train") or (
            room
            and room.startswith("room")
            and len(self.op_data.plan.get(room, ())) == 1
        ):
            # 加工站、办公室及训练室协助位没有清空按钮，逐卡取消实读蓝框。
            self.require_agent_selection_page()
            before_sort = getattr(self.recog, "_img", None)
            self.switch_arrange_order("技能", room)
            sorted_image = getattr(self.recog, "_img", None)
            observation = None
            if (
                isinstance(sorted_image, np.ndarray)
                and sorted_image is not before_sort
                and not self.low_frame_rate_mode
                and not self.find("connecting")
            ):
                self.require_agent_selection_page()
                observation = self.current_search_page(full_scan=True)
            page = self.wait_for_agent_page(
                observation=observation, wait_after_observation=True
            )
            self.require_agent_selection_page()
            if (
                not page
                or any(not name or scope is None for name, scope in page)
                or page[0][1][0][0] > 650
            ):
                raise AgentSelectionNotReady("单岗位选人名单不完整，返回房间重试")
            states = [
                (scope, agent_card_selected(self.recog.img, scope)) for _, scope in page
            ]
            selected = [scope for scope, state in states if state is True]
            if any(state is None for _, state in states) or len(selected) > 1:
                raise AgentSelectionNotReady("单岗位选中状态不明确，返回房间重试")
            if selected:
                self.tap(
                    selected[0],
                    interval=0.3 if self.performance_profile.mode == "high" else 0.5,
                )
            return self.wait_for_cleared_selection()
        self.tap(
            (self.recog.w * 0.38, self.recog.h * 0.95),
            interval=0.3 if self.performance_profile.mode == "high" else 0.5,
        )
        return self.wait_for_cleared_selection()

    def wait_for_cleared_selection(self):
        read = self.agent_page_reader()
        poll_interval, max_attempts = self.selection_observation_timing()
        previous = None
        matches = 0
        capture_time = 0
        for attempt in range(max_attempts):
            if attempt:
                self.wait_for_next_observation(capture_time, poll_interval)
            else:
                self.recog.update()
            started = perf_counter()
            connecting = self.find("connecting")
            capture_time = perf_counter() - started
            if connecting:
                previous, matches = None, 0
                continue
            try:
                page = read(self.recog.img)
            except (MowerExit, AgentSelectionPageChanged):
                raise
            except Exception:
                self.require_agent_selection_page()
                previous, matches = None, 0
                continue
            self.check_agent_page(page)
            if page and all(
                name and agent_card_selected(self.recog.img, scope) is False
                for name, scope in page
            ):
                matches = matches + 1 if self.same_agent_page(page, previous) else 1
                if matches >= self.performance_profile.stable_page_matches:
                    return page
                previous = page
            else:
                previous, matches = None, 0
        raise AgentSelectionNotReady("清空选择后旧蓝框尚未消失，返回房间重试")

    profession_labels = PROFESSION_LABELS

    def _arrange_order_x(self, current_room):
        """排序列→x 坐标单一来源（#85：detect/switch 共用，取实机校准的读坐标）。"""
        if current_room == "train_trainee":
            return _ARRANGE_ORDER_X_TRAINEE
        if current_room.startswith("dormitory") or current_room == "central":
            return _ARRANGE_ORDER_X_DORM
        return _ARRANGE_ORDER_X

    def detect_arrange_order(self, current_room):
        y = 64 if current_room == "train_trainee" else 70
        order = self._arrange_order_x(current_room)
        left, right = min(order.values()), max(order.values()) + 5
        # 只转换排序箭头覆盖区域，坐标与检测顺序仍由原房型映射决定。
        region = self.recog.img[y : y + 13, left:right]
        if region.size == 0:
            return None
        hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (95, 100, 100), (105, 255, 255))
        for name, x in order.items():
            x -= left
            if np.count_nonzero(mask[:3, x : x + 5]):
                return (name, False)
            if np.count_nonzero(mask[10:13, x : x + 5]):
                return (name, True)

    def switch_arrange_order(
        self, name, current_room, ascending=False, *, refresh=True
    ):
        """按当前箭头设置排序，需要将已选干员重新置顶时刷新列表。"""
        if isinstance(ascending, str):
            ascending = ascending == "true"
        if config.stop_mower.is_set():
            raise MowerExit
        target = (name, ascending)
        position = (self._arrange_order_x(current_room)[name], 60)
        slow = self.low_frame_rate_mode
        if slow:
            poll_interval, max_attempts = self.selection_observation_timing()
            self.recog.update()
            initial_reads = max_attempts
        else:
            poll_interval, max_attempts = self.selection_transition_timing()
            initial_reads = max_attempts + 1
        capture_time = 0
        for attempt in range(initial_reads):
            if attempt:
                self.wait_for_next_observation(capture_time, poll_interval)
            started = perf_counter()
            before = self.detect_arrange_order(current_room)
            capture_time = perf_counter() - started
            if before is not None:
                break
        else:
            raise AgentSelectionNotReady("无法读取干员排序状态，返回房间重试")
        if before == target and not refresh:
            return
        for _ in range(2):
            self.tap(position, interval=0.5 if slow else 0.1)
            previous = None
            capture_time = 0
            first_change_attempt = None
            for attempt in range(max_attempts):
                if attempt:
                    self.wait_for_next_observation(capture_time, poll_interval)
                started = perf_counter()
                actual = self.detect_arrange_order(current_room)
                capture_time = perf_counter() - started
                if actual is not None and actual != before:
                    if first_change_attempt is None:
                        first_change_attempt = attempt
                    if not slow or actual == previous:
                        self.record_operation_feedback(first_change_attempt)
                        break
                previous = actual
            else:
                raise AgentSelectionNotReady(
                    "干员排序点击后尚未确认画面变化，返回房间重试"
                )
            if actual == target:
                return
            before = actual
        raise AgentSelectionNotReady("干员排序未到达目标状态，返回房间重试")

    def wait_for_next_observation(self, capture_time, interval=0.5):
        """仅扣除取帧耗时，名字识别耗时不能替代等待；零等待也清除旧帧。"""
        self.sleep(max(0, interval - capture_time))

    @staticmethod
    def same_agent_page(left, right, *, allow_unknown=False):
        """比较整页名字及卡片位置，允许识别边界的少量像素抖动。"""
        if not left or not right or len(left) != len(right):
            return False
        for (name, scope), (old_name, old_scope) in zip(left, right):
            if (
                (not name and not allow_unknown)
                or name != old_name
                or scope is None
                or old_scope is None
            ):
                return False
            if any(
                abs(value - old_value) > 3
                for point, old_point in zip(scope, old_scope)
                for value, old_value in zip(point, old_point)
            ):
                return False
        return True

    @staticmethod
    def agent_page_reader(
        *, full_scan=True, train=False, seed_image=None, seed_page=None
    ):
        """名字区域未变化时复用已确认页面的姓名匹配结果。"""

        def name_key(img):
            if isinstance(img, np.ndarray):
                left, right = (
                    (545, 1920) if train else (600, 1920 if full_scan else 1860)
                )
                rows = ((479, 506), (895, 922)) if train else ((488, 520), (909, 941))
                return tuple(img[y1:y2, left:right].tobytes() for y1, y2 in rows)
            return None

        previous_key = name_key(seed_image) if seed_page is not None else None
        previous_ret = seed_page

        def read(img):
            nonlocal previous_key, previous_ret
            key = name_key(img)
            if key is not None and key == previous_key:
                logger.debug("选人名字区域未变化，复用已确认的识别结果")
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

    def observe_agent_page(self, page, *, full_scan=True, train=False, before=None):
        return AgentPageObservation(
            tuple(
                (name, tuple(tuple(point) for point in scope)) for name, scope in page
            ),
            self.recog,
            getattr(self.recog, "_img", None),
            full_scan,
            train,
            None
            if before is None
            else tuple(
                (name, tuple(tuple(point) for point in scope)) for name, scope in before
            ),
        )

    def current_search_page(
        self, *, full_scan, before=(), profession=None, branch=None, visible_target=None
    ):
        """复用已读的进房画面，或名单已随职业、分支改变的筛选画面。"""
        img = getattr(self.recog, "_img", None)
        if (self.low_frame_rate_mode and visible_target is None) or not isinstance(
            img, np.ndarray
        ):
            return None
        try:
            page = operator_list(img, full_scan=full_scan)
        except (MowerExit, AgentSelectionPageChanged):
            raise
        except Exception:
            self.require_agent_selection_page()
            return None
        visible = page if full_scan else self._cards_before_profession_sidebar(page)
        if visible_target is not None and not any(
            name == visible_target for name, _ in visible
        ):
            return None
        if self.check_agent_page(visible):
            return None
        if profession:
            # 职业可先于名单高亮。名单须出现新的同职业干员，其余职业只允许已选卡片。
            previous = {name for name, _ in before}
            changed = False
            for name, scope in visible:
                if agent_profession.get(name) == profession and (
                    not branch or agent_branch.get(name) == branch
                ):
                    if name not in previous:
                        changed = True
                    continue
                if agent_card_selected(img, scope) is not True:
                    return None
            if not before or not changed:
                return None
        return self.observe_agent_page(visible, full_scan=full_scan)

    def require_agent_selection_page(self):
        """同帧房间页签或二次确认表明选人页面已变化。"""
        if self.find("double_confirm/main"):
            raise AgentSelectionPageChanged(
                "选人页面出现二次确认，停止选人并返回房间实读重试"
            )
        if self.find("arrange_check_in_on") or self.find("recycle/dashboard"):
            raise AgentSelectionPageChanged(
                "选人页面已退出到当前房间入住信息，停止选人并返回房间实读重试"
            )

    def check_agent_page(self, page, *, train=False):
        """异常名单检查退出并返回 True；正常名单不检查页面。"""
        if (
            not page
            or any(not name or scope is None for name, scope in page)
            or (not train and page[0][1][0][0] > 650)
        ):
            self.require_agent_selection_page()
            return True
        return False

    @staticmethod
    def agent_page_has_right_gap(img, page, *, train=False):
        """名字横带右侧全为空白时，按住画面不能作为抬手后坐标。"""
        if not isinstance(img, np.ndarray):
            return False
        if not page or any(scope is None for _, scope in page):
            return True
        left = max(scope[1][0] for _, scope in page) + 4
        # 两种布局均排除职业栏；半张卡片也阻止空白判定。
        right = 1790
        if right - left < 20:
            return False
        rows = ((479, 506), (895, 922)) if train else ((488, 520), (909, 941))
        return all(
            np.mean(np.min(img[bottom - 8 : bottom, left:right], axis=2) > 85) >= 0.9
            for _, bottom in rows
        )

    def wait_for_agent_page(
        self,
        *,
        full_scan=True,
        train=False,
        before=None,
        observation=None,
        exclude_sidebar=False,
        wait_after_observation=False,
    ):
        """先复核当前页；滑动后不把连续两张相同的旧画面当成新页。"""
        seed_image = observation.image if observation is not None else None
        previous = (
            observation.consume(self.recog, full_scan=full_scan, train=train)
            if observation is not None
            else None
        )
        read = self.agent_page_reader(
            full_scan=full_scan,
            train=train,
            seed_image=seed_image,
            seed_page=previous or None,
        )
        stable = False
        stable_matches = 0
        first_changed_attempt = None
        ret = []
        capture_time = 0
        poll_interval, max_attempts = self.selection_observation_timing()
        for attempt in range(max_attempts):
            # 排序箭头先于卡片到位，两次姓名观测仍须按原间隔取帧。
            if attempt or (wait_after_observation and previous):
                self.wait_for_next_observation(capture_time, poll_interval)
            elif previous != ():
                self.recog.update()
            started = perf_counter()
            connecting = self.find("connecting")
            capture_time = perf_counter() - started
            logger.debug(
                f"选人等待及截图检查耗时：{(perf_counter() - started) * 1000:.0f} ms"
            )
            if connecting:
                previous = None
                stable = False
                stable_matches = 0
                first_changed_attempt = None
                continue
            try:
                ret = read(self.recog.img)
                if exclude_sidebar:
                    ret = self._cards_before_profession_sidebar(ret)
            except (MowerExit, AgentSelectionPageChanged):
                raise
            except Exception as e:
                self.require_agent_selection_page()
                logger.debug(f"翻页名单读取失败，原地复核：{e}")
                previous = None
                stable = False
                stable_matches = 0
                continue
            self.check_agent_page(ret, train=train)
            if previous == () and self.agent_page_has_right_gap(
                self.recog.img, ret, train=train
            ):
                # 末页抬手后会回弹，按住帧不能计入两帧位置稳定证据。
                previous = None
                continue
            if (
                before is not None
                and ret
                and first_changed_attempt is None
                and not self.same_agent_page(ret, before, allow_unknown=True)
            ):
                first_changed_attempt = attempt
            # 搜索时允许无关卡片识别为空；仍须整页位置稳定，且只点击识别出的目标。
            # 最终名单校验继续拒绝空名字。
            if self.same_agent_page(ret, previous, allow_unknown=True):
                stable_matches += 1
            else:
                stable_matches = 0
            stable = stable_matches >= self.performance_profile.stable_page_matches
            if stable and (
                before is None
                or not self.same_agent_page(ret, before, allow_unknown=True)
            ):
                if before is not None:
                    self.record_operation_feedback(
                        first_changed_attempt
                        if first_changed_attempt is not None
                        else attempt
                    )
                logger.debug(f"确认当前干员页：{ret}")
                return ret
            previous = ret
        if stable:
            # 滑动后仍是旧页：交给调用方确认手势未推进，不能当成新页跳过。
            return ret
        raise AgentCardObservationNotReady(
            "干员页面仍在移动或名字识别不全，返回房间重试"
        )

    def swipe_agent_page(
        self, page, agent, *, full_scan=True, train=False, return_page=False
    ):
        """保留两列重叠，确认翻页生效；未推进时只做一次短距离复核。"""
        if any(scope is None for _, scope in page):
            self.require_agent_selection_page()
            raise AgentSelectionNotReady("干员卡片位置不明，返回房间重试")
        columns = []
        right_edge = -1
        for left, right in sorted(scope for _, scope in page):
            if left[0] > right_edge:
                columns.append(left)
            right_edge = max(right_edge, right[0])
        if len(columns) < 2:
            raise AgentPageNotAdvanced("可识别干员列不足，返回房间重试")
        first_x = columns[0][0]
        if not self.low_frame_rate_mode:
            start = page[-2][1][0]
            if start[0] < columns[1][0]:
                start = columns[-1]
            self.swipe_noinertia(
                start,
                (first_x - start[0], 0),
                interval=0.1 if self.performance_profile.mode == "high" else 0.2,
                capture=True,
            )
            return (
                (
                    1,
                    self.observe_agent_page(
                        (), full_scan=full_scan, train=train, before=page
                    ),
                )
                if return_page
                else 1
            )
        start_x = columns[-2][0] if len(columns) > 2 else columns[-1][0]
        y = page[0][1][0][1]
        for attempt in range(2):
            # 第二次只移动一列，防止第一次延迟完成时又跨过一整页。
            distance = first_x - (start_x if attempt == 0 else columns[1][0])
            if attempt:
                self.swipe_noinertia(
                    (start_x, y), (distance, 0), retry=True, capture=True
                )
            else:
                self.swipe_noinertia((start_x, y), (distance, 0), capture=True)
            actual = self.wait_for_agent_page(
                full_scan=full_scan,
                train=train,
                before=page,
                observation=self.observe_agent_page(
                    (), full_scan=full_scan, train=train
                ),
            )
            if not self.same_agent_page(actual, page, allow_unknown=True):
                if return_page:
                    return attempt + 1, self.observe_agent_page(
                        actual, full_scan=full_scan, train=train
                    )
                return attempt + 1
            logger.debug(f"翻页第{attempt + 1}次未确认推进，仍需查找：{agent}")
        raise AgentPageNotAdvanced(
            f"两次滑动后整页干员及位置均未变化，可能已到末尾或手势未生效；"
            f"返回房间重试，仍需查找：{agent}"
        )

    def _allow_dorm_filler_mood(self, name, mood):
        return not trade_order_dorm_entry_blocked(
            self.op_data, name, card_mood=mood, require_known=True
        )

    def _dorm_entry_mood_check(self, agents, room):
        from arknights_mower.utils.operators import TRADE_ORDER_AGENTS

        new_runners = {
            name
            for index, name in enumerate(agents)
            if name in TRADE_ORDER_AGENTS
            and not getattr(
                self.op_data.operators.get(name), "current_room", ""
            ).startswith("dorm")
            and self.op_data.is_dynamic_dorm_position(room, index, name)
        }
        if not new_runners:
            return None

        def check_dorm_entry(name, mood):
            if name not in new_runners or self._allow_dorm_filler_mood(name, mood):
                return
            if mood is not None:
                observed_at = datetime.now()
                self.op_data.dorm_mood_estimates[name] = (mood, observed_at)
                if self.op_data.mood_calculation_enabled:
                    self.op_data.mood_model.observe(name, mood, observed_at)
            raise AgentSelectionNotReady(
                f"{name} 的心情不符合跑单干员入住条件，重新选择宿舍补位"
            )

        return check_dorm_entry

    @staticmethod
    def _cards_before_profession_sidebar(page):
        return tuple(
            (name, scope) for name, scope in page if scope and scope[1][0] <= 1790
        )

    @staticmethod
    def _cards_in_slot_order(page, slots):
        if slots is None:
            return page
        return sorted(
            (card for card in page if card[0] in slots),
            key=lambda card: slots[card[0]],
        )

    @staticmethod
    def next_page_may_contain(page, earlier_names, target):
        names = tuple(name for name, _ in page)
        if len(names) < 5 or not all(names) or target not in earlier_names:
            return False
        tail = names[-3:]
        if tail[-1] not in earlier_names:
            return False
        end = earlier_names.index(tail[-1]) + 1
        # 末尾三人顺序仍相同，保留两列重叠后，一页足以覆盖先前见过的目标。
        return (
            earlier_names[max(0, end - 3) : end] == tail
            and target in earlier_names[end : end + len(names) - 4]
        )

    def _select_named_card(
        self,
        name,
        scope,
        *,
        interval,
        train=False,
        respect_train_selection=False,
        page_checked=False,
    ):
        selected = (
            agent_card_selected(self.recog.img, scope, train=train)
            if isinstance(self.recog.img, np.ndarray)
            or (respect_train_selection and train)
            else False
        )
        if selected is None:
            logger.debug(
                f"选人卡片边框未确认：干员{name}，姓名范围{scope}，"
                f"画面尺寸{getattr(self.recog.img, 'shape', None)}，训练室{train}"
            )
            if not page_checked:
                self.require_agent_selection_page()
            raise AgentCardObservationNotReady("干员选中边框不清晰，返回房间重试")
        if selected:
            logger.debug(f"干员 {name} 已有蓝框，跳过再次点击")
        else:
            self.tap(scope, interval=interval)

    def scan_agent(
        self,
        agent: list[str],
        error_count=0,
        max_agent_count=-1,
        full_scan=True,
        train=False,
        observation=None,
        respect_train_selection=False,
        mood_estimates=None,
        skip_full_mood=False,
        require_full_mood=False,
        mood_check=None,
        exclude_sidebar=False,
        target_slots=None,
    ):
        if not self.low_frame_rate_mode:
            return self._scan_agent_fast(
                agent,
                error_count,
                max_agent_count,
                full_scan,
                train,
                respect_train_selection,
                mood_estimates,
                skip_full_mood,
                observation=observation,
                require_full_mood=require_full_mood,
                mood_check=mood_check,
                exclude_sidebar=exclude_sidebar,
                target_slots=target_slots,
            )
        # 无目标时仍返回已复核的页面供调用方判断，但不进行点击。
        ret = self.wait_for_agent_page(
            full_scan=full_scan, train=train, observation=observation
        )
        select_name = []
        while True:
            if exclude_sidebar:
                ret = self._cards_before_profession_sidebar(ret)
            eligible = self.observe_agent_moods(
                ret,
                agent,
                mood_estimates,
                skip_full_mood,
                train=train,
                require_full=require_full_mood,
                mood_check=mood_check,
            )
            target = next(
                (
                    card
                    for card in self._cards_in_slot_order(ret, target_slots)
                    if card[0] in eligible
                ),
                None,
            )
            if target is None:
                return select_name, ret
            name, scope = target
            self._select_named_card(
                name,
                scope,
                interval=0.2,
                train=train,
                respect_train_selection=respect_train_selection,
            )
            select_name.append(name)
            agent.remove(name)
            if not agent or (
                max_agent_count != -1 and len(select_name) >= max_agent_count
            ):
                return select_name, ret
            # 点击可能改变卡片位置；下一名必须从新页面重新定位。
            ret = self.wait_for_agent_page(full_scan=full_scan, train=train)

    def _scan_agent_fast(
        self,
        agent,
        error_count,
        max_agent_count,
        full_scan,
        train,
        respect_train_selection=False,
        mood_estimates=None,
        skip_full_mood=False,
        observation=None,
        require_full_mood=False,
        mood_check=None,
        exclude_sidebar=False,
        target_slots=None,
    ):
        """普通设备沿用单帧批量选人及缩小扫描区域的识别重试。"""
        try:
            before = observation.before if observation is not None else None
            held_page = (
                observation.consume(self.recog, full_scan=full_scan, train=train)
                if observation is not None
                else None
            )
            if held_page is None:
                self.recog.update()
            ret = held_page
            while self.find("connecting"):
                ret = None
                self.sleep()
            ret = ret or (
                operator_list_train(self.recog.img)
                if train
                else operator_list(self.recog.img, full_scan=full_scan)
            )
            page_checked = self.check_agent_page(ret, train=train)
        except (MowerExit, AgentSelectionPageChanged):
            raise
        except Exception:
            self.require_agent_selection_page()
            if error_count >= 2:
                raise
            return self._scan_agent_fast(
                agent,
                error_count + 1,
                max_agent_count,
                False,
                train,
                respect_train_selection,
                mood_estimates,
                skip_full_mood,
                require_full_mood=require_full_mood,
                mood_check=mood_check,
                exclude_sidebar=exclude_sidebar,
                target_slots=target_slots,
            )
        unchanged_held_page = before is not None and self.same_agent_page(
            ret, before, allow_unknown=True
        )
        if held_page == () and (
            unchanged_held_page
            or self.agent_page_has_right_gap(self.recog.img, ret, train=train)
        ):
            logger.debug("按住画面未推进或末页右侧空白，抬手后重新确认卡片位置")
            ret = self.wait_for_agent_page(
                full_scan=full_scan,
                train=train,
                before=before if unchanged_held_page else None,
            )
        if exclude_sidebar:
            ret = self._cards_before_profession_sidebar(ret)
        eligible = self.observe_agent_moods(
            ret,
            agent,
            mood_estimates,
            skip_full_mood,
            train=train,
            require_full=require_full_mood,
            mood_check=mood_check,
        )
        selected = []
        for name, scope in self._cards_in_slot_order(ret, target_slots):
            if name and name in eligible:
                self._select_named_card(
                    name,
                    scope,
                    interval=0,
                    train=train,
                    respect_train_selection=respect_train_selection,
                    page_checked=page_checked,
                )
                selected.append(name)
                agent.remove(name)
                if max_agent_count != -1 and len(selected) >= max_agent_count:
                    break
        return selected, ret

    def observe_agent_moods(
        self,
        page,
        candidates,
        estimates,
        skip_full,
        *,
        train=False,
        require_full=False,
        mood_check=None,
    ):
        """复用识别帧记录候选预估，不刷新截图或修改干员实读数据。"""
        eligible = set(candidates)
        if train:
            return eligible
        if getattr(getattr(self, "task", None), "emergency_staffing", False):
            from arknights_mower.utils.emergency_staffing import worker_block_reason

            temporary_workers = {
                name
                for room, row in self.task.plan.items()
                if room in self.op_data.plan and not room.startswith("dorm")
                for index, name in enumerate(row)
                if (op := self.op_data.operators.get(name)) is None
                or (op.current_room, op.current_index) != (room, index)
            }
            for name, scope in page:
                if name not in eligible or name not in temporary_workers:
                    continue
                mood = estimate_agent_mood(self.recog.img, scope)
                if mood is None:
                    self.op_data.dorm_mood_estimates.pop(name, None)
                else:
                    self.op_data.dorm_mood_estimates[name] = (mood, datetime.now())
                reason = worker_block_reason(self.op_data, name, mood, set())
                if reason and not getattr(self.task, "emergency_takeover", False):
                    raise AgentSelectionNotReady(
                        f"自动救急候选 {name} {reason}，取消本次选人"
                    )
        if estimates is None:
            if not require_full and mood_check is None:
                return eligible
            estimates = {}
        now = datetime.now()
        for name, scope in page:
            if name not in eligible:
                continue
            mood = estimate_agent_mood(self.recog.img, scope)
            if mood_check is not None and mood_check(name, mood) is False:
                eligible.discard(name)
            if mood is None:
                estimates.pop(name, None)
                if require_full:
                    eligible.discard(name)
                continue
            estimates[name] = (mood, now)
            if skip_full and mood >= 24:
                eligible.discard(name)
            if require_full and mood != 24:
                eligible.discard(name)
        return eligible

    @timed_step("verify")
    def wait_for_arranged_agents(
        self,
        agent,
        *,
        ordered=True,
        full_scan=True,
        train=False,
        observation=None,
        slot_numbers=None,
        visible_only=False,
        card_scopes=None,
        quick_check=None,
    ):
        """校验当前名单；低帧率适配还要求连续两帧的位置和名字一致。"""
        seed_image = observation.image if observation is not None else None
        page = (
            observation.consume(self.recog, full_scan=full_scan, train=train)
            if observation is not None
            else None
        )
        if not agent:
            return []
        read = self.agent_page_reader(
            full_scan=full_scan,
            train=train,
            seed_image=seed_image,
            seed_page=page,
        )
        previous = page[: len(agent)] if page else None
        stable = False
        stable_matches = 0
        previous_numbers = {}
        actual = []
        capture_time = 0
        poll_interval, max_attempts = self.selection_observation_timing()
        if quick_check is None:
            quick_check = visible_only
        if quick_check:
            max_attempts = self.performance_profile.stable_page_matches + 1
        for attempt in range(max_attempts):
            if attempt:
                self.wait_for_next_observation(capture_time, poll_interval)
            else:
                self.recog.update()
            started = perf_counter()
            connecting = self.find("connecting")
            capture_time = perf_counter() - started
            if connecting:
                previous = None
                stable = False
                stable_matches = 0
                continue
            try:
                ret = read(self.recog.img)
            except (MowerExit, AgentSelectionPageChanged):
                raise
            except Exception as e:
                self.require_agent_selection_page()
                logger.debug(f"选人名单读取失败，等待下一帧：{e}")
                previous = None
                stable = False
                stable_matches = 0
                continue
            page_checked = self.check_agent_page(ret, train=train)
            if not train and ret and ret[0][1] is not None and ret[0][1][0][0] > 650:
                logger.debug(
                    "选人列表左侧仍被裁切，原地等待，不读取后续卡片作为已选名单"
                )
                previous = None
                stable = False
                stable_matches = 0
                actual = []
                continue
            if train or isinstance(self.recog.img, np.ndarray):
                # 排序或筛选变化后，前几张卡并不一定都已选；重排前先读蓝框。
                states = [
                    (
                        name,
                        scope,
                        agent_card_selected(self.recog.img, scope, train=train),
                    )
                    for name, scope in ret
                ]
                uncertain = [
                    (name, scope)
                    for name, scope, state in states
                    if state is None and (not visible_only or name in agent)
                ]
                if uncertain:
                    if not page_checked:
                        self.require_agent_selection_page()
                    logger.debug(f"选人卡片边框未确认，等待下一帧：{uncertain}")
                    previous = None
                    stable = False
                    stable_matches = 0
                    continue
                selected = [(name, scope) for name, scope, state in states if state]
            else:
                selected = ret[: len(agent)]
            actual = [name for name, _ in selected]
            logger.debug(f"选人校验第{attempt + 1}次读取：{actual}")
            numbers = {}
            if slot_numbers is not None and not train:
                numbers = {
                    name: number
                    for name, scope in selected
                    if (number := selection_slot(self.recog.img, scope)) is not None
                }
            if (
                len(actual) == len(agent)
                and self.same_agent_page(
                    selected, previous if self.low_frame_rate_mode else selected
                )
                and (not self.low_frame_rate_mode or numbers == previous_numbers)
            ):
                stable_matches += 1
            else:
                stable_matches = 0
            previous_numbers = numbers
            stable = stable_matches >= self.performance_profile.stable_page_matches
            matches = actual == agent if ordered else sorted(actual) == sorted(agent)
            if (
                matches
                and stable
                and (
                    not visible_only
                    or slot_numbers is None
                    or len(numbers) == len(agent)
                )
            ):
                if slot_numbers is not None:
                    slot_numbers.update(numbers)
                if card_scopes is not None:
                    for name, scope in ret:
                        if name:
                            card_scopes[name] = None if name in card_scopes else scope
                return actual
            if stable and not self.low_frame_rate_mode and not visible_only:
                return None
            previous = selected
        if visible_only:
            return None
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
        observation=None,
        ordered=True,
    ):
        try:
            numbers = {}
            options = {} if ordered else {"ordered": False, "slot_numbers": numbers}
            actual = self.wait_for_arranged_agents(
                agent,
                full_scan=full_scan,
                train=train,
                observation=observation,
                **options,
            )
            if actual is None:
                return False
            if ordered or len(agent) == 1:
                return True
            if numbers == {name: index for index, name in enumerate(agent, 1)}:
                return True
            # 名单相同仍可能错序。调用者可从空选开始逐次核对新增的干员。
            return None
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
                    ordered=ordered,
                )
            else:
                logger.exception(e)
                raise e

    @timed_step("filter_reset")
    def swipe_left(
        self, right_swipe, special_filter, *, train=False, return_page=False
    ):
        if not self.low_frame_rate_mode and right_swipe == 0:
            # 没有翻页时无需复位；翻页后用职业筛选确保回到首列。
            return (0, None) if return_page else 0
        # 保留旧接口供选人调用；实际通过切换职业筛选复位，不再反向拖动。
        # 即使计数为零也要真正切换，重复点击当前筛选不能证明列表已归零。
        buttons = self._profession_filter_buttons()
        filter_was_closed = bool(buttons) and all(x > 1650 for _, x, _ in buttons)
        profession = special_filter or "ALL"
        temporary = (
            next(label for label in self.profession_labels if label != "ALL")
            if profession == "ALL"
            else "ALL"
        )
        self.profession_filter(temporary)
        self.profession_filter(profession)
        if filter_was_closed:
            # 只恢复明确读到的入口状态，不以职业推断侧栏是否展开。
            self._close_profession_filter()
        full_scan = profession == "ALL"
        if not self.low_frame_rate_mode:
            return (0, None) if return_page else 0
        actual = self.wait_for_agent_page(full_scan=full_scan, train=train)
        if not actual or (not train and actual[0][1][0][0] > 650):
            raise AgentSelectionNotReady("筛选复位后列表仍被裁切，返回房间重试")
        logger.debug(f"职业筛选已复位选人列表，首张完整卡片：{actual[0]}")
        if return_page:
            return 0, self.observe_agent_page(actual, full_scan=full_scan, train=train)
        return 0

    def agent_station_filter(self, status=None):
        """读取或设置进驻筛选；确认菜单展开后才点击选项。"""
        options = {"全部": 137, "宿舍锁定": 213, "未进驻": 289}
        if status is not None and status not in options:
            raise ValueError(f"未知进驻筛选：{status}")

        def observe(*, menu):
            if config.stop_mower.is_set():
                raise MowerExit
            self.require_agent_selection_page()
            return read_station_filter(self.recog.img, self.read_screen, menu=menu)

        poll_interval, max_attempts = self.selection_transition_timing()

        def wait_for(predicate, *, menu=True, error="进驻筛选尚未生效"):
            for attempt in range(max_attempts):
                if attempt:
                    self.sleep(poll_interval)
                current, opened = observe(menu=menu)
                if current is not None and predicate(current, opened):
                    return current, opened
            raise AgentSelectionNotReady(error)

        current, opened = wait_for(
            lambda value, opened: True,
            menu=status is not None,
            error="未识别进驻筛选标题",
        )
        if status is None or (current == status and not opened):
            return current
        if not opened:
            self.tap((1675, 60), interval=0.1)
            wait_for(lambda value, menu: menu)
        self.tap((1675, options[status]), interval=0.1)
        wait_for(lambda value, menu: value == status and not menu)
        return status

    def profession_filter(self, profession=None):
        """
                    confirm_blue	confirm_train
        训练位筛选开	1548 0.89		1554
        训练位筛选关	not				1669
        普通位筛选关	1724			1732 0.7
        普通位筛选开	1609			not
        """
        if profession:
            if config.stop_mower.is_set():
                raise MowerExit
            logger.debug(f"打开 {profession} 筛选")
        else:
            logger.debug("关闭职业筛选")
            self.profession_filter("ALL")
            self._close_profession_filter()
            return
        x = 1918
        label_pos = [(x, 135 + i * 110) for i in range(9)]
        label_pos_map = dict(zip(self.profession_labels, label_pos))
        self._set_profession_filter_open(True)
        position = label_pos_map[profession]
        if profession == "ALL":
            if not self._profession_highlighted(position):
                self.tap(position, interval=0.1)
                self._wait_for_profession_filter(position)
            return
        active = [
            label
            for label, pos in label_pos_map.items()
            if self._profession_highlighted(pos)
        ]
        state = (
            branch_filter_state(self.recog.img, profession)
            if active == [profession]
            else None
        )
        if state is None or state[1]:
            if len(active) != 1 or active == [profession]:
                # 已限制到分支或高亮不明时，先恢复 ALL，再选择完整职业。
                self.tap(label_pos_map["ALL"], interval=0.1)
                self._wait_for_profession_filter(label_pos_map["ALL"], label_pos[1:])
            others = [
                pos for label, pos in label_pos_map.items() if label != profession
            ]
            self.tap(position, interval=0.1)
            self._wait_for_profession_filter(position, others)
            state = branch_filter_state(self.recog.img, profession)
        if state is not None:
            opened, filtered = state
            if filtered:
                raise AgentSelectionNotReady("职业内仍有限定分支，返回房间重试")
            if opened and not set_branch_menu_open(self, profession, False):
                raise AgentSelectionNotReady("分支菜单未能收起，返回房间重试")

    def _profession_highlighted(self, position):
        red, _, blue = self.get_color(position)
        return blue >= 240 and int(blue) - int(red) >= 100

    def _wait_for_profession_filter(self, position, others=()):
        # 普通设备收到反馈即继续；仅未生效时轮询，两种模式保留相同的等待预算。
        poll_interval, max_attempts = self.selection_transition_timing()
        for attempt in range(max_attempts):
            if attempt:
                self.sleep(poll_interval)
            self.require_agent_selection_page()
            if self._profession_highlighted(position) and not any(
                self._profession_highlighted(pos) for pos in others
            ):
                self.record_operation_feedback(attempt)
                return
        raise AgentSelectionNotReady("职业筛选尚未生效，返回房间重试")

    def _close_profession_filter(self):
        """仅收起筛选侧栏，保留当前职业。"""
        self._set_profession_filter_open(False)

    def _profession_filter_buttons(self, *, stationary_only=False):
        img = getattr(getattr(self, "recog", None), "_img", None)
        if isinstance(img, np.ndarray) and img.shape == (1080, 1920, 3):
            buttons = []
            # 核对静止按钮的底色和文字，保留同时命中两端的过渡帧。
            for resource, y, positions in (
                ("confirm_blue", 990, (1609, 1724)),
                ("confirm_train", 997, (1554, 1669)),
            ):
                template = loadres(resource)
                h, w = template.shape[:2]
                for x in positions:
                    region = img[y : y + h, x : x + w]
                    if cv2.norm(region, template, cv2.NORM_L1) > 12 * template.size:
                        continue
                    score = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
                    if score.item() >= 0.95:
                        buttons.append((resource, x, y))
            if buttons:
                return tuple(buttons)
        if stationary_only:
            return ()
        # 遮挡、移动中的按钮和非标准画面继续按原模板定位。
        return tuple(
            (resource, button[0][0], button[0][1])
            for resource in ("confirm_blue", "confirm_train")
            if (button := self.find(resource))
        )

    def _set_profession_filter_open(self, opened):
        """按确认按钮位置开关侧栏，原位置持续不变时有限补点。"""
        poll_interval, max_attempts = self.selection_transition_timing()
        retry_interval = max(1.0, 3 * poll_interval)
        previous = None
        stable_since = perf_counter()
        taps = 0
        for attempt in range(max_attempts + 1):
            if config.stop_mower.is_set():
                raise MowerExit
            self.require_agent_selection_page()
            buttons = self._profession_filter_buttons()
            state = None
            if buttons and all(x < 1650 for _, x, _ in buttons):
                state = True
            elif buttons and all(x > 1650 for _, x, _ in buttons):
                state = False
            if state is opened:
                return
            if attempt == max_attempts:
                break
            now = perf_counter()
            # 缺失、冲突或移动中的按钮不能证明上一次点击未生效。
            if state is None or buttons != previous:
                stable_since = now
            previous = buttons
            if state is not None and (
                taps == 0 or (taps < 3 and now - stable_since >= retry_interval)
            ):
                self.tap((1860, 60), interval=0.1)
                taps += 1
                stable_since = perf_counter()
            else:
                self.sleep(poll_interval)
        action = "打开" if opened else "关闭"
        raise AgentSelectionNotReady(f"{action}职业筛选失败")

    def detect_room_number(self, img) -> int | None:
        best_digit, best_score = None, -1
        for i in range(1, 5):
            digit = loadres(f"room/{i}")
            if img.shape[0] < digit.shape[0] or img.shape[1] < digit.shape[1]:
                continue
            result = cv2.matchTemplate(img, digit, cv2.TM_CCOEFF_NORMED)
            score = cv2.minMaxLoc(result)[1]
            if np.isfinite(score) and score > best_score:
                best_digit, best_score = i, score
        return best_digit if best_score >= 0.78 else None

    def detect_room_type(self) -> str | None:
        """标题优先确认设施类型；未知标题保留图标识别。"""
        if room := self._detect_room_title():
            return ROOM_TITLE_TYPES[room]
        return self._detect_room_type_by_color()

    def _detect_room_type_by_color(self) -> str | None:
        color_map = {
            "制造站": 25,
            "贸易站": 99,
            "发电站": 36,
            "训练室": 178,
            "加工站": 32,
        }
        img = cropimg(self.recog.img, ((568, 18), (957, 95)))
        # 只读取标题栏左侧的设施图标。整条标题栏会透出房间背景，
        # 加工站的暖色装饰曾被当成制造站的黄色。
        hsv = cv2.cvtColor(img[2:74, 2:74], cv2.COLOR_RGB2HSV)
        color_scores = {
            room: cv2.countNonZero(
                cv2.inRange(hsv, (color - 1, 80, 90), (color + 2, 255, 255))
            )
            for room, color in color_map.items()
        }
        best_room = max(color_scores, key=color_scores.get)
        if color_scores[best_room] > 150:
            return best_room
        return None

    def _detect_room_title(self) -> str | None:
        img = cropimg(self.recog.img, ((568, 18), (957, 95)))
        # 标题优先于颜色；进入动画中透出的背景不能覆盖已确认的设施标题。
        best_room = None
        best_score = -1
        for room in ROOM_TITLE_TYPES:
            tpl = loadres(f"room/{room}")
            result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            score = cv2.minMaxLoc(result)[1]
            if score > best_score:
                best_room, best_score = room, score
        return best_room if best_score >= 0.78 else None

    def detect_room(self) -> str:
        room = self._detect_room_title()
        img = cropimg(self.recog.img, ((568, 18), (957, 95)))
        if room and room not in ("manufacture", "trade", "power"):
            if room == "central":
                logger.debug("控制中枢")
            elif room == "dormitory":
                digit = cropimg(img, ((168, 18), (201, 60)))
                digit = self.detect_room_number(digit)
                if digit is None:
                    return ""
                if digit == 4:
                    logger.debug("宿舍B401")
                else:
                    logger.debug(f"宿舍B{digit}04")
                return f"dormitory_{digit}"
            elif room == "meeting":
                logger.debug("会客室1F02")
            elif room == "recycle":
                logger.debug("回收站")
            elif room == "factory":
                logger.debug("加工站B105")
            elif room == "train":
                logger.debug("训练室")
            else:
                logger.debug("办公室")
            return room

        colored_room = (
            ROOM_TITLE_TYPES[room] if room else self._detect_room_type_by_color()
        )
        if colored_room in ["制造站", "贸易站", "发电站"]:
            # 订单页标题较房间详情略有偏移，保留六像素边距以匹配完整数字。
            digit_1 = cropimg(img, ((205, 18), (238, 60)))
            digit_2 = cropimg(img, ((247, 18), (280, 60)))
            digit_1 = self.detect_room_number(digit_1)
            digit_2 = self.detect_room_number(digit_2)
            if digit_1 is None or digit_2 is None:
                return ""
            logger.debug(f"{colored_room}B{digit_1}0{digit_2}")
            return f"room_{digit_1}_{digit_2}"
        elif colored_room == "训练室":
            logger.debug("训练室")
            return "train"
        elif colored_room == "加工站":
            logger.debug("加工站B105")
            return "factory"
        return ""

    def adjust_room(self, _room):
        """只返回当前画面可点击的矩形；拖动后交由下一次尝试重新定位。"""
        rectangle = np.array(_room, dtype=float, copy=True)
        width, height = self.recog.w, self.recog.h
        if (
            rectangle.shape != (4, 2)
            or not np.isfinite(rectangle).all()
            or width <= 1
            or height <= 1
        ):
            self.sleep(0.5)
            return None
        min_x, min_y = rectangle.min(axis=0)
        max_x, max_y = rectangle.max(axis=0)
        if min_x >= max_x or min_y >= max_y:
            self.sleep(0.5)
            return None
        if max(min_x, 0) < min(max_x, width - 1) and max(min_y, 0) < min(
            max_y, height - 1
        ):
            rectangle[:, 0] = np.clip(rectangle[:, 0], 0, width - 1)
            rectangle[:, 1] = np.clip(rectangle[:, 1], 0, height - 1)
            return rectangle

        dx = 0
        if max_x <= 0:
            dx = -min_x
        elif min_x >= width - 1:
            dx = width - 1 - max_x
        # 偏移量与手势共享，确保整条路径都在屏内。
        if dx and height > NOINERTIA_OFFSET:
            start = (
                width // 2,
                min(height // 2, height - NOINERTIA_OFFSET - 1),
            )
            end_x = int(np.clip(start[0] + dx, 0, width - 1))
            if end_x != start[0]:
                logger.debug("房间在屏外，拖动地图后重新识别实际位置")
                self.swipe_noinertia(start, (end_x - start[0], 0), interval=0.5)
                return None
        # 纵向不可见或没有有效水平路径时，不把边缘线当成房间点击。
        self.sleep(0.5)
        return None

    @timed_step("enter_room")
    def enter_room(self, room, *, max_attempts=3, log_group=None):
        """从基建首页进入房间"""

        def entered_room():
            return self.detect_room() == room and not self.find("order_label")

        profile = self.performance_profile
        poll_interval = profile.screenshot_interval / 1000
        for enter_times in range(max_attempts):
            actions = 0
            for retry_times in range(9):
                if self.find("connecting"):
                    self.sleep()
                elif self.find("order_label"):
                    # 同一房间的订单页也不能作为房间进入完成，先恢复地图入口。
                    logger.info(
                        "仍在贸易站订单列表，返回基建地图后进入 %s",
                        room,
                        extra={"log_group": log_group},
                    )
                    self.back_to_infrastructure()
                elif pos := self.find("control_central"):
                    # 地图观测参与场景计时，避免跨房换班只累计房间结束页。
                    if self.scene() != Scene.INFRA_MAIN:
                        if self.detect_room() == room:
                            return
                        # 场景观测可能清除超时画面；重新确认地图锚点后再点击。
                        if not (pos := self.find("control_central")):
                            self.sleep(0.2)
                            continue
                    if actions >= 5:
                        break
                    actions += 1
                    _room = segment.base(
                        self.recog.img,
                        pos,
                        right_side_room_order=config.conf.right_side_room_order,
                    )[room]
                    logger.debug(
                        f"进入房间 {room}，第{enter_times + 1}轮第{retry_times + 1}次尝试"
                    )
                    visible_room = self.adjust_room(_room)
                    if visible_room is None:
                        continue
                    self.tap(visible_room, interval=0.2)
                    room_deadline = perf_counter() + profile.transition_timeout
                    while True:
                        # 点击后的地图、连接中和未知画面共用同一确认期限。
                        if not self.find("connecting"):
                            self._handle_room_entry_reward(room)
                            if entered_room():
                                return
                        # 先识别再检查期限，保留超时后的首帧；截图耗时计入等待。
                        if perf_counter() >= room_deadline:
                            break
                        self.sleep(poll_interval)
                    if self.find("connecting"):
                        break
                    # 收取产物后仍可能停在地图，沿用本轮点击上限继续进入。
                    if self.find("control_central") and not self.find("order_label"):
                        continue
                    scene = self.scene()
                    if scene in (
                        Scene.INFRA_DETAILS,
                        Scene.CTRLCENTER_ASSISTANT,
                        Scene.ORDER_LIST,
                    ):
                        logger.info(
                            "仍在其他房间，返回基建地图后进入 %s",
                            room,
                            extra={"log_group": log_group},
                        )
                        self.back_to_infrastructure()
                    elif scene != Scene.INFRA_MAIN:
                        if scene == Scene.UNKNOWN and enter_times + 1 < max_attempts:
                            # 首页导航遇到未知画面也会先等一帧；此处仍知道刚点击的房间。
                            self.sleep()
                            if not self.find("connecting") and entered_room():
                                return
                        break
                elif self.detect_room() == room:
                    return
                elif self.scene() in (
                    Scene.INFRA_DETAILS,
                    Scene.CTRLCENTER_ASSISTANT,
                ):
                    # 上一个房间的返回键可能没有生效，先回基建地图再点击。
                    logger.info(
                        "仍在其他房间，返回基建地图后进入 %s",
                        room,
                        extra={"log_group": log_group},
                    )
                    self.back_to_infrastructure()
                else:
                    self.sleep()
            if enter_times < max_attempts - 1:
                # 仍停在全局视角时，原逻辑会一直点击同一位置；退出基建
                # 再重新进入，重新定位房间。此处不重启或关闭游戏。
                logger.warning(
                    f"未确认进入房间 {room}，返回首页后重新定位（{enter_times + 1}/{max_attempts - 1}）",
                    extra={"log_group": log_group},
                )
                self.back_to_index()
                self.back_to_infrastructure()
        raise RuntimeError(f"未成功进入房间 {room}：重新定位后仍未确认房间画面")

    def _handle_room_entry_reward(self, room):
        """仅处理本次房间点击产生的领取页，由收取记录的拥有者确认来源。"""
        return False

    def double_read_time(self, cord, upperLimit=None, use_digit_reader=False):
        self.recog.update()
        time_in_seconds = self.read_time(
            cord, upperLimit, use_digit_reader=use_digit_reader
        )
        if time_in_seconds is None:
            logger.warning(
                "贸易站订单倒计时识别失败，回退为当前时间；不能据此确认实际订单完成时间"
            )
            return datetime.now()
        return self._order_completion_time(time_in_seconds)

    def _order_completion_time(self, remaining):
        observed_at = getattr(self.recog, "capture_started_at", None)
        if not isinstance(observed_at, datetime):
            observed_at = datetime.now()
        return observed_at + timedelta(seconds=remaining)

    def read_accurate_mood(self, img):
        try:
            if not isinstance(img, np.ndarray) or img.ndim != 2 or not img.size:
                return -1
            img = thres2(img, 200)
            return cv2.countNonZero(img) * 24 / 310
        except Exception as e:
            logger.exception(e)
            return -1

    def detect_product_complete(self):
        for product in [
            "gold",
            "exp",
            "lmd",
            "ori",
            "oru",
            "trust",
            "credit",
            "info",
        ]:
            if pos := self.find(
                f"infra_{product}_complete",
                scope=((1230, 0), (1920, 1080)),
            ):
                return pos

    def wait_product_complete(self, max_retries: int = 5, *, log_group=None) -> bool:
        """等待产物收取提示浮动动画结束并消失，避免遮挡后续 UI。

        :param max_retries: 提示持续显示时最多等待的轮数，每轮 1 秒。
        :return: 若提示消失返回 True，若达到最大重试次数仍未消失返回 False。
        """
        for _ in range(max_retries):
            if not self.detect_product_complete():
                return True
            logger.info("检测到产物收取提示，等待消失", extra={"log_group": log_group})
            self.sleep(1)
        if self.detect_product_complete():
            logger.warning(
                "产物收取提示等待超时，继续执行后续流程", extra={"log_group": log_group}
            )
            return False
        return True

    def read_operator_in_room(self, img):
        img = _room_name_mask(img)
        img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(img, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        if not rect:
            return ""
        x0 = min(x for x, y, w, h in rect)
        y0 = min(y for x, y, w, h in rect)
        x1 = max(x + w for x, y, w, h in rect)
        y1 = max(y + h for x, y, w, h in rect)
        if (x1 - x0) < 20:
            return ""
        img = img[y0:y1, x0:x1]
        tpl = np.zeros(ROOM_NAME_TEMPLATE_SHAPE, dtype=np.uint8)
        h = min(img.shape[0], tpl.shape[0])
        w = min(img.shape[1], tpl.shape[1])
        tpl[:h, :w] = img[:h, :w]
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        sample_width = _foreground_width(tpl)
        max_score = 0
        best_operator = None
        scores = {}
        for operator in _room_name_candidates(tpl):
            result = cv2.matchTemplate(tpl, OP_ROOM[operator], cv2.TM_CCORR_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            scores[operator] = max_val
            if max_val > max_score:
                max_score = max_val
                best_operator = operator
        if max_score < OPERATOR_ROOM_MIN_SCORE:
            logger.debug(
                f"房间干员识别置信度过低 ({best_operator}: {max_score:.3f} < {OPERATOR_ROOM_MIN_SCORE})，判定为未识别"
            )
            return ""
        return _resolve_operator_room_prefix(
            best_operator, max_score, scores, sample_width
        )

    @timed_step("room_read")
    def read_screen(self, img, type="mood", limit=24, cord=None):
        resident_time = (
            type == "time"
            and cord is not None
            and is_resident_timer_scope(cord)
            and isinstance(img, np.ndarray)
            and img.dtype == np.uint8
            and img.shape in ((1080, 1920, 3), (1080, 1920))
        )
        if cord is not None:
            img = cropimg(img, cord)
        if resident_time and (clock := read_resident_timer(img)) is not None:
            return clock
        if type == "name":
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
                text = ret.strip()
                if resident_time and not resident_timer_supports_ocr(
                    img, text, cord[0][1]
                ):
                    return limit + 1
                return text
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
            from arknights_mower.utils.workshop_ui import furniture_formula_name

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
            for idx, item in enumerate(ocr_result[0]):
                if (
                    len(item) > 2
                    and item[1] in workshop_formula.keys()
                    or item[1] == "家具零件"
                ):
                    name = item[1]
                    box = item[0]
                    box_global = [[x + offset_x, y + offset_y] for (x, y) in box]
                    if name == "家具零件":
                        name = furniture_formula_name(self.recog.img, box_global)
                        if name is None:
                            continue
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
                                break
                    # 等于 0 则出界了
                    if valid != 0:
                        if name.startswith("家具零件_"):
                            left = 1120 if box_global[0][0] > 1100 else 376
                            top = min(point[1] for point in box_global)
                            box_global = [
                                [left + 20, top + 45],
                                [left + 230, top + 195],
                            ]
                        res.append((name, box_global, valid > 0))
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

    @staticmethod
    def _time_seconds(time_str, upperlimit=None):
        h, m, s = map(int, str(time_str).split(":"))
        if h < 0 or not (0 <= m < 60 and 0 <= s < 60):
            raise ValueError("读取错误")
        seconds = h * 3600 + m * 60 + s
        if upperlimit is not None and seconds > upperlimit:
            raise ValueError("超过读取上限")
        return seconds

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
            return BaseMixin._time_seconds(time_str, upperlimit)
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
