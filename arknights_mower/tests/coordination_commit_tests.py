"""首次物理提交前按当前实际阵容复核完整协调准入和普通召回续航。"""

from copy import copy, deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests import exhaust_replacement_tests, recall_full_recovery_tests
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

base = exhaust_replacement_tests.base_schedule
solver = exhaust_replacement_tests.solver
recall = recall_full_recovery_tests.recall
NOW = recall_full_recovery_tests.NOW


@pytest.fixture
def confirmation(recall, monkeypatch):
    solver, rates, calculated = recall
    data = solver.op_data
    recall_full_recovery_tests.set_recalled_mood(solver, 12, calculated=calculated)
    # 陈仍在会客室工作，替班关系把它纳入本次共享资源依赖。
    data.operators["能天使"].replacement = ["陈", "斥罪"]
    data.plan["meeting"][0].replacement = ["陈", "斥罪"]
    data.operators["陈"].mood = 4 if calculated else 4.5
    data.operators["陈"].depletion_rate = 1
    data.operators["机械师"].depletion_rate = 1
    data.operators["机械师"].rest_in_full = False
    if calculated:
        data.mood_model.observe("陈", 4, NOW)

    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    plan = solver._plan_exhaust_support(["机械师"])
    assert plan
    request = SchedulerTask(
        time=NOW, task_type=TaskTypes.EXHAUST_OFF, meta_data="机械师"
    )
    request.ordinary_coordination = True
    support = SchedulerTask(
        time=NOW, task_type=TaskTypes.SELF_CORRECTION, task_plan=plan
    )
    support.exhaust_support = support.ordinary_coordination = True
    support.coordination_request_names = ["机械师"]
    solver.task, solver.tasks = support, [support, request]
    assert solver._coordination_support_valid(plan, ["机械师"])
    solver.recog = SimpleNamespace(w=1920, h=1080, update=Mock())
    solver.tap, solver.sleep, solver.back = Mock(), Mock(), Mock()
    solver.back_to_infrastructure = Mock()
    save = Mock(return_value=True)
    monkeypatch.setattr(base, "save_current_state", save)
    page = {"button": True}

    def find(template, **kwargs):
        if template == "confirm_blue" and page["button"]:
            return (100, 200)
        return (100, 200) if template == "room_detail" and not page["button"] else None

    solver.find = Mock(side_effect=find)
    solver.tap.side_effect = lambda *a, **k: page.update(button=False)
    return SimpleNamespace(
        solver=solver,
        rates=rates,
        calculated=calculated,
        clock=Clock,
        support=support,
        request=request,
        save=save,
        page=page,
        find=find,
    )


def latest_support_valid(case):
    fresh = copy(case.solver)
    fresh.op_data = case.solver.op_data.project_arrangements([], now=case.clock.now())
    return fresh._coordination_support_valid(case.support.plan, ["机械师"])


def test_selection_elapsed_time_rechecks_endurance_at_first_physical_confirmation(
    confirmation,
):
    case = confirmation
    case.clock.current = NOW + timedelta(minutes=30)
    # 固定速率：观测模式最初需17/4小时减普通回班的8分钟，陈可工作4.5h；
    # 选人0.5h后需17.5/4小时减8分钟，超过陈剩余的4h。
    # 计算模式用实际模型的宿舍恢复速率，陈4h的初始续航同样在选人后不足。
    assert not latest_support_valid(case)
    assert case.solver.op_data.operators["陈"].current_mood(case.clock.now()) > 0
    assert case.solver.op_data.operators["机械师"].current_mood(case.clock.now()) > 0
    case.clock.current = NOW
    before = deepcopy(vars(case.support))
    find = case.find

    def selection_elapsed(template, **kwargs):
        result = find(template, **kwargs)
        if template == "confirm_blue" and result:
            case.clock.current = NOW + timedelta(minutes=30)
        return result

    case.solver.find.side_effect = selection_elapsed
    with pytest.raises(base.ProductSwitchDeferred):
        case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_not_called()
    case.save.assert_not_called()
    assert case.support.time == before["time"] and case.support.plan == before["plan"]
    assert not getattr(case.support, "mood_physical_started", False)
    assert case.solver.tasks == [case.support, case.request]


def install_room_selection(case):
    solver = case.solver
    solver.enter_room = Mock()
    solver.scene = Mock(return_value=base.Scene.INFRA_ARRANGE)
    solver.waiting_scene = []
    solver.turn_on_room_detail = Mock()
    solver.record_selection_failure = Mock()
    solver.get_agent_from_room = Mock(
        side_effect=lambda room, *a, **k: [
            {"agent": name} for name in solver.op_data.get_current_room(room, True)
        ]
    )
    solver.choose_agent = Mock(
        side_effect=lambda *a, **k: setattr(
            case.clock, "current", NOW + timedelta(minutes=30)
        )
    )


