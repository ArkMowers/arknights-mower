"""肥鸭任务的明确名单不参与普通宿舍清退；选目标前补读失效心情。"""

from datetime import datetime, timedelta
from types import MethodType
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_group_tests
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "dormitory_1"
solver = dorm_group_tests.solver


def test_initial_charge_restoration_reenters_normal_planning(solver, monkeypatch):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils import scheduler_task

    class Clock(datetime):
        current = datetime(2026, 10, 6, 19, 51, 41, 669869)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    monkeypatch.setattr(base_schedule, "save_log", MagicMock())
    solver.find_next_task = MethodType(
        base_schedule.BaseSchedulerSolver.find_next_task, solver
    )
    future = SchedulerTask(
        time=Clock.now() + timedelta(hours=4), task_type=TaskTypes.SKILL_UPGRADE
    )
    solver.tasks = [future]
    solver.task = None
    solver.planned = solver.todo_task = solver.collect_notification = False
    solver.error = False
    solver.defer_backup_plan_until_mood_read = True
    solver.find = MagicMock(return_value=True)
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.recog = MagicMock()
    solver.check_current_focus = MagicMock()
    solver.party_time = solver.free_clue = solver.credit_fight = None
    solver._read_agent_mood = MagicMock()
    solver._read_initial_card_mood = MagicMock()
    solver._refresh_fia_candidate_moods = MagicMock()
    solver._refresh_deferred_product_reservations = MagicMock()
    solver._schedule_maintenance_backup_check = MagicMock()
    solver._sync_run_order_tasks = MagicMock()
    solver._fill_empty_dorms = MagicMock()
    solver.op_data.correct_dorm = MagicMock()
    solver.agent_get_mood = MagicMock(return_value=None)
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.queue_product_switches = MagicMock()
    solver.run_order_solver = MagicMock()
    solver.plan_solver = MagicMock(side_effect=solver.skip)
    target = solver.op_data.operators["伊内丝"]
    target.group, target.mood, target.time_stamp = "", 1, Clock.now()
    solver.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        ROOM,
        index=3,
        current_room=ROOM,
        current_index=3,
        mood=24,
        time_stamp=Clock.now(),
    )
    solver.check_fia = lambda: ([target.name], ROOM)
    monkeypatch.setattr(config.conf, "fia_fool", True)
    original = {ROOM: ["塑心", "冰酿", "泥岩", "菲亚梅塔", "年"]}
    solver.agent_arrange_room = MagicMock(side_effect=[original, {}])

    assert solver.infra_main() is True
    solver.plan_solver.assert_not_called()
    solver.planned = solver.todo_task = solver.collect_notification = False
    for stage in range(3):
        if stage == 2:
            Clock.current = datetime(2026, 10, 6, 19, 53, 2, 589686)
        solver.task = None
        solver.infra_main()
    assert solver.agent_arrange_room.call_count == 2
    assert future in solver.tasks
    assert not any(getattr(task, "initial_fia", False) for task in solver.tasks)
    followup = solver.find_next_task(task_type=TaskTypes.NOT_SPECIFIC)
    assert followup is not None, "Startup restoration must resume normal planning"
    assert followup.time <= Clock.now()
    solver.plan_solver.assert_not_called()

    solver.run()

    solver.backup_plan_solver.assert_called()
    solver.run_order_solver.assert_called_once()
    solver.plan_solver.assert_called_once()
    assert future in solver.tasks


def test_deferred_initial_restoration_keeps_priority_without_followup(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_schedule

    restoration = SchedulerTask(
        time=datetime.now(),
        task_type=TaskTypes.FIAMMETTA,
        task_plan={ROOM: ["塑心", "冰酿", "泥岩", "菲亚梅塔", "年"]},
        initial_fia=True,
    )
    solver.task, solver.tasks = restoration, [restoration]
    solver.find = MagicMock(return_value=True)
    solver.agent_arrange = MagicMock(
        side_effect=base_schedule.RoomArrangementDeferred(
            ROOM, RuntimeError("room observation unavailable")
        )
    )
    solver.back_to_infrastructure = MagicMock()
    solver._refresh_deferred_product_reservations = MagicMock()
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())

    solver.infra_main()

    assert solver.tasks == [restoration]
    assert restoration.initial_fia
    assert restoration.time > datetime.now()


