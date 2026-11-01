import unittest
from unittest.mock import MagicMock

import numpy as np

from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene


class TestNavigationBarRecognition(unittest.TestCase):
    def test_training_pages_take_priority_over_infra_overview(self):
        pages = {
            "room_detail": Scene.INFRA_DETAILS,
            "arrange_check_in_on": Scene.INFRA_DETAILS,
            "train_main": Scene.TRAIN_MAIN,
            "skill_collect_confirm": Scene.TRAIN_FINISH,
            "training_support": Scene.TRAIN_SKILL_SELECT,
            "upgrade_failure": Scene.TRAIN_SKILL_UPGRADE_ERROR,
            "skill_confirm": Scene.TRAIN_SKILL_UPGRADE,
        }
        for resource, expected in pages.items():
            with self.subTest(resource=resource):
                recognizer = Recognizer.__new__(Recognizer)
                recognizer.scene = Scene.UNDEFINED
                recognizer.find = MagicMock(
                    side_effect=lambda name: name in {"infra_overview", resource}
                )
                recognizer.check_loading_time = MagicMock()
                self.assertEqual(recognizer.get_train_scene(), expected)

    def test_specialized_scenes_preserve_overview_connecting_and_unknown(self):
        cases = [
            ({"infra_overview"}, Scene.INFRA_MAIN),
            (
                {"connecting", "infra_overview", "train_main", "factory_dashboard"},
                Scene.CONNECTING,
            ),
            (set(), Scene.UNKNOWN),
        ]
        for method in ("get_train_scene", "get_factory_scene"):
            for resources, expected in cases:
                with self.subTest(method=method, resources=resources):
                    recognizer = Recognizer.__new__(Recognizer)
                    recognizer.scene = Scene.UNDEFINED
                    recognizer.find = MagicMock(
                        side_effect=lambda name: name in resources
                    )
                    recognizer.check_loading_time = MagicMock()
                    recognizer.check_current_focus = MagicMock()
                    self.assertEqual(getattr(recognizer, method)(), expected)
                    self.assertEqual(
                        recognizer.check_current_focus.call_count,
                        int(expected == Scene.UNKNOWN),
                    )

    def test_factory_pages_take_priority_over_infra_overview(self):
        pages = {
            "factory_dashboard": Scene.FACTORY_DASHBOARD,
            "factory_formula": Scene.FACTORY_FORMULA,
            "factory_furniture": Scene.FACTORY_FORMULA,
            "factory_product_collect": Scene.FACTORY_PRODUCT_COLLECT,
            "factory_tag": Scene.FACTORY_ROOM,
        }
        for resource, expected in pages.items():
            with self.subTest(resource=resource):
                recognizer = Recognizer.__new__(Recognizer)
                recognizer.scene = Scene.UNDEFINED
                recognizer.find = MagicMock(
                    side_effect=lambda name: name in {"infra_overview", resource}
                )
                recognizer.check_loading_time = MagicMock()
                self.assertEqual(recognizer.get_factory_scene(), expected)

    def test_room_button_takes_priority_over_infra_overview(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer.find = MagicMock(
            side_effect=lambda resource: (
                resource in {"infra_overview", "arrange_check_in"}
            )
        )
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.INFRA_DETAILS)
        self.assertNotIn(
            "infra_overview", [call.args[0] for call in recognizer.find.call_args_list]
        )

    def test_navigation_bar_overrides_visible_factory_collect(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer.find = MagicMock(
            side_effect=lambda resource: resource in {"nav_bar", "factory_collect"}
        )
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.NAVIGATION_BAR)
        recognizer.find.assert_any_call("nav_bar")
        self.assertNotIn(
            "factory_collect", [call.args[0] for call in recognizer.find.call_args_list]
        )

    def test_logo_without_white_captcha_panel_is_not_captcha(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer._gray = np.full((1080, 1920), 100, dtype=np.uint8)
        recognizer.find = MagicMock(
            side_effect=lambda resource, **_: resource == "login_captcha"
        )
        recognizer.detect_index_scene = MagicMock(return_value=False)
        recognizer.check_announcement = MagicMock(return_value=False)
        recognizer.check_current_focus = MagicMock()
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.UNKNOWN)
        self.assertNotIn(
            "login_captcha", [call.args[0] for call in recognizer.find.call_args_list]
        )

    def test_login_page_takes_priority_over_agency_dialog_features(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer.find = MagicMock(
            side_effect=lambda resource, **_: (
                resource
                in {
                    "ope_elimi_agency_confirm",
                    "ope_elimi_agency_panel",
                    "login_logo",
                    "hypergryph",
                    "login_awake",
                }
            )
        )
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.LOGIN_QUICKLY)
        self.assertNotIn(
            "ope_elimi_agency_panel",
            [call.args[0] for call in recognizer.find.call_args_list],
        )

    def test_login_connecting_takes_priority_over_infra_todo(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer.find = MagicMock(
            side_effect=lambda resource, **_: (
                resource in {"login_connecting", "infra_todo"}
            )
        )
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.LOGIN_LOADING)
        self.assertNotIn(
            "infra_todo", [call.args[0] for call in recognizer.find.call_args_list]
        )

    def test_agency_title_without_button_does_not_match_dialog(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer.find = MagicMock(
            side_effect=lambda resource, **_: (
                resource in {"ope_elimi_agency_panel", "terminal_main"}
            )
        )
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.TERMINAL_MAIN)

    def test_agency_dialog_requires_button_and_title(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer.scene = Scene.UNDEFINED
        recognizer.find = MagicMock(
            side_effect=lambda resource, **_: (
                resource in {"ope_elimi_agency_confirm", "ope_elimi_agency_panel"}
            )
        )
        recognizer.check_freeze = MagicMock()

        self.assertEqual(recognizer.get_scene(), Scene.OPERATOR_ELIMINATE_AGENCY)


if __name__ == "__main__":
    unittest.main()
