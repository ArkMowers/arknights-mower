"""卡片预估复用选人帧；实读缓存和恢复计时保持独立。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_mixin, record
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import dorm_empty_release_tests, dorm_recovery_tests
from arknights_mower.tests.choose_agent_filter_tests import RESIDENTS, selection_solver
from arknights_mower.utils import resting_priority
from arknights_mower.utils.character_recognize import estimate_agent_mood
from arknights_mower.utils.dorm_candidates import dorm_candidate_mood, dorm_candidates
from arknights_mower.utils.dorm_recovery import DormRecoveryPaddingUnavailable
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.resting_priority import has_resting_mood
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_add_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
arrangement_solver = dorm_recovery_tests.solver
ROOM = dorm_empty_release_tests.ROOM
FIXTURES = Path(__file__).parent / "fixtures" / "selection"
SCOPE = ((0, 32), (189, 64))


@pytest.fixture(autouse=True)
def no_persistent_actions(monkeypatch):
    monkeypatch.setattr(record, "save_agent_action", MagicMock())


def strip(label):
    return cv2.cvtColor(
        cv2.imread(str(FIXTURES / f"mood_{label}_20261001.png")), cv2.COLOR_BGR2RGB
    )


@pytest.mark.parametrize(
    "label,expected",
    [("zero", 0), ("low", 1), ("low_selected", 1), ("full", 24), ("full_selected", 24)],
)
def test_emulator_card_estimates(label, expected):
    assert estimate_agent_mood(strip(label), SCOPE) == pytest.approx(expected, abs=1)


@pytest.mark.parametrize("fraction", [0.25, 0.5, 0.75])
def test_partial_bar_ratio(fraction):
    frame = strip("low")
    frame[15:19, 45:171] = 80
    frame[15:19, 45 : 45 + round(126 * fraction)] = 255
    assert estimate_agent_mood(frame, SCOPE) == pytest.approx(24 * fraction, abs=0.3)


@pytest.mark.parametrize("damage", ["blank", "icon", "bar", "disconnected", "cropped"])
def test_unreadable_card_remains_unknown(damage):
    frame = strip("low")
    frame[15:19, 45:171] = 255
    if damage == "blank":
        frame[:] = 0
    elif damage == "icon":
        frame[4:30, 16:43] = 0
    elif damage == "bar":
        frame[15:19, 45:171] = 0
    elif damage == "disconnected":
        frame[15:19, 75:130] = 80
    elif damage == "cropped":
        frame = frame[:, :180]
    assert estimate_agent_mood(frame, SCOPE) is None


@pytest.mark.parametrize("label,expected", [("zero", 0), ("full", 24)])
def test_clear_face_does_not_need_readable_bar(label, expected):
    frame = strip(label)
    frame[15:19, 45:171] = 0
    assert estimate_agent_mood(frame, SCOPE) == expected


def test_yellow_face_with_long_bar_never_becomes_full():
    frame = strip("low")
    frame[15:19, 45:171] = 255
    assert estimate_agent_mood(frame, SCOPE) < 24


def test_yellow_face_with_short_bar_is_not_zero():
    frame = strip("low")
    frame[15:19, 45:171] = 80
    assert 0 < estimate_agent_mood(frame, SCOPE) < 1


def test_color_washed_out_by_selection_remains_unknown():
    assert estimate_agent_mood(strip("zero_selected"), SCOPE) is None


@pytest.mark.parametrize(
    "label,expected", [("zero", 0), ("full", 24), ("full_selected", 24)]
)
def test_color_endpoints_are_exact(label, expected):
    assert estimate_agent_mood(strip(label), SCOPE) == expected


@pytest.mark.parametrize("slow", [False, True])
@pytest.mark.parametrize(
    "full_only,cache", [(False, True), (True, True), (True, False)]
)
def test_scan_uses_existing_frame_without_per_candidate_capture(
    monkeypatch, slow, full_only, cache
):
    instance = object.__new__(BaseMixin)
    page = (("满条", SCOPE), ("低条", ((0, 96), (189, 128))))
    frame = np.concatenate([strip("full"), strip("low")])
    instance.recog = SimpleNamespace(img=frame, update=MagicMock())
    instance.tap = MagicMock()
    instance.find = MagicMock(return_value=False)
    monkeypatch.setattr(BaseMixin, "low_frame_rate_mode", property(lambda self: slow))
    instance.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list", MagicMock(return_value=page))
    monkeypatch.setattr(
        base_mixin, "agent_card_selected", lambda *args, **kwargs: False
    )
    estimates = {}
    remaining = ["满条", "低条"]
    selected, _ = instance.scan_agent(
        remaining,
        max_agent_count=1,
        mood_estimates=estimates if cache else None,
        skip_full_mood=not full_only,
        require_full_mood=full_only,
    )
    assert selected == (["满条"] if full_only else ["低条"])
    assert remaining == (["低条"] if full_only else ["满条"])
    instance.tap.assert_called_once()
    assert instance.recog.update.call_count == (0 if slow else 1)
    assert instance.wait_for_agent_page.call_count == (1 if slow else 0)
    if cache:
        assert estimates["满条"][0] == 24
        assert estimates["低条"][0] < 3


def test_estimates_do_not_establish_verified_full_or_timers(solver):
    instance, _ = solver
    data = instance.op_data
    op = data.operators["红"]
    op.time_stamp = None
    snapshot = (op.mood, op.time_stamp, op.depletion_rate)
    data.dorm_mood_estimates["红"] = (24, datetime.now())
    candidates = dorm_candidates(data)
    assert "红" not in candidates.unknown
    assert "红" not in candidates.full
    assert "红" in candidates.filling
    assert not has_resting_mood(op)
    assert snapshot == (op.mood, op.time_stamp, op.depletion_rate)
    assert not data.rest_mood_complete("红")


def test_temporary_named_dorm_selection_observes_card_moods(monkeypatch):
    instance, selected = selection_solver(monkeypatch, residents=[])
    scan = instance.scan_agent.side_effect

    def observe(names, **kwargs):
        estimates = kwargs.get("mood_estimates")
        assert estimates is instance.op_data.dorm_mood_estimates
        result = scan(names, **kwargs)
        for name in result[0]:
            estimates[name] = (24, datetime.now())
        return result

    instance.scan_agent.side_effect = observe
    final = RESIDENTS + ["伊芙利特"]
    instance.choose_agent(final.copy(), ROOM, False, preserve_dorm_occupants=True)
    assert selected == final
    assert set(instance.op_data.dorm_mood_estimates) == set(final)


@pytest.mark.parametrize("count", [1, 2])
def test_padding_selects_visible_descending_cards_without_registration(
    monkeypatch, count
):
    instance, selected = selection_solver(monkeypatch, residents=[])
    assert not instance.op_data.operators
    worker = Operator("杜林", "")
    worker._current_room = "meeting"
    instance.op_data.operators[worker.name] = worker
    instance.get_dorm_candidates = MagicMock(
        return_value=SimpleNamespace(filling=["梅", "闪灵", "杜林", "伊芙利特", "妮芙"])
    )
    scan = instance.scan_agent.side_effect
    owned = ["伊芙利特", "妮芙"][:count]

    def observe(names, **kwargs):
        if kwargs.get("require_full_mood"):
            assert instance.switch_arrange_order.call_args.args == ("心情", ROOM, False)
            assert "梅" in names  # 图鉴姓名可以是搜索池，不能指定不存在者。
            assert "闪灵" not in names
            assert "杜林" not in names
            assert all(name not in instance.op_data.operators for name in owned)
            result = scan(owned.copy(), **kwargs)
            for name in result[0]:
                kwargs["mood_estimates"][name] = (24, datetime.now())
            return result
        return scan(names, **kwargs)

    instance.scan_agent.side_effect = observe
    agents = ["爱丽丝"] + ["Free"] * count
    instance.choose_agent(
        agents, ROOM, False, preserve_dorm_occupants=True, recovery_padding=True
    )
    assert selected == agents == ["爱丽丝"] + owned
    assert set(instance.op_data.operators) == set(owned) | {worker.name}
    assert all(instance.op_data.operators[name].time_stamp is None for name in owned)


@pytest.mark.parametrize("mood", [None, 23.9])
def test_descending_unavailable_cards_stop_padding_search_without_retry(
    monkeypatch, mood
):
    instance, selected = selection_solver(monkeypatch, residents=[])
    instance.get_dorm_candidates = MagicMock(
        return_value=SimpleNamespace(filling=["杜林", "梅"])
    )
    scan = instance.scan_agent.side_effect

    def observe(names, **kwargs):
        if kwargs.get("require_full_mood"):
            if mood is None:
                return [], [("闪灵", None)]
            kwargs["mood_estimates"]["杜林"] = (mood, datetime.now())
            return [], [("杜林", None)]
        return scan(names, **kwargs)

    instance.scan_agent.side_effect = observe
    instance.swipe_agent_page.side_effect = base_mixin.AgentSelectionNotReady(
        "已到末页"
    )
    with pytest.raises(DormRecoveryPaddingUnavailable):
        instance.choose_agent(
            ["爱丽丝", "Free"],
            ROOM,
            False,
            preserve_dorm_occupants=True,
            recovery_padding=True,
        )
    assert selected == ["爱丽丝"]
    assert instance.swipe_agent_page.call_count == (1 if mood is None else 0)
    assert not instance.op_data.operators


def test_low_card_stays_unknown_and_sorts_before_full_unknown(solver):
    instance, _ = solver
    data = instance.op_data
    data.add(Operator("陈", ""))
    for name in ("红", "陈"):
        data.operators[name].time_stamp = None
    data.dorm_mood_estimates["红"] = (5, datetime.now())
    candidates = dorm_candidates(data)
    assert candidates.unknown[:2] == ["红", "陈"]
    assert "红" not in candidates.recovering


@pytest.mark.parametrize("age", [-1, 3600, 7200])
def test_expired_or_future_estimate_is_unknown(solver, age):
    instance, _ = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    now = datetime.now()
    data.dorm_mood_estimates["红"] = (24, now - timedelta(seconds=age))
    assert dorm_candidate_mood(data, "红", now) is None
    assert "红" in dorm_candidates(data, now=now).unknown


def test_room_readback_overrides_estimate_and_new_search_clears_it(solver):
    instance, _ = solver
    data = instance.op_data
    data.dorm_mood_estimates["红"] = (24, datetime.now())
    assert dorm_candidate_mood(data, "红") == 24
    data.update_detail("红", 8, "", -1, True)
    assert "红" not in data.dorm_mood_estimates
    data.dorm_mood_estimates["红"] = (24, datetime.now())
    assert dorm_candidate_mood(data, "红") == 24
    assert data.operators["红"].mood == 8
    data.refresh_idle_dorm_search(reason="干员下班")
    assert data.dorm_mood_estimates == {}


def test_cached_occupancy_read_preserves_estimate_until_measurement(solver):
    instance, _ = solver
    data = instance.op_data
    op = data.operators["空爆"]
    estimate = (6, datetime.now())
    data.dorm_mood_estimates[op.name] = estimate
    data.update_detail(op.name, op.mood, op.current_room, op.current_index, False)
    assert data.dorm_mood_estimates[op.name] == estimate
    data.update_detail(op.name, 8, op.current_room, op.current_index, True)
    assert op.name not in data.dorm_mood_estimates


def test_position_change_invalidates_only_moved_operator_estimate(solver):
    instance, _ = solver
    data = instance.op_data
    now = datetime.now()
    data.dorm_mood_estimates = {"空爆": (24, now), "红": (6, now)}
    data.update_detail("空爆", 24, "", -1, False)
    assert data.dorm_mood_estimates == {"红": (6, now)}


def test_full_estimate_keeps_full_resident_without_trial_admission(solver):
    instance, _ = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    data.dorm_mood_estimates["红"] = (24, datetime.now())
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []
    plan = instance.task.plan[ROOM]
    instance.prepare_dorm_selection(plan, ROOM)
    assert plan[-1] == "空爆"


def test_full_estimate_still_fills_vacant_bed(solver):
    instance, _ = solver
    data = instance.op_data
    for name in ("空爆", "红"):
        data.operators[name].time_stamp = None
        data.dorm_mood_estimates[name] = (24, datetime.now())
    data.update_detail("空爆", -1, "", -1, False)
    data.dorm_mood_estimates["空爆"] = (24, datetime.now())
    data.dorm[0].reset()
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks and tasks[0].plan[ROOM][-1] in ("红", "空爆")


@pytest.mark.parametrize("estimated,expected", [(24, "空爆"), (6, "红")])
def test_unknown_card_screening_preserves_full_resident_only_without_lower_card(
    solver, estimated, expected
):
    instance, selected = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    scan = instance.scan_agent.side_effect
    observations = []

    def screen(names, max_agent_count=None, **kwargs):
        if kwargs.get("skip_full_mood"):
            observations.append(set(names))
            kwargs["mood_estimates"]["红"] = (estimated, datetime.now())
            if estimated >= 23.5:
                return [], (("红", None),)
            names[:] = ["红"]
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = screen
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert observations
    assert plan[-1] == expected
    assert selected == plan
    assert data.operators["红"].time_stamp is None


@pytest.mark.parametrize("mode", ["high", "medium"])
@pytest.mark.parametrize("verified", [False, True])
def test_full_resident_retention_cancels_selection_and_stops_release_cycle(
    solver, monkeypatch, mode, verified
):
    instance, selected = solver
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    data = instance.op_data
    data.operators["红"].time_stamp = None
    plan = instance.task.plan[ROOM]
    expected = selected.copy()
    scan = instance.scan_agent.side_effect
    set_filter = instance.profession_filter.side_effect
    profession = "ALL"
    screened = False

    def filter_cards(value=None):
        nonlocal profession
        profession = value or "ALL"
        set_filter(value)

    def scan_page(names, **kwargs):
        nonlocal screened
        if kwargs.get("skip_full_mood"):
            screened = True
            kwargs["mood_estimates"]["红"] = (24, datetime.now())
            return [], (("红", None),)
        # 原住者取消选择后位于全部职业列表的后段；职业筛选才能就近找回。
        if screened and profession == "ALL" and "空爆" in names:
            visible = [name for name in names if name != "空爆"]
            found, page = scan(visible, **kwargs)
            for name in found:
                names.remove(name)
            return found, page
        return scan(names, **kwargs)

    instance.profession_filter.side_effect = filter_cards
    instance.scan_agent.side_effect = scan_page

    if not verified:
        instance._cancel_unchanged_dorm_selection.side_effect = (
            base_mixin.AgentSelectionNotReady("未返回房间")
        )
        with pytest.raises(base_mixin.AgentSelectionNotReady, match="未返回房间"):
            instance.choose_agent(plan, ROOM)
        assert plan == expected
        assert data.operators["空爆"].dorm_mood_fallback == ""
        return

    assert instance.choose_agent(plan, ROOM) is False

    assert screened
    assert selected == plan == expected
    instance.swipe_agent_page.assert_not_called()
    instance._cancel_unchanged_dorm_selection.assert_called_once()
    assert data.idle_dorm_release_suspended
    assert data.config.free_room
    # 连续调度不能重建同一清退；独立回班仍可执行，新的低心情观测仍可补位。
    data.operators["银灰"]._current_room = ""
    data.operators["红"]._current_room = "meeting"
    for _ in range(3):
        tasks = plan_metadata(data, [])
        try_add_release_dorm({}, None, data, tasks)
        assert [(task.type, task.plan) for task in tasks] == [
            (TaskTypes.SHIFT_ON, {"meeting": ["银灰"]})
        ]
    data.operators["银灰"]._current_room = "meeting"
    data.update_detail("红", 6, "", -1, True)
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert [task.plan for task in tasks] == [{ROOM: ["Current"] * 4 + ["红"]}]


@pytest.mark.parametrize("estimate", [None, 6, 20, 24])
def test_personal_limit_candidate_requires_valid_low_scheduling_mood(solver, estimate):
    instance, _ = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    data.config.operator_mood_limits["红"] = {"lower": 0, "upper": 20}
    data.operators["红"].upper_limit = 20
    if estimate is not None:
        data.dorm_mood_estimates["红"] = (estimate, datetime.now())
    candidates = dorm_candidates(data)
    assert ("红" in candidates.filling) == (estimate == 6)
    assert ("红" in candidates.estimated_recovering) == (estimate == 6)
    assert "红" not in candidates.recovering
    assert data.operators["红"].time_stamp is None


def test_unregistered_full_card_keeps_free_through_projection_and_selection(
    solver, monkeypatch
):
    instance, selected = solver
    data = instance.op_data
    monkeypatch.setattr(resting_priority, "agent_list", ["伊芙利特"])
    data.config.free_blacklist = ["红", "空爆"]
    data.update_detail("空爆", 24, "", -1, True)
    data.dorm[0].reset()
    data.dorm_mood_estimates["伊芙利特"] = (24, datetime.now())
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM][-1] == "Free"
    data.project_arrangements([tasks[0].plan])
    instance.task = tasks[0]
    plan = instance.task.plan[ROOM]
    plan[:4] = selected[:4]
    assert instance.prepare_dorm_selection(plan, ROOM) == []
    assert plan[-1] == "Free"
    selected.pop()
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == "伊芙利特"
    assert "伊芙利特" in data.operators
    assert data.operators["伊芙利特"].time_stamp is None


def test_full_card_retention_uses_current_frame_over_old_measured_mood(solver):
    instance, selected = solver
    data = instance.op_data
    data.operators["红"].mood = 21
    data.operators["红"].upper_limit = 20
    data.operators["空爆"].upper_limit = 20
    scan = instance.scan_agent.side_effect
    observed = []

    def screen(names, max_agent_count=None, **kwargs):
        if kwargs.get("skip_full_mood"):
            observed.append(set(names))
            kwargs["mood_estimates"]["红"] = (24, datetime.now())
            return [], (("红", None),)
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = screen
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM, dorm_mood_candidates=["红", "空爆"])
    assert observed and plan[-1] == "空爆"
    assert selected == plan


def test_multi_bed_retention_never_selects_the_same_resident_twice(solver):
    instance, selected = solver
    data = instance.op_data
    for name in ("桃金娘", "空爆"):
        data.operators[name].upper_limit = 20
        data.operators[name].mood = 20
    instance.task.dorm_mood_residents = ["桃金娘", "空爆"]
    plan = instance.task.plan[ROOM]
    plan[3:] = ["Free", "Free"]
    scan = instance.scan_agent.side_effect
    scan([])
    observations = []

    def screen(names, max_agent_count=None, **kwargs):
        if kwargs.get("skip_full_mood"):
            observations.append(set(names))
            if len(observations) == 1:
                kwargs["mood_estimates"]["桃金娘"] = (23, datetime.now())
                names[:] = ["桃金娘"]
            else:
                kwargs["mood_estimates"]["红"] = (24, datetime.now())
                return [], (("红", None),)
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = screen
    instance.choose_agent(plan, ROOM, dorm_mood_candidates=["桃金娘", "空爆", "红"])
    assert len(observations) == 2
    assert plan[3:] == ["桃金娘", "空爆"]
    assert selected == plan and len(set(selected)) == len(selected)


@pytest.mark.parametrize("invalid", [None, np.empty((0, 310), dtype=np.uint8)])
def test_failed_detail_read_does_not_become_full(invalid):
    assert BaseMixin.read_accurate_mood(object.__new__(BaseMixin), invalid) == -1


@pytest.mark.parametrize("estimate", [float("nan"), float("inf"), -1, 25])
def test_invalid_estimate_cannot_override_numeric_mood(solver, estimate):
    instance, _ = solver
    data = instance.op_data
    op = data.operators["红"]
    op.mood, op.time_stamp, op.depletion_rate = 6, datetime.now(), 0
    data.dorm_mood_estimates[op.name] = (estimate, datetime.now())
    assert dorm_candidate_mood(data, op.name) == 6


@pytest.mark.parametrize("resident", ["空爆", "但书"])
def test_other_room_changes_use_visible_full_filler_instead_of_old_resident(
    solver, resident
):
    instance, selected = solver
    data = instance.op_data
    old = data.operators.pop("空爆")
    old.name = resident
    data.operators[resident] = old
    data.dorm[0].name = resident
    instance.task.meta_data = resident
    data.operators["红"].time_stamp = None
    plan = data.get_current_room(ROOM, True)
    plan[0], plan[1] = plan[1], plan[0]
    plan[-1] = "Free"
    instance.task.plan[ROOM] = plan
    scan = instance.scan_agent.side_effect

    def scan_page(names, **kwargs):
        if kwargs.get("skip_full_mood"):
            kwargs["mood_estimates"]["红"] = (24, datetime.now())
            return [], (("红", None),)
        visible = [name for name in names if name != resident]
        found, page = scan(visible, **kwargs)
        for name in found:
            names.remove(name)
        return found, page

    instance.scan_agent.side_effect = scan_page
    instance.choose_agent(plan, ROOM, False, dorm_mood_candidates=["红", resident])

    assert selected == plan
    assert plan[-1] == "红"
    assert resident not in selected
    assert data.idle_dorm_release_suspended
    assert instance.task.idle_dorm_search_names == {ROOM: {"红"}}
    instance._cancel_unchanged_dorm_selection.assert_not_called()
    instance.swipe_agent_page.assert_not_called()


@pytest.mark.parametrize("finished", [False, True])
def test_cancel_unchanged_selection_discards_pending_staffing(finished):
    instance = object.__new__(BaseSchedulerSolver)
    instance.recog = SimpleNamespace(w=1920, h=1080, update=MagicMock())
    instance.scene = MagicMock(
        side_effect=[
            Scene.INFRA_ARRANGE_ORDER,
            Scene.CONNECTING,
            Scene.INFRA_ARRANGE_CONFIRM,
            Scene.INFRA_DETAILS,
        ]
        if finished
        else [Scene.INFRA_ARRANGE_ORDER] * 8
    )
    instance.back = MagicMock()
    instance.tap = MagicMock()
    instance.sleep = MagicMock()
    if finished:
        instance._cancel_unchanged_dorm_selection()
        instance.back.assert_called_once_with(interval=0.5)
        instance.tap.assert_called_once_with((640, 1070), interval=0.5)
    else:
        with pytest.raises(base_mixin.AgentSelectionNotReady, match="有限次数"):
            instance._cancel_unchanged_dorm_selection()
        assert instance.back.call_count == 8
        instance.tap.assert_not_called()


def test_cancelled_selection_reads_back_without_submit_or_timer_reset(
    arrangement_solver,
):
    instance = arrangement_solver
    actual = instance.physical.copy()
    instance.task.plan = {ROOM: actual[:4] + ["Free"]}
    instance.prepare_dorm_selection = MagicMock(return_value=[])
    instance.ensure_dorm_recovery_order = MagicMock(return_value=False)
    instance.op_data.invalidate_dorm_time = MagicMock()
    independent = SchedulerTask(task_plan={"meeting": ["黑角"]})
    instance.tasks.append(independent)

    def cancel(agents, *args, **kwargs):
        agents[:] = actual
        return False

    instance.choose_agent.side_effect = cancel
    instance.agent_arrange_room({}, ROOM, instance.task.plan)

    assert instance.task.plan == {}
    assert instance.physical == actual
    instance.tap_confirm.assert_not_called()
    instance.op_data.invalidate_dorm_time.assert_not_called()
    assert instance.get_agent_from_room.call_count >= 1
    assert independent.plan == {"meeting": ["黑角"]}
    assert independent in instance.tasks
