import copy
import heapq
from datetime import datetime, timedelta
from enum import Enum
from typing import Literal

from arknights_mower.utils import config
from arknights_mower.utils.datetime import the_same_time
from arknights_mower.utils.log import logger


class TaskTypes(Enum):
    RUN_ORDER = ("run_order", "跑单", 1)
    FIAMMETTA = ("菲亚梅塔", "肥鸭", 2)
    SHIFT_OFF = ("shifit_off", "下班", 2)
    SHIFT_ON = ("shifit_on", "上班", 2)
    EXHAUST_OFF = ("exhaust_on", "用尽下班", 2)
    SELF_CORRECTION = ("self_correction", "纠错", 2)
    CLUE_PARTY = ("Impart", "趴体", 2)
    MAA_MALL = ("maa_Mall", "MAA信用购物", 2)
    NOT_SPECIFIC = ("", "空任务", 2)
    RECRUIT = ("recruit", "公招", 2)
    SKLAND = ("skland", "森空岛签到", 2)
    RE_ORDER = ("宿舍排序", "宿舍排序", 2)
    RELEASE_DORM = ("释放宿舍空位", "释放宿舍空位", 2)
    REFRESH_TIME = ("强制刷新任务时间", "强制刷新任务时间", 2)
    SKILL_UPGRADE = ("技能专精", "技能专精", 2)
    DEPOT = ("仓库扫描", "仓库扫描", 2)  # 但是我不会写剩下的

    def __new__(cls, value, display_value, priority):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display_value = display_value
        obj.priority = priority
        return obj


