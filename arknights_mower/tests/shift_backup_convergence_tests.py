"""上下班直接执行副表收敛后的最终阵容，避免红松/深海先换错站再纠错。"""

import copy
import pickle
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("薇薇安娜", "红松", ["陈"])],
                    "room_1_2": [
                        Room("野鬃", "红松", ["酒神"]),
                        Room("灰毫", "红松", ["食铁兽"]),
                    ],
                    "room_2_2": [
                        Room("乌尔比安", "深海", ["苍苔"]),
                        Room("安哲拉", "深海", ["引星棘刺"]),
                    ],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [
                Plan(
                    {
                        "room_1_2": [
                            Room("乌尔比安", "深海", ["酒神"]),
                            Room("安哲拉", "深海", ["食铁兽"]),
                        ],
                        "room_2_2": [
                            Room("野鬃", "红松", ["苍苔"]),
                            Room("灰毫", "红松", ["引星棘刺"]),
                        ],
                    },
                    PlanConfig("", "", ""),
                    trigger=LogicExpression(
                        "op_data.operators['薇薇安娜'].is_working()", "!=", "True"
                    ),
                    task={
                        "room_1_2": ["乌尔比安", "安哲拉"],
                        "room_2_2": ["苍苔", "引星棘刺"],
                    },
                )
            ],
        }
    )
    assert instance.op_data.init_and_validate() is None
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, datetime.now()
    instance.op_data.first_init = False
    instance.tasks, instance.task = [], None
    instance._sync_run_order_tasks = MagicMock()
    instance.queue_product_switches = MagicMock()
    instance.find = MagicMock(return_value=True)
    instance.skip = MagicMock()
    instance.refresh_connecting = False
    monkeypatch.setattr(
        Operators, "current_room_changed_callback", instance.current_room_changed
    )
    return instance


@pytest.fixture
def startup_waiting_backup(solver):
    factory = "room_3_1"
    group_factory = "room_3_2"
    group = "自动化"
    config = PlanConfig("", "", "")
    solver.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    factory: [Room("阿罗玛", "", ["娜斯提"], "制造站")],
                    group_factory: [
                        Room("森蚺", group, ["八幡海铃"], "制造站"),
                        Room("温蒂", group, ["娜斯提"], "制造站"),
                    ],
                    "room_1_2": [Room("薇薇安娜", "红松", ["陈"], "制造站")],
                    "room_1_3": [Room("槐琥", "", ["娜斯提"], "制造站")],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                config,
            ),
            "backup_plans": [
                Plan(
                    {factory: [Room("阿罗玛", "", ["多萝西"], "制造站")]},
                    config,
                    trigger=LogicExpression(
                        "op_data.operators['森蚺'].is_working()", "!=", "True"
                    ),
                )
            ],
        }
    )
    assert solver.op_data.init_and_validate() is None
    assert solver.op_data.swap_plan([True], refresh=True) is None
    solver.op_data.commit_group_shifts({group: True})
    for room in (factory, group_factory):
        solver._reconcile_room_observation(
            room, [{"agent": "", "mood": -1} for _ in solver.op_data.plan[room]]
        )
    waiting = SchedulerTask(
        time=datetime.now() - timedelta(seconds=10),
        task_plan={
            factory: ["阿罗玛"],
            group_factory: ["森蚺", "温蒂"],
            "room_1_3": ["娜斯提"],
        },
        task_type=TaskTypes.RE_ORDER,
        meta_data="副表内存收敛",
    )
    correction = SchedulerTask(
        task_plan={factory: ["多萝西"], group_factory: ["森蚺", "温蒂"]},
        task_type=TaskTypes.SELF_CORRECTION,
    )
    correction.initial_staffing = correction.derived_correction = True
    solver.tasks = [correction]
    solver.task = correction
    solver._suspend_group_shift(waiting, {group})
    return correction, waiting, factory, group_factory, group