def test_real_selection_keeps_full_charge_target(solver, monkeypatch):
    data = solver.op_data
    data.config.free_room = True
    data.add(Operator("菲亚梅塔", ROOM, index=3))
    data.operators["伊内丝"].mood = 24
    instance, selected = selection_solver(
        monkeypatch, residents=["塑心", "冰酿", "泥岩", "能天使", "年"]
    )
    instance.op_data = data
    instance.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data="伊内丝")
    agents = ["伊内丝", "菲亚梅塔"]

    instance.choose_agent(agents, ROOM)

    assert agents == selected == ["伊内丝", "菲亚梅塔"]
    instance.get_free_list.assert_not_called()


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("phase", ["charge", "restore"])
def test_fiammetta_exact_roster_survives_dorm_normalization(solver, free_room, phase):
    data = solver.op_data
    data.config.free_room = free_room
    data.add(Operator("菲亚梅塔", ROOM, index=3))
    data.operators["伊内丝"].mood = 24
    data.operators["伊内丝"].depletion_rate = 3
    data.operators["泥岩"].mood = 24
    # 原住者保床也不能覆盖临时充能名单。
    data.config.free_room_exclusions = ["泥岩"]
    agents = (
        ["伊内丝", "菲亚梅塔"]
        if phase == "charge"
        else ["塑心", "冰酿", "泥岩", "菲亚梅塔", "年"]
    )
    solver.task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={ROOM: agents.copy()},
        meta_data="伊内丝" if phase == "charge" else "",
    )
    solver.tasks = [solver.task]
    # 这两个入口分别覆盖测试宿舍执行边界和稳定逻辑选人边界。
    solver.preserve_resting_crafters(agents, ROOM)
    assert solver.prepare_dorm_selection(agents, ROOM) == []

    assert agents == solver.task.plan[ROOM]
    assert data.operators["伊内丝"].depletion_rate == 3


def test_fia_does_not_retain_idle_excluded_resident_in_target_slot(solver):
    data = solver.op_data
    data.config.free_room = True
    data.config.free_room_exclusions = ["泥岩"]
    target = data.operators["伊内丝"]
    target.mood = target.upper_limit = 12
    data.config.operator_mood_limits[target.name] = {"lower": 0, "upper": 12}
    agents = ["塑心", "冰酿", target.name, "菲亚梅塔"]
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data=target.name)

    solver.prepare_dorm_selection(agents, ROOM)

    assert agents[2] == target.name


def test_plan_fia_refreshes_zero_rate_cache_before_full_mood_decision(
    solver, monkeypatch
):
    target = solver.op_data.operators["伊内丝"]
    target.group = ""
    target.mood = 24
    target.depletion_rate = 0
    target.time_stamp = datetime.now() - timedelta(minutes=40)
    solver.check_fia = lambda: ([target.name], ROOM)
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.enter_room = MagicMock()
    solver.back = MagicMock()

    def read(room, indexes):
        assert (room, indexes) == ("meeting", [0])
        solver.op_data.update_detail(target.name, 20, room, 0, True)

    solver.get_agent_from_room = MagicMock(side_effect=read)
    monkeypatch.setattr(config.conf, "fia_fool", True)
    solver.plan_fia()

    assert target.mood == 20
    assert target.depletion_rate > 0
    assert solver.tasks[0].plan == {ROOM: [target.name, "菲亚梅塔"]}
    solver.enter_room.assert_called_once_with("meeting")
    solver.back.assert_called_once()


