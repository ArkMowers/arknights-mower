import unittest
from unittest.mock import patch

from arknights_mower.solvers.mission import MissionSolver
from arknights_mower.utils.recognize import Scene


class TestMissionSolver(unittest.TestCase):
    @patch.object(MissionSolver, "__init__", lambda x: None)
    def test_trainee_mission_goes_to_daily_before_daily_checked(self):
        solver = MissionSolver()
        solver.daily = False

        with (
            patch.object(MissionSolver, "scene", return_value=Scene.MISSION_TRAINEE),
            patch.object(MissionSolver, "tap_element") as mock_tap_element,
        ):
            result = solver.transition()

        self.assertIsNone(result)
        mock_tap_element.assert_called_once_with("mission_daily")

    @patch.object(MissionSolver, "__init__", lambda x: None)
    def test_trainee_mission_goes_to_weekly_after_daily_checked(self):
        solver = MissionSolver()
        solver.daily = True

        with (
            patch.object(MissionSolver, "scene", return_value=Scene.MISSION_TRAINEE),
            patch.object(MissionSolver, "tap_element") as mock_tap_element,
        ):
            result = solver.transition()

        self.assertIsNone(result)
        mock_tap_element.assert_called_once_with("mission_weekly")


if __name__ == "__main__":
    unittest.main()
