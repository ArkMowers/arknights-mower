"""原生心情模型沿用收益演算的主表设施等级。"""

import copy
import pickle
from datetime import datetime, timedelta

import pytest

from arknights_mower.utils import calculated_mood, config
from arknights_mower.utils.calculated_mood import sync_model
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.plan import Room

NOW = datetime(2026, 10, 25, 20, 3, 47)


@pytest.fixture
def owner(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(calculated_mood, "datetime", Clock)
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_cultivate_snapshot",
        lambda: None,
    )
    conf = config.Conf(test_mood_calculation=True)

    def create(*, third_power=False, levels=None):
        primary = {
            "room_1_1": {
                "name": "制造站",
                "plans": [{"agent": "芬", "replacement": ["香草"]}],
            },
            "room_1_3": {"name": "发电站", "plans": []},
            "room_2_3": {"name": "发电站", "plans": []},
            "central": {"name": "", "plans": []},
            "dormitory_1": {
                "name": "",
                "plans": [{"agent": "Free"} for _ in range(5)],
            },
        }
        if third_power:
            primary["room_3_3"] = {"name": "发电站", "plans": []}
        source = config.PlanModel.model_validate(
            {"default": "plan1", "plan1": primary, "facility_levels": levels or {}}
        )
        data = Operators(
            build_global_plan(plan_model=source, conf_model=conf),
            runtime_conf=conf,
            facility_levels=source.facility_levels,
        )
        data.add(
            Operator(
                "芬",
                "room_1_1",
                current_room="dormitory_1",
                current_index=0,
                mood=20,
                time_stamp=NOW,
            )
        )
        data.mood_model.observe("芬", 20, NOW)
        data.facility_states = {
            room: {} for room in ("meeting", "contact", "factory", "train", "recycle")
        }
        return data

    return create


def test_two_empty_power_plants_use_level_one_recovery_and_deadline(owner):
    data = owner()
    saved = copy.deepcopy(data.facility_levels)
    value = sync_model(data, NOW)
    assert value.rooms["dormitory_1"]["level"] == 1
    assert value.rooms["room_1_1"]["level"] == 1
    assert value.rooms["room_1_3"]["level"] == 3
    assert value.rooms["central"]["level"] == 5
    for room in ("meeting", "contact", "factory", "train", "recycle"):
        assert value.rooms[room]["level"] == 3
    assert data.calculated_mood("芬", NOW + timedelta(hours=1)) == pytest.approx(22)
    assert data.calculated_mood_deadline("芬", 24, NOW) == NOW + timedelta(hours=2)
    assert data.facility_levels == saved


@pytest.mark.parametrize("level,rate", [(1, 2), (2, 2.5), (5, 4)])
def test_explicit_level_overrides_inference_and_changes_actual_forecast(
    owner, level, rate
):
    data = owner(levels={"dormitory_1": level, "meeting": 0, "contact": 1})
    value = sync_model(data, NOW)
    assert value.rooms["dormitory_1"]["level"] == level
    assert value.rooms["meeting"]["level"] == 0
    assert value.rooms["contact"]["level"] == 1
    assert data.calculated_mood("芬", NOW + timedelta(hours=1)) == pytest.approx(
        20 + rate
    )
    assert data.calculated_mood_deadline("芬", 24, NOW) == NOW + timedelta(
        hours=4 / rate
    )


@pytest.mark.parametrize(
    "levels,dorm_level,work_level,hours",
    [
        ({}, 5, 3, 1),
        ({"room_3_3": 0}, 1, 1, 2),
        ({"room_3_3": 0, "dormitory_1": 2, "room_1_1": 2}, 2, 2, 1.6),
    ],
)
def test_only_built_power_plants_control_unset_facility_levels(
    owner,
    levels,
    dorm_level,
    work_level,
    hours,
):
    data = owner(third_power=True, levels=levels)
    value = sync_model(data, NOW)
    assert value.rooms["dormitory_1"]["level"] == dorm_level
    assert value.rooms["room_1_1"]["level"] == work_level
    assert value.rooms["room_3_3"]["level"] == levels.get("room_3_3", 3)
    assert data.calculated_mood_deadline("芬", 24, NOW) == NOW + timedelta(hours=hours)


def test_active_backup_and_live_edit_do_not_change_startup_facility_defaults(
    owner, monkeypatch
):
    data = owner()
    data.plan["room_1_1"] = [Room("芬", "", [], facility="发电站")]
    data.facility_states["room_1_1"] = {"facility": "发电站"}
    monkeypatch.setattr(config.plan, "facility_levels", {"dormitory_1": 5})
    sync_model(data, NOW)
    assert data.mood_model.rooms["dormitory_1"]["level"] == 1
    assert data.calculated_mood_deadline("芬", 24, NOW) == NOW + timedelta(hours=2)


def test_restored_level_five_model_rebuilds_forecast_from_unchanged_observation(owner):
    data = owner()
    sync_model(data, NOW)
    data.mood_model.rooms["dormitory_1"]["level"] = 5
    assert data.mood_model.deadline("芬", 24, NOW) == NOW + timedelta(hours=1)
    data.mood_model = pickle.loads(pickle.dumps(data.mood_model)).restore()
    assert data.calculated_mood_deadline("芬", 24, NOW) == NOW + timedelta(hours=2)
    assert data.mood_model.rooms["dormitory_1"]["level"] == 1
    assert data.mood_model.observed["芬"] == NOW
    assert data.mood_model.moods["芬"] == 20


def test_observed_room_type_does_not_build_a_missing_room(owner):
    data = owner(levels={"dormitory_1": 0})
    sync_model(data, NOW)
    assert data.mood_model.rooms["dormitory_1"]["level"] == 0


def test_old_runtime_hash_discards_persisted_wrong_level_before_fresh_observation(
    owner,
):
    data = owner()
    sync_model(data, NOW)
    data.mood_model.rooms["dormitory_1"]["level"] = 5
    data.mood_model.rules_hash = "previous-runtime-with-level-five-default"
    data.mood_model = pickle.loads(pickle.dumps(data.mood_model)).restore()
    assert data.mood_model.moods == {}
    data.mood_model.observe("芬", 20, NOW)
    assert data.calculated_mood_deadline("芬", 24, NOW) == NOW + timedelta(hours=2)
