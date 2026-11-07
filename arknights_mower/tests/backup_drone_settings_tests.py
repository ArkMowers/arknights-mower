import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import BackupPlanConf, PlanModel
from arknights_mower.utils.operators import Operators, build_global_plan


def test_active_backup_drone_settings_restore_each_layer_without_persisting(
    monkeypatch,
):
    conf = config.Conf(drone_room="room_3_3", drone_count_limit=130)
    monkeypatch.setattr(config, "conf", conf)
    model = PlanModel.model_validate(
        {
            "plan1": {},
            "backup_plans": [
                {
                    "plan": {},
                    "conf": {"drone_room": "room_1_1", "drone_count_limit": 150},
                },
                {"plan": {}, "conf": {"drone_room": "", "drone_count_limit": 80}},
                {"plan": {}, "conf": {}},
            ],
        }
    )
    before = copy.deepcopy(model.model_dump())
    data = Operators(build_global_plan(plan_model=model, conf_model=conf))
    solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    solver.op_data = data
    solver.drone_room = conf.drone_room
    for flags, room, limit in [
        ([False, False, False], "room_3_3", 130),
        ([True, False, True], "room_1_1", 150),
        ([True, True, True], None, 80),
        ([True, False, False], "room_1_1", 150),
        ([False, True, False], None, 80),
        ([False, False, True], "room_3_3", 130),
    ]:
        assert data.swap_plan(flags) is None
        assert solver.drone_room == room
        assert solver.drone_count_limit == limit
        assert conf.drone_room == "room_3_3"
        assert conf.drone_count_limit == 130
    assert model.model_dump() == before


@pytest.mark.parametrize(
    "limit, expected", [(None, None), (0, 20), (19, 20), (20, 20), (150, 150)]
)
def test_backup_drone_limit_validation_and_round_trip(limit, expected):
    model = PlanModel.model_validate(
        {"backup_plans": [{"conf": {"drone_room": "", "drone_count_limit": limit}}]}
    )
    restored = PlanModel.model_validate_json(model.model_dump_json())
    assert restored.backup_plans[0].conf.drone_count_limit == expected
    assert restored.backup_plans[0].conf.drone_room == ""


@pytest.mark.parametrize("limit", [20.5, "invalid", [], {}])
def test_invalid_backup_drone_limit_is_rejected(limit):
    with pytest.raises(ValidationError):
        BackupPlanConf(drone_count_limit=limit)


@pytest.mark.parametrize(
    "override, expected", [(None, 50), (150, 30), (180, None), (190, None)]
)
def test_manufacturing_acceleration_uses_effective_backup_reserve(
    monkeypatch, override, expected
):
    monkeypatch.setattr(config, "conf", config.Conf(drone_count_limit=130))
    model = PlanModel.model_validate(
        {
            "plan1": {},
            "backup_plans": [{"plan": {}, "conf": {"drone_count_limit": override}}],
        }
    )
    data = Operators(build_global_plan(plan_model=model))
    assert data.swap_plan([True]) is None
    solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    solver.op_data = data
    solver.recog = SimpleNamespace(w=1920, h=1080, gray=None)
    solver.digit_reader = SimpleNamespace(get_drone=lambda _: 180)
    for method in (
        "enter_room",
        "tap",
        "_wait_drone_interface",
        "_cache_facility_state_from_current_page",
        "_tap_drone_accelerate",
        "_confirm_drone_count",
    ):
        setattr(solver, method, MagicMock())
    solver.find = MagicMock(return_value=True)
    solver.drone("room_1_1", not_return=True)
    if expected is None:
        solver._confirm_drone_count.assert_not_called()
        solver._tap_drone_accelerate.assert_not_called()
    else:
        solver._confirm_drone_count.assert_called_once_with(expected)
    assert config.conf.drone_count_limit == 130
