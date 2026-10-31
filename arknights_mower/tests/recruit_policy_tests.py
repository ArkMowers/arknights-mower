from unittest.mock import Mock

import pytest

from arknights_mower.solvers import recruit


def make_solver(monkeypatch, level, same_results=False):
    solver = recruit.RecruitSolver.__new__(recruit.RecruitSolver)
    solver.recruit_order = [6, 5, 1, 4, 3, 2]
    solver.recruit_order_index = 2
    solver.recruit_index = 1
    solver.agent_choose = {}
    solver.back = Mock()
    results = {star: [] for star in range(1, 7)}
    results[level] = [
        {"tag": ("输出",), "result": [{"id": "a", "name": "甲", "star": level}]},
        {
            "tag": ("控场",),
            "result": [
                {"id": "a", "name": "甲", "star": level}
                if same_results
                else {"id": "b", "name": "乙", "star": level}
            ],
        },
    ]
    solver.recruit_cal = Mock(return_value=results)
    notify = Mock()
    monkeypatch.setattr(recruit, "send_message", notify)
    return solver, notify, results


@pytest.mark.parametrize("mode", [1, 2], ids=["auto", "manual"])
@pytest.mark.parametrize("only_unique", [False, True])
@pytest.mark.parametrize("combination_count", [1, 2])
def test_five_star_selection_policy(monkeypatch, mode, only_unique, combination_count):
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_5", mode)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_only5", only_unique)
    solver, notify, results = make_solver(monkeypatch, 5)
    results[5] = results[5][:combination_count]

    solver.recruit_tags({"输出": (0, 0), "控场": (1, 1)})

    notify.assert_called_once()
    if mode == 1 or (only_unique and combination_count == 1):
        assert solver.recruit_index == 1
        solver.back.assert_not_called()
        assert solver.agent_choose == {
            1: {
                "tags": list(results[5][-1]["tag"]),
                "result": results[5][-1]["result"],
                "level": 5,
                "choosed": False,
            }
        }
    else:
        assert solver.recruit_index == 2
        solver.back.assert_called_once_with()
        assert solver.agent_choose == {}


@pytest.mark.parametrize("only_unique", [False, True])
def test_manual_policy_after_equivalent_results_collapse(monkeypatch, only_unique):
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_5", 2)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_only5", only_unique)
    solver, notify, _ = make_solver(monkeypatch, 5, same_results=True)

    solver.recruit_tags({"输出": (0, 0), "控场": (1, 1)})

    notify.assert_called_once()
    if only_unique:
        assert solver.agent_choose[1]["tags"] == ["控场"]
        assert solver.recruit_index == 1
        solver.back.assert_not_called()
    else:
        assert solver.agent_choose == {}
        assert solver.recruit_index == 2
        solver.back.assert_called_once_with()


@pytest.mark.parametrize("level", [6, 1, 4, 3])
def test_manual_five_star_policy_preserves_other_rarities(monkeypatch, level):
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_5", 2)
    monkeypatch.setattr(recruit.config.conf, "recruit_auto_only5", False)
    solver, notify, _ = make_solver(monkeypatch, level)

    solver.recruit_tags({"输出": (0, 0), "控场": (1, 1)})

    if level in (6, 1):
        notify.assert_called_once()
        assert solver.agent_choose == {}
        assert solver.recruit_index == 2
        solver.back.assert_called_once_with()
    else:
        notify.assert_not_called()
        assert solver.agent_choose[1]["level"] == level
        assert solver.recruit_index == 1
        solver.back.assert_not_called()
