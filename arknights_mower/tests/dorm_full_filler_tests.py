from datetime import datetime, timedelta

import pytest

from arknights_mower.utils import config, resting_priority
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import try_add_release_dorm

ROOM = "dormitory_4"


@pytest.fixture
def incident(monkeypatch, offline_maintenance):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "meeting": [Room("银灰", "", ["Mon3tr", "斑点"])],
                    ROOM: [
                        Room(name, "", [])
                        for name in ["杜林", "闪灵", "爱丽丝", "Free", "Free"]
                    ],
                },
                PlanConfig("", "", "", free_room=True),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    data.add(Operator("九色鹿", ""))
    monkeypatch.setattr(resting_priority, "agent_list", list(data.operators))
    now = datetime.now()
    for op in data.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 24, now, 0
    data.operators["九色鹿"].mood = 14.17
    data.operators["斑点"].mood = 15.17
    for index, name in enumerate(["杜林", "闪灵", "爱丽丝", "九色鹿", "Mon3tr"]):
        op = data.operators[name]
        op.current_room, op.current_index = ROOM, index
    for bed, name in zip(data.dorm, ["九色鹿", "Mon3tr"]):
        bed.name = name
        bed.time = now + timedelta(hours=4) if name == "九色鹿" else now
    data.operators["Mon3tr"].dorm_mood_fallback = ROOM
    return data


def test_recovery_replaces_full_filler_before_unfinished_resident(incident):
    data = incident
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    projected = data.project_arrangements([tasks[0].plan])
    assert {bed.name for bed in projected.dorm} == {"斑点", "九色鹿"}
    assert projected.operators["Mon3tr"].current_room == ""
    assert resting_tier(data, "Mon3tr") == RestingTier.IDLE
    assert resting_tier(data, "斑点") == RestingTier.REPLACEMENT
    assert resting_tier(data, "九色鹿") == RestingTier.IDLE


@pytest.mark.parametrize("free_room", [False, True])
def test_full_fallback_yields_to_known_tired_idle(incident, free_room):
    data = incident
    data.config.free_room = free_room
    data.operators["九色鹿"].current_room = ""
    data.operators["九色鹿"].current_index = -1
    op = data.operators["斑点"]
    op.current_room, op.current_index = ROOM, 3
    data.dorm[0].name = "斑点"
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    assert tasks[0].plan[ROOM] == ["Current"] * 4 + ["九色鹿"]
    projected = data.project_arrangements([tasks[0].plan])
    assert projected.operators["Mon3tr"].current_room == ""
    assert projected.operators["九色鹿"].is_resting()
    for _ in range(3):
        repeated = []
        try_add_release_dorm({}, None, projected, repeated)
        assert repeated == []


def test_real_standby_is_above_ordinary_replacement(incident):
    data = incident
    op = data.operators["银灰"]
    op.mood = 10
    op.resting_priority = "standby"
    assert resting_tier(data, op.name) == RestingTier.STANDBY
    assert resting_tier(data, op.name) < resting_tier(data, "Mon3tr")


def test_standby_configuration_applies_to_non_primary(incident):
    data = incident
    data.config.resting_standby = ["九色鹿"]
    data.add(Operator("九色鹿", ""))
    assert not data.operators["九色鹿"].is_high()
    assert resting_tier(data, "九色鹿") == RestingTier.STANDBY


@pytest.mark.parametrize("reserved", ["name", "bed"])
def test_full_filler_replacement_respects_reservations(incident, reserved):
    data = incident
    data.config.free_blacklist = ["九色鹿"]
    tasks = []
    kwargs = (
        {"reserved_names": {"斑点"}}
        if reserved == "name"
        else {"reserved_slots": {(ROOM, 4)}}
    )
    try_add_release_dorm({}, None, data, tasks, **kwargs)
    assert tasks == []


def test_full_filler_does_not_yield_to_unknown_mood(incident):
    data = incident
    data.config.free_blacklist = ["九色鹿"]
    data.operators["斑点"].time_stamp = None
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []


def test_primary_bed_assignment_also_prefers_full_filler(incident):
    data = incident
    primary = data.operators["银灰"]
    primary.mood = 0
    bed = data.assign_dorm(primary.name)
    assert bed is not None
    assert bed.position == (ROOM, 4)


