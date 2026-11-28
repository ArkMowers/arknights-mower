from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers.base_mixin import AgentCardObservationNotReady
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests.agent_page_observation_tests import page
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import config
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scheduler_task import TaskTypes


class ProfessionSearch(Exception):
    pass


class CardsSelected(Exception):
    pass


def frame(name, suffix=".jpg"):
    path = Path(__file__).parent / "fixtures/selection" / (name + "_20261123" + suffix)
    recog = Recognizer(None, path.read_bytes())
    return recog.screencap, recog.img, recog.gray


@pytest.fixture
def dorm(monkeypatch):
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = None
    solver.last_room = ""
    solver.choose_error = set()
    solver.device = MagicMock()
    solver.device.check_current_focus.return_value = False
    solver.recog = Recognizer(solver.device)
    solver.op_data = SimpleNamespace(
        get_current_room=lambda *a: [],
        profession_filter=set(),
        operators={
            name: SimpleNamespace(room="dormitory_4", is_resting=lambda: False)
            for name in ("冰酿", "菲亚梅塔", "杜林", "聆音")
        },
        dorm_mood_estimates={},
    )
    solver.get_order = lambda name: (True, ("技能", "false"))
    solver.prepare_dorm_selection = MagicMock(return_value=[])
    solver.wait_for_arranged_agents = MagicMock(return_value=[])
    solver.clear_agent_selection = MagicMock()
    solver.detect_arrange_order = lambda room: ("心情", True)

    def filter_profession(profession=None):
        if profession is not None:
            raise ProfessionSearch(profession)

    solver.profession_filter = MagicMock(side_effect=filter_profession)
    return solver


def replay(solver, names, sorted_frame, *, after_first=None, **options):
    before = frame("dorm4_mood")
    after = frame(sorted_frame)
    solver.recog.set_frame(before)
    solver.device.screencap.return_value = before

    def sort(*args, **kwargs):
        solver.recog.set_frame(after)
        solver.device.screencap.return_value = after

    solver.switch_arrange_order = MagicMock(side_effect=sort)
    native = solver.scan_agent
    chosen = []

    def scan(*args, **kw):
        hits, page = native(*args, **kw)
        chosen.extend(hits)
        if hits and after_first is not None:
            solver.device.screencap.return_value = frame(after_first)
        if chosen == names:
            raise CardsSelected(chosen)
        return hits, page

    solver.scan_agent = MagicMock(side_effect=scan)
    room = "dormitory_1" if sorted_frame.startswith("dorm1") else "dormitory_4"
    solver.choose_agent(
        names, room, preserve_dorm_occupants=True, recovery_padding=True, **options
    )


@pytest.mark.parametrize("mode", ["high", "low"])
@pytest.mark.parametrize("fresh", [True, False])
def test_named_dorm_entry_keeps_expanded_all_until_visible_target(
    dorm, monkeypatch, mode, fresh
):
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    sidebar = frame("dorm4_all_open_skill", ".webp")
    closed = frame("dorm4_skill_durin")
    current = sidebar
    dorm.recog.set_frame(current)
    dorm.device.screencap.side_effect = lambda: current
    dorm.profession_filter = BaseSchedulerSolver.profession_filter.__get__(dorm)
    dorm.detect_arrange_order = BaseSchedulerSolver.detect_arrange_order.__get__(dorm)
    native = dorm.scan_agent

    def tap(position):
        nonlocal current
        if position == (1860, 60):
            current = closed

    def scan(*args, **kwargs):
        hits, cards = native(*args, **kwargs)
        if hits == ["杜林"]:
            assert kwargs["exclude_sidebar"] == fresh
            raise CardsSelected(hits)
        return hits, cards

    dorm.device.tap.side_effect = tap
    dorm.scan_agent = scan
    with pytest.raises(CardsSelected):
        dorm.choose_agent(["杜林"], "dormitory_4", fresh_room_entry=fresh)
    actions = [call.args[0] for call in dorm.device.tap.call_args_list]
    assert actions == ([(942, 504)] if fresh else [(1860, 60), (942, 504)])


