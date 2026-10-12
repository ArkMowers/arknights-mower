"""Offline admission regressions for INV-SCHED-36."""

import copy
import unittest
from collections import defaultdict, deque
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from arknights_mower.utils import config, operation_timing
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    estimate_task_duration,
    independent_room_plans,
    scheduling,
)


@patch(
    "arknights_mower.utils.scheduler_task.NewsChecker.get_update_time",
    return_value=(None, None),
)
class TestSchedulingRoomPlans(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(operation_timing, "_dorm_durations", {}))
        self.enterContext(patch.object(operation_timing, "_work_durations", {}))
        self.enterContext(patch.object(config.conf, "enable_mastery", False))
        self.enterContext(
            patch.object(config.conf.run_order_grandet_mode, "enable", True)
        )

    now = datetime(2026, 10, 8, 10, 36, 9)

    def make_task(self, plan, seconds=0, task_type=TaskTypes.SHIFT_ON):
        return SchedulerTask(
            time=self.now + timedelta(seconds=seconds),
            task_plan=plan,
            task_type=task_type,
        )

    def make_op_data(self, current, targets=(), groups=None):
        groups = groups or {}
        data = object.__new__(Operators)
        data.plan = {
            room: [Room(name, groups.get(name, ""), []) for name in names]
            for room, names in current.items()
        }
        data.operators = {
            name: Operator(
                name,
                room,
                index=index,
                current_room=room,
                current_index=index,
                group=groups.get(name, ""),
            )
            for room, names in current.items()
            for index, name in enumerate(names)
        }
        for name in targets:
            data.operators.setdefault(
                name, Operator(name, "", group=groups.get(name, ""))
            )
        data.groups = {}
        data.group_shift_state = {}
        data.dorm = []
        data.group_dorm = []
        data.backup_plans = []
        data.run_order_rooms = {}
        return data

    def test_duration_uses_room_kind_and_actual_roster(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "dormitory_1": ["B"], "dormitory_2": ["C"]}
        )
        task = self.make_task(
            {"room_1_1": ["D"], "dormitory_1": ["E"], "dormitory_2": ["C"]}
        )
        self.assertEqual(
            estimate_task_duration(task, op_data=data), timedelta(seconds=235)
        )
        self.assertEqual(
            estimate_task_duration(task, execution_time=0.75), timedelta(seconds=225)
        )
        self.assertEqual(
            estimate_task_duration(self.make_task({"dormitory_1": ["Current"]})),
            timedelta(seconds=100),
        )

    def test_independent_rooms_are_split_without_losing_plan(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
        )
        task = self.make_task({"room_1_1": ["C"], "room_1_2": ["D"]})
        order = self.make_task({}, seconds=85, task_type=TaskTypes.RUN_ORDER)
        tasks = [task, order]

        scheduling(tasks, time_now=self.now, op_data=data)

        self.assertIs(tasks[0], task)
        self.assertEqual(task.plan, {"room_1_1": ["C"]})
        self.assertIs(tasks[1], order)
        remainder = tasks[2]
        self.assertEqual(remainder.plan, {"room_1_2": ["D"]})
        self.assertEqual(remainder.type, task.type)
        self.assertFalse(remainder.adjusted)
        self.assertEqual(remainder.time, order.time + timedelta(seconds=1))
        scheduling(tasks, time_now=self.now, op_data=data)
        self.assertEqual(len(tasks), 3)
        self.assertEqual(data.get_current_room("room_1_1"), ["A"])

    def test_operator_moves_and_groups_are_atomic(self, _get_update_time):
        cases = (
            (
                {"room_1_1": ["A"], "room_1_2": ["B"]},
                {"room_1_1": ["B"], "room_1_2": ["A"]},
                {},
            ),
            (
                {"room_1_1": ["A"], "room_1_2": ["B"]},
                {"room_1_1": ["C"], "room_1_2": ["D"]},
                {"C": "group", "D": "group"},
            ),
            (
                {"room_1_1": ["A"], "dormitory_1": ["B"]},
                {"room_1_1": ["C"], "dormitory_1": ["A"]},
                {},
            ),
        )
        for current, plan, groups in cases:
            with self.subTest(plan=plan, groups=groups):
                data = self.make_op_data(current, targets=("C", "D"), groups=groups)
                task = self.make_task(plan)
                order = self.make_task({}, seconds=85, task_type=TaskTypes.RUN_ORDER)
                tasks = [task, order]
                self.assertEqual(independent_room_plans(task, data), [plan])

                scheduling(tasks, time_now=self.now, op_data=data)

                self.assertEqual(len(tasks), 2)
                self.assertIs(tasks[0], order)
                self.assertEqual(task.plan, plan)

    def test_small_independent_component_can_run_before_large_group(
        self, _get_update_time
    ):
        data = self.make_op_data(
            {"dormitory_1": ["A"], "dormitory_2": ["B"], "room_1_1": ["E"]},
            targets=("C", "D", "F"),
            groups={"C": "group", "D": "group"},
        )
        task = self.make_task(
            {"dormitory_1": ["C"], "dormitory_2": ["D"], "room_1_1": ["F"]}
        )
        order = self.make_task({}, seconds=85, task_type=TaskTypes.RUN_ORDER)
        tasks = [task, order]

        scheduling(tasks, time_now=self.now, op_data=data)

        self.assertEqual(task.plan, {"room_1_1": ["F"]})
        self.assertEqual(tasks[2].plan, {"dormitory_1": ["C"], "dormitory_2": ["D"]})

    def test_unknown_roster_and_phase_tasks_are_not_split(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
        )
        plan = {"room_1_1": ["C"], "room_1_2": ["D"]}
        task = self.make_task(plan)
        with patch.object(data, "get_current_room", return_value=None):
            self.assertEqual(independent_room_plans(task, data), [plan])
        task.type = TaskTypes.RE_ORDER
        self.assertEqual(independent_room_plans(task, data), [plan])
        task.type = TaskTypes.SHIFT_OFF
        task.meta_data = "宿舍排序完成"
        self.assertEqual(independent_room_plans(task, data), [plan])

    def test_deferred_tasks_keep_their_dependency_order(self, _get_update_time):
        first = self.make_task({"room_1_1": ["A"]})
        second = self.make_task({"room_1_1": ["B"]})
        third = self.make_task({"room_1_1": ["Current"]})
        order = self.make_task({}, seconds=100, task_type=TaskTypes.RUN_ORDER)
        tasks = [first, second, third, order]

        scheduling(tasks, time_now=self.now)

        self.assertEqual(tasks, [first, order, second, third])
        self.assertEqual(first.time, self.now)
        self.assertEqual(second.time, order.time + timedelta(seconds=1))
        self.assertEqual(third.time, order.time + timedelta(seconds=2))

    def test_future_start_time_is_included(self, _get_update_time):
        task = self.make_task({"room_1_1": ["A"]}, seconds=100)
        order = self.make_task({}, seconds=130, task_type=TaskTypes.RUN_ORDER)
        tasks = [task, order]

        scheduling(tasks, time_now=self.now)

        self.assertIs(tasks[0], order)
        self.assertEqual(task.time, order.time + timedelta(seconds=1))

    def test_duration_accounts_for_previous_roster_changes(self, _get_update_time):
        data = self.make_op_data({"room_1_1": ["A"]}, targets=("B",))
        first = self.make_task({"room_1_1": ["B"]})
        second = self.make_task({"room_1_1": ["A"]})
        order = self.make_task({}, seconds=110, task_type=TaskTypes.RUN_ORDER)
        tasks = [first, second, order]

        scheduling(tasks, time_now=self.now, op_data=data)

        self.assertEqual(tasks, [first, order, second])
        self.assertEqual(second.time, order.time + timedelta(seconds=1))
        self.assertEqual(data.get_current_room("room_1_1"), ["A"])

    def test_splitting_accounts_for_previous_operator_moves(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "room_1_2": ["B"], "dormitory_1": ["D"]},
            targets=("C",),
        )
        first = self.make_task({"room_1_2": ["A"]})
        second = self.make_task({"room_1_2": ["C"], "dormitory_1": ["A"]})
        order = self.make_task({}, seconds=135, task_type=TaskTypes.RUN_ORDER)
        tasks = [first, second, order]

        scheduling(tasks, time_now=self.now, op_data=data)

        self.assertEqual(tasks, [first, order, second])
        self.assertEqual(len(second.plan), 2)
        self.assertEqual(data.operators["A"].current_room, "room_1_1")

    @patch("arknights_mower.utils.scheduler_task.config.conf.run_order_delay", 3)
    def test_deferred_backlog_is_checked_against_following_order(
        self, _get_update_time
    ):
        first = self.make_task({"room_1_1": ["A"], "room_1_2": ["B"]})
        order1 = self.make_task({}, seconds=100, task_type=TaskTypes.RUN_ORDER)
        second = self.make_task({"dormitory_1": ["Current"]}, seconds=110)
        order2 = self.make_task({}, seconds=410, task_type=TaskTypes.RUN_ORDER)
        tasks = [first, order1, second, order2]

        scheduling(tasks, time_now=self.now)

        self.assertEqual(tasks, [order1, order2, first, second])
        self.assertEqual(first.time, order2.time + timedelta(seconds=1))
        self.assertEqual(second.time, order2.time + timedelta(seconds=2))

    @patch("arknights_mower.utils.scheduler_task.config.conf.run_order_delay", 3)
    def test_previous_order_wait_and_restore_are_included(self, _get_update_time):
        previous = self.make_task({}, task_type=TaskTypes.RUN_ORDER)
        first = self.make_task({"room_1_1": ["A"]}, seconds=1)
        second = self.make_task({"room_1_2": ["B"]}, seconds=2)
        order = self.make_task({}, seconds=310, task_type=TaskTypes.RUN_ORDER)
        tasks = [previous, first, second, order]

        scheduling(tasks, time_now=self.now)

        self.assertEqual(tasks, [previous, first, order, second])
        self.assertEqual(first.time, self.now + timedelta(seconds=1))
        self.assertEqual(second.time, order.time + timedelta(seconds=1))

    @patch("arknights_mower.utils.scheduler_task.config.conf.run_order_delay", 3)
    @patch(
        "arknights_mower.utils.scheduler_task.config.conf.run_order_grandet_mode.enable",
        False,
    )
    def test_drone_order_does_not_reserve_grandet_wait(self, _get_update_time):
        previous = self.make_task({}, task_type=TaskTypes.RUN_ORDER)
        shift = self.make_task({"room_1_1": ["A"]}, seconds=1)
        order = self.make_task({}, seconds=180, task_type=TaskTypes.RUN_ORDER)
        tasks = [previous, shift, order]

        scheduling(tasks, time_now=self.now)

        self.assertEqual(tasks, [previous, shift, order])
        self.assertEqual(shift.time, self.now + timedelta(seconds=1))

    def test_pending_shifts_are_not_counted_repeatedly(self, _get_update_time):
        now = datetime(2026, 10, 8, 10, 36, 9)
        for available_seconds in (489, 420):
            for previous_order in (False, True):
                with self.subTest(
                    available_seconds=available_seconds, previous_order=previous_order
                ):
                    shifts = [
                        SchedulerTask(
                            time=now,
                            task_plan={
                                f"room_1_{room}": ["Current"] * 5
                                for room in range(1, 4)
                            },
                            task_type=task_type,
                        )
                        for task_type in (
                            TaskTypes.SHIFT_OFF,
                            TaskTypes.SHIFT_ON,
                            TaskTypes.SELF_CORRECTION,
                        )
                    ]
                    order = SchedulerTask(
                        time=now
                        + timedelta(
                            seconds=available_seconds + (90 if previous_order else 0)
                        ),
                        task_type=TaskTypes.RUN_ORDER,
                    )
                    tasks = shifts + [order]
                    if previous_order:
                        tasks.insert(
                            0,
                            SchedulerTask(
                                time=now - timedelta(minutes=10),
                                task_type=TaskTypes.RUN_ORDER,
                            ),
                        )

                    # 九个工作房间共 405 秒，另留 15 秒余量及前次跑单操作时间。
                    for _ in range(2):
                        self.assertIsNone(
                            scheduling(tasks, execution_time=0.75, time_now=now)
                        )
                        self.assertEqual([shift.time for shift in shifts], [now] * 3)
                        self.assertIs(tasks[-1], order)

    def test_pending_shifts_exceeding_order_time_are_delayed(self, _get_update_time):
        now = datetime(2026, 10, 8, 10, 36, 9)
        shifts = [
            SchedulerTask(
                time=now,
                task_plan={f"room_1_{room}": ["Current"] * 5 for room in range(1, 4)},
                task_type=TaskTypes.SHIFT_OFF,
            )
            for _ in range(3)
        ]
        order = SchedulerTask(
            time=now + timedelta(seconds=419),
            task_type=TaskTypes.RUN_ORDER,
        )
        tasks = shifts + [order]

        self.assertIsNone(scheduling(tasks, execution_time=0.75, time_now=now))

        # 先完成前两条任务，仅延后第三条。
        self.assertEqual([shift.time for shift in shifts[:2]], [now] * 2)
        self.assertIs(tasks[2], order)
        self.assertEqual(
            shifts[2].time,
            order.time + timedelta(seconds=1),
        )

    def test_work_no_change_and_observed_slowdown(self, _get_update_time):
        data = self.make_op_data({"room_1_1": ["A"]}, targets=("B",))
        unchanged = self.make_task({"room_1_1": ["A"]})
        assert estimate_task_duration(unchanged, op_data=data).total_seconds() == 25
        operation_timing._work_durations["room_1_1"] = deque([80])
        changed = self.make_task({"room_1_1": ["B"]})
        assert estimate_task_duration(changed, op_data=data).total_seconds() == 121
        assert data.get_current_room("room_1_1") == ["A"]

    def test_split_survives_fixed_task_and_repeated_scheduling(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
        )
        task = self.make_task({"room_1_1": ["C"], "room_1_2": ["D"]})
        order = self.make_task({}, seconds=85, task_type=TaskTypes.RUN_ORDER)
        fixed = self.make_task(
            {"dormitory_1": ["Free"]}, seconds=1000, task_type=TaskTypes.RELEASE_DORM
        )
        fixed.strict_mood_limit = True
        tasks = [task, order, fixed]
        scheduling(tasks, time_now=self.now, op_data=data)
        assert len(tasks) == 4
        remainder = next(t for t in tasks if t is not task and t.type == task.type)
        assert remainder.plan == {"room_1_2": ["D"]}
        assert any(t is fixed for t in tasks)
        remainder.plan["room_1_2"][0] = "B"
        assert task.plan == {"room_1_1": ["C"]}
        scheduling(tasks, time_now=self.now, op_data=data)
        assert len(tasks) == 4

    def test_multigroup_bindings_connect_room_components(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
        )
        data.operators["C"].group_bindings = [
            {"group": "first", "replacement": []},
            {"group": "shared", "replacement": []},
        ]
        data.operators["D"].group = "shared"
        task = self.make_task({"room_1_1": ["C"], "room_1_2": ["D"]})
        assert independent_room_plans(task, data) == [task.plan]
        tasks = [task, self.make_task({}, seconds=85, task_type=TaskTypes.RUN_ORDER)]
        scheduling(tasks, time_now=self.now, op_data=data)
        assert len(tasks) == 2
        assert tasks[1] is task

    def test_phase_and_backup_state_keep_complete_task(self, _get_update_time):
        data = self.make_op_data(
            {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
        )
        task = self.make_task({"room_1_1": ["C"], "room_1_2": ["D"]})
        for field, value in (
            ("group_shift_expected", {("room_1_1", 0): "C"}),
            ("dorm_recovery_restore", ["dormitory_1"]),
            ("backup_shift_intent", copy.deepcopy(task.plan)),
            ("return_window", {"deadline": self.now}),
        ):
            with self.subTest(field=field):
                setattr(task, field, value)
                assert independent_room_plans(task, data) == [task.plan]
                delattr(task, field)
        data.backup_plans = [object()]
        assert independent_room_plans(task, data) == [task.plan]
        data.backup_plans = []
        task.plan["room_1_2"] = ["Free"]
        assert independent_room_plans(task, data) == [task.plan]

    def test_adjusted_work_keeps_time_and_blocks_later_work(self, _get_update_time):
        first = self.make_task({"room_1_1": ["A"]})
        first.adjusted = True
        second = self.make_task({"room_1_2": ["B"]})
        order = self.make_task({}, seconds=70, task_type=TaskTypes.RUN_ORDER)
        tasks = [first, second, order]
        scheduling(tasks, time_now=self.now)
        assert first.time == self.now
        assert tasks == [first, order, second]

    def test_dynamic_task_invalidates_later_occupancy_estimates(self, _get_update_time):
        data = self.make_op_data({"room_1_1": ["A"]})
        dynamic = self.make_task({}, task_type=TaskTypes.FIAMMETTA)
        after = self.make_task({"room_1_1": ["A"]})
        order = self.make_task({}, seconds=230, task_type=TaskTypes.RUN_ORDER)
        tasks = [dynamic, after, order]
        scheduling(tasks, time_now=self.now, op_data=data)
        assert tasks == [dynamic, order, after]
        assert data.get_current_room("room_1_1") == ["A"]

    def test_distant_order_still_checks_admission(self, _get_update_time):
        large = self.make_task({f"room_{n}": ["A"] for n in range(20)})
        order = self.make_task({}, seconds=660, task_type=TaskTypes.RUN_ORDER)
        tasks = [large, order]
        scheduling(tasks, time_now=self.now)
        assert tasks == [order, large]


@pytest.mark.usefixtures("offline_maintenance")
def test_work_measurements_are_bounded_and_failures_do_not_change_estimate(monkeypatch):
    monkeypatch.setattr(
        operation_timing, "_work_durations", defaultdict(lambda: deque(maxlen=8))
    )
    clock = iter([0.0, 80.0, 90.0, 290.0])
    monkeypatch.setattr(operation_timing, "perf_counter", lambda: next(clock))

    @operation_timing.timed_room
    def arrange(room, fails=False):
        if fails:
            raise RuntimeError("room incomplete")

    arrange("room_1_1")
    assert operation_timing.estimate_work_minutes("room_1_1") == 111 / 60
    with pytest.raises(RuntimeError):
        arrange("room_1_1", fails=True)
    assert operation_timing.estimate_work_minutes("room_1_1") == 111 / 60
    samples = operation_timing._work_durations["room_1_1"]
    samples.extend(range(20))
    assert list(samples) == list(range(12, 20))
