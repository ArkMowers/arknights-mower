import unittest
from unittest.mock import patch

from flask import Flask

from arknights_mower.views.mastery import mastery_bp


class TestMasteryRouteView(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(mastery_bp)
        self.client = app.test_client()

    @patch("arknights_mower.views.mastery.save_route")
    def test_route_post_forwards_all_persisted_settings(self, save_route_mock):
        response = self.client.post(
            "/mastery-route",
            json={
                "profession": "近卫",
                "supports": [],
                "optimal": True,
                "half_off": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        save_route_mock.assert_called_once_with(
            "近卫",
            "[]",
            is_default=0,
            optimal=True,
            half_off=False,
        )

    @patch("arknights_mower.views.mastery.get_route_settings")
    @patch("arknights_mower.views.mastery.get_all_routes")
    def test_route_get_includes_settings(self, routes_mock, settings_mock):
        # #91 修订：GET /mastery-route 带全局设置（中枢加成 + 换人缓冲），前端一个开关读它
        routes_mock.return_value = []
        settings_mock.return_value = {"central_bonus": 5, "mastery_swap_buffer": 15}
        response = self.client.get("/mastery-route")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            data["settings"], {"central_bonus": 5, "mastery_swap_buffer": 15}
        )
        self.assertEqual(data["routes"], [])

    @patch("arknights_mower.views.mastery.save_route_settings")
    def test_route_settings_post_forwards_values(self, save_mock):
        response = self.client.post(
            "/mastery-route/settings",
            json={"central_bonus": 5, "mastery_swap_buffer": 15},
        )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_called_once_with(central_bonus=5, mastery_swap_buffer=15)

    @patch("arknights_mower.views.mastery.save_route_settings")
    def test_route_settings_post_keeps_zero_buffer(self, save_mock):
        # review 修复：显式 buffer=0 合法（UI min=0），不得被 or 10 吞成 10
        response = self.client.post(
            "/mastery-route/settings",
            json={"central_bonus": 0, "mastery_swap_buffer": 0},
        )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_called_once_with(central_bonus=0, mastery_swap_buffer=0)


class TestMasteryPlanView(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(mastery_bp)
        self.client = app.test_client()

    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.views.mastery.get_all_history")
    @patch("arknights_mower.views.mastery.get_failed_plans")
    @patch("arknights_mower.views.mastery.get_all_plans")
    def test_plan_get_includes_failed_plans(
        self, get_all, get_failed, get_history, get_skill
    ):
        # #69：failed 计划要带给前端（含 failed_reason），不能"凭空消失"
        get_all.return_value = [
            {
                "id": 1,
                "char_id": "char_001",
                "char_name": "测试干员",
                "skill_index": 0,
                "skill_name": "一技能",
                "target_level": 1,
                "status": "idle",
                "priority": 0,
                "expires_at": None,
                "failed_reason": None,
            }
        ]
        get_failed.return_value = [
            {
                "id": 2,
                "char_id": "char_002",
                "char_name": "失败干员",
                "skill_index": 1,
                "skill_name": "二技能",
                "target_level": 2,
                "status": "failed",
                "priority": 0,
                "expires_at": None,
                "failed_reason": "材料不足",
            }
        ]
        get_history.return_value = []
        get_skill.return_value = {"characters": {}}

        response = self.client.get("/mastery-plan")
        self.assertEqual(response.status_code, 200)
        plans = response.get_json()["plans"]
        self.assertEqual([p["status"] for p in plans], ["idle", "failed"])
        failed = next(p for p in plans if p["status"] == "failed")
        self.assertEqual(failed["failed_reason"], "材料不足")
        self.assertEqual(failed["name"], "失败干员")

    def _char_table(self):
        return {
            "characters": {
                "char_001": {
                    "name": "阿米娅",
                    "skills": [
                        {"name": "一技能"},
                        {"name": "二技能"},
                        {"name": "三技能"},
                    ],
                }
            }
        }

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_bulk_rejects_out_of_range_target(self, get_skill, insert):
        # #65/B7：bulk 路径 target_level 越界（0/4/布尔 true）拒绝，不落库
        get_skill.return_value = self._char_table()
        for bad in (0, 4, True):
            r = self.client.post(
                "/mastery-plan",
                json={
                    "items": [{"name": "阿米娅", "skill_index": 0, "target_level": bad}]
                },
            )
            res = r.get_json()["results"][0]
            self.assertEqual(res["status"], "error")
            self.assertIn("无效", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_bulk_rejects_non_int_target(self, get_skill, insert):
        # #65/B7：target_level 非整数（如字符串 "3"）拒绝
        get_skill.return_value = self._char_table()
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 0, "target_level": "3"}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "error")
        self.assertIn("无效", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_bulk_defaults_target_to_three(self, get_level, get_skill, insert):
        # #65/B7：bulk 未传 target_level 默认专三（与推荐一致），不再硬编码专一
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 5
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 0}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "added")
        self.assertEqual(res["id"], 5)
        self.assertEqual(insert.call_args.kwargs["target_level"], 3)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_bulk_honors_explicit_target(self, get_level, get_skill, insert):
        # #65/B7：bulk 显式 target_level 被采纳（在范围内且低于当前等级）
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 8
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 1, "target_level": 2}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "added")
        self.assertEqual(insert.call_args.kwargs["target_level"], 2)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_bulk_rejects_operator_already_at_target(
        self, get_level, get_skill, insert
    ):
        # #65/B7：干员已到目标档位 → 拒绝并给清晰文案，不落库
        get_skill.return_value = self._char_table()
        get_level.return_value = 2
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 0, "target_level": 2}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "error")
        self.assertIn("无需再练", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_flat_defaults_target_to_three(self, get_level, get_skill, insert):
        # #65/B7：扁平路径不传 target_level，默认专三（不再硬编码专一）
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 7
        r = self.client.post("/mastery-plan", json={"阿米娅": 0})
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "added")
        self.assertEqual(res["id"], 7)
        self.assertEqual(insert.call_args.kwargs["target_level"], 3)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_flat_rejects_operator_already_at_target(
        self, get_level, get_skill, insert
    ):
        # #65/B7：干员已专三（≥ 默认目标）→ 扁平路径也拒绝
        get_skill.return_value = self._char_table()
        get_level.return_value = 3
        r = self.client.post("/mastery-plan", json={"阿米娅": 0})
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "error")
        self.assertIn("已专", res["reason"])
        insert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