def test_room_selection_defer_propagates_without_reselection(confirmation):
    case = confirmation
    solver = case.solver
    install_room_selection(case)
    with pytest.raises(base.ProductSwitchDeferred):
        solver.agent_arrange_room({}, "room_2_2", case.support.plan)
    solver.choose_agent.assert_called_once()
    solver.record_selection_failure.assert_not_called()
    solver.tap.assert_not_called()
    case.save.assert_not_called()


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("failure", ["false", "raise"])
def test_first_submission_storage_failure_restores_unsubmitted_markers(
    confirmation, retained, failure
):
    case = confirmation
    case.support.execution_retained = retained
    if failure == "false":
        case.save.return_value = False
        expected = base.RecognizeError
    else:
        case.save.side_effect = RuntimeError("storage")
        expected = RuntimeError
    with pytest.raises(expected):
        case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_not_called()
    assert not case.support.mood_physical_started
    assert case.support.execution_retained is retained
    assert case.solver.tasks == [case.support, case.request]
    case.save.side_effect, case.save.return_value = None, True
    case.clock.current = NOW + timedelta(minutes=30)
    with pytest.raises(base.ProductSwitchDeferred):
        case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_not_called()


def test_safe_support_records_first_submission_in_both_modes(confirmation):
    case = confirmation
    case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_called_once()
    case.save.assert_called_once()
    assert case.support.mood_physical_started and case.support.execution_retained
    case.clock.current = NOW + timedelta(minutes=30)
    case.page["button"] = True
    case.solver.tap_confirm("contact")
    assert case.solver.tap.call_count == 2
    case.save.assert_called_once()


@pytest.mark.parametrize("retained", [False, True])
def test_prepared_targets_and_noop_room_do_not_prove_physical_submission(
    confirmation, retained
):
    case = confirmation
    data = case.solver.op_data
    case.support.execution_retained = retained
    case.support.group_shift_expected = {("meeting", 0): "陈"}
    case.support.urgent_recovery_initial_positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    case.support.urgent_recovery_support_names = ["苍苔", "絮雨"]
    case.clock.current = NOW + timedelta(minutes=30)
    with pytest.raises(base.ProductSwitchDeferred):
        case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_not_called()
    case.save.assert_not_called()


def test_legacy_partial_support_uses_confirmed_initial_position_change(confirmation):
    case = confirmation
    data = case.solver.op_data
    case.support.urgent_recovery_initial_positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    case.support.urgent_recovery_support_names = ["苍苔", "絮雨"]
    case.solver.op_data = data.project_arrangements([{"room_2_2": ["苍苔"]}])
    case.support.plan.pop("room_2_2")
    case.support.execution_retained = True
    case.clock.current = NOW + timedelta(minutes=30)
    remaining = deepcopy(case.support.plan)
    case.solver.tap_confirm("contact")
    case.solver.tap.assert_called_once()
    assert case.support.plan == remaining


def test_exhaustion_support_keeps_ordinary_endurance_exemption(confirmation):
    case = confirmation
    case.clock.current = NOW + timedelta(minutes=30)
    assert not latest_support_valid(case)
    case.support.ordinary_coordination = False
    assert latest_support_valid(case)
    case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_called_once()


def test_dispatch_retains_deferred_support_and_resumes_only_after_observation(
    confirmation,
):
    case = confirmation
    solver = case.solver
    # 当前普通协调只有具名support，随后由确认后的原任务派生具体下班安排。
    # 旧版空EXHAUST_OFF placeholder在正常入口会被清理，不作为此回归的原请求。
    solver.tasks = [case.support]
    solver.planned = True
    solver.todo_task = solver.collect_notification = False
    install_room_selection(case)
    solver.find.side_effect = lambda template, **kwargs: (
        (100, 200) if template == "control_central" else case.find(template, **kwargs)
    )
    solver.agent_arrange = Mock(
        side_effect=lambda plan, *args, **kwargs: solver.agent_arrange_room(
            {}, "room_2_2", plan
        )
    )
    at, plan = case.support.time, deepcopy(case.support.plan)
    solver.infra_main()
    assert case.support in solver.tasks
    assert case.support.time == at and case.support.plan == plan
    assert case.support.execution_failure["dependency"]
    solver.tap.assert_not_called()
    solver._resume_failed_tasks()
    assert case.support.execution_failure
    independent = SchedulerTask(time=case.clock.now(), task_type=TaskTypes.CLUE_PARTY)
    solver.tasks.append(independent)
    solver.task = independent
    solver._run_clue_flow = Mock(return_value=True)
    solver.infra_main()
    solver._run_clue_flow.assert_called_once()
    assert independent not in solver.tasks and case.support in solver.tasks
    assert solver.choose_agent.call_count == 1
    data = solver.op_data
    data.operators["陈"].mood, data.operators["陈"].time_stamp = 12, case.clock.now()
    if case.calculated:
        data.mood_model.observe("陈", 12, case.clock.now())
    solver._resume_failed_tasks()
    assert not getattr(case.support, "execution_failure", None)
    assert case.support.execution_retained
    solver.task = case.support
    assert latest_support_valid(case)
    solver.tap_confirm("room_2_2")
    solver.tap.assert_called_once()
    assert case.support.time == at and case.support.plan == plan


