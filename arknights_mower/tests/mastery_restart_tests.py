"""Cold-start mastery recovery using persisted plans and an empty task queue."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from arknights_mower.solvers import base_schedule, record
from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils import mastery_db, mastery_support_data
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class MasteryRestartTests(unittest.TestCase):
    def setUp(self):
        for method in ("get_maintenance", "get_daily_reset"):
            self.enterContext(patch.object(NewsChecker, method, return_value=None))
        self.enterContext(
            patch.object(base_schedule, "_training_room_scan_disabled", False)
        )
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
        self.enterContext(
            patch("arknights_mower.solvers.mastery._get_plan_route", return_value={})
        )
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

    def test_trusted_panel_with_unavailable_route_preserves_swap_intent(self):
        mastery_db.update_plan_status(self.plan_id, "training", swap_frozen=0)
        with patch(
            "arknights_mower.solvers.mastery._get_plan_route", return_value=None
        ):
            for _ in range(2):
                reader.reconcile_short(self.solver, self.room)
        task = self.assert_one_task(TaskTypes.SWAP_SUPPORT)
        self.assertTrue(task.mastery_swap_verify_only)
        self.assertLessEqual(task.time, datetime.now())
        self.assertEqual(self.plan()["status"], "training")
        self.assertEqual(self.plan()["swap_frozen"], 0)

    def test_unreadable_panel_and_route_preserve_one_swap_verification(self):
        mastery_db.update_plan_status(self.plan_id, "training", swap_frozen=0)
        room = reader.RoomState("training", read_failed=True)
        with patch(
            "arknights_mower.solvers.mastery._get_plan_route", return_value=None
        ):
            for _ in range(2):
                reader.reconcile_short(self.solver, room)
        task = self.assert_one_task(TaskTypes.SWAP_SUPPORT)
        self.assertTrue(task.mastery_swap_verify_only)
        self.assertEqual(self.plan()["status"], "training")
        self.assertEqual(self.plan()["swap_frozen"], 0)

    def test_reset_recovers_observed_training_from_each_persisted_status(self):
        for status in ("idle", "failed", "arranging", "training", "waiting_collect"):
            with self.subTest(status=status):
                mastery_db.update_plan_status(self.plan_id, status, swap_frozen=1)
                self.solver.tasks = []
                reader.reconcile_short(self.solver, self.room)
                self.assertEqual(self.plan()["status"], "training")
                task = self.assert_one_task(TaskTypes.SKILL_UPGRADE)
                self.assertEqual(task.time, self.room.panel.countdown)

    def test_reset_collects_each_finished_tier_and_requeues_unfinished_skill(self):
        for tier in (1, 2, 3):
            with self.subTest(tier=tier):
                mastery_db.update_plan_status(self.plan_id, "waiting_collect")
                self.solver.tasks = []
                self.room.state = "waiting_collect"
                self.room.panel.mastery_tier = tier
                self.room.panel.countdown_state = "zero"
                self.room.panel.countdown = None
                with (
                    patch.object(reader, "collect_flow") as collect,
                    patch.object(reader, "_tap_collect_confirm"),
                ):
                    self.assertTrue(reader.reconcile_short(self.solver, self.room))
                collect.assert_called_once()
                if tier < 3:
                    self.assertEqual(self.plan()["status"], "idle")
                    self.assert_one_task(TaskTypes.SKILL_UPGRADE)
                else:
                    self.assertEqual(self.plan()["status"], "completed")
                    self.assertEqual(self.solver.tasks, [])

    def test_deleted_training_is_observed_and_collected_without_resurrecting_plan(self):
        mastery_db.update_plan_status(self.plan_id, "training")
        self.assertTrue(mastery_db.delete_plan(self.plan_id))
        with patch.object(reader, "_notify_blocked"):
            reader.reconcile_short(self.solver, self.room)
        self.assertEqual(len(self.solver.tasks), 1)
        self.assertIsNone(self.solver.tasks[0].plan_key)
        self.assertIsNone(self.plan())
        self.solver.tasks = []
        self.room.state = "waiting_collect"
        self.room.panel.mastery_tier = 3
        with (
            patch.object(reader, "collect_flow") as collect,
            patch.object(reader, "_tap_collect_confirm"),
        ):
            reader.reconcile_short(self.solver, self.room)
        self.assertIsNone(collect.call_args.args[1])
        self.assertIsNone(self.plan())
        self.assertEqual(self.solver.tasks, [])

    def test_reset_restores_amiya_form_wait_and_later_correct_skill_releases_it(self):
        import numpy as np

        from arknights_mower.solvers import mastery
        from arknights_mower.utils import rapidocr

        pid = mastery_db.insert_plan(
            "char_1001_amiya2", 1, 3, char_name="阿米娅", skill_name="二技能·影霄·绝影"
        )
        pending = mastery_db.get_plan_by_id(pid)
        room = reader.RoomState(
            "empty", train_slot="阿米娅", support_slot="逻各斯", slots_reliable=True
        )
        old = MagicMock(tasks=[], task=None)
        with patch("arknights_mower.utils.email.send_message"):
            mastery._defer_amiya_form(old, pending, room, False)
        self.assertEqual(
            mastery_db.get_plan_by_id(pid)["failed_reason"],
            reader.AMIYA_FORM_WAIT_REASON,
        )
        fresh = MagicMock(tasks=[], task=None, amiya_pending_plan_id=None)
        fresh.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        fresh.train_scene.return_value = reader.Scene.TRAIN_SKILL_SELECT
        box = [(240, 526), (520, 526), (520, 561), (240, 561)]
        with (
            patch.object(
                reader, "_settle_in_room", return_value=reader.Scene.TRAIN_MAIN
            ),
            patch.object(
                reader,
                "read_main_panel",
                return_value=reader.RoomPanel(idle_marker=True),
            ),
            patch.object(
                reader,
                "_read_slots_checked",
                return_value=("逻各斯", "阿米娅", [], True),
            ),
            patch.object(reader, "_back_to_train_main", return_value=True),
            patch.object(reader, "_compute_protected", return_value=True),
            patch.object(
                rapidocr, "engine", return_value=([[box, "精神爆发", 0.99]], 0)
            ) as ocr,
            patch("arknights_mower.utils.email.send_message"),
        ):
            observed = reader.read_room_state(fresh)
            self.assertTrue(observed.amiya_form_waiting)
            self.assertEqual(fresh.amiya_pending_plan_id, pid)
            fresh.choose_train.assert_not_called()
            self.assertEqual(len(fresh.tasks), 1)
            ocr.return_value = ([[box, "影霄·绝影", 0.99]], 0)
            self.assertFalse(reader.read_room_state(fresh).amiya_form_waiting)
        self.assertIsNone(fresh.amiya_pending_plan_id)
        self.assertEqual(len(fresh.tasks), 1)
        self.assertEqual(fresh.tasks[0].plan_key, str(pid))
        self.assertEqual(mastery_db.get_plan_by_id(pid)["failed_reason"], "")

    def test_reset_preserves_recorded_halving_without_inventing_missing_work(self):
        from arknights_mower.solvers import mastery_support_runtime as runtime
        from arknights_mower.tests.mastery_support_fixtures import stat
        from arknights_mower.utils.mastery_support import StageSpec, stage_route

        for recorded in (False, True):
            with self.subTest(recorded=recorded):
                mastery_db.update_plan_status(self.plan_id, "idle")
                route = stage_route(stat("艾丽妮", 30, True), None, StageSpec(2, 16))
                route.update(working_operator="艾丽妮", working_halves=True)
                if recorded:
                    route["working_since"] = (
                        datetime.now() - timedelta(hours=6)
                    ).isoformat()
                self.assertTrue(
                    mastery_db.save_support_plan(self.plan_id, {"stages": [route]})
                )
                self.assertTrue(
                    mastery_db.save_support_plan(self.plan_id, route, runtime=True)
                )
                mastery_db.update_plan_status(self.plan_id, "training", swap_frozen=1)
                self.solver = SimpleNamespace(tasks=[], task=None)
                self.room.state = "training"
                self.room.panel.mastery_tier = 2
                self.room.panel.countdown_state = "active"
                self.room.slots_reliable = True
                self.room.support_slot = "艾丽妮"
                reader.reconcile_short(self.solver, self.room)
                self.assert_one_task(TaskTypes.SKILL_UPGRADE)
                self.solver.tasks = []
                self.room.state = "waiting_collect"
                self.room.panel.countdown_state = "zero"
                with (
                    patch.object(reader, "collect_flow"),
                    patch.object(reader, "_tap_collect_confirm"),
                ):
                    reader.reconcile_short(self.solver, self.room)
                carry = runtime._carried_halving(self.plan(), 3, ("艾丽妮", "测试干员"))
                self.assertEqual(carry, "艾丽妮" if recorded else None)
                self.assert_one_task(TaskTypes.SKILL_UPGRADE)

    def test_reset_retains_material_wait_boundary_until_selected_plan_resumes(self):
        mastery_db.update_plan_status(
            self.plan_id, "idle", failed_reason="材料不足", expires_at="2030-01-01"
        )
        other_id = mastery_db.insert_plan("other", 0, 3, char_name="其他干员")
        self.room.state = "empty"
        result, _ = reader._reconcile(
            self.solver,
            self.room,
            None,
            mastery_db.get_reconcile_plans(),
            scan_plan=mastery_db.get_plan_by_id(other_id),
        )
        self.assertIsNone(result)
        self.assertEqual(self.plan()["failed_reason"], "材料不足")
        result, _ = reader._reconcile(
            self.solver,
            self.room,
            None,
            mastery_db.get_reconcile_plans(),
            scan_plan=self.plan(),
        )
        self.assertEqual(result["id"], self.plan_id)

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

    def test_failed_panel_restores_legacy_swap_before_next_patrol(self):
        from arknights_mower.solvers import mastery

        expiry = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
        mastery_db.update_plan_status(self.plan_id, "training", expires_at=expiry)
        before = self.plan()
        solver = self.mood_solver()
        solver.find.return_value = None
        started = datetime.now()
        with (
            patch.object(
                reader, "_settle_in_room", return_value=reader.Scene.TRAIN_MAIN
            ),
            patch.object(reader, "read_main_panel", return_value=reader.RoomPanel()),
            patch.object(
                mastery,
                "_get_plan_route",
                side_effect=lambda plan, level: (
                    {"operator": "协助干员", "swap_target": "艾丽妮"}
                    if level == 2
                    else None
                ),
            ),
        ):
            self.read_mood(solver)
            reader.reconcile_short(solver, solver.train_room_state)
        self.assertTrue(solver.train_room_state.read_failed)
        self.assertEqual(len(solver.tasks), 1)
        task = solver.tasks[0]
        self.assertEqual(task.type, TaskTypes.SWAP_SUPPORT)
        self.assertEqual(task.plan_key, str(self.plan_id))
        self.assertGreaterEqual(task.time, started)
        self.assertLessEqual(task.time, datetime.now())
        self.assertEqual(self.plan(), before)
        solver.choose_train.assert_not_called()

    def test_unreadable_identity_restores_swap_without_inventing_deadline(self):
        mastery_db.update_plan_status(self.plan_id, "training")
        room = reader.RoomState("training")
        with patch(
            "arknights_mower.solvers.mastery._get_plan_route",
            return_value={"operator": "协助干员", "swap_target": "艾丽妮"},
        ):
            reader.reconcile_short(self.solver, room)
            reader.reconcile_short(self.solver, room)
        self.assert_one_task(TaskTypes.SWAP_SUPPORT)
        self.assertIsNone(self.plan()["expires_at"])
        self.assertFalse(self.plan()["swap_frozen"])

    def test_failed_panel_restores_confirmed_runtime_swap_deadline(self):
        from arknights_mower.tests.mastery_support_fixtures import stat
        from arknights_mower.utils.mastery_support import StageSpec, stage_route

        route = stage_route(
            stat("协助干员", 75), stat("艾丽妮", 30, True), StageSpec(2, 16)
        )
        route["working_operator"] = "协助干员"
        mastery_db.save_support_plan(self.plan_id, {"stages": [route]})
        mastery_db.save_support_plan(self.plan_id, route, runtime=True)
        expiry = (datetime.now() + timedelta(hours=8)).replace(microsecond=0)
        mastery_db.update_plan_status(
            self.plan_id, "training", expires_at=expiry.isoformat(sep=" ")
        )
        before = self.plan()
        room = reader.RoomState("training", read_failed=True)
        for _ in range(2):
            reader.reconcile_short(self.solver, room)
        task = self.assert_one_task(TaskTypes.SWAP_SUPPORT)
        self.assertLess(
            abs((task.time - expiry + timedelta(minutes=232.5)).total_seconds()), 1
        )
        self.assertEqual(self.plan(), before)

    def test_failed_panel_preserves_existing_swap_including_current_and_failures(self):
        mastery_db.update_plan_status(self.plan_id, "training")
        room = reader.RoomState("training", read_failed=True)
        for state in ("queued", "current", "execution_failure", "execution_retained"):
            with self.subTest(state=state):
                original_time = datetime.now() - timedelta(minutes=15)
                task = SchedulerTask(
                    time=original_time, task_type=TaskTypes.SWAP_SUPPORT
                )
                task.plan_key = str(self.plan_id)
                if state == "execution_failure":
                    task.execution_failure = {"reason": "读取失败"}
                elif state == "execution_retained":
                    task.execution_retained = True
                self.solver.tasks = [task]
                self.solver.task = task if state == "current" else None
                reader.reconcile_short(self.solver, room)
                self.assertEqual(len(self.solver.tasks), 1)
                self.assertIs(self.solver.tasks[0], task)
                self.assertEqual(task.time, original_time)

    def test_failed_panel_does_not_restart_confirmed_finished_swap(self):
        mastery_db.update_plan_status(self.plan_id, "training", swap_frozen=1)
        with patch(
            "arknights_mower.solvers.mastery._get_plan_route",
            return_value={"operator": "协助干员", "swap_target": "艾丽妮"},
        ):
            reader.reconcile_short(
                self.solver, reader.RoomState("training", read_failed=True)
            )
        self.assertEqual(self.solver.tasks, [])

    def test_retained_reader_tasks_keep_their_timestamp_after_observation(self):
        for task_type in (TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE):
            for state in ("execution_failure", "execution_retained"):
                with self.subTest(task_type=task_type, state=state):
                    original_time = datetime.now() - timedelta(hours=1)
                    task = SchedulerTask(time=original_time, task_type=task_type)
                    task.plan_key = str(self.plan_id)
                    setattr(
                        task,
                        state,
                        {"reason": "读取失败"}
                        if state == "execution_failure"
                        else True,
                    )
                    self.solver.tasks = [task]
                    if task_type == TaskTypes.SWAP_SUPPORT:
                        reader._upsert_swap_task_now(
                            self.solver, self.plan(), "协助干员"
                        )
                    else:
                        reader._schedule_collect(
                            self.solver, self.plan(), datetime.now()
                        )
                    self.assertIs(self.solver.tasks[0], task)
                    self.assertEqual(task.time, original_time)

    def test_countdown_and_safe_panel_propagate_interruption(self):
        for error_type in (MowerExit, DeviceRecoveryError):
            for read in (reader._read_train_countdown3, reader._safe_read_panel):
                with self.subTest(error_type=error_type, read=read):
                    solver = MagicMock()
                    solver.read_time.side_effect = error_type("interrupted")
                    solver.recog.update.side_effect = error_type("interrupted")
                    with self.assertRaises(error_type):
                        read(solver)

    def test_only_successful_current_panel_releases_observation_failure(self):
        old = datetime.now() - timedelta(hours=1)
        for seconds in (None, 0, 3600):
            with self.subTest(seconds=seconds):
                solver = MagicMock(last_mastery_observation=old)
                solver.train_scene.return_value = reader.Scene.TRAIN_MAIN
                solver.find.return_value = None
                solver.read_time.return_value = seconds
                with (
                    patch.object(
                        reader,
                        "_read_panel_text",
                        return_value=reader.RoomPanel(
                            operator_name="测试干员", skill_name="测试技能"
                        ),
                    ),
                    patch.object(reader, "_count_lit_mastery_icons", return_value=2),
                ):
                    reader.read_main_panel(solver)
                if seconds is None:
                    self.assertEqual(solver.last_mastery_observation, old)
                else:
                    self.assertGreater(solver.last_mastery_observation, old)

    def test_confirmed_finish_banner_releases_failure_without_slot_reads(self):
        old = datetime.now() - timedelta(hours=1)
        solver = MagicMock(last_mastery_observation=old)
        with (
            patch.object(
                reader, "_settle_in_room", return_value=reader.Scene.TRAIN_FINISH
            ),
            patch.object(reader, "read_main_panel", return_value=None),
            patch.object(reader, "_read_slots_checked") as slots,
        ):
            room = reader.read_room_state(solver)
        self.assertEqual(room.state, "waiting_collect")
        self.assertGreater(solver.last_mastery_observation, old)
        slots.assert_not_called()

    def test_explicit_panel_image_does_not_release_retained_execution(self):
        old = datetime.now() - timedelta(hours=1)
        solver = MagicMock(last_mastery_observation=old)
        solver.read_time.return_value = 3600
        with (
            patch.object(
                reader,
                "_read_panel_text",
                return_value=reader.RoomPanel(
                    operator_name="测试干员", skill_name="测试技能"
                ),
            ),
            patch.object(reader, "_count_lit_mastery_icons", return_value=2),
        ):
            reader.read_main_panel(solver, img=object())
        self.assertEqual(solver.last_mastery_observation, old)
        solver.recog.update.assert_not_called()

    def mood_solver(self, count=None):
        solver = MagicMock()
        solver._read_agent_mood = (
            base_schedule.BaseSchedulerSolver._read_agent_mood.__get__(solver)
        )
        solver._read_room_mood = (
            base_schedule.BaseSchedulerSolver._read_room_mood.__get__(solver)
        )
        solver.task = None
        solver.tasks = []
        solver.last_train_mood_read = None
        solver.last_train_mood_attempt = None
        solver.op_data.mood_calculation_enabled = False
        self.room.slots_read = self.room.slots_reliable = True
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

    def test_mood_scan_recovers_swap_from_trusted_panel_with_unreadable_slots(self):
        from arknights_mower.solvers import mastery

        mastery_db.update_plan_status(self.plan_id, "training")
        solver = self.mood_solver()
        route = {
            "operator": "协助干员",
            "swap_target": "艾丽妮",
            "efficiency": 75,
            "job_match": True,
            "central_bonus": 0,
            "mastery_swap_buffer": 10,
        }
        with (
            patch.object(
                reader, "_settle_in_room", return_value=reader.Scene.TRAIN_MAIN
            ),
            patch.object(reader, "read_main_panel", return_value=self.room.panel),
            patch.object(
                reader, "_read_slots_checked", return_value=("", "", [], False)
            ),
            patch.object(mastery, "_get_plan_route", return_value=route),
        ):
            self.read_mood(solver)

        observed = solver.train_room_state
        self.assertTrue(observed.slots_read)
        self.assertFalse(observed.slots_reliable)
        self.assertTrue(
            base_schedule.BaseSchedulerSolver._train_scheduling_protected(
                SimpleNamespace(
                    train_room_state=observed,
                    _train_mastery_active=lambda: False,
                    _train_protected=lambda: False,
                )
            )
        )
        self.assertIsNone(solver.last_train_mood_read)
        self.assertIsInstance(solver.last_train_mood_attempt, datetime)
        self.assertEqual(len(solver.tasks), 1)
        task = solver.tasks[0]
        self.assertEqual(task.type, TaskTypes.SWAP_SUPPORT)
        self.assertEqual(task.plan_key, str(self.plan_id))
        self.assertFalse(observed.read_failed)
        # 310 minutes at 135% replaces 232.5 minutes at the current 180% rate.
        expected = self.room.panel.countdown - timedelta(minutes=232.5)
        self.assertLess(abs((task.time - expected).total_seconds()), 1)
        self.assertEqual(self.plan()["status"], "training")

    def test_mood_scan_collects_finish_banner_without_reading_slots(self):
        mastery_db.update_plan_status(self.plan_id, "waiting_collect")
        panel = reader.RoomPanel(
            operator_name="测试干员",
            skill_name="测试技能",
            mastery_tier=3,
            countdown_state="zero",
        )
        solver = self.mood_solver()
        with (
            patch.object(
                reader, "_settle_in_room", return_value=reader.Scene.TRAIN_FINISH
            ),
            patch.object(reader, "read_main_panel", return_value=panel),
            patch.object(reader, "_read_slots_checked") as read_slots,
            patch.object(reader, "collect_flow") as collect,
            patch.object(reader, "_tap_collect_confirm") as confirm,
        ):
            self.read_mood(solver)

        observed = solver.train_room_state
        self.assertFalse(observed.slots_read)
        self.assertFalse(observed.slots_reliable)
        read_slots.assert_not_called()
        collect.assert_called_once_with(solver, ANY, panel)
        confirm.assert_called_once_with(solver)
        self.assertFalse(observed.read_failed)
        self.assertTrue(observed.collected)
        self.assertEqual(self.plan()["status"], "completed")
        self.assertEqual(solver.tasks, [])
        self.assertIsNone(solver.last_train_mood_read)
        self.assertIsInstance(solver.last_train_mood_attempt, datetime)

    def test_empty_and_failed_mood_scans_resume_at_normal_interval(self):
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
                    if failed:
                        self.assertIsNone(solver.last_train_mood_read)
                    else:
                        solver.last_train_mood_read -= timedelta(hours=3)
                    solver.last_train_mood_attempt -= timedelta(hours=3)
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
        with (
            patch.object(reader.config.conf, "enable_mastery", False),
            patch.object(reader, "read_room_state", return_value=empty_room),
            patch.object(reader, "reconcile_short") as reconcile,
        ):
            self.read_mood(solver)
        reconcile.assert_not_called()
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

    def test_unbuilt_training_room_disables_scan_for_entire_process(self):
        for enabled in (False, True):
            with (
                self.subTest(enabled=enabled),
                patch.object(base_schedule, "_training_room_scan_disabled", False),
            ):
                solver = self.mood_solver()
                solver.enter_room.side_effect = RuntimeError("未成功进入房间 train")
                with (
                    patch.object(reader.config.conf, "enable_mastery", enabled),
                    patch.object(reader, "read_room_state") as read,
                ):
                    self.read_mood(solver)
                    self.read_mood(solver)
                solver.enter_room.assert_called_once_with("train", max_attempts=1)
                solver.back_to_infrastructure.assert_called_once()
                solver.back.assert_not_called()
                read.assert_not_called()
                self.assertTrue(base_schedule._training_room_scan_disabled)
                self.assertEqual(solver.tasks, [])
                # 超过限频时间、进房恢复正常，也不再尝试。
                solver.last_train_mood_read = datetime.now() - timedelta(hours=3)
                solver.enter_room.side_effect = None
                solver.get_agent_from_room.return_value = []
                room = reader.RoomState(state="empty")
                with (
                    patch.object(reader.config.conf, "enable_mastery", enabled),
                    patch.object(
                        reader,
                        "read_room_state",
                        return_value=(room, []) if enabled else room,
                    ),
                    patch.object(reader, "reconcile_short"),
                ):
                    self.read_mood(solver)
                    restarted_solver = self.mood_solver()
                    self.read_mood(restarted_solver)
                    restarted_solver.enter_room.assert_not_called()
                solver.enter_room.assert_called_once_with("train", max_attempts=1)
                self.assertTrue(base_schedule._training_room_scan_disabled)

    def test_unavailable_training_does_not_block_other_rooms_or_create_correction(self):
        solver = self.mood_solver(count=2)
        op = SimpleNamespace(
            name="干员",
            room="meeting",
            need_to_refresh=lambda: True,
            current_room="meeting",
            time_stamp=None,
            not_valid=lambda: False,
        )
        solver.op_data.operators = {"干员": op}
        solver.op_data.plan["meeting"] = [SimpleNamespace(agent="干员")]
        solver.op_data.get_current_room.side_effect = lambda room, *args: (
            ["干员"] if room == "meeting" else ["", ""]
        )
        solver.op_data.true_exhaust_room = set()

        def enter(room, **kwargs):
            if room == "train":
                raise RuntimeError("未成功进入房间 train")

        solver.enter_room.side_effect = enter
        solver.get_agent_from_room.return_value = [{"agent": "干员", "mood": 12}]
        solver._suppress_train_correction.side_effect = lambda plan: (
            base_schedule.BaseSchedulerSolver._suppress_train_correction(solver, plan)
        )
        with patch.object(reader.config.conf, "enable_mastery", False):
            plan = base_schedule.BaseSchedulerSolver.agent_get_mood(
                solver, return_plan=True
            )
        solver.get_agent_from_room.assert_called_once_with("meeting", None)
        self.assertNotIn("train", plan)

    def test_mood_scan_leaves_protected_trainee_to_automatic_mastery(self):
        mastery_db.update_plan_status(self.plan_id, "completed")
        room = reader.RoomState(
            state="training",
            panel=reader.RoomPanel(operator_name="面板干员", countdown_state="active"),
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
            self.read_mood(solver)
        self.assertFalse(stop.is_set())
        conflict.assert_not_called()
        notify.assert_not_called()
        solver.back.assert_called_once_with()
        save.assert_not_called()
        reconcile.assert_called_once_with(solver, room, defer_collect=False)

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
            patch.object(reader, "read_room_state", return_value=self.room),
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

    def test_idle_finished_or_unreliable_trainee_does_not_stop_scheduling(self):
        for enabled in (False, True):
            for state, failed, countdown in (
                ("empty", False, "failed"),
                ("waiting_collect", False, "zero"),
                ("training", True, "active"),
                ("training", False, "failed"),
            ):
                with self.subTest(enabled=enabled, state=state, failed=failed):
                    solver = self.mood_solver()
                    moods = [
                        {"agent": "协助干员", "mood": 24},
                        {"agent": "测试干员", "mood": 24},
                    ]
                    solver.get_agent_from_room.return_value = moods
                    room = reader.RoomState(
                        state=state,
                        train_slot="测试干员",
                        panel=reader.RoomPanel(
                            operator_name="测试干员", countdown_state=countdown
                        ),
                        read_failed=failed,
                    )
                    stop = Event()
                    with (
                        patch.object(reader.config.conf, "enable_mastery", enabled),
                        patch.object(
                            reader,
                            "read_room_state",
                            return_value=(room, moods) if enabled else room,
                        ),
                        patch.object(reader, "reconcile_short") as reconcile,
                        patch.object(
                            mastery_support_data, "trainee_schedule_conflict"
                        ) as conflict,
                        patch.object(base_schedule.config, "stop_mower", stop),
                    ):
                        self.read_mood(solver)
                    conflict.assert_not_called()
                    self.assertFalse(stop.is_set())
                    if not enabled:
                        reconcile.assert_not_called()

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
