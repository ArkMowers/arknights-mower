"""原生个人极速模拟，使用已有设备会话并在基建截止前保存对局。"""

import time
from datetime import datetime

import cv2

from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene

from .model import GarrisonError, catalogue, normal_name, record_wins
from .upstream import FarmSession, strategy_panel
from .vision import Vision


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
        deadline=None,
        vision=None,
    ):
        self.device, self.recog = device, recog
        self.progress, self.save = progress, save
        self.target_wins = target_wins
        if target_wins not in (3, 6):
            raise ValueError("策略刻章目标必须为三胜或六胜")
        self.deadline = deadline
        self.vision = vision
        self.last_frame = None
        self._end = time.monotonic() + 24 * 3600
        self._quick_confirmed = False
        self._entered = False

    def remaining(self):
        if config.stop_mower.is_set():
            raise MowerExit
        seconds = self._end - time.monotonic()
        if self.deadline is not None:
            seconds = min(
                seconds, (self.deadline() - datetime.now()).total_seconds() - 30
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
        if frame.quick and frame.screen in {
            "mode",
            "info",
            "strategy",
            "squad",
            "prep",
            "battle",
        }:
            self._quick_confirmed = True
        return frame

    def click(self, point):
        self.remaining()
        self.device.tap(tuple(map(int, point)))
        self.sleep(0.3)

    def text_click(self, frame, pattern, region=None):
        text = frame.find(pattern, region)
        if text is None:
            raise GarrisonError(f"未识别到按钮：{pattern}")
        self.click(text.center)

    def wait(self, predicate, timeout=8):
        end = time.monotonic() + min(timeout, self.remaining())
        while time.monotonic() < end:
            frame = self.capture()
            if predicate(frame):
                return frame
            self.sleep(0.2)
        raise GarrisonError("操作后没有观察到预期画面，保留当前对局")

    def persist(self):
        self.save(self.progress)

    def enter(self):
        return GarrisonNavigation(self.device, self.recog).run(
            self.capture, self.click, self.wait
        )

    def start_or_resume(self, frame):
        reconnect = "断线重连|继续模拟|返回模拟|继续作战"
        lobby_controls = reconnect + "|极速模拟|搜寻队友"
        visible = (0, 0, 1920, 1040)
        if frame.screen == "lobby" and not frame.find(lobby_controls, visible):
            frame = self.wait(
                lambda f: f.screen == "lobby" and f.find(lobby_controls, visible), 12
            )
        resume = frame.find(reconnect, visible)
        if resume:
            self.click(resume.center)
            return self.wait(
                lambda f: (
                    f.screen
                    in {"info", "strategy", "squad", "prep", "battle", "result"}
                ),
                30,
            )
        if self.progress.get("match"):
            raise GarrisonError("已保存未完成对局，但未找到继续入口；未开始新对局")
        if frame.screen == "lobby":
            if not frame.find("极速模拟"):
                if not frame.find("搜寻队友") or not frame.find("同盟模拟|联合模拟"):
                    raise GarrisonError("无法确认个人模拟入口")
                self.text_click(frame, "^个人模拟$")
                frame = self.wait(lambda f: f.screen == "lobby" and f.find("极速模拟"))
            self.text_click(frame, "^极速模拟$")
            frame = self.wait(lambda f: f.screen in {"mode", "info", "strategy"}, 20)
        if frame.screen == "mode":
            if not frame.quick:
                raise GarrisonError("当前模式不是个人极速模拟")
            # 点击前写入正在开局，避免取消发生在点击与截图之间时误开第二局。
            self.progress["match"] = {"phase": "starting"}
            self.persist()
            self.text_click(frame, "^开始模拟$")
            frame = self.wait(lambda f: f.screen in {"info", "strategy"}, 25)
        return frame

    def choose_decision(self, frame):
        if frame.find("^确认选择$|^确认$"):
            self.text_click(frame, "^确认选择$|^确认$")
            return
        choices = []
        for center in (475, 990, 1500):
            text = "".join(
                t.text
                for t in frame.texts
                if 380 < t.y < 720 and abs(t.center[0] - center) < 240
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
        if not choices:
            raise GarrisonError("战术决策选项未读到")
        self.click((max(choices)[1], 540))

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
                        wins = strategy_panel(panel)
                        if wins is not None:
                            break
                        if attempt < 2:
                            self.sleep(0.4)
                    if wins is None:
                        continue
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
                    if wins >= self.target_wins:
                        continue
                    frame = self.capture()
                    if frame.screen != "strategy":
                        return frame
                    self.text_click(frame, "确认选择|准备就绪|淮备就绪")
                    return self.wait(
                        lambda f: f.screen != "strategy" and f.screen != "unknown", 20
                    )
            if all(
                self.progress["wins"].get(k, -1) >= self.target_wins
                for k in strategies.values()
            ):
                return None
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
                session = FarmSession(self)
                try:
                    self._entered = True
                    frame = self.enter()
                    self.play(session.game, frame)
                finally:
                    session.release()
        except GarrisonYield:
            logger.info("卫戍协议交还设备，本次空档结束")
        finally:
            self.leave_match()

    def play(self, game, frame):
        board = game.Board()
        state = None
        last_change = time.monotonic()
        while True:
            self.remaining()
            current = (frame.screen, board.round_done)
            if current != state:
                last_change, state = time.monotonic(), current
            elif time.monotonic() - last_change >= 600:
                raise GarrisonError("卫戍协议十分钟未观察到对局进展")
            if frame.screen in {"lobby", "mode"}:
                frame = self.start_or_resume(frame)
                continue
            if frame.screen == "unknown":
                frame = self.wait(lambda f: f.screen != "unknown", 15)
                continue
            if not self._quick_confirmed:
                raise GarrisonError("未确认当前对局为极速模拟")
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
                self.progress["match"] = None
                self.progress["attempts"] = self.progress.get("attempts", 0) + 1
                self.persist()
                self.text_click(frame, "返回主页")
                frame = self.wait(lambda f: f.screen == "lobby", 20)
                if self.remaining() + 30 < 540:
                    return
                if self.progress["attempts"] >= 200:
                    raise GarrisonError("已尝试两百局，请核对策略进度")
                board = game.Board()
                self._quick_confirmed = False
                continue
            else:
                raise GarrisonError(f"卫戍协议画面未确认：{frame.screen}")
            frame = self.capture()
