"""不养闲人按当前床位判断，不受干员字典插入顺序影响。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import try_add_release_dorm

ROOM = "dormitory_1"


@pytest.fixture
def op_data(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    config.conf.enable_mastery = False
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "meeting": [Room("银灰", "", ["红"])],
                    ROOM: [
                        Room(name, "", [])
                        for name in ["杜林", "闪灵", "爱丽丝", "桃金娘", "Free"]
                    ],
                },
                PlanConfig("", "", "", free_room=True),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    data.add(Operator("空爆", ""))
    for op in data.operators.values():
        op.mood = 24
        op.time_stamp = datetime.now()
    data.operators["红"].mood = 10
    occupant = data.operators["空爆"]
    occupant.current_room = ROOM
    occupant.current_index = 4
    data.dorm[0].name = occupant.name
    data.dorm[0].time = datetime.now() - timedelta(minutes=1)
    return data


@pytest.mark.parametrize("last", ["银灰", "红"])
def test_full_occupant_replaced_regardless_of_last_operator(op_data, last):
    op_data.operators[last] = op_data.operators.pop(last)
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert [task.plan for task in tasks] == [{ROOM: ["Current"] * 4 + ["红"]}]


def test_full_main_not_removed_by_free_room(op_data):
    occupant = op_data.operators["空爆"]
    occupant.operator_type = "high"
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks == []


def test_free_room_reads_dynamic_slot_countdown(op_data):
    assert op_data.get_refresh_index(ROOM, ["Current"] * 4 + ["空爆"]) == [4]


def test_repeated_planning_does_not_duplicate_bed_or_candidate(op_data):
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    try_add_release_dorm({}, None, op_data, tasks)
    assert len(tasks) == 1


def test_empty_dynamic_bed_also_accepts_waiting_operator(op_data):
    op_data.dorm[0].reset()
    op_data.operators["空爆"].current_room = ""
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"


@pytest.mark.parametrize(
    "excluded", ["blacklist", "workaholic", "full", "unknown", "working"]
)
def test_ineligible_waiting_operator_not_selected(op_data, excluded):
    op = op_data.operators["红"]
    if excluded == "blacklist":
        op_data.config.free_blacklist = [op.name]
    elif excluded == "workaholic":
        op.workaholic = True
    elif excluded == "full":
        op.mood = 24
    elif excluded == "unknown":
        op.time_stamp = None
    else:
        op.current_room = "train"
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks == []


def test_replacement_precedes_lower_mood_unplanned_operator(op_data):
    op_data.add(Operator("陈", "", mood=0, time_stamp=datetime.now()))
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"


def test_same_tier_compares_absolute_mood(op_data):
    op_data.add(Operator("陈", "", mood=12, lower_limit=10, time_stamp=datetime.now()))
    op_data.plan["meeting"][0].replacement.append("陈")
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"


@pytest.mark.parametrize("mood,expected", [(22, True), (22.01, False)])
def test_free_room_obeys_idle_takeover_limit(op_data, mood, expected):
    op_data.operators["空爆"].mood = 2
    op_data.dorm[0].time = datetime.now() + timedelta(hours=5)
    op_data.operators["红"].mood = mood
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert bool(tasks) == expected


def test_missing_countdown_in_explicit_plan_does_not_raise(op_data):
    op_data.dorm[0].time = None
    tasks = []
    try_add_release_dorm({ROOM: ["Free", "Current", "空爆"]}, None, op_data, tasks)
    try_add_release_dorm({ROOM: ["空爆"]}, datetime.now(), op_data, tasks)
    assert tasks == []


def test_active_training_operator_not_selected_even_with_stale_empty_room(
    op_data, monkeypatch
):
    from arknights_mower.utils import mastery_db

    config.conf.enable_mastery = True
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"char_name": "红"})
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks == []
