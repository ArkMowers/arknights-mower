import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers import recruit
from arknights_mower.utils import mastery_recommendation

ROBOT_ID = "char_285_medic2"
TAGS = ["支援机械", "医疗干员", "近战位", "远程位", "新手"]


@pytest.fixture
def robot_solver(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: path)
    mastery_recommendation._read_cultivate_data.cache_clear()
    monkeypatch.setattr(recruit, "send_message", Mock())
    monkeypatch.setattr(recruit.config.conf, "recruit_robot", True)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_robot", True)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_5", 1)
    monkeypatch.setattr(recruit.config.conf, "recruitment_permit", 30)

    solver = recruit.RecruitSolver.__new__(recruit.RecruitSolver)
    solver.recruit_order = [6, 5, 1, 4, 3, 2]
    solver.recruit_order_index = 2
    solver.recruit_index = 1
    solver.agent_choose = {}
    solver.back = Mock()

    def save_roster(potential=0):
        characters = [
            {
                "id": agent["id"],
                "potentialRank": potential if agent["id"] == ROBOT_ID else 5,
            }
            for agent in recruit.agent_with_tags["支援机械"]
        ]
        path.write_text(
            json.dumps({"data": {"characters": characters, "items": []}}),
            encoding="utf-8",
        )

    yield solver, path, save_roster
    mastery_recommendation._read_cultivate_data.cache_clear()


def test_robot_automation_defaults_off_and_round_trips():
    from arknights_mower.utils.config.conf import RecruitPart

    assert RecruitPart().recruit_auto_robot is False
    assert (
        RecruitPart.model_validate({"recruit_robot": False}).recruit_auto_robot is False
    )
    saved = RecruitPart(recruit_auto_robot=True, recruit_robot=True).model_dump()
    restored = RecruitPart.model_validate(saved)
    assert restored.recruit_auto_robot is True
    assert restored.recruit_robot is True


@pytest.mark.parametrize("reserve_robot", [False, True])
def test_disabled_automation_keeps_saved_policy(
    robot_solver, monkeypatch, reserve_robot
):
    solver, _, save_roster = robot_solver
    save_roster()
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_robot", False)
    monkeypatch.setattr(recruit.config.conf, "recruit_robot", reserve_robot)
    solver.add_recruit_param()
    cache_read = Mock(side_effect=AssertionError("disabled automation read cache"))
    monkeypatch.setattr(recruit, "get_cultivate_snapshot", cache_read)

    solver.recruit_tags(TAGS)

    cache_read.assert_not_called()
    if reserve_robot:
        assert solver.agent_choose == {}
        solver.back.assert_called_once_with()
    else:
        assert solver.agent_choose[1]["level"] == 3
        solver.back.assert_not_called()


@pytest.mark.parametrize("reserve_robot", [False, True])
@pytest.mark.parametrize("potential", [0, 4])
def test_selects_confirmed_unfinished_robot(
    robot_solver, monkeypatch, reserve_robot, potential
):
    solver, _, save_roster = robot_solver
    save_roster(potential)
    monkeypatch.setattr(recruit.config.conf, "recruit_robot", reserve_robot)
    solver.add_recruit_param()

    solver.recruit_tags(TAGS)

    assert solver.agent_choose[1] == {
        "tags": ["医疗干员", "支援机械"],
        "result": [{"id": ROBOT_ID, "name": "Lancet-2", "star": 1}],
        "level": 1,
        "choosed": False,
    }
    solver.back.assert_not_called()


@pytest.mark.parametrize("potential", [5, None, -1, 6, True, "4"])
@pytest.mark.parametrize("reserve_robot", [False, True])
def test_unconfirmed_or_full_potential_keeps_saved_policy(
    robot_solver, monkeypatch, potential, reserve_robot
):
    solver, _, save_roster = robot_solver
    save_roster(potential)
    monkeypatch.setattr(recruit.config.conf, "recruit_robot", reserve_robot)
    solver.add_recruit_param()

    solver.recruit_tags(TAGS)

    if reserve_robot:
        assert solver.agent_choose == {}
        assert solver.recruit_index == 2
        solver.back.assert_called_once_with()
    else:
        assert solver.agent_choose[1]["level"] == 3
        solver.back.assert_not_called()


@pytest.mark.parametrize("payload", [None, "{", "{}", '{"data":{"characters":[]}}'])
def test_missing_or_invalid_cache_keeps_manual_robot(robot_solver, payload):
    solver, path, _ = robot_solver
    if payload is not None:
        path.write_text(payload, encoding="utf-8")

    solver.recruit_tags(TAGS)

    assert solver.agent_choose == {}
    solver.back.assert_called_once_with()


