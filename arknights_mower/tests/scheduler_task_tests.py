import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    scheduling,
    try_reorder,
)

with patch.dict("sys.modules", {"save_action_to_sqlite_decorator": MagicMock()}):
    pass


class TestScheduling(unittest.TestCase):
    def test_adjust_two_orders(self):
        # 测试两个跑单任务被拉开
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 2"},
        )
        task3 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 3"},
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task2, task3, task4, task5]
        res = scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 09:01", "%Y-%m-%d %H:%M")
        )
        # 返还的是应该拉开跑单的任务
        self.assertNotEqual(res, None)

    def test_adjust_two_orders_fia(self):
        # 测试菲亚换班时间预设3分钟有效
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={},
            task_type=TaskTypes.FIAMMETTA,
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task2, task4, task5]
        scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        )
        # 跑单任务被提前
        self.assertEqual(tasks[0].type, TaskTypes.RUN_ORDER)

    def test_adjust_time(self):
        # 测试跑单任务被挤兑
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 2"},
        )
        task3 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 3"},
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task2, task3, task4, task5]
        res = scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M")
        )
        # 其他任务会被移送至跑单任务以后
        self.assertEqual(tasks[2].plan["task"], "Task 4")
        self.assertEqual(res, None)

    def test_find_next(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
        )
        task4 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 4"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
        )
        task5 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
            task_plan={"task": "Task 5"},
        )
        tasks = [task1, task4, task5]
        now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        res1 = find_next_task(
            tasks,
            now + timedelta(minutes=5),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
            compare_type=">",
        )
        res2 = find_next_task(
            tasks,
            now + timedelta(minutes=-60),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room",
            compare_type=">",
        )
        self.assertEqual(res1, None)
        self.assertNotEqual(res2, None)

    def test_adjust_three_orders(self):
        # 测试342跑单任务被拉开
        task1 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
            task_plan={"task1": "Task 1"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="task1",
        )
        task2 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
            task_plan={"task2": "Task 2"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="task2",
        )
        task3 = SchedulerTask(
            time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
            task_plan={"task3": "Task 3"},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="task3",
        )
        tasks = [task1, task2, task3]
        res = scheduling(
            tasks, time_now=datetime.strptime("2023-09-19 09:01", "%Y-%m-%d %H:%M")
        )

        while res is not None and res[0].meta_data == "task1":
            task_time = res[0].time - timedelta(minutes=(2))
            task = find_next_task(
                tasks, task_type=TaskTypes.RUN_ORDER, meta_data="task1"
            )
            if task is not None:
                task.time = task_time
                res = scheduling(
                    tasks,
                    time_now=datetime.strptime("2023-09-19 09:03", "%Y-%m-%d %H:%M"),
                )
            else:
                break
        # 返还的是应该拉开跑单的任务
        self.assertNotEqual(res, None)

    def test_reorder_1(self):
        # 高优先级被拉前面
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.operators["凯尔希"].current_room = "dormitory_2"
        op_data.operators["凯尔希"].current_index = 2
        op_data.dorm[2].name = "夕"
        plan = try_reorder(op_data, {})
        self.assertEqual(plan["dormitory_1"][2], "夕")

    def test_reorder_2(self):
        # 非高优高效不会被移动
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.dorm[2].name = "夕"
        op_data.dorm[3].name = "见行者"
        op_data.dorm[4].name = "森蚺"

        # op_data.config.ope_resting_priority=["森蚺","夕"]
        plan = try_reorder(op_data, {})
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan["dormitory_1"][2], "夕")
        self.assertEqual(plan["dormitory_1"][4], "凯尔希")

    def test_reorder_3(self):
        # 如果高优都占了，则不动
        op_data = self.init_opdata()
        op_data.dorm[0].name = "夕"
        op_data.dorm[1].name = "焰尾"
        op_data.dorm[2].name = "森蚺"
        op_data.dorm[3].name = "玛恩纳"
        op_data.operators["见行者"].current_room = "dormitory_2"
        op_data.operators["见行者"].current_index = 2
        op_data.dorm[4].name = "见行者"
        try_reorder(op_data, {})
        plan = try_reorder(op_data, {})
        self.assertEqual(plan["dormitory_1"][2], "夕")
        self.assertEqual(plan["dormitory_1"][3], "见行者")

    def init_opdata(self):
        agent_base_config = PlanConfig(
            "稀音,黑键,伊内丝,承曦格雷伊", "稀音,柏喙,伊内丝", "见行者"
        )
        plan_config = {
            "central": [
                Room("夕", "", ["麒麟R夜刀"]),
                Room("焰尾", "", ["凯尔希"]),
                Room("森蚺", "", ["凯尔希"]),
                Room("令", "", ["火龙S黑角"]),
                Room("薇薇安娜", "", ["玛恩纳"]),
            ],
            "meeting": [
                Room("伊内丝", "", ["陈", "红"]),
                Room("见行者", "", ["陈", "红"]),
            ],
            "dormitory_1": [
                Room("塑心", "", []),
                Room("冰酿", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
            "dormitory_2": [
                Room("琴柳", "", []),
                Room("阿米娅", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
            "dormitory_3": [
                Room("迷迭香", "", []),
                Room("杜林", "", []),
                Room("月见夜", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
        }
        plan = {
            "default_plan": Plan(plan_config, agent_base_config),
            "backup_plans": [],
        }
        op_data = Operators(plan)
        op_data.init_and_validate()
        # 预设干员位置
        op_data.operators["冰酿"].current_room = op_data.operators[
            "塑心"
        ].current_room = op_data.operators["见行者"].current_room = "dormitory_1"

        op_data.operators["红"].current_room = op_data.operators[
            "玛恩纳"
        ].current_room = "dormitory_1"

        op_data.operators["冰酿"].current_index = 0
        op_data.operators["塑心"].current_index = 1
        op_data.operators["红"].current_index = 2
        op_data.operators["见行者"].current_index = 3
        op_data.operators["玛恩纳"].current_index = 4
        # drom 2
        op_data.operators["琴柳"].current_room = op_data.operators[
            "阿米娅"
        ].current_room = "dormitory_2"
        op_data.operators["琴柳"].current_index = 0
        op_data.operators["阿米娅"].current_index = 1
        # drom 3
        op_data.operators["迷迭香"].current_room = op_data.operators[
            "杜林"
        ].current_room = op_data.operators["月见夜"].current_room = "dormitory_3"
        op_data.operators["迷迭香"].current_index = 0
        op_data.operators["杜林"].current_index = 1
        op_data.operators["月见夜"].current_index = 2

        return op_data
