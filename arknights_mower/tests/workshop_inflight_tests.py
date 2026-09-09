"""Exercise the real crafting loop while HTTP configuration restores its recipes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_automation_tests import manual_setting
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils import workshop_config as state


@pytest.mark.parametrize("entry", ["workshop", "release", "direct"])
@pytest.mark.parametrize("cancel_at", [None, "scan", "selection", "submit"])
@pytest.mark.parametrize("cancel_by", ["disable", "delete"])
def test_restore_during_real_crafting_never_submits_manual_recipe(
    next_skill, monkeypatch, cancel_at, cancel_by, entry
):
    import server
    from arknights_mower.solvers import base_schedule as base
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    manual = manual_setting()
    manual.operator = "赫拉格"
    config.conf.workshop_settings = [manual]
    auto.update_workshop_config()
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM if entry == "release" else TaskTypes.WORKSHOP,
        meta_data="赫拉格",
        task_plan={"dormitory_1": ["Free"]} if entry == "release" else {},
    )
    if entry == "workshop":
        auto.stamp_workshop_task(task)
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = task
    solver.tasks = [task]
    solver.recog = MagicMock(w=1920, h=1080)
    solver.op_data = SimpleNamespace(
        operators={
            "赫拉格": SimpleNamespace(
                current_room="dormitory_1" if entry == "release" else "factory",
                current_index=0,
                mood=24,
                is_high=lambda: False,
            )
        }
    )
    for method in [
        "enter_room",
        "agent_arrange",
        "back",
        "back_to_infrastructure",
        "swipe_noinertia",
        "backup_plan_solver",
        "plan_metadata",
    ]:
        setattr(solver, method, MagicMock())
    solver.factory_scene = MagicMock(
        side_effect=[
            base.Scene.FACTORY_DASHBOARD,
            base.Scene.FACTORY_DASHBOARD,
            base.Scene.FACTORY_FORMULA,
            base.Scene.FACTORY_DASHBOARD,
            base.Scene.FACTORY_PRODUCT_COLLECT,
            base.Scene.FACTORY_PRODUCT_COLLECT,
            base.Scene.FACTORY_DASHBOARD,
            base.Scene.FACTORY_FORMULA,
        ]
    )
    submitted = []
    selected = []
    produce_btn = (1920 * 0.88, 1080 * 0.88)
    solver.tap = MagicMock(side_effect=lambda pos, **kw: submitted.append(pos))
    solver.find = lambda name: name == "factory_warning" and produce_btn in submitted

    def cancel(stage):
        if stage != cancel_at:
            return
        if cancel_by == "disable":
            req = state.read_user_config()
            req["enable_mastery"] = False
            assert server.app.test_client().post("/conf", json=req).status_code == 200
        else:
            next_skill.plans.clear()
            auto.restore_if_no_plans()
        if entry == "workshop":
            assert not auto.workshop_task_current(task)
        assert config.conf.workshop_settings == [manual]

    def items():
        cancel("selection")
        selected.append(True)
        return [
            ("技巧概要·卷3", ((10, 10), (20, 20)), True),
            ("碳素组", ((30, 30), (40, 40)), True),
        ]

    def valid():
        cancel("submit")
        return produce_btn not in submitted

    solver.item_list = items
    solver.item_valid = valid
    monkeypatch.setattr(
        base,
        "cultivateDepotSolver",
        lambda: SimpleNamespace(start=lambda: cancel("scan")),
    )
    stock = {"技巧概要·卷3": 0, "技巧概要·卷2": 100, "碳素组": 0, "碳": 100}
    monkeypatch.setattr(base, "get_inventory_counts", lambda: dict(stock))
    monkeypatch.setattr(
        base,
        "apply_workshop_inventory",
        lambda delta: stock.update(
            {name: stock.get(name, 0) + n for name, n in delta.items()}
        ),
    )
    errors = MagicMock()
    monkeypatch.setattr(base, "save_exception", errors)
    if entry == "release":
        solver.infra_main()
    elif entry == "direct":
        solver.generate_product("赫拉格")
    else:
        solver.craft_material()
    errors.assert_not_called()
    assert submitted.count(produce_btn) == (1 if cancel_at is None else 0)
    if cancel_at == "scan":
        assert selected == []


def test_running_task_uses_a_deep_snapshot(next_skill):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    auto.update_workshop_config()
    task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="赫拉格")
    auto.stamp_workshop_task(task)
    snapshot = auto.workshop_task_snapshot(task)
    original = snapshot.settings[0].items[0].item_names[:]
    config.conf.workshop_settings[0].items[0].item_names[:] = ["碳素组"]
    assert snapshot.settings[0].items[0].item_names == original
