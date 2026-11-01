import unittest
from unittest.mock import MagicMock, patch

import server
from arknights_mower.utils import config


def _headers():
    token = getattr(server.app, "token", "")
    return {"token": token} if token else {}


class WeeklyPlanInventoryRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.manager = MagicMock()
        self.manager.get_active_plan_key.return_value = "活动"
        self.manager.get_plans.return_value = ["活动", "常规"]

    def test_switch_plan_saves_source_rules_and_returns_target_rules(self):
        source = {"enabled": True, "limit_rules": [], "ratio_rules": []}
        target = {"enabled": False, "limit_rules": [], "ratio_rules": []}
        self.manager.set_inventory_config.return_value = True
        self.manager.set_active_plan.return_value = True
        self.manager.get_plan.return_value = []
        self.manager.get_inventory_config.return_value = target
        self.manager.get_activity_fallbacks.return_value = {}
        self.manager.get_activity_fallback_switch_times.return_value = {}
        self.manager.get_activity_plan_end_times.return_value = {}

        with patch(
            "arknights_mower.utils.config.weekly_plan_loader.get_weekly_plan_manager",
            return_value=self.manager,
        ):
            response = self.client.post(
                "/weekly-plans/active",
                json={"active": "常规", "source_inventory_config": source},
                headers=_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.manager.set_inventory_config.assert_called_once_with("活动", source)
        self.manager.set_active_plan.assert_called_once_with("常规")
        self.assertEqual(response.get_json()["inventory_config"], target)

    def test_conf_partial_inventory_edit_keeps_other_rules_for_that_plan(self):
        stored = {
            "enabled": False,
            "limit_rules": [{"stage": "ACT-1"}],
            "ratio_rules": [{"name": "活动比例"}],
        }
        self.manager.get_inventory_config.return_value = stored
        self.manager.set_inventory_config.return_value = True

        with (
            patch(
                "arknights_mower.utils.config.weekly_plan_loader.get_weekly_plan_manager",
                return_value=self.manager,
            ),
            patch(
                "arknights_mower.utils.workshop_config.save_user_config",
                return_value={},
            ) as save,
        ):
            response = self.client.post(
                "/conf",
                json={
                    "maa_weekly_plan_active": "活动",
                    "maa_stage_inventory_enable": True,
                },
                headers=_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.manager.set_inventory_config.assert_called_once_with(
            "活动",
            {
                "enabled": True,
                "limit_rules": [{"stage": "ACT-1"}],
                "ratio_rules": [{"name": "活动比例"}],
            },
        )
        payload = save.call_args.args[0]
        self.assertNotIn("maa_weekly_plan_active", payload)
        self.assertEqual(
            payload["maa_weekly_plan"],
            [item.model_dump() for item in config.conf.maa_weekly_plan],
        )

    def test_delayed_source_autosave_keeps_active_runtime_rules(self):
        source = {"enabled": True, "limit_rules": [], "ratio_rules": []}
        active = {
            "enabled": False,
            "limit_rules": [{"stage": "1-7"}],
            "ratio_rules": [{"name": "常规比例"}],
        }
        self.manager.get_active_plan_key.return_value = "常规"
        self.manager.get_inventory_config.side_effect = lambda key: {
            "活动": source,
            "常规": active,
        }[key]
        self.manager.set_inventory_config.return_value = True

        with (
            patch(
                "arknights_mower.utils.config.weekly_plan_loader.get_weekly_plan_manager",
                return_value=self.manager,
            ),
            patch(
                "arknights_mower.utils.workshop_config.save_user_config",
                return_value={},
            ) as save,
        ):
            response = self.response_for_plan_autosave(source)

        self.assertEqual(response.status_code, 200)
        self.manager.set_inventory_config.assert_called_once_with("活动", source)
        payload = save.call_args.args[0]
        self.assertFalse(payload["maa_stage_inventory_enable"])
        self.assertEqual(payload["maa_stage_limit_rules"], active["limit_rules"])
        self.assertEqual(payload["maa_stage_ratio_rules"], active["ratio_rules"])

    def response_for_plan_autosave(self, source):
        return self.client.post(
            "/conf",
            json={
                "maa_weekly_plan_active": "活动",
                "maa_stage_inventory_enable": source["enabled"],
                "maa_stage_limit_rules": source["limit_rules"],
                "maa_stage_ratio_rules": source["ratio_rules"],
            },
            headers=_headers(),
        )

    def test_deleted_plan_autosave_is_not_applied_to_active_plan(self):
        source = {"enabled": True, "limit_rules": [], "ratio_rules": []}
        active = {"enabled": False, "limit_rules": [], "ratio_rules": []}
        self.manager.get_active_plan_key.return_value = "常规"
        self.manager.get_plans.return_value = ["常规"]
        self.manager.get_inventory_config.return_value = active

        with (
            patch(
                "arknights_mower.utils.config.weekly_plan_loader.get_weekly_plan_manager",
                return_value=self.manager,
            ),
            patch(
                "arknights_mower.utils.workshop_config.save_user_config",
                return_value={},
            ) as save,
        ):
            response = self.response_for_plan_autosave(source)

        self.assertEqual(response.status_code, 200)
        self.manager.set_inventory_config.assert_not_called()
        payload = save.call_args.args[0]
        self.assertFalse(payload["maa_stage_inventory_enable"])
        self.assertEqual(payload["maa_stage_limit_rules"], [])
        self.assertEqual(payload["maa_stage_ratio_rules"], [])


if __name__ == "__main__":
    unittest.main()
