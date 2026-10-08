import copy
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    _merge_deferred_dorm_schedules,
    adjust_run_order_for_maintenance,
    find_next_task,
    plan_metadata,
    rebalance_plan_swap_dorms,
    scheduling,
    try_add_release_dorm,
    try_reorder,
)

with patch.dict("sys.modules", {"save_action_to_sqlite_decorator": MagicMock()}):
    pass


class TestRunOrderRestorationScheduling(unittest.TestCase):
    def setUp(self):
        from arknights_mower.utils import config

        self.now = datetime(2026, 10, 8, 18)
        conf = config.Conf()
        conf.enable_mastery = False
        conf.run_order_grandet_mode.enable = True
        for replacement in (
            patch.object(config, "conf", conf),
            patch(
                "arknights_mower.utils.scheduler_task.NewsChecker.get_update_time",
                return_value=(None, None),
            ),
            patch(
                "arknights_mower.utils.scheduler_task.estimate_dorm_minutes",
                return_value=1,
            ),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def make_restore(self, seconds=0):
        task = SchedulerTask(
            time=self.now + timedelta(seconds=seconds),
            task_plan={"room_1_1": ["图耶"]},
            task_type=TaskTypes.RUN_ORDER,
        )
        task.run_order_original_roster = copy.deepcopy(task.plan)
        task.run_order_restore_pending = True
        return task

    def test_restoration_between_orders_does_not_become_drone_adjustment_target(self):
        first = SchedulerTask(
            time=self.now + timedelta(minutes=1),
            task_plan={"room_2_1": ["但书"]},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_2_1",
        )
        restore = self.make_restore(seconds=120)
        second = SchedulerTask(
            time=self.now + timedelta(minutes=3),
            task_plan={"room_3_1": ["但书"]},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_3_1",
        )
        tasks = [first, restore, second]

        self.assertEqual(scheduling(tasks, time_now=self.now), (first, second))

        self.assertIn(restore, tasks)
        self.assertEqual(restore.time, self.now + timedelta(minutes=2))
        self.assertFalse(restore.adjusted)

    def test_restoration_retains_unified_priority_over_due_ordinary_work(
        self,
    ):
        restore = self.make_restore()
        ordinary = SchedulerTask(
            time=self.now - timedelta(minutes=1),
            task_plan={"central": ["阿米娅"]},
            task_type=TaskTypes.SELF_CORRECTION,
        )
        tasks = [ordinary, restore]

        self.assertIsNone(scheduling(tasks, time_now=self.now))

        self.assertIs(tasks[0], restore)
        self.assertEqual(restore.time, self.now)
        self.assertEqual(ordinary.time, self.now + timedelta(seconds=1))

    def test_restoration_budget_excludes_grandet_wait_before_next_order(self):
        restore = self.make_restore()
        ordinary = SchedulerTask(
            time=self.now + timedelta(minutes=1),
            task_plan={"central": ["阿米娅"]},
            task_type=TaskTypes.SELF_CORRECTION,
        )
        order = SchedulerTask(
            time=self.now + timedelta(minutes=3),
            task_plan={"room_2_1": ["但书"]},
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_2_1",
        )
        tasks = [restore, ordinary, order]

        self.assertIsNone(scheduling(tasks, execution_time=0.75, time_now=self.now))

        self.assertIs(tasks[0], restore)
        self.assertEqual(ordinary.time, self.now + timedelta(minutes=1))
        self.assertEqual(order.time, self.now + timedelta(minutes=3))

    def test_restoration_still_protects_strict_release_operation_window(self):
        restore = self.make_restore(seconds=120)
        release = SchedulerTask(
            time=self.now + timedelta(minutes=5),
            task_plan={"dormitory_1": ["Free"]},
            task_type=TaskTypes.RELEASE_DORM,
            meta_data="红",
            strict_mood_limit=True,
        )
        tasks = [restore, release]

        self.assertIsNone(scheduling(tasks, time_now=self.now))

        self.assertLess(release.time + timedelta(minutes=1), restore.time)
        self.assertEqual(restore.time, self.now + timedelta(minutes=2))
        self.assertEqual(release.mood_limit_deadline, self.now + timedelta(minutes=5))

    def test_maintenance_excludes_only_marked_restoration(self):
        restore = self.make_restore(seconds=120)
        pending_insertion = self.make_restore(seconds=180)
        pending_insertion.meta_data = "room_1_1"
        legacy = SchedulerTask(
            time=self.now + timedelta(minutes=4),
            task_plan={"room_2_1": ["鸿雪"]},
            task_type=TaskTypes.RUN_ORDER,
        )
        start = self.now + timedelta(minutes=5)
        with patch(
            "arknights_mower.utils.scheduler_task.NewsChecker.get_update_time",
            return_value=(start, start + timedelta(hours=6)),
        ):
            adjusted = adjust_run_order_for_maintenance(
                [restore, pending_insertion, legacy]
            )

        self.assertEqual(adjusted, [pending_insertion, legacy])
        self.assertEqual(restore.time, self.now + timedelta(minutes=2))
        self.assertFalse(restore.adjusted)
        self.assertTrue(pending_insertion.adjusted)
        self.assertTrue(legacy.adjusted)


class TestScheduling(unittest.TestCase):
    def setUp(self):
        # Scheduling tests use fixed times; a live announcement request makes
        # their result and runtime depend on the external news service.
        maintenance = patch(
            "arknights_mower.utils.scheduler_task.NewsChecker.get_update_time",
            return_value=(None, None),
        )
        maintenance.start()
        self.addCleanup(maintenance.stop)

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
        # 保留可以完成的任务，仅将三分钟充能延后。
        self.assertEqual(tasks, [task1, task4, task2, task5])
        self.assertGreater(task2.time, task4.time)

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
        self.assertEqual(tasks, [task1, task4, task2, task3, task5])
        self.assertEqual(res, None)

    def test_dorm_prefix_runs_and_deferred_suffix_merges(self):
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
        scheduling(tasks, time_now=now)

        self.assertEqual(len(tasks), 3)
        self.assertIs(tasks[0], dorm_tasks[0])
        self.assertIs(tasks[1], run_order)
        self.assertEqual(run_order.time, now + timedelta(minutes=3))
        self.assertGreater(tasks[2].time, run_order.time)
        self.assertEqual(set(tasks[2].plan), {f"dormitory_{i}" for i in range(2, 5)})

    def test_dorm_wakeup_yields_to_run_order(self):
        for work_room in (False, True):
            for wake_type in (TaskTypes.NOT_SPECIFIC, TaskTypes.RE_ORDER):
                with self.subTest(work_room=work_room, wake_type=wake_type):
                    now = datetime(2026, 9, 23, 12)
                    dorm = SchedulerTask(
                        time=now,
                        task_type=TaskTypes.RE_ORDER,
                        task_plan={"dormitory_1": ["Current", "Free"]},
                    )
                    wake = SchedulerTask(time=now, task_type=wake_type)
                    order = SchedulerTask(
                        time=now + timedelta(seconds=30),
                        task_type=TaskTypes.RUN_ORDER,
                        task_plan={"room_1_1": ["Current"]},
                    )
                    tasks = [dorm, wake, order]
                    if work_room:
                        tasks.insert(
                            0,
                            SchedulerTask(
                                time=now,
                                task_type=TaskTypes.SHIFT_OFF,
                                task_plan={"central": ["阿米娅"]},
                            ),
                        )
                    with (
                        patch(
                            "arknights_mower.utils.scheduler_task.NewsChecker.get_update_time",
                            return_value=(None, None),
                        ),
                    ):
                        scheduling(tasks, time_now=now)
                    self.assertGreater(dorm.time, order.time)
                    if wake in tasks:
                        self.assertGreater(wake.time, order.time)

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

    def test_deferred_dorm_merge_keeps_final_reorder_wakeup(self):
        now = datetime(2026, 9, 27, 5)
        first = SchedulerTask(
            time=now,
            task_plan={"dormitory_1": ["Current", "休息者甲"]},
            task_type=TaskTypes.RE_ORDER,
        )
        first_followup = SchedulerTask(time=now)
        final = SchedulerTask(
            time=now,
            task_plan={"dormitory_2": ["Current", "休息者乙"]},
            task_type=TaskTypes.RE_ORDER,
        )
        final_followup = SchedulerTask(time=now)
        independent_wakeup = SchedulerTask(time=now + timedelta(minutes=1))

        result = _merge_deferred_dorm_schedules(
            [first, first_followup, final, final_followup, independent_wakeup]
        )

        self.assertEqual(result, [final, final_followup, independent_wakeup])
        self.assertEqual(
            final.plan,
            {
                "dormitory_1": ["Current", "休息者甲"],
                "dormitory_2": ["Current", "休息者乙"],
            },
        )

    def test_deferred_dorm_merge_keeps_wakeup_for_remaining_work(self):
        now = datetime(2026, 9, 27, 5)
        reorder = SchedulerTask(
            time=now,
            task_plan={
                "room_1_1": ["上班者"],
                "dormitory_1": ["Current", "休息者"],
            },
            task_type=TaskTypes.RE_ORDER,
        )
        followup = SchedulerTask(time=now)
        shift_off = SchedulerTask(
            time=now,
            task_plan={"dormitory_2": ["Current", "下班者"]},
            task_type=TaskTypes.SHIFT_OFF,
        )

        result = _merge_deferred_dorm_schedules([reorder, followup, shift_off])

        self.assertEqual(result, [reorder, followup, shift_off])
        self.assertEqual(reorder.plan, {"room_1_1": ["上班者"]})
        self.assertEqual(
            shift_off.plan,
            {
                "dormitory_1": ["Current", "休息者"],
                "dormitory_2": ["Current", "下班者"],
            },
        )

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
        # 空单回位按优先级和稳定候选顺序分配，不产生置换链。
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.operators["凯尔希"].current_room = "dormitory_2"
        op_data.operators["凯尔希"].current_index = 2
        op_data.dorm[2].name = "夕"
        plan = try_reorder(op_data, {})
        self.assertEqual(plan["dormitory_1"][2:], ["夕", "Free", "Free"])
        self.assertEqual(plan["dormitory_2"][2], "凯尔希")
        self.assertEqual(plan["dormitory_3"][3], "麒麟R夜刀")
        projected = op_data.project_arrangements([plan])
        self.assertEqual(
            {bed.name for bed in projected.dorm if bed.name},
            {"夕", "麒麟R夜刀", "凯尔希"},
        )
        self.assertEqual(try_reorder(projected, {}), {})

    def test_reorder_2(self):
        # 三个主班取得单回位，普通替班留在其余床位。
        op_data = self.init_opdata()
        op_data.dorm[0].name = "麒麟R夜刀"
        op_data.dorm[1].name = "凯尔希"
        op_data.dorm[2].name = "夕"
        op_data.dorm[3].name = "见行者"
        op_data.dorm[4].name = "森蚺"

        plan = try_reorder(op_data, {})
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan["dormitory_1"][2:], ["夕", "凯尔希", "麒麟R夜刀"])
        self.assertEqual(plan["dormitory_2"][2:4], ["森蚺", "Free"])
        self.assertEqual(plan["dormitory_3"][3], "见行者")

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
        self.assertEqual(first["dormitory_1"][2:], ["夕", "玛恩纳", "Free"])
        self.assertEqual(first["dormitory_2"][2:4], ["焰尾", "见行者"])
        self.assertEqual(first["dormitory_3"][3], "森蚺")
        projected = op_data.project_arrangements([first])
        self.assertCountEqual(
            [bed.name for bed in projected.dorm if bed.name],
            ["夕", "焰尾", "森蚺", "玛恩纳", "见行者"],
        )
        self.assertEqual(try_reorder(projected, {}), {})

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
        target.dorm_recovery_index = target.current_index
        target.dorm_recovery_fixed = ("塑心", "冰酿")
        closing.name = target.name
        closing.time = datetime.now() + timedelta(hours=1)
        previous = copy.deepcopy(op_data.dorm)

        self.assertIsNone(op_data.swap_plan([True], refresh=True))
        plan = rebalance_plan_swap_dorms(op_data, previous)

        destination = next(dorm for dorm in op_data.dorm if dorm.name == target.name)
        self.assertEqual(destination.position[0], "dormitory_1")
        target = op_data.operators[target.name]
        self.assertEqual(target.dorm_recovery_room, "")
        self.assertEqual(target.dorm_recovery_index, -1)
        self.assertEqual(plan["dormitory_1"][2], "真言")
        self.assertEqual(plan["dormitory_1"][destination.position[1]], target.name)

    def test_single_recovery_move_to_other_room_requests_recovery_again(self):
        op_data = self.init_opdata()
        target_bed = op_data.dorm[0]
        target = op_data.operators["麒麟R夜刀"]
        target.current_room, target.current_index = target_bed.position
        target.dorm_recovery_room = target_bed.position[0]
        target.dorm_recovery_index = target.current_index
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

    def test_single_recovery_target_cannot_displace_higher_tier_during_capacity_drop(
        self,
    ):
        op_data = self.init_opdata()
        protected_bed, preferred_bed = op_data.dorm[:2]
        protected = op_data.operators["麒麟R夜刀"]
        protected.current_room, protected.current_index = protected_bed.position
        protected.dorm_recovery_room = protected_bed.position[0]
        protected.dorm_recovery_index = protected.current_index
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

        self.assertEqual(op_data.dorm[0].name, preferred.name)
        self.assertEqual(protected.dorm_recovery_room, "")

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
        # 重新开放不抢占仍在位的单回目标，普通补位仍在其余空床进行。
        self.assertFalse(self.task_writes_slot(restored_tasks, "dormitory_1", 2))
        self.assertTrue(
            op_data.is_effective_free_slot(
                next(bed for bed in op_data.dorm if bed.position == ("dormitory_1", 2))
            )
        )
        projected = op_data.project_arrangements([task.plan for task in restored_tasks])
        self.assertIsNotNone(projected.get_dorm_by_name("陈")[0])

    def init_opdata(self):
        agent_base_config = PlanConfig(
            "稀音,黑键,伊内丝,承曦格雷伊",
            "稀音,柏喙,伊内丝",
            "见行者",
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
