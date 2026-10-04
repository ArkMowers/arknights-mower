"""救急上岗心情与专项预约门槛。"""

from datetime import datetime

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_staffing import worker_block_reason
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operator


@pytest.mark.parametrize("name", TRADE_ORDER_AGENTS)
def test_only_explicitly_reserved_trade_order_agent_is_excluded(solver, name):
    op = Operator(name, "", mood=24, time_stamp=datetime.now())
    solver.op_data.add(op)
    assert worker_block_reason(solver.op_data, name, 24, set()) is None
    assert worker_block_reason(solver.op_data, name, 24, {name}) is not None


@pytest.mark.parametrize("mood", [None, 0])
def test_unknown_or_low_card_mood_cannot_staff(solver, mood):
    solver.op_data.config.resting_threshold = 0.65
    op = next(iter(solver.op_data.operators.values()))
    assert (
        worker_block_reason(solver.op_data, op.name, mood, set(), allow_zero=False)
        is not None
    )


def test_personal_normal_shift_line_and_reservation_are_used(solver):
    op = next(iter(solver.op_data.operators.values()))
    op.lower_limit, op.upper_limit = 6, 20
    line = op.lower_limit + 0.1
    assert (
        worker_block_reason(
            solver.op_data, op.name, line - 0.1, set(), allow_zero=False
        )
        is not None
    )
    assert (
        worker_block_reason(solver.op_data, op.name, line, set(), allow_zero=False)
        is None
    )
    assert worker_block_reason(solver.op_data, op.name, 24, {op.name}) is not None


@pytest.mark.parametrize("mood", [0, 1, 8])
def test_known_low_mood_is_allowed_without_bypassing_reservation(solver, mood):
    name = next(iter(solver.op_data.operators))
    assert worker_block_reason(solver.op_data, name, mood, set()) is None
    assert worker_block_reason(solver.op_data, name, mood, {name}) == "已被其他任务预约"


@pytest.mark.parametrize("mood", [None, float("nan"), float("inf"), -1, 25])
def test_invalid_reading_never_allows_zero_mood_staffing(solver, mood):
    name = next(iter(solver.op_data.operators))
    assert (
        worker_block_reason(solver.op_data, name, mood, set()) == "心情读数未知或无效"
    )
