from datetime import datetime
from typing import Optional

import cv2

from arknights_mower.models import secret_front
from arknights_mower.solvers.local_operation import (
    DEFAULT_STAGE_DURATION_SECONDS,
    compute_next_threshold_time,
)
from arknights_mower.solvers.record import (
    get_stage_operation_duration,
    record_operation_batch,
)
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.datetime import get_server_weekday
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene


class OperationSolver(SceneGraphSolver):
    def run(
        self,
        stop_time: datetime | None = None,
        *,
        stage_id: str | None = None,
        next_task_time: datetime | None = None,
        target_total_runs: int | None = None,
        simulated_current_ap: int | None = None,
        ap_cost: int | None = None,
        sanity_threshold: int | None = None,
        stage_duration_seconds: int | None = None,
    ):
        logger.info("Start: 代理作战")
        logger.info("start operation solver")
        self.stage_id = stage_id
        self.next_task_time = next_task_time or stop_time
        self.target_total_runs = target_total_runs
        # Seeded once from SKLand before entering operation; after that we only
        # simulate AP locally based on successful runs and do not refetch SKLand.
        self.simulated_current_ap = simulated_current_ap
        self.ap_cost = ap_cost
        self.sanity_threshold = sanity_threshold
        self.sanity_drain = False
        self.stopped_by_deadline = False
        self.executed_runs = 0
        self.remaining_runs = (
            None if target_total_runs is None else max(0, int(target_total_runs))
        )
        self.last_batch_duration_seconds = None
        self.estimated_stage_duration_seconds = (
            stage_duration_seconds
            or get_stage_operation_duration(
                stage_id or "",
                DEFAULT_STAGE_DURATION_SECONDS,
            )
        )
        logger.debug(
            "operation context | stage_id=%s | next_task_time=%s | target_total_runs=%s | simulated_current_ap=%s | ap_cost=%s | sanity_threshold=%s | estimated_stage_duration_seconds=%s",
            self.stage_id,
            self.next_task_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.next_task_time is not None
            else None,
            self.target_total_runs,
            self.simulated_current_ap,
            self.ap_cost,
            self.sanity_threshold,
            self.estimated_stage_duration_seconds,
        )

        while True:
            if self.remaining_runs is not None and self.remaining_runs <= 0:
                logger.debug(
                    "stop operation loop because remaining_runs reached zero | stage_id=%s | executed_runs=%s",
                    self.stage_id,
                    self.executed_runs,
                )
                break
            if (
                self.ap_cost is not None
                and self.simulated_current_ap is not None
                and self.simulated_current_ap < self.ap_cost
            ):
                self.sanity_drain = True
                logger.info(
                    "stop operation loop because simulated ap is below stage cost | stage_id=%s | simulated_current_ap=%s | ap_cost=%s",
                    self.stage_id,
                    self.simulated_current_ap,
                    self.ap_cost,
                )
                break
            if self._should_stop_for_deadline():
                self.stopped_by_deadline = True
                logger.info(
                    "stop operation loop because next task deadline is too close | stage_id=%s | now=%s | next_task_time=%s | estimated_stage_duration_seconds=%s",
                    self.stage_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    self.next_task_time.strftime("%Y-%m-%d %H:%M:%S")
                    if self.next_task_time is not None
                    else None,
                    self.estimated_stage_duration_seconds,
                )
                break

            self._prepare_batch_state()
            logger.info(
                "operation batch start | stage_id=%s | desired_repeat_times=%s | remaining_runs=%s | simulated_current_ap=%s",
                self.stage_id,
                self.desired_repeat_times,
                self.remaining_runs,
                self.simulated_current_ap,
            )
            super().run()

            if self.current_batch_success:
                self.executed_runs += self.current_batch_repeat_count
                if self.remaining_runs is not None:
                    self.remaining_runs = max(
                        0, self.remaining_runs - self.current_batch_repeat_count
                    )
                if self.ap_cost is not None and self.simulated_current_ap is not None:
                    self.simulated_current_ap = max(
                        0,
                        self.simulated_current_ap
                        - self.current_batch_repeat_count * self.ap_cost,
                    )
                self.last_batch_duration_seconds = self.current_batch_duration_seconds
                if (
                    self.stage_id
                    and self.current_batch_started_at is not None
                    and self.current_batch_finished_at is not None
                    and self.ap_cost is not None
                ):
                    record_operation_batch(
                        stage_id=self.stage_id,
                        run_count=self.current_batch_repeat_count,
                        ap_cost=self.ap_cost,
                        started_at=self.current_batch_started_at,
                        finished_at=self.current_batch_finished_at,
                        duration_seconds=self.current_batch_duration_seconds,
                    )
                logger.info(
                    "operation batch success | stage_id=%s | batch_repeat_count=%s | batch_duration_seconds=%.2f | executed_runs=%s | remaining_runs=%s | simulated_current_ap=%s",
                    self.stage_id,
                    self.current_batch_repeat_count,
                    self.current_batch_duration_seconds,
                    self.executed_runs,
                    self.remaining_runs,
                    self.simulated_current_ap,
                )
            else:
                logger.info(
                    "operation batch ended without success | stage_id=%s | sanity_drain=%s | repeat_count=%s",
                    self.stage_id,
                    self.sanity_drain,
                    self.current_batch_repeat_count,
                )
                break

            if self.target_total_runs is None:
                logger.info(
                    "stop operation loop because target_total_runs is not limited | stage_id=%s",
                    self.stage_id,
                )
                break

        next_threshold_time = None
        if self.simulated_current_ap is not None and self.sanity_threshold is not None:
            next_threshold_time = compute_next_threshold_time(
                self.simulated_current_ap,
                self.sanity_threshold,
            )

        result = {
            "executed_runs": self.executed_runs,
            "sanity_drain": self.sanity_drain,
            "next_threshold_time": next_threshold_time,
            "stopped_by_deadline": self.stopped_by_deadline,
            "last_batch_duration_seconds": self.last_batch_duration_seconds,
            "simulated_current_ap": self.simulated_current_ap,
            "remaining_runs": self.remaining_runs,
        }
        logger.info(
            "operation finished | stage_id=%s | result=%s", self.stage_id, result
        )
        return result

    def _prepare_batch_state(self):
        self.auto_repeat = True
        self.repeat_button_attempts = 0
        self.current_batch_success = False
        self.current_batch_repeat_count = 1
        self.current_batch_started_at = None
        self.current_batch_finished_at = None
        self.current_batch_duration_seconds = 0.0
        affordable_repeat_times = None
        if (
            self.ap_cost is not None
            and self.ap_cost > 0
            and self.simulated_current_ap is not None
        ):
            affordable_repeat_times = max(
                1, min(6, self.simulated_current_ap // self.ap_cost)
            )
        if self.remaining_runs is None:
            self.desired_repeat_times = max(
                1, min(6, int(getattr(config.conf, "operation_repeat_times", 6) or 6))
            )
        else:
            self.desired_repeat_times = max(
                1,
                min(
                    6,
                    int(getattr(config.conf, "operation_repeat_times", 6) or 6),
                    int(self.remaining_runs or 1),
                ),
            )
        if affordable_repeat_times is not None:
            self.desired_repeat_times = max(
                1,
                min(self.desired_repeat_times, affordable_repeat_times),
            )
        logger.info(
            "prepared operation batch state | stage_id=%s | desired_repeat_times=%s | affordable_repeat_times=%s | remaining_runs=%s | simulated_current_ap=%s",
            self.stage_id,
            self.desired_repeat_times,
            affordable_repeat_times,
            self.remaining_runs,
            self.simulated_current_ap,
        )

    def _should_stop_for_deadline(self) -> bool:
        if self.next_task_time is None:
            return False
        return (
            datetime.now().timestamp() + self.estimated_stage_duration_seconds
            > self.next_task_time.timestamp()
        )

    def _mark_battle_started(self):
        if self.current_batch_started_at is None:
            self.current_batch_started_at = datetime.now()

    def _finish_batch(self, success: bool):
        self.current_batch_success = success
        self.current_batch_finished_at = datetime.now()
        if self.current_batch_started_at is None:
            self.current_batch_started_at = self.current_batch_finished_at
        self.current_batch_duration_seconds = max(
            0.0,
            (
                self.current_batch_finished_at - self.current_batch_started_at
            ).total_seconds(),
        )

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
            if w < 5 or h < 5:
                continue
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            digit = cv2.copyMakeBorder(
                digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,)
            )
            score = []
            for i in range(10):
                im = secret_front[i]
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val, _, _, _ = cv2.minMaxLoc(result)
                score.append(min_val)
            value = value * 10 + score.index(min(score))
        return value

    def repeat_slot_scope(self, repeat_times: int) -> tp.Scope:
        y = 291 + (6 - repeat_times) * 93
        return (1445, y), (1555, y + 90)

    def best_repeat_option(
        self, desired_repeat_times: Optional[int] = None
    ) -> tuple[int, tp.Scope]:
        desired = (
            self.desired_repeat_times
            if desired_repeat_times is None
            else desired_repeat_times
        )
        desired = max(1, min(6, int(desired)))
        for repeat_times in range(desired, 0, -1):
            scope = self.repeat_slot_scope(repeat_times)
            if repeat_times > 1 and self.find("operation/+", scope=scope):
                continue
            img = cropimg(self.recog.gray, scope)
            img = thres2(img, 200)
            if repeat_times > 1 and cv2.countNonZero(img) < 60:
                continue
            return repeat_times, scope
        return 1, self.repeat_slot_scope(1)

    def transition(self):
        if (scene := self.scene()) == Scene.OPERATOR_BEFORE:
            if self.recog.gray[907][1600] < 127:
                self.tap((1776, 908))
                return
            if self.auto_repeat:
                if self.repeat_button_attempts == 0:
                    self.repeat_button_attempts += 1
                    self.tap((1501, 891), interval=0.5)
                    return
                if self.find("operation/x3") or self.find("operation/x4"):
                    repeat_times, scope = self.best_repeat_option(
                        self.desired_repeat_times
                    )
                    self.current_batch_repeat_count = repeat_times
                    logger.info(
                        "选择连战次数：目标 %s，实际 %s",
                        self.desired_repeat_times,
                        repeat_times,
                    )
                    self.tap(self.get_pos(scope), interval=0.5)
                    self.auto_repeat = False
                    self.repeat_button_attempts = 0
                    return
                repeat = self.number(((1515, 870), (1545, 910)), 28)
                logger.debug(
                    "operation repeat_status: repeat=%s auto_repeat=%s attempts=%s",
                    repeat,
                    self.auto_repeat,
                    self.repeat_button_attempts,
                )
                if repeat > 1:
                    self.current_batch_repeat_count = repeat
                    logger.info(
                        "choose operation repeat by legacy detector | desired=%s | actual=%s",
                        self.desired_repeat_times,
                        repeat,
                    )
                    # self.tap((1500, 910), interval=0.5) # 疑似多余点击
                    self.tap((1500, 801), interval=0.5)
                    self.auto_repeat = False
                    self.repeat_button_attempts = 0
                    return
                self.current_batch_repeat_count = 1
                logger.info(
                    "fallback to single run because repeat selector is unavailable | desired=%s",
                    self.desired_repeat_times,
                )
                self.auto_repeat = False
                self.repeat_button_attempts = 0
            self._mark_battle_started()
            self.tap_element("ope_start", interval=2)
        elif scene == Scene.OPERATOR_SELECT:
            self.tap((1655, 781))
        elif scene == Scene.OPERATOR_FINISH:
            self._finish_batch(True)
            logger.info(
                "operation scene finish | stage_id=%s | repeat_count=%s",
                self.stage_id,
                self.current_batch_repeat_count,
            )
            self.tap((310, 330))
            return True
        elif scene == Scene.OPERATOR_FAILED:
            self._finish_batch(False)
            logger.warning(
                "operation scene failed | stage_id=%s | repeat_count=%s",
                self.stage_id,
                self.current_batch_repeat_count,
            )
            self.tap((310, 330))
            return True
        elif scene == Scene.OPERATOR_ONGOING:
            if self.find("ope_agency_fail"):
                self.tap((121, 79))
            else:
                self.sleep(10)
        elif scene == Scene.OPERATOR_GIVEUP:
            self._finish_batch(False)
            logger.warning(
                "operation scene giveup | stage_id=%s | repeat_count=%s",
                self.stage_id,
                self.current_batch_repeat_count,
            )
            self.tap_element("double_confirm/main", x_rate=1)
            return True
        elif scene == Scene.OPERATOR_RECOVER_POTION:
            use_medicine = False
            if config.conf.maa_expiring_medicine:
                if config.conf.exipring_medicine_on_weekend:
                    use_medicine = get_server_weekday() >= 5
                else:
                    use_medicine = True
            if use_medicine:
                img = cropimg(self.recog.img, ((1015, 515), (1170, 560)))
                img = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
                img = cv2.inRange(img, (170, 0, 0), (174, 255, 255))
                use_medicine = cv2.countNonZero(img) > 3000
            if use_medicine:
                logger.info("使用即将过期的理智药")
                self.tap((1635, 865))
                return
            self.sanity_drain = True
            self._finish_batch(False)
            logger.info(
                "stop operation because sanity potion is not allowed | stage_id=%s",
                self.stage_id,
            )
            return True
        elif scene == Scene.OPERATOR_RECOVER_ORIGINITE:
            self.sanity_drain = True
            self._finish_batch(False)
            logger.info(
                "stop operation because originite recovery dialog appeared | stage_id=%s",
                self.stage_id,
            )
            return True
        elif scene == Scene.OPERATOR_ELIMINATE:
            logger.info(
                "entered OPERATOR_ELIMINATE | stage_id=%s | repeat_count=%s",
                self.stage_id,
                self.current_batch_repeat_count,
            )
            if self.find("ope_agency_lock"):
                logger.error("无法代理当期剿灭")
                self.sanity_drain = True
                self._finish_batch(False)
                return True
            if self.find("1800"):
                logger.info("本周剿灭已完成")
                self.sanity_drain = True
                self._finish_batch(False)
                return True
            if pos := self.find("ope_elimi_agency"):
                logger.info("found ope_elimi_agency button | pos=%s", pos)
                self.tap(pos, interval=0.5)
                return
            logger.info("ope_elimi_agency button not found, fallback to ope_start")
            self._mark_battle_started()
            self.tap_element("ope_start", interval=2)
        elif scene == Scene.OPERATOR_ELIMINATE_AGENCY:
            logger.info(
                "entered OPERATOR_ELIMINATE_AGENCY | stage_id=%s | tap confirm",
                self.stage_id,
            )
            self._mark_battle_started()
            self.tap_element("ope_elimi_agency_confirm", interval=2)
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self._finish_batch(False)
            logger.warning(
                "stop operation because scene is unexpected | stage_id=%s | scene=%s",
                self.stage_id,
                scene,
            )
            return True
