import unittest
from unittest.mock import MagicMock

import numpy as np

from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene


class TestNavigationBarRecognition(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
