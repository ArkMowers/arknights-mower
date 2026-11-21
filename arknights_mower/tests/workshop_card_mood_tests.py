"""加工准入和执行复用保守卡牌预算，实读与预估分别保存。"""

from copy import deepcopy
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin, base_schedule, record
from arknights_mower.tests import initial_dorm_mood_tests
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import config, scheduler_task, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.workshop_limits import (
    WorkshopSelectionBlocked,
    workshop_candidate_mood,
)
from arknights_mower.utils.workshop_status import workshop_status

op_data = initial_dorm_mood_tests.op_data
card_scan_solver = initial_dorm_mood_tests.solver


@pytest.fixture(params=["manual", "mastery"])
def case(request, monkeypatch):
    automatic = request.param == "mastery"
    setting = RIICPart.WorkShopSetting(
        operator="赫拉格",
        source=request.param,
        items=[
            WorkShopItem(
                item_names=["技巧概要·卷3"],
                self_upper_limit=7,
                children_lower_limit=0,
            )
        ],
    )
    monkeypatch.setattr(
        config,
        "conf",
        config.Conf(workshop_auto_active=automatic, workshop_settings=[setting]),
    )
    monkeypatch.setattr(record, "workshop_inventory_changed", Event())
    monkeypatch.setattr(workshop_automation, "_refresh_error", None)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(
        workshop_automation,
        "calculate_workshop_plan",
        lambda *args, **kwargs: SimpleNamespace(focus=None, recipe="技巧概要·卷3"),
    )
    stock = {"技巧概要·卷3": 0, "技巧概要·卷2": 21}
    monkeypatch.setattr(record, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(base_schedule, "get_inventory_counts", lambda: stock)
    data = SimpleNamespace(
        operators={"赫拉格": Operator("赫拉格", "", mood=-1)},
        dorm_mood_estimates={"赫拉格": (24, datetime.now())},
        is_standby=lambda name: False,
        plan={},
    )
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.task = data, [], None
    solver.sleeping = False
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock(return_value=[{"agent": "年"}])
    solver.agent_arrange = MagicMock()
    solver.generate_product = MagicMock()
    snapshot = SimpleNamespace(settings=[setting], is_current=lambda: True)
    monkeypatch.setattr(
        workshop_automation, "workshop_task_snapshot", lambda _: snapshot
    )
    return SimpleNamespace(solver=solver, data=data, setting=setting, stock=stock)


@pytest.mark.parametrize("inferred", [False, True])
def test_full_card_allows_status_queue_and_pre_move_check_without_measured_cache(
    case, inferred
):
    solver, data = case.solver, case.data
    if inferred:
        mood, observed = data.dorm_mood_estimates["赫拉格"]
        data.dorm_mood_estimates["赫拉格"] = (mood, observed, False)
    before = deepcopy(vars(data.operators["赫拉格"]))
    estimates = deepcopy(data.dorm_mood_estimates)
    assert workshop_status(solver, running=True)["execution"] == "ready"
    scheduler_task.try_workshop_tasks(data, solver.tasks)
    assert [task.meta_data for task in solver.tasks] == ["赫拉格"]
    solver.task = solver.tasks[0]
    restoration = {}
    assert solver._craft_material(restoration) == "赫拉格"
    solver.agent_arrange.assert_called_once_with({"factory": ["赫拉格"]})
    solver.generate_product.assert_called_once()
    assert restoration == {"factory": ["年"]}
    assert vars(data.operators["赫拉格"]) == before
    assert data.dorm_mood_estimates == estimates


@pytest.mark.parametrize("reason", ["expired", "future", "missing"])
def test_unusable_full_card_blocks_status_and_dispatch(case, reason):
    estimates = case.data.dorm_mood_estimates
    if reason == "expired":
        estimates["赫拉格"] = (24, datetime.now() - timedelta(hours=1))
    elif reason == "future":
        estimates["赫拉格"] = (24, datetime.now() + timedelta(minutes=1))
    else:
        estimates.clear()
    status = workshop_status(case.solver, running=True)
    assert status["execution"] == "waiting"
    assert status["blockers"][0]["code"] == "mood_unknown"
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert case.solver.tasks == []


@pytest.mark.parametrize("measured", [0, 1, 20])
def test_numeric_mood_takes_priority_and_keeps_manual_and_batch_thresholds(
    case, measured
):
    op = case.data.operators["赫拉格"]
    op.mood, op.time_stamp = measured, datetime.now()
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    expected = case.setting.source == "mastery" and measured >= 2
    assert bool(case.solver.tasks) == expected
    if not expected:
        assert (
            workshop_status(case.solver, running=True)["blockers"][0]["code"]
            == "mood_insufficient"
        )


def test_expired_card_keeps_automatic_guard_and_manual_room_read(case):
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert len(case.solver.tasks) == 1
    case.solver.task = case.solver.tasks[0]
    case.data.dorm_mood_estimates["赫拉格"] = (
        24,
        datetime.now() - timedelta(hours=1),
    )
    if case.setting.source == "mastery":
        assert case.solver._craft_material({}) is None
        case.solver.enter_room.assert_not_called()
        case.solver.agent_arrange.assert_not_called()
    else:
        # 已排入的手动任务沿用未知心情入站读取；新入队仍须超过 22。
        assert case.solver._craft_material({}) == "赫拉格"
        case.solver.agent_arrange.assert_called_once_with({"factory": ["赫拉格"]})


@pytest.mark.parametrize("reservation", ["task", "rescue"])
def test_full_card_keeps_operator_reservations(case, reservation):
    if reservation == "task":
        case.solver.tasks.append(
            SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"train": ["赫拉格"]})
        )
    else:
        case.data.emergency_reserved_agents = {"赫拉格"}
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert not any(t.type == TaskTypes.WORKSHOP for t in case.solver.tasks)
    assert (
        workshop_status(case.solver, running=True)["blockers"][0]["code"]
        == "operator_reserved"
    )