@pytest.mark.parametrize("resume", [False, True])
def test_startup_correction_can_release_unstarted_backup_wait(
    solver, startup_waiting_backup, resume
):
    correction, waiting, factory, group_factory, group = startup_waiting_backup
    before_waiting = copy.deepcopy(waiting.__dict__)
    original_time = correction.time
    if resume:
        solver._retain_failed_task(
            correction, "副表换班暂缓", (factory, group_factory), dependency=True
        )
        solver._resume_failed_tasks()
        assert correction.execution_failure
        solver._reconcile_room_observation(factory, [{"agent": "", "mood": -1}])
        solver._resume_failed_tasks()
        assert not correction.retains_execution
    solver._prepare_group_shift(correction)
    solver._prepare_shift_cycle(correction)

    assert correction.plan[group_factory] == ["森蚺", "温蒂"]
    assert correction.plan[factory][0] in {"阿罗玛", "娜斯提"}
    assert correction.backup_shift_conditions == [False]
    assert correction.group_shift_transitions[group] is False
    assert correction.time == original_time
    assert solver.op_data.plan_condition == [True]
    assert solver.op_data.group_is_resting(group)
    assert solver.op_data.get_current_operator(factory, 0) is None
    assert solver.op_data.get_current_operator(group_factory, 0) is None
    assert solver.waiting_group_shifts[0] is waiting
    assert waiting.__dict__ == before_waiting


@pytest.mark.parametrize("extra_work", [False, True])
def test_confirmed_startup_correction_retires_superseded_backup_targets(
    solver, startup_waiting_backup, extra_work
):
    correction, waiting, factory, group_factory, _ = startup_waiting_backup
    independent_room = "room_1_2"
    resident = solver.op_data.operators["薇薇安娜"]
    resident.current_room, resident.current_index = independent_room, 0
    resident.mood, resident.time_stamp = 24, datetime.now()
    if extra_work:
        waiting.plan[independent_room] = ["陈"]
    waiting.backup_explicit_slots = {
        (room, index)
        for room, row in waiting.plan.items()
        for index, name in enumerate(row)
        if name != "Current"
    }
    original_waiting = copy.deepcopy(waiting.__dict__)
    solver._prepare_group_shift(correction)
    solver._prepare_shift_cycle(correction)
    solver._activate_shift_backup(correction)
    solver._prepare_group_shift(correction, remember_targets=True)
    final = copy.deepcopy(correction.plan)
    assert final[factory] == ["阿罗玛"]
    assert final["room_1_3"] == ["槐琥"]
    assert independent_room not in final
    assert final[group_factory] == ["森蚺", "温蒂"]
    assert not solver._complete_group_shift(correction)
    assert waiting.__dict__ == original_waiting
    assert solver.waiting_group_shifts == [waiting]

    solver.op_data = solver.op_data.project_arrangements([final])
    assert solver._complete_group_shift(correction)
    assert not solver.waiting_group_shifts
    if extra_work:
        assert any(task is waiting for task in solver.tasks)
        assert waiting.plan == {independent_room: ["陈"]}
        assert waiting.backup_explicit_slots == {(independent_room, 0)}
        assert waiting.time == original_waiting["time"]
    else:
        assert all(task is not waiting for task in solver.tasks)


@pytest.mark.parametrize("protected", ["started", "additional_group"])
def test_startup_correction_keeps_other_backup_reservations(
    solver, startup_waiting_backup, protected
):
    correction, waiting, factory, group_factory, _ = startup_waiting_backup
    if protected == "started":
        waiting.mood_physical_started = True
    else:
        waiting.group_shift_waiting.add("红松")
        solver.op_data.commit_group_shifts({"红松": True})
    before_waiting = copy.deepcopy(waiting.__dict__)
    solver._prepare_group_shift(correction)
    with pytest.raises(base.ProductSwitchDeferred, match="无法为阿罗玛匹配替班"):
        solver._prepare_shift_cycle(correction)

    assert correction.plan == {factory: ["多萝西"], group_factory: ["森蚺", "温蒂"]}
    assert waiting.__dict__ == before_waiting


def downshift(solver, kind=TaskTypes.SHIFT_OFF):
    task = SchedulerTask(
        task_type=kind,
        task_plan={
            "central": ["陈"],
            "room_1_2": ["酒神", "食铁兽"],
            "dormitory_1": ["Current", "Current", "薇薇安娜", "野鬃", "灰毫"],
        },
    )
    solver.tasks = [task]
    solver.task = task
    return task


