"""Cold-start mastery recovery using persisted plans and an empty task queue."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.solvers import base_schedule, record
from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils import mastery_db, mastery_support_data
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class MasteryRestartTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db_path = folder / "data.db"

        def get_path(value):
            return self.db_path if value.endswith("data.db") else folder

        self.enterContext(patch.object(mastery_db, "get_path", side_effect=get_path))
        self.enterContext(patch.object(record, "get_path", side_effect=get_path))
        self.enterContext(patch.object(record, "_tables_created", False))
        self.addCleanup(mastery_db._tables_created.discard, str(self.db_path))
        self.enterContext(patch.object(reader.config.conf, "enable_mastery", True))
        self.enterContext(
            patch.object(reader.config.conf, "assistant_follows_schedule", False)
        )
        # Deterministic route and skill inputs; persistence and scheduling stay real.
        self.enterContext(patch.object(reader, "resolve_panel_skill", return_value=1))
        self.plan_id = mastery_db.insert_plan(
            "char_fixture", 1, 3, char_name="测试干员", skill_name="二技能·测试技能"
        )
        self.solver = SimpleNamespace(tasks=[], task=None)
        self.room = reader.RoomState(
            state="training",
            panel=reader.RoomPanel(
                operator_name="测试干员",
                skill_name="测试技能",
                mastery_tier=2,
                countdown=datetime.now() + timedelta(hours=8),
                countdown_state="active",
            ),
        )

    def plan(self):
        return mastery_db.get_plan_by_id(self.plan_id)

    def assert_one_task(self, task_type):
        self.assertEqual(len(self.solver.tasks), 1)
        task = self.solver.tasks[0]
        self.assertEqual(task.type, task_type)
        self.assertEqual(task.plan_key, str(self.plan_id))
        return task

    def test_reset_route_preserves_plan_and_scan_redispatches_once(self):
        import server
        from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

        before = self.plan()
        with (
            patch.object(server, "active_job", return_value=False),
            patch.object(server, "_job_running", return_value=False),
            patch.object(server, "mower_thread", None),
            patch.object(server, "log_stream"),
            patch.object(server, "get_path", return_value=self.db_path.parent),
            patch.object(server.config, "stop_mower"),
            patch.object(server, "load_state", side_effect=ValueError("old snapshot")),
            patch.object(server, "Thread") as thread,
            patch.object(server, "set_mower_thread"),
        ):
            headers = {"token": getattr(server.app, "token", "")}
            response = server.app.test_client().get("/start/2", headers=headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            self.assertEqual(thread.call_args.kwargs["args"][0], {})
        self.assertEqual(self.plan(), before)
        confirmed = [{"char_id": "char_fixture", "skill_index": 1, "current_level": 0}]
        for _ in range(2):
            BaseSchedulerSolver._dispatch_scan_start_tasks(self.solver, confirmed)
        task = self.assert_one_task(TaskTypes.SKILL_UPGRADE)
        self.assertEqual(task.step_level, 1)
        self.assertEqual(self.plan()["status"], "idle")

    def test_training_recreates_collection_from_room_countdown(self):
        mastery_db.update_plan_status(self.plan_id, "training", swap_frozen=1)
        for _ in range(2):
            reader.reconcile_short(self.solver, self.room)
        task = self.assert_one_task(TaskTypes.SKILL_UPGRADE)
        self.assertEqual(task.time, self.room.panel.countdown)
        self.assertEqual(self.plan()["status"], "training")
        self.assertEqual(
            self.plan()["expires_at"], task.time.strftime("%Y-%m-%d %H:%M:%S")
        )

    def test_training_recreates_support_swap_once(self):
        mastery_db.update_plan_status(self.plan_id, "training")
        route = {
            "operator": "协助干员",
            "swap_target": "艾丽妮",
            "efficiency": 0.3,
            "job_match": True,
        }
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route", return_value=route
            ),
            patch.object(
                reader,
                "_read_slots_checked",
                return_value=("协助干员", "测试干员", [], True),
            ),
        ):
            for _ in range(2):
                reader.reconcile_short(self.solver, self.room)
        self.assert_one_task(TaskTypes.SWAP_SUPPORT)
        self.assertEqual(self.plan()["status"], "training")

    def mood_solver(self, count=None):
        solver = MagicMock()
        solver.task = None
        solver.tasks = []
        solver.last_train_mood_read = None
        names = ["协助干员", "测试干员"][: count or 0]
        solver.op_data.plan = (
            {}
            if count is None
            else {"train": [SimpleNamespace(agent=name) for name in names]}
        )
        solver.op_data.operators = {}
        solver.op_data.get_current_room.return_value = ["协助干员", "测试干员"]
        solver.op_data.has_dorm_groups.return_value = False
        return solver

    def read_mood(self, solver):
        from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

        return BaseSchedulerSolver.agent_get_mood(solver, skip_dorm=True)

    def test_mood_scan_recovers_collection_for_all_roster_sizes_and_tiers(self):
        for count in (None, 0, 1, 2):
            for tier in (1, 2, 3):
                with self.subTest(count=count, tier=tier):
                    mastery_db.update_plan_status(
                        self.plan_id, "training", swap_frozen=1
                    )
                    self.room.panel.mastery_tier = tier
                    solver = self.mood_solver(count)
                    with patch.object(
                        reader, "read_room_state", return_value=(self.room, [])
                    ) as read:
                        self.read_mood(solver)
                        self.read_mood(solver)
                    read.assert_called_once_with(solver, enter=False, want_mood=True)
                    self.assertEqual(len(solver.tasks), 1)
                    self.assertEqual(solver.tasks[0].type, TaskTypes.SKILL_UPGRADE)
                    self.assertEqual(solver.tasks[0].time, self.room.panel.countdown)
                    self.assertEqual(solver.tasks[0].plan_key, str(self.plan_id))

    def test_mood_scan_recovers_swap_from_idle_and_failed_without_roster(self):
        route = {
            "operator": "协助干员",
            "swap_target": "艾丽妮",
            "efficiency": 0.3,
            "job_match": True,
        }
        for status in ("idle", "failed"):
            with self.subTest(status=status):
                mastery_db.update_plan_status(self.plan_id, status)
                solver = self.mood_solver()
                with (
                    patch.object(
                        reader, "read_room_state", return_value=(self.room, [])
                    ),
                    patch(
                        "arknights_mower.solvers.mastery._get_plan_route",
                        return_value=route,
                    ),
                    patch.object(
                        reader,
                        "_read_slots_checked",
                        return_value=("协助干员", "测试干员", [], True),
                    ),
                ):
                    self.read_mood(solver)
                self.assertEqual(self.plan()["status"], "training")
                self.assertEqual(len(solver.tasks), 1)
                self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)

    def test_mood_scan_collects_finished_training_without_roster(self):
        mastery_db.update_plan_status(self.plan_id, "waiting_collect")
        self.room.state = "waiting_collect"
        self.room.panel.mastery_tier = 3
        self.room.panel.countdown_state = "zero"
        self.room.panel.countdown = None
        solver = self.mood_solver()
        with (
            patch.object(reader, "read_room_state", return_value=(self.room, [])),
            patch.object(reader, "collect_flow") as collect,
            patch.object(reader, "_tap_collect_confirm"),
        ):
            self.read_mood(solver)
        collect.assert_called_once()
        self.assertEqual(self.plan()["status"], "completed")
        self.assertEqual(solver.tasks, [])

    def test_empty_or_failed_mood_read_is_throttled_and_later_rechecked(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                mastery_db.update_plan_status(self.plan_id, "idle")
                self.room.state = "empty"
                solver = self.mood_solver()
                with patch.object(
                    reader,
                    "read_room_state",
                    return_value=(self.room, []),
                    side_effect=ValueError("OCR") if failed else None,
                ) as read:
                    self.read_mood(solver)
                    self.read_mood(solver)
                    self.assertEqual(read.call_count, 1)
                    solver.last_train_mood_read -= timedelta(hours=3)
                    self.read_mood(solver)
                    self.assertEqual(read.call_count, 2)
                self.assertEqual(solver.tasks, [])
                self.assertEqual(self.plan()["status"], "idle")

    def test_mood_scan_checks_training_room_without_plan_or_mastery(self):
        mastery_db.update_plan_status(self.plan_id, "completed")
        empty_room = reader.RoomState(state="empty", slots_reliable=True)
        with (
            patch.object(
                reader, "read_room_state", return_value=(empty_room, [])
            ) as read,
            patch.object(reader, "reconcile_short"),
        ):
            self.read_mood(self.mood_solver())
        read.assert_called_once()

        solver = self.mood_solver()
        solver.get_agent_from_room.return_value = [
            {"agent": "", "mood": -1},
            {"agent": "", "mood": -1},
        ]
        with patch.object(reader.config.conf, "enable_mastery", False):
            self.read_mood(solver)
        solver.get_agent_from_room.assert_called_once_with("train", None)

    def test_cached_mood_projection_does_not_scan_training_room(self):
        for enabled in (False, True):
            with self.subTest(enable_mastery=enabled):
                solver = self.mood_solver()
                with (
                    patch.object(reader.config.conf, "enable_mastery", enabled),
                    patch.object(reader, "read_room_state") as read,
                ):
                    plan = base_schedule.BaseSchedulerSolver.agent_get_mood(
                        solver, skip_dorm=True, read_rooms=False, return_plan=True
                    )
                self.assertEqual(plan, {})
                read.assert_not_called()
                solver.enter_room.assert_not_called()
                solver.get_agent_from_room.assert_not_called()
                solver.back.assert_not_called()
                self.assertIsNone(solver.last_train_mood_read)
                self.assertEqual(solver.tasks, [])

    def test_mood_scan_stops_when_manual_trainee_is_in_nontraining_schedule(self):
        mastery_db.update_plan_status(self.plan_id, "completed")
        room = reader.RoomState(
            state="training",
            panel=reader.RoomPanel(operator_name="面板干员"),
            train_slot="测试干员",
            slots_reliable=True,
        )
        stop = Event()
        with (
            patch.object(reader, "read_room_state", return_value=(room, [])),
            patch.object(reader, "reconcile_short") as reconcile,
            patch.object(
                mastery_support_data,
                "trainee_schedule_conflict",
                return_value="测试干员 出现在非训练室排班（room_1_1），不能进行专精训练",
            ) as conflict,
            patch.object(base_schedule.config, "stop_mower", stop),
            patch.object(base_schedule, "send_message") as notify,
            patch.object(record, "save_current_state") as save,
        ):
            solver = self.mood_solver()
            solver.back.side_effect = lambda: self.assertFalse(stop.is_set())
            with self.assertRaises(MowerExit):
                self.read_mood(solver)
        self.assertTrue(stop.is_set())
        conflict.assert_called_once_with("测试干员")
        notify.assert_called_once()
        self.assertIn("已停止 Mower", notify.call_args.args[0])
        solver.back.assert_called_once_with()
        save.assert_called_once_with()
        reconcile.assert_not_called()

    def test_mood_scan_does_not_stop_on_failed_room_read(self):
        solver = self.mood_solver()
        with (
            patch.object(
                reader, "_settle_in_room", return_value=reader.Scene.TRAIN_MAIN
            ),
            patch.object(
                reader,
                "read_main_panel",
                return_value=reader.RoomPanel(operator_name="测试干员"),
            ),
            patch.object(reader, "_classify_panel", return_value="ocr_fail"),
            patch.object(reader, "reconcile_short"),
            patch.object(mastery_support_data, "trainee_schedule_conflict") as conflict,
        ):
            self.read_mood(solver)
        conflict.assert_not_called()
        self.assertTrue(solver.train_room_state.read_failed)
        solver.back.assert_called_once_with()

    def test_mood_scan_closes_detail_before_stop_when_mastery_disabled(self):
        solver = self.mood_solver()
        solver.get_agent_from_room.return_value = [
            {"agent": "协助干员", "mood": 24},
            {"agent": "测试干员", "mood": 24},
        ]
        stop = Event()
        solver.back.side_effect = lambda: self.assertFalse(stop.is_set())
        with (
            patch.object(reader.config.conf, "enable_mastery", False),
            patch.object(
                mastery_support_data,
                "trainee_schedule_conflict",
                return_value="测试干员 出现在非训练室排班（room_1_1）",
            ) as conflict,
            patch.object(base_schedule.config, "stop_mower", stop),
            patch.object(base_schedule, "send_message"),
            patch.object(record, "save_current_state"),
        ):
            with self.assertRaises(MowerExit):
                self.read_mood(solver)
        conflict.assert_called_once_with("测试干员")
        self.assertEqual(solver.back.call_count, 2)
        self.assertTrue(stop.is_set())

    def test_finished_training_is_collected_with_empty_queue(self):
        mastery_db.update_plan_status(self.plan_id, "waiting_collect")
        self.room.state = "waiting_collect"
        self.room.panel.mastery_tier = 3
        self.room.panel.countdown_state = "zero"
        self.room.panel.countdown = None
        # Mock only device actions; the reconciliation and DB completion are real.
        with (
            patch.object(reader, "collect_flow") as collect,
            patch.object(reader, "_tap_collect_confirm") as confirm,
        ):
            self.assertTrue(
                reader.reconcile_short(self.solver, self.room, defer_collect=True)
            )
        collect.assert_called_once()
        confirm.assert_called_once()
        self.assertEqual(self.plan()["status"], "completed")
        self.assertEqual(self.solver.tasks, [])

    def test_unreadable_room_preserves_plan_until_next_read(self):
        mastery_db.update_plan_status(self.plan_id, "training")
        before = self.plan()
        self.room.panel.operator_name = ""
        self.room.panel.skill_name = ""
        reader.reconcile_short(self.solver, self.room)
        self.assertEqual(self.plan(), before)
        self.assertEqual(self.solver.tasks, [])

    def test_mood_reload_keeps_only_fresh_mastery_tasks(self):
        import arknights_mower.__main__ as entry

        mastery_db.update_plan_status(self.plan_id, "training", swap_frozen=1)
        reader.reconcile_short(self.solver, self.room)
        collect = self.assert_one_task(TaskTypes.SKILL_UPGRADE)
        swap = SchedulerTask(time=collect.time, task_type=TaskTypes.SWAP_SUPPORT)
        swap.plan_key = "another-plan"
        shift = SchedulerTask(time=collect.time, task_type=TaskTypes.SHIFT_ON)
        fresh_state = {"tasks": [collect, swap, shift], "operators": {"fresh": "mood"}}
        # The first simulate run writes the new snapshot after re-reading rooms.
        simulate = MagicMock()

        def run(saved, restart_after_mood_read=False):
            if restart_after_mood_read:
                self.assertIsNone(saved)
                self.assertTrue(record.save_state_to_db(fresh_state))
                return "restart_after_mood_read"

        simulate.side_effect = run
        with (
            patch.object(entry.rapidocr, "initialize_ocr"),
            patch.object(entry, "simulate", simulate),
        ):
            entry._main({}, restart_after_mood_read=True)
        restored = simulate.call_args.args[0]
        self.assertEqual(
            [task.type for task in restored["tasks"]],
            [TaskTypes.SKILL_UPGRADE, TaskTypes.SWAP_SUPPORT],
        )
        self.assertEqual(
            [task.plan_key for task in restored["tasks"]],
            [str(self.plan_id), "another-plan"],
        )
        self.assertEqual(restored["operators"], fresh_state["operators"])
        self.assertEqual(self.plan()["status"], "training")