def test_full_card_does_not_bypass_material_shortage(case):
    case.stock["技巧概要·卷2"] = 2
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert case.solver.tasks == []
    assert (
        workshop_status(case.solver, running=True)["blockers"][0]["code"]
        == "material_shortage"
    )


@pytest.mark.parametrize("card_newer", [False, True])
def test_low_card_vetoes_numeric_full_only_when_newer(case, card_newer):
    observed = datetime.now() - timedelta(minutes=2)
    op = case.data.operators["赫拉格"]
    op.mood, op.time_stamp = 24, observed
    case.data.dorm_mood_estimates["赫拉格"] = (
        1,
        observed + timedelta(seconds=1 if card_newer else -1),
    )

    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)

    assert bool(case.solver.tasks) is (not card_newer)
    assert workshop_candidate_mood(case.data, "赫拉格") == (1 if card_newer else 24)
    if card_newer:
        assert (
            workshop_status(case.solver, running=True)["blockers"][0]["code"]
            == "mood_insufficient"
        )
        case.solver.task = SchedulerTask(
            task_type=TaskTypes.WORKSHOP, meta_data="赫拉格"
        )
        assert case.solver._craft_material({}) is None
        case.solver.enter_room.assert_not_called()


@pytest.mark.parametrize("slow", [False, True])
@pytest.mark.parametrize("mood", [0, 1])
def test_workshop_selection_blocks_low_card_before_target_click(
    case, monkeypatch, slow, mood
):
    instance, selected = workshop_selection_solver(case, monkeypatch, slow, mood)

    with pytest.raises(WorkshopSelectionBlocked, match="心情"):
        instance.choose_agent(["赫拉格"], "factory", fast_mode=False)

    assert selected == []
    instance.tap.assert_not_called()
    assert instance.op_data.dorm_mood_estimates["赫拉格"][0] == mood
    assert instance.recog.update.call_count == (0 if slow else 1)