def resting(solver):
    data = solver.op_data
    assert data.swap_plan([True], refresh=True) is None
    solver.op_data = data.project_arrangements(
        [
            {
                "central": ["陈"],
                "room_1_2": ["乌尔比安", "安哲拉"],
                "room_2_2": ["苍苔", "引星棘刺"],
                "dormitory_1": ["杜林", "桃金娘", "薇薇安娜", "野鬃", "灰毫"],
            }
        ]
    )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            "central": ["薇薇安娜"],
            "room_2_2": ["野鬃", "灰毫"],
        },
    )
    solver.tasks = [task]
    solver.task = task
    return task


def positions(data):
    return {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }


@pytest.mark.parametrize("cross_room", [False, True])
@pytest.mark.parametrize("group", ["", "红松", "深海"])
def test_changed_dorm_posts_follow_final_group_state(solver, cross_room, group):
    plans = copy.deepcopy(solver.op_data.global_plan)
    main = plans["default_plan"].plan
    main["dormitory_1"][0] = Room("杜林", group, ["梓兰"] if group else [])
    if cross_room:
        main["dormitory_2"] = [
            Room("安赛尔", "", []),
            Room("嘉维尔", "", []),
            *[Room("Free", "", []) for _ in range(3)],
        ]
    target_room, target_index = ("dormitory_2", 0) if cross_room else ("dormitory_1", 1)
    new_dorms = {
        room: copy.deepcopy(slots)
        for room, slots in main.items()
        if room.startswith("dorm")
    }
    new_dorms["dormitory_1"][0], new_dorms[target_room][target_index] = (
        new_dorms[target_room][target_index],
        new_dorms["dormitory_1"][0],
    )
    plans["backup_plans"][0].plan.update(new_dorms)
    solver.op_data = Operators(plans)
    assert solver.op_data.init_and_validate() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, datetime.now()
    solver.op_data.first_init = False
    task = downshift(solver)
    # 红松下班时，绑组宿管已在原换班意图中交给替班。
    if group == "红松":
        task.plan["dormitory_1"][0] = "梓兰"
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    expected = "梓兰" if group == "红松" else "杜林"
    assert task.plan[target_room][target_index] == expected
    assert task.plan["dormitory_1"][0] == ("安赛尔" if cross_room else "桃金娘")
    assert positions(solver.op_data) == before
    solver._activate_shift_backup(task)
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    assert not solver.agent_get_mood(read_rooms=False, return_plan=True)

    # 回班同样先退出副表，宿舍成员直接回主表位置。
    return_plan = {}
    for name in solver.op_data.groups["红松"]:
        op = solver.op_data.operators[name]
        return_plan.setdefault(
            op.room, ["Current"] * len(solver.op_data.plan[op.room])
        )[op.index] = name
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan=return_plan)
    solver.task, solver.tasks = task, [task]
    solver._prepare_shift_backup(task)
    assert task.plan["dormitory_1"][0] == "杜林"
    assert task.plan[target_room][target_index] == (
        "安赛尔" if cross_room else "桃金娘"
    )
    solver._activate_shift_backup(task)
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    assert not solver.agent_get_mood(read_rooms=False, return_plan=True)


@pytest.mark.parametrize("kind", [TaskTypes.SHIFT_OFF, TaskTypes.EXHAUST_OFF])
def test_downshift_merges_backup_actions_without_first_installing_replacements(
    solver, kind
):
    task = downshift(solver, kind)
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    assert task.plan["room_1_2"] == ["乌尔比安", "安哲拉"]
    assert task.plan["room_2_2"] == ["苍苔", "引星棘刺"]
    assert task.plan["dormitory_1"][2:] == ["薇薇安娜", "野鬃", "灰毫"]
    assert task.backup_shift_conditions == [True]
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    assert solver.tasks == [task]


@pytest.mark.parametrize(
    "kind", [TaskTypes.SHIFT_ON, TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER]
)
def test_upshift_skips_backup_posts_and_returns_directly_to_main_posts(solver, kind):
    task = resting(solver)
    task.type = kind
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    assert task.plan["room_1_2"] == ["野鬃", "灰毫"]
    assert task.plan["room_2_2"] == ["乌尔比安", "安哲拉"]
    assert task.backup_shift_conditions == [False]
    assert positions(solver.op_data) == before
    assert solver.op_data.plan_condition == [True]
    names = [
        name
        for agents in task.plan.values()
        for name in agents
        if name not in ("Current", "Free", "")
    ]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("kind", [TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER])
