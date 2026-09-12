import unittest
from copy import deepcopy
from unittest.mock import patch

import numpy as np

from arknights_mower import data
from arknights_mower.solvers import base_mixin, recruit
from arknights_mower.utils import character_recognize, mastery_recommendation


class TestResourceCacheReload(unittest.TestCase):
    def test_data_reload_preserves_imported_container_references(self):
        targets = {
            "stage_data_full.json": [{"id": "HOT-1"}],
            "agent.json": ["测试干员"],
            "agent_profession.json": {"测试干员": "WARRIOR"},
            "workshop_formula.json": {"测试材料": {"apCost": 2}},
            "stage_order.json": ["HOT-1"],
            "recruit.json": {
                "char_test": {
                    "name": "测试干员",
                    "stars": 6,
                    "tags": ["测试标签", "近战位"],
                }
            },
            "recruit_result.json": {"6": ["测试干员"]},
            "key_mapping.json": {"item_test": ["item_test", "MATERIAL", "测试材料"]},
        }
        containers = {
            "_stage_data_base": data._stage_data_base,
            "agent_list": data.agent_list,
            "agent_profession": data.agent_profession,
            "workshop_formula": data.workshop_formula,
            "stage_order": data.stage_order,
            "recruit_agent": data.recruit_agent,
            "recruit_result": data.recruit_result,
            "key_mapping": data.key_mapping,
            "recruit_tag": data.recruit_tag,
            "agent_with_tags": data.agent_with_tags,
            "result_template_list": data.result_template_list,
        }
        originals = {name: deepcopy(value) for name, value in containers.items()}

        try:
            with patch.object(
                data,
                "_read_resource_json",
                side_effect=lambda name, expected_type: deepcopy(targets[name]),
            ):
                data.reload_resource_data()

            for name, original_ref in containers.items():
                self.assertIs(getattr(data, name), original_ref)
            self.assertEqual(data.agent_list, ["测试干员"])
            self.assertEqual(data._stage_data_base, [{"id": "HOT-1"}])
            self.assertEqual(
                data.agent_with_tags["测试标签"],
                [{"id": "char_test", "name": "测试干员", "star": 6}],
            )
            self.assertEqual(data.result_template_list, ["测试干员"])
        finally:
            for name, original in originals.items():
                current = getattr(data, name)
                if isinstance(current, list):
                    data._replace_list(current, original)
                else:
                    data._replace_dict(current, original)

    def test_recognition_model_reload_preserves_references(self):
        select_ref = character_recognize.OP_SELECT
        train_ref = character_recognize.OP_TRAIN
        select_original = select_ref.copy()
        train_original = train_ref.copy()
        try:
            with patch.object(
                character_recognize,
                "_load_models",
                return_value=({"select": "new"}, {"train": "new"}),
            ):
                character_recognize.reload_resource_models()
            self.assertIs(character_recognize.OP_SELECT, select_ref)
            self.assertIs(character_recognize.OP_TRAIN, train_ref)
            self.assertEqual(select_ref, {"select": "new"})
            self.assertEqual(train_ref, {"train": "new"})
        finally:
            select_ref.clear()
            select_ref.update(select_original)
            train_ref.clear()
            train_ref.update(train_original)

    def test_room_model_reload_refreshes_widths_in_place(self):
        room_ref = base_mixin.OP_ROOM
        widths_ref = base_mixin.OP_ROOM_WIDTH
        room_original = room_ref.copy()
        widths_original = widths_ref.copy()
        model = {"测试干员": np.ones((4, 7), dtype=np.uint8)}
        try:
            with patch.object(
                base_mixin, "_load_operator_room_model", return_value=model
            ):
                base_mixin.reload_resource_models()
            self.assertIs(base_mixin.OP_ROOM, room_ref)
            self.assertIs(base_mixin.OP_ROOM_WIDTH, widths_ref)
            self.assertEqual(widths_ref, {"测试干员": 7})
        finally:
            room_ref.clear()
            room_ref.update(room_original)
            widths_ref.clear()
            widths_ref.update(widths_original)

    def test_recruit_and_skill_reload_preserve_references(self):
        result_ref = recruit.recruit_res_template
        tag_ref = recruit.tag_template
        skill_ref = mastery_recommendation.get_skill_data()
        result_original = result_ref.copy()
        tag_original = tag_ref.copy()
        skill_original = deepcopy(skill_ref)
        try:
            with patch.object(
                recruit,
                "_load_recruit_models",
                return_value=({"result": "new"}, {"tag": "new"}),
            ):
                recruit.reload_resource_models()
            with patch.object(
                mastery_recommendation,
                "_load_skill_data",
                return_value={"characters": {"char_test": {}}},
            ):
                mastery_recommendation.reload_resource_data()

            self.assertIs(recruit.recruit_res_template, result_ref)
            self.assertIs(recruit.tag_template, tag_ref)
            self.assertIs(mastery_recommendation.get_skill_data(), skill_ref)
            self.assertEqual(result_ref, {"result": "new"})
            self.assertEqual(tag_ref, {"tag": "new"})
            self.assertEqual(skill_ref, {"characters": {"char_test": {}}})
        finally:
            result_ref.clear()
            result_ref.update(result_original)
            tag_ref.clear()
            tag_ref.update(tag_original)
            skill_ref.clear()
            skill_ref.update(skill_original)


if __name__ == "__main__":
    unittest.main()
