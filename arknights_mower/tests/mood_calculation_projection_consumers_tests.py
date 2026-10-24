"""救急周转与共享替班召回使用隔离的心情模型预演。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import exhaust_replacement_tests, mass_mood_recovery_tests
from arknights_mower.tests.mood_calculation_consumers_tests import set_e0_box
from arknights_mower.utils import calculated_mood, config, emergency_recovery
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.replacement_coordination import recall_can_sustain
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = mass_mood_recovery_tests.solver
recall_solver = exhaust_replacement_tests.solver
NOW = mass_mood_recovery_tests.NOW
PRIMARY = mass_mood_recovery_tests.PRIMARY
COVERS = mass_mood_recovery_tests.COVERS


def enable(data, now, monkeypatch, *, omitted=()):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(calculated_mood, "datetime", Clock)
    data.runtime_conf = config.conf.model_copy(deep=True)
    data.runtime_conf.test_mood_calculation = True
    set_e0_box(monkeypatch, data.operators)
    for room, slots in data.plan.items():
        if room.startswith("room_"):
            for slot in slots:
                slot.facility = "manufacture"
    for name, operator in data.operators.items():
        if name not in omitted:
            data.mood_model.observe(name, operator.mood, now)
    data.calculated_mood(next(iter(data.operators)), now)


def observations(data):
    return {
        name: (op.mood, op.time_stamp, op.current_room, op.current_index)
        for name, op in data.operators.items()
    }


def test_future_native_rotation_uses_model_recovery_deadline(solver, monkeypatch):
    data = solver.op_data
    required = data.operators[PRIMARY[0]]
    resident = data.operators[PRIMARY[1]]
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = resident.room, resident.index
    bed = data.dorm[0]
    resident._current_room, resident.current_index = bed.position
    resident.mood = required.mood = 12
    bed.name, bed.time = resident.name, None
    for name in COVERS[1:]:
        data.operators[name].mood = 0
    enable(data, NOW, monkeypatch)
    before = deepcopy(vars(data.mood_model)), observations(data)
    result = emergency_recovery.native_opportunity(solver, [required.name], NOW)
    # 五级宿舍基础恢复 4，E0 闪灵的「善解人意」增加 0.55；冰酿未解锁宿舍技能。
    assert result.complete and result.opportunity is not None
    assert (result.opportunity - NOW).total_seconds() == pytest.approx(12 / 4.55 * 3600)
    assert (vars(data.mood_model), observations(data)) == before
    assert bed.time is None
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("known", [False, True])
def test_future_native_task_uses_model_endurance_without_measured_rate(
    solver, monkeypatch, known
):
    data = solver.op_data
    required = data.operators[PRIMARY[0]]
    required.mood, required.depletion_rate = 12, 0
    for name in COVERS:
        data.operators[name].mood = 0
    solver.tasks = [
        SchedulerTask(
            time=NOW + timedelta(minutes=10),
            task_type=TaskTypes.SHIFT_OFF,
            task_plan={
                required.room: [COVERS[0]],
                "dormitory_1": [
                    "Current",
                    "Current",
                    required.name,
                    "Current",
                    "Current",
                ],
            },
        )
    ]
    enable(data, NOW, monkeypatch, omitted=() if known else (required.name,))
    before = deepcopy(vars(data.mood_model)), observations(data)
    result = emergency_recovery.native_opportunity(solver, [required.name], NOW)
    if known:
        assert result.complete and result.opportunity == NOW + timedelta(minutes=10)
    else:
        assert result.opportunity is None and not result.complete
    assert (vars(data.mood_model), observations(data)) == before


@pytest.mark.parametrize("blocked", [1, 2])
def test_calculated_fiammetta_charge_is_consumed_once_without_measured_write(
    solver, monkeypatch, blocked
):
    data = solver.op_data
    for name in PRIMARY[:blocked]:
        data.operators[name].mood = 0
    for name in COVERS[:blocked]:
        data.operators[name].mood = 0
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = "", -1
    data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        mood=8,
        time_stamp=NOW,
        operator_type="high",
        replacement=PRIMARY[:blocked],
    )
    solver.tasks = [
        SchedulerTask(
            time=NOW,
            task_type=TaskTypes.FIAMMETTA,
            task_plan={"dormitory_1": [target, "菲亚梅塔"]},
            meta_data=target,
        )
        for target in PRIMARY[:blocked]
    ]
    enable(data, NOW, monkeypatch)
    data.mood_model.observe("菲亚梅塔", 24, NOW)
    before = deepcopy(vars(data.mood_model)), observations(data)
    result = emergency_recovery.native_opportunity(
        solver, PRIMARY[:blocked], NOW, current_only=True
    )
    assert result.complete
    assert (result.opportunity == NOW) is (blocked == 1)
    assert (vars(data.mood_model), observations(data)) == before
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("low,unknown", [(False, False), (True, False), (False, True)])
def test_real_recall_forecast_uses_projected_model_without_rate_history(
    recall_solver, monkeypatch, low, unknown
):
    data = recall_solver.op_data
    now = datetime.now()
    if low:
        data.operators["苍苔"].mood = 1
    enable(data, now, monkeypatch, omitted=("絮雨",) if unknown else ())
    admitted = data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "room_3_3": ["槐琥"],
                "dormitory_1": ["Current", "Current", "机械师", "Free", "Free"],
            }
        ]
    )
    before = deepcopy(vars(data.mood_model)), observations(data)
    admitted_before = deepcopy(vars(admitted.mood_model)), observations(admitted)
    assert recall_can_sustain(
        data, admitted, ["苍苔", "絮雨"], ["机械师"], now=now
    ) is (not low and not unknown)
    assert (vars(data.mood_model), observations(data)) == before
    assert (vars(admitted.mood_model), observations(admitted)) == admitted_before
