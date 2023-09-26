from datetime import datetime
import unittest
from arknights_mower.utils.scheduler_task import scheduling, SchedulerTask, TaskTypes


class TestScheduling(unittest.TestCase):

    def test_adjust_two_orders(self):
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
        self.assertNotEqual(res, None)

    def test_adjust_time(self):
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
        self.assertEqual(tasks[2].plan["task"], "Task 4")
        self.assertEqual(res, None)
