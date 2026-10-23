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


@pytest.mark.parametrize("reading", ["unknown", "predicted", "future", "full"])
def test_card_estimate_cannot_replace_measured_recovery_need(incident, reading):
    data = incident
    candidate = data.operators["九色鹿"]
    candidate.current_room, candidate.current_index = "", -1
    if reading == "unknown":
        candidate.time_stamp = None
    elif reading == "predicted":
        candidate.mood_is_prediction = True
    elif reading == "future":
        candidate.time_stamp = datetime.now() + timedelta(hours=1)
    else:
        candidate.mood = 24
    data.dorm_mood_estimates = {candidate.name: (10, datetime.now())}
    assert not resting_priority.bed_takeover_allowed(data, candidate.name, "Mon3tr")


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
@pytest.mark.parametrize(
    "reading", ["unknown", "predicted", "future", "full", "measured"]
)
def test_full_priority_resident_requires_measured_applicant_in_every_tier(
    incident, tier, reading
):
    data = incident
    data.config.free_blacklist = ["九色鹿"]
    data.config.ope_resting_priority = ["Mon3tr"]
    candidate = data.operators["斑点"]
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
    if reading == "unknown":
        candidate.time_stamp = None
    elif reading == "predicted":
        candidate.mood_is_prediction = True
    elif reading == "future":
        candidate.time_stamp = datetime.now() + timedelta(hours=1)
    elif reading == "full":
        candidate.mood = candidate.upper_limit
    data.dorm_mood_estimates = {candidate.name: (10, datetime.now())}
    allowed = reading == "measured"
    assert (
        resting_priority.bed_takeover_allowed(data, candidate.name, "Mon3tr") is allowed
    )
    if candidate.is_high():
        bed = data.assign_dorm(candidate.name)
        assert (bed is not None) is allowed
        if allowed:
            assert bed.position == (ROOM, 4)
        return
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    if allowed:
        assert len(tasks) == 1
        assert tasks[0].plan[ROOM] == ["Current"] * 4 + [candidate.name]
    else:
        assert tasks == []
    assert data.operators["Mon3tr"].current_room == ROOM


@pytest.mark.parametrize("name", ["九色鹿", "Mon3tr", "杜林"])
def test_any_operator_can_use_configured_standby_recovery_tier(incident, name):
    data = incident
    data.config.resting_standby = [name]
    data.operators[name].mood = 10
    assert resting_tier(data, name) == RestingTier.STANDBY


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
