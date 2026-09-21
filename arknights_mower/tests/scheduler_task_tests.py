import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    plan_metadata,
    scheduling,
    try_add_release_dorm,
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

    def add_dorm_overlay_backup(self, op_data):
        op_data.global_plan["default_plan"].config.free_room = True
        backup = Plan(
            {
                "dormitory_1": [
                    Room("Current", "", []),
                    Room("Current", "", []),
                    Room("真言", "", []),
                    Room("Current", "", []),
                    Room("Current", "", []),
                ]
            },
            PlanConfig("", "", ""),
        )
        op_data.global_plan["backup_plans"] = [backup]
        op_data.backup_plans = [backup]
        self.assertIsNone(op_data.swap_plan([False], refresh=True))
        return next(
            dorm for dorm in op_data.dorm if dorm.position == ("dormitory_1", 2)
        )

    @staticmethod
    def task_writes_slot(tasks, room, index):
        for task in tasks:
            room_plan = task.plan.get(room)
            if room_plan and index < len(room_plan) and room_plan[index] != "Current":
                return True
        return False

    def test_effective_free_slot_round_trip_and_capacity(self):
        op_data = self.init_opdata()
        target = self.add_dorm_overlay_backup(op_data)
        before_low = op_data.available_free("low")

        self.assertTrue(op_data.is_effective_free_slot(target))
        self.assertIsNone(op_data.swap_plan([True], refresh=True))
        self.assertFalse(op_data.is_effective_free_slot(target))
        self.assertEqual(before_low - 1, op_data.available_free("low"))

        self.assertIsNone(op_data.swap_plan([False], refresh=True))
        self.assertTrue(op_data.is_effective_free_slot(target))
        self.assertEqual(before_low, op_data.available_free("low"))

    def test_active_high_resting_ignores_backup_overlaid_slot(self):
        op_data = self.init_opdata()
        target = self.add_dorm_overlay_backup(op_data)
        op_data.operators["红"].current_room = ""
        op_data.operators["红"].current_index = -1
        high = op_data.operators["夕"]
        high.current_room = "dormitory_1"
        high.current_index = 2
        target.name = "夕"
        target.time = datetime.now() + timedelta(hours=1)

        self.assertEqual(1, op_data.active_high_resting_count())
        self.assertIsNone(op_data.swap_plan([True], refresh=True))
        self.assertEqual(0, op_data.active_high_resting_count())
        self.assertIsNone(op_data.swap_plan([False], refresh=True))
        self.assertEqual(1, op_data.active_high_resting_count())

    def test_backup_overlay_blocks_task_rebuild_and_free_room_writes(self):
        op_data = self.init_opdata()
        target = self.add_dorm_overlay_backup(op_data)
        now = datetime.now()
        red = op_data.operators["红"]
        red.current_room = "dormitory_1"
        red.current_index = 2
        red.mood = red.upper_limit
        red.time_stamp = now
        target.name = "红"
        target.time = now + timedelta(hours=1)

        waiting = op_data.operators["陈"]
        waiting.current_room = ""
        waiting.current_index = -1
        waiting.mood = 1
        waiting.time_stamp = now

        self.assertIsNone(op_data.swap_plan([True], refresh=True))

        rebuilt = plan_metadata(op_data, [])
        self.assertFalse(self.task_writes_slot(rebuilt, "dormitory_1", 2))

        release_tasks = []
        try_add_release_dorm(
            {"meeting": ["红"]}, now + timedelta(hours=2), op_data, release_tasks
        )
        self.assertFalse(self.task_writes_slot(release_tasks, "dormitory_1", 2))

        free_room_tasks = []
        try_add_release_dorm({}, None, op_data, free_room_tasks)
        self.assertFalse(self.task_writes_slot(free_room_tasks, "dormitory_1", 2))

        self.assertIsNone(op_data.swap_plan([False], refresh=True))
        restored_tasks = []
        try_add_release_dorm({}, None, op_data, restored_tasks)
        self.assertTrue(self.task_writes_slot(restored_tasks, "dormitory_1", 2))

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
