"""Test isolation for DB/API contracts that do not exercise assistant optimization."""

from unittest.mock import patch


def stub_support_planner(test_case):
    planner = patch(
        "arknights_mower.utils.mastery_support.plan_supports",
        return_value={"version": 1, "stages": []},
    )
    planner.start()
    test_case.addCleanup(planner.stop)