def test_correction_executes_final_main_posts_without_intermediate_backup_posts(
    solver, kind
):
    task = resting(solver)
    task.type = kind
    # 本例仅验证回班岗位；低心情下一组同步下班由完整轮休测试覆盖。
    for name in solver.op_data.groups["深海"]:
        solver.op_data.operators[name].mood = 24
    solver.plan_metadata = MagicMock()

    def arrange(plan, get_time):
        assert solver.op_data.plan_condition == [False]
        assert plan["room_1_2"] == ["野鬃", "灰毫"]
        assert plan["room_2_2"] == ["乌尔比安", "安哲拉"]
        solver.op_data = solver.op_data.project_arrangements([plan])
        plan.clear()

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.infra_main()
    solver.agent_arrange.assert_called_once()
    assert solver.op_data.operators["野鬃"].current_room == "room_1_2"
    assert solver.op_data.operators["乌尔比安"].current_room == "room_2_2"
    assert not any(t.plan for t in solver.tasks)


def test_backup_actions_can_trigger_another_backup_before_any_real_arrangement(solver):
    bp = Plan(
        {},
        PlanConfig("", "", ""),
        trigger=LogicExpression(
            "op_data.operators['乌尔比安'].current_room", "==", "'room_1_2'"
        ),
        task={"dormitory_1": ["桃金娘", "杜林", "Current", "Current", "Current"]},
    )
    solver.op_data.backup_plans.append(bp)
    solver.op_data.plan_condition.append(False)
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    assert task.backup_shift_conditions == [True, True]
    assert task.plan["dormitory_1"][:2] == ["桃金娘", "杜林"]
    assert solver.op_data.plan_condition == [False, False]


def test_cycle_keeps_live_state_queue_and_original_task_unchanged(solver, monkeypatch):
    info = MagicMock()
    monkeypatch.setattr(base.logger, "info", info)
    solver.op_data.backup_plans[0].task["central"] = ["薇薇安娜"]
    solver.op_data.backup_plans.append(
        Plan(
            {},
            PlanConfig("", "", ""),
            trigger=LogicExpression(
                "op_data.operators['薇薇安娜'].is_working()", "==", "True"
            ),
            task={"central": ["陈"]},
        )
    )
    solver.op_data.plan_condition.append(False)
    task = downshift(solver)
    original = copy.deepcopy(task.plan)
    before = positions(solver.op_data)
    with pytest.raises(ValueError, match="循环"):
        solver._prepare_shift_backup(task)
    assert task.plan == original
    assert solver.op_data.plan_condition == [False, False]
    assert positions(solver.op_data) == before
    assert not hasattr(task, "backup_shift_active")
    records = [call for call in info.call_args_list if "收敛演算耗时" in call.args[0]]
    assert len(records) == 1
    assert records[0].args[1] == "上下班副表"
    assert records[0].args[3].startswith("上下班副表 ")
    assert int(records[0].args[3].split()[1]) > 1
    assert records[0].args[4] == "异常中断（ValueError）"
    assert base._backup_timing_runtime.current is None


def test_activation_changes_configuration_but_never_fakes_actual_positions(solver):
    task = resting(solver)
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    assert not solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False]
    # 宿舍延期或换人失败后重试，保持同一个最终方案。
    expected = copy.deepcopy(task.plan)
    solver._prepare_shift_backup(task)
    assert task.plan == expected
    solver.plan_metadata()
    assert solver.tasks == [task]


def test_another_shift_waits_for_partially_completed_transaction(solver):
    active = resting(solver)
    solver._prepare_shift_backup(active)
    solver._activate_shift_backup(active)
    other = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={"central": ["陈"]})
    solver.tasks.append(other)
    with pytest.raises(base.ProductSwitchDeferred, match="上一轮"):
        solver._prepare_shift_backup(other)
    assert other.plan == {"central": ["陈"]}


