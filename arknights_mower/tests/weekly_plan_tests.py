import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from arknights_mower.utils.config.weekly_plan_loader import WeeklyPlanManager


def _activity_stage(stage_id: str, end: int) -> dict:
    return {
        "id": stage_id,
        "stageType": "ACTIVITY",
        "endTs": {"startTs": 100, "endTs": end},
    }


class WeeklyPlanManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = object.__new__(WeeklyPlanManager)

    def test_switches_to_bound_plan_after_activity_ends(self):
        plan = [{"weekday": "周一", "stage": ["ACT-1"]}]
        with (
            patch.object(self.manager, "get_active_plan_key", return_value="活动"),
            patch.object(
                self.manager,
                "get_activity_fallbacks",
                return_value={"活动": "常规"},
            ),
            patch.object(self.manager, "get_plan", return_value=plan),
            patch.object(self.manager, "_read_weekly_plans", return_value={}),
            patch.object(self.manager, "_write_weekly_plans"),
            patch.object(
                self.manager, "get_activity_fallback_switch_times", return_value={}
            ),
            patch.object(self.manager, "set_active_plan", return_value=True) as switch,
        ):
            result = self.manager.maybe_switch_expired_activity_plan(
                stages=[_activity_stage("ACT-1", 200)],
                now=200,
            )

        switch.assert_called_once_with("常规")
        self.assertEqual(
            result,
            {
                "source": "活动",
                "target": "常规",
                "activity_end_ts": 200,
                "switch_ts": 200,
            },
        )

    def test_keeps_activity_plan_before_detected_end_time(self):
        plan = [{"weekday": "周一", "stage": ["ACT-1"]}]
        with (
            patch.object(self.manager, "get_active_plan_key", return_value="活动"),
            patch.object(
                self.manager,
                "get_activity_fallbacks",
                return_value={"活动": "常规"},
            ),
            patch.object(self.manager, "get_plan", return_value=plan),
            patch.object(self.manager, "_read_weekly_plans", return_value={}),
            patch.object(self.manager, "_write_weekly_plans"),
            patch.object(
                self.manager, "get_activity_fallback_switch_times", return_value={}
            ),
            patch.object(self.manager, "set_active_plan", return_value=True) as switch,
        ):
            result = self.manager.maybe_switch_expired_activity_plan(
                stages=[_activity_stage("ACT-1", 200)],
                now=199,
            )

        switch.assert_not_called()
        self.assertIsNone(result)

    def test_uses_saved_end_time_after_activity_leaves_resource_overlay(self):
        plan = [{"weekday": "周一", "stage": ["ACT-1"]}]
        with (
            patch.object(self.manager, "get_active_plan_key", return_value="活动"),
            patch.object(
                self.manager,
                "get_activity_fallbacks",
                return_value={"活动": "常规"},
            ),
            patch.object(self.manager, "get_plan", return_value=plan),
            patch.object(
                self.manager,
                "_read_weekly_plans",
                return_value={"activity_fallback_end_times": {"活动": 200}},
            ),
            patch.object(
                self.manager, "get_activity_fallback_switch_times", return_value={}
            ),
            patch.object(self.manager, "set_active_plan", return_value=True) as switch,
        ):
            result = self.manager.maybe_switch_expired_activity_plan(stages=[], now=201)

        switch.assert_called_once_with("常规")
        self.assertEqual(result["activity_end_ts"], 200)

    def test_custom_switch_time_overrides_detected_activity_end(self):
        plan = [{"weekday": "周一", "stage": ["ACT-1"]}]
        with (
            patch.object(self.manager, "get_active_plan_key", return_value="活动"),
            patch.object(
                self.manager,
                "get_activity_fallbacks",
                return_value={"活动": "常规"},
            ),
            patch.object(self.manager, "get_plan", return_value=plan),
            patch.object(self.manager, "_read_weekly_plans", return_value={}),
            patch.object(self.manager, "_write_weekly_plans"),
            patch.object(
                self.manager,
                "get_activity_fallback_switch_times",
                return_value={"活动": 300},
            ),
            patch.object(self.manager, "set_active_plan", return_value=True) as switch,
        ):
            before = self.manager.maybe_switch_expired_activity_plan(
                stages=[_activity_stage("ACT-1", 200)],
                now=250,
            )
            after = self.manager.maybe_switch_expired_activity_plan(
                stages=[_activity_stage("ACT-1", 200)],
                now=301,
            )

        self.assertIsNone(before)
        switch.assert_called_once_with("常规")
        self.assertEqual(after["activity_end_ts"], 200)
        self.assertEqual(after["switch_ts"], 300)

    def test_server_clock_offset_corrects_device_time(self):
        from arknights_mower.utils import skland

        with (
            patch(
                "arknights_mower.utils.config.weekly_plan_loader.time.time",
                return_value=100,
            ),
            patch.object(skland, "server_time_offset", 25),
        ):
            self.assertEqual(self.manager._current_server_timestamp(), 125)

    def test_saved_end_time_switches_persisted_active_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "plans": {
                            "活动": [{"weekday": "周一", "stage": ["ACT-1"]}],
                            "常规": [{"weekday": "周一", "stage": ["1-7"]}],
                        },
                        "activity_fallbacks": {"活动": "常规"},
                        "activity_fallback_end_times": {"活动": 200},
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            state = {"active_weekly_plan": "活动"}
            with (
                patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path),
                patch.object(
                    self.manager, "_read_state", side_effect=lambda: dict(state)
                ),
                patch.object(self.manager, "_write_state", side_effect=state.update),
                patch.object(
                    self.manager, "sync_active_plan_to_config", return_value=True
                ) as sync,
            ):
                result = self.manager.maybe_switch_expired_activity_plan(
                    stages=[], now=201
                )

            self.assertEqual(state["active_weekly_plan"], "常规")
            sync.assert_called_once_with("常规")
            self.assertEqual(result["target"], "常规")

    def test_activity_fallback_binding_is_persisted_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            path.write_text(
                yaml.safe_dump(
                    {"plans": {"活动": [], "常规": []}},
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path):
                with patch.object(
                    self.manager,
                    "_activity_end_ts_for_plan_data",
                    return_value=200,
                ):
                    self.assertTrue(self.manager.set_activity_fallback("活动", "常规"))
                self.assertEqual(
                    self.manager.get_activity_fallbacks(), {"活动": "常规"}
                )
                self.assertEqual(
                    yaml.safe_load(path.read_text("utf-8"))[
                        "activity_fallback_end_times"
                    ],
                    {"活动": 200},
                )
                self.assertTrue(self.manager.set_activity_fallback("活动", ""))
                self.assertEqual(self.manager.get_activity_fallbacks(), {})

    def test_custom_switch_time_can_reset_to_activity_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            path.write_text(
                yaml.safe_dump(
                    {"plans": {"活动": [], "常规": []}},
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path),
                patch.object(
                    self.manager,
                    "_activity_end_ts_for_plan_data",
                    return_value=200,
                ),
            ):
                self.assertTrue(
                    self.manager.set_activity_fallback("活动", "常规", switch_time=250)
                )
                self.assertEqual(
                    self.manager.get_activity_fallback_switch_times(), {"活动": 250}
                )
                self.assertEqual(
                    self.manager.get_activity_plan_end_times(),
                    {"活动": 200, "常规": 200},
                )
                self.assertTrue(
                    self.manager.set_activity_fallback("活动", "常规", switch_time=None)
                )
                self.assertEqual(self.manager.get_activity_fallback_switch_times(), {})
                self.assertEqual(
                    yaml.safe_load(path.read_text("utf-8"))[
                        "activity_fallback_end_times"
                    ],
                    {"活动": 200},
                )

    def test_single_plan_exposes_detected_activity_end_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            path.write_text(
                yaml.safe_dump(
                    {"plans": {"活动": []}},
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path),
                patch.object(
                    self.manager,
                    "_activity_end_ts_for_plan_data",
                    return_value=200,
                ),
            ):
                self.assertEqual(
                    self.manager.get_activity_plan_end_times(), {"活动": 200}
                )

    def test_plan_update_preserves_cached_end_when_activity_data_disappears(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "plans": {"活动": [], "常规": []},
                        "activity_fallbacks": {"活动": "常规"},
                        "activity_fallback_end_times": {"活动": 200},
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path),
                patch.object(
                    self.manager,
                    "_activity_end_ts_for_plan_data",
                    return_value=None,
                ),
                patch.object(self.manager, "set_active_plan", return_value=True),
            ):
                self.assertTrue(self.manager.create_or_update_plan("活动", []))

            self.assertEqual(
                yaml.safe_load(path.read_text("utf-8"))["activity_fallback_end_times"],
                {"活动": 200},
            )


if __name__ == "__main__":
    unittest.main()