@pytest.mark.parametrize(
    "tier",
    [
        "explicit",
        "main",
        "low_main",
        "priority_replacement",
        "standby",
        "replacement",
        "idle",
    ],
)
@pytest.mark.parametrize("upper", [12, 24])
@pytest.mark.parametrize(
    "source",
    [
        "measured",
        "card_only",
        "predicted",
        "future_reading",
        "old_full_reading",
        "unknown",
        "expired",
        "future_estimate",
        "full_estimate",
        "newer_full_reading",
    ],
)
def test_full_priority_resident_accepts_valid_scheduling_mood(
    incident, tier, upper, source
):
    data = incident
    data.config.free_blacklist = ["九色鹿"]
    data.config.ope_resting_priority = ["Mon3tr"]
    candidate = data.operators["斑点"]
    now = datetime.now()
    candidate.upper_limit, candidate.mood = upper, 5
    candidate.time_stamp = now - timedelta(minutes=5)
    if upper < 24:
        data.config.operator_mood_limits[candidate.name] = {"lower": 0, "upper": upper}
    if tier == "explicit":
        data.config.ope_resting_priority.append(candidate.name)
    elif tier in ("main", "low_main"):
        candidate.operator_type, candidate.room = "high", "meeting"
        candidate.resting_priority = "low" if tier == "low_main" else "high"
    elif tier == "priority_replacement":
        data.config.resting_priority_replacement = [candidate.name]
    elif tier == "standby":
        data.config.resting_standby = [candidate.name]
    elif tier == "idle":
        data.plan["meeting"][0].replacement = ["Mon3tr"]
    if source != "measured":
        data.dorm_mood_estimates = {candidate.name: (5, now - timedelta(minutes=1))}
    if source in (
        "card_only",
        "unknown",
        "expired",
        "future_estimate",
        "full_estimate",
    ):
        candidate.time_stamp = None
    if source == "predicted":
        candidate.mood_is_prediction = True
    elif source == "future_reading":
        candidate.time_stamp = now + timedelta(hours=1)
    elif source == "old_full_reading":
        candidate.mood = upper
    elif source == "unknown":
        data.dorm_mood_estimates = {}
    elif source == "expired":
        data.dorm_mood_estimates[candidate.name] = (5, now - timedelta(hours=1))
    elif source == "future_estimate":
        data.dorm_mood_estimates[candidate.name] = (5, now + timedelta(minutes=1))
    elif source == "full_estimate":
        data.dorm_mood_estimates[candidate.name] = (upper, now - timedelta(minutes=1))
    elif source == "newer_full_reading":
        candidate.mood, candidate.time_stamp = upper, now - timedelta(seconds=10)
    sample = candidate.mood, candidate.time_stamp, candidate.mood_is_prediction
    allowed = source in (
        "measured",
        "card_only",
        "predicted",
        "future_reading",
        "old_full_reading",
    )
    assert (
        resting_priority.bed_takeover_allowed(data, candidate.name, "Mon3tr") is allowed
    )
    if candidate.is_high():
        bed = data.assign_dorm(candidate.name)
        assert (bed is not None) is allowed
        if allowed:
            assert bed.position == (ROOM, 4)
    else:
        tasks = []
        try_add_release_dorm({}, None, data, tasks)
        if allowed:
            assert len(tasks) == 1
            assert tasks[0].plan[ROOM] == ["Current"] * 4 + [candidate.name]
        else:
            assert tasks == []
    assert (
        candidate.mood,
        candidate.time_stamp,
        candidate.mood_is_prediction,
    ) == sample
    assert data.operators["Mon3tr"].current_room == ROOM


@pytest.mark.parametrize("name", ["九色鹿", "Mon3tr", "杜林"])
def test_any_operator_can_use_configured_standby_recovery_tier(incident, name):
    data = incident
    data.config.resting_standby = [name]
    data.operators[name].mood = 10
    assert resting_tier(data, name) == RestingTier.STANDBY


def test_estimated_candidate_is_not_assigned_to_two_full_beds(incident):
    data = incident
    data.operators["九色鹿"].mood = 24
    candidate = data.operators["斑点"]
    candidate.time_stamp = None
    data.dorm_mood_estimates = {candidate.name: (5, datetime.now())}
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    assert tasks[0].plan[ROOM].count(candidate.name) == 1
    assert tasks[0].plan[ROOM].count("Current") == 4
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1


