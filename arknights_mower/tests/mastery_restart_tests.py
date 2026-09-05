"""Cold-start mastery recovery using persisted plans and an empty task queue."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.solvers import record
from arknights_mower.utils import mastery_db
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
            patch.object(server, "log_lines", []),
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
