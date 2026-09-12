"""Exercise real assistant preparation and slot reading through the start scene loop."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.tests.mastery_support_fixtures import (
    context_game as context_game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    database as database,
)
from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    stat,
)
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_support_types import StageSpec
from arknights_mower.utils.scene import Scene


def scene_solver(transient, readable, support_name="艾丽妮"):
    solver = MagicMock()
    solver.recog.w, solver.recog.h = 1920, 1080
    current = [Scene.TRAIN_MAIN]
    events = []
    solver.train_scene.side_effect = lambda: current[0]

    def tap(position, **kwargs):
        if position == "close":
            assert current[0] == Scene.INFRA_DETAILS
            events.append("close")
            current[0] = Scene.TRAIN_MAIN
        elif current[0] == Scene.TRAIN_MAIN:
            current[0] = Scene.TRAIN_SKILL_SELECT
        else:
            assert current[0] == Scene.TRAIN_SKILL_UPGRADE
            events.append("confirm")

    def back():
        assert current[0] == Scene.TRAIN_SKILL_SELECT
        events.append("back")
        current[0] = transient

    def sleep(*args):
        if current[0] in (Scene.UNKNOWN, Scene.CONNECTING):
            events.append("settle")
            current[0] = Scene.TRAIN_MAIN

    def read_slots(room):
        assert room == "train" and current[0] == Scene.TRAIN_MAIN
        assert solver.choose_train.call_count == solver.ctap.call_count == 0
        events.append("read")
        current[0] = Scene.INFRA_DETAILS if readable else Scene.TRAIN_MAIN
        return [{"agent": support_name}, {"agent": "能天使"}]

    def select_skill(*args):
        assert current[0] == Scene.TRAIN_SKILL_SELECT
        events.append("select")
        current[0] = Scene.TRAIN_SKILL_UPGRADE

    solver.tap.side_effect = tap
    solver.back.side_effect = back
    solver.sleep.side_effect = sleep
    solver.get_agent_from_room.side_effect = read_slots
    solver.ctap.side_effect = select_skill
    solver.find.side_effect = lambda name: (
        "close" if name == "arrange_check_in_on" else "confirm"
    )
    return solver, events


@pytest.mark.parametrize(
    "transient", [Scene.TRAIN_MAIN, Scene.UNKNOWN, Scene.CONNECTING]
)
@pytest.mark.parametrize("readable", [True, False])
@pytest.mark.parametrize("scheduled_occupant", [False, True])
def test_start_waits_for_main_before_real_preparation(
    database, context_game, transient, readable, scheduled_occupant
):
    _, ids = context_game
    stage = support.stage_route(stat("艾丽妮", 30, True), None, StageSpec(1, 8))
    pid = db.insert_plan(
        ids["能天使"], 0, 3, char_name="能天使", support_plan={"stages": [stage]}
    )
    plan = db.get_plan_by_id(pid)
    solver, events = scene_solver(
        transient, readable, "赫默" if scheduled_occupant else "艾丽妮"
    )
    with (
        patch(
            "arknights_mower.solvers.mastery_support_runtime.schedule_context",
            return_value=({"赫默": {"room_3_2"}} if scheduled_occupant else {}, 0),
        ),
        patch.object(mastery, "_read_train_countdown3", return_value=("failed", None)),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slot_mastery_tier",
            return_value=0,
        ) as tier,
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=False),
        ),
        patch.object(
            mastery, "_confirm_training_started", return_value="started"
        ) as confirm,
        patch.object(mastery, "_exit_failed") as fail,
    ):
        mastery._start_new_training(
            solver, plan, room=SimpleNamespace(train_slot="能天使")
        )
    assert events[0] == "back"
    if transient != Scene.TRAIN_MAIN:
        assert events[1] == "settle"
    assert "read" in events
    solver.choose_train.assert_not_called()
    if readable:
        assert events[-3:] == ["close", "select", "confirm"]
        assert tier.call_count == 2
        confirm.assert_called_once()
        fail.assert_not_called()
        saved = support.decode_json(db.get_plan_by_id(pid)["support_runtime"])
        assert saved["operator"] == "艾丽妮" and saved["level"] == 1
    else:
        solver.ctap.assert_not_called()
        confirm.assert_not_called()
        fail.assert_called_once()
        assert "无法确认当前训练室协助者" in fail.call_args.args[2]
        assert db.get_plan_by_id(pid)["support_runtime"] is None
