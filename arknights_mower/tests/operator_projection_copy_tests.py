"""干员复制隔离扩展状态，连续预演保留真实驻员和恢复读数。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests.backup_snapshot_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator, Operators


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    return Operator(
        "伊内丝",
        "meeting",
        replacement=["陈", "砾"],
        current_room="meeting",
        current_index=0,
        refresh_order_room=[True, ["room_1_1"]],
        group_bindings=[{"group": "一组", "replacement": ["陈", "砾"]}],
    )


def test_copied_nested_operator_state_can_change_without_affecting_source(operator):
    operator.dorm_mood_peers = {"陈": {"mood": [12]}}
    operator.extension = {"readings": [{"mood": 8}]}

    cloned = deepcopy(operator)
    cloned.replacement.append("香草")
    cloned.group_bindings[0]["replacement"].remove("陈")
    cloned.refresh_order_room[1].append("room_1_2")
    cloned.arrange_order[0] = "心情"
    cloned.dorm_mood_peers["陈"]["mood"].append(24)
    cloned.extension["readings"][0]["mood"] = 0

    assert operator.replacement == ["陈", "砾"]
    assert operator.group_bindings == [{"group": "一组", "replacement": ["陈", "砾"]}]
    assert operator.refresh_order_room == [True, ["room_1_1"]]
    assert operator.arrange_order == ["技能", "false"]
    assert operator.dorm_mood_peers == {"陈": {"mood": [12]}}
    assert operator.extension == {"readings": [{"mood": 8}]}


def test_copied_extensions_preserve_internal_aliases_and_cycles(operator):
    shared = ["陈"]
    operator.extension = {"owner": operator, "members": shared}
    operator.extension_alias = shared
    operator.extension["cycle"] = operator.extension
    operator.state_reference = operator.__dict__

    cloned = deepcopy(operator)
    assert cloned.extension["owner"] is cloned
    assert cloned.extension["cycle"] is cloned.extension
    assert cloned.extension["members"] is cloned.extension_alias
    assert cloned.state_reference is cloned.__dict__
    cloned.extension_alias.append("砾")
    cloned.state_reference["mood"] = 3

    assert shared == ["陈"]
    assert operator.mood == 24
    assert operator.state_reference is operator.__dict__
    assert operator.extension["owner"] is operator


def test_scalar_subclass_extension_keeps_its_mutable_attributes_isolated(operator):
    class ObservedMood(float):
        pass

    operator.extension = ObservedMood(12)
    operator.extension.samples = [12]

    cloned = deepcopy(operator)
    cloned.extension.samples.append(8)

    assert type(cloned.extension) is ObservedMood
    assert cloned.extension == 12
    assert operator.extension.samples == [12]


def test_copy_reuses_operator_state_already_reached_from_container(operator):
    operator.owner = operator

    state, cloned = deepcopy([operator.__dict__, operator])

    assert cloned.__dict__ is state
    assert state["owner"] is cloned
    state["replacement"].append("香草")
    assert operator.replacement == ["陈", "砾"]


def test_copy_preserves_shared_model_and_configuration_inside_snapshot(solver):
    data = solver.op_data
    model = data.mood_model
    conf = config.Conf(test_mood_calculation=True)
    model.moods["伊内丝"] = 12
    deadlines = {}
    for op in data.operators.values():
        op._mood_model = model
        op._mood_conf = conf
        op._projection_deadlines = deadlines

    copied = deepcopy((data.operators, model, conf, deadlines))
    operators, copied_model, copied_conf, copied_deadlines = copied
    for op in operators.values():
        assert op._mood_model is copied_model
        assert op._mood_conf is copied_conf
        assert op._projection_deadlines is copied_deadlines
    copied_model.moods["伊内丝"] = 0
    copied_conf.rescue_threshold = 0.1
    copied_deadlines["伊内丝"] = datetime(2026, 10, 27, 8)

    assert model.moods["伊内丝"] == 12
    assert conf.rescue_threshold == 0.75
    assert deadlines == {}


def test_copy_does_not_replay_position_setters_or_callbacks(operator, monkeypatch):
    callback = Mock()
    monkeypatch.setattr(Operators, "current_room_changed_callback", callback)

    def reject_setter(*args):
        raise AssertionError("copy must preserve observed state without moving")

    monkeypatch.setattr(
        Operator,
        "current_room",
        property(Operator.current_room.fget, reject_setter),
    )
    monkeypatch.setattr(
        Operator,
        "current_index",
        property(Operator.current_index.fget, reject_setter),
    )

    cloned = deepcopy(operator)

    assert (cloned.current_room, cloned.current_index) == ("meeting", 0)
    assert cloned.dorm_position_version == operator.dorm_position_version
    callback.assert_not_called()


def test_public_projection_preserves_source_readings_and_invalidates_moved_bed(
    solver, monkeypatch
):
    source = solver.op_data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["Current", "伊内丝"]}]
    )
    resident = source.operators["伊内丝"]
    observed = datetime(2026, 10, 27, 8)
    deadline = observed + timedelta(hours=4)
    resident.mood, resident.time_stamp = 6, observed
    resident.dorm_recovery_fixed = ("塑心", ("dormitory_1", 1), 7)
    source_bed = source.get_dorm_by_name("伊内丝")[1]
    source_bed.time = deadline
    callback = Mock()
    monkeypatch.setattr(Operators, "current_room_changed_callback", callback)

    unchanged = source.project_arrangements([])
    assert unchanged.get_dorm_by_name("伊内丝")[1].time == deadline
    assert unchanged.operators["伊内丝"].dorm_recovery_fixed == (
        "塑心",
        ("dormitory_1", 1),
        7,
    )

    projected = source.project_arrangements(
        [
            {"meeting": ["伊内丝"], "dormitory_1": ["Current", "Free"]},
            {
                "meeting": ["陈"],
                "dormitory_1": ["Current", "Current", "伊内丝"],
            },
        ]
    )

    moved = projected.operators["伊内丝"]
    assert (moved.current_room, moved.current_index) == ("dormitory_1", 2)
    assert moved.dorm_recovery_fixed == ()
    assert projected.get_dorm_by_name("伊内丝")[1].time is None
    assert projected.get_current_operator("meeting", 0).name == "陈"
    assert projected.get_current_operator("dormitory_1", 1) is None
    assert (moved.mood, moved.time_stamp) == (6, observed)
    assert (resident.current_room, resident.current_index) == ("dormitory_1", 1)
    assert (resident.mood, resident.time_stamp) == (6, observed)
    assert resident.dorm_recovery_fixed == ("塑心", ("dormitory_1", 1), 7)
    assert (source_bed.name, source_bed.time) == ("伊内丝", deadline)
    assert source.get_current_operator("meeting", 0).name == "陈"
    callback.assert_not_called()
