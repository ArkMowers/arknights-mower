"""选人画面延迟、缺帧及重排顺序的回归测试。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402

TARGET = ["多萝西", "淬羽赫默", "娜斯提"]
OLD = ["斯卡蒂", "幽灵鲨", "娜斯提"]


def reader(monkeypatch, frames):
    solver = BaseMixin()
    snapshots = iter(frames)
    solver.recog = SimpleNamespace(img=None)

    def update():
        solver.recog.img = next(snapshots)

    solver.recog.update = MagicMock(side_effect=update)
    solver.sleep = MagicMock()
    solver.find = MagicMock(return_value=False)
    solver.tap = MagicMock()
    monkeypatch.setattr(
        base_mixin, "operator_list", lambda img, **kwargs: [(n, None) for n in img]
    )
    return solver


def test_waits_for_delayed_selection_without_tapping_again(monkeypatch):
    solver = reader(monkeypatch, [OLD, OLD, TARGET, OLD, TARGET, TARGET])
    assert solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 6
    solver.tap.assert_not_called()


@pytest.mark.parametrize("frame", [[], TARGET[:2], OLD])
def test_missing_or_incorrect_names_never_pass(monkeypatch, frame):
    solver = reader(monkeypatch, [frame] * 6)
    assert not solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 6


def test_reorder_uses_actual_stable_card_order(monkeypatch):
    actual = list(reversed(TARGET))
    solver = reader(monkeypatch, [OLD, actual, actual])
    assert solver.wait_for_arranged_agents(TARGET, ordered=False) == actual


def test_final_verification_requires_requested_order(monkeypatch):
    solver = reader(monkeypatch, [list(reversed(TARGET))] * 6)
    assert not solver.verify_agent(TARGET, "room_3_3")


def test_stop_during_wait_propagates_without_retry(monkeypatch):
    solver = reader(monkeypatch, [OLD])
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 1


def test_connection_overlay_breaks_consecutive_match(monkeypatch):
    solver = reader(monkeypatch, [TARGET] * 4)
    solver.find.side_effect = [False, True, False, False]
    assert solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 4