def workshop_selection_solver(case, monkeypatch, slow, mood):
    instance, selected = selection_solver(monkeypatch, residents=[])
    instance.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="赫拉格")
    instance._workshop_selection_target = "赫拉格"
    monkeypatch.setattr(
        workshop_automation,
        "workshop_task_snapshot",
        lambda _: SimpleNamespace(settings=[case.setting]),
    )
    monkeypatch.setattr(base_schedule, "get_inventory_counts", lambda: case.stock)
    instance.scan_agent = base_mixin.BaseMixin.scan_agent.__get__(instance)
    instance.recog.img = {"mood": mood}
    page = [("赫拉格", ((0, 32), (189, 64)))]
    instance.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list", lambda *args, **kwargs: page)
    monkeypatch.setattr(base_mixin, "estimate_agent_mood", lambda img, scope: mood)
    monkeypatch.setattr(
        base_mixin.BaseMixin, "low_frame_rate_mode", property(lambda self: slow)
    )
    instance.check_agent_page = MagicMock(return_value=True)
    instance.clear_agent_selection = MagicMock()
    instance.tap = MagicMock()
    instance.verify_agent = MagicMock(return_value=True)
    return instance, selected


@pytest.mark.parametrize("slow", [False, True])
@pytest.mark.parametrize("mood", [None, 2, 24])
def test_workshop_selection_allows_unknown_or_affordable_card(
    case, monkeypatch, slow, mood
):
    instance, _ = workshop_selection_solver(case, monkeypatch, slow, mood)

    instance.choose_agent(["赫拉格"], "factory", fast_mode=False)

    instance.tap.assert_called_once()
    assert instance.tap.call_args.args[0] == ((0, 32), (189, 64))
    instance.verify_agent.assert_called_once_with(["赫拉格"], "factory")
    assert instance.recog.update.call_count == (0 if slow else 1)
    if mood is None:
        assert "赫拉格" not in instance.op_data.dorm_mood_estimates
    else:
        assert instance.op_data.dorm_mood_estimates["赫拉格"][0] == mood


def test_new_low_card_blocks_repeated_dispatch_until_new_numeric_read(case):
    op = case.data.operators["赫拉格"]
    observed = datetime.now() - timedelta(seconds=3)
    op.mood, op.time_stamp = 24, observed
    case.data.dorm_mood_estimates["赫拉格"] = (1, observed + timedelta(seconds=1))
    for _ in range(2):
        scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
        assert case.solver.tasks == []
    op.mood, op.time_stamp = 24, observed + timedelta(seconds=2)

    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)

    assert [task.meta_data for task in case.solver.tasks] == ["赫拉格"]


@pytest.mark.parametrize("slow", [False, True])
def test_workshop_low_card_propagates_through_room_arrangement_without_retry(
    case, monkeypatch, slow
):
    instance, _ = workshop_selection_solver(case, monkeypatch, slow, 0)
    instance.op_data.get_current_room = lambda *args: [""]
    instance.op_data.run_order_rooms = {}
    instance._prepare_group_shift_execution_targets = MagicMock()
    instance._suppress_facility_arrangement = MagicMock()
    instance.ensure_dorm_recovery_order = MagicMock(return_value=False)
    instance._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    instance.enter_room = MagicMock()
    instance.turn_on_room_detail = MagicMock()
    instance.find = MagicMock(side_effect=lambda label: label == "confirm_blue")
    instance.scene = MagicMock(return_value=Scene.INFRA_MAIN)
    instance.choose_agent = MagicMock(wraps=instance.choose_agent)
    instance.tap_confirm = MagicMock()
    save_exception = MagicMock()
    retries = MagicMock()
    monkeypatch.setattr(base_schedule, "save_exception", save_exception)
    monkeypatch.setattr(base_schedule, "record_selection_retry", retries)

    with pytest.raises(WorkshopSelectionBlocked, match="心情"):
        instance.agent_arrange_room({}, "factory", {"factory": ["赫拉格"]})

    instance.choose_agent.assert_called_once()
    instance.tap.assert_not_called()
    instance.tap_confirm.assert_not_called()
    save_exception.assert_not_called()
    retries.assert_not_called()


