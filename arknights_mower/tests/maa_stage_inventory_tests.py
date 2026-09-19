import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils.maa_stage_inventory import (
    build_stage_options,
    default_materials_for_stage,
    load_inventory_snapshot,
    select_stages_by_inventory,
)


class MaaStageInventoryTests(unittest.TestCase):
    def test_default_regular_drops(self):
        self.assertEqual(
            default_materials_for_stage("SK-5"),
            [
                {"id": "3114", "name": "碳素组"},
                {"id": "3113", "name": "碳素"},
                {"id": "3401", "name": "家具零件"},
            ],
        )
        self.assertEqual(
            default_materials_for_stage("PR-A-2"),
            [
                {"id": "3232", "name": "重装芯片组"},
                {"id": "3262", "name": "医疗芯片组"},
            ],
        )

    def test_and_limit_requires_every_positive_limit(self):
        result = select_stages_by_inventory(
            ["SK-5", "1-7"],
            limit_rules=[
                {
                    "stage": "SK-5",
                    "operator": "and",
                    "items": [
                        {"item_id": "3114", "limit": 100},
                        {"item_id": "3113", "limit": 60},
                        {"item_id": "3401", "limit": 0},
                    ],
                }
            ],
            inventory={"3114": 100, "3113": 59, "3401": 9999},
        )
        self.assertEqual(result["stages"], ["SK-5", "1-7"])

        result = select_stages_by_inventory(
            ["SK-5", "1-7"],
            limit_rules=[
                {
                    "stage": "SK-5",
                    "operator": "and",
                    "items": [
                        {"item_id": "3114", "limit": 100},
                        {"item_id": "3113", "limit": 60},
                    ],
                }
            ],
            inventory={"3114": 100, "3113": 60},
        )
        self.assertEqual(result["stages"], ["1-7"])
        self.assertEqual(result["limit_skipped"], ["SK-5"])

    def test_or_limit_skips_when_any_item_reaches_limit(self):
        result = select_stages_by_inventory(
            ["PR-A-2", "1-7"],
            limit_rules=[
                {
                    "stage": "PR-A-2",
                    "operator": "or",
                    "items": [
                        {"item_id": "3232", "limit": 20},
                        {"item_id": "3262", "limit": 20},
                    ],
                }
            ],
            inventory={"3232": 20, "3262": 1},
        )
        self.assertEqual(result["stages"], ["1-7"])

    def test_all_limit_skips_fall_back_to_original_plan(self):
        result = select_stages_by_inventory(
            ["1-7", "CE-6"],
            limit_rules=[
                {"stage": "1-7", "items": [{"item_id": "30012", "limit": 10}]},
                {"stage": "CE-6", "items": [{"item_id": "4001", "limit": 10}]},
            ],
            inventory={"30012": 10, "4001": 10},
        )
        self.assertTrue(result["limit_fallback"])
        self.assertEqual(result["stages"], ["1-7", "CE-6"])
        self.assertEqual(result["ratio_decisions"], [])

    def test_ratio_selects_lowest_inventory_per_weight(self):
        result = select_stages_by_inventory(
            ["ACT-A", "ACT-B"],
            ratio_rules=[
                {
                    "name": "2比1",
                    "members": [
                        {"stage": "ACT-A", "item_id": "A", "ratio": 2},
                        {"stage": "ACT-B", "item_id": "B", "ratio": 1},
                    ],
                }
            ],
            inventory={"A": 100, "B": 60},
        )
        self.assertEqual(result["stages"], ["ACT-A"])
        self.assertEqual(result["ratio_decisions"][0]["selected"], "ACT-A")

    def test_ratio_score_tie_uses_weekly_plan_order(self):
        result = select_stages_by_inventory(
            ["ACT-B", "ACT-A"],
            ratio_rules=[
                {
                    "members": [
                        {"stage": "ACT-A", "item_id": "A", "ratio": 1},
                        {"stage": "ACT-B", "item_id": "B", "ratio": 1},
                    ]
                }
            ],
            inventory={"A": 10, "B": 10},
        )
        self.assertEqual(result["stages"], ["ACT-B"])
        self.assertEqual(result["ratio_decisions"][0]["selected"], "ACT-B")

    def test_item_name_alias_matches_inventory_item_id(self):
        for item in ({"item_id": "固源岩"}, {"item_name": "固源岩"}):
            with self.subTest(item=item):
                result = select_stages_by_inventory(
                    ["1-7", "CE-6"],
                    limit_rules=[
                        {
                            "stage": "1-7",
                            "items": [{**item, "limit": 100}],
                        }
                    ],
                    inventory={"30012": 100},
                )
                self.assertEqual(result["stages"], ["CE-6"])
                self.assertEqual(result["limit_skipped"], ["1-7"])

    def test_zero_ratio_member_does_not_participate(self):
        result = select_stages_by_inventory(
            ["ACT-A", "ACT-B", "ACT-C"],
            ratio_rules=[
                {
                    "members": [
                        {"stage": "ACT-A", "item_id": "A", "ratio": 2},
                        {"stage": "ACT-B", "item_id": "B", "ratio": 1},
                        {"stage": "ACT-C", "item_id": "C", "ratio": 0},
                    ]
                }
            ],
            inventory={"A": 100, "B": 60, "C": 0},
        )
        self.assertEqual(result["stages"], ["ACT-A", "ACT-C"])
        self.assertEqual(result["ratio_decisions"][0]["selected"], "ACT-A")

    def test_rules_never_add_unselected_stage_to_weekly_plan(self):
        result = select_stages_by_inventory(
            ["1-7"],
            limit_rules=[{"stage": "ACT-A", "items": [{"item_id": "A", "limit": 10}]}],
            ratio_rules=[
                {
                    "members": [
                        {"stage": "ACT-A", "item_id": "A", "ratio": 1},
                        {"stage": "ACT-B", "item_id": "B", "ratio": 1},
                    ]
                }
            ],
            inventory={"A": 0, "B": 0},
        )
        self.assertEqual(result["stages"], ["1-7"])
        self.assertEqual(result["ratio_decisions"], [])

    def test_activity_materials_use_selected_hot_update_entry(self):
        stages = [
            {"id": "ACT-8", "drop": [{"id": "OLD"}]},
            {"id": "ACT-8", "drop": None},
        ]
        selected = [
            {"code": "ACT-8", "materials": [{"id": "NEW", "name": "新材料"}]},
            {"code": "ACT-7", "materials": [{"id": "OTHER", "name": "另一材料"}]},
        ]
        with (
            patch("arknights_mower.utils.maa_stage_inventory.stage_data_full", stages),
            patch(
                "arknights_mower.utils.maa_stage_inventory.select_latest_activity_stages",
                return_value=selected,
            ),
        ):
            options, suggestion = build_stage_options()
        self.assertEqual(options[0]["materials"], selected[0]["materials"])
        self.assertEqual(options[0]["label"], "ACT-8：新材料")
        self.assertEqual(suggestion["name"], "当前活动绑定")
        self.assertEqual(suggestion["members"][0]["item_id"], "NEW")
        self.assertEqual(suggestion["members"][0]["ratio"], 0)

    def test_limit_is_applied_before_ratio(self):
        result = select_stages_by_inventory(
            ["ACT-A", "ACT-B", "1-7"],
            limit_rules=[{"stage": "ACT-A", "items": [{"item_id": "A", "limit": 100}]}],
            ratio_rules=[
                {
                    "members": [
                        {"stage": "ACT-A", "item_id": "A", "ratio": 1},
                        {"stage": "ACT-B", "item_id": "B", "ratio": 1},
                    ]
                }
            ],
            inventory={"A": 100, "B": 999},
        )
        self.assertEqual(result["limit_skipped"], ["ACT-A"])
        self.assertEqual(result["stages"], ["ACT-B", "1-7"])
        self.assertEqual(result["ratio_decisions"], [])

    def test_load_inventory_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cultivate.json"
            path.write_text(
                json.dumps(
                    {
                        "data": {
                            "items": [
                                {"id": "30012", "count": "123"},
                                {"id": "4001", "count": 456},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            inventory, updated_at = load_inventory_snapshot(path)
        self.assertEqual(inventory, {"30012": 123, "4001": 456})
        self.assertIsNotNone(updated_at)


if __name__ == "__main__":
    unittest.main()
