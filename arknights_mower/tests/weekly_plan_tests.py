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


def _inventory_config(stage: str, item_id: str, limit: int) -> dict:
    return {
        "enabled": True,
        "limit_rules": [
            {
                "stage": stage,
                "operator": "and",
                "enabled": True,
                "items": [
                    {
                        "item_id": item_id,
                        "item_name": item_id,
                        "limit": limit,
                    }
                ],
            }
        ],
        "ratio_rules": [],
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

    def test_legacy_inventory_rules_migrate_only_to_active_plan(self):
        data = {"plans": {"活动": [], "常规": []}}
        legacy = _inventory_config("ACT-1", "30012", 100)
        with (
            patch.object(
                self.manager, "_read_state", return_value={"active_weekly_plan": "活动"}
            ),
            patch.object(
                self.manager, "_runtime_inventory_config", return_value=legacy
            ),
        ):
            changed = self.manager._ensure_inventory_configs(data)

        self.assertTrue(changed)
        self.assertEqual(data["inventory_configs"]["活动"], legacy)
        self.assertEqual(
            data["inventory_configs"]["常规"],
            {"enabled": False, "limit_rules": [], "ratio_rules": []},
        )

    def test_inventory_rules_are_saved_independently_per_plan(self):
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
            activity = _inventory_config("ACT-1", "30012", 100)
            regular = _inventory_config("1-7", "30011", 300)
            with patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path):
                self.assertTrue(self.manager.set_inventory_config("活动", activity))
                self.assertTrue(self.manager.set_inventory_config("常规", regular))
                self.assertEqual(self.manager.get_inventory_config("活动"), activity)
                self.assertEqual(self.manager.get_inventory_config("常规"), regular)

            saved = yaml.safe_load(path.read_text("utf-8"))["inventory_configs"]
            self.assertEqual(saved["活动"], activity)
            self.assertEqual(saved["常规"], regular)

    def test_switching_plan_syncs_its_inventory_rules_to_runtime(self):
        from arknights_mower.utils import config

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            regular = _inventory_config("1-7", "30011", 300)
            path.write_text(
                yaml.safe_dump(
                    {
                        "plans": {"活动": [], "常规": []},
                        "inventory_configs": {
                            "活动": _inventory_config("ACT-1", "30012", 100),
                            "常规": regular,
                        },
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path),
                patch.object(config, "conf", config.Conf()),
            ):
                self.assertTrue(self.manager.sync_active_plan_to_config("常规"))
                self.assertTrue(config.conf.maa_stage_inventory_enable)
                self.assertEqual(
                    [rule.model_dump() for rule in config.conf.maa_stage_limit_rules],
                    regular["limit_rules"],
                )
                self.assertEqual(config.conf.maa_stage_ratio_rules, [])

    def test_deleting_plan_removes_its_inventory_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_plans.yml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "plans": {"活动": [], "常规": []},
                        "inventory_configs": {
                            "活动": _inventory_config("ACT-1", "30012", 100),
                            "常规": _inventory_config("1-7", "30011", 300),
                        },
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", path),
                patch.object(self.manager, "get_active_plan_key", return_value="活动"),
            ):
                self.assertTrue(self.manager.delete_plan("常规"))

            saved = yaml.safe_load(path.read_text("utf-8"))
            self.assertNotIn("常规", saved["plans"])
            self.assertNotIn("常规", saved["inventory_configs"])


if __name__ == "__main__":
    unittest.main()
