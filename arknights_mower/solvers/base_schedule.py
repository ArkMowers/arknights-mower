import copy
import json
import os
import pathlib
import sys
import urllib
from ctypes import CFUNCTYPE, c_char_p, c_int, c_void_p
from datetime import datetime, timedelta
from typing import Literal

import cv2

from arknights_mower.data import agent_list, agent_profession, base_room_list
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.solvers.credit import CreditSolver
from arknights_mower.solvers.cultivate_depot import cultivate as cultivateDepotSolver
from arknights_mower.solvers.depotREC import depotREC as DepotSolver
from arknights_mower.solvers.mail import MailSolver
from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.solvers.recruit import RecruitSolver
from arknights_mower.solvers.report import ReportSolver
from arknights_mower.solvers.secret_front import SecretFront
from arknights_mower.solvers.shop import CreditShop
from arknights_mower.solvers.skland import SKLand
from arknights_mower.utils import config, detector, rapidocr
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.datetime import (
    format_time,
    get_server_weekday,
)
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.email import maa_template, send_message
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.path import get_path
from arknights_mower.utils.plan import PlanTriggerTiming
from arknights_mower.utils.recognize import Recognizer, Scene
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    check_dorm_ordering,
    find_next_task,
    plan_metadata,
    scheduling,
    try_add_release_dorm,
    try_reorder,
)
from arknights_mower.utils.trading_order import TradingOrder