def test_third_dorm_recovery_still_clears_and_reselects_swapped_last_two(monkeypatch):
    planned = ["隐德来希", "蜜莓", "絮雨", "国度", "伊芙利特"]
    previous = [*planned[:3], planned[4], planned[3]]
    solver, selected = selection_solver(monkeypatch, residents=previous)
    solver.reorder_selected_agents = MagicMock(wraps=solver.reorder_selected_agents)
    solver.choose_agent(
        planned.copy(),
        "dormitory_3",
        preserve_dorm_occupants=True,
        recovery_padding=True,
    )
    solver.reorder_selected_agents.assert_called_once_with(planned, previous)
    assert selected == planned
    assert solver.tap.call_count == 6
    assert solver.tap.call_args_list[0].args[0][1] == 1026


@pytest.mark.parametrize("mode", ["high", "low"])
@pytest.mark.parametrize(
    "case",
    ["visible", "clipped_resident", "hidden_target", "unreadable", "extra_highlight"],
)
def test_named_dorm_replacement_verifies_removed_resident_and_all_five_beds(
    monkeypatch, mode, case
):
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    residents = ["杜林", "聆音", "至简", "槐琥", "白面鸮"]
    planned = residents[:4] + ["虎狼丸"]
    solver, selected = selection_solver(monkeypatch, residents=residents)
    solver.preserve_resting_crafters.return_value = []
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.recog.img = solver.recog._img = img
    solver._profession_filter_buttons = MagicMock(
        return_value=(("confirm_blue", 1609, 990),)
    )
    solver._profession_highlighted = lambda point: (
        point[1] == 135 or case == "extra_highlight" and point[1] == 245
    )
    scopes = dict(page(residents))
    observations = []

    def observe(expected, **options):
        assert expected == selected
        observations.append(expected.copy())
        if "card_scopes" in options:
            options["card_scopes"].update(scopes)
            if case == "clipped_resident":
                options["card_scopes"]["白面鸮"] = ((1680, 488), (1850, 520))
        if "slot_numbers" in options:
            options["slot_numbers"].update(
                (name, i) for i, name in enumerate(selected, 1)
            )
        return selected.copy()

    def remove(point, **_):
        if case in ("clipped_resident", "extra_highlight"):
            x, y = solver.agent_selection_positions[4]
            assert point == (1920 * x, 1080 * y)
        else:
            assert point == scopes["白面鸮"]
        selected.remove("白面鸮")

    def scan(pending, **options):
        assert pending == ["虎狼丸"]
        if options["exclude_sidebar"]:
            if case == "hidden_target":
                return [], page(tuple(selected))
            if case == "unreadable":
                raise AgentCardObservationNotReady("姓名范围无法稳定")
        selected.append(pending.pop())
        return ["虎狼丸"], page(tuple(selected))

    solver.tap.side_effect = remove
    solver.wait_for_arranged_agents = MagicMock(side_effect=observe)
    solver.scan_agent.side_effect = scan
    solver.choose_agent(planned.copy(), "dormitory_4", fresh_room_entry=True)
    assert selected == planned
    assert observations[0] == residents and observations[-1] == planned
    assert solver.wait_for_arranged_agents.call_args.kwargs["slot_numbers"] == {
        name: slot for slot, name in enumerate(planned, 1)
    }
    assert solver.profession_filter.call_count == int(case != "visible")
    solver.tap.assert_called_once()


@pytest.mark.parametrize(
    "task, names, options",
    [
        (TaskTypes.FIAMMETTA, ["菲亚梅塔", "杜林"], {}),
        (TaskTypes.RE_ORDER, ["杜林"], {}),
        (TaskTypes.FILL_DORM, ["杜林"], {}),
        (TaskTypes.RELEASE_DORM, ["杜林"], {}),
        (TaskTypes.SHIFT_OFF, ["杜林", "Free"], {}),
        (TaskTypes.SHIFT_OFF, ["杜林", "Current"], {}),
        (TaskTypes.SHIFT_OFF, ["杜林"], {"recovery_padding": True}),
        (TaskTypes.SHIFT_OFF, ["杜林"], {"preserve_dorm_occupants": True}),
        (TaskTypes.SHIFT_OFF, ["杜林"], {"choose_error": 1}),
    ],
)
def test_dorm_entry_closes_sidebar_for_special_selection(dorm, task, names, options):
    current = frame("dorm4_all_open_skill", ".webp")
    dorm.recog.set_frame(current)
    dorm.device.screencap.return_value = current
    dorm.task = SimpleNamespace(type=task, plan={})
    dorm.refresh_dorm_selection_candidates = MagicMock(return_value=None)
    dorm._check_group_shift_targets = MagicMock()
    dorm.profession_filter.side_effect = ProfessionSearch
    with pytest.raises(ProfessionSearch):
        dorm.choose_agent(names, "dormitory_4", fresh_room_entry=True, **options)
    dorm.profession_filter.assert_called_once_with()
    dorm.device.tap.assert_not_called()


