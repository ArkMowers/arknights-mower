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

MATCH_TRANSITION_SECONDS = 60
MATCH_SECONDS = 12 * 60


class GarrisonYield(BaseException):
    """本轮需要交还设备。"""

    DEADLINE = "排班截止"
    INSUFFICIENT_MATCH_TIME = "剩余时间不足以开新局"


class GarrisonNavigation(SceneGraphSolver):
    def transition(self):
        return True

    def run(self, capture, click, wait, *, team_exit_pending=False):
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
        return wait(
            lambda f: (
                f.screen == "lobby" or (team_exit_pending and f.screen == "result")
            ),
            MATCH_TRANSITION_SECONDS,
        )


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
        self._entered = False
        self.yield_reason: str | None = None

    def remaining(self):
        if config.stop_mower.is_set():
            raise MowerExit
        seconds = self._end - time.monotonic()
        reason = "24 小时运行上限"
        if self.deadline is not None:
            until_deadline = (self.deadline() - datetime.now()).total_seconds()
            if until_deadline <= seconds:
                reason = GarrisonYield.DEADLINE
            seconds = min(seconds, until_deadline)
        if seconds <= 0:
            raise GarrisonYield(reason)
        if config.stop_maa.is_set():
            raise GarrisonYield("用户停止 MAA")
        return seconds

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            csleep(min(0.2, max(0, end - time.monotonic()), self.remaining()))

    def read_frame(self):
        self.remaining()
        self.recog.update()
        frame = self.vision.frame(self.recog.img.copy())
        self.remaining()
        self.last_frame = frame
        return frame

    def capture(self):
        frame = self.read_frame()
        if self.progress.get("team_exit_pending"):
            return frame
        if frame.quick and frame.screen in {
            "mode",
            "info",
            "strategy",
            "squad",
            "choice",
            "confirm-ready",
            "prep",
            "battle",
        }:
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
        self,
        predicate,
        timeout=8,
        *,
        read=None,
        error="操作后没有观察到预期画面，保留当前对局",
    ):
        frame = self.wait_for_observation(read or self.capture, predicate, timeout)
        if frame is None:
            raise GarrisonError(error)
        return frame

    def wait_for_observation(self, read, predicate, timeout):
        end = time.monotonic() + min(timeout, self.remaining())
        while time.monotonic() < end:
            frame = read()
            remaining = min(self.remaining(), end - time.monotonic())
            if remaining <= 0:
                break
            if predicate(frame):
                return frame
            self.sleep(min(0.2, remaining))
        self.remaining()
        return None

    def persist(self):
        self.save(self.progress)

    def theme_lobby(self, frame):
        if frame.screen in {"lobby", "theme"}:
            return frame
        nav = GarrisonNavigation(self.device, self.recog)
        if frame.screen not in {"terminal-garrison", "unknown"}:
            nav.restart_game()
        return nav.run(
            self.capture,
            self.click,
            self.wait,
            team_exit_pending=self.progress.get("team_exit_pending", False),
        )

    def leave_terminated_team(self, frame):
        def lobby_ready(f):
            return f.screen == "lobby" and (
                f.personal_simulation_selected()
                or f.find("^搜寻队友$", (1150, 900, 1920, 1040))
            )

        def can_leave(f):
            return lobby_ready(f) or (f.screen == "result" and f.find("^返回主页$"))

        if not can_leave(frame) and not frame.terminated_team_reconnect():
            frame = self.wait(
                lambda f: can_leave(f) or f.terminated_team_reconnect(),
                MATCH_TRANSITION_SECONDS,
                read=self.read_frame,
            )
        if button := frame.terminated_team_reconnect():
            self.progress["team_exit_pending"] = True
            self.persist()
            self.click(button.center)
            frame = self.wait(can_leave, MATCH_TRANSITION_SECONDS, read=self.read_frame)
        if frame.screen == "result":
            self.text_click(frame, "^返回主页$")
            frame = self.wait(
                lobby_ready, MATCH_TRANSITION_SECONDS, read=self.read_frame
            )
        self.progress.pop("team_exit_pending")
        self.persist()
        return frame

    def prepare_theme(self, frame):
        if frame.terminated_team_reconnect() or (
            self.progress.get("team_exit_pending") and frame.screen != "theme"
        ):
            frame = self.leave_terminated_team(frame)
        panel = theme.open_equipped(self, frame)
        if theme.equipped(panel) != theme.DEFAULT_THEME:
            theme.apply(self, panel, theme.DEFAULT_THEME)
        self.click((65, 58))
        lobby = self.wait(lambda f: f.screen == "lobby")
        self._theme_checked = True
        return lobby

    def enter(self):
        frame = self.capture()
        if frame.screen == "tutorial":
            raise GarrisonError("请先手动完成卫戍协议教程")
        if frame.screen != "result":
            frame = self.theme_lobby(frame)
        if frame.screen == "result" and not self.progress.get("team_exit_pending"):
            return frame
        return self.prepare_theme(frame)

    def start_or_resume(self, frame):
        if self.progress.get("team_exit_pending"):
            return self.leave_terminated_team(frame)
        reconnect = "断线重连|继续模拟|返回模拟|继续作战"
        controls = (1150, 900, 1920, 1040)
        visible = (0, 0, 1920, 1040)
        personal = (1050, 730, 1810, 925)

        def lobby_action(f):
            if f.screen != "lobby":
                return None
            if f.find(reconnect, visible):
                if f.terminated_team_reconnect():
                    return "terminated_team"
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

        action = None
        returned_from_mode = False
        while frame.screen == "lobby" or (
            frame.screen == "mode"
            and (action == "resume" or self.progress.get("match"))
        ):
            if frame.screen == "mode":
                if returned_from_mode:
                    raise GarrisonError("重连再次进入难度选择页，已保留对局")
                self.click((65, 58))
                frame = self.wait(lambda f: f.screen == "lobby", 12)
                returned_from_mode = True
            action = lobby_action(frame)
            if not action:
                frame = self.wait(
                    lobby_action,
                    12,
                    error="复核后仍未确认大厅模式或对局入口，已保留对局",
                )
                action = lobby_action(frame)
            if action == "terminated_team":
                return self.leave_terminated_team(frame)
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
            if action != "resume":
                break
            self.text_click(frame, reconnect, controls)
            frame = self.wait(
                lambda f: (
                    f.screen
                    in {
                        "mode",
                        "info",
                        "strategy",
                        "squad",
                        "prep",
                        "battle",
                        "result",
                        "battle-timeout",
                        "choice",
                        "confirm-ready",
                    }
                ),
                MATCH_TRANSITION_SECONDS,
            )
            if frame.screen != "mode":
                return frame
        if action == "start":
            if self.remaining() < MATCH_SECONDS:
                raise GarrisonYield(GarrisonYield.INSUFFICIENT_MATCH_TIME)
            self.text_click(frame, "^极速模拟$", controls)
            frame = self.wait(lambda f: f.screen in {"mode", "info", "strategy"}, 20)
        if frame.screen == "mode":
            frame = self.observe(
                frame,
                lambda f: f.screen == "mode" and f.quick and f.find("^开始模拟$"),
                error="复核后仍未确认个人极速模拟的开局按钮，已保留对局",
            )
            if self.remaining() < MATCH_SECONDS:
                raise GarrisonYield(GarrisonYield.INSUFFICIENT_MATCH_TIME)
            # 点击前写入正在开局，避免取消发生在点击与截图之间时误开第二局。
            self.progress.pop("settlement_counted", None)
            self.progress["match"] = {"phase": "starting"}
            self.persist()
            self.text_click(frame, "^开始模拟$")
            frame = self.wait(
                lambda f: f.screen in {"info", "strategy"}, MATCH_TRANSITION_SECONDS
            )
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

    def read_strategy_action(self, game, strategies):
        def read():
            panel = game.ocr(game.shot(), (1440, 150, 1920, 800))
            if self.match_limit is not None:
                return "play" if panel_open(panel) else None
            wins = strategy_panel(panel)
            if wins is None:
                return None
            key = next(
                (
                    strategies[normal_name(t)]
                    for _, y, t in panel
                    if 520 < y < 650 and normal_name(t) in strategies
                ),
                None,
            )
            return (key, wins) if wins or key else None

        result = self.wait_for_observation(read, bool, 4)
        if result is None or result == "play":
            return result
        key, wins = result
        if key:
            wins = max(wins, self.progress["wins"].get(key, 0))
        if key and self.progress["wins"].get(key) != wins:
            record_wins(self.progress, key, wins)
            self.persist()
            if wins >= self.target_wins and all(
                self.progress["wins"].get(k, -1) >= self.target_wins
                for k in strategies.values()
            ):
                return "completed"
        if wins < self.target_wins:
            return "play"
        return "verified" if key is not None else "skip"

    @staticmethod
    def strategy_cells(game, page, *, initial=False):
        top, bottom = game.GRID_TOP + 60, game.GRID_BOTTOM - 40
        cells = {
            (x, y): span
            for (x, y), span in game.framed_cells(page).items()
            if top <= y <= bottom
        }
        framed_rows = {y for _, y in cells}
        fallback = game.GRID_Y if initial else game.detect_rows(page)
        rows = framed_rows.union(
            y
            for y in fallback
            if top <= y <= bottom and not any(abs(y - row) <= 96 for row in framed_rows)
        )
        for y in sorted(rows):
            for x in game.GRID_X:
                if any(cx == x and abs(cy - y) <= 96 for cx, cy in cells):
                    continue
                if game.has_portrait(page, x, y):
                    # Two portrait estimates still match within 40 pixels.
                    cells[x, y] = (y - 20, y + 20)
        return dict(sorted(cells.items(), key=lambda item: (item[0][1], item[0][0])))

    def choose_strategy(self, game):
        strategies = {
            normal_name(s["name"]): s["id"] for s in catalogue()["strategies"]
        }
        self.click((1500, 580))
        page = game.shot()
        cells = self.strategy_cells(game, page, initial=True)
        offset = 0
        checked_rows = {x: [] for x in game.GRID_X}
        skipped_badges = False
        for recheck_panels in (False, True):
            if recheck_panels and not skipped_badges:
                break
            for page_index in range(8):
                for (x, y), (top, bottom) in cells.items():
                    start, end = top + offset, bottom + offset
                    if any(start <= hi and lo <= end for lo, hi in checked_rows[x]):
                        continue
                    if (
                        not recheck_panels
                        and self.match_limit is None
                        and (
                            game.has_color_badge(page, x, y)
                            or self.target_wins == 3
                            and game.has_badge(page, x, y)
                        )
                    ):
                        skipped_badges = True
                        continue
                    frame = self.capture()
                    if frame.screen != "strategy":
                        return frame
                    game.tap(x, y, 0.7)
                    action = self.read_strategy_action(game, strategies)
                    if action == "verified":
                        checked_rows[x].append((start, end))
                    if action == "completed":
                        return None
                    if action == "play":
                        frame = self.capture()
                        if frame.screen != "strategy":
                            return frame
                        self.text_click(frame, "确认选择|准备就绪|淮备就绪")
                        return self.wait(
                            lambda f: f.screen not in {"strategy", "unknown"}, 20
                        )
                if page_index == 7:
                    break
                frame = self.capture()
                if frame.screen != "strategy":
                    return frame
                next_page = self.scroll_strategy_page(game, backwards=recheck_panels)
                if next_page is None:
                    break
                page, cells, shift = next_page
                if shift is None:
                    # Unknown page alignment cannot identify previously opened cards.
                    checked_rows = {x: [] for x in game.GRID_X}
                    offset = 0
                else:
                    offset += shift
        raise GarrisonError("本次未找到可刷策略，部分胜场仍待核对")

    def scroll_strategy_page(self, game, *, backwards):
        before = game.shot()
        if backwards:
            game.swipe(1000, 480, 1000, 900, ms=800)
        else:
            game.scroll_grid()

        def read():
            after = game.shot()
            shift = game.grid_shift(before, after)
            if shift is not None and abs(shift) < 20:
                return None
            cells = self.strategy_cells(game, after)
            if cells:
                return after, cells, shift
            return None

        return self.wait_for_observation(read, bool, 4)

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

        if goal_reached(self.progress, self.target_wins, self.match_limit):
            return
        if self.vision is None:
            rapidocr.initialize_ocr()
            self.vision = Vision(rapidocr.engine)
        try:
            with device_io_budget(self.remaining), cancellation_scope(cancelled):
                session = FarmSession(self)
                self._entered = True
                try:
                    frame = self.enter()
                    self.play(session.game, frame)
                finally:
                    session.release()
        except GarrisonYield as exc:
            self.yield_reason = str(exc) or None
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
                timeout=(
                    MATCH_TRANSITION_SECONDS
                    if state and state[0] == "battle" and frame.screen == "unknown"
                    else 15
                ),
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
                    MATCH_TRANSITION_SECONDS,
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
                    MATCH_TRANSITION_SECONDS,
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
                frame = self.wait(
                    lambda f: f.screen == "lobby", MATCH_TRANSITION_SECONDS
                )
                if self.remaining() < MATCH_SECONDS:
                    self.yield_reason = GarrisonYield.INSUFFICIENT_MATCH_TIME
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