@pytest.mark.parametrize("existing_factory", [False, True])
def test_blocked_workshop_selection_restores_only_current_restore_plan_changes(
    case, existing_factory
):
    solver, data = case.solver, case.data
    op = data.operators["赫拉格"]
    op.current_room, op.current_index = "meeting", 1
    data.plan["meeting"] = [None, None]
    solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="赫拉格")
    solver.back_to_infrastructure = MagicMock()
    solver._workshop_selection_target = "之前的加工干员"
    restoration = {"meeting": ["银灰", "Current"]}
    if existing_factory:
        restoration["factory"] = ["年"]
    before = deepcopy(restoration)

    def block(plan):
        assert solver._workshop_selection_target == "赫拉格"
        assert restoration["meeting"] == ["银灰", "赫拉格"]
        raise WorkshopSelectionBlocked("心情不足")

    solver.agent_arrange.side_effect = block

    assert solver._craft_material(restoration) is None

    assert restoration == before
    assert solver._workshop_selection_target == "之前的加工干员"
    solver.back_to_infrastructure.assert_called_once()
    solver.generate_product.assert_not_called()


def prepare_missing_workshop_card(solver, monkeypatch):
    monkeypatch.setattr(
        config.conf,
        "workshop_settings",
        [RIICPart.WorkShopSetting(operator="红")],
    )
    solver.defer_backup_plan_until_mood_read = False
    op = solver.op_data.operators["红"]
    op.mood, op.time_stamp = -1, None
    solver.recog.img = {0: 3, 1: 24}
    solver.wait_for_agent_page.return_value = [("红", 0), ("银灰", 1)]