@pytest.mark.parametrize("cause", ["expired", "zero_rate", "resting"])
def test_fia_refresh_groups_candidate_reads_by_actual_room(solver, cause):
    names = ["伊内丝", "银灰"]
    room = ROOM if cause == "resting" else "meeting"
    for index, name in enumerate(names):
        op = solver.op_data.operators[name]
        op.current_room, op.current_index = room, index
        op.depletion_rate = 0 if cause == "zero_rate" else 1
        op.time_stamp = datetime.now() - timedelta(hours=3 if cause == "expired" else 0)
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock()
    solver.back = MagicMock()

    solver._refresh_fia_candidate_moods(names)

    solver.enter_room.assert_called_once_with(room)
    solver.get_agent_from_room.assert_called_once_with(room, [0, 1])
    solver.back.assert_called_once()


def test_fia_fresh_working_cache_needs_no_extra_room_visit(solver):
    target = solver.op_data.operators["伊内丝"]
    target.depletion_rate = 1
    solver._refresh_fia_candidate_moods([target.name])
    solver.enter_room.assert_not_called()


def test_fia_failed_mood_read_does_not_schedule_from_stale_cache(solver):
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.check_fia = lambda: (["伊内丝"], ROOM)
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock(side_effect=RuntimeError("read failed"))
    solver.back = MagicMock()
    with pytest.raises(RuntimeError, match="read failed"):
        solver.plan_fia()
    assert solver.tasks == []


@pytest.mark.parametrize("read_mood", [False, True])
def test_charge_return_keeps_work_rate_and_later_work_can_recalibrate(
    solver, monkeypatch, read_mood
):
    import numpy as np

    data = solver.op_data
    target = data.operators["讯使"]
    target._current_room, target.current_index = ROOM, 2
    target.mood, target.time_stamp, target.depletion_rate = 24, datetime.now(), 3.25
    solver.task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, task_plan={"contact": ["讯使"]}
    )
    solver.tasks = [solver.task]
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.find = MagicMock(return_value=None)
    solver.refresh_facility_state = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.scroll_room_operators = MagicMock()
    solver.read_screen = MagicMock(return_value="讯使")
    solver.read_accurate_mood = MagicMock(return_value=24)
    solver.read_operator_time = MagicMock(return_value=datetime.now())
    monkeypatch.setattr(target, "need_to_refresh", lambda **kw: read_mood)
    monkeypatch.setattr(
        "arknights_mower.solvers.record.save_agent_action", lambda *a, **kw: None
    )
    solver.get_agent_from_room("contact")
    assert target.current_room == "contact"
    assert target.depletion_rate == 3.25
    assert target.mood == 24
    half_hour = target.time_stamp + timedelta(minutes=30)
    assert target.current_mood(half_hour) == pytest.approx(22.375)
    # 正常工作实读仍校准速度，充能保护不是永久锁定速度。
    target.time_stamp = datetime.now() - timedelta(hours=1)
    data.update_detail(target.name, 20, "contact", 0, True)
    assert target.depletion_rate == pytest.approx(4, abs=0.01)


@pytest.mark.parametrize(
    "mood,known,targets,expected",
    [
        (24, True, True, True),
        (23, True, True, False),
        (24, False, True, False),
        (24, True, False, False),
    ],
)
def test_initial_fia_requires_measured_full_mood_and_targets(
    solver, mood, known, targets, expected
):
    fia = Operator(
        "菲亚梅塔",
        ROOM,
        index=3,
        current_room=ROOM,
        current_index=3,
        mood=mood,
        time_stamp=datetime.now() if known else None,
    )
    solver.op_data.operators[fia.name] = fia
    solver.check_fia = lambda: (["伊内丝"] if targets else [], ROOM)
    solver.tasks = []
    assert solver._queue_initial_fia() is expected
    assert len(solver.tasks) == int(expected)
    if expected:
        assert solver.tasks[0].initial_fia
        assert solver.tasks[0].type == TaskTypes.FIAMMETTA
    assert not solver._queue_initial_fia()
    assert len(solver.tasks) == int(expected)


