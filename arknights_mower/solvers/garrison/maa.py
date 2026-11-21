"""在卫戍协议空档内通过已安装的 MAA 核心执行个人模拟。"""

from arknights_mower.utils.maa_update import is_maa_version_newer

from .model import GarrisonError
from .solver import MATCH_SECONDS, MATCH_TRANSITION_SECONDS, GarrisonSolver


class MaaGarrisonSolver(GarrisonSolver):
    def __init__(self, *args, scheduler, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheduler = scheduler
        self.task_id = None
        self.settled = False
        self.all_badges = False
        self.chain_error = False

    def record_message(self, msg, payload):
        if (
            self.task_id is None
            or payload.get("taskid") != self.task_id
            or payload.get("taskchain") != "StrongholdProtocol"
        ):
            return
        if msg == 10000:
            self.chain_error = True
        if msg != 20003:
            return
        details = payload.get("details")
        if not isinstance(details, dict):
            return
        if payload.get("what") == "StrongholdStrategiesCompleted":
            self.all_badges = details.get("target") == self.target_wins
        elif payload.get("what") == "StrongholdSettlement":
            self.settled = type(details.get("cleared")) is bool

    def score_entry(self, frame):
        controls = (1150, 900, 1920, 1040)

        def action(f):
            if f.screen == "lobby":
                if f.find("断线重连|放弃模拟|继续模拟|返回模拟|继续作战"):
                    return "saved"
                if f.personal_simulation_selected() and f.find("^极速模拟$", controls):
                    return "ready"
                if f.find("^搜寻队友$", controls) and f.find("^个人模拟$"):
                    return "switch"
            return None

        frame = self.observe(
            frame, action, error="未确认 MAA 刷分所需的个人极速模拟入口"
        )
        if action(frame) == "switch":
            self.text_click(frame, "^个人模拟$", (1050, 730, 1810, 925))
            frame = self.wait(lambda f: action(f) in {"ready", "saved"}, 12)
        if action(frame) != "ready":
            raise GarrisonError("MAA 刷分需要空存档，请先完成已有对局")

    def defer_for_refresh(self):
        refresh = self.scheduler._maa_refresh_deadline()
        if refresh is None:
            return False
        self.scheduler._defer_maa_for_refresh(refresh)
        return True

    def run_game(self):
        if self.defer_for_refresh():
            return
        scheduler = self.scheduler
        scheduler.release_maa()
        try:
            self.remaining()
            scheduler.initialize_maa(
                task_callback=self.record_message, reset_stop=False
            )
            core = scheduler.MAA
            if is_maa_version_newer("v6.23.0-beta.1", core.get_version()):
                raise GarrisonError(
                    "请将 MAA 核心和资源更新至 v6.23.0-beta.1 或更高版本"
                )
            self._entered = True
            frame = self.enter()
            while not self.defer_for_refresh():
                if self.mode == "maa_score":
                    self.score_entry(frame)
                    if self.remaining() < MATCH_SECONDS:
                        return
                    params = {"mode": "score"}
                else:
                    if frame.screen in {"lobby", "mode"}:
                        frame = self.start_or_resume(frame)
                    if not (
                        self.can_dispatch_frame(frame)
                        and frame.screen not in {"lobby", "mode", "tutorial"}
                        and (self._quick_confirmed or frame.screen == "result")
                    ):
                        raise GarrisonError("未确认个人极速模拟对局，已保留存档")
                    params = {
                        "mode": "badge",
                        "theme": "Regulation",
                        "target": self.target_wins,
                        "runs": 1,
                        "attempts": 1,
                    }

                self.remaining()
                self.settled = self.all_badges = self.chain_error = False
                self.task_id = core.append_task("StrongholdProtocol", params)
                self.remaining()
                if self.defer_for_refresh():
                    return
                if not self.task_id or not core.start():
                    raise GarrisonError("MAA 未接受卫戍任务，请核对核心与资源版本")
                while core.running():
                    self.sleep(0.5)
                self.task_id = None
                self.remaining()
                self.recog.reset_after_external_control()
                if self.chain_error:
                    raise GarrisonError("MAA 卫戍任务执行失败，请检查 MAA 日志")
                if self.all_badges and self.mode == "maa_medals":
                    self.progress["maa_badge_target"] = self.target_wins
                    self.persist()
                    return
                if self.mode == "maa_score":
                    return
                if not self.settled:
                    raise GarrisonError("MAA 未报告本局结算或全部角标达标，已保留进度")
                self._quick_confirmed = False
                self.progress["match"] = None
                self.persist()
                if self.remaining() < MATCH_SECONDS:
                    return
                frame = self.wait(
                    lambda f: f.screen == "lobby", MATCH_TRANSITION_SECONDS
                )
        finally:
            self.task_id = None
            try:
                if scheduler.MAA is not None:
                    scheduler.maa_stop()
            finally:
                scheduler.release_maa()
                self.recog.reset_after_external_control()
