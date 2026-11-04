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
            json.dumps({"data": {"characters": characters}}),
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
    monkeypatch.setattr(recruit, "get_cultivate_characters", cache_read)

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
                    "characters": [
                        {"id": agent["id"], "potentialRank": 4}
                        for agent in recruit.agent_with_tags["支援机械"]
                    ]
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
def test_transition_selects_tags_sets_350_and_ignores_permit_floor(
    robot_solver, tickets
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
    current_time = {"hour": 9, "minute": 0}
    solver.get_recruit_time = Mock(side_effect=current_time.get)

    def choose_time(before, after, mode):
        assert current_time[mode] == before
        current_time[mode] = after

    solver.choose_time = Mock(side_effect=choose_time)

    def start(name):
        assert name == "recruit/start_recruit"
        assert current_time == {"hour": 3, "minute": 50}

    solver.tap_element = Mock(side_effect=start)
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
        solver.choose_time.assert_any_call(0, 50, mode="minute")
        solver.choose_time.assert_any_call(9, 3, mode="hour")
        solver.tap_element.assert_called_once_with("recruit/start_recruit")
        solver.back.assert_not_called()
    else:
        solver.tap_element.assert_not_called()
        solver.choose_time.assert_not_called()
        solver.back.assert_called_once_with()