@pytest.mark.parametrize("ordinary", [False, True])
def test_observation_change_reprepares_unsubmitted_support_on_same_task(
    confirmation, ordinary
):
    case = confirmation
    solver = case.solver
    case.support.ordinary_coordination = ordinary
    case.request.ordinary_coordination = ordinary
    solver.tasks = [case.support] if ordinary else [case.support, case.request]
    solver._prepare_group_shift(case.support, remember_targets=True)
    original_time = case.support.time
    assert case.support.group_shift_expected
    case.clock.current = NOW + timedelta(minutes=30)
    data = solver.op_data
    data.operators["机械师"].replacement = ["陈"]
    data.plan["room_3_3"][0].replacement = ["陈"]
    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        solver.tap_confirm("room_2_2")
    case.support.product_shift_waiting = True
    solver._retain_failed_task(
        case.support, str(deferred.value), deferred.value.rooms, dependency=True
    )
    solver._refresh_coordination_support(case.support)
    assert case.support.plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    solver.op_data = data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "能天使"]}],
        now=case.clock.now(),
    )
    data = solver.op_data
    for name, mood in (("能天使", 20), ("陈", 12)):
        data.operators[name].mood, data.operators[name].time_stamp = (
            mood,
            case.clock.now(),
        )
        if case.calculated:
            data.mood_model.observe(name, mood, case.clock.now())
    data.get_dorm_by_name("能天使")[1].time = case.clock.now() + timedelta(hours=1)
    data.operators["机械师"].mood = 6.5
    data.operators["机械师"].time_stamp = case.clock.now()
    if case.calculated:
        data.mood_model.observe("机械师", 6.5, case.clock.now())
    # 旧projection戳不能让新实读在重准备需求判断中被当成未来读数。
    data._projection_now = NOW
    solver._resume_failed_tasks()
    assert not getattr(case.support, "execution_failure", None)
    solver._refresh_coordination_support(case.support)
    assert case.support.plan == {"meeting": ["能天使"]}
    assert case.support.time == original_time
    assert not getattr(case.support, "group_shift_expected", None)
    assert case.support in solver.tasks
    if not ordinary:
        assert case.request in solver.tasks and case.request.time == NOW
    solver.tap_confirm("meeting")
    solver.tap.assert_called_once()


@pytest.mark.parametrize(
    "protection",
    [
        "mood_physical_started",
        "urgent_recovery_started",
        "backup_shift_active",
        "backup_explicit_slots",
        "product_shift_locked",
        "product_switched_before_arrangement",
    ],
)
def test_pending_commit_never_rewrites_started_or_explicit_support(
    confirmation, protection
):
    case = confirmation
    case.support.coordination_commit_pending = True
    case.support.group_shift_expected = {("room_2_2", 0): "苍苔"}
    setattr(case.support, protection, True)
    before = deepcopy(vars(case.support))
    case.solver._refresh_coordination_support(case.support)
    assert vars(case.support) == before


@pytest.mark.parametrize("recall", [True], indirect=True)
@pytest.mark.parametrize("cause", ["full", "personal-limit"])
@pytest.mark.parametrize("retained", [False, True])
def test_per_operator_calculated_rejection_retains_coordination_semantics(
    confirmation, cause, retained
):
    case = confirmation
    data = case.solver.op_data
    case.support.execution_retained = retained
    find = case.find

    def changed_during_selection(template, **kwargs):
        result = find(template, **kwargs)
        if template == "confirm_blue" and result:
            if cause == "full":
                data.operators["苍苔"].rest_in_full = True
            else:
                data.config.operator_mood_limits["苍苔"] = {"lower": 0, "upper": 24}
        return result

    case.solver.find.side_effect = changed_during_selection
    before = deepcopy(case.support.plan), case.support.time
    with pytest.raises(base.ProductSwitchDeferred):
        case.solver.tap_confirm("room_2_2")
    case.solver.tap.assert_not_called()
    case.save.assert_not_called()
    assert (case.support.plan, case.support.time) == before
    assert case.support.coordination_commit_pending