def find_next_task(
    tasks,
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
    if compare_type == "=":
        return next(
            (
                e
                for e in tasks
                if the_same_time(e.time, compare_time)
                and (True if task_type == "" else task_type == e.type)
                and (True if meta_data == "" else meta_data in e.meta_data)
            ),
            None,
        )
    elif compare_type == ">":
        return next(
            (
                e
                for e in tasks
                if (True if compare_time is None else e.time > compare_time)
                and (True if task_type == "" else task_type == e.type)
                and (True if meta_data == "" else meta_data in e.meta_data)
            ),
            None,
        )
    else:
        return next(
            (
                e
                for e in tasks
                if (True if compare_time is None else e.time < compare_time)
                and (True if task_type == "" else task_type == e.type)
                and (True if meta_data == "" else meta_data in e.meta_data)
            ),
            None,
        )


def scheduling(tasks, run_order_delay=5, execution_time=0.75, time_now=None):
    # execution_time per room
    if time_now is None:
        time_now = datetime.now()
    if len(tasks) > 0:
        tasks.sort(key=lambda x: x.time)

        # 任务间隔最小时间（5分钟）
        min_time_interval = timedelta(minutes=run_order_delay)

        # 初始化变量以跟踪上一个优先级0任务和计划执行时间总和
        last_priority_0_task = None
        total_execution_time = 0

        # 遍历任务列表
        for i, task in enumerate(tasks):
            current_time = time_now
            # 判定任务堆积，如果第一个任务已经超时，则认为任务堆积
            if task.type.priority == 1 and current_time > task.time:
                total_execution_time += (current_time - task.time).total_seconds() / 60

            if task.type.priority == 1:
                if last_priority_0_task is not None:
                    time_difference = task.time - last_priority_0_task.time
                    if (
                        config.conf.run_order_grandet_mode.enable
                        and time_difference < min_time_interval
                        and time_now < last_priority_0_task.time
                    ):
                        logger.info("检测到跑单任务过于接近，准备修正跑单时间")
                        return last_priority_0_task
                # 更新上一个优先级0任务和总执行时间
                last_priority_0_task = task
                total_execution_time = 0
            else:
                # 找到下一个优先级0任务的位置
                next_priority_0_index = -1
                for j in range(i + 1, len(tasks)):
                    if tasks[j].type.priority == 1:
                        next_priority_0_index = j
                        break
                # 如果其他任务的总执行时间超过了下一个优先级0任务的执行时间，调整它们的时间
                if next_priority_0_index > -1:
                    for j in range(i, next_priority_0_index):
                        # 菲亚充能/派对内置3分钟，线索购物内置1分钟
                        task_time = (
                            0
                            if len(tasks[j].plan) > 0
                            and tasks[j].type
                            not in [TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY]
                            else (
                                3
                                if tasks[j].type
                                in [TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY]
                                else 1
                            )
                        )
                        # 其他任务按照 每个房间*预设执行时间算 默认 45秒
                        estimate_time = (
                            len(tasks[j].plan) * execution_time
                            if task_time == 0
                            else task_time
                        )
                        if (
                            timedelta(minutes=total_execution_time + estimate_time)
                            + time_now
                            < tasks[j].time
                        ):
                            total_execution_time = 0
                        else:
                            total_execution_time += estimate_time
                    if (
                        timedelta(minutes=total_execution_time) + time_now
                        > tasks[next_priority_0_index].time
                    ):
                        logger.info("检测到任务可能影响到下次跑单修改任务至跑单之后")
                        logger.debug("||".join([str(t) for t in tasks]))
                        next_priority_0_time = tasks[next_priority_0_index].time
                        for j in range(i, next_priority_0_index):
                            tasks[j].time = next_priority_0_time + timedelta(seconds=1)
                            next_priority_0_time = tasks[j].time
                        logger.debug("||".join([str(t) for t in tasks]))
                        break
        tasks.sort(key=lambda x: x.time)


def try_add_release_dorm(plan, time, op_data, tasks):
    if not op_data.config.free_room:
        return
    # 有plan 的情况
    for k, v in plan.items():
        for name in v:
            if name != "Current":
                _idx, __dorm = op_data.get_dorm_by_name(name)
                if __dorm and __dorm.time < time:
                    add_release_dorm(tasks, op_data, name)
    # 普通情况
    if not plan:
        try:
            # 查看是否有未满心情的人
            logger.info("启动不养闲人安排空余宿舍位")
            waiting_list = []
            for k, v in op_data.operators.items():
                if (
                    not v.is_high()
                    and v.current_mood() < v.upper_limit
                    and v.current_room == ""
                    and v.name not in op_data.free_blacklist
                ):
                    heapq.heappush(
                        waiting_list,
                        (
                            1 if k in ["九色鹿", "年"] else 0,
                            (v.current_mood() - v.lower_limit)
                            / (v.upper_limit - v.lower_limit),
                            k,
                        ),
                    )
                    logger.debug(f"{k}:心情：{v.current_mood()}")
            if not waiting_list:
                return
            logger.debug(f"有{len(waiting_list)}个干员心情未满")
            plan = {}
            for idx, value in enumerate(op_data.dorm):
                if value.name in op_data.operators:
                    if not waiting_list:
                        break
                    agent = op_data.operators[value.name]
                    logger.info(str(value))
                    if not v.is_high() and (
                        agent.current_mood() >= agent.upper_limit
                        or (value.time is not None and value.time < datetime.now())
                    ):
                        rest = heapq.heappop(waiting_list)
                        if value.position[0] not in plan:
                            plan[value.position[0]] = ["Current"] * 5
                        plan[value.position[0]][value.position[1]] = rest[2]
            if plan:
                logger.debug(f"不养闲人任务：{plan}")
                logger.info("添加不养闲人任务完成")
                task = SchedulerTask(task_plan=plan)
                tasks.append(task)
        except Exception as ex:
            logger.exception(ex)


def add_release_dorm(tasks, op_data, name):
    _idx, __dorm = op_data.get_dorm_by_name(name)
    if (
        __dorm.time > datetime.now()
        and find_next_task(tasks, task_type=TaskTypes.RELEASE_DORM, meta_data=name)
        is None
    ):
        _free = op_data.operators[name]
        if _free.current_room.startswith("dorm"):
            __plan = {_free.current_room: ["Current"] * 5}
            __plan[_free.current_room][_free.current_index] = "Free"
            task = SchedulerTask(
                time=__dorm.time,
                task_type=TaskTypes.RELEASE_DORM,
                task_plan=__plan,
                meta_data=name,
            )
            tasks.append(task)
            logger.info(name + " 新增释放宿舍任务")
            logger.debug(str(task))


def check_dorm_ordering(tasks, op_data):
    # 仅当下班的时候才触发宿舍排序任务
    plan = op_data.plan
    if len(tasks) == 0:
        return
    if tasks[0].type == TaskTypes.SHIFT_OFF and tasks[0].meta_data == "":
        extra_plan = {}
        other_plan = {}
        working_agent = []
        for room, v in tasks[0].plan.items():
            if not room.startswith("dorm"):
                working_agent.extend(v)
        for room, v in tasks[0].plan.items():
            # 非宿舍则不需要清空
            if room.startswith("dorm"):
                # 是否检查过vip位置
                pass_first_free = False
                for idx, agent in enumerate(v):
                    # 如果当前位置非宿管 且无人员变动（有变动则是下班干员）
                    if "Free" == plan[room][idx].agent and agent == "Current":
                        # 如果高优先不变，则跳过逻辑判定
                        if not pass_first_free:
                            continue
                        current = next(
                            (
                                obj
                                for obj in op_data.operators.values()
                                if obj.current_room == room and obj.current_index == idx
                            ),
                            None,
                        )
                        if current:
                            if current.name not in working_agent:
                                v[idx] = current.name
                            else:
                                logger.debug(f"检测到干员{current.name}已经上班")
                                v[idx] = "Free"
                        if room not in extra_plan:
                            extra_plan[room] = copy.deepcopy(v)
                        # 新生成移除任务 --> 换成移除
                        extra_plan[room][idx] = ""
                    if "Free" == plan[room][idx].agent and not pass_first_free:
                        pass_first_free = True
            else:
                other_plan[room] = v
        tasks[0].meta_data = "宿舍排序完成"
        if extra_plan:
            for k, v in other_plan.items():
                del tasks[0].plan[k]
                extra_plan[k] = v
            logger.info("新增排序任务任务")
            task = SchedulerTask(
                task_plan=extra_plan,
                time=tasks[0].time - timedelta(seconds=1),
                task_type=TaskTypes.RE_ORDER,
            )
            tasks.insert(0, task)
            logger.debug(str(task))


def set_type_enum(value):
    if value is None:
        return TaskTypes.NOT_SPECIFIC
    if isinstance(value, TaskTypes):
        return value
    if isinstance(value, str):
        for task_type in TaskTypes:
            if value.upper() == task_type.display_value.upper():
                return task_type
    return TaskTypes.NOT_SPECIFIC


def merge_release_dorm(tasks, merge_interval):
    for idx in range(1, len(tasks) + 1):
        if idx == 1:
            continue
        task = tasks[-idx]
        last_not_release = None
        if task.type != TaskTypes.RELEASE_DORM:
            continue
        for index_last_not_release in range(idx + 1, len(tasks) + 1):
            if tasks[-index_last_not_release].type != TaskTypes.RELEASE_DORM and tasks[
                -index_last_not_release
            ].time > task.time - timedelta(minutes=1):
                last_not_release = tasks[-index_last_not_release]
        if last_not_release is not None:
            continue
        elif task.time + timedelta(minutes=merge_interval) > tasks[-idx + 1].time:
            tasks[-idx].time = tasks[-idx + 1].time + timedelta(seconds=1)
            tasks[-idx], tasks[-idx + 1] = (
                tasks[-idx + 1],
                tasks[-idx],
            )
            logger.info(f"自动合并{merge_interval}分钟以内任务")


class SchedulerTask:
    time = None
    type = ""
    plan = {}
    meta_data = ""

    def __init__(self, time=None, task_plan={}, task_type="", meta_data=""):
        if time is None:
            self.time = datetime.now()
        else:
            self.time = time
        self.plan = task_plan
        self.type = set_type_enum(task_type)
        self.meta_data = meta_data

    def format(self, time_offset=0):
        res = copy.deepcopy(self)
        res.time += timedelta(hours=time_offset)
        res.type = res.type.display_value
        if res.type == "空任务" and res.meta_data:
            res.type = res.meta_data
        return res

    def __str__(self):
        return f"SchedulerTask(time='{self.time}',task_plan={self.plan},task_type={self.type},meta_data='{self.meta_data}')"

    def __eq__(self, other):
        if isinstance(other, SchedulerTask):
            return (
                self.type == other.type
                and self.plan == other.plan
                and the_same_time(self.time, other.time)
            )
        return False
