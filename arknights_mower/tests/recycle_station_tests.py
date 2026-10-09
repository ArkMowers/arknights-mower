"""回收站预览素材及离线选人流程。"""

import sys
from copy import deepcopy
from itertools import permutations
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_mixin import (  # noqa: E402
    AgentSelectionPageChanged,
    BaseMixin,
    agent_card_selected,
)
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import segment  # noqa: E402
from arknights_mower.utils.character_recognize import operator_list  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.config.plan import Plan1, PlanModel, Task  # noqa: E402
from arknights_mower.utils.config.plan_advanced import (  # noqa: E402
    export_advanced_settings,
)
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "recycle"


def preview(name):
    img = cv2.resize(
        cv2.imread(str(FIXTURES / f"{name}.png")),
        (1920, 1080),
        interpolation=cv2.INTER_AREA,
    )
    return Recognizer(MagicMock(), cv2.imencode(".png", img)[1].tobytes())


@pytest.mark.parametrize("page", ["room", "dashboard", "room_small", "dashboard_small"])
def test_official_preview_room_identity(page):
    solver = BaseMixin()
    solver.recog = preview(page)
    assert solver.detect_room() == "recycle"
    assert bool(solver.recog.find("recycle/dashboard")) == page.startswith("dashboard")
    assert solver.recog.get_scene() == Scene.INFRA_DETAILS


def test_dashboard_cannot_be_read_as_operator_cards():
    solver = BaseMixin()
    solver.recog = preview("dashboard")
    solver.find = solver.recog.find
    with pytest.raises(AgentSelectionPageChanged):
        solver.require_agent_selection_page()


@pytest.mark.parametrize(
    "page,selected",
    [("selection_empty", []), ("selection_two", ["艾雅法拉", "安洁莉娜"])],
)
def test_official_animation_uses_shared_two_person_selection(page, selected):
    recog = preview(page)
    assert recog.find("confirm_blue") is not None
    assert recog.find("recycle/dashboard") is None
    cards = operator_list(recog.img)
    assert len(cards) == 10
    assert [
        name for name, scope in cards if agent_card_selected(recog.img, scope)
    ] == selected


def test_official_animation_returns_to_occupied_dashboard():
    recog = preview("dashboard_two")
    assert recog.find("recycle/dashboard") is not None
    assert recog.find("confirm_blue") is None


def test_confirm_accepts_official_recycle_dashboard_return():
    frames = [preview("selection_two"), preview("dashboard_two")]
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask()
    solver.op_data = SimpleNamespace(run_order_rooms={})
    solver.recog = SimpleNamespace(w=1920, h=1080, update=MagicMock())
    state = {"frame": 0}
    solver.find = lambda name, **kwargs: frames[state["frame"]].find(name, **kwargs)
    solver.tap = MagicMock(side_effect=lambda *args, **kwargs: state.update(frame=1))
    solver.sleep = MagicMock()

    solver.tap_confirm("recycle", {})

    solver.tap.assert_called_once()
    solver.sleep.assert_not_called()


def test_recycle_map_matches_preview_and_is_independent_of_room_swap():
    # 第三张预览中加工站约 (254, 245)-(437, 326)，反推现有中枢锚点。
    frame = preview("map").img
    alpha = 183 / 297 * 1920 / 1192
    x1 = 254 * 1920 / 1192 - 643 * alpha
    y1 = 245 * 1080 / 671 - 252 * alpha
    anchor = ((x1, y1), (x1 + 262 * alpha, y1 + 160 * alpha))
    for order in permutations(("contact", "train", "recycle")):
        rooms = segment.base(frame, anchor, right_side_room_order=order)
        x, y = np.mean(rooms[order[2]], axis=0)
        assert 254 < x * 1192 / 1920 < 437
        assert 540 < y * 671 / 1080 < 624
        assert preview("map").find("recycle/dashboard") is None


def test_plan_and_backup_tasks_roundtrip_and_legacy_omission():
    facility = {"plans": [{"agent": "芬"}, {"agent": "香草"}]}
    plan = PlanModel(
        plan1={"recycle": facility},
        backup_plans=[
            {
                "plan": {"recycle": facility},
                "task": {"recycle": ["Current", "芬"]},
            }
        ],
    )
    restored = PlanModel.model_validate_json(plan.model_dump_json())
    assert restored.plan1.recycle.plans[1].agent == "香草"
    assert restored.backup_plans[0].plan.recycle.plans[0].agent == "芬"
    assert restored.backup_plans[0].task.recycle == ["Current", "芬"]
    assert PlanModel(plan1={}).plan1.recycle is None
    assert "recycle" not in Plan1().model_dump(exclude_none=True)


@pytest.mark.parametrize("model", [Plan1, Task])
def test_third_recycle_slot_is_rejected(model):
    slots = ["芬", "香草", "Current"]
    value = {"plans": [{"agent": n} for n in slots]} if model is Plan1 else slots
    with pytest.raises(ValidationError):
        model(recycle=value)


@pytest.mark.parametrize("staff", [None, [], ["芬"], ["芬", "香草"]])
def test_cache_and_reader_use_two_physical_slots(staff):
    plan = (
        {} if staff is None else {"recycle": [SimpleNamespace(agent=n) for n in staff]}
    )
    data = object.__new__(Operators)
    data.plan = deepcopy(plan)
    data.operators = {
        "香草": SimpleNamespace(name="香草", current_room="recycle", current_index=1)
    }
    assert data.get_current_room("recycle", True) == ["", "香草"]
    assert data.plan == plan
    solver = MagicMock()
    solver.task = None
    solver.op_data.plan = deepcopy(plan)
    solver.find.return_value = True
    result = BaseSchedulerSolver.get_agent_from_room(solver, "recycle")
    assert [slot["agent"] for slot in result] == ["", ""]
    solver.scroll_room_operators.assert_not_called()
    assert solver.op_data.plan == plan


