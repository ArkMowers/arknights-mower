from datetime import datetime, timedelta
import unittest
from arknights_mower.utils.scheduler_task import scheduling, SchedulerTask, TaskTypes, find_next_task


class TestScheduling(unittest.TestCase):

    def test_adjust_two_orders(self):
        # 测试两个跑单任务被拉开
        task1 = SchedulerTask(time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 1"}, task_type=TaskTypes.RUN_ORDER)
        task2 = SchedulerTask(time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 2"})
        task3 = SchedulerTask(time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 3"})
        task4 = SchedulerTask(time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 4"}, task_type=TaskTypes.RUN_ORDER)
        task5 = SchedulerTask(time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 5"})
        tasks = [task1, task2, task3, task4, task5]
        res = scheduling(tasks,time_now=datetime.strptime("2023-09-19 09:01", "%Y-%m-%d %H:%M"))
        # 返还的是应该拉开跑单的任务
        self.assertNotEqual(res, None)

    def test_adjust_two_orders_fia(self):
        # 测试菲亚换班时间预设3分钟有效
        task1 = SchedulerTask(time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 1"})
        task2 = SchedulerTask(time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
                              task_plan={},task_type=TaskTypes.FIAMMETTA)
        task4 = SchedulerTask(time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 4"}, task_type=TaskTypes.RUN_ORDER)
        task5 = SchedulerTask(time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 5"})
        tasks = [task1, task2, task4, task5]
        res = scheduling(tasks,time_now=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"))
        # 跑单任务被提前
        self.assertEqual(tasks[0].type, TaskTypes.RUN_ORDER)

    def test_adjust_time(self):
        # 测试跑单任务被挤兑
        task1 = SchedulerTask(time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 1"}, task_type=TaskTypes.RUN_ORDER)
        task2 = SchedulerTask(time=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 2"})
        task3 = SchedulerTask(time=datetime.strptime("2023-09-19 10:02", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 3"})
        task4 = SchedulerTask(time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 4"}, task_type=TaskTypes.RUN_ORDER)
        task5 = SchedulerTask(time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 5"})
        tasks = [task1, task2, task3, task4, task5]
        res = scheduling(tasks,time_now=datetime.strptime("2023-09-19 10:01", "%Y-%m-%d %H:%M"))
        # 其他任务会被移送至跑单任务以后
        self.assertEqual(tasks[2].plan["task"], "Task 4")
        self.assertEqual(res, None)

    def test_find_next(self):
        # 测试 方程有效
        task1 = SchedulerTask(time=datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 1"}, task_type=TaskTypes.RUN_ORDER, meta_data="room")
        task4 = SchedulerTask(time=datetime.strptime("2023-09-19 10:03", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 4"}, task_type=TaskTypes.RUN_ORDER,meta_data="room")
        task5 = SchedulerTask(time=datetime.strptime("2023-09-19 10:30", "%Y-%m-%d %H:%M"),
                              task_plan={"task": "Task 5"})
        tasks = [task1, task4, task5]
        now = datetime.strptime("2023-09-19 10:00", "%Y-%m-%d %H:%M")
        res1 = find_next_task(tasks, now + timedelta(minutes=5),
                                                                    task_type=TaskTypes.RUN_ORDER,
                                                                    meta_data="room", compare_type=">")
        res2 = find_next_task(tasks, now + timedelta(minutes=-60),
                                                                    task_type=TaskTypes.RUN_ORDER,
                                                                    meta_data="room", compare_type=">")
        self.assertEqual(res1, None)
        self.assertNotEqual(res2, None)
