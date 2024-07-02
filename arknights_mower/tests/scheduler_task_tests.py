from datetime import datetime, timedelta
import unittest
from unittest.mock import patch, MagicMock

from arknights_mower.utils.plan import Plan, Room, PlanConfig
from arknights_mower.utils.scheduler_task import (
    scheduling,
    SchedulerTask,
    TaskTypes,
    find_next_task,
    check_dorm_ordering,
)
from ..utils.operators import Operators

with patch.dict("sys.modules", {"save_action_to_sqlite_decorator": MagicMock()}):
    from ..solvers.record import save_action_to_sqlite_decorator


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
        res = scheduling(
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

    def test_check_dorm_ordering_add_plan_1(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "夕", "Current", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        check_dorm_ordering(tasks, op_data)
        # 生成额外宿舍任务
        self.assertEqual(2, len(tasks))
        # 验证第一个宿舍任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 老plan含有见行者
        self.assertEqual("见行者", tasks[1].plan["dormitory_1"][3])
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第二个任务仅仅包宿舍任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_add_plan_2(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "夕", "Current", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["见行者"].current_index = -1
        op_data.operators["见行者"].current_room = "meeting"
        op_data.operators["麒麟R夜刀"].current_index = 3
        op_data.operators["麒麟R夜刀"].current_room = "dormitory_1"
        check_dorm_ordering(tasks, op_data)
        # 生成额外宿舍任务
        self.assertEqual(2, len(tasks))
        # 验证第一个宿舍任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 老plan不变
        self.assertEqual("Current", tasks[1].plan["dormitory_1"][3])
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第二个任务仅仅包宿舍任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_add_plan_3(self):
        # 测试 宿舍4号位置已经吃到VIP的情况，安排新的高效干员去3号位置刷新VIP
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "夕", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["红"].current_index = -1
        op_data.operators["红"].current_room = "meeting"
        op_data.operators["夕"].resting_priority = "low"
        op_data.operators["焰尾"].current_index = 2
        op_data.operators["焰尾"].current_room = "dormitory_1"
        check_dorm_ordering(tasks, op_data)

        # 如果非VIP位置被占用，则刷新
        self.assertEqual(2, len(tasks))
        # 验证第任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第任务包宿舍+换班任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_add_plan_4(self):
        # 测试 方程有效
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "夕", "Current", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        op_data.operators["玛恩纳"].current_room = ""
        op_data.operators["玛恩纳"].current_index = -1
        check_dorm_ordering(tasks, op_data)
        # 生成额外宿舍任务
        self.assertEqual(2, len(tasks))
        # 验证第一个宿舍任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 老plan含有见行者
        self.assertEqual("见行者", tasks[1].plan["dormitory_1"][3])
        # 假设换班任务执行完毕
        del tasks[0]
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第二个任务仅仅包宿舍任务
        self.assertEqual(1, len(tasks[0].plan))

    def test_check_dorm_ordering_not_plan(self):
        # 测试 如果当前已经有前置位VIP干员在吃单回，则不会新增任务
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "夕", "令"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "火龙S黑角"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["红"].current_index = -1
        op_data.operators["夕"].resting_priority = "low"
        op_data.operators["红"].current_room = "meeting"
        op_data.operators["焰尾"].current_index = 2
        op_data.operators["焰尾"].current_room = "dormitory_1"
        check_dorm_ordering(tasks, op_data)

        # 如果VIP位已经被占用，则不会生成新任务
        self.assertEqual(1, len(tasks))
        # 验证第任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(1, len(tasks))
        # 验证第任务包宿舍+换班任务
        self.assertEqual(2, len(tasks[0].plan))

    def test_check_dorm_ordering_not_plan2(self):
        # 测试 如果当前已经有前置位VIP干员在吃单回，则不会新增任务
        task1 = SchedulerTask(
            time=datetime.now(),
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "夕", "Current"],
                "central": ["麒麟R夜刀", "Current", "Current", "Current", "Current"],
            },
            task_type=TaskTypes.SHIFT_OFF,
            meta_data="",
        )
        tasks = [task1]
        op_data = self.init_opdata()
        # 预设干员位置
        op_data.operators["红"].current_index = 2
        op_data.operators["红"].current_room = "dormitory_1"
        op_data.operators["夕"].resting_priority = "low"
        op_data.operators["红"].current_room = "meeting"
        check_dorm_ordering(tasks, op_data)

        # 如果VIP位已经被占用，则不会生成新任务
        self.assertEqual(2, len(tasks))
        # 验证第任务包含换班+宿舍任务
        self.assertEqual(2, len(tasks[0].plan))
        # 重复执行不会生成新的
        check_dorm_ordering(tasks, op_data)
        self.assertEqual(2, len(tasks))
        # 验证第任务包宿舍+换班任务
        self.assertEqual(2, len(tasks[0].plan))

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

        while res is not None and res.meta_data == "task1":
            task_time = res.time - timedelta(minutes=(2))
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
        return op_data
