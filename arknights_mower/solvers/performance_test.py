"""Explicit, bounded selection trials without confirming room staffing."""

from contextlib import contextmanager
from dataclasses import replace
from time import monotonic

from arknights_mower.solvers.base_mixin import (
    AgentSelectionNotReady,
    AgentSelectionPageChanged,
    BaseMixin,
    agent_card_selected,
)
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, cancellation_scope
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.performance import PERFORMANCE_PRESETS
from arknights_mower.utils.scene import Scene

CLEANUP_TIMEOUT = 10
MODES = ("xhigh", "high", "medium", "low")


class SelectionPerformanceTest(BaseMixin, SceneGraphSolver):
    room = "dormitory_1"

    def __init__(self, device, configuration, cancelled, report):
        super().__init__(device=device)
        self.configuration = configuration
        self.cancelled = cancelled
        self.report = report
        self.entered_room = False
        self._navigating = False
        self.trials = []

    @staticmethod
    def record_operation_feedback(extra_observations):
        """Explicit trials leave automatic selection history untouched."""

    @contextmanager
    def profile(self, mode, *, preparation=False):
        conf = self.configuration
        profile = replace(
            PERFORMANCE_PRESETS[mode],
            screenshot_interval=conf.screenshot_interval,
            poll_interval=conf.selection_poll_interval,
            transition_timeout=conf.selection_transition_timeout,
        )
        if preparation:
            profile = replace(
                profile,
                poll_interval=max(0.5, profile.poll_interval),
                transition_timeout=max(6, profile.transition_timeout),
            )
        previous = getattr(self, "_selection_profile_snapshot", None)
        self._selection_profile_snapshot = profile
        try:
            yield
        finally:
            if previous is None:
                del self._selection_profile_snapshot
            else:
                self._selection_profile_snapshot = previous

    @contextmanager
    def budget(self, seconds=None, *, cleanup=False):
        deadline = monotonic() + seconds if seconds is not None else None

        def cancelled():
            return config.stop_mower.is_set() or (not cleanup and self.cancelled())

        def remaining():
            if cancelled():
                raise MowerExit("游戏内性能测试已取消")
            if deadline is None:
                return 30.0
            value = deadline - monotonic()
            if value <= 0:
                raise TimeoutError("测试暂选清理超时，请检查游戏画面")
            return value

        def check_cancelled():
            remaining()
            return False

        with cancellation_scope(check_cancelled), device_io_budget(remaining):
            self.checkpoint = remaining
            yield

    def scene(self):
        scene = super().scene()
        manual_scenes = (
            Scene.LOGIN_MAIN,
            Scene.LOGIN_INPUT,
            Scene.LOGIN_REGISTER,
            Scene.LOGIN_CAPTCHA,
            Scene.LOGIN_BILIBILI_PRIVACY,
            Scene.AGREEMENT_UPDATE,
        )
        if scene in manual_scenes:
            # Loading transitions can briefly match a login control. Observe
            # another frame without clicking before requiring manual action.
            self.sleep(1)
            scene = super().scene()
            if scene in manual_scenes:
                raise RuntimeError("请先在游戏中手动完成登录验证或协议确认，再重新测试")
        if getattr(self, "_navigating", False) and scene in (
            Scene.INFRA_ARRANGE_ORDER,
            Scene.INFRA_ARRANGE_CONFIRM,
            Scene.RIIC_OPERATOR_SELECT,
            Scene.DOUBLE_CONFIRM,
        ):
            raise RuntimeError("检测到尚未确认的操作，请先退出该页面后重试")
        return scene

    def open_selection(self):
        self.report({"phase": "navigating", "message": "正在启动游戏并进入基建"})
        self._navigating = True
        try:
            self.checkpoint()
            self.check_current_focus()
            scene = self.scene()
            if scene != Scene.INFRA_MAIN and not (
                scene == Scene.INFRA_DETAILS and self.detect_room() == self.room
            ):
                self.back_to_infrastructure()
                scene = self.scene()
                if scene != Scene.INFRA_MAIN:
                    raise RuntimeError("未能进入基建首页，请检查登录或游戏画面")
            if scene == Scene.INFRA_MAIN:
                self.enter_room(self.room, max_attempts=1)
        finally:
            self._navigating = False
        self.entered_room = True
        for _ in range(12):
            self.checkpoint()
            if self.scene() == Scene.INFRA_ARRANGE_ORDER:
                return
            if self.find("room_detail"):
                self.tap((self.recog.w * 0.82, self.recog.h * 0.2), interval=0.5)
            elif pos := self.find("arrange_check_in") or self.find(
                "arrange_check_in_small"
            ):
                self.tap(pos, interval=0.5)
            else:
                self.sleep(0.5)
        raise RuntimeError("未进入宿舍一选人页面，请检查游戏画面")

    def prepare_round(self):
        """Locate repeatable targets with conservative input before measurement."""
        with self.profile("low", preparation=True):
            self.checkpoint()
            if self.scene() != Scene.INFRA_ARRANGE_ORDER:
                raise RuntimeError("游戏已离开宿舍选人页，请返回基建首页后重试")
            self.profession_filter()
            self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            self.switch_arrange_order("技能", self.room)
            self.swipe_left(1, "ALL")
            before = self.wait_for_agent_page()
            if any(
                agent_card_selected(self.recog.img, scope) is not False
                for _, scope in before
            ):
                raise RuntimeError("准备阶段未确认暂选已清空，请检查游戏画面")
            _, observation = self.swipe_agent_page(before, [], return_page=True)
            after = observation.page
            original = {name for name, _ in before}
            targets = list(
                dict.fromkeys(
                    name for name, _ in after if name and name not in original
                )
            )[:2]
            if len(targets) != 2:
                raise RuntimeError("翻页后可识别的新干员不足两名，无法进行性能测试")
            self.swipe_left(1, "ALL")
            reset = self.wait_for_agent_page()
            if not self.same_agent_page(reset, before, allow_unknown=True):
                raise RuntimeError("准备阶段列表未复位，无法进行性能测试")
            return reset, targets

    def trial(self, before, targets):
        self.checkpoint()
        _, observation = self.swipe_agent_page(before, targets, return_page=True)
        pending = targets.copy()
        self.scan_agent(pending, observation=observation)
        if pending:
            raise AgentSelectionNotReady("滑动后未选中全部目标干员")
        self.switch_arrange_order("技能", self.room)
        _, observation = self.swipe_left(1, "ALL", return_page=True)
        actual = self.wait_for_arranged_agents(
            targets, ordered=False, observation=observation
        )
        if actual is None:
            raise AgentSelectionNotReady("检测到干员选择错误")
        self.reorder_selected_agents(targets, actual)
        self.switch_arrange_order("技能", self.room)
        if self.wait_for_arranged_agents(targets, ordered=False) is None:
            raise AgentSelectionNotReady("重排后检测到干员选择错误")

    def cancel_selection(self):
        if not self.entered_room:
            return
        with self.budget(CLEANUP_TIMEOUT, cleanup=True):
            for _ in range(8):
                self.checkpoint()
                self.recog.update()
                scene = self.scene()
                if scene in (Scene.INFRA_MAIN, Scene.INFRA_DETAILS):
                    return
                if scene == Scene.INFRA_ARRANGE_ORDER:
                    self.back(interval=0.5)
                elif scene == Scene.INFRA_ARRANGE_CONFIRM:
                    # The left action discards the pending arrangement.
                    self.tap((self.recog.w // 3, self.recog.h - 10), interval=0.5)
                else:
                    raise RuntimeError("测试暂选尚未取消，请在游戏中返回并放弃换人")
            raise RuntimeError("测试暂选尚未取消，请在游戏中返回并放弃换人")

    def run(self):
        result = None
        try:
            with self.budget(), self.profile("low", preparation=True):
                self.report({"status": "running", "message": "正在进入宿舍一选人页"})
                self.open_selection()
                for mode in MODES:
                    for round_number in range(1, 4):
                        self.checkpoint()
                        self.report(
                            {"mode": mode, "round": round_number, "phase": "preparing"}
                        )
                        before, targets = self.prepare_round()
                        self.report({"phase": "testing"})
                        try:
                            with self.profile(mode):
                                self.trial(before, targets)
                        except AgentSelectionPageChanged:
                            raise
                        except AgentSelectionNotReady as exc:
                            self.trials.append(
                                {
                                    "mode": mode,
                                    "round": round_number,
                                    "ok": False,
                                    "message": str(exc),
                                }
                            )
                            self.report({"trials": self.trials.copy()})
                            break
                        self.trials.append(
                            {"mode": mode, "round": round_number, "ok": True}
                        )
                        self.report({"trials": self.trials.copy()})
                    else:
                        result = {
                            "status": "passed",
                            "recommended_mode": mode,
                            "message": "连续三轮滑动选人及名单校验通过",
                        }
                        break
                if result is None:
                    result = {
                        "status": "failed",
                        "recommended_mode": None,
                        "message": "低档仍未通过，请检查游戏画面与识别结果",
                    }
        finally:
            self.report({"phase": "cleanup"})
            if config.stop_mower.is_set() and self.entered_room:
                raise MowerExit("测试已停止；请检查游戏并放弃尚未取消的暂选")
            try:
                self.cancel_selection()
            except MowerExit:
                raise MowerExit("测试已停止；请检查游戏并放弃尚未取消的暂选") from None
            except Exception as exc:
                raise RuntimeError(
                    f"未确认测试暂选已取消，请在游戏中返回并放弃换人：{exc}"
                ) from exc
        return {**result, "trials": self.trials.copy(), "phase": "done"}