def test_product_delay_keeps_real_configuration_and_all_actions_pending(solver):
    task = downshift(solver)
    intent = copy.deepcopy(task.plan)
    before = positions(solver.op_data)
    solver._switch_products_before_arrangement = MagicMock(
        side_effect=base.ProductSwitchDeferred(
            "等待切产物", ready_at=datetime.now() + timedelta(minutes=5)
        )
    )
    solver.agent_arrange = MagicMock()
    solver.infra_main()
    assert not getattr(task, "backup_shift_active", False)
    assert task in solver.tasks
    assert task.backup_shift_intent["central"] == intent["central"]
    assert task.backup_shift_intent["dormitory_1"] == intent["dormitory_1"]
    assert task.backup_shift_intent["room_1_2"] == ["乌尔比安", "安哲拉"]
    assert task.backup_shift_intent["room_2_2"] == ["苍苔", "引星棘刺"]
    assert task.backup_explicit_slots >= {
        ("room_1_2", 0),
        ("room_1_2", 1),
        ("room_2_2", 0),
        ("room_2_2", 1),
    }
    assert task.time > datetime.now() + timedelta(minutes=4)
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    solver.agent_arrange.assert_not_called()


def test_failed_arrangement_retains_final_task_for_retry(solver):
    task = resting(solver)
    solver.agent_arrange = MagicMock(side_effect=RuntimeError("读屏失败"))
    solver.infra_main()
    assert task in solver.tasks
    assert task.backup_shift_active
    assert not solver.backup_plan_solver()
    assert task.plan["room_1_2"] == ["野鬃", "灰毫"]


def test_restart_restores_active_transaction_configuration_without_replaying_intent(
    solver,
):
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    task.plan.pop("central")  # 已确认的工作房间不应在重启后重做。
    task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task]
    solver.task = task
    assert solver.op_data.swap_plan([False], refresh=True) is None
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    assert solver.op_data.plan_condition == [True]
    assert "central" not in task.plan
    assert positions(solver.op_data) == before


def test_prepared_shift_waits_if_fiammetta_becomes_due(solver):
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    solver.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    with pytest.raises(base.ProductSwitchDeferred, match="肥鸭"):
        solver._prepare_shift_backup(task)
    assert solver.op_data.plan_condition == [False]


def test_cancel_old_return_also_invalidates_saved_simulation_intent(solver):
    task = resting(solver)
    solver._prepare_shift_backup(task)
    solver.task = None
    solver.op_data.update_detail("野鬃", 20, "room_1_2", 0, True)
    assert all("野鬃" not in names for names in task.plan.values())
    assert not hasattr(task, "backup_shift_intent")
    assert not hasattr(task, "backup_shift_conditions")
    solver._prepare_shift_backup(task)
    assert all(
        "野鬃" not in names or room == "room_1_2" for room, names in task.plan.items()
    )


@pytest.mark.parametrize("direction", [downshift, resting])
def test_infra_main_executes_only_one_final_arrangement(solver, direction):
    task = direction(solver)
    seen = []

    def arrange(plan, get_time):
        seen.append(copy.deepcopy(plan))
        solver.op_data = solver.op_data.project_arrangements([plan])
        return True

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.infra_main()
    assert len(seen) == 1
    expected = ["乌尔比安", "安哲拉"] if direction is downshift else ["野鬃", "灰毫"]
    assert seen[0]["room_1_2"] == expected
    assert not any(t.meta_data == "副表内存收敛" for t in solver.tasks)
    assert not task.backup_shift_active


def test_product_lock_keeps_converged_shift_as_one_transaction(solver):
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    solver._reserve_deferred_product_shift(task, {("central", 0)})
    assert solver.tasks == [task]
    assert task.product_lock_slots == {
        (room, index)
        for room, names in task.plan.items()
        for index, name in enumerate(names)
        if name != "Current"
    }
    assert solver.op_data.plan_condition == [False]


@pytest.mark.parametrize("kind", [TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER])
def test_special_tasks_are_not_simulated_as_normal_shifts(solver, kind):
    task = downshift(solver, kind)
    original = copy.deepcopy(task.plan)
    solver._prepare_shift_backup(task)
    assert task.plan == original
    assert not hasattr(task, "backup_shift_conditions")