def test_initial_fia_reuses_cached_wakeup_and_marks_charge(solver, monkeypatch):
    from arknights_mower.utils.scheduler_task import protect_priority_tasks

    now = datetime.now()
    target = solver.op_data.operators["伊内丝"]
    target.group = ""
    target.mood = 1
    target.time_stamp = now
    solver.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        ROOM,
        index=3,
        current_room=ROOM,
        current_index=3,
        mood=24,
        time_stamp=now,
    )
    solver.check_fia = lambda: ([target.name], ROOM)
    solver._refresh_fia_candidate_moods = MagicMock()
    cached = SchedulerTask(time=now + timedelta(hours=1), task_type=TaskTypes.FIAMMETTA)
    ordinary = SchedulerTask(
        time=now - timedelta(minutes=5), task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks = [ordinary, cached]
    assert solver._queue_initial_fia()
    assert solver.tasks[-1] is cached
    protect_priority_tasks(solver.tasks)
    assert solver.tasks[0] is cached
    solver.task = cached
    solver.plan_fia()
    charge = next(
        task for task in solver.tasks if task.type == TaskTypes.FIAMMETTA and task.plan
    )
    assert charge.initial_fia
    assert charge.plan == {ROOM: [target.name, "菲亚梅塔"]}


@pytest.mark.parametrize(
    "kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT, TaskTypes.RELEASE_DORM]
)
def test_initial_fia_respects_due_critical_tasks(
    solver, monkeypatch, kind, offline_maintenance
):
    from arknights_mower.utils.scheduler_task import protect_priority_tasks

    monkeypatch.setattr(config.conf, "enable_mastery", True)
    now = datetime.now()
    initial = SchedulerTask(time=now, task_type=TaskTypes.FIAMMETTA, initial_fia=True)
    critical = SchedulerTask(
        time=now - timedelta(minutes=1),
        task_type=kind,
        strict_mood_limit=kind == TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current", "Current", "Free"]}
        if kind == TaskTypes.RELEASE_DORM
        else {},
    )
    tasks = [initial, critical]
    protect_priority_tasks(tasks, time_now=now)
    assert tasks[0] is critical


def test_initial_fia_restoration_retains_startup_priority(solver):
    from arknights_mower.utils.scheduler_task import protect_priority_tasks

    now = datetime.now()
    charge = SchedulerTask(
        time=now,
        task_type=TaskTypes.FIAMMETTA,
        task_plan={ROOM: ["伊内丝", "菲亚梅塔"]},
        initial_fia=True,
    )
    ordinary = SchedulerTask(
        time=now - timedelta(minutes=1), task_type=TaskTypes.SHIFT_OFF
    )
    solver.task, solver.tasks = charge, [charge, ordinary]
    original = {ROOM: ["塑心", "冰酿", "泥岩", "菲亚梅塔", "年"]}
    solver.agent_arrange_room = MagicMock(return_value=original)
    solver.skip = MagicMock()
    solver.agent_arrange(charge.plan)
    restoration = solver.tasks[-1]
    assert restoration.initial_fia
    assert restoration.plan == original
    solver.tasks.remove(charge)
    protect_priority_tasks(solver.tasks)
    assert solver.tasks[0] is restoration


@pytest.mark.parametrize("rescue_startup", [False, True])
def test_initial_fia_dispatch_preempts_selected_ordinary_work(solver, rescue_startup):
    now = datetime.now()
    ordinary = SchedulerTask(
        time=now - timedelta(minutes=1), task_type=TaskTypes.SHIFT_OFF
    )
    initial = SchedulerTask(time=now, task_type=TaskTypes.FIAMMETTA, initial_fia=True)
    solver.task, solver.tasks = ordinary, [ordinary, initial]
    solver._emergency_startup_pending = rescue_startup
    solver._emergency_startup = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.plan_fia = MagicMock()
    solver.agent_arrange = MagicMock()
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.infra_main()
    solver.plan_fia.assert_called_once()
    solver.agent_arrange.assert_not_called()
    assert ordinary in solver.tasks
    assert initial not in solver.tasks
