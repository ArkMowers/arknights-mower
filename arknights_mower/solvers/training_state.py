import json
import os
from datetime import datetime, timedelta
from enum import Enum

from arknights_mower.utils.log import logger
from arknights_mower.utils.mastery_recommendation import (
    _build_route_supports,
    _supports_from_dicts,
    get_skill_data,
)
from arknights_mower.utils.path import get_path
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class TrainingState(Enum):
    IDLE = 0
    TRAINING = 1
    WAITING_COLLECT = 2


class TrainingStateMachine:
    def __init__(self, scheduler):
        self._scheduler = scheduler
        self._state = TrainingState.IDLE
        self._transition_history = []
        self._transition_max_interval = 60
        self._transition_max_count = 5
        self._last_training_countdown = None
        self._initial_checked = False
        self._lit_zones = 0
        self._trainee_plan_key = ""
        self._trainee_name = ""
        self._trainee_cid = ""
        self._target_skill = -1
        self._trainer_name = ""

    def gate_sync(self):
        plan = self._scheduler._get_mastery_plan()
        if plan:
            from arknights_mower.utils.scheduler_task import TaskTypes

            if not self._scheduler.find_next_task(task_type=TaskTypes.SKILL_UPGRADE):
                self.sync()

    @property
    def state(self):
        return self._state

    def sync(self):
        import traceback

        caller = traceback.extract_stack()[-2].name
        new_state = self._determine_state()
        if new_state == self._state:
            self._act_on_state(new_state)
            return
        old = self._state
        self._state = new_state
        self._transition_history.append((datetime.now(), old.name, new_state.name))
        if len(self._transition_history) > self._transition_max_count:
            self._transition_history.pop(0)
        if (
            len(self._transition_history) >= self._transition_max_count
            and (
                self._transition_history[-1][0] - self._transition_history[0][0]
            ).total_seconds()
            < self._transition_max_interval
        ):
            logger.warning(
                f"STUCK_DETECT: {len(self._transition_history)} "
                f"transitions in {self._transition_max_interval}s"
            )
            self._transition_history.clear()
        logger.info(f"训练室状态: {old.name} -> {new_state.name} (来自{caller})")
        if old == TrainingState.IDLE and new_state == TrainingState.TRAINING:
            if self._trainee_name and self._target_skill >= 0:
                lvl = self._lit_zones + 1
                logger.info(
                    f"恢复全自动专精任务：{self._trainee_name} "
                    f"技能{self._target_skill + 1} -> 专精{lvl}"
                )
        if new_state == TrainingState.IDLE:
            if self._scheduler.op_data.skill_upgrade_supports:
                logger.info(
                    f"训练室空闲: 已清除协助位配置 "
                    f"(之前 {[s.name for s in self._scheduler.op_data.skill_upgrade_supports]})"
                )
            self._scheduler.op_data.skill_upgrade_supports = []
            self._lit_zones = 0
            self._trainee_plan_key = ""
            self._trainee_name = ""
            self._trainee_cid = ""
            self._target_skill = -1
            self._trainer_name = ""
        self._act_on_state(new_state)

    def _determine_state(self):
        plan = self._scheduler._get_mastery_plan()
        if not plan:
            logger.debug("_determine_state: plan empty -> IDLE")
            return TrainingState.IDLE
        if self._state == TrainingState.IDLE and self._initial_checked:
            logger.debug(
                "_determine_state: IDLE (already checked), skip physical entry"
            )
            return TrainingState.IDLE
        if (
            self._state == TrainingState.TRAINING
            and self._last_training_countdown is not None
            and self._last_training_countdown > datetime.now()
        ):
            logger.debug(
                "_determine_state: training still running "
                "(countdown valid), cache state=TRAINING"
            )
            return TrainingState.TRAINING
        self._initial_checked = True
        result = self._read_physical_state()
        logger.debug(f"_determine_state: plan non-empty, physical={result.name}")
        return result

    def should_skip_room(self, task):
        if task.meta_data == "_mastery":
            return False
        if self._scheduler.find_next_task(task_type=TaskTypes.SKILL_UPGRADE):
            logger.info("有未完成的专精任务，跳过训练室排班")
            return True
        if self._state in {
            TrainingState.TRAINING,
            TrainingState.WAITING_COLLECT,
        }:
            logger.info("训练室专精进行中，跳过非专精排班")
            return True
        return False

    def get_training_context(self):
        """返回当前训练详情 {name, skill_label, level}，若无活跃训练则返回 None"""
        try:
            if self._lit_zones == 0 or not self._trainee_plan_key:
                return None
            from arknights_mower.utils.mastery_recommendation import get_skill_data

            parts = self._trainee_plan_key.rsplit("_", 1)
            if len(parts) != 2:
                return None
            char_table = get_skill_data().get("characters", {})
            name = char_table.get(parts[0], {}).get("name", "")
            if not name:
                return None
            training_lvl = self._lit_zones + 1
            return {
                "name": name,
                "skill_label": str(training_lvl),
                "level": training_lvl,
            }
        except Exception:
            pass
        return None

    def set_trainee_info(self, lit_zones, plan_key):
        self._lit_zones = lit_zones
        self._trainee_plan_key = plan_key

    def get_training_level(self):
        return self._lit_zones + 1 if self._lit_zones > 0 else 1

    def read_mastery_zones(self, skill_idx):
        """在专精技能选择页面读取三角形区域的亮起数量 (0~3)"""
        zone_coords = {
            0: [  # 一技能
                ((596, 167), (631, 202)),
                ((575, 203), (610, 238)),
                ((618, 203), (653, 238)),
            ],
            1: [  # 二技能
                ((596, 483), (631, 518)),
                ((575, 518), (610, 553)),
                ((618, 518), (653, 553)),
            ],
            2: [  # 三技能
                ((596, 799), (631, 834)),
                ((575, 835), (610, 870)),
                ((618, 835), (653, 870)),
            ],
        }
        coords = zone_coords.get(skill_idx, [])
        if not coords:
            return 0
        self._scheduler.recog.update()
        gray = self._scheduler.recog.gray
        lit = 0
        threshold = 200
        for (x0, y0), (x1, y1) in coords:
            if y0 >= gray.shape[0] or x0 >= gray.shape[1]:
                continue
            y1 = min(y1, gray.shape[0])
            x1 = min(x1, gray.shape[1])
            crop = gray[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            bright_pixels = (crop > threshold).sum()
            ratio = bright_pixels / crop.size
            if ratio > 0.5:
                lit += 1
        logger.debug(f"read_mastery_zones(skill={skill_idx + 1}): lit={lit}/3")
        return lit

    def _enrich_meta(self, skill_label, cid, lvl):
        """构建显示用的 meta_data"""
        try:
            char_table = get_skill_data().get("characters", {})
            name = char_table.get(cid, {}).get("name", "")
            if name:
                return f"{name} 技能{skill_label} -> 专精{lvl} "
        except Exception:
            pass
        return skill_label

    def _read_physical_state(self):
        self._scheduler.enter_room("train")
        try:
            scene = self._scheduler.train_scene()
            if scene != Scene.TRAIN_MAIN:
                self._last_training_countdown = None
                return TrainingState.IDLE
            # 先判断状态：检查是否可收集
            completed_found = self._scheduler.find("training_completed")
            if completed_found:
                self._last_training_countdown = None
                return TrainingState.WAITING_COLLECT
            # 读倒计时确定是否在专精中
            time_in_seconds = self._scheduler.read_time(
                ((236, 978), (380, 1020)), upperlimit=None
            )
            if time_in_seconds is None:
                self._last_training_countdown = None
                return TrainingState.IDLE
            execute_time = datetime.now() + timedelta(seconds=time_in_seconds)
            self._last_training_countdown = execute_time
            # 重试进入技能选择页（弹窗可能挡住，最多试 5 次）
            skill_scene = Scene.UNKNOWN
            for attempt in range(5):
                self._scheduler.tap(
                    (self._scheduler.recog.w * 0.05, self._scheduler.recog.h * 0.95),
                )
                self._scheduler.sleep(0.5)
                skill_scene = self._scheduler.train_scene()
                if skill_scene == Scene.TRAIN_SKILL_SELECT:
                    break

            if skill_scene == Scene.TRAIN_SKILL_SELECT:
                try:
                    for idx in range(3):
                        self._scheduler.tap(
                            (
                                self._scheduler.recog.w * 0.33,
                                self._scheduler.recog.h * (idx * 0.3 + 0.32),
                            )
                        )
                    self._scheduler.sleep(0.1)
                    self._scheduler.recog.update()
                    gray = self._scheduler.recog.gray
                    skill_regions = [
                        ((792, 292), (909, 325)),
                        ((792, 609), (909, 643)),
                        ((792, 926), (909, 961)),
                    ]
                    means = []
                    for (x0, y0), (x1, y1) in skill_regions:
                        if y0 >= gray.shape[0] or x0 >= gray.shape[1]:
                            means.append(255)
                            continue
                        y1 = min(y1, gray.shape[0])
                        x1 = min(x1, gray.shape[1])
                        crop = gray[y0:y1, x0:x1]
                        means.append(crop.mean())
                    self._target_skill = min(range(3), key=lambda i: means[i])
                    self._lit_zones = self.read_mastery_zones(self._target_skill)
                except Exception:
                    pass
                self._scheduler.back()
            # 回到 TRAIN_MAIN 后读干员
            current = self._scheduler.get_agent_from_room("train")
            if not any(e["agent"] not in ("", "Free") for e in current):
                self._last_training_countdown = None
                return TrainingState.IDLE
            if len(current) > 1:
                self._trainer_name = current[0].get("agent", "")
                self._trainee_name = current[1].get("agent", "")
                char_table = get_skill_data().get("characters", {})
                for cid, info in char_table.items():
                    if info.get("name") == self._trainee_name:
                        self._trainee_cid = cid
                        break
            return TrainingState.TRAINING
        finally:
            self._scheduler.back()

    def _act_on_state(self, state):
        if state == TrainingState.IDLE:
            return
        try:
            if self._target_skill < 0 or not self._trainee_cid:
                return

            char_table = get_skill_data().get("characters", {})
            trainee_name = self._trainee_name
            trainee_cid = self._trainee_cid
            target_skill = self._target_skill
            trainee_skill_label = str(target_skill + 1)
            trainer = {"charId": ""}
            if self._trainer_name:
                for cid, info in char_table.items():
                    if info.get("name") == self._trainer_name:
                        trainer["charId"] = cid
                        break

            plan_has_trainee = False
            matery_plan = self._scheduler._get_mastery_plan()
            if matery_plan:
                try:
                    plan_key = f"{trainee_cid}_{target_skill}"
                    if matery_plan.get(plan_key):
                        plan_has_trainee = True
                except Exception:
                    pass

            supports_list = self._scheduler.op_data.skill_upgrade_supports
            if not supports_list and matery_plan:
                try:
                    trainee_info = char_table.get(trainee_cid, {})
                    profession = trainee_info.get("profession", "")
                    if profession:
                        route = _build_route_supports(profession)
                        if route:
                            supports_list = _supports_from_dicts(route)
                except Exception as e:
                    logger.warning(f"加载专精路线失败: {e}")

            if state == TrainingState.TRAINING:
                if supports_list:
                    self._correct_assistant(
                        trainer,
                        trainee_cid,
                        target_skill,
                        char_table,
                        supports_list,
                        trainee_skill_label,
                    )

            if state == TrainingState.WAITING_COLLECT:
                if not self._scheduler.find_next_task(
                    task_type=TaskTypes.SKILL_UPGRADE
                ):
                    lvl = self._lit_zones + 1
                    self._scheduler.tasks.append(
                        SchedulerTask(
                            time=datetime.now(),
                            task_type=TaskTypes.SKILL_UPGRADE,
                            meta_data=self._enrich_meta(
                                trainee_skill_label, trainee_cid, lvl
                            ),
                            adjusted=True,
                        )
                    )

            if target_skill >= 0:
                if not plan_has_trainee and not self._scheduler.find_next_task(
                    meta_data="_mastery"
                ):
                    logger.error(
                        f"训练位干员 {trainee_name} skill_{trainee_skill_label}"
                        f" 不在专精计划和一键专精上下文中"
                    )
                    return

            if state == TrainingState.TRAINING and supports_list:
                self._recover_half_off_chain(
                    trainee_cid,
                    target_skill,
                    supports_list,
                    trainee_skill_label,
                )
        except Exception:
            pass

    def _correct_assistant(
        self,
        trainer,
        trainee_cid,
        target_skill,
        char_table,
        supports_list,
        trainee_skill_label,
    ):
        from arknights_mower.utils import config

        if config.conf.assistant_follows_schedule:
            logger.debug(
                "assistant_follows_schedule enabled, skip assistant correction"
            )
            return
        trainer_cid = trainer.get("charId")
        trainer_name = (
            char_table.get(trainer_cid, {}).get("name", trainer_cid)
            if trainer_cid
            else ""
        )

        half_off_names = {
            s.swap_name for s in supports_list if s.swap_name and s.swap_name != s.name
        }
        if trainer_name and trainer_name in half_off_names:
            if self._scheduler.find_next_task(task_type=TaskTypes.SKILL_UPGRADE):
                return
            if (
                self._last_training_countdown
                and self._last_training_countdown > datetime.now()
            ):
                remaining_h = (
                    self._last_training_countdown - datetime.now()
                ).total_seconds() / 3600
                if remaining_h <= 5 + 10 / 60:
                    return

        current_level = self._lit_zones
        if current_level == 0:
            if not trainer_name:
                correct = supports_list[0].name
            elif trainer_name not in {s.name for s in supports_list}:
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=datetime.now(),
                        task_plan={"train": ["Free", "Current"]},
                        meta_data="_mastery",
                        adjusted=True,
                    )
                )
                return
            else:
                correct = trainer_name
        else:
            training_lvl = current_level + 1
            match = next(
                (s for s in supports_list if s.level == training_lvl),
                None,
            )
            correct = match.name if match else supports_list[0].name

        logger.info(
            f"训练室: 协助位={trainer_name}, "
            f"当前等级={current_level}, 应为={correct}, "
            f"路线={[s.name for s in supports_list]}"
        )

        if trainer_name != correct:
            logger.warning(
                f"协助位干员 {trainer_name} 不是当前等级的正确人选"
                f"（应为 {correct}），创建换人任务"
            )
            self._scheduler.tasks.append(
                SchedulerTask(
                    time=datetime.now(),
                    task_plan={"train": [correct, "Current"]},
                    meta_data="_mastery",
                    adjusted=True,
                )
            )
            # 强制下次 sync 物理重读训练室
            self._last_training_countdown = None
            # 协助位纠正后排一个 REFRESH_TIME 触发换人时间计算
            self._scheduler.tasks.append(
                SchedulerTask(
                    time=datetime.now() + timedelta(seconds=5),
                    task_plan={},
                    task_type=TaskTypes.REFRESH_TIME,
                    meta_data="train",
                )
            )
            existing = self._scheduler.find_next_task(
                task_type=TaskTypes.SKILL_UPGRADE,
                meta_data=trainee_skill_label,
            )
            if existing:
                existing.time = datetime.now()

    def _recover_half_off_chain(
        self,
        trainee_cid,
        target_skill,
        supports_list,
        trainee_skill_label,
    ):
        from arknights_mower.utils import config

        if config.conf.assistant_follows_schedule:
            logger.debug(
                "assistant_follows_schedule enabled, skip half-off chain recovery"
            )
            return
        if (
            self._last_training_countdown is None
            or self._last_training_countdown <= datetime.now()
        ):
            return
        try:
            if self._lit_zones == 0:
                training_lvl = 1
            else:
                training_lvl = self._lit_zones + 1
            if training_lvl >= 3:
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=self._last_training_countdown,
                        task_type=TaskTypes.SKILL_UPGRADE,
                        meta_data=self._enrich_meta(
                            trainee_skill_label, trainee_cid, training_lvl
                        ),
                    )
                )
                return
            support = next((s for s in supports_list if s.level == training_lvl), None)
            if (
                support is None
                or not support.swap_name
                or support.swap_name == support.name
            ):
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=self._last_training_countdown,
                        task_type=TaskTypes.SKILL_UPGRADE,
                        meta_data=self._enrich_meta(
                            trainee_skill_label, trainee_cid, training_lvl
                        ),
                    )
                )
                return
            remaining_h = (
                self._last_training_countdown - datetime.now()
            ).total_seconds() / 3600
            swap_name = support.swap_name

            # 等协助位纠正为正确人选后才能算换人
            if self._trainer_name not in ("", support.name, swap_name):
                return

            # 读中枢加成
            central_bonus = 0
            try:
                route_path = get_path("@app/tmp/matery_route.json")
                if os.path.exists(route_path):
                    with open(route_path, "r", encoding="utf-8") as _f:
                        _route = json.load(_f)
                    if _route.get("controlCenter", "none") != "none":
                        central_bonus = 5
            except Exception:
                pass

            if self._trainer_name == swap_name:
                # 场景4：逻各斯/艾丽妮在位，剩余 > 5h10m → 换出再换入
                if remaining_h <= 5 + 10 / 60:
                    self._scheduler.tasks.append(
                        SchedulerTask(
                            time=self._last_training_countdown,
                            task_type=TaskTypes.SKILL_UPGRADE,
                            meta_data=self._enrich_meta(
                                trainee_skill_label, trainee_cid, training_lvl
                            ),
                        )
                    )
                    return
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=datetime.now(),
                        task_plan={"train": [support.name, "Current"]},
                        meta_data="_mastery",
                        adjusted=True,
                    )
                )
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=datetime.now() + timedelta(seconds=5),
                        task_plan={},
                        task_type=TaskTypes.REFRESH_TIME,
                        meta_data="train",
                    )
                )
                return

            # _trainer_name == "" or support.name：反推换入后剩余
            swap_match = support.match
            current_total = 100 + support.efficiency + 5
            swap_total = 100 + 5 + central_bonus + (30 if swap_match else 0)
            projected = remaining_h * current_total / swap_total
            if projected <= 5:
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=self._last_training_countdown,
                        task_type=TaskTypes.SKILL_UPGRADE,
                        meta_data=self._enrich_meta(
                            trainee_skill_label, trainee_cid, training_lvl
                        ),
                    )
                )
                return
            self._scheduler._schedule_half_off_swap_internal(
                support,
                self._last_training_countdown,
                trainee_skill_label,
                check_duplicate=True,
            )
        except Exception:
            pass
