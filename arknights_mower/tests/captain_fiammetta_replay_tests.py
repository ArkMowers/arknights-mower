"""captain 9 月 27 日 20:52 排班与日志回放；仅替代设备交互。"""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture
def captain(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 27, 20, 52, 33)

        @classmethod
        def now(cls):
            return cls.current

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.experimental_dorm_logic = True
    config.conf.enable_mastery = False
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate_json(
            (FIXTURES / "captain_plan_20260927.json").read_text()
        ),
    )
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    state = json.loads((FIXTURES / "captain_fiammetta_state_20260927.json").read_text())
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(build_global_plan())
    assert solver.op_data.init_and_validate() is None
    assert solver.op_data.swap_plan(state["conditions"], refresh=True) is None
    for name, values in state["operators"].items():
        if name not in solver.op_data.operators:
            solver.op_data.add(Operator(name, ""))
        for key, value in values.items():
            if key == "time_stamp" and value:
                value = datetime.fromisoformat(value)
            setattr(solver.op_data.operators[name], key, value)
    for saved in state["dorms"]:
        for bed in solver.op_data.dorm:
            if tuple(saved["position"]) == bed.position:
                bed.name = saved["name"]
                bed.time = (
                    datetime.fromisoformat(saved["time"]) if saved["time"] else None
                )
    solver.op_data.first_init = False
    solver.clock = Clock
    solver.task, solver.tasks = None, []
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.refresh_connecting = False
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    solver.plan_metadata = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.scene = MagicMock(return_value=base.Scene.INFRA_MAIN)
    solver.log_state = state
    return solver


def logged_rest(solver):
    task = SchedulerTask(
        time=solver.clock.now() - timedelta(seconds=1),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan=copy.deepcopy(solver.log_state["shift_off"]),
    )
    solver.tasks.append(task)
    return task


def charged(solver):
    solver.clock.current = datetime(2026, 9, 27, 20, 53, 55)
    solver.op_data.update_detail("歌蕾蒂娅", 24, "central", 1, True)


def test_logged_charge_replaces_old_rest_in_one_final_arrangement(captain):
    old = logged_rest(captain)
    charged(captain)
    created = []
    assert captain.backup_plan_solver(generated_tasks=created)
    assert all(t is not old for t in captain.tasks)
    final = next(t for t in created if t.plan)
    deepsea = set(captain.op_data.groups["深海"])
    assert not any(
        deepsea & set(names)
        for room, names in final.plan.items()
        if room.startswith("dorm")
    )
    assert final.plan["central"][1] == "歌蕾蒂娅"
    assert final.plan["room_1_2"][:2] == ["乌尔比安", "斯卡蒂"]
    assert final.plan["room_3_1"][:2] == ["幽灵鲨", "安哲拉"]
    # 同批信仰搅拌机的正常下班保留。
    assert final.plan["meeting"] == ["陈", "Current"]
    assert "信仰搅拌机" in final.plan["dormitory_3"]
    seen = []

    def arrange(plan, get_time):
        seen.append(copy.deepcopy(plan))
        captain.op_data = captain.op_data.project_arrangements([plan])
        plan.clear()

    captain.task = final
    captain.agent_arrange = MagicMock(side_effect=arrange)
    captain.infra_main()
    assert len(seen) == 1
    assert seen[0]["central"][1] == "歌蕾蒂娅"
    assert captain.op_data.operators["歌蕾蒂娅"].current_room == "central"
    assert all(captain.op_data.operators[n].is_working() for n in deepsea)
    assert captain.op_data.operators["信仰搅拌机"].is_resting()


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.RUN_ORDER,
        TaskTypes.FIAMMETTA,
        TaskTypes.SWAP_SUPPORT,
        TaskTypes.SKILL_UPGRADE,
    ],
)
def test_backup_transition_keeps_special_sequences(captain, kind):
    old = logged_rest(captain)
    special = SchedulerTask(
        task_type=kind,
        task_plan={"central": ["Current", "歌蕾蒂娅"]},
        time=captain.clock.now() + timedelta(seconds=1),
    )
    captain.tasks.append(special)
    charged(captain)
    # FIAMMETTA 充能期间禁止切副表，在此直接验证队列合并边界。
    transition = {"central": ["Current", "歌蕾蒂娅", "Current", "Current", "Current"]}
    merged, superseded = captain._coalesce_backup_transition(transition)
    assert any(t is old for t in superseded)
    assert all(t is not special for t in superseded)
    assert merged["central"][1] == "歌蕾蒂娅"