class BaseSchedulerSolver(SceneGraphSolver, BaseMixin):
    """
    收集基建的产物：物资、赤金、信赖
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.op_data = None
        self.party_time = None
        self.drone_time = None
        self.reload_time = None
        self.reload_room = None
        self.clue_count_limit = 9
        self.enable_party = True
        self.leifeng_mode = False
        self.digit_reader = DigitReader()
        self.error = False
        self.clue_count = 0
        self.tasks = []
        self.free_clue = None
        self.credit_fight = None
        self.task_count = 0
        self.refresh_connecting = False
        self.recruit_time = None
        self.last_clue = None
        self.sleeping = False
        self.operators = {}
        self.last_execution = {"maa": None, "recruit": None, "todo": None}
        self.order_reader = TradingOrder()
        self.sign_in = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.daily_report = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.daily_skland = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.daily_mail = (datetime.now() - timedelta(days=1, hours=8)).date()
        self.daily_visit_friend = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.ideal_resting_count = 4
        self.choose_error = set()
        self.drop_send = False

    def find_next_task(
        self,
        compare_time: datetime | None = None,
        task_type="",
        compare_type: Literal["<", "=", ">"] = "<",
        meta_data="",
    ):
        """找符合条件的下一个任务

        Args:
            tasks: 任务列表
            compare_time: 截止时间
        """
        return find_next_task(
            self.tasks, compare_time, task_type, compare_type, meta_data
        )

    @property
    def party_time(self):
        return self._party_time

    @party_time.setter
    def party_time(self, value):
        self._party_time = value
        if self.op_data is not None:
            self.op_data.party_time = value

    def run(self) -> None:
        """
        :param clue_collect: bool, 是否收取线索
        """

        self.error = False
        self.handle_error(True)

        scheduling(self.tasks)
        check_dorm_ordering(self.tasks, self.op_data)
        if len(self.tasks) > 0:
            # 找到时间最近的一次单个任务
            self.task = self.tasks[0]
        else:
            self.task = None
        if self.task is not None and datetime.now() < self.task.time:
            reschedule_time = (self.task.time - datetime.now()).total_seconds()
            if reschedule_time > 0:
                logger.info(
                    f"出现任务调度情况休息{reschedule_time}秒等待下一个任务开始"
                )
                self.sleep(reschedule_time)
        if self.party_time is not None and self.party_time < datetime.now():
            self.party_time = None
        if self.free_clue is not None and self.free_clue != get_server_weekday():
            self.free_clue = None
        if self.credit_fight is not None and self.credit_fight != get_server_weekday():
            self.credit_fight = None
        self.todo_task = False
        self.collect_notification = False
        self.planned = False
        if self.op_data is None or self.op_data.operators is None:
            self.initialize_operators()
        self.op_data.correct_dorm()
        self.backup_plan_solver(PlanTriggerTiming.BEGINNING)
        logger.debug("当前任务: " + ("||".join([str(t) for t in self.tasks])))
        return super().run()

    def transition(self) -> None:
        if (scene := self.scene()) == Scene.INFRA_MAIN:
            return self.infra_main()
        elif scene == Scene.INFRA_TODOLIST:
            return self.todo_list()
        elif scene == Scene.RIIC_OPERATOR_SELECT:
            self.tap_element("confirm_blue")
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.INFRA_MAIN)
            self.last_room = ""
            logger.debug("重设上次房间为空")

    def overtake_room(self):
        candidates = self.task.meta_data.split(",")
        if len(candidates) == 0:
            return
        if self.op_data.operators[candidates[0]].group != "":
            candidates = self.op_data.groups[
                self.op_data.operators[candidates[0]].group
            ]
        logger.debug(f"更新下班小组信息为{candidates}")
        # 在candidate 中，计算出需要的high free 和 Low free 数量
        current_resting = (
            len(self.op_data.dorm)
            - self.op_data.available_free()
            - self.op_data.available_free("low")
        )
        plan = {}
        self.get_resting_plan(candidates, [], plan, current_resting)
        if len(plan.items()) > 0:
            self.tasks.append(
                SchedulerTask(
                    datetime.now(), task_plan=plan, task_type=TaskTypes.SHIFT_OFF
                )
            )
            re_order_dorm_plan = try_reorder(self.op_data, plan)
            if re_order_dorm_plan:
                logger.debug(f"新增宿舍任务{re_order_dorm_plan}")
                task = SchedulerTask(
                    task_plan=re_order_dorm_plan, task_type=TaskTypes.SHIFT_OFF
                )
                self.tasks.append(task)
        else:
            msg = f"无法完成 {self.task.meta_data} 的排班，如果重复接收此邮件请检查替换组是否被占用"
            send_message(msg, level="ERROR")
            # 简单暴力一点，移除所有非回满的
            # 智能情况的话，得在人数和替换冲突中做出选择
            required = 0
            for x in candidates:
                op = self.op_data.operators[x]
                if op.workaholic:
                    continue
                required += 1
            remove_name = set()
            # 按心情降序排序
            sorted_dorms = sorted(
                self.op_data.dorm,
                key=lambda dorm: self.op_data.operators[dorm.name].mood
                if dorm.name in self.op_data.operators
                else 25,
                reverse=True,
            )
            for idx, dorm in enumerate(sorted_dorms):
                if not dorm.name or dorm.name not in self.op_data.operators:
                    continue
                if dorm.time is not None and dorm.time < datetime.now():
                    logger.debug(f"跳过{str(dorm)}，休息完毕")
                    continue
                operator = self.op_data.operators[dorm.name]
                if (
                    operator.rest_in_full
                    or operator.group in self.op_data.rest_in_full_group
                ):
                    # 如果回满，则跳过
                    logger.debug(f"跳过{str(dorm)}，回满")
                    continue
                if not operator.is_high():
                    # 跳过非高优
                    continue
                if operator.group and operator.name not in remove_name:
                    # 增加当前宿舍组的所有在休息中的干员
                    for name in self.op_data.groups[operator.group]:
                        if self.op_data.operators[name].is_resting():
                            _, dorm = self.op_data.get_dorm_by_name(name)
                            # 跳过已经计算的休息完毕的人
                            if dorm.time is not None and dorm.time < datetime.now():
                                continue
                            remove_name.add(name)
                else:
                    remove_name.add(dorm.name)

                # 检查条件是否满足
                if current_resting - len(remove_name) + required <= len(
                    self.op_data.dorm
                ):
                    break
            if current_resting - len(remove_name) + required > len(self.op_data.dorm):
                msg = f"无法完成 {self.task.meta_data} 的排班，宿舍可用空位不足，请减少使用回满词条"
                send_message(msg, level="ERROR")
                return
            logger.debug(f"需要提前移出宿舍的干员: {remove_name}")
            planned = set()
            for name in remove_name:
                if name in planned:
                    continue
                op = self.op_data.operators[name]
                group = [op.name] if not op.group else self.op_data.groups[op.group]
                for agent in group:
                    o = self.op_data.operators[agent]
                    if o.room not in plan:
                        plan[o.room] = ["Current"] * len(self.op_data.plan[o.room])
                    plan[o.room][o.index] = agent
                    planned.add(o.name)
            logger.debug(f"生成顶替上班任务{plan}")
            if plan:
                self.tasks.append(SchedulerTask(task_plan=plan))
                # 执行完提前换班任务再次执行本任务
                self.tasks.append(
                    SchedulerTask(
                        task_plan=copy.deepcopy(self.task.plan),
                        meta_data=self.task.meta_data,
                        task_type=self.task.type,
                    )
                )
            else:
                msg = f"无法完成 {self.task.meta_data} 的排班，请检查是否有替换组冲突"
                logger.warning(msg)
                send_message(msg, level="ERROR")
            self.skip()

    def handle_error(self, force=False):
        if self.scene() == Scene.UNKNOWN:
            self.device.exit()
            self.check_current_focus()
        if self.error or force:
            # 如果没有任何时间小于当前时间的任务才生成空任务
            if self.find_next_task(datetime.now()) is None:
                logger.debug("由于出现错误情况，生成一次空任务来执行纠错")
                self.tasks.append(SchedulerTask())
            # 如果没有任何时间小于当前时间的任务-10分钟 则清空任务
            if self.find_next_task(datetime.now() - timedelta(seconds=900)):
                logger.info("检测到执行超过15分钟的任务，清空全部任务")
                self.tasks = []
        elif self.find_next_task(datetime.now() + timedelta(hours=2.5)) is None:
            logger.debug("2.5小时内没有其他任务，生成一个空任务")
            self.tasks.append(SchedulerTask(time=datetime.now() + timedelta(hours=2.5)))
        return True

    def plan_fia(self):
        fia_plan, fia_room = self.check_fia()
        if fia_room is None or fia_plan is None:
            return
        # 肥鸭充能新模式：https://github.com/ArkMowers/arknights-mower/issues/551
        target = None
        if not config.conf.fia_fool:
            fia_threshold = config.conf.fia_threshold
            logger.info(f"菲亚防呆设计未开启，菲亚阈值为{fia_threshold}")
        else:
            fia_threshold = 0.9
            logger.info(f"菲亚防呆设计已开启，菲亚阈值为{fia_threshold}")
        for operator in fia_plan:
            data = self.op_data.operators[operator]
            operator_morale = data.current_mood()
            operator_limit = data.lower_limit
            logger.debug(f"{operator}的心情为{operator_morale}")
            if operator_morale > fia_threshold * 24:
                logger.debug(f"{operator}的心情高于阈值，跳过充能")
                continue
            if data.rest_in_full and data.exhaust_require and not data.is_resting():
                logger.debug(f"{operator}为暖机干员但不在宿舍，跳过充能")
                continue
            if data.group:
                lowest = True
                for member in self.op_data.groups[data.group]:
                    if member == operator:
                        continue
                    # Lancet-2
                    if (
                        self.op_data.operators[member].workaholic
                        and member not in fia_plan
                    ):
                        continue
                    member_morale = self.op_data.operators[member].current_mood()
                    member_limit = self.op_data.operators[member].lower_limit
                    logger.debug(f"{data.group}组内{member}的心情为{member_morale}")
                    if member_morale - member_limit < operator_morale - operator_limit:
                        lowest = False
                        logger.debug(f"{operator}的心情高于{member}，跳过充能")
                        break
                if not lowest:
                    continue
            target = operator
            break
        # 若全部跳过且关闭防呆则令目标干员为心情最低干员
        if target is None and not config.conf.fia_fool:
            target = fia_plan[0]
            op_mood = 24
            for op in fia_plan:
                data = self.op_data.operators[op]
                op_mood_t = data.current_mood()
                if data.rest_in_full and data.exhaust_require and not data.is_resting():
                    logger.debug(f"{operator}为暖机干员但不在宿舍，跳过充能")
                    continue
                if op_mood_t < op_mood:
                    target = op
                    op_mood = op_mood_t
        if target:
            self.tasks.append(
                SchedulerTask(
                    time=self.task.time,
                    task_type=TaskTypes.FIAMMETTA,
                    task_plan={fia_room: [target, "菲亚梅塔"]},
                )
            )
            # 充能结束后整组立即上班
            for task in self.tasks:
                if task.type == TaskTypes.SHIFT_ON:
                    for room, operators in task.plan.items():
                        if target in operators:
                            task.time = self.task.time + timedelta(seconds=1)
                            self.tasks.sort(key=lambda task: task.time)
                            return
        else:
            logger.info("肥鸭充能干员不足，请添加更多干员！")
            self.tasks.append(
                SchedulerTask(
                    time=self.task.time + timedelta(hours=24 * (1 - fia_threshold) / 2),
                    task_type=TaskTypes.FIAMMETTA,
                )
            )
            self.tasks.sort(key=lambda task: task.time)

    def plan_metadata(self):
        self.tasks = plan_metadata(self.op_data, self.tasks)

    def infra_main(self):
        """位于基建首页"""
        if self.find("control_central") is None:
            self.back()
            return
        if self.task is not None:
            try:
                if len(self.task.plan.keys()) > 0:
                    get_time = False
                    if TaskTypes.SHIFT_OFF == self.task.type:
                        get_time = True
                    if TaskTypes.RELEASE_DORM == self.task.type:
                        # 如果该房间提前已经被移出，则跳过安排避免影响正常排班
                        free_room = list(self.task.plan.keys())[0]
                        if "Free" in self.task.plan[free_room]:
                            free_index = self.task.plan[free_room].index("Free")
                            if self.task.meta_data in self.op_data.operators.keys():
                                free_agent = self.op_data.operators[self.task.meta_data]
                                if (
                                    free_agent.current_room == free_room
                                    and free_agent.current_index == free_index
                                ):
                                    get_time = True
                                    # 如果是高优先，还需要把宿舍reference移除
                                    if free_agent.is_high():
                                        idx, dorm = self.op_data.get_dorm_by_name(
                                            free_agent.name
                                        )
                                        if idx is not None:
                                            update_task = find_next_task(
                                                self.tasks,
                                                task_type=TaskTypes.SHIFT_ON,
                                                meta_data="dorm" + str(idx),
                                            )
                                            if update_task:
                                                logger.debug("开始更新宿舍信息")
                                                dorm_list = update_task.meta_data.split(
                                                    ","
                                                )
                                                dorm_list.remove("dorm" + str(idx))
                                                update_task.meta_data = ",".join(
                                                    dorm_list
                                                )
                                                free_agent.mood = free_agent.upper_limit
                                                free_agent.time_stamp = dorm.time
                                else:
                                    self.task.plan = {}
                            else:
                                self.task.plan = {}
                        else:
                            self.task.plan = {}
                    if (
                        config.conf.run_order_grandet_mode.back_to_index
                        and TaskTypes.RUN_ORDER == self.task.type
                        and not self.refresh_connecting
                        and config.conf.run_order_buffer_time > 0
                    ):
                        logger.info("跑单前返回主界面以保持登录状态")
                        self.back_to_index()
                        self.refresh_connecting = True
                        return
                    self.refresh_connecting = False
                    self.agent_arrange(self.task.plan, get_time)
                    if get_time:
                        if not self.backup_plan_solver(
                            PlanTriggerTiming.BEFORE_PLANNING
                        ):
                            self.plan_metadata()
                        else:
                            logger.info("检测到排班表切换，跳过plan")
                    if TaskTypes.RE_ORDER == self.task.type:
                        self.skip()
                # 如果任务名称包含干员名,则为动态生成的
                elif self.task.type == TaskTypes.FIAMMETTA:
                    self.plan_fia()
                elif (
                    self.task.meta_data.split(",")[0] in agent_list
                    and self.task.type == TaskTypes.EXHAUST_OFF
                ):
                    self.overtake_room()
                elif self.task.type == TaskTypes.CLUE_PARTY:
                    self.party_time = None
                    self.last_clue = None
                    self.clue_new()
                    self.last_clue = datetime.now()
                    self.skip(["collect_notification"])
                elif self.task.type == TaskTypes.REFRESH_TIME:
                    if self.task.meta_data == "train":
                        if upgrade := self.find_next_task(
                            task_type=TaskTypes.SKILL_UPGRADE
                        ):
                            self.refresh_skill_time(upgrade)
                    else:
                        self.plan_run_order(self.task.meta_data)
                    self.skip(["todo_task", "collect_notification"])
                elif self.task.type == TaskTypes.SKILL_UPGRADE:
                    self.skill_upgrade(self.task.meta_data)
                del self.tasks[0]
                if self.tasks and self.tasks[0].type in [TaskTypes.SHIFT_ON]:
                    self.backup_plan_solver(PlanTriggerTiming.AFTER_PLANNING)
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(e)
                if (
                    type(e) is ConnectionAbortedError
                    or type(e) is AttributeError
                    or type(e) is ConnectionError
                ):
                    raise e
                else:
                    self.skip()
                    self.error = True
            self.task = None
        elif not self.planned:
            try:
                # 如果有任何type 则会最后修正
                if not self.no_pending_task(1):
                    self.skip(["planned", "todo_task", "collect_notification"])
                else:
                    mood_result = self.agent_get_mood(skip_dorm=True)
                    if mood_result is not None:
                        self.skip(["planned", "todo_task", "collect_notification"])
                        return True
                    self.run_order_solver()
                    self.plan_solver()
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(e)
                if (
                    type(e) is ConnectionAbortedError
                    or type(e) is AttributeError
                    or type(e) is ConnectionError
                ):
                    raise e
                else:
                    self.error = True
            self.planned = True
        elif not self.todo_task:
            if (
                self.enable_party
                and (
                    self.last_clue is None
                    or datetime.now() - self.last_clue > timedelta(hours=1)
                )
                and self.no_pending_task(3)
            ):
                self.clue_new()
                self.last_clue = datetime.now()
            if (
                self.drone_room not in self.op_data.run_order_rooms
                and (
                    self.drone_time is None
                    or self.drone_time
                    < datetime.now() - timedelta(hours=config.conf.drone_interval)
                )
                and self.drone_room is not None
                and self.no_pending_task(2)
            ):
                self.drone(self.drone_room)
                logger.info(f"记录本次无人机使用时间为:{datetime.now()}")
                self.drone_time = datetime.now()
            if (
                self.reload_room is not None
                and self.no_pending_task(2)
                and (
                    self.reload_time is None
                    or self.reload_time
                    < datetime.now() - timedelta(hours=config.conf.maa_gap)
                )
            ):
                self.reload()
                logger.info(f"记录本次补货时间为:{datetime.now()}")
            self.todo_task = True
        elif not self.collect_notification:
            if self.no_pending_task(1):
                notification = detector.infra_notification(self.recog.img)
                if notification is None:
                    self.sleep(1)
                    notification = detector.infra_notification(self.recog.img)
                if notification is not None:
                    self.tap(notification)
            self.collect_notification = True
        else:
            return self.handle_error()

    def translate_room(self, room):
        translations = {
            "room": lambda parts: f"B{parts[1]}0{parts[2]}",
            "dormitory": lambda parts: f"{parts[1]}层宿舍",
            "contact": lambda parts: "办公室",
            "central": lambda parts: "控制中枢",
            "factory": lambda parts: "加工站",
            "meeting": lambda parts: "会客室",
        }

        for keyword, translation_func in translations.items():
            if keyword in room:
                parts = room.split("_")
                return translation_func(parts)

        return room

    def agent_get_mood(self, skip_dorm=False, force=False):
        # 暂时规定纠错只适用于主班表
        need_read = set(
            v.room
            for k, v in self.op_data.operators.items()
            if v.need_to_refresh() and v.room in base_room_list
        )
        for room in need_read:
            error_count = 0
            # 由于训练室不纠错，如果训练室有干员且时间读取过就跳过
            current_working = [
                value
                for key, value in self.op_data.operators.items()
                if value.current_room == room
            ]

            if current_working and all(
                operator.time_stamp
                and operator.time_stamp
                > datetime.now()
                - timedelta(
                    hours=0.5 if operator.name in ["歌蕾蒂娅", "见行者"] else 2.5
                )
                for operator in current_working
            ):
                for e in current_working:
                    logger.debug(e.time_stamp)
                logger.debug(f"{room} 所有干员不满足扫描条件，跳过")
                continue
            while True:
                try:
                    self.enter_room(room)
                    _mood_data = self.get_agent_from_room(room)
                    mood_info = [
                        f"干员: '{item['agent']}', 心情: {round(item['mood'], 3)}"
                        for item in _mood_data
                    ]
                    logger.info(f"房间 {self.translate_room(room)}  {mood_info}")
                    break
                except MowerExit:
                    raise
                except Exception as e:
                    logger.exception(e)
                    if error_count > 3:
                        raise e
                    error_count += 1
                    self.back()
                    continue
            self.back()
        plan = self.op_data.plan
        fix_plan = {}
        for key in plan:
            if key == "train":
                continue
            need_fix = False
            _current_room = self.op_data.get_current_room(key, True)
            for idx, name in enumerate(_current_room):
                # 如果是空房间
                if name == "":
                    if not need_fix:
                        fix_plan[key] = ["Current"] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx].agent
                    continue
                # 随意人员则跳过
                if plan[key][idx].agent == "Free":
                    continue
                if not (
                    name == plan[key][idx].agent
                    or (
                        (
                            name in plan[key][idx].replacement
                            and name not in ["但书", "龙舌兰", "佩佩"]
                        )
                        and len(plan[key][idx].replacement) > 0
                    )
                ):
                    if not need_fix:
                        fix_plan[key] = ["Current"] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx].agent
        # 最后如果有任何高效组心情没有记录 或者高效组在宿舍
        miss_list = {k: v for (k, v) in self.op_data.operators.items() if v.not_valid()}
        if len(miss_list.keys()) > 0:
            # 替换到他应该的位置
            logger.debug(f"高效组心情没有记录{str(miss_list)}")
            for key in miss_list:
                _agent = miss_list[key]
                if (
                    _agent.group != ""
                    and next(
                        (
                            k
                            for k, v in self.op_data.operators.items()
                            if v.group == _agent.group
                            and not v.not_valid()
                            and v.is_resting()
                        ),
                        None,
                    )
                    is not None
                    and (
                        _agent.current_mood() == _agent.upper_limit
                        or _agent.workaholic
                        or _agent.mood == _agent.upper_limit
                    )
                ):
                    logger.debug(f"跳过检查{_agent}")
                    continue
                elif _agent.group != "":
                    # 把所有小组成员都移到工作站
                    agents = self.op_data.groups[_agent.group]
                    for a in agents:
                        __agent = self.op_data.operators[a]
                        if __agent.room not in fix_plan.keys():
                            fix_plan[__agent.room] = ["Current"] * len(
                                self.op_data.plan[__agent.room]
                            )
                        fix_plan[__agent.room][__agent.index] = a
                if _agent.room not in fix_plan.keys():
                    fix_plan[_agent.room] = ["Current"] * len(
                        self.op_data.plan[_agent.room]
                    )
                fix_plan[_agent.room][_agent.index] = key
                # 如果是错位：
                if (
                    _agent.current_index != -1 and _agent.current_index != _agent.index
                ) or (_agent.current_room != "" and _agent.room != _agent.current_room):
                    moved_room = _agent.current_room
                    moved_index = _agent.current_index
                    if moved_room not in fix_plan.keys():
                        fix_plan[moved_room] = ["Current"] * len(
                            self.op_data.plan[moved_room]
                        )
                    fix_plan[moved_room][moved_index] = self.op_data.plan[moved_room][
                        moved_index
                    ].agent
        if len(fix_plan.keys()) > 0:
            # 不能在房间里安排同一个人 如果有重复则换成Free
            remove_keys = []
            logger.debug(f"Fix_plan {str(fix_plan)}")
            for key in fix_plan:
                if "dormitory" in key:
                    # 如果宿舍差Free干员  则跳过
                    if (
                        next(
                            (e for e in fix_plan[key] if e not in ["Free", "Current"]),
                            None,
                        )
                        is None
                        and skip_dorm
                    ):
                        remove_keys.append(key)
                        continue
            if len(remove_keys) > 0:
                for item in remove_keys:
                    del fix_plan[item]
            # 还要确保同一组在同时上班
            for g in self.op_data.groups:
                g_agents = self.op_data.groups[g]
                is_any_working = next(
                    (
                        x
                        for x in g_agents
                        if self.op_data.operators[x].current_room != ""
                        and not self.op_data.operators[x].is_resting()
                    ),
                    None,
                )
                if is_any_working is not None:
                    # 确保所有人同时在上班
                    is_any_resting = next(
                        (
                            x
                            for x in g_agents
                            if self.op_data.operators[x].current_room == ""
                            or self.op_data.operators[x].is_resting()
                        ),
                        None,
                    )
                    if is_any_resting is not None:
                        # 生成纠错任务
                        for x in g_agents:
                            if (
                                self.op_data.operators[x].current_room == ""
                                or self.op_data.operators[x].is_resting()
                            ):
                                room = self.op_data.operators[x].room
                                if room not in fix_plan:
                                    fix_plan[room] = ["Current"] * len(plan[room])
                                fix_plan[room][self.op_data.operators[x].index] = x
            if len(fix_plan.keys()) > 0:
                # 如果5分钟之内有任务则跳过心情读取
                next_task = self.find_next_task()
                second = (
                    0
                    if next_task is None
                    else (next_task.time - datetime.now()).total_seconds()
                )
                # 如果下个任务的操作时间超过下个任务，则跳过
                if (
                    not force
                    and next_task is not None
                    and len(fix_plan.keys()) * 45 > second
                ):
                    logger.info("有未完成的任务，跳过纠错")
                    self.skip()
                    return
                else:
                    self.tasks.append(
                        SchedulerTask(
                            task_plan=fix_plan, task_type=TaskTypes.SELF_CORRECTION
                        )
                    )
                    logger.info(f"纠错任务为-->{fix_plan}")
                    return "self_correction"

    def refresh_skill_time(self, task):
        try:
            unknown_cnt = 0
            tasks = ["refresh"]
            while tasks:
                scene = self.train_scene()
                if scene == Scene.UNKNOWN:
                    unknown_cnt += 1
                    if unknown_cnt > 5:
                        unknown_cnt = 0
                        self.back_to_infrastructure()
                        self.enter_room("train")
                    else:
                        self.sleep()
                    continue
                if scene == Scene.CONNECTING:
                    self.sleep(1)
                if scene == Scene.INFRA_MAIN:
                    self.enter_room("train")
                if scene == Scene.TRAIN_MAIN:
                    task.time = self.double_read_time(
                        (
                            (236, 978),
                            (380, 1020),
                        ),
                        use_digit_reader=True,
                    )
                    del tasks[0]
                if scene == Scene.TRAIN_SKILL_SELECT:
                    self.back()
                if scene == Scene.TRAIN_SKILL_UPGRADE:
                    self.back()
            self.back()
        except Exception as e:
            logger.exception(e)

    def skill_upgrade(self, skill):
        try:
            unknown_cnt = 0
            tasks = ["collect", "upgrade", "confirm"]
            execute_time = None
            level = 1
            while tasks:
                scene = self.train_scene()
                if scene == Scene.UNKNOWN:
                    unknown_cnt += 1
                    if unknown_cnt > 5:
                        unknown_cnt = 0
                        self.back_to_infrastructure()
                        self.enter_room("train")
                    else:
                        self.sleep()
                elif scene == Scene.CONNECTING:
                    self.sleep()
                elif scene == Scene.INFRA_MAIN:
                    self.enter_room("train")
                elif scene == Scene.TRAIN_FINISH:
                    self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.5)
                elif scene == Scene.TRAIN_MAIN:
                    if tasks[0] == "collect":
                        completed = self.find("training_completed")
                        if completed:
                            logger.debug("训练完成")
                            self.tap(completed, interval=3)
                            del tasks[0]
                        else:
                            logger.info("检测到专精未完成,刷新任务时间")
                            execute_time = self.double_read_time(
                                (
                                    (236, 978),
                                    (380, 1020),
                                ),
                                use_digit_reader=True,
                            )
                            if execute_time > datetime.now():
                                self.tasks.append(
                                    SchedulerTask(
                                        time=execute_time,
                                        task_type=TaskTypes.SKILL_UPGRADE,
                                        meta_data=skill,
                                    )
                                )
                                return
                            else:
                                del tasks[0]
                    if tasks[0] == "upgrade":
                        # 进入技能选择界面
                        self.tap(
                            (self.recog.w * 0.05, self.recog.h * 0.95),
                            interval=0.5,
                        )
                    if tasks[0] == "confirm":
                        # 读取专精倒计时 如果没有，判定专精失败
                        execute_time = self.double_read_time(
                            ((236, 978), (380, 1020)), use_digit_reader=True
                        )
                        if execute_time < (datetime.now() + timedelta(hours=2)):
                            raise Exception(
                                "未获取专精时间倒计时，请确认技能专精材料充足"
                            )
                        else:
                            del tasks[0]
                elif scene == Scene.TRAIN_SKILL_SELECT:
                    if tasks[0] == "upgrade":
                        # 点击技能
                        height = (int(skill) - 1) * 0.3 + 0.32
                        self.ctap((self.recog.w * 0.33, self.recog.h * height))
                    else:
                        self.back()
                elif scene == Scene.TRAIN_SKILL_UPGRADE:
                    if tasks[0] == "upgrade":
                        # 根据剩余时间判定专精技能等级
                        finish_time = self.double_read_time(
                            (
                                (94, 998),
                                (223, 1048),
                            ),
                            use_digit_reader=True,
                        )
                        hours = (finish_time - datetime.now()).total_seconds() / 3600
                        if hours > 23:
                            level = 3
                        elif hours > 15:
                            level = 2
                        logger.info(f"本次专精将提升{skill}技能至{level}")
                        # 点击确认开始专精
                        self.tap((self.recog.w * 0.87, self.recog.h * 0.9))
                        del tasks[0]
                    else:
                        self.back()
                elif scene == Scene.TRAIN_SKILL_UPGRADE_ERROR:
                    # 如果材料不满足则会出现错误
                    if tasks[0] == "confirm":
                        raise Exception("专精材料不足")
                    else:
                        self.back()
            if len(self.op_data.skill_upgrade_supports) > 0:
                support = next(
                    (
                        e
                        for e in self.op_data.skill_upgrade_supports
                        if e.level == level
                    ),
                    None,
                )
                h = self.op_data.calculate_switch_time(support)
                if support is not None:
                    self.tasks.append(
                        SchedulerTask(task_plan={"train": [support.name, "Current"]})
                    )
                    # 提前10分钟换人，确保触发技能
                    # 3 级不需要换人
                    if level != 3:
                        swap_time = (
                            datetime.now() + timedelta(hours=h) - timedelta(minutes=10)
                        )
                        self.tasks.append(
                            SchedulerTask(
                                time=swap_time,
                                task_plan={"train": [support.swap_name, "Current"]},
                            )
                        )
                        self.tasks.append(
                            SchedulerTask(
                                time=swap_time + timedelta(seconds=1),
                                task_plan={},
                                task_type=TaskTypes.REFRESH_TIME,
                                meta_data="train",
                            )
                        )
                        # 默认 5小时
                        self.tasks.append(
                            SchedulerTask(
                                time=datetime.now()
                                + timedelta(hours=h + 5)
                                + timedelta(minutes=15),
                                task_plan={},
                                task_type=TaskTypes.SKILL_UPGRADE,
                                meta_data=skill,
                            )
                        )
                else:
                    self.tasks.append(
                        SchedulerTask(
                            time=execute_time,
                            task_plan={},
                            task_type=TaskTypes.SKILL_UPGRADE,
                            meta_data=skill,
                        )
                    )
            self.back()
        except Exception as e:
            logger.exception(e)
            send_message("专精任务失败" + str(e), level="ERROR")

    def plan_run_order(self, room):
        plan = self.op_data.plan
        if self.find_next_task(meta_data=room, task_type=TaskTypes.RUN_ORDER):
            return
        in_out_plan = {room: ["Current"] * len(plan[room])}
        for idx, x in enumerate(plan[room]):
            if any(
                any(char in replacement_str for replacement_str in x.replacement)
                for char in ["但书", "龙舌兰", "佩佩"]
            ):
                in_out_plan[room][idx] = x.replacement[0]
        self.tasks.append(
            SchedulerTask(
                time=self.get_run_order_time(room),
                task_plan=in_out_plan,
                task_type=TaskTypes.RUN_ORDER,
                meta_data=room,
            )
        )

    def run_order_solver(self):
        plan = self.op_data.plan
        if len(self.op_data.run_order_rooms) > 0:
            # 判定宿舍是否满员
            valid = True
            for key in plan.keys():
                if "dormitory" in key:
                    dorm = self.op_data.get_current_room(key)
                    if dorm is not None and len(dorm) == 5:
                        continue
                    else:
                        valid = False
                        logger.info("宿舍未满员,跳过读取插拔时间")
                        break
            if valid:
                # 处理龙舌兰/但书/佩佩的插拔
                for k, v in self.op_data.run_order_rooms.items():
                    self.plan_run_order(k)
                adj_task = scheduling(self.tasks)
                max_execution = 3
                adj_count = 0
                while adj_task is not None and adj_count < max_execution:
                    self.drone(adj_task.meta_data, adjust_time=True)
                    adj_task = scheduling(self.tasks)
                    adj_count += 1
        fia_plan, fia_room = self.check_fia()
        if fia_room is not None and fia_plan is not None:
            if self.find_next_task(task_type=TaskTypes.FIAMMETTA) is None:
                fia_data = self.op_data.operators["菲亚梅塔"]
                fia_idx = (
                    fia_data.current_index
                    if fia_data.current_index != -1
                    else fia_data.index
                )
                result = [{}] * (fia_idx + 1)
                result[fia_idx]["time"] = datetime.now()
                if fia_data.mood != 24:
                    if (
                        fia_data.time_stamp is not None
                        and fia_data.time_stamp > datetime.now()
                    ):
                        result[fia_idx]["time"] = fia_data.time_stamp
                    else:
                        self.enter_room(fia_room)
                        result = self.get_agent_from_room(fia_room, [fia_idx])
                        self.back()
                logger.info(
                    "下一次进行菲亚梅塔充能："
                    + result[fia_idx]["time"].strftime("%H:%M:%S")
                )
                self.tasks.append(
                    SchedulerTask(
                        time=result[fia_idx]["time"], task_type=TaskTypes.FIAMMETTA
                    )
                )
        for name in self.op_data.exhaust_agent:
            op = self.op_data.operators[name]
            if op.is_resting():
                continue
            if op.current_mood() <= op.lower_limit + 2:
                if (
                    self.find_next_task(
                        task_type=TaskTypes.EXHAUST_OFF, meta_data=op.name
                    )
                    is None
                ):
                    self.enter_room(op.current_room)
                    result = self.get_agent_from_room(
                        op.current_room, [op.current_index]
                    )
                    _time = datetime.now()
                    if (
                        result[op.current_index]["time"] is not None
                        and result[op.current_index]["time"] > _time
                    ):
                        _time = result[op.current_index]["time"] - timedelta(minutes=10)
                    elif (
                        op.current_mood() > 0.25 + op.lower_limit
                        and op.depletion_rate != 0
                    ):
                        _time = (
                            datetime.now()
                            + timedelta(
                                hours=(op.current_mood() - op.lower_limit - 0.25)
                                / op.depletion_rate
                            )
                            - timedelta(minutes=10)
                        )
                    self.back()
                    # plan 是空的是因为得动态生成
                    update_time = False
                    if op.group != "":
                        # 检查是否有其他同组任务，刷新时间
                        for item in self.op_data.groups[op.group]:
                            if item not in self.op_data.exhaust_agent:
                                continue
                            elif self.find_next_task(
                                task_type=TaskTypes.EXHAUST_OFF, meta_data=item
                            ):
                                update_time = True
                                exh_task = self.find_next_task(
                                    task_type=TaskTypes.EXHAUST_OFF,
                                    meta_data=item,
                                )
                                if _time < exh_task.time:
                                    logger.info(
                                        f"检测到用尽同组{op.name}比{item}提前下班，更新任务时间为{_time}"
                                    )
                                    exh_task.time = _time
                                exh_task.meta_data += f",{op.name}"
                                logger.debug(f"更新用尽meta_data为{exh_task.meta_data}")
                    if not update_time:
                        logger.info(f"生成{op.name}的下班任务")

                        self.tasks.append(
                            SchedulerTask(
                                time=_time,
                                task_type=TaskTypes.EXHAUST_OFF,
                                meta_data=op.name,
                            )
                        )
                    # 如果是生成的过去时间，则停止 plan 其他
                    if _time < datetime.now():
                        break

    def plan_solver(self):
        # 准备数据
        logger.debug(self.op_data.print())
        # 根据剩余心情排序
        self.total_agent = list(
            v
            for k, v in self.op_data.operators.items()
            if v.is_high() and not v.room.startswith("dorm")
        )
        self.total_agent.sort(key=lambda x: x.current_mood(), reverse=False)
        # 目前有换班的计划后面改
        logger.debug(f"当前基地数据--> {self.total_agent}")
        new_plan = {}
        try:
            # 重新排序
            if self.find_next_task(task_type=TaskTypes.SHIFT_OFF):
                logger.info("有未完成的下班任务")
                return
            self.plan_metadata()
            new_plan = self.resting()
        except MowerExit:
            raise
        except Exception as e:
            logger.exception(e)
        # 更新宿舍任务
        re_order_dorm_plan = try_reorder(self.op_data, new_plan)
        if re_order_dorm_plan:
            logger.debug(f"新增宿舍任务{re_order_dorm_plan}")
            task = SchedulerTask(
                task_plan=re_order_dorm_plan,
                task_type=TaskTypes.SHIFT_OFF if new_plan else TaskTypes.NOT_SPECIFIC,
            )
            self.tasks.append(task)
        if not self.find_next_task(datetime.now() + timedelta(minutes=5)):
            try_add_release_dorm({}, None, self.op_data, self.tasks)
        if self.find_next_task(datetime.now() + timedelta(seconds=15)):
            logger.info("有其他任务,跳过宿舍纠错")
            return
        if self.agent_get_mood() is None:
            self.backup_plan_solver()

    def resting(self):
        self.total_agent.sort(
            key=lambda x: x.current_mood() - x.lower_limit, reverse=False
        )
        self.plan_metadata()
        current_resting = (
            len(self.op_data.dorm)
            - self.op_data.available_free()
            - self.op_data.available_free("low")
        )
        # 阈值暂定为 0.5
        self.ideal_resting_count = (
            4
            if self.op_data.average_mood()
            > self.op_data.config.resting_threshold * config.conf.rescue_threshold
            else len(self.op_data.dorm)
        )
        logger.debug(f"当前理想休息人数是{self.ideal_resting_count}")
        _replacement = []
        _plan = {}
        for op in self.total_agent:
            if (
                current_resting + len(_replacement) >= self.ideal_resting_count
                and self.op_data.available_free() == 0
            ):
                break
            if op.name in self.op_data.workaholic_agent:
                continue
            if (
                op.is_resting()
                or op.current_room in ["factory", "train"]
                or op.room in ["factory", "train"]
            ):
                continue
            # 忽略掉心情太高的
            if op.upper_limit - op.current_mood() < 2:
                continue
            # 忽略 用尽，已经处理
            if op.name in self.op_data.exhaust_agent:
                continue
            # 忽略掉心情值没低于上限的的
            if op.current_mood() > int(
                (op.upper_limit - op.lower_limit)
                * self.op_data.config.resting_threshold
                + op.lower_limit
            ):
                continue
            if op.group != "":
                if op.group in self.op_data.exhaust_group:
                    # 忽略掉用尽心情的分组
                    continue
                group_resting = self.op_data.groups[op.group]
                self.get_resting_plan(
                    group_resting, _replacement, _plan, current_resting
                )
            else:
                self.get_resting_plan([op.name], _replacement, _plan, current_resting)
        if len(_plan.keys()) > 0:
            self.tasks.append(
                SchedulerTask(task_plan=_plan, task_type=TaskTypes.SHIFT_OFF)
            )
            logger.info(f"生成{_plan}的下班任务")
        return _plan

    def backup_plan_solver(self, timing=None):
        if timing is None:
            timing = PlanTriggerTiming.END
        try:
            new_task = False
            if self.op_data.backup_plans:
                con = copy.deepcopy(self.op_data.plan_condition)
                current_con = self.op_data.plan_condition
                for idx, bp in enumerate(self.op_data.backup_plans):
                    func = str(bp.trigger)
                    logger.debug(func)
                    con[idx] = self.op_data.evaluate_expression(func)
                    if (
                        current_con[idx] != con[idx]
                        and bp.trigger_timing.value <= timing.value
                    ):
                        task = self.op_data.backup_plans[idx].task
                        if task and con[idx]:
                            new_task = True
                            self.tasks.append(
                                SchedulerTask(task_plan=copy.deepcopy(task))
                            )
                    else:
                        # 不切换
                        con[idx] = current_con[idx]
                # 不满足条件且为其他排班表，则切换回来
                if con != current_con:
                    logger.info(
                        f"检测到副班条件变更，启动超级变换形态, 当前条件:{current_con}"
                    )
                    logger.info(f"新条件列表:{con}")
                    self.op_data.swap_plan(con, refresh=True)
                    if not new_task:
                        self.tasks.append(SchedulerTask(task_plan={}))
            return new_task
        except MowerExit:
            raise
        except Exception as e:
            logger.exception(e)
        return False

    def rearrange_resting_priority(self, group):
        operators = self.op_data.groups[group]
        # 肥鸭充能新模式：https://github.com/ArkMowers/arknights-mower/issues/551
        fia_plan, fia_room = self.check_fia()
        # 排序
        # 1. 肥鸭充能列表中的干员靠前
        # 2. 不在加工站的干员靠前
        # 3. 心情低的干员靠前
        operators.sort(
            key=lambda y: (
                y not in fia_plan if fia_plan else True,
                self.op_data.operators[y].current_room in ["factory", "train"],
                self.op_data.operators[y].current_mood()
                - self.op_data.operators[y].lower_limit,
            )
        )

        high_count = 0
        for operator in operators:
            if self.op_data.operators[operator].workaholic:
                continue
            if self.op_data.operators[operator].resting_priority == "high":
                high_count += 1
        for operator in operators:
            if self.op_data.operators[operator].workaholic:
                continue
            self.op_data.operators[operator].resting_priority = (
                "high" if high_count > 0 else "low"
            )
            high_count -= 1

    def get_resting_plan(self, agents, exist_replacement, plan, current_resting):
        __replacement = []
        __plan = {}
        required = 0
        for x in agents:
            op = self.op_data.operators[x]
            if op.workaholic:
                continue
            required += 1
        logger.debug(f"需求:{current_resting} 当前休息")
        logger.debug(f"需求:{required}宿舍空位")
        logger.debug(f"需求:{exist_replacement} 当前安排")
        logger.debug(f"当前计划{plan}")
        if current_resting + required + len(exist_replacement) > len(self.op_data.dorm):
            return
        success = True

        fia_plan, fia_room = self.check_fia()
        agents.sort(
            key=lambda y: (
                y not in fia_plan if fia_plan else True,
                self.op_data.operators[y].current_room in ["factory", "train"],
                self.op_data.operators[y].current_mood()
                - self.op_data.operators[y].lower_limit,
            )
        )
        logger.debug(f"计算排班:{agents}")
        for agent in agents:
            if not success:
                break
            x = self.op_data.operators[agent]
            if x.room not in base_room_list:
                logger.debug(f"干员房间出错:{agent}")
                success = False
                break
            if self.op_data.get_dorm_by_name(x.name)[0] is not None:
                # 如果干员已经被安排了
                success = False
                break
            _rep = next(
                (
                    obj
                    for obj in x.replacement
                    if (
                        not (
                            self.op_data.operators[obj].current_room != ""
                            and not self.op_data.operators[obj].is_resting()
                        )
                    )
                    and obj not in ["但书", "龙舌兰", "佩佩"]
                    and obj not in exist_replacement
                    and obj not in __replacement
                    and self.op_data.operators[obj].current_room != x.room
                ),
                None,
            )
            if _rep is not None:
                __replacement.append(_rep)
                if x.room not in __plan.keys():
                    __plan[x.room] = ["Current"] * len(self.op_data.plan[x.room])
                __plan[x.room][x.index] = _rep
            else:
                success = False
        if success:
            # 记录替换组
            logger.debug(f"当前替换{__replacement}")
            exist_replacement.extend(__replacement)
            for idx, x in enumerate(agents):
                # 0心情不需要宿舍位
                if self.op_data.operators[x].workaholic:
                    continue
                _dorm = self.op_data.assign_dorm(x, True)
            logger.debug(_dorm)
            for k, v in __plan.items():
                if k not in plan.keys():
                    plan[k] = __plan[k]
                for idx, name in enumerate(__plan[k]):
                    if plan[k][idx] == "Current" and name != "Current":
                        plan[k][idx] = name
            logger.debug(f"当前plan{plan}")

    def initialize_operators(self):
        self.op_data = Operators(self.global_plan)
        Operators.current_room_changed_callback = self.current_room_changed
        return self.op_data.init_and_validate()

    def check_fia(self):
        if "菲亚梅塔" in self.op_data.operators.keys() and self.op_data.operators[
            "菲亚梅塔"
        ].room.startswith("dormitory"):
            return self.op_data.operators[
                "菲亚梅塔"
            ].replacement, self.op_data.operators["菲亚梅塔"].room
        return None, None

    def get_run_order_time(self, room):
        logger.info("基建：读取插拔时间")
        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        error_count = 0
        while self.find("bill_accelerate") is None:
            if error_count > 5:
                raise Exception("未成功进入无人机界面")
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
            error_count += 1
        execute_time = self.double_read_time(
            (
                (int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404)),
                (int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
            ),
            use_digit_reader=True,
        )
        execute_time = execute_time - timedelta(
            seconds=(60 * config.conf.run_order_delay)
        )
        logger.info("下一次进行插拔的时间为：" + execute_time.strftime("%H:%M:%S"))
        self.scene_graph_navigation(Scene.INFRA_MAIN)
        return execute_time

    def todo_list(self) -> None:
        """处理基建 Todo 列表"""
        tapped = False
        collect = {"bill": "订单", "factory": "制造站产物", "trust": "信赖"}
        if self.last_execution["todo"] is None or self.last_execution[
            "todo"
        ] < datetime.now() - timedelta(minutes=15):
            for res, name in collect.items():
                tap_times = 0
                while pos := self.find(f"infra_collect_{res}"):
                    logger.info(f"收取{name}")
                    self.tap(pos)
                    tapped = True
                    tap_times += 1
                    if tap_times > 0:
                        break
            self.last_execution["todo"] = datetime.now()
        if not tapped:
            # 点击右上角的通知图标
            # 可能被产物收取提示挡住，所以直接点位置
            self.tap((1840, 140))
            self.todo_task = True

    def clue_new(self):
        try:
            logger.info("基建：线索")
            self.scene_graph_navigation(Scene.INFRA_MAIN)
            self.enter_room("meeting")

            clue_size = (162, 216)
            clue_top_left = {
                "daily": (1118, 334),
                "receive": (1305, 122),
                "give_away": (30, 208),
                # 摆放线索界面，线索框的左上角
                1: (72, 228),
                2: (374, 334),
                3: (679, 198),
                4: (1003, 265),
                5: (495, 660),
                6: (805, 573),
                7: (154, 608),
            }
            dot_offset = (168, -8)
            main_offset = (425, 0)
            main_time_offset = (443, 257)

            def va(a, b):
                return a[0] + b[0], a[1] + b[1]

            def tl2p(top_left):
                return top_left, va(top_left, clue_size)

            def is_orange(dot):
                orange_dot = (255, 104, 1)
                return all([abs(dot[i] - orange_dot[i]) < 3 for i in range(3)])

            clue_scope = {}
            for index, top_left in clue_top_left.items():
                clue_scope[index] = tl2p(top_left)
            clue_dots = {}
            main_dots = {}
            main_time = {}
            main_scope = {}
            for i in range(1, 8):
                clue_dots[i] = va(clue_top_left[i], dot_offset)
                main_dots[i] = va(clue_dots[i], main_offset)
                main_time[i] = va(clue_top_left[i], main_time_offset)
                main_scope[i] = tl2p(va(clue_top_left[i], main_offset))

            class ClueTaskManager:
                def __init__(self):
                    # 操作顺序：领取每日线索、接收好友线索、摆线索、送线索、更新线索交流结束时间
                    self.task_list = [
                        "daily",
                        "receive",
                        "place",
                        "give_away",
                        "party_time",
                    ]
                    self.task = self.task_list[0]

                def complete(self, task):
                    task = task or self.task
                    if task in self.task_list:
                        self.task_list.remove(task)
                    self.task = self.task_list[0] if self.task_list else None

            tm_thres = 0.6

            def clue_cls(scope):
                scope_dict = clue_scope if isinstance(scope, str) else main_scope
                img = cropimg(self.recog.img, scope_dict[scope])
                for i in range(1, 8):
                    res = loadres(f"clue/{i}")
                    result = cv2.matchTemplate(img, res, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                    if max_val > tm_thres:
                        return i
                return None

            exit_pos = (1239, 144)

            ctm = ClueTaskManager()

            friend_clue = []

            clue_status = {}

            def place_index():
                for cl, st in clue_status.items():
                    if st in ["available", "self", "available_self_only"]:
                        return cl, st
                return None, None

            def detect_unlock():
                unlock_pos = self.find("clue/button_unlock")
                if unlock_pos is None:
                    return None
                color = self.get_color(self.get_pos(unlock_pos))
                if all(color > [252] * 3):
                    return unlock_pos
                return None

            while ctm.task:
                scene = self.scene()

                if scene == Scene.INFRA_DETAILS:
                    logger.info("INFRA_DETAILS")
                    if ctm.task == "party_time":
                        if pos := self.find("clue/check_party"):
                            logger.info("tap")
                            self.tap(pos)
                        self.party_time = self.double_read_time(
                            ((1768, 438), (1902, 480))
                        )
                        if self.party_time > datetime.now():
                            logger.info(f"线索交流结束时间：{self.party_time}")
                            if not find_next_task(
                                self.tasks,
                                task_type=TaskTypes.CLUE_PARTY,
                            ):
                                self.tasks.append(
                                    SchedulerTask(
                                        time=self.party_time
                                        - timedelta(milliseconds=1),
                                        task_type=TaskTypes.CLUE_PARTY,
                                    )
                                )
                        else:
                            self.party_time = None
                            logger.info("线索交流未开启")
                        ctm.complete("party_time")
                    else:
                        # 点击左下角，关闭进驻信息，进入线索界面
                        self.tap((330, 1000))

                elif scene == Scene.INFRA_CONFIDENTIAL:
                    logger.info("INFRA_CONFIDENTIAL")
                    if ctm.task == "daily":
                        # 检查是否领过线索
                        daily_scope = ((1815, 200), (1895, 250))
                        if self.find("clue/badge_new", scope=daily_scope):
                            self.tap((1800, 270))
                        else:
                            ctm.complete("daily")
                    elif ctm.task == "receive":
                        receive_scope = ((1815, 360), (1895, 410))
                        if self.find("clue/badge_new", scope=receive_scope):
                            self.ctap((1800, 430))
                        else:
                            ctm.complete("receive")
                    elif ctm.task == "place":
                        if unlock_pos := detect_unlock():
                            self.tap(unlock_pos)
                            continue
                        for i in range(1, 8):
                            if is_orange(self.get_color(main_dots[i])):
                                clue_status[i] = "available"
                            elif clue_cls(i):
                                hsv = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
                                if 160 < hsv[main_time[i][1]][main_time[i][0]][0] < 180:
                                    clue_status[i] = "friend"
                                else:
                                    clue_status[i] = "self"
                            else:
                                clue_status[i] = None
                        cl, st = place_index()
                        if st in ["available", "self", "available_self_only"]:
                            self.tap(main_scope[cl])
                            continue
                        else:
                            ctm.complete("place")
                    elif ctm.task == "give_away":
                        self.ctap((1799, 578))
                    elif ctm.task == "party_time":
                        self.back()

                elif scene == Scene.CLUE_DAILY:
                    logger.info("CLUE_DAILY")
                    if not self.find(
                        "clue/icon_notification", scope=((1400, 0), (1920, 400))
                    ) and (clue := clue_cls("daily")):
                        logger.info(f"领取今日线索（{clue}号）")
                        self.tap_element("clue/button_get")
                        ctm.complete("daily")
                    else:
                        # 今日线索已领取，点X退出
                        self.tap((1484, 152))

                elif scene == Scene.CLUE_RECEIVE:
                    logger.info("CLUE_RECEIVE")
                    if self.find(
                        "infra_trust_complete",
                        scope=((1230, 0), (1920, 1080)),
                        score=0.1,
                    ):
                        self.sleep()
                        continue
                    if clue := clue_cls("receive"):
                        name_scope = ((1580, 220), (1880, 255))
                        name_img = cropimg(self.recog.gray, name_scope)
                        name_img = cv2.copyMakeBorder(
                            name_img, 48, 48, 48, 48, cv2.BORDER_REPLICATE
                        )
                        name = rapidocr.engine(
                            name_img,
                            use_det=True,
                            use_cls=False,
                            use_rec=True,
                        )[0][0][1]
                        name = name.strip() if name else "好友"
                        logger.info(f"接收{name}的{clue}号线索")
                        self.tap(name_scope)
                    else:
                        ctm.complete("receive")
                        self.tap(exit_pos)

                elif scene == Scene.CLUE_PLACE:
                    logger.info("CLUE_PLACE")
                    cl, st = place_index()
                    if cl is None:
                        if unlock_pos := detect_unlock():
                            self.tap(unlock_pos)
                        else:
                            ctm.complete("place")
                            self.tap(exit_pos)
                        continue
                    if self.get_color((1328 + 77 * cl, 114))[0] < 150:
                        # 右上角 1-7
                        self.tap(clue_scope[cl])
                        continue
                    receive = st in ["available", "self"]
                    filter_receive = (1900, 45)
                    filter_self = (1610, 70)
                    filter_pos = filter_receive if receive else filter_self
                    if not all(self.get_color(filter_pos) > [252] * 3):
                        self.tap(filter_pos)
                        continue
                    clue_pos = ((1305, 208), (1305, 503), (1305, 797))
                    clue_list = []
                    for cp in clue_pos:
                        clue_img = cropimg(self.recog.img, tl2p(cp))
                        res = loadres(f"clue/{cl}")
                        result = cv2.matchTemplate(clue_img, res, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                        if max_val > tm_thres:
                            name_scope = (va(cp, (274, 99)), va(cp, (580, 134)))
                            name_img = cropimg(self.recog.gray, name_scope)
                            name_img = cv2.copyMakeBorder(
                                name_img, 48, 48, 48, 48, cv2.BORDER_REPLICATE
                            )
                            name = rapidocr.engine(
                                name_img,
                                use_det=True,
                                use_cls=False,
                                use_rec=True,
                            )[0][0][1]
                            if name:
                                name = name.strip()
                            time_scope = (va(cp, (45, 222)), va(cp, (168, 255)))
                            time_hsv = cropimg(self.recog.img, time_scope)
                            time_hsv = cv2.cvtColor(time_hsv, cv2.COLOR_RGB2HSV)
                            if 165 < time_hsv[0][0][0] < 175:
                                time_img = thres2(
                                    cropimg(self.recog.gray, time_scope), 180
                                )
                                time_img = cv2.copyMakeBorder(
                                    time_img, 48, 48, 48, 48, cv2.BORDER_REPLICATE
                                )
                                time = rapidocr.engine(
                                    time_img,
                                    use_det=True,
                                    use_cls=False,
                                    use_rec=True,
                                )[0][0][1]
                                if time:
                                    time = time.strip()
                            else:
                                time = None
                            clue_list.append(
                                {"name": name, "time": time, "scope": tl2p(cp)}
                            )
                        else:
                            break
                    if clue_list:
                        list_name = "接收库" if receive else "自有库"
                        logger.info(f"{cl}号线索{list_name}：{clue_list}")
                        selected = None
                        for c in clue_list:
                            if c["time"]:
                                selected = c
                                break
                        selected = selected or clue_list[0]
                        self.tap(selected["scope"])
                        if clue_status[cl] == "available":
                            clue_status[cl] = "friend"
                        elif clue_status[cl] == "available_self_only":
                            clue_status[cl] = "self_only"
                        elif clue_status[cl] == "self":
                            clue_status[cl] = "friend"
                        else:
                            clue_status[cl] = None
                    else:
                        if clue_status[cl] == "available":
                            clue_status[cl] = "available_self_only"
                        elif clue_status[cl] == "available_self_only":
                            clue_status[cl] = None
                        elif clue_status[cl] == "self":
                            clue_status[cl] = "self_only"
                        else:
                            clue_status[cl] = None

                elif scene == Scene.CLUE_GIVE_AWAY:
                    logger.info("CLUE_GIVE_AWAY")
                    give_away_true = self.leifeng_mode or (
                        not self.leifeng_mode
                        and self.clue_count > self.clue_count_limit
                    )
                    if (c := clue_cls("give_away")) and give_away_true:
                        if not friend_clue:
                            if self.find(
                                "clue/icon_notification", scope=((1400, 0), (1920, 400))
                            ):
                                self.sleep()
                                continue
                            for i in range(4):
                                label_scope = (
                                    (1450, 228 + i * 222),
                                    (1580, 278 + i * 222),
                                )
                                if not self.find(
                                    "clue/label_give_away", scope=label_scope
                                ):
                                    break
                                name_top_left = (870, 127 + 222 * i)
                                name_scope = (
                                    name_top_left,
                                    va(name_top_left, (383, 62)),
                                )
                                name = rapidocr.engine(
                                    cropimg(self.recog.gray, name_scope),
                                    use_det=True,
                                    use_cls=False,
                                    use_rec=True,
                                )[0][0][1]
                                if name:
                                    name = name.strip()
                                data = {"name": name}
                                for j in range(1, 8):
                                    pos = (1230 + j * 64, 142 + i * 222)
                                    data[j] = self.get_color(pos)[0] < 137
                                friend_clue.append(data)
                        logger.debug(friend_clue)
                        friend = None
                        for idx, fc in enumerate(friend_clue):
                            if not fc[c]:
                                friend = idx
                                fc[c] = True
                                break
                        friend = friend or 0
                        logger.info(f"给{friend_clue[friend]['name']}送一张线索{c}")
                        self.tap(clue_scope["give_away"])
                        self.clue_count -= 1
                        self.tap((1790, 200 + friend * 222))
                    else:
                        ctm.complete("give_away")
                        self.tap((1868, 54))

                elif scene == Scene.CLUE_SUMMARY:
                    logger.info("CLUE_SUMMARY")
                    self.back()

                elif scene in self.waiting_scene:
                    logger.info("waiting_scene")
                    self.waiting_solver()

                else:
                    self.scene_graph_navigation(Scene.INFRA_MAIN)
                    self.enter_room("meeting")
            shop_solver = CreditShop(self.device, self.recog)
            shop_solver.run()
            self.scene_graph_navigation(Scene.INFRA_MAIN)
        except Exception as e:
            logger.exception(e)
            return

    def adjust_order_time(self, accelerate, room):
        error_count = 0
        action_required_task = scheduling(self.tasks)
        while (
            action_required_task is not None and action_required_task.meta_data == room
        ):
            self.tap(accelerate)
            if self.scene() in self.waiting_scene:
                if not self.waiting_solver():
                    return
            self.tap((self.recog.w * 1320 // 1920, self.recog.h * 502 // 1080))
            if self.scene() in self.waiting_scene:
                if not self.waiting_solver():
                    return
            self.tap((self.recog.w * 3 // 4, self.recog.h * 4 // 5))
            if self.scene() in self.waiting_scene:
                if not self.waiting_solver():
                    return
            while self.find("bill_accelerate") is None:
                if error_count > 5:
                    raise Exception("未成功进入订单界面")
                self.tap((self.recog.w // 20, self.recog.h * 19 // 20), interval=1)
                error_count += 1
            _time = self.double_read_time(
                (
                    (self.recog.w * 650 // 2496, self.recog.h * 660 // 1404),
                    (self.recog.w * 815 // 2496, self.recog.h * 710 // 1404),
                ),
                use_digit_reader=True,
            )
            task_time = _time - timedelta(minutes=config.conf.run_order_delay)
            if task := find_next_task(
                self.tasks, task_type=TaskTypes.RUN_ORDER, meta_data=room
            ):
                task.time = task_time
                logger.info(
                    f"房间 {room} 无人机加速后接单时间为 {task_time.strftime('%H:%M:%S')}"
                )
                action_required_task = scheduling(self.tasks)
            else:
                break

    def drone(
        self,
        room: str,
        not_customize=False,
        not_return=False,
        adjust_time=False,
        skip_enter=False,
    ):
        logger.info("基建：无人机加速" if not adjust_time else "开始调整订单时间")
        all_in = 0
        if not not_customize:
            all_in = len(self.op_data.run_order_rooms)
        # 点击进入该房间
        if not skip_enter:
            self.enter_room(room)
        # 进入房间详情

        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
        # 关闭掉房间总览
        error_count = 0
        while (
            self.find("factory_accelerate") is None
            and self.find("bill_accelerate") is None
        ):
            if error_count > 5:
                raise Exception("未成功进入无人机界面")
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
            error_count += 1

        accelerate = self.find("factory_accelerate")
        if accelerate:
            drone_count = self.digit_reader.get_drone(self.recog.gray)
            logger.info(f"当前无人机数量为：{drone_count}")
            if drone_count < config.conf.drone_count_limit or drone_count > 225:
                logger.info(f"无人机数量小于{config.conf.drone_count_limit}->停止")
                return
            logger.info("制造站加速")
            self.tap(accelerate)
            # self.tap_element('all_in')
            # 如果不是全部all in
            if all_in > 0:
                tap_times = (
                    drone_count - config.conf.drone_count_limit
                )  # 修改为无人机阈值
                for _count in range(tap_times):
                    self.tap((self.recog.w * 0.7, self.recog.h * 0.5), interval=0.1)
            else:
                self.tap_element("all_in")
            self.tap(accelerate, y_rate=1)
        else:
            accelerate = self.find("bill_accelerate")
            while accelerate and not adjust_time:
                logger.info("贸易站加速")
                self.tap(accelerate)
                self.tap_element("all_in")
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8))
                if self.scene() in self.waiting_scene:
                    if not self.waiting_solver():
                        return
                self.recog.update()
                self.accept_order()
                if not (
                    self.drone_room is None
                    or (
                        self.drone_room == room and room in self.op_data.run_order_rooms
                    )
                ):
                    break
                if not_customize:
                    drone_count = self.digit_reader.get_drone(self.recog.gray)
                    logger.info(f"当前无人机数量为：{drone_count}")
                    # 200 为识别错误
                    if (
                        drone_count < config.conf.drone_count_limit
                        or drone_count == 201
                    ):
                        logger.info(
                            f"无人机数量小于{config.conf.drone_count_limit}->停止"
                        )
                        break
                accelerate = self.find("bill_accelerate")
            if adjust_time:
                self.adjust_order_time(accelerate, room)
        if not_return:
            return
        self.scene_graph_navigation(Scene.INFRA_MAIN)

    # 用于制造站切换产物，请注意在调用该函数前有足够的无人机，并补足相应制造站产物，目前仅支持中级作战记录与赤金之间的切换
    # def 制造站切换产物(self, room: str, 目标产物: str, not_customize=False, not_return=False):
    #     # 点击进入该房间
    #     self.enter_room(room)
    #     while self.get_infra_scene() == 9:
    #         time.sleep(1)
    #         self.recog.update()
    #     # 进入房间详情
    #     self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
    #     # 关闭掉房间总览
    #     error_count = 0
    #     while self.find('factory_accelerate') is None:
    #         if error_count > 5:
    #             raise Exception('未成功进入制造详情界面')
    #         self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
    #         error_count += 1
    #     accelerate = self.find('factory_accelerate')
    #     无人机数量 = self.digit_reader.get_drone(self.recog.gray, self.recog.h, self.recog.w)
    #     if accelerate:
    #         self.tap_element('factory_accelerate')
    #         self.recog.update()
    #         剩余制造加速总时间 = self.digit_reader.识别制造加速总剩余时间(self.recog.gray, self.recog.h, self.recog.w)
    #         # logger.info(f'制造站 B{room[5]}0{room[7]} 剩余制造总时间为 {剩余制造加速总时间}')
    #         时 = int(剩余制造加速总时间[0:3])
    #         if 时 > 118: 当前产物 = '经验'
    #         else:   当前产物 = '赤金'
    #         if 当前产物 == 目标产物:
    #             logger.info('返回基建主界面')
    #             while self.get_infra_scene() != 201:
    #                 if self.find('index_infrastructure') is not None:
    #                     self.tap_element('index_infrastructure')
    #                 elif self.find('12cadpa') is not None:
    #                     self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                 else:
    #                     self.back()
    #                 self.recog.update()
    #         else:
    #             logger.info(f'制造站 B{room[5]}0{room[7]} 当前产物为{当前产物}，切换产物为{目标产物}')
    #             需要无人机数 = 0
    #             while 需要无人机数 < 10:
    #                 总分钟数 = int(剩余制造加速总时间[4:6]) + 60 * 时
    #                 if 当前产物 == '赤金':
    #                     需要无人机数 = (总分钟数 % 72) // 3 + 1
    #                 elif 当前产物 == '经验':
    #                     需要无人机数 = (总分钟数 % 180) // 3 + 1
    #                 else:
    #                     logger.warning('目前不支持该产物切换策略，尚待完善')
    #                     logger.info('返回基建主界面')
    #                     while self.get_infra_scene() != 201:
    #                         if self.find('index_infrastructure') is not None:
    #                             self.tap_element('index_infrastructure')
    #                         elif self.find('12cadpa') is not None:
    #                             self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                         else:
    #                             self.back()
    #                         self.recog.update()
    #                 if 需要无人机数 > 无人机数量 - 10:
    #                     logger.warning(f'''
    #                     切换产物需要无人机{需要无人机数}个，当前仅有{无人机数量}个，
    #                     无法切换产物，建议该任务至少在{(需要无人机数 - 无人机数量 + 10) * 3.5 // 3}分钟后再执行
    #                     ''')
    #                     logger.info('返回基建主界面')
    #                     while self.get_infra_scene() != 201:
    #                         if self.find('index_infrastructure') is not None:
    #                             self.tap_element('index_infrastructure')
    #                         elif self.find('12cadpa') is not None:
    #                             self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                         else:
    #                             self.back()
    #                         self.recog.update()
    #                 else:
    #                     logger.warning(f'需要加无人机{需要无人机数}个')
    #                     for 次数 in range(需要无人机数):
    #                         self.tap((self.recog.w * 1320 // 1920, self.recog.h * 502 // 1080), interval=0.05)
    #                     self.recog.update()
    #                     剩余制造加速总时间 = self.digit_reader.识别制造加速总剩余时间(
    #                         self.recog.gray, self.recog.h, self.recog.w)
    #                     # logger.info(f'制造站 B{room[5]}0{room[7]} 剩余制造总时间为 {剩余制造加速总时间}')
    #                 总分钟数 = int(剩余制造加速总时间[4:6]) + 60 * 时
    #                 if 当前产物 == '赤金':
    #                     需要无人机数 = (总分钟数 % 72) // 3 + 1
    #                 elif 当前产物 == '经验':
    #                     需要无人机数 = (总分钟数 % 180) // 3 + 1
    #                 else:
    #                     logger.warning('目前不支持该产物切换策略，尚待完善')
    #                     logger.info('返回基建主界面')
    #                     while self.get_infra_scene() != 201:
    #                         if self.find('index_infrastructure') is not None:
    #                             self.tap_element('index_infrastructure')
    #                         elif self.find('12cadpa') is not None:
    #                             self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                         else:
    #                             self.back()
    #                         self.recog.update()
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 4 // 5), interval=3)    # 确认加速
    #             self.tap((self.recog.w * 9 // 10, self.recog.h // 2), interval=1)     # 点击当前产品
    #             if 目标产物 == '经验':
    #                 self.tap((self.recog.w // 2, self.recog.h // 2), interval=1)    # 点击中级作战记录
    #             elif 目标产物 == '赤金':
    #                 self.tap((self.recog.w // 10, self.recog.h // 3), interval=1)   # 进入贵金属分类
    #                 self.tap((self.recog.w // 2, self.recog.h // 4), interval=1)    # 点击赤金
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 2 // 7), interval=1)    # 点击最多
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 5 // 6), interval=1)    # 确认数量
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 7 // 10), interval=1)   # 确认更改

    def get_order(self, name):
        if name in self.op_data.operators:
            return True, self.op_data.operators[name].arrange_order
        else:
            return False, [2, "false"]

    def tap_confirm(self, room, new_plan=None):
        if new_plan is None:
            new_plan = {}
        self.recog.update()
        if (
            room in self.op_data.run_order_rooms
            and len(new_plan) == 1
            and config.conf.run_order_buffer_time > 0
        ):
            wait_confirm = round(
                (
                    (self.task.time - datetime.now()).total_seconds()
                    + config.conf.run_order_delay * 60
                    - config.conf.run_order_buffer_time
                ),
                1,
            )
            if wait_confirm > 0:
                logger.info(f"等待跑单 {str(wait_confirm)} 秒")
                self.sleep(wait_confirm)
        retry_count = 0
        while self.find("confirm_blue") and retry_count < 4:
            self.tap_element("confirm_blue")
            self.sleep(0.5)
            self.recog.update()
            retry_count += 1
        retry_count = 0
        while self.find("arrange_confirm") and retry_count < 4:
            _x0 = self.recog.w // 3 * 2  # double confirm
            _y0 = self.recog.h - 10
            self.tap((_x0, _y0))
            self.sleep(0.5)
            self.recog.update()

    def choose_train_agent(
        self, current_room, agents, idx, error_count=0, fast_mode=False
    ):
        if current_room[idx] != agents[idx]:
            while (
                # self.find("arrange_order_options",scope=((1785, 0), (1920, 128))) is None
                self.find("confirm_blue") is None
            ):
                if error_count > 3:
                    raise Exception("未成功进入干员选择界面")
                self.ctap((self.recog.w * 0.82, self.recog.h * 0.18 * (idx + 1)))
                error_count += 1
            self.choose_agent([agents[idx]], "train", fast_mode)
            self.tap_confirm("train")

    def choose_train(self, agents: list[str], fast_mode=True):
        current_room = self.op_data.get_current_room("train", True)
        self.choose_train_agent(current_room, agents, 0, 0, fast_mode)
        # 训练室第二个人的干员识别会出错（工作中的干员无法识别 + 正在训练的干员无法换下）
        # self.choose_train_agent(current_room, agents, 1, 0, fast_mode)

    def choose_agent(
        self, agents: list[str], room: str, fast_mode=True, train_index=0
    ) -> None:
        """
        :param order: ArrangeOrder, 选择干员时右上角的排序功能
        """
        first_name = ""
        max_swipe = 50
        position = [
            (0.35, 0.35),
            (0.35, 0.75),
            (0.45, 0.35),
            (0.45, 0.75),
            (0.55, 0.35),
        ]
        # 空位置跳过安排
        if "" in agents:
            fast_mode = False
            agents = [item for item in agents if item != ""]
        current_list = set()
        for idx, n in enumerate(agents):
            if n not in current_list:
                current_list.add(n)
            elif n != "Free":
                agents[idx] = "Free"
            if room.startswith("dorm") and agents[idx] in self.op_data.operators.keys():
                __agent = self.op_data.operators[agents[idx]]
                if __agent.mood == __agent.upper_limit and not __agent.room.startswith(
                    "dorm"
                ):
                    agents[idx] = "Free"
                    __agent.depletion_rate = 0
                    logger.info("检测满心情释放休息位")
                elif agents[idx] == "Free" and self.task.type != TaskTypes.RE_ORDER:
                    if self.op_data.config.free_room:
                        current_free = self.op_data.get_current_operator(room, idx)
                        if (
                            current_free
                            and current_free.mood < current_free.upper_limit
                        ):
                            agents[idx] = current_free.name
        agent = copy.deepcopy(agents)
        exists = []
        if fast_mode:
            current_room = self.op_data.get_current_room(room, True)
            # 如果空位置进房间会被向前挤
            current_room = sorted(current_room, key=lambda x: x == "")
            differences = []
            for i in range(len(current_room)):
                if current_room[i] not in agents:
                    differences.append(i)
                else:
                    exists.append(current_room[i])
            if room == "train":
                differences = [x for x in differences if x == train_index]
            for pos in differences:
                if current_room[pos] != "":
                    self.tap(
                        (
                            self.recog.w * position[pos][0],
                            self.recog.h * position[pos][1],
                        ),
                        interval=0,
                    )
            agent = [x for x in agents if x not in exists]
        logger.info(f"安排干员 ：{agent}")
        # 若不是空房间，则清空工作中的干员
        is_dorm = room.startswith("dorm")
        first_time = True
        # 在 agent 中 'Free' 表示任意空闲干员
        free_num = agent.count("Free")
        for i in range(agent.count("Free")):
            agent.remove("Free")
        index_change = False
        pre_order = [2, False]
        right_swipe = 0
        retry_count = 0
        selected = []
        logger.debug(f"上次进入房间为：{self.last_room},本次房间为：{room}")
        self.profession_filter()
        if self.detect_arrange_order()[0] == "信赖值":
            self.switch_arrange_order("工作状态")
        siege = False  # 推进之王
        last_special_filter = "ALL"
        while len(agent) > 0:
            if retry_count > 1:
                raise Exception("到达最大尝试次数 1次")
            if right_swipe > max_swipe:
                # 到底了则返回再来一次
                self.choose_error.add(agent[0])
                raise Exception("重试一次")
            if first_time:
                # 清空
                if is_dorm:
                    self.switch_arrange_order(3, "true")
                    pre_order = [3, "true"]
                if not fast_mode:
                    self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
                changed, ret = self.scan_agent(
                    agent, full_scan=last_special_filter == "ALL"
                )
                if changed:
                    selected.extend(changed)
                    if len(agent) == 0:
                        break
                    index_change = True

            # 如果选中了人，则可能需要重新排序
            if index_change or first_time:
                # 第一次则调整
                is_custom, arrange_type = self.get_order(agent[0])
                if is_dorm and not (
                    agent[0] in self.op_data.operators.keys()
                    and self.op_data.operators[agent[0]].room.startswith("dormitory")
                ):
                    arrange_type = (3, "true")
                # 如果重新排序则滑到最左边
                if pre_order[0] != arrange_type[0] or pre_order[1] != arrange_type[1]:
                    self.switch_arrange_order(arrange_type[0], arrange_type[1])
                    # 滑倒最左边
                    self.sleep(interval=0.5)
                    if not siege:
                        right_swipe = self.swipe_left(right_swipe, last_special_filter)
                    pre_order = arrange_type
            first_time = False
            if (
                not siege
                and not is_dorm
                and agent
                and all(element in self.op_data.profession_filter for element in agent)
            ):
                siege = True
                if agent[0] in self.op_data.profession_filter:
                    profession = agent_profession[agent[0]]
                    self.profession_filter(profession)
                    if last_special_filter != profession:
                        right_swipe = 0
                    last_special_filter = profession
            elif agent and agent[0] in agent_list:
                if is_dorm and agent[0] != "阿米娅":
                    # 在宿舍并且不是阿米娅则打开职介筛选
                    profession = agent_profession[agent[0]]
                    self.profession_filter(profession)
                    if last_special_filter != profession:
                        right_swipe = 0
                    last_special_filter = profession
                    if index_change:
                        self.switch_arrange_order(3, "true")
                elif is_dorm and agent[0] == "阿米娅" and last_special_filter != "ALL":
                    # 如果是阿米娅且filter 不是all
                    self.profession_filter("ALL")
                    last_special_filter = "ALL"
                if (
                    agent[0] in self.op_data.operators
                    and self.op_data.operators[agent[0]].is_resting()
                    and fast_mode
                    and is_dorm
                    and agent[0] != "阿米娅"
                    and agent[0] not in self.choose_error
                ):
                    # 如果在休息，则直接翻最后:
                    swipe_map = [20, 3, 5, 3, 3, 3, 3, 3, 3]
                    skip_swipe_count = swipe_map[
                        self.profession_labels.index(last_special_filter)
                    ]
                    for i in range(skip_swipe_count):
                        self.swipe_noinertia(
                            (0.8 * self.recog.w, 0.5 * self.recog.h),
                            (-1900, 0),
                            interval=0,
                        )
                    right_swipe = skip_swipe_count
                    self.sleep(1)
            changed, ret = self.scan_agent(
                agent, full_scan=last_special_filter == "ALL"
            )
            if changed:
                selected.extend(changed)
                # 如果找到了
                index_change = True
                siege = False
            else:
                # 如果没找到 而且右移次数大于5
                if ret[0][0] == first_name and right_swipe >= 3:
                    max_swipe = right_swipe
                else:
                    first_name = ret[0][0]
                index_change = False
                st = ret[-2][1][0]  # 起点
                ed = ret[0][1][0]  # 终点
                self.swipe_noinertia(st, (ed[0] - st[0], 0))
                right_swipe += 1
                if right_swipe >= 3:
                    self.sleep(0.3)
            if len(agent) == 0:
                if siege:
                    if last_special_filter != "ALL":
                        right_swipe = 0
                break

        # 安排空闲干员
        if free_num:
            if free_num == len(agents):
                self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            if not first_time:
                # 滑动到最左边
                right_swipe = self.swipe_left(right_swipe, last_special_filter)
            if last_special_filter != "ALL":
                self.profession_filter("ALL")
                last_special_filter = "ALL"
            self.switch_arrange_order(3, "true")
            # 只选择在列表里面的
            # 替换组小于20才休息，防止进入就满心情进行网络连接
            free_list = [
                v.name
                for k, v in self.op_data.operators.items()
                if v.name not in agents
                and v.operator_type != "high"
                and v.current_room == ""
            ]
            free_list.extend(
                [
                    _name
                    for _name in agent_list
                    if _name not in self.op_data.operators.keys()
                    and _name not in agents
                ]
            )
            train_support = self.op_data.get_train_support()
            # 获取所有要移除的字符串集合（排除 'Crueent'）
            remove_set = set()
            for key, value_list in self.task.plan.items():
                remove_set.update(value_list)  # 加入所有列表中的元素
            remove_set.discard("Current")
            remove_set.discard("Free")
            logger.debug(f"去除被安排的人员{remove_set}")
            free_list = list(
                set(free_list) - set(self.op_data.config.free_blacklist) - remove_set
            )
            if train_support in free_list:
                free_list.remove(train_support)
            while free_num:
                selected_name, ret = self.scan_agent(
                    free_list,
                    max_agent_count=free_num,
                    full_scan=last_special_filter == "ALL",
                )
                selected.extend(selected_name)
                free_num -= len(selected_name)
                while len(selected_name) > 0:
                    agents[agents.index("Free")] = selected_name[0]
                    selected_name.remove(selected_name[0])
                if free_num == 0:
                    break
                else:
                    st = ret[-2][1][0]  # 起点
                    ed = ret[0][1][0]  # 终点
                    self.swipe_noinertia(st, (ed[0] - st[0], 0))
                    right_swipe += 1
        # 排序
        if len(agents) != 1:
            # 左移
            right_swipe = self.swipe_left(right_swipe, last_special_filter)
            self.switch_arrange_order("技能")
            not_match = False
            exists.extend(selected)
            logger.info(exists)
            for idx, item in enumerate(agents):
                if agents[idx] != exists[idx] or not_match:
                    not_match = True
                    p_idx = exists.index(agents[idx])
                    self.tap(
                        (
                            self.recog.w * position[p_idx][0],
                            self.recog.h * position[p_idx][1],
                        ),
                        interval=0,
                    )
                    self.tap(
                        (
                            self.recog.w * position[p_idx][0],
                            self.recog.h * position[p_idx][1],
                        ),
                        interval=0,
                    )
        logger.debug("验证干员选择..")
        self.swipe_left(right_swipe, last_special_filter)
        self.switch_arrange_order(2)
        if not self.verify_agent(agents):
            logger.debug(agents)
            raise Exception("检测到干员选择错误，重新选择")
        self.last_room = room

    def reset_room_time(self, room):
        for _operator in self.op_data.operators.keys():
            if self.op_data.operators[_operator].room == room:
                self.op_data.operators[_operator].time_stamp = None

    def turn_on_room_detail(self, room):
        for enter_times in range(3):
            for retry_times in range(10):
                if pos := self.find("room_detail"):
                    if all(self.get_color((1233, 1)) > [252] * 3):
                        return
                    logger.info("等待动画")
                    self.sleep(interval=0.5)
                elif pos := self.find("arrange_check_in"):
                    self.tap(pos, interval=0.7)
                elif pos := self.find("arrange_check_in_small"):
                    self.tap(pos, interval=0.7)
                else:
                    self.sleep()
            for back_time in range(3):
                if pos := self.find("control_central"):
                    break
                self.back()
            if not pos:
                self.back_to_infrastructure()
            self.enter_room(room)
        self.reset_room_time(room)
        raise Exception("未成功进入房间")

    def get_agent_from_room(self, room, read_time_index=None):
        if read_time_index is None:
            read_time_index = []
        if room == "meeting" and not self.leifeng_mode:
            self.sleep(0.5)
            self.recog.update()
            clue_res = self.read_screen(
                self.recog.img, limit=10, cord=((439, 987), (577, 1033))
            )
            if clue_res != 11:
                self.clue_count = clue_res
                logger.info(f"当前拥有线索数量为{self.clue_count}")
        self.turn_on_room_detail(room)
        # 如果是宿舍则全读取
        if room.startswith("dorm"):
            read_time_index = [
                i
                for i, obj in enumerate(self.op_data.plan[room])
                if obj.agent == "Free" or obj.agent == "菲亚梅塔"
            ]
        while self.detect_product_complete():
            logger.info("检测到产物收取提示")
            self.sleep(1)
        length = len(self.op_data.plan[room])
        if length > 3:
            while self.get_color((1800, 138))[0] > 51:
                self.swipe(
                    (self.recog.w * 0.8, self.recog.h * 0.5),
                    (0, self.recog.h * 0.45),
                    duration=500,
                    interval=1,
                )
        name_x = (1288, 1869)
        name_y = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        name_p = [tuple(zip(name_x, y)) for y in name_y]
        time_x = (1650, 1780)
        time_y = [(270, 305), (480, 515), (690, 725), (668, 703), (877, 912)]
        time_p = [tuple(zip(time_x, y)) for y in time_y]
        mood_x = (1470, 1780)
        mood_y = (219, 428, 637, 615, 823)
        mood_y = [(y, y + 1) for y in mood_y]
        mood_p = [tuple(zip(mood_x, y)) for y in mood_y]
        result = []
        swiped = False
        for i in range(0, length):
            if i >= 3 and not swiped:
                while self.get_color((1800, 930))[0] > 51:
                    self.swipe(
                        (self.recog.w * 0.8, self.recog.h * 0.5),
                        (0, -self.recog.h * 0.45),
                        duration=500,
                        interval=1,
                    )
                swiped = True
            data = {}
            if self.find("infra_no_operator", scope=name_p[i]):
                _name = ""
            else:
                _name = self.read_screen(
                    cropimg(self.recog.gray, name_p[i]), type="name"
                )
            _mood = 24
            # 如果房间不为空
            if _name != "":
                if _name not in self.op_data.operators.keys() and _name in agent_list:
                    self.op_data.add(Operator(_name, ""))
                update_time = False
                agent = self.op_data.operators[_name]
                if self.op_data.operators[_name].need_to_refresh(r=room) or (
                    self.tasks and self.tasks[0].type == TaskTypes.SHIFT_ON
                ):
                    _mood = self.read_accurate_mood(cropimg(self.recog.gray, mood_p[i]))
                    update_time = True
                else:
                    _mood = self.op_data.operators[_name].current_mood()
                high_no_time = self.op_data.update_detail(
                    _name, _mood, room, i, update_time
                )
                data["depletion_rate"] = agent.depletion_rate
                if high_no_time is not None and high_no_time not in read_time_index:
                    logger.debug(
                        f"检测到高效组休息时间数据不存在:{room},{high_no_time}"
                    )
                    read_time_index.append(high_no_time)
            else:
                _mood = -1
            data["agent"] = _name
            data["mood"] = _mood
            if i in read_time_index and _name != "":
                if _mood == 24 or room in ["central", "meeting", "factory"]:
                    data["time"] = datetime.now()
                else:
                    upperLimit = 43200
                    logger.debug(f"开始记录时间:{room},{i}")
                    data["time"] = self.double_read_time(
                        time_p[i], upperLimit=upperLimit
                    )
                self.op_data.refresh_dorm_time(room, i, data)
                logger.debug(f"停止记录时间:{str(data)}")
            result.append(data)
        for _operator in self.op_data.operators.keys():
            if self.op_data.operators[
                _operator
            ].current_room == room and _operator not in [
                res["agent"] for res in result
            ]:
                self.op_data.operators[_operator].current_room = ""
                self.op_data.operators[_operator].current_index = -1
                if (
                    self.op_data.config.free_room
                    and self.task is not None
                    and self.task.type != TaskTypes.SHIFT_OFF
                ):
                    release_task = self.find_next_task(
                        task_type=TaskTypes.RELEASE_DORM, meta_data=_operator
                    )
                    if release_task and self.task != release_task:
                        self.tasks.remove(release_task)
                logger.info(f"重设 {_operator} 至空闲")
        return result

    def refresh_current_room(self, room, current_index=None):
        _current_room = self.op_data.get_current_room(room, current_index=current_index)
        if _current_room is None:
            self.get_agent_from_room(room)
            _current_room = self.op_data.get_current_room(room, True)
        return _current_room

    def get_order_remaining_time(self):
        error_count = 0
        while (
            self.find("factory_accelerate") is None
            and self.find("bill_accelerate") is None
        ):
            if error_count > 5:
                raise Exception("未成功进入无人机界面")
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.5)
            error_count += 1
        # 订单剩余时间
        execute_time = self.double_read_time(
            (
                (int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404)),
                (int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
            ),
            use_digit_reader=True,
        )
        return round((execute_time - datetime.now()).total_seconds(), 1)

    def current_room_changed(self, instance):
        if not self.op_data.first_init:
            logger.info(f"{instance.name} 房间变动")
            ref_rooms = (
                instance.refresh_order_room[1]
                if instance.refresh_order_room[1]
                else list(self.op_data.run_order_rooms.keys())
            )
            for ref_room in ref_rooms:
                self.refresh_run_order_time(ref_room)
            if (
                instance.name in self.op_data.operators
                and self.op_data.operators[instance.name].refresh_drained
            ):
                self.refresh_drained_time()

    def refresh_drained_time(self):
        logger.debug("刷新用尽倒计时")
        solved = []
        for agent in self.op_data.exhaust_agent:
            if agent in solved:
                continue
            logger.debug(f"开始检查{agent}")
            shift_off = self.find_next_task(
                datetime.now() + timedelta(hours=24),
                task_type=TaskTypes.EXHAUST_OFF,
                meta_data=agent,
                compare_type="<",
            )
            if shift_off:
                logger.info(f"移除 {shift_off.meta_data} 用尽下班任务以刷新时间")
                exhausts = shift_off.meta_data.split(",")
                solved.extend(exhausts)
                self.tasks.remove(shift_off)
                for o in exhausts:
                    self.op_data.operators[o].time_stamp = None
                self.task
            else:
                self.op_data.operators[agent].time_stamp = None
        if solved:
            self.tasks.append(
                (
                    SchedulerTask(
                        time=datetime.now(),
                        task_plan={},
                        task_type=TaskTypes.NOT_SPECIFIC,
                    )
                )
            )

    def refresh_run_order_time(self, room):
        logger.debug("检测到插拔房间人员变动！")
        limit = 15
        if run_order_task := self.find_next_task(
            datetime.now() + timedelta(minutes=limit),
            task_type=TaskTypes.RUN_ORDER,
            meta_data=room,
            compare_type=">",
        ):
            logger.info(f"移除超过{limit}分钟的跑单任务以刷新时间")
            self.tasks.remove(run_order_task)
        run_order_task = self.find_next_task(
            datetime.now() + timedelta(minutes=limit),
            task_type=TaskTypes.RUN_ORDER,
            meta_data=room,
            compare_type="<",
        )
        if run_order_task and run_order_task.time > datetime.now():
            task_time = datetime.now()
            if len(self.tasks) > 0 and self.tasks[0].type != TaskTypes.FIAMMETTA:
                task_time = self.tasks[0].time - timedelta(seconds=1)
            logger.info(f"移除{limit}分钟以内的跑单任务以强X刷新时间")
            self.tasks.remove(run_order_task)
            logger.info("新增强X刷新跑单时间任务")
            self.tasks.append(
                (
                    SchedulerTask(
                        time=task_time,
                        task_plan={},
                        task_type=TaskTypes.REFRESH_TIME,
                        meta_data=room,
                    )
                )
            )

    def agent_arrange_room(
        self, new_plan, room, plan, skip_enter=False, get_time=False
    ):
        finished = False
        choose_error = 0
        checked = False
        while not finished:
            try:
                error_count = 0
                if not skip_enter:
                    self.enter_room(room)
                self.turn_on_room_detail(room)
                error_count = 0
                if not checked:
                    if any(
                        any(char in item for item in plan[room])
                        for char in ["但书", "龙舌兰", "佩佩"]
                    ) and not room.startswith("dormitory"):
                        new_plan[room] = self.refresh_current_room(room)
                    if "菲亚梅塔" in plan[room] and len(plan[room]) == 2:
                        new_plan[room] = self.refresh_current_room(room)
                        working_room = self.op_data.operators[plan[room][0]].room
                        new_plan[working_room] = self.op_data.get_current_room(
                            working_room, True
                        )
                    if "Current" in plan[room] or "" in plan[room]:
                        self.refresh_current_room(
                            room,
                            [
                                index
                                for index, value in enumerate(plan[room])
                                if value == "Current"
                            ],
                        )
                        _current_room = self.op_data.get_current_room(room, True)
                        for current_idx, _name in enumerate(plan[room]):
                            if _name == "Current":
                                plan[room][current_idx] = (
                                    _current_room[current_idx]
                                    if _current_room[current_idx] != ""
                                    else "Free"
                                )
                            if _name == "":
                                plan[room][current_idx] = "Free"
                    if (
                        room in self.op_data.run_order_rooms
                        and len(new_plan) == 0
                        and self.task.type != TaskTypes.RUN_ORDER
                    ):
                        if plan[room] != self.op_data.get_current_room(room):
                            self.refresh_run_order_time(room)
                checked = True
                current_room = self.op_data.get_current_room(room, True)
                same = len(plan[room]) == len(current_room)
                if same:
                    for item1, item2 in zip(plan[room], current_room):
                        if item1 != item2:
                            same = False
                if not same:
                    # choose_error <= 0 选人如果失败则马上重新选过
                    if (
                        len(new_plan) == 1
                        and config.conf.run_order_buffer_time > 0
                        and choose_error <= 0
                    ):
                        remaining_time = self.get_order_remaining_time()
                        if 0 < remaining_time < (config.conf.run_order_delay + 10) * 60:
                            if config.conf.run_order_buffer_time > 0:
                                self.task.time = (
                                    datetime.now()
                                    + timedelta(seconds=remaining_time)
                                    - timedelta(minutes=config.conf.run_order_delay)
                                )
                                logger.info(f"订单倒计时 {remaining_time}秒")
                                self.back()
                                self.turn_on_room_detail(room)
                        else:
                            logger.info("检测到漏单")
                            send_message("检测到漏单！", level="WARNING")
                            self.reset_room_time(room)
                            raise Exception("检测到漏单！")
                    if room == "train":
                        self.choose_train(plan[room], choose_error <= 0)
                    else:
                        while self.find("confirm_blue") is None:
                            if error_count > 3:
                                raise Exception("未成功进入干员选择界面")
                            self.ctap((self.recog.w * 0.82, self.recog.h * 0.2))
                            error_count += 1
                        self.choose_agent(plan[room], room, choose_error <= 0)
                        self.tap_confirm(room, new_plan)
                    read_time_index = []
                    if get_time:
                        read_time_index = self.op_data.get_refresh_index(
                            room, plan[room]
                        )
                    if len(new_plan) > 1:
                        self.op_data.operators["菲亚梅塔"].time_stamp = None
                        self.op_data.operators[plan[room][0]].time_stamp = None
                    current = self.get_agent_from_room(room, read_time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]["agent"] != name and name != "Free":
                            if not (room == "train" and idx == 1):
                                logger.error(
                                    f"检测到的干员{current[idx]['agent']},需要安排的干员{name}"
                                )
                                raise Exception("检测到安排干员未成功")
                else:
                    logger.info(f"任务与当前房间相同，跳过安排{room}人员")
                finished = True
                skip_enter = False
                # 如果完成则移除该任务
                del plan[room]
                # back to 基地主界面
                if self.scene() in self.waiting_scene:
                    if not self.waiting_solver():
                        return
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(e)
                choose_error += 1
                self.recog.update()
                if "检测到漏单！" in str(e):
                    return {}
                if choose_error > 3:
                    raise e
                if "检测到安排干员未成功" in str(e):
                    skip_enter = True
                    continue
                back_count = 0
                while self.scene() != Scene.INFRA_MAIN:
                    self.back(interval=0.5)
                    back_count += 1
                    if back_count > 3:
                        raise e
                continue
        if len(new_plan) != 1:
            self.back(0.5)
        else:
            if config.conf.run_order_buffer_time <= 0:
                self.back(0.5)
        return new_plan

    def accept_order(self):
        wait = 0
        # 等待订单完成
        while self.find("order_ready", scope=((450, 675), (600, 750))) is None:
            if wait > 6:
                break
            self.recog.update()
            self.sleep(0.5)
            wait += 1
        not_take = True
        while self.find("order_ready", scope=((450, 675), (600, 750))) is not None:
            if not_take:
                self.recog.save_screencap("run_order")
                self.order_reader.save(self.recog.img)
                not_take = False
            self.tap((self.recog.w * 0.25, self.recog.h * 0.25), interval=0.5)

    def agent_arrange(self, plan: tp.BasePlan, get_time=False):
        logger.info("基建：排班")
        rooms = list(plan.keys())
        new_plan = {}
        # 优先替换工作站再替换宿舍
        rooms.sort(
            key=lambda x: (
                x.startswith("dormitory_"),
                int(x.split("_")[1]) if x.startswith("dormitory_") else 0,
            )
        )
        for room in rooms:
            new_plan = self.agent_arrange_room(new_plan, room, plan, get_time=get_time)
        if len(new_plan) == 1:
            if config.conf.run_order_buffer_time <= 0:
                logger.info("开始插拔")
                self.drone(room, not_customize=True)
            else:
                # 葛朗台跑单模式
                error_count = 0
                while (
                    self.find("factory_accelerate") is None
                    and self.find("bill_accelerate") is None
                ):
                    if error_count > 5:
                        raise Exception("未成功进入无人机界面")
                    self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.5)
                    error_count += 1
                # 订单剩余时间
                execute_time = self.double_read_time(
                    (
                        (
                            int(self.recog.w * 650 / 2496),
                            int(self.recog.h * 660 / 1404),
                        ),
                        (
                            int(self.recog.w * 815 / 2496),
                            int(self.recog.h * 710 / 1404),
                        ),
                    ),
                    use_digit_reader=True,
                )
                wait_time = round((execute_time - datetime.now()).total_seconds(), 1)
                logger.debug(f"停止{wait_time}秒等待订单完成")
                if 0 < wait_time < config.conf.run_order_delay * 60:
                    logger.info(f"停止{wait_time}秒等待订单完成")
                    self.sleep(wait_time)
                    # 等待服务器交互
                    if self.scene() in self.waiting_scene:
                        if not self.waiting_solver():
                            return
                else:
                    logger.info("检测到漏单")
                    send_message("检测到漏单！", level="WARNING")
                self.accept_order()
                if self.drone_room is None or (
                    self.drone_room == room and room in self.op_data.run_order_rooms
                ):
                    drone_count = self.digit_reader.get_drone(self.recog.gray)
                    logger.info(f"当前无人机数量为：{drone_count}")
                    # 200 为识别错误
                    if (
                        drone_count >= config.conf.drone_count_limit
                        and drone_count != 201
                    ):
                        self.drone(
                            room, not_return=True, not_customize=True, skip_enter=True
                        )
                if config.conf.run_order_buffer_time > 0:
                    while self.find("bill_accelerate") is not None:
                        self.back(interval=0.5)
                else:
                    self.back(interval=0.5)
                    self.back(interval=0.5)
            # 防止由于意外导致的死循环
            run_order_room = next(iter(new_plan))
            if any(
                any(char in item for item in new_plan[run_order_room])
                for char in ["但书", "龙舌兰", "佩佩"]
            ):
                new_plan[run_order_room] = [
                    data.agent for data in self.op_data.plan[room]
                ]
            if config.conf.run_order_buffer_time > 0:
                self.agent_arrange_room({}, run_order_room, new_plan, skip_enter=True)
            else:
                self.tasks.append(
                    SchedulerTask(
                        time=self.tasks[0].time,
                        task_plan=new_plan,
                        task_type=TaskTypes.RUN_ORDER,
                    )
                )
                self.skip()
        elif len(new_plan) > 1:
            self.tasks.append(
                SchedulerTask(
                    time=self.tasks[0].time,
                    task_plan=new_plan,
                    task_type=TaskTypes.FIAMMETTA,
                )
            )
            # 急速换班
            self.skip()
        logger.info("返回基建主界面")

    def skip(self, task_names="All"):
        if task_names == "All":
            task_names = ["planned", "collect_notification", "todo_task"]
        if "planned" in task_names:
            self.planned = True
        if "todo_task" in task_names:
            self.todo_task = True
        if "collect_notification" in task_names:
            self.collect_notification = True

    def no_pending_task(self, minute=0):
        return self.find_next_task(datetime.now() + timedelta(minutes=minute)) is None

    def reload(self):
        error = False
        for room in self.reload_room:
            try:
                logger.info(f"开始搓玉补货:{room}")
                self.enter_room(room)
                self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.25)
                self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.25)
                self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.25)
                # 补货
                self.tap((self.recog.w * 0.75, self.recog.h * 0.3), interval=0.5)
                self.tap((self.recog.w * 0.75, self.recog.h * 0.9), interval=0.5)
                if self.scene() in self.waiting_scene:
                    if not self.waiting_solver():
                        return
                self.scene_graph_navigation(Scene.INFRA_MAIN)
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(e)
                error = True
                self.recog.update()
                back_count = 0
                while self.scene() != Scene.INFRA_MAIN:
                    self.back()
                    back_count += 1
                    if back_count > 3:
                        raise e
        if not error:
            self.reload_time = datetime.now()

    @CFUNCTYPE(None, c_int, c_char_p, c_void_p)
    def log_maa(msg, details, arg):
        m = Message(msg)
        d = json.loads(details.decode("utf-8"))
        logger.debug(d)
        logger.debug(m)
        logger.debug(arg)
        if "what" in d and d["what"] == "StageDrops":
            global stage_drop
            stage_drop["details"].append(d["details"]["drops"])
            stage_drop["summary"] = d["details"]["stats"]

        elif "what" in d and d["what"] == "RecruitTagsSelected":
            global recruit_tags_selected
            recruit_tags_selected["tags"].append(d["details"]["tags"])

        elif "what" in d and d["what"] == "RecruitResult":
            global recruit_results
            temp_dict = {
                "tags": d["details"]["tags"],
                "level": d["details"]["level"],
                "result": d["details"]["result"],
            }
            recruit_results["results"].append(temp_dict)

        elif "what" in d and d["what"] == "RecruitSpecialTag":
            global recruit_special_tags
            recruit_special_tags["tags"].append(d["details"]["tags"])
        # elif d.get("what") == "DepotInfo" and d["details"].get("done") is True:
        #     logger.info(f"开始扫描仓库（MAA）")
        #     process_itemlist(d)

    def initialize_maa(self):
        config.stop_maa.clear()
        conf = config.conf
        path = pathlib.Path(conf.maa_path)
        asst_path = os.path.dirname(path / "Python" / "asst")
        if asst_path not in sys.path:
            sys.path.append(asst_path)
        global Message

        try:
            from asst.asst import Asst
            from asst.utils import InstanceOptionType, Message

            logger.info("Maa Python模块导入成功")
        except Exception as e:
            logger.exception(f"Maa Python模块导入失败：{str(e)}")
            raise Exception("Maa Python模块导入失败")

        try:
            logger.debug("开始更新Maa活动关卡导航……")
            ota_tasks_url = (
                "https://ota.maa.plus/MaaAssistantArknights/api/resource/tasks.json"
            )
            ota_tasks_path = path / "cache" / "resource" / "tasks.json"
            ota_tasks_path.parent.mkdir(parents=True, exist_ok=True)
            headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0'}
            request = urllib.request.Request(url=ota_tasks_url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as u:
                res = u.read().decode("utf-8")
            with open(ota_tasks_path, "w", encoding="utf-8") as f:
                f.write(res)
            logger.info("Maa活动关卡导航更新成功")
        except Exception as e:
            logger.error(f"Maa活动关卡导航更新失败：{str(e)}")

        Asst.load(path=path, incremental_path=path / "cache")

        self.MAA = Asst(callback=self.log_maa)
        self.stages = []
        self.MAA.set_instance_option(
            InstanceOptionType.touch_type, conf.maa_touch_option
        )
        if self.MAA.connect(
            conf.maa_adb_path, self.device.client.device_id, conf.maa_conn_preset
        ):
            logger.info("MAA 连接成功")
        else:
            logger.info("MAA 连接失败")
            raise Exception("MAA 连接失败")

    def append_maa_task(self, type):
        if type in ["StartUp", "Visit"]:
            self.MAA.append_task(type)
        elif type == "Fight":
            conf = config.conf
            server_weekday = get_server_weekday()
            _plan = conf.maa_weekly_plan[server_weekday]
            logger.info(f"现在服务器是{_plan.weekday}")
            use_medicine = False
            if conf.maa_expiring_medicine:
                if conf.exipring_medicine_on_weekend:
                    use_medicine = server_weekday >= 5
                else:
                    use_medicine = True
            for stage in _plan.stage:
                logger.info(f"添加关卡:{stage}")
                self.MAA.append_task(
                    "Fight",
                    {
                        # 空值表示上一次
                        # 'stage': '',
                        "stage": stage,
                        "medicine": _plan.medicine,
                        "stone": 999 if conf.maa_eat_stone else 0,
                        "times": 999,
                        "report_to_penguin": True,
                        "client_type": "",
                        "penguin_id": "",
                        "DrGrandet": False,
                        "server": "CN",
                        "expiring_medicine": 999 if use_medicine else 0,
                    },
                )
                self.stages.append(stage)
        elif type == "Mall":
            conf = config.conf
            self.MAA.append_task(
                "Mall",
                {
                    "shopping": True,
                    "buy_first": conf.maa_mall_buy.split(","),
                    "blacklist": conf.maa_mall_blacklist.split(","),
                    "credit_fight": conf.maa_credit_fight
                    and "" not in self.stages
                    and self.credit_fight is None,
                    "select_formation": conf.credit_fight.squad,
                    "force_shopping_if_credit_full": conf.maa_mall_ignore_blacklist_when_full,
                },
            )
        elif type == "Award":
            self.MAA.append_task(
                "Award",
                {
                    "award": True,
                    "mail": config.conf.maa_mail,
                    "recruit": config.conf.maa_recruit,
                    "orundum": config.conf.maa_orundum,
                    "mining": config.conf.maa_mining,
                    "specialaccess": config.conf.maa_specialaccess,
                },
            )

    def maa_stop(self, stop=True):
        if stop:
            self.MAA.stop()
        logger.debug(stage_drop)
        # 有掉落东西再发
        if stage_drop["details"] and not self.drop_send:
            send_message(
                maa_template.render(stage_drop=stage_drop),
                "Maa停止",
            )
            self.drop_send = True

    def maa_plan_solver(self, tasks="All", one_time=False):
        """清日常"""
        try:
            self.drop_send = False
            conf = config.conf
            if (
                not one_time
                and self.last_execution["maa"] is not None
                and (
                    delta := (
                        timedelta(hours=conf.maa_gap)
                        + self.last_execution["maa"]
                        - datetime.now()
                    )
                )
                > timedelta()
            ):
                logger.info(f"{format_time(delta.total_seconds())}后开始做日常任务")
            else:
                send_message("启动MAA")
                self.back_to_index()
                # 任务及参数请参考 docs/集成文档.md
                self.initialize_maa()
                if tasks == "All":
                    tasks = ["StartUp", "Fight", "Mall", "Award"]
                for maa_task in tasks:
                    self.append_maa_task(maa_task)
                self.MAA.start()
                stop_time = None
                if one_time:
                    stop_time = datetime.now() + timedelta(minutes=5)
                else:
                    global stage_drop
                    stage_drop = {"details": [], "summary": {}}

                logger.info("MAA 启动")
                hard_stop = False
                while self.MAA.running():
                    # 单次任务默认5分钟
                    if one_time and stop_time < datetime.now():
                        self.maa_stop()
                        hard_stop = True
                    # 5分钟之前就停止
                    elif (
                        not one_time
                        and (self.tasks[0].time - datetime.now()).total_seconds() < 300
                    ):
                        self.maa_stop()
                        hard_stop = True
                    elif config.stop_maa.is_set():
                        self.maa_stop()
                        hard_stop = True
                    else:
                        self.sleep(5)
                if hard_stop:
                    hard_stop_msg = "Maa任务未完成，等待3分钟关闭游戏"
                    logger.info(hard_stop_msg)
                    send_message(hard_stop_msg)
                    self.sleep(180)
                    self.device.exit()
                    if self.device.check_current_focus():
                        self.recog.update()
                elif not one_time:
                    logger.info("记录MAA 本次执行时间")
                    self.last_execution["maa"] = datetime.now()
                    logger.info(self.last_execution["maa"])
                    if "Mall" in tasks and self.credit_fight is None:
                        self.credit_fight = get_server_weekday()
                        logger.info("记录首次信用作战")
                        self.maa_stop(False)
                else:
                    send_message("Maa单次任务停止")
                    if (
                        self.find_next_task(datetime.now() + timedelta(minutes=15))
                        is None
                    ):
                        logger.debug(
                            "Maa单次任务结束15分钟内没有其他任务，新增单次任务防止漏单"
                        )
                        self.tasks.insert(0, SchedulerTask(time=datetime.now()))
            conf = config.conf
            now_time = datetime.now().time()
            try:
                min_time = datetime.strptime(conf.maa_rg_sleep_min, "%H:%M").time()
                max_time = datetime.strptime(conf.maa_rg_sleep_max, "%H:%M").time()
                if max_time < min_time:
                    rg_sleep = now_time > min_time or now_time < max_time
                else:
                    rg_sleep = min_time < now_time < max_time
            except ValueError:
                rg_sleep = False
            if (conf.RG or conf.SSS) and not rg_sleep:
                logger.info("准备开始：肉鸽/保全")
                send_message("启动 肉鸽/保全")
                while True:
                    self.MAA = None
                    self.initialize_maa()
                    self.recog.update()
                    self.back_to_index()
                    if conf.RG:
                        self.MAA.append_task(
                            "Roguelike",
                            {
                                "theme": conf.maa_rg_theme,
                                "squad": conf.rogue.squad,
                                "roles": conf.rogue.roles,
                                "core_char": conf.rogue.core_char,
                                "use_support": conf.rogue.use_support,
                                "use_nonfriend_support": conf.rogue.use_nonfriend_support,
                                "mode": conf.rogue.mode,
                                "refresh_trader_with_dice": conf.rogue.refresh_trader_with_dice,
                                "starts_count": 9999999,
                                "investments_count": 9999999,
                                "expected_collapsal_paradigms": conf.rogue.expected_collapsal_paradigms,
                            },
                        )
                    elif conf.SSS:
                        copilot = get_path("@app/sss.json")
                        if (
                            not copilot.is_file()
                            or conf.sss.type not in [1, 2]
                            or conf.sss.ec not in [1, 2, 3]
                        ):
                            raise Exception("保全派驻配置错误")
                        if self.to_sss():
                            raise Exception("保全派驻导航失败")
                        self.MAA.append_task(
                            "SSSCopilot",
                            {"filename": str(copilot), "loop_times": 9999999},
                        )
                    logger.info("启动")
                    self.MAA.start()
                    maa_crash = True
                    while self.MAA.running():
                        csleep(5)
                        if (
                            self.tasks[0].time - datetime.now() < timedelta(seconds=30)
                            or config.stop_maa.is_set()
                        ):
                            maa_crash = False
                            self.maa_stop()
                            break
                    if maa_crash:
                        self.device.exit()
                        self.check_current_focus()
                    else:
                        break

            elif not rg_sleep:
                if conf.RA:
                    self.back_to_index()
                    ra_solver = ReclamationAlgorithm(self.device, self.recog)
                    ra_solver.run(self.tasks[0].time - datetime.now())
                elif conf.SF:
                    self.back_to_index()
                    sf_solver = SecretFront(self.device, self.recog)
                    sf_solver.run(self.tasks[0].time - datetime.now())

            remaining_time = (self.tasks[0].time - datetime.now()).total_seconds()
            subject = f"休息 {format_time(remaining_time)}，到{self.tasks[0].time.strftime('%H:%M:%S')}开始工作"
            context = f"下一次任务:{self.tasks[0].plan if len(self.tasks[0].plan) != 0 else '空任务' if self.tasks[0].type == '' else self.tasks[0].type}"
            logger.info(context)
            logger.info(subject)
            self.task_count += 1
            logger.info(f"第{self.task_count}次任务结束")
            if remaining_time > 0:
                if remaining_time > 300:
                    if config.conf.close_simulator_when_idle:
                        from arknights_mower.utils.simulator import restart_simulator

                        restart_simulator(start=False)
                    elif config.conf.exit_game_when_idle:
                        self.device.exit()
                self.sleep(remaining_time)
                self.check_current_focus()
            self.MAA = None
        except MowerExit:
            if self.MAA is not None:
                self.maa_stop()
                logger.info("停止maa")
            raise
        except Exception as e:
            logger.exception(e)
            self.MAA = None
            self.device.exit()
            send_message(str(e), "Maa调用出错！", level="ERROR")
            remaining_time = (self.tasks[0].time - datetime.now()).total_seconds()
            if remaining_time > 0:
                logger.info(
                    f"休息 {format_time(remaining_time)}，到{self.tasks[0].time.strftime('%H:%M:%S')}开始工作"
                )
                self.sleep(remaining_time)
            self.check_current_focus()

    def skland_plan_solover(self):
        try:
            return SKLand().start()
        except MowerExit:
            raise
        except Exception as e:
            logger.exception(f"森空岛签到失败:{e}")
            send_message(f"森空岛签到失败: {e}", level="ERROR")
        # 仅尝试一次 不再尝试
        return (datetime.now() - timedelta(hours=4)).date()

    def recruit_plan_solver(self):
        if self.last_execution[
            "recruit"
        ] is None or datetime.now() > self.last_execution["recruit"] + timedelta(
            hours=config.conf.recruit_gap
        ):
            RecruitSolver(self.device, self.recog).run()

            self.last_execution["recruit"] = datetime.now()
            logger.info(f"下一次公开招募执行时间在{config.conf.recruit_gap}小时之后")

    def mail_plan_solver(self):
        if config.conf.check_mail_enable:
            MailSolver(self.device, self.recog).run()
        return True

    def report_plan_solver(self):
        if config.conf.report_enable:
            return ReportSolver(self.device, self.recog).run()

    def visit_friend_plan_solver(self):
        if config.conf.visit_friend:
            return CreditSolver(self.device, self.recog).run()

    def sign_in_plan_solver(self):
        if not config.conf.sign_in.enable:
            return
        # hot_update.update()
        try:
            import sign_in

            sign_in_solver = sign_in.SignInSolver(self.device, self.recog)
            return sign_in_solver.run()
        except MowerExit:
            raise
        except Exception as e:
            logger.exception(e)
            return True

    def 仓库扫描(self):
        try:
            cultivateDepotSolver().start()
            DepotSolver(self.device, self.recog).run()
        except Exception as e:
            logger.exception(f"先不运行 出bug了 : {e}")
            return False
        return True
