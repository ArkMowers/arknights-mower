"""救急上岗心情与专项预约门槛。"""

from datetime import datetime

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_staffing import eligible_worker
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operator


@pytest.mark.parametrize("name", TRADE_ORDER_AGENTS)
def test_only_explicitly_reserved_trade_order_agent_is_excluded(solver, name):
    op = Operator(name, "", mood=24, time_stamp=datetime.now())
    solver.op_data.add(op)
    assert eligible_worker(solver.op_data, name, 24, set())
    assert not eligible_worker(solver.op_data, name, 24, {name})


@pytest.mark.parametrize("mood", [None, 0, 15.9])
def test_unknown_or_low_card_mood_cannot_staff(solver, mood):
    solver.op_data.config.resting_threshold = 0.65
    op = next(iter(solver.op_data.operators.values()))
    assert not eligible_worker(solver.op_data, op.name, mood, set())


def test_personal_normal_shift_line_and_reservation_are_used(solver):
    op = next(iter(solver.op_data.operators.values()))
    op.lower_limit, op.upper_limit = 6, 20
    line = solver.op_data.resting_mood_threshold(op) + 1
    assert not eligible_worker(solver.op_data, op.name, line - 0.1, set())
    assert eligible_worker(solver.op_data, op.name, line, set())
    assert not eligible_worker(solver.op_data, op.name, 24, {op.name})