def test_old_runtime_promotion_cannot_change_standby_tier(incident):
    import pickle

    data = incident
    data.config.resting_standby = ["银灰"]
    data.operators["银灰"].mood = 10
    data.operators["银灰"].standby_low_priority = True
    restored = pickle.loads(pickle.dumps(data))
    assert resting_tier(restored, "银灰") == RestingTier.STANDBY
    assert restored.standby_candidates(["银灰"]) == set()


@pytest.mark.parametrize("reading", ["unknown", "predicted", "future", "unfinished"])
def test_completed_filler_requires_confirmed_full_reading(incident, reading):
    data = incident
    data.config.free_blacklist = ["九色鹿"]
    resident = data.operators["Mon3tr"]
    if reading == "unknown":
        resident.time_stamp = None
    elif reading == "predicted":
        resident.mood_is_prediction = True
    elif reading == "future":
        resident.time_stamp = datetime.now() + timedelta(hours=1)
    else:
        resident.mood = 10
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []


@pytest.mark.parametrize("free_room", [False, True])
def test_non_primary_standby_wins_admission_before_ordinary_replacement(
    incident, free_room
):
    data = incident
    data.config.free_room = free_room
    data.config.resting_standby = ["九色鹿"]
    data.update_detail("九色鹿", 22, "", -1, True)
    data.operators["斑点"].mood = 5
    primary = data.operators["银灰"]
    primary.current_room, primary.current_index = ROOM, 3
    primary.mood = 10
    data.dorm[0].name = primary.name
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    projected = data.project_arrangements([tasks[0].plan])
    assert {bed.name for bed in projected.dorm} == {"银灰", "九色鹿"}
    assert projected.operators["斑点"].current_room == ""
    assert not projected.operators["九色鹿"].is_high()


@pytest.mark.parametrize(
    "priority", ["explicit", "main", "low_main", "replacement", "standby"]
)
@pytest.mark.parametrize("mood", [12, 13, 24])
@pytest.mark.parametrize("retained", [False, True])
def test_capped_dynamic_operators_lose_priority_unless_retained(
    incident, priority, mood, retained
):
    data = incident
    op = data.operators["Mon3tr"]
    op.upper_limit, op.mood = 12, mood
    op.current_room, op.current_index = "", -1
    expected = RestingTier.REPLACEMENT
    if priority == "explicit":
        data.config.ope_resting_priority = [op.name]
        expected = RestingTier.PRIORITY
    elif priority in ("main", "low_main"):
        op.operator_type, op.room = "high", "meeting"
        op.resting_priority = "low" if priority == "low_main" else "high"
        expected = RestingTier.LOW_MAIN if priority == "low_main" else RestingTier.MAIN
    elif priority == "replacement":
        data.config.resting_priority_replacement = [op.name]
        expected = RestingTier.PRIORITY_REPLACEMENT
    else:
        data.config.resting_standby = [op.name]
        expected = RestingTier.STANDBY
    if retained:
        data.config.free_room_exclusions = [op.name]
    assert resting_tier(data, op.name) == (expected if retained else RestingTier.IDLE)
    if not retained:
        assert resting_priority.resting_key(
            data, "九色鹿"
        ) < resting_priority.resting_key(data, op.name)
        assert not resting_priority.bed_takeover_allowed(data, op.name, "九色鹿")


@pytest.mark.parametrize("retained", [False, True])
def test_full_priority_resident_yields_only_outside_retention_list(incident, retained):
    data = incident
    data.config.ope_resting_priority = ["Mon3tr"]
    if retained:
        data.config.free_room_exclusions = ["Mon3tr"]
    data.config.free_blacklist = ["九色鹿"]
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert bool(tasks) is not retained
    if not retained:
        assert (
            data.project_arrangements([tasks[0].plan]).operators["Mon3tr"].current_room
            == ""
        )


def test_fixed_dormitory_primary_keeps_priority_at_cap(incident):
    data = incident
    op = data.operators["杜林"]
    assert op.mood == op.upper_limit
    assert resting_tier(data, op.name) == RestingTier.MAIN
    assert not resting_priority.is_full_dorm_filler(data, op.name)