@pytest.mark.parametrize("staff", [None, [], ["芬"], ["芬", "香草"]])
@pytest.mark.parametrize("initial", ["room", "detail", "dashboard"])
def test_arrangement_uses_residence_list_and_reads_actual_mood(staff, initial):
    solver = MagicMock()
    solver.task = SchedulerTask()
    solver.tasks = []
    solver.waiting_scene = []
    solver.scene.return_value = Scene.INFRA_DETAILS
    solver.ensure_dorm_recovery_order.return_value = False
    solver._can_refresh_idle_dorm_search.return_value = False
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.op_data.plan = (
        {} if staff is None else {"recycle": [SimpleNamespace(agent=n) for n in staff]}
    )
    original_plan = deepcopy(solver.op_data.plan)
    solver.op_data.run_order_rooms = {}
    solver.op_data.operators = {}
    for name in ("芬", "香草"):
        op = MagicMock()
        op.name, op.current_room, op.current_index = name, "", -1
        op.need_to_refresh.return_value = True
        op.depletion_rate = 1
        solver.op_data.operators[name] = op
    solver.op_data.get_current_room.side_effect = MethodType(
        Operators.get_current_room, solver.op_data
    )
    solver.get_agent_from_room.side_effect = MethodType(
        BaseSchedulerSolver.get_agent_from_room, solver
    )
    solver.recog.w, solver.recog.h = 1920, 1080
    solver.get_color.return_value = np.array([255, 255, 255])
    state = [initial]
    detail_button = ((30, 350), (150, 450))

    def find(name, **kwargs):
        return {
            "room": {"arrange_check_in": detail_button},
            "detail": {"room_detail": True},
            "dashboard": {"recycle/dashboard": True},
            "selection": {"confirm_blue": True},
        }[state[0]].get(name)

    def tap(point, **kwargs):
        expected, following = {
            "room": (detail_button, "detail"),
            "detail": ((1920 * 0.82, 1080 * 0.2), "selection"),
        }[state[0]]
        assert point == expected
        state[0] = following

    solver.find.side_effect = find
    solver.tap.side_effect = tap
    solver.back.side_effect = lambda *args: state.__setitem__(0, "room")
    solver.turn_on_room_detail.side_effect = MethodType(
        BaseSchedulerSolver.turn_on_room_detail, solver
    )
    solver.tap_confirm.side_effect = lambda *args: state.__setitem__(0, "room")
    names = iter(("芬", "香草"))

    def read_name(*args, **kwargs):
        assert state[0] == "detail"
        return next(names)

    solver.read_screen.side_effect = read_name
    solver.read_accurate_mood.return_value = 20

    def update(name, mood, room, index, update_time):
        op = solver.op_data.operators[name]
        op.current_room, op.current_index = room, index

    solver.op_data.update_detail.side_effect = update
    plan = {"recycle": ["芬", "香草"]}
    assert BaseSchedulerSolver.agent_arrange_room(solver, {}, "recycle", plan) == {}
    assert state[0] == "room"
    assert solver.turn_on_room_detail.call_count == 2
    assert solver.op_data.plan == original_plan
    assert solver.read_accurate_mood.call_count == 2
    assert [call.args[1] for call in solver.op_data.update_detail.call_args_list] == [
        20,
        20,
    ]
    solver.choose_agent.assert_called_once()
    assert solver.choose_agent.call_args.args == (["芬", "香草"], "recycle")
    solver.tap_confirm.assert_called_once_with("recycle", {})
    assert solver.op_data.get_current_room("recycle", True) == ["芬", "香草"]
    assert plan == {}


@pytest.mark.parametrize("order", list(permutations(("contact", "train", "recycle"))))
def test_all_three_room_permutations_preserve_physical_locations(order):
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    anchor = ((400, 80), (600, 240))
    default = segment.base(img, anchor)
    changed = segment.base(img, anchor, right_side_room_order=order)
    for original, room in zip(("contact", "train", "recycle"), order):
        np.testing.assert_array_equal(changed[room], default[original])
    for room in default.keys() - set(order):
        np.testing.assert_array_equal(changed[room], default[room])
    conf = Conf(right_side_room_order=order)
    assert conf.right_side_room_order == list(order)
    assert "right_side_room_order" not in export_advanced_settings(conf)


@pytest.mark.parametrize("swapped", [False, True])
def test_legacy_layout_migration_and_new_order_precedence(swapped):
    conf = Conf(swap_contact_train=swapped)
    expected = (
        ["train", "contact", "recycle"] if swapped else ["contact", "train", "recycle"]
    )
    assert conf.right_side_room_order == expected
    assert "swap_contact_train" not in conf.model_dump()
    explicit = ["recycle", "train", "contact"]
    assert (
        Conf(
            swap_contact_train=swapped, right_side_room_order=explicit
        ).right_side_room_order
        == explicit
    )


@pytest.mark.parametrize(
    "order",
    [
        ["contact", "train"],
        ["train", "train", "recycle"],
        ["contact", "train", "factory"],
    ],
)
def test_invalid_local_layout_is_rejected(order):
    with pytest.raises(ValidationError):
        Conf(right_side_room_order=order)