@pytest.mark.parametrize(
    "source,targets,points",
    [
        ("dorm4_skill_durin", ["杜林"], [(942, 504)]),
        ("dorm4_selected_durin", ["杜林"], []),
        ("dorm1_skill_snipers", ["冰酿", "菲亚梅塔"], [(1157, 504), (725, 925)]),
    ],
)
def test_dorm_selects_named_cards_on_the_sorted_frame(dorm, source, targets, points):
    with pytest.raises(CardsSelected) as chosen:
        replay(dorm, targets, source)
    assert chosen.value.args == (targets,)
    assert [call.args[0] for call in dorm.device.tap.call_args_list] == points
    assert dorm.profession_filter.call_count == 1
    assert (
        dorm.scan_agent.call_args.kwargs["mood_estimates"]
        is dorm.op_data.dorm_mood_estimates
    )


@pytest.mark.parametrize(
    "source,target,setup",
    [
        ("dorm4_sidebar_open", "杜林", "normal"),
        ("dorm4_skill_durin", "聆音", "normal"),
        ("dorm4_skill_durin", "杜林", "low"),
        ("dorm4_skill_durin", "杜林", "retry"),
        ("dorm4_skill_durin", "杜林", "emergency"),
        ("dorm4_skill_durin", "杜林", "uncertain_border"),
    ],
)
def test_dorm_sort_falls_back_to_its_target_profession(
    dorm, monkeypatch, source, target, setup
):
    if setup == "low":
        monkeypatch.setattr(config.conf, "performance_mode", "low")
    if setup == "emergency":
        dorm.task = SimpleNamespace(emergency_staffing=True, plan={})
    if setup == "uncertain_border":
        monkeypatch.setattr(
            "arknights_mower.solvers.base_schedule.agent_card_selected",
            lambda *args: None,
        )
    with pytest.raises(ProfessionSearch):
        replay(dorm, [target], source, choose_error=int(setup == "retry"))
    assert dorm.profession_filter.call_args.args == (
        "CASTER" if target == "杜林" else "WARRIOR",
    )
    dorm.device.tap.assert_not_called()


def test_sidebar_moved_after_first_card_keeps_second_for_profession_search(dorm):
    with pytest.raises(ProfessionSearch):
        replay(
            dorm,
            ["冰酿", "菲亚梅塔"],
            "dorm1_skill_snipers",
            after_first="dorm4_sidebar_open",
        )
    dorm.device.tap.assert_called_once_with((1157, 504))
    assert dorm.profession_filter.call_args.args == ("SNIPER",)


def test_visible_target_still_requires_its_dorm_mood_check(dorm):
    dorm.recog.set_frame(frame("dorm4_skill_durin"))
    mood_check = MagicMock(return_value=False)
    assert (
        dorm._select_sorted_dorm_targets(
            ["杜林"], mood_check=mood_check, mood_estimates=None
        )
        == []
    )
    assert mood_check.call_args.args[0] == "杜林"
    dorm.device.tap.assert_not_called()


def test_connecting_on_first_sorted_frame_discards_its_card_coordinates(dorm):
    find = dorm.find
    shown = []

    def with_network_overlay(resource, *args, **kwargs):
        if resource == "connecting" and dorm.switch_arrange_order.called and not shown:
            shown.append(True)
            return True
        return find(resource, *args, **kwargs)

    dorm.find = with_network_overlay
    dorm.sleep = MagicMock(side_effect=lambda *a: dorm.recog.update())
    with pytest.raises(ProfessionSearch):
        replay(dorm, ["杜林"], "dorm4_skill_durin")
    assert shown
    dorm.device.tap.assert_not_called()