def test_missing_workshop_scan_keeps_post_scan_observation_until_relevant_change(
    card_scan_solver, monkeypatch
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    before = deepcopy(vars(solver.op_data.operators["红"]))

    assert solver._read_missing_workshop_moods() is True

    assert solver.op_data.dorm_mood_estimates["红"][0] == 3
    assert workshop_candidate_mood(solver.op_data, "红") == 3
    assert vars(solver.op_data.operators["红"]) == before
    solver._workshop_card_moods_scanned_this_run = False
    assert solver._read_missing_workshop_moods() is None
    solver.enter_room.assert_called_once_with("factory", max_attempts=1)
    solver.op_data.operators["红"].current_room = "meeting"
    solver.op_data.dorm_mood_estimates["红"] = (3, datetime.now() - timedelta(hours=2))
    assert solver._read_missing_workshop_moods() is True
    assert solver.enter_room.call_count == 2
    solver.tap_confirm.assert_not_called()
    solver.agent_arrange_room.assert_not_called()


def test_missing_workshop_scan_yields_to_imminent_task_and_retries_when_idle(
    card_scan_solver, monkeypatch
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    task = SchedulerTask(datetime.now(), {"meeting": ["银灰"]}, TaskTypes.SHIFT_ON)
    solver.tasks = [task]
    original_time = task.time

    assert solver._read_missing_workshop_moods() is None

    solver.enter_room.assert_not_called()
    assert not getattr(solver, "_workshop_card_moods_scanned_this_run", False)
    task.time += timedelta(minutes=2)
    assert solver._read_missing_workshop_moods() is True
    solver.enter_room.assert_called_once_with("factory", max_attempts=1)
    assert solver.tasks == [task]
    assert task.time == original_time + timedelta(minutes=2)
    solver.no_pending_task.assert_not_called()


@pytest.mark.parametrize("reason", ["initial", "known", "disabled", "scanned"])
def test_missing_workshop_scan_preserves_other_mood_observation_owners(
    card_scan_solver, monkeypatch, reason
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    if reason == "initial":
        solver.defer_backup_plan_until_mood_read = True
    elif reason == "known":
        solver.op_data.dorm_mood_estimates["红"] = (24, datetime.now())
    elif reason == "scanned":
        solver._workshop_card_moods_scanned_this_run = True
    else:
        config.conf.workshop_settings[0].enabled = False

    solver._read_missing_workshop_moods()

    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("calculated", [False, True])
def test_workshop_scan_is_independent_of_normal_scan_and_accepts_queued_workshop(
    card_scan_solver, monkeypatch, calculated
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    monkeypatch.setattr(config.conf, "test_mood_calculation", calculated)
    solver._card_moods_scanned_this_run = True
    solver.tasks = [
        SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="红"),
        SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="银灰"),
    ]
    solver.task = solver.tasks[0]

    assert solver._read_missing_workshop_moods() is True

    solver.enter_room.assert_called_once_with("factory", max_attempts=1)
    assert solver.op_data.dorm_mood_estimates["红"][0] == 3
    assert solver._card_moods_scanned_this_run is True
    solver.no_pending_task.assert_not_called()
    solver.tap_confirm.assert_not_called()
    if calculated:
        assert solver.op_data.calculated_mood("红") == 3


def test_workshop_scan_does_not_reobserve_calculated_baseline_with_unknown_rate(
    card_scan_solver, monkeypatch
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    monkeypatch.setattr(config.conf, "test_mood_calculation", True)
    model = solver.op_data.mood_model
    model.observe("红", 3, datetime.now())
    model._rates()
    monkeypatch.setattr(model, "_rates", MagicMock(return_value={"红": None}))
    assert solver.op_data.calculated_mood("红") is None
    before = deepcopy(model.moods)

    assert solver._read_missing_workshop_moods() is None

    solver.enter_room.assert_not_called()
    assert model.moods == before


@pytest.mark.parametrize("reason", ["unbuilt", "compensation"])
def test_workshop_scan_preserves_unbuilt_factory_and_pending_compensation(
    card_scan_solver, monkeypatch, reason
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    if reason == "unbuilt":
        solver.op_data.facility_levels["factory"] = 0
    else:
        solver.tasks = [
            SchedulerTask(
                task_type=TaskTypes.WORKSHOP,
                task_plan={"factory": ["年"]},
            )
        ]
    tasks = list(solver.tasks)
    times = [task.time for task in tasks]

    assert solver._read_missing_workshop_moods() is None

    solver.enter_room.assert_not_called()
    assert not getattr(solver, "_workshop_card_moods_scanned_this_run", False)
    assert solver.tasks == tasks
    assert [task.time for task in solver.tasks] == times


@pytest.mark.parametrize("bound", ["pages", "seconds"])
def test_workshop_missing_scan_has_shared_bounds_and_cancels_selection(
    card_scan_solver, monkeypatch, bound
):
    solver = card_scan_solver
    prepare_missing_workshop_card(solver, monkeypatch)
    solver.wait_for_agent_page.side_effect = [[(f"其他{i}", 0)] for i in range(30)]
    if bound == "seconds":
        monkeypatch.setattr(
            base_schedule, "monotonic", MagicMock(side_effect=[0, 0, 46])
        )

    assert solver._read_missing_workshop_moods() is True

    assert solver.wait_for_agent_page.call_count == (1 if bound == "seconds" else 20)
    assert solver.swipe_agent_page.call_count == (0 if bound == "seconds" else 19)
    solver.enter_room.assert_called_once_with("factory", max_attempts=1)
    solver.tap_confirm.assert_not_called()
    solver.agent_arrange_room.assert_not_called()
    solver.back_to_infrastructure.assert_called_once()


@pytest.mark.parametrize("all_known", [False, True])
def test_first_workshop_scans_later_unknown_worker_before_any_move_and_batches(
    card_scan_solver, monkeypatch, all_known
):
    solver = card_scan_solver

    class Clock(datetime):
        current = datetime.now() - timedelta(seconds=1)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    settings = [
        RIICPart.WorkShopSetting(
            operator=name,
            items=[
                WorkShopItem(
                    item_names=["技巧概要·卷3"],
                    self_upper_limit=7,
                    children_lower_limit=0,
                )
            ],
        )
        for name in ["赫拉格", "年"]
    ]
    monkeypatch.setattr(config.conf, "workshop_settings", settings)
    stock = {"技巧概要·卷3": 0, "技巧概要·卷2": 21}
    monkeypatch.setattr(base_schedule, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(
        workshop_automation,
        "workshop_task_snapshot",
        lambda _: SimpleNamespace(settings=settings, is_current=lambda: True),
    )
    solver.defer_backup_plan_until_mood_read = False
    for index, name in enumerate(["赫拉格", "年"]):
        op = Operator(name, "", mood=24 if index == 0 or all_known else -1)
        op.time_stamp = Clock.now() if index == 0 or all_known else None
        solver.op_data.add(op)
    scheduler_task.try_workshop_tasks(solver.op_data, solver.tasks)
    assert [task.meta_data for task in solver.tasks] == (
        ["赫拉格", "年"] if all_known else ["赫拉格"]
    )
    solver.task = solver.tasks[0]
    events = []
    solver.enter_room.side_effect = lambda room, **kwargs: events.append(
        ("enter", room)
    )
    solver.wait_for_agent_page.side_effect = lambda **kwargs: (
        events.append(("scan", "年")) or [("年", 1)]
    )
    solver.back_to_infrastructure.side_effect = lambda: events.append(
        ("cancel", "factory")
    )
    solver.get_agent_from_room = MagicMock(return_value=[{"agent": "特克诺"}])
    solver.agent_arrange = MagicMock(
        side_effect=lambda plan, **kwargs: events.append(("arrange", deepcopy(plan)))
    )

    def craft(name, snapshot):
        events.append(("craft", name))
        solver.op_data.operators[name].mood = 0
        Clock.current += timedelta(seconds=30)

    solver.generate_product = MagicMock(side_effect=craft)
    solver._plan_dorm_recovery = MagicMock(return_value=True)
    solver.op_data.refresh_idle_dorm_search = MagicMock()

    solver.craft_material()

    assert [event for event in events if event[0] == "craft"] == [
        ("craft", "赫拉格"),
        ("craft", "年"),
    ]
    assert events[:3] == [
        ("enter", "factory"),
        ("scan", "年"),
        ("cancel", "factory"),
    ]
    solver.wait_for_agent_page.assert_called_once()
    assert events[3:5] == [
        ("enter", "factory"),
        ("arrange", {"factory": ["赫拉格"]}),
    ]
    assert events[-1] == ("arrange", {"factory": ["特克诺"]})
    assert solver.tasks == []
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize(
    "estimate, budget", [(0, 0), (1.9, 1), (2.9, 2), (22.9, 22), (23.9, 23)]
)
def test_card_budget_rounds_down_and_preserves_manual_threshold(case, estimate, budget):
    case.data.dorm_mood_estimates["赫拉格"] = (estimate, datetime.now())
    before = deepcopy(vars(case.data.operators["赫拉格"]))

    assert workshop_candidate_mood(case.data, "赫拉格") == budget
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)

    expected = budget >= 2 if case.setting.source == "mastery" else budget > 22
    assert bool(case.solver.tasks) is expected
    assert vars(case.data.operators["赫拉格"]) == before
    if not expected:
        assert (
            workshop_status(case.solver, running=True)["blockers"][0]["code"]
            == "mood_insufficient"
        )
