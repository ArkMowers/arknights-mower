"""Fixed mastery handoffs share run-order collision handling without being accelerated."""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import mastery_support_state as state  # noqa: E402
from arknights_mower.solvers import mastery_support_swap as swap_runtime  # noqa: E402
from arknights_mower.tests.mastery_scheduling_fixtures import (  # noqa: E402
    clock as clock,  # noqa: E402
)
from arknights_mower.tests.mastery_support_fixtures import stat  # noqa: E402
from arknights_mower.utils.mastery_optimizer import stage_route  # noqa: E402
from arknights_mower.utils.mastery_support_types import StageSpec  # noqa: E402


@pytest.mark.parametrize("central", [0, 5])
def test_conservative_swap_timing_matches_legacy_and_optimizer(central):
    now = datetime(2026, 9, 8, 17, 42)
    route = stage_route(
        stat("缄默德克萨斯", 80), stat("逻各斯", 0, True), StageSpec(2, 8, central)
    )
    route["working_operator"] = route["operator"]
    plan = {
        "id": 1,
        "target_level": 3,
        "support_plan": {"stages": [route]},
        "support_runtime": route,
    }
    end = now + timedelta(hours=8 / (1.85 + central / 100))
    buffer = 15 if central else 10
    expected = end - timedelta(minutes=(300 + buffer) * (1.05 + central / 100) / 1.85)
    with (
        patch.object(state, "datetime") as mock_now,
        patch.object(state, "enqueue_support_swap"),
    ):
        mock_now.now.return_value = now
        at = state.schedule_support_swap(MagicMock(), plan, end, 2)
    assert at == expected
    assert abs((at - now).total_seconds() - route["switch_after"] * 3600) < 1
    # Duration uses actual nominal rates, even though the handoff is conservative.
    expected_hours = route["switch_after"] + (
        8 - route["switch_after"] * (1.85 + central / 100)
    ) / (1.05 + central / 100)
    assert route["hours"] == pytest.approx(expected_hours)
    speed = swap_runtime._current_rate(
        {"教官": {2: stat("教官", 80)}}, "教官", 2, central
    )
    assert speed == pytest.approx(1.85 + central / 100)
    remaining = (end - at).total_seconds()
    selected, delay = swap_runtime.select_swap_support(
        remaining * speed,
        speed,
        [stat("逻各斯", 0, True)],
        (central, buffer),
        schedule_rate=1.85,
    )
    assert selected["name"] == "逻各斯"
    assert delay == pytest.approx(0, abs=1e-5)