def test_due_fiammetta_defers_convergence_until_finished(solver):
    task = downshift(solver)
    solver.tasks.append(
        SchedulerTask(
            task_type=TaskTypes.FIAMMETTA, time=datetime.now() - timedelta(seconds=1)
        )
    )
    solver._prepare_shift_backup(task)
    assert not hasattr(task, "backup_shift_conditions")
    solver.tasks.pop()
    solver._prepare_shift_backup(task)
    assert hasattr(task, "backup_shift_conditions")


def test_group_selection_is_committed_only_with_final_shift(solver):
    backup = solver.op_data.backup_plans[0]
    backup.group_ids = ["rest"]
    solver.op_data.backup_groups = [
        {
            "id": "rest",
            "name": "休息",
            "trigger": {
                "left": "op_data.operators['薇薇安娜'].is_resting()",
                "operator": "==",
                "right": "True",
            },
        }
    ]
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    assert task.backup_shift_conditions == [True]
    assert task.backup_group == ("default", "rest")
    assert solver.op_data.backup_group == "default"
    assert solver.op_data.plan_condition == [False]
    solver._activate_shift_backup(task)
    assert solver.op_data.backup_group == ("default", "rest")
    assert solver.op_data.plan_condition == [True]


def test_failed_group_transition_restores_selection_and_flags(solver):
    solver.op_data.backup_groups = [
        {
            "id": "new",
            "name": "新分组",
            "trigger": {"left": "True", "operator": "==", "right": "True"},
        }
    ]
    backup = solver.op_data.backup_plans[0]
    backup.group_ids = ["new"]
    backup.trigger = LogicExpression("True", "==", "True")
    solver._backup_transition_plan = MagicMock(
        side_effect=ValueError("injected transition failure")
    )
    assert not solver.backup_plan_solver()
    assert solver.op_data.backup_group == "default"
    assert solver.op_data.plan_condition == [False]


def test_direct_selection_remembers_group_with_no_active_backup(solver):
    solver.op_data.backup_groups = [
        {
            "id": "empty",
            "name": "空分组",
            "trigger": {"left": "True", "operator": "==", "right": "True"},
        }
    ]
    assert not solver.backup_plan_solver()
    assert solver.op_data.backup_group == ("default", "empty")
    assert solver.op_data.plan_condition == [False]


def test_full_shift_emits_one_timing_for_nested_backup_rounds(solver, monkeypatch):
    info = MagicMock()
    monkeypatch.setattr(base.logger, "info", info)
    task = downshift(solver)

    solver._prepare_shift_cycle(task)

    records = [call for call in info.call_args_list if "收敛演算耗时" in call.args[0]]
    assert len(records) == 1
    assert records[0].args[1] == "完整换班"
    assert "完整换班" in records[0].args[3]
    assert "上下班副表" in records[0].args[3]
    assert records[0].args[4] == "已收敛"
    assert task.backup_shift_conditions == [True]
    assert base._backup_timing_runtime.current is None


def test_concurrent_group_state_survives_complete_shift_and_saved_task(solver):
    first = solver.op_data.backup_plans[0]
    first.group_ids = ["rest"]
    first.backup_type = "exclusive"
    other = Plan(
        {},
        PlanConfig("", "", ""),
        trigger=LogicExpression("True", "==", "True"),
        group_ids=["parallel"],
        backup_type="exclusive",
    )
    solver.op_data.backup_plans.append(other)
    solver.op_data.plan_condition.append(False)
    solver.op_data.backup_groups = [
        {
            "id": "rest",
            "name": "休息",
            "trigger": {"left": "op_data.operators['薇薇安娜'].is_resting()"},
            "exclusive_with": [],
        },
        {
            "id": "parallel",
            "name": "并行",
            "trigger": {"left": "True"},
            "exclusive_with": [],
        },
    ]
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    assert task.backup_shift_conditions == [True, True]
    assert task.backup_group == ("default", "rest", "parallel")
    assert solver.op_data.backup_group == "default"
    task = pickle.loads(pickle.dumps(task))
    solver._activate_shift_backup(task)
    assert solver.op_data.backup_group == ("default", "rest", "parallel")
    assert solver.op_data.plan_condition == [True, True]
    before = (
        list(task.backup_shift_conditions),
        task.backup_group,
        copy.deepcopy(task.plan),
    )
    solver._prepare_shift_backup(task)
    assert (task.backup_shift_conditions, task.backup_group, task.plan) == before