def test_missing_robot_in_valid_cache_does_not_confirm_potential(robot_solver):
    solver, path, _ = robot_solver
    path.write_text('{"data":{"characters":[{"id":"other"}]}}', encoding="utf-8")

    solver.recruit_tags(TAGS)

    assert solver.agent_choose == {}
    solver.back.assert_called_once_with()


def test_mixed_robot_pool_without_isolating_tags_stays_manual(robot_solver):
    solver, _, save_roster = robot_solver
    save_roster()

    solver.recruit_tags(["支援机械", "近战位", "远程位", "输出", "新手"])

    assert solver.agent_choose == {}
    solver.back.assert_called_once_with()


def test_all_candidates_unfinished_can_select_a_multi_robot_combination(robot_solver):
    solver, path, _ = robot_solver
    path.write_text(
        json.dumps(
            {
                "data": {
                    "items": [],
                    "characters": [
                        {"id": agent["id"], "potentialRank": 4}
                        for agent in recruit.agent_with_tags["支援机械"]
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    solver.recruit_tags(["支援机械", "近战位", "远程位", "新手"])

    assert solver.agent_choose[1]["tags"] == ["支援机械", "近战位"]
    assert {agent["name"] for agent in solver.agent_choose[1]["result"]} == {
        "Castle-3",
        "THRM-EX",
        "Friston-3",
        "CONFESS-47",
    }
    assert solver.agent_choose[1]["level"] == 1
    solver.back.assert_not_called()


@pytest.mark.parametrize(
    "potential,tokens,automatic",
    [(4, 0, True), (4, 1, False), (3, 1, True), (3, 2, False)],
)
def test_unused_tokens_count_toward_full_potential(
    robot_solver, potential, tokens, automatic
):
    solver, path, save_roster = robot_solver
    save_roster(potential)
    payload = json.loads(path.read_text())
    payload["data"]["items"] = [{"id": f"p_{ROBOT_ID}", "count": str(tokens)}]
    path.write_text(json.dumps(payload), encoding="utf-8")

    solver.recruit_tags(TAGS)

    assert (1 in solver.agent_choose) is automatic


@pytest.mark.parametrize(
    "items",
    [
        None,
        {},
        [{"id": f"p_{ROBOT_ID}", "count": "bad"}],
        [{"id": f"p_{ROBOT_ID}", "count": -1}],
    ],
)
def test_unknown_token_inventory_does_not_auto_recruit(robot_solver, items):
    solver, path, save_roster = robot_solver
    save_roster()
    payload = json.loads(path.read_text())
    payload["data"]["items"] = items
    path.write_text(json.dumps(payload), encoding="utf-8")

    solver.recruit_tags(TAGS)

    assert solver.agent_choose == {}


def test_started_robot_recruitment_reserves_candidates_in_same_run(robot_solver):
    solver, _, save_roster = robot_solver
    save_roster(4)
    solver.recruit_tags(TAGS)
    solver.agent_choose[1]["choosed"] = True
    solver.recruit_index = 2

    solver.recruit_tags(TAGS)

    assert 2 not in solver.agent_choose
    assert solver.recruit_index == 3


@pytest.mark.parametrize(
    "rare_tag, level", [("快速复活", 4), ("资深干员", 5), ("高级资深干员", 6)]
)
@pytest.mark.parametrize("reserve_robot", [False, True])
def test_higher_rarity_keeps_saved_policy(
    robot_solver, monkeypatch, rare_tag, level, reserve_robot
):
    solver, _, save_roster = robot_solver
    save_roster()
    monkeypatch.setattr(recruit.config.conf, "recruit_robot", reserve_robot)
    solver.add_recruit_param()

    solver.recruit_tags(["支援机械", "医疗干员", rare_tag, "近战位", "新手"])

    if (reserve_robot and level == 4) or level == 6:
        assert solver.agent_choose == {}
        solver.back.assert_called_once_with()
    else:
        assert solver.agent_choose[1]["level"] == level


def test_without_robot_tag_keeps_three_star_selection(robot_solver):
    solver, _, save_roster = robot_solver
    save_roster()

    solver.recruit_tags(["医疗干员", "近战位", "远程位", "新手"])

    assert solver.agent_choose[1]["level"] == 3


@pytest.mark.parametrize("tickets", [0, 1, 30])
@pytest.mark.parametrize("initial_time", [(1, 0), (9, 0), (4, 20), (3, 50)])
def test_transition_selects_tags_sets_350_and_ignores_permit_floor(
    robot_solver, tickets, initial_time
):
    solver, _, save_roster = robot_solver
    save_roster()
    solver.scene = Mock(return_value=recruit.Scene.RECRUIT_TAGS)
    solver.refresh = False
    solver.tags = {1: {tag: (index * 200, 520) for index, tag in enumerate(TAGS)}}
    solver.get_ticket_number = Mock(return_value=tickets)
    solver.recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))
    solver.find = Mock(return_value=(10, 10))
    selected = set()
    solver.tag_not_choosed = Mock(side_effect=lambda _: len(selected) < 2)
    solver.tap = Mock(side_effect=selected.add)
    current_time = dict(zip(("hour", "minute"), initial_time))
    solver.get_recruit_time = Mock(side_effect=current_time.get)

    def start(name):
        assert name == "recruit/start_recruit"
        assert current_time == {"hour": 3, "minute": 50}

    def tap_element(name, x_rate=0.5, y_rate=0.5, interval=1):
        if name != "one_hour":
            return start(name)
        direction = 1 if y_rate == 0.2 else -1
        total = current_time["hour"] * 60 + current_time["minute"]
        total += direction * (10 if x_rate == 0.5 else 60)
        if total < 60:
            total = 540
        elif total > 540:
            total = 60
        current_time["hour"], current_time["minute"] = divmod(total, 60)

    solver.tap_element = Mock(side_effect=tap_element)
    solver.wait_for_scene_stable = Mock(return_value=True)

    solver.transition()
    assert solver.agent_choose[1]["level"] == 1
    for _ in range(5 if tickets else 2):
        if solver.recruit_index > 1:
            break
        solver.transition()

    assert selected == {solver.tags[1]["医疗干员"], solver.tags[1]["支援机械"]}
    solver.find.assert_not_called()
    assert solver.recruit_index == 2
    if tickets:
        assert solver.agent_choose[1]["choosed"] is True
        assert solver.ticket_number == tickets - 1
        assert solver.tap_element.call_args.args == ("recruit/start_recruit",)
        assert solver.tap_element.call_count == (
            abs(initial_time[0] - 3) + abs(initial_time[1] - 50) // 10 + 1
        )
        if initial_time[0] != 3:
            assert solver.tap_element.call_args_list[0].args[1] == 0.2
        solver.back.assert_not_called()
    else:
        solver.tap_element.assert_not_called()
        solver.back.assert_called_once_with()


@pytest.mark.parametrize("before", [0, 10, 20, 30, 40, 50])
@pytest.mark.parametrize("after", [0, 10, 20, 30, 40, 50])
def test_minute_adjustment_reaches_target_on_cyclic_game_control(before, after):
    solver = recruit.RecruitSolver.__new__(recruit.RecruitSolver)
    current = before

    def tap_element(name, x_rate, y_rate, interval):
        nonlocal current
        assert name == "one_hour" and x_rate == 0.5
        current = (current + (10 if y_rate == 0.2 else -10)) % 60

    solver.tap_element = Mock(side_effect=tap_element)

    solver.choose_time(before, after, mode="minute")

    assert current == after
    assert solver.tap_element.call_count <= 5


def test_nine_hour_recruitment_clears_minutes_before_setting_hours(robot_solver):
    solver, _, _ = robot_solver
    solver.scene = Mock(return_value=recruit.Scene.RECRUIT_TAGS)
    solver.refresh = False
    solver.tags = {1: {}}
    solver.agent_choose = {1: {"tags": [], "level": 3, "result": [], "choosed": False}}
    solver.find = Mock(return_value=None)
    solver.get_ticket_number = Mock(return_value=30)
    current = {"hour": 3, "minute": 50}
    solver.get_recruit_time = current.get

    def tap_element(name, x_rate=0.5, y_rate=0.5, interval=1):
        if name == "recruit/start_recruit":
            assert current == {"hour": 9, "minute": 0}
            return
        total = current["hour"] * 60 + current["minute"]
        total += (1 if y_rate == 0.2 else -1) * (10 if x_rate == 0.5 else 60)
        if total < 60:
            total = 540
        elif total > 540:
            total = 60
        current["hour"], current["minute"] = divmod(total, 60)

    solver.tap_element = Mock(side_effect=tap_element)
    solver.wait_for_scene_stable = Mock(return_value=True)

    for _ in range(3):
        solver.transition()

    assert solver.agent_choose[1]["choosed"] is True
    assert solver.tap_element.call_args_list[0].args == ("one_hour", 0.5, 0.8, 0.1)
    assert solver.tap_element.call_args.args == ("recruit/start_recruit",)
