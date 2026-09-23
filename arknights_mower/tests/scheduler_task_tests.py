import copy
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    _merge_deferred_dorm_schedules,
    find_next_task,
    plan_metadata,
    rebalance_plan_swap_dorms,
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

    def test_experimental_dorm_only_tasks_run_before_run_order(self):
        now = datetime(2026, 9, 23, 2, 15)
        dorm_tasks = [
            SchedulerTask(
                time=now,
                task_plan={f"dormitory_{index}": ["Free"] * 5},
                task_type=TaskTypes.RE_ORDER,
            )
            for index in range(1, 5)
        ]
        run_order = SchedulerTask(
            time=now + timedelta(minutes=3),
            task_plan={"room_2_1": ["跑单组"]},
            task_type=TaskTypes.RUN_ORDER,
        )
        tasks = [*dorm_tasks, run_order]

        with patch.object(config.conf, "experimental_dorm_logic", True):
            scheduling(tasks, time_now=now)

        self.assertEqual([task.time for task in dorm_tasks], [now] * 4)
        self.assertEqual(tasks[-1], run_order)
        self.assertEqual(run_order.time, now + timedelta(minutes=3))
        self.assertFalse(any(task.deferred_by_run_order for task in dorm_tasks))

    def test_deferred_dorm_schedules_are_merged_before_run_order(self):
        shift_off = SchedulerTask(
            time=datetime(2026, 9, 22, 5, 18, 15),
            task_plan={
                "room_1_1": ["替班"],
                "dormitory_1": [
                    "Current",
                    "Current",
                    "虎狼丸",
                    "Current",
                    "Current",
                ],
                "dormitory_3": [
                    "Current",
                    "信仰搅拌机",
                    "食铁兽",
                    "Current",
                    "Current",
                ],
                "dormitory_4": ["夕", "九色鹿", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
        )
        reorder_time = datetime(2026, 9, 22, 5, 18, 44)
        reorder = SchedulerTask(
            time=reorder_time,
            task_plan={
                "dormitory_1": ["Current", "Current", "焰尾", "Current", "Current"],
                "dormitory_2": ["砾", "信仰搅拌机", "Current", "Current", "Current"],
                "dormitory_3": ["夕", "Current", "Current", "Current", "Current"],
                "dormitory_4": ["九色鹿", "Free", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.RE_ORDER,
        )
        followup = SchedulerTask(time=reorder_time)
        shift_on = SchedulerTask(
            time=datetime(2026, 9, 22, 5, 25, 31),
            task_plan={
                "room_1_1": ["焰尾", "砾"],
                "dormitory_1": ["Current", "Current", "Free", "Current", "Current"],
                "dormitory_2": ["Free", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_ON,
        )
        run_order = SchedulerTask(
            time=datetime(2026, 9, 22, 5, 26, 17),
            task_plan={"room_2_1": ["跑单组"]},
            task_type=TaskTypes.RUN_ORDER,
        )
        tasks = [shift_off, reorder, followup, shift_on, run_order]
        stable_tasks = copy.deepcopy(tasks)

        with patch.object(config.conf, "experimental_dorm_logic", True):
            scheduling(tasks, time_now=datetime(2026, 9, 22, 5, 25, 30))

        self.assertEqual(
            [task.type for task in tasks],
            [TaskTypes.RUN_ORDER, TaskTypes.SHIFT_OFF, TaskTypes.SHIFT_ON],
        )
        dorm_tasks = [
            task
            for task in tasks
            if any(room.startswith("dormitory_") for room in task.plan)
        ]
        self.assertEqual(dorm_tasks, [shift_off])
        self.assertEqual(
            shift_off.plan["dormitory_1"],
            ["Current", "Current", "Free", "Current", "Current"],
        )
        self.assertEqual(
            shift_off.plan["dormitory_2"],
            ["Free", "信仰搅拌机", "Current", "Current", "Current"],
        )
        self.assertEqual(
            (shift_off.time, shift_on.time),
            (
                run_order.time + timedelta(seconds=1),
                run_order.time + timedelta(seconds=2),
            ),
        )
        self.assertTrue(shift_off.deferred_by_run_order)
        self.assertTrue(shift_on.deferred_by_run_order)

        with patch.object(config.conf, "experimental_dorm_logic", False):
            scheduling(stable_tasks, time_now=datetime(2026, 9, 22, 5, 25, 30))
        self.assertEqual(
            [task.type for task in stable_tasks],
            [
                TaskTypes.RUN_ORDER,
                TaskTypes.SHIFT_OFF,
                TaskTypes.RE_ORDER,
                TaskTypes.NOT_SPECIFIC,
                TaskTypes.SHIFT_ON,
            ],
        )
        self.assertEqual(
            sum(
                any(room.startswith("dormitory_") for room in task.plan)
                for task in stable_tasks
            ),
            3,
        )

    def test_deferred_dorm_merge_preserves_special_tasks(self):
        special_cases = (
            (
                TaskTypes.FIAMMETTA,
                "充能目标",
                ["菲亚梅塔", "充能目标", "Current", "Current", "Current"],
            ),
            (
                TaskTypes.RELEASE_DORM,
                "待释放干员",
                ["Free", "Current", "Current", "Current", "Current"],
            ),
        )
        for task_type, meta_data, agents in special_cases:
            with self.subTest(task_type=task_type):
                shift_off = SchedulerTask(
                    task_plan={"dormitory_1": ["休息者", "Current"]},
                    task_type=TaskTypes.SHIFT_OFF,
                )
                reorder = SchedulerTask(
                    task_plan={"dormitory_1": ["Current", "候补者"]},
                    task_type=TaskTypes.RE_ORDER,
                )
                special_plan = {"dormitory_2": agents}
                special = SchedulerTask(
                    task_plan=copy.deepcopy(special_plan),
                    task_type=task_type,
                    meta_data=meta_data,
                )

                result = _merge_deferred_dorm_schedules([shift_off, special, reorder])

                self.assertTrue(any(task is special for task in result))
                self.assertEqual(special.type, task_type)
                self.assertEqual(special.meta_data, meta_data)
                self.assertEqual(special.plan, special_plan)

    def test_deferred_dorm_merge_keeps_empty_shift_off_and_its_followup(self):
        shift_off = SchedulerTask(
            task_plan={"dormitory_1": ["Current", "Current"]},
            task_type=TaskTypes.SHIFT_OFF,
        )
        reorder = SchedulerTask(
            task_plan={"dormitory_1": ["Current", "临时休息者"]},
            task_type=TaskTypes.RE_ORDER,
        )
        followup = SchedulerTask(time=reorder.time)

        result = _merge_deferred_dorm_schedules([reorder, followup, shift_off])

        self.assertEqual(result, [shift_off])
        self.assertEqual(shift_off.plan, {"dormitory_1": ["Current", "临时休息者"]})

    def test_deferred_dorm_merge_keeps_followup_for_anchor_reorder(self):
        shift_off = SchedulerTask(
            task_plan={"room_1_1": ["替班"]},
            task_type=TaskTypes.SHIFT_OFF,
        )
        reorder = SchedulerTask(
            task_plan={"dormitory_1": ["Current", "临时休息者"]},
            task_type=TaskTypes.RE_ORDER,
        )
        followup = SchedulerTask(time=reorder.time)

        result = _merge_deferred_dorm_schedules([shift_off, reorder, followup])

        self.assertEqual(result, [shift_off, reorder, followup])
        self.assertEqual(reorder.plan, {"dormitory_1": ["Current", "临时休息者"]})

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
        # 测试逻辑直接落实本轮已经选好的床位，不再全量移动现有休息者。
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.operators["凯尔希"].current_room = "dormitory_2"
        op_data.operators["凯尔希"].current_index = 2
        op_data.dorm[2].name = "夕"
        plan = try_reorder(op_data, {})
        self.assertEqual(plan["dormitory_1"][2:], ["麒麟R夜刀", "凯尔希", "夕"])
        self.assertEqual(plan["dormitory_2"][2], "Free")

    def test_reorder_2(self):
        # 新入住者不能让已经选好的其他床位再按实时心情洗牌。
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.dorm[2].name = "夕"
        op_data.dorm[3].name = "见行者"
        op_data.dorm[4].name = "森蚺"

        plan = try_reorder(op_data, {})
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan["dormitory_1"][2:], ["麒麟R夜刀", "凯尔希", "夕"])
        self.assertEqual(plan["dormitory_2"][2:4], ["见行者", "森蚺"])

    def test_reorder_3(self):
        # 未执行前重复演算得到同一结果，不会在两种宿舍布局间振荡。
        op_data = self.init_opdata()
        op_data.dorm[0].name = "夕"
        op_data.dorm[1].name = "焰尾"
        op_data.dorm[2].name = "森蚺"
        op_data.dorm[3].name = "玛恩纳"
        op_data.operators["见行者"].current_room = "dormitory_2"
        op_data.operators["见行者"].current_index = 2
        op_data.dorm[4].name = "见行者"
        first = try_reorder(op_data, {})
        second = try_reorder(op_data, {})
        self.assertEqual(first, second)
        self.assertEqual(first["dormitory_1"][2:], ["夕", "焰尾", "森蚺"])
        self.assertEqual(first["dormitory_2"][2:4], ["玛恩纳", "见行者"])

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
            PlanConfig("", "", "", experimental_dorm_logic=True),
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

    def test_active_high_resting_migrates_when_backup_removes_bed(self):
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
        migration = rebalance_plan_swap_dorms(op_data)
        self.assertTrue(migration)
        self.assertEqual(1, op_data.active_high_resting_count())
        self.assertIsNone(op_data.swap_plan([False], refresh=True))
        rebalance_plan_swap_dorms(op_data)
        self.assertEqual(1, op_data.active_high_resting_count())

    def test_backup_removed_bed_is_restored_and_occupant_is_migrated(self):
        op_data = self.init_opdata()
        target = self.add_dorm_overlay_backup(op_data)
        high = op_data.operators["夕"]
        high.current_room, high.current_index = target.position
        target.name = "夕"
        target.time = datetime.now() + timedelta(hours=1)

        self.assertIsNone(op_data.swap_plan([True], refresh=True))
        self.assertFalse(
            any(dorm.position == ("dormitory_1", 2) for dorm in op_data.dorm)
        )
        plan = rebalance_plan_swap_dorms(op_data)
        self.assertEqual("真言", plan["dormitory_1"][2])
        destination = next(dorm for dorm in op_data.dorm if dorm.name == "夕")
        room, index = destination.position
        self.assertEqual("夕", plan[room][index])
        self.assertEqual(target.time, destination.time)

    def test_single_recovery_target_stays_in_room_when_its_bed_closes(self):
        op_data = self.init_opdata()
        closing = self.add_dorm_overlay_backup(op_data)
        target = op_data.operators["麒麟R夜刀"]
        target.current_room, target.current_index = closing.position
        target.dorm_recovery_room = "dormitory_1"
        target.dorm_recovery_fixed = ("塑心", "冰酿")
        closing.name = target.name
        closing.time = datetime.now() + timedelta(hours=1)
        previous = copy.deepcopy(op_data.dorm)

        self.assertIsNone(op_data.swap_plan([True], refresh=True))
        plan = rebalance_plan_swap_dorms(op_data, previous)

        destination = next(dorm for dorm in op_data.dorm if dorm.name == target.name)
        self.assertEqual(destination.position[0], "dormitory_1")
        self.assertEqual(target.dorm_recovery_room, "dormitory_1")
        self.assertEqual(plan["dormitory_1"][2], "真言")
        self.assertEqual(plan["dormitory_1"][destination.position[1]], target.name)

    def test_single_recovery_move_to_other_room_requests_recovery_again(self):
        op_data = self.init_opdata()
        target_bed = op_data.dorm[0]
        target = op_data.operators["麒麟R夜刀"]
        target.current_room, target.current_index = target_bed.position
        target.dorm_recovery_room = target_bed.position[0]
        target.dorm_recovery_fixed = ("塑心", "冰酿")
        target_bed.name = target.name
        target_bed.time = datetime.now() + timedelta(hours=1)
        previous = copy.deepcopy(op_data.dorm)
        op_data.dorm = [
            bed for bed in op_data.dorm if bed.position[0] != target.current_room
        ]

        plan = rebalance_plan_swap_dorms(op_data, previous)

        destination = next(dorm for dorm in op_data.dorm if dorm.name == target.name)
        self.assertNotEqual(destination.position[0], target.current_room)
        self.assertEqual(target.dorm_recovery_room, "")
        self.assertEqual(
            plan[destination.position[0]][destination.position[1]], target.name
        )

    def test_single_recovery_target_is_exempt_from_capacity_drop(self):
        op_data = self.init_opdata()
        protected_bed, preferred_bed = op_data.dorm[:2]
        protected = op_data.operators["麒麟R夜刀"]
        protected.current_room, protected.current_index = protected_bed.position
        protected.dorm_recovery_room = protected_bed.position[0]
        protected.dorm_recovery_fixed = ("塑心", "冰酿")
        protected.mood = 23
        protected.time_stamp = datetime.now()
        protected_bed.name = protected.name
        preferred = op_data.operators["夕"]
        preferred.current_room, preferred.current_index = preferred_bed.position
        preferred.mood = 1
        preferred.time_stamp = datetime.now()
        preferred_bed.name = preferred.name
        previous = copy.deepcopy(op_data.dorm[:2])
        op_data.dorm = [protected_bed]

        rebalance_plan_swap_dorms(op_data, previous)

        self.assertEqual(op_data.dorm[0].name, protected.name)
        self.assertEqual(protected.dorm_recovery_room, protected.current_room)

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
            "稀音,黑键,伊内丝,承曦格雷伊",
            "稀音,柏喙,伊内丝",
            "见行者",
            experimental_dorm_logic=True,
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