@pytest.mark.parametrize("protected", ["future", "strict", "restore", "empty"])
def test_backup_transition_keeps_future_rest_and_safety_tasks(captain, protected):
    old = logged_rest(captain)
    if protected == "future":
        old.time += timedelta(hours=3)
    elif protected == "strict":
        old.strict_mood_limit = True
    elif protected == "restore":
        old.dorm_recovery_restore = ["dormitory_1"]
    else:
        old.plan = {}
    charged(captain)
    captain.backup_plan_solver()
    assert any(t is old for t in captain.tasks)


def test_due_charge_does_not_generate_rest_from_precharge_mood(captain):
    captain.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    captain.resting = MagicMock(side_effect=AssertionError("must wait for charge"))
    captain.plan_solver()
    assert not any(t.type == TaskTypes.SHIFT_OFF for t in captain.tasks)


def test_backed_off_old_task_is_still_replaced_by_new_backup(captain):
    old = logged_rest(captain)
    old.arrangement_retry_due_at = old.time
    old.time += timedelta(minutes=6)
    charged(captain)
    captain.backup_plan_solver()
    assert all(t is not old for t in captain.tasks)


def test_failed_room_yields_without_losing_remaining_rooms_or_charge(
    captain, monkeypatch
):
    monkeypatch.setattr(base, "save_exception", lambda error: None)
    old = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_2_2": ["阿罗玛", "苍苔", "砾"]},
    )
    fia = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    captain.tasks = [old, fia]
    captain.task = old
    captain._prepare_shift_backup = MagicMock()
    captain.agent_arrange = MagicMock(
        side_effect=base.RoomArrangementDeferred(
            "room_2_2", RuntimeError("empty names")
        )
    )
    captain.infra_main()
    assert captain.tasks[0] is fia
    assert old.time == captain.clock.now() + timedelta(minutes=1)
    assert old.plan == {"room_2_2": ["阿罗玛", "苍苔", "砾"]}
    assert old.arrangement_retry_count == 1
    captain.back_to_infrastructure.assert_called_once()
    for count in range(2, 8):
        captain.clock.current = old.time
        captain.task = old
        captain.infra_main()
        assert old.time == captain.clock.now() + timedelta(minutes=min(count, 5))
        assert any(t is fia for t in captain.tasks)


def test_overdue_correction_does_not_erase_fiammetta_reservation(captain):
    old = logged_rest(captain)
    old.time -= timedelta(minutes=20)
    fia = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, time=captain.clock.now() - timedelta(minutes=16)
    )
    order = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, time=captain.clock.now() + timedelta(minutes=10)
    )
    captain.tasks.extend([fia, order])
    captain.error = True
    captain.handle_error(force=True)
    assert any(t is fia for t in captain.tasks)
    assert any(t is order for t in captain.tasks)
    assert all(t is not old for t in captain.tasks)
    # 单独一条过期肥鸭任务不应每轮触发清队。
    before = [id(t) for t in captain.tasks]
    captain.handle_error(force=True)
    assert [id(t) for t in captain.tasks] == before


def test_partially_executed_old_shift_does_not_replay_completed_room(captain):
    old = logged_rest(captain)
    old.backup_shift_intent = copy.deepcopy(old.plan)
    old.backup_shift_active = True
    old.backup_shift_conditions = [False] * 5
    old.plan.pop("meeting")  # 此房间已执行，不能从旧意图重新带回。
    charged(captain)
    # 实际执行中的事务仍受原副表锁保护；合并工具只读取剩余计划。
    assert not captain.backup_plan_solver()
    transition = {"central": ["Current", "歌蕾蒂娅", "Current", "Current", "Current"]}
    final, superseded = captain._coalesce_backup_transition(transition)
    assert any(task is old for task in superseded)
    assert "meeting" not in final
    assert final["central"][1] == "歌蕾蒂娅"


def test_connected_old_tasks_converge_without_duplicate_operator(captain):
    old = logged_rest(captain)
    other = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_2_2": ["阿罗玛", "结城理", "Current"]},
    )
    # 第三条任务经由下班任务中的结城理与本轮副表产生关联。
    captain.tasks.insert(0, other)
    charged(captain)
    captain.backup_plan_solver()
    assert all(t is not old and t is not other for t in captain.tasks)
    final = next(t for t in captain.tasks if t.plan)
    assigned = [
        name
        for names in final.plan.values()
        for name in names
        if name not in ("Current", "Free", "")
    ]
    assert len(assigned) == len(set(assigned))
    assert "阿罗玛" in final.plan["room_2_2"]


def test_legacy_backup_keeps_existing_dispatch(captain):
    captain.op_data.config.experimental_dorm_logic = False
    captain._legacy_backup_plan_solver = MagicMock(return_value=True)
    captain._coalesce_backup_transition = MagicMock(
        side_effect=AssertionError("legacy")
    )
    assert captain.backup_plan_solver()
    captain._legacy_backup_plan_solver.assert_called_once()
