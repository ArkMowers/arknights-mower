"""原生个人极速模拟，使用已有设备会话并在基建截止前保存对局。"""

import time
from datetime import datetime

import cv2

from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.log import logger, save_screenshot_frame
from arknights_mower.utils.scene import Scene

from . import theme
from .model import GarrisonError, catalogue, goal_reached, normal_name, record_wins
from .upstream import FarmSession, panel_open, strategy_panel
from .vision import Vision

RECONNECT_SECONDS = 30
MATCH_SECONDS = 12 * 60


class GarrisonYield(BaseException):
    """基建任务即将到期，需要归还设备。"""


class GarrisonNavigation(SceneGraphSolver):
    def transition(self):
        return True

    def run(self, capture, click, wait):
        frame = capture()
        if frame.screen == "tutorial":
            raise GarrisonError("请先手动完成卫戍协议教程")
        if frame.screen not in {"unknown", "terminal-garrison"}:
            return frame
        if frame.screen != "terminal-garrison":
            self.scene_graph_navigation(Scene.TERMINAL_MAIN)
            if self.scene() != Scene.TERMINAL_MAIN:
                raise GarrisonError("未确认终端主页，未点击卫戍协议入口")
            click((1780, 1005))
            frame = wait(lambda f: f.screen == "terminal-garrison", 10)
        click(frame.find("^(?:模拟开放中|模拟中)$").center)
        return wait(lambda f: f.screen == "lobby", 20)