def test_low_cap_full_priority_filler_ranks_after_tired_idle_candidate(incident):
    from arknights_mower.utils.dorm_candidates import dorm_candidates

    data = incident
    data.config.ope_resting_priority = ["Mon3tr"]
    full = data.operators["Mon3tr"]
    full.mood, full.upper_limit = 12, 12
    for bed in data.dorm:
        op = data.operators[bed.name]
        op.current_room, op.current_index = "", -1
        bed.reset()
    data.operators["九色鹿"].mood = 22
    data.operators["斑点"].mood = 24
    assert dorm_candidates(data).filling[0] == "九色鹿"
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    assert tasks[0].plan[ROOM][3] == "九色鹿"


def test_latest_card_cap_removes_priority_without_fabricating_real_reading(incident):
    data = incident
    data.config.ope_resting_priority = ["斑点"]
    op = data.operators["斑点"]
    data.dorm_mood_estimates = {op.name: (24, datetime.now())}
    assert resting_tier(data, op.name) == RestingTier.IDLE
    assert op.mood == 15.17
    assert not resting_priority.is_full_dorm_filler(data, op.name)


@pytest.mark.parametrize("upper", [12, 24])
def test_full_retained_primary_takes_completed_filler_bed(incident, upper):
    data = incident
    primary = data.operators["银灰"]
    primary.upper_limit = primary.mood = upper
    primary.resting_priority = "standby"
    data.config.resting_standby = [primary.name]
    data.config.free_room_exclusions = [primary.name]
    data.operators["斑点"].current_room = "meeting"
    data.operators["斑点"].current_index = 0
    primary.current_room, primary.current_index = "meeting", 0
    beds = data.assign_dorm_group([primary.name])
    assert beds is not None
    assert [bed.position for bed in beds] == [(ROOM, 4)]
    assert data.operators["九色鹿"].current_room == ROOM


@pytest.mark.parametrize(
    "restriction",
    ["primary", "priority_replacement", "retained", "excluded", "unknown"],
)
def test_full_retained_primary_keeps_resident_protections(incident, restriction):
    data = incident
    primary = data.operators["银灰"]
    primary.resting_priority = "standby"
    data.config.resting_standby = [primary.name]
    data.config.free_room_exclusions = [primary.name, "九色鹿"]
    if restriction == "primary":
        data.operators["Mon3tr"].operator_type = "high"
        data.operators["Mon3tr"].mood = 14
        data.operators["Mon3tr"].room = "meeting"
    elif restriction == "priority_replacement":
        data.config.resting_priority_replacement = ["Mon3tr"]
        data.operators["Mon3tr"].mood = 14
    elif restriction == "unknown":
        primary.time_stamp = None
    elif restriction == "retained":
        data.config.free_room_exclusions.append("Mon3tr")
    else:
        data.config.free_blacklist.append(primary.name)
    assert data.assign_dorm_group([primary.name]) is None


@pytest.mark.parametrize("mood", [5, 24])
@pytest.mark.parametrize("requester_priority", ["high", "standby"])
def test_retained_full_primary_uses_existing_takeover_tiers(
    incident, mood, requester_priority
):
    data = incident
    primary = data.operators["银灰"]
    primary.resting_priority = requester_priority
    data.config.resting_standby = ["Mon3tr"]
    data.config.free_room_exclusions = [primary.name, "九色鹿"]
    data.operators["Mon3tr"].mood = mood
    beds = data.assign_dorm_group([primary.name])
    if requester_priority == "standby" and mood < 24:
        assert beds is None
    else:
        assert beds is not None
        assert [bed.position for bed in beds] == [(ROOM, 4)]


@pytest.mark.parametrize("mood", [5, 24])
def test_retained_full_standby_can_displace_lower_tier(incident, mood):
    data = incident
    primary = data.operators["银灰"]
    primary.resting_priority = "standby"
    data.config.resting_standby = [primary.name]
    data.config.free_room_exclusions = [primary.name, "九色鹿"]
    data.operators["Mon3tr"].mood = mood
    beds = data.assign_dorm_group([primary.name])
    assert beds is not None
    assert [bed.position for bed in beds] == [(ROOM, 4)]


def test_retained_full_primary_respects_reserved_bed(incident):
    data = incident
    primary = data.operators["银灰"]
    data.config.free_room_exclusions = [primary.name, "九色鹿"]
    assert (
        data.assign_dorm_group([primary.name], reserved_slots={(ROOM, 3), (ROOM, 4)})
        is None
    )