class GarrisonSolver:
    def __init__(
        self,
        device,
        recog,
        progress,
        save,
        *,
        target_wins=3,
        match_limit=None,
        deadline=None,
        vision=None,
    ):
        self.device, self.recog = device, recog
        self.progress, self.save = progress, save
        self.match_limit = match_limit
        self.target_wins = target_wins
        if target_wins not in (3, 6):
            raise ValueError("策略刻章目标必须为三胜或六胜")
        self.deadline = deadline
        self.vision = vision
        self.last_frame = None
        self._end = time.monotonic() + 24 * 3600
        self._quick_confirmed = False
        self._theme_checked = False
        self._restoring_theme = False
        self._entered = False

    def remaining(self):
        if config.stop_mower.is_set():
            raise MowerExit
        seconds = self._end - time.monotonic()
        if self.deadline is not None:
            seconds = min(
                seconds,
                (self.deadline() - datetime.now()).total_seconds()
                - (5 if self._restoring_theme else 0),
            )
        if seconds <= 0 or config.stop_maa.is_set():
            raise GarrisonYield
        return seconds

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            csleep(min(0.2, max(0, end - time.monotonic()), self.remaining()))

    def capture(self):
        self.remaining()
        self.recog.update()
        frame = self.vision.frame(self.recog.img.copy())
        self.remaining()
        self.last_frame = frame
        if (
            not self._restoring_theme
            and frame.quick
            and frame.screen
            in {
                "mode",
                "info",
                "strategy",
                "squad",
                "prep",
                "battle",
            }
        ):
            self._quick_confirmed = True
            match = self.progress.get("match") or {}
            if frame.screen != "mode" and (
                not match or match.get("phase") == "starting"
            ):
                self.progress.pop("settlement_counted", None)
                self.progress["match"] = {**match, "phase": "active"}
                self.persist()
        return frame

    def click(self, point):
        self.remaining()
        self.device.tap(tuple(map(int, point)))
        self.sleep(0.3)

    def text_click(self, frame, pattern, region=None):
        screen = frame.screen
        frame = self.observe(
            frame,
            lambda f: f.screen == screen and f.find(pattern, region),
            error=f"复核后仍未识别到按钮：{pattern}",
        )
        self.click(frame.find(pattern, region).center)

    def observe(self, frame, predicate, *, timeout=8, error):
        if predicate(frame):
            return frame
        return self.wait(predicate, timeout, error=error)

    def wait(
        self, predicate, timeout=8, *, error="操作后没有观察到预期画面，保留当前对局"
    ):
        end = time.monotonic() + min(timeout, self.remaining())
        while time.monotonic() < end:
            frame = self.capture()
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            if predicate(frame):
                return frame
            self.sleep(min(0.2, remaining))
        self.remaining()
        raise GarrisonError(error)

    def persist(self):
        self.save(self.progress)

    def theme_lobby(self, frame):
        if frame.screen in {"lobby", "theme"}:
            return frame
        nav = GarrisonNavigation(self.device, self.recog)
        if frame.screen not in {"terminal-garrison", "unknown"}:
            nav.restart_game()
        return nav.run(self.capture, self.click, self.wait)

    def prepare_theme(self, frame):
        panel = theme.open_equipped(self, frame)
        original = theme.equipped(panel)
        if original != theme.DEFAULT_THEME:
            if not self.progress.get("original_theme"):
                self.progress["original_theme"] = original
                self.persist()
            theme.apply(self, panel, theme.DEFAULT_THEME)
        self.click((65, 58))
        lobby = self.wait(lambda f: f.screen == "lobby")
        self._theme_checked = True
        return lobby

    def restore_theme(self):
        name = self.progress.get("original_theme")
        if not name or config.stop_mower.is_set() or config.stop_maa.is_set():
            return
        self._restoring_theme = True
        self._end = min(self._end, time.monotonic() + 90)
        try:
            panel = theme.open_equipped(self, self.theme_lobby(self.capture()))
            theme.apply(self, panel, name)
        except MowerExit:
            raise
        except GarrisonYield:
            logger.info(f"卫戍协议留待下次空档恢复主题「{name}」")
            return
        except Exception as exc:
            raise GarrisonError(f"恢复卫戍协议主题「{name}」失败：{exc}") from exc
        self.progress.pop("original_theme")
        self.persist()
        logger.info(f"已恢复卫戍协议主题「{name}」")

    def enter(self):
        frame = self.capture()
        if frame.screen == "tutorial":
            raise GarrisonError("请先手动完成卫戍协议教程")
        if frame.screen == "result":
            return frame
        return self.prepare_theme(self.theme_lobby(frame))

    def start_or_resume(self, frame):
        reconnect = "断线重连|继续模拟|返回模拟|继续作战"
        controls = (1150, 900, 1920, 1040)
        visible = (0, 0, 1920, 1040)
        personal = (1050, 730, 1810, 925)

        def lobby_action(f):
            if f.screen != "lobby":
                return None
            if f.find(reconnect, visible):
                if f.find(reconnect, controls) and f.personal_simulation_selected():
                    return "resume"
                return None
            if f.find("放弃模拟", visible):
                return None
            if f.find("^搜寻队友$", controls) and f.find("^个人模拟$", personal):
                return "switch"
            if not f.personal_simulation_selected() or not f.find(
                "^极速模拟$", controls
            ):
                return None
            match = self.progress.get("match")
            if not match:
                return "start"
            if f.find("^极速模拟$", (1150, 900, 1520, 1040)) and f.find(
                "^独立模拟$", (1520, 900, 1920, 1040)
            ):
                if match == {"phase": "starting"}:
                    return "start"
                if match == {"phase": "active"}:
                    return "verify_start"
            return None

        if frame.screen == "lobby":
            action = lobby_action(frame)
            if not action:
                frame = self.wait(
                    lobby_action,
                    12,
                    error="复核后仍未确认大厅模式或对局入口，已保留对局",
                )
                action = lobby_action(frame)
            if action == "switch":
                self.text_click(frame, "^个人模拟$", personal)
                frame = self.wait(
                    lambda f: lobby_action(f) in {"resume", "start", "verify_start"}, 12
                )
                action = lobby_action(frame)
            if action == "verify_start":
                frame = self.wait(
                    lambda f: lobby_action(f) in {"verify_start", "resume"}, 12
                )
                action = "resume" if lobby_action(frame) == "resume" else "start"
        elif self.progress.get("match"):
            raise GarrisonError("已保存未完成对局，但未找到继续入口；未开始新对局")
        else:
            action = None
        if action == "resume":
            self.text_click(frame, reconnect, controls)
            return self.wait(
                lambda f: (
                    f.screen
                    in {
                        "info",
                        "strategy",
                        "squad",
                        "prep",
                        "battle",
                        "result",
                        "battle-timeout",
                    }
                ),
                RECONNECT_SECONDS,
            )
        if action == "start":
            if self.remaining() < MATCH_SECONDS:
                raise GarrisonYield
            self.text_click(frame, "^极速模拟$", controls)
            frame = self.wait(lambda f: f.screen in {"mode", "info", "strategy"}, 20)
        if frame.screen == "mode":
            frame = self.observe(
                frame,
                lambda f: f.screen == "mode" and f.quick and f.find("^开始模拟$"),
                error="复核后仍未确认个人极速模拟的开局按钮，已保留对局",
            )
            if self.remaining() < MATCH_SECONDS:
                raise GarrisonYield
            # 点击前写入正在开局，避免取消发生在点击与截图之间时误开第二局。
            self.progress.pop("settlement_counted", None)
            self.progress["match"] = {"phase": "starting"}
            self.persist()
            self.text_click(frame, "^开始模拟$")
            frame = self.wait(lambda f: f.screen in {"info", "strategy"}, 25)
        return frame

    @staticmethod
    def decision_point(frame):
        if frame.screen != "choice":
            return None
        if confirm := frame.find("^确认选择$|^确认$"):
            return confirm.center
        choices = []
        for center in (475, 990, 1500):
            text = "".join(
                t.text
                for t in frame.texts
                if t.score >= 0.6
                and 380 < t.y < 720
                and abs(t.center[0] - center) < 240
            )
            if text:
                score = (
                    100 * any(b in text for b in {"精准", "奥术"})
                    + 40 * ("资金" in text)
                    + 10 * ("层数" in text)
                )
                score -= 100 * any(
                    b in text for b in ("生命上限-", "无法被治疗", "流失")
                )
                choices.append((score, center))
        return (max(choices)[1], 540) if choices else None

    def choose_decision(self, frame):
        frame = self.observe(
            frame,
            self.decision_point,
            error="复核后仍未识别到战术决策选项，已保留对局",
        )
        self.click(self.decision_point(frame))

    def strategy_action(self, panel, strategies):
        if self.match_limit is not None:
            return "play" if panel_open(panel) else None
        wins = strategy_panel(panel)
        if wins is None:
            return None
        key = next(
            (
                strategies[normal_name(t)]
                for _, py, t in panel
                if 520 < py < 650 and normal_name(t) in strategies
            ),
            None,
        )
        if key and self.progress["wins"].get(key) != wins:
            record_wins(self.progress, key, wins)
            self.persist()
            if wins >= self.target_wins and all(
                self.progress["wins"].get(k, -1) >= self.target_wins
                for k in strategies.values()
            ):
                return "completed"
        return "skip" if wins >= self.target_wins else "play"

    def choose_strategy(self, game):
        strategies = {
            normal_name(s["name"]): s["id"] for s in catalogue()["strategies"]
        }
        self.click((1500, 580))
        rows = game.GRID_Y
        for _ in range(8):
            before = game.shot()
            for y in rows:
                if not game.GRID_TOP + 60 <= y <= game.GRID_BOTTOM - 40:
                    continue
                for x in game.GRID_X:
                    frame = self.capture()
                    if frame.screen != "strategy":
                        return frame
                    game.tap(x, y, 0.7)
                    for attempt in range(3):
                        panel = game.ocr(game.shot(), (1440, 150, 1920, 800))
                        action = self.strategy_action(panel, strategies)
                        if action is not None:
                            break
                        if attempt < 2:
                            self.sleep(0.4)
                    if action == "completed":
                        return None
                    if action != "play":
                        continue
                    frame = self.capture()
                    if frame.screen != "strategy":
                        return frame
                    self.text_click(frame, "确认选择|准备就绪|淮备就绪")
                    return self.wait(
                        lambda f: f.screen != "strategy" and f.screen != "unknown", 20
                    )
            frame = self.capture()
            if frame.screen != "strategy":
                return frame
            game.scroll_grid()
            after = game.shot()
            shift = game.grid_shift(before, after)
            rows = game.detect_rows(after)
            if not rows or shift is not None and abs(shift) < 20:
                break
        raise GarrisonError("本次未找到可刷策略，部分胜场仍待核对")

    def leave_match(self):
        if self._entered:
            try:
                self.device.exit_after_task_stop()
            finally:
                self.recog.reset_after_external_control()
                self._entered = False

    def run(self):
        from arknights_mower.utils.csleep import cancellation_scope

        def cancelled():
            self.remaining()
            return False

        if self.vision is None:
            rapidocr.initialize_ocr()
            self.vision = Vision(rapidocr.engine)
        try:
            with device_io_budget(self.remaining), cancellation_scope(cancelled):
                if goal_reached(self.progress, self.target_wins, self.match_limit):
                    self._entered = True
                    self.restore_theme()
                    return
                session = FarmSession(self)
                self._entered = True
                try:
                    frame = self.enter()
                    self.play(session.game, frame)
                finally:
                    session.release()
                if goal_reached(self.progress, self.target_wins, self.match_limit):
                    self.restore_theme()
        except GarrisonYield:
            logger.info("卫戍协议交还设备，本次空档结束")
        finally:
            self.leave_match()

    def can_dispatch_frame(self, frame):
        if frame.screen in {"lobby", "mode", "tutorial", "battle-timeout"}:
            return True
        if frame.screen not in {
            "info",
            "strategy",
            "squad",
            "prep",
            "battle",
            "confirm-ready",
            "choice",
            "result",
        }:
            return False
        return self._quick_confirmed or (
            frame.screen == "result"
            and frame.find("模拟结束|模拟成功|模拟失败|模拟胜利|模拟完成|模拟中断")
            and (self.progress.get("match") or self.progress.get("settlement_counted"))
        )

    def play(self, game, frame):
        board = game.Board()
        state = None
        timeout_round = None
        last_change = time.monotonic()
        while True:
            self.remaining()
            frame = self.observe(
                frame,
                self.can_dispatch_frame,
                timeout=15,
                error="复核后仍未确认卫戍协议的对局画面，已保留对局",
            )
            current = (frame.screen, board.round_done)
            if current != state:
                last_change, state = time.monotonic(), current
            elif time.monotonic() - last_change >= 600:
                raise GarrisonError("卫戍协议十分钟未观察到对局进展")
            if frame.screen in {"lobby", "mode"}:
                frame = self.start_or_resume(frame)
                continue
            if frame.screen == "tutorial":
                raise GarrisonError("请先手动完成卫戍协议教程")
            if frame.screen == "battle-timeout":
                if timeout_round == board.round_done:
                    raise GarrisonError("同一回合再次出现战斗超时，已保留对局")
                timeout_round = board.round_done
                self.text_click(frame, "^确认$", (800, 655, 1120, 800))
                frame = self.wait(
                    lambda f: (
                        f.screen
                        in {
                            "battle",
                            "prep",
                            "result",
                            "choice",
                            "confirm-ready",
                            "squad",
                            "info",
                            "strategy",
                        }
                    ),
                    RECONNECT_SECONDS,
                )
                continue
            if frame.screen == "info":
                self.text_click(frame, "[准淮]备就绪|^确认$")
                frame = self.wait(
                    lambda f: f.screen in {"strategy", "squad", "prep"}, 20
                )
                continue
            if frame.screen == "strategy":
                frame = self.choose_strategy(game)
                if frame is None:
                    return
                continue
            if frame.screen == "squad":
                game.pick_squad()
                frame = self.wait(
                    lambda f: (
                        f.screen
                        in {"prep", "battle", "battle-timeout", "choice", "result"}
                    ),
                    60,
                )
                continue
            elif frame.screen == "prep":
                game.prep_phase(board, cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR))
                if board.prep_done and time.monotonic() - board.last_ready > 10:
                    self.text_click(frame, "[准淮]备就绪")
                    board.last_ready = time.monotonic()
            elif frame.screen == "battle":
                board.prep_done = False
                self.sleep(2)
            elif frame.screen == "confirm-ready":
                game.handle_popups()
            elif frame.screen == "choice":
                self.choose_decision(frame)
            elif frame.screen == "result":
                home = frame.find("返回主页")
                if home is None:
                    frame = self.wait(
                        lambda f: f.screen == "result" and f.find("返回主页"), 15
                    )
                    home = frame.find("返回主页")
                if not self.progress.get("settlement_counted"):
                    save_screenshot_frame(frame.image, "garrison_result")
                    self.progress["match"] = None
                    self.progress["settlement_counted"] = True
                    self.progress["attempts"] = self.progress.get("attempts", 0) + 1
                    if self.match_limit is not None:
                        self.progress["matches_played"] = (
                            self.progress.get("matches_played", 0) + 1
                        )
                    self.persist()
                self.click(home.center)
                if (
                    self.match_limit
                    and self.progress.get("matches_played", 0) >= self.match_limit
                ):
                    return
                frame = self.wait(lambda f: f.screen == "lobby", 20)
                if self.remaining() < MATCH_SECONDS:
                    return
                if self.match_limit is None and self.progress["attempts"] >= 200:
                    raise GarrisonError("已尝试两百局，请核对策略进度")
                if not self._theme_checked:
                    frame = self.prepare_theme(frame)
                board = game.Board()
                timeout_round = None
                self._quick_confirmed = False
                continue
            frame = self.capture()
