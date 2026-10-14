import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from rapidocr_onnxruntime import RapidOCR

from arknights_mower.solvers.clue_gift import ClueGiftMixin, clue_card_number
from arknights_mower.utils import rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.image import bytes2img, cropimg
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

FIXTURES = Path(__file__).parent / "fixtures" / "clue"


def frame(name):
    return bytes2img((FIXTURES / name).read_bytes())


@pytest.fixture
def gift_ui(monkeypatch):
    solver = ClueGiftMixin()
    state = SimpleNamespace(
        count=10,
        limit=10,
        filtered=False,
        filter_works=True,
        filter_known=True,
        missing_rows={0},
        all_rows={0, 1, 2, 3},
        sent=[],
        selected=False,
        number=None,
        delivery=True,
        send_error=None,
        during_selection=None,
        scene=Scene.CLUE_GIVE_AWAY,
    )
    solver.leifeng_mode = False
    solver.clue_count = 10
    solver.recog = MagicMock(img=frame("clue_gift_inventory.jpg"))
    solver.scene = lambda: state.scene
    solver.sleep = MagicMock()
    solver.wait_product_complete = MagicMock()

    def color(point):
        if not state.filter_known:
            return np.array([80, 80, 80])
        white = point == ((1078, 38) if state.filtered else (1050, 38))
        return np.array([255, 255, 255] if white else [64, 64, 64])

    solver.get_color = color

    def find(resource, *, scope):
        assert resource == "clue/label_give_away"
        row = (scope[0][1] - 228) // 222
        rows = state.missing_rows if state.filtered else state.all_rows
        return scope if row in rows else None

    solver.find = find

    def tap(point):
        if point == (1064, 38):
            if state.filter_works:
                state.filtered = not state.filtered
            if state.during_selection is not None:
                state.count = state.during_selection
        elif point == ((30, 208), (192, 424)):
            state.selected = True
        elif point[1] == 130:
            state.number = (point[0] - 130) // 77 + 1
        elif point[0] == 1790:
            assert state.selected
            state.sent.append((state.number, state.filtered, (point[1] - 200) // 222))
            if state.send_error is not None:
                raise state.send_error
            if state.delivery:
                state.count -= 1

    solver.tap = MagicMock(side_effect=tap)
    monkeypatch.setattr(
        rapidocr,
        "engine",
        MagicMock(
            side_effect=lambda *a, **kw: (
                [[f"自有库{state.count}/{state.limit}", 0.99]],
                None,
            )
        ),
    )
    return solver, state


@pytest.mark.parametrize(
    "leifeng,count,limit,expected",
    [
        (False, 9, 10, False),
        (False, 10, 10, True),
        (True, 9, 10, True),
        (True, 0, 10, False),
        (False, 20, 20, True),
    ],
)
def test_gift_is_allowed_by_leifeng_or_observed_full_capacity(
    gift_ui, leifeng, count, limit, expected
):
    solver, state = gift_ui
    solver.leifeng_mode = leifeng
    state.count, state.limit = count, limit
    assert solver._give_one_placed_clue({1}) is expected
    assert len(state.sent) == int(expected)
    if expected:
        assert solver.clue_count == count - 1


def test_prefers_a_friend_missing_the_selected_number_and_restores_filter(gift_ui):
    solver, state = gift_ui
    state.missing_rows = {2}
    assert solver._give_one_placed_clue({1, 4, 6, 7})
    assert state.sent == [(1, True, 2)]
    assert state.filtered is False
    assert state.count == 9


@pytest.mark.parametrize("original_filter", [False, True])
def test_no_missing_friend_uses_first_available_friend(gift_ui, original_filter):
    solver, state = gift_ui
    state.filtered = original_filter
    state.missing_rows = set()
    state.all_rows = {1, 3}
    assert solver._give_one_placed_clue({1})
    assert state.sent == [(1, False, 1)]
    assert state.filtered is original_filter


@pytest.mark.parametrize("placed", [set(), {2, 3, 5}])
def test_never_sends_inventory_clue_without_matching_placed_number(gift_ui, placed):
    solver, state = gift_ui
    assert not solver._give_one_placed_clue(placed)
    assert state.sent == []
    assert state.selected is False


def test_no_available_friend_does_not_send(gift_ui):
    solver, state = gift_ui
    state.missing_rows = state.all_rows = set()
    assert not solver._give_one_placed_clue({1})
    assert state.sent == []
    assert state.filtered is False


def test_gift_without_observed_inventory_decrease_is_not_repeated(gift_ui):
    solver, state = gift_ui
    state.delivery = False
    assert not solver._give_one_placed_clue({1, 4, 6, 7})
    assert state.sent == [(1, True, 0)]
    assert solver.clue_count == 10


def test_inventory_changes_during_selection_cancel_the_send(gift_ui):
    solver, state = gift_ui
    state.during_selection = 9
    assert not solver._give_one_placed_clue({1})
    assert state.sent == []


@pytest.mark.parametrize("known,works", [(False, True), (True, False)])
def test_unknown_or_unchanged_filter_does_not_send(gift_ui, known, works):
    solver, state = gift_ui
    state.filter_known, state.filter_works = known, works
    assert not solver._give_one_placed_clue({1})
    assert state.sent == []
    assert sum(call.args == ((1064, 38),) for call in solver.tap.call_args_list) <= 1


def test_stop_during_send_propagates_without_additional_filter_click(gift_ui):
    solver, state = gift_ui
    state.send_error = MowerExit()
    with pytest.raises(MowerExit):
        solver._give_one_placed_clue({1})
    assert state.sent == [(1, True, 0)]
    assert state.filtered is True
    assert solver.tap.call_args.args == ((1790, 200),)


@pytest.mark.parametrize(
    "ocr",
    [
        None,
        [],
        [["自有库10/10", 0.5]],
        [["自有库110/10", 1]],
        [["自有库11/10", 1]],
        [["自有库10/0", 1]],
        [["自有库10", 1]],
        [["10/10", 1]],
        [["自有库", 1], ["10/10", 1]],
    ],
)
def test_unconfirmed_capacity_does_not_send(gift_ui, monkeypatch, ocr):
    solver, state = gift_ui
    monkeypatch.setattr(rapidocr, "engine", lambda *a, **kw: (ocr, None))
    assert not solver._give_one_placed_clue({1})
    solver.tap.assert_not_called()
    assert state.sent == []


def test_real_board_identifies_placed_cards_but_not_empty_number_slots(gift_ui):
    solver, state = gift_ui
    state.scene = Scene.INFRA_CONFIDENTIAL
    solver.recog.img = frame("clue_placed_before_gift.jpg")
    assert solver._read_placed_clue_numbers() == {1, 4, 6, 7}
    solver.wait_product_complete.assert_called_once()
    assert (
        clue_card_number(
            cropimg(frame("clue_gift_inventory.jpg"), ((30, 208), (192, 424)))
        )
        == 1
    )


@pytest.mark.parametrize(
    "filename,capacity,filtered",
    [
        ("clue_gift_inventory.jpg", (5, 10), False),
        ("clue_gift_missing_filter.png", (5, 10), True),
        ("clue_gift_sent.png", (4, 10), False),
    ],
)
def test_actual_ocr_reads_gift_inventory_and_filter(
    gift_ui, monkeypatch, filename, capacity, filtered
):
    solver, _ = gift_ui
    solver.recog.img = frame(filename)
    monkeypatch.setattr(rapidocr, "engine", RapidOCR())
    solver.get_color = lambda p: solver.recog.img[p[1], p[0]]
    assert solver._read_clue_gift_capacity() == capacity
    assert solver._clue_missing_filter() is filtered


@pytest.mark.parametrize(
    "filename", ["clue_gift_inventory.jpg", "clue_gift_missing_filter.png"]
)
def test_actual_recognizer_finds_receivable_friend_on_gift_page(gift_ui, filename):
    from arknights_mower.utils.recognize import Recognizer

    solver, _ = gift_ui
    solver.recog = Recognizer(MagicMock(), (FIXTURES / filename).read_bytes())
    solver.find = solver.recog.find
    assert solver._first_clue_recipient() == (1790, 200)


def test_disabled_recipient_button_is_skipped(gift_ui):
    solver, state = gift_ui
    state.missing_rows = {0, 1}
    solver.recog.img[110:284, 1768:1835] = 100
    assert solver._give_one_placed_clue({1})
    assert state.sent == [(1, True, 1)]


@pytest.fixture
def clue_workflow(gift_ui, monkeypatch):
    # 保留真正的线索任务列表和补送流程，仅替换画面、点击及外部操作。
    with monkeypatch.context() as imports:
        imports.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
        from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    monkeypatch.setattr(
        "arknights_mower.solvers.base_schedule.save_exception", MagicMock()
    )
    ui, state = gift_ui
    solver = object.__new__(BaseSchedulerSolver)
    solver.__dict__.update(ui.__dict__)
    solver.clue_count = 0  # 模拟之前没有读到最新数量，赠送页须重新读取。
    solver.clue_count_limit = 9
    solver._clue_credit_enabled = MagicMock(return_value=False)
    solver._clue_flow_resume_time = MagicMock(return_value=None)
    solver._prepare_clue_room = MagicMock()
    solver._collect_clue_message_board = MagicMock(return_value=True)
    solver.op_data = None
    solver.tasks = []
    solver.skip = MagicMock()
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.scene_graph_navigation = MagicMock()
    solver.enter_room = MagicMock()
    solver.read_party_time = MagicMock(return_value=None)
    solver.set_detected_party_time = MagicMock()
    solver.backup_plan_solver = MagicMock()
    solver._run_clue_shop = MagicMock()
    state.after_fast = 10
    state.fast_taps = []
    state.scene = Scene.INFRA_DETAILS
    snapshots = {
        Scene.INFRA_DETAILS: frame("clue_placed_before_gift.jpg"),
        Scene.INFRA_CONFIDENTIAL: frame("clue_placed_before_gift.jpg"),
        Scene.CLUE_GIVE_AWAY: frame("clue_gift_inventory.jpg"),
    }
    frames = 0

    def scene():
        nonlocal frames
        frames += 1
        assert frames <= 80, "线索流程未能推进"
        solver.recog.img = snapshots[state.scene]
        return state.scene

    solver.scene = scene
    recipient_find = solver.find

    def find(resource, **kwargs):
        if resource == "control_central":
            return (960, 540)
        if resource == "clue/label_give_away":
            return recipient_find(resource, **kwargs)
        if resource == "clue/fast_giveaway":
            return (300, 1030)
        return None

    solver.find = find
    device_tap = ui.tap.side_effect

    def tap(point, **kwargs):
        if point == (330, 1000):
            state.scene = Scene.INFRA_CONFIDENTIAL
        elif point == (1799, 578):
            state.scene = Scene.CLUE_GIVE_AWAY
        elif point == (1868, 54):
            state.scene = Scene.INFRA_CONFIDENTIAL
        elif point == (300, 1030):
            state.fast_taps.append(point)
            assert state.sent == []
            state.count = state.after_fast
        else:
            device_tap(point)

    solver.tap = MagicMock(side_effect=tap)
    solver.ctap = solver.tap
    solver.back = lambda: setattr(state, "scene", Scene.INFRA_DETAILS)

    return solver, state


@pytest.mark.parametrize(
    "leifeng,after_fast,expected_extra",
    [(False, 10, 1), (False, 9, 0), (True, 9, 1)],
)
def test_real_clue_workflow_runs_extra_gift_after_fast_gift(
    clue_workflow, leifeng, after_fast, expected_extra
):
    solver, state = clue_workflow
    solver.leifeng_mode = leifeng
    state.after_fast = after_fast

    solver.clue_new()

    assert state.fast_taps == [(300, 1030)]
    assert len(state.sent) == expected_extra
    assert state.count == after_fast - expected_extra
    assert solver.clue_count == state.count
    solver.read_party_time.assert_called_once()
    solver._run_clue_shop.assert_called_once()


@pytest.mark.parametrize("credit_enabled", [False, True])
@pytest.mark.parametrize("error_type", [MowerExit, DeviceRecoveryError, SharedADBError])
def test_gift_failure_does_not_complete_clue_flow(
    clue_workflow, credit_enabled, error_type
):
    solver, state = clue_workflow
    solver._clue_credit_enabled.return_value = credit_enabled
    previous_check = solver.last_clue = datetime(2026, 10, 13, 12)
    state.send_error = error_type("赠送故障")

    with pytest.raises(error_type) as raised:
        solver._run_clue_flow()

    assert raised.value is state.send_error
    assert state.sent == [(1, True, 0)]
    assert solver.last_clue == previous_check
    assert state.filtered is True
    assert solver.tap.call_args.args == ((1790, 200),)
    solver.read_party_time.assert_not_called()
    solver._run_clue_shop.assert_not_called()
    solver.skip.assert_not_called()


@pytest.mark.parametrize("credit_enabled", [False, True])
@pytest.mark.parametrize("error_type", [MowerExit, DeviceRecoveryError])
@pytest.mark.parametrize("task_type", [TaskTypes.CLUE, TaskTypes.CLUE_PARTY])
def test_gift_failure_preserves_dispatched_clue_task(
    clue_workflow, credit_enabled, error_type, task_type
):
    solver, state = clue_workflow
    solver._clue_credit_enabled.return_value = credit_enabled
    previous_check = solver.last_clue = datetime(2026, 10, 13, 12)
    task = SchedulerTask(
        time=datetime.now() - timedelta(minutes=20), task_type=task_type
    )
    original_due = task.time
    solver.task = task
    solver.tasks = [task]
    state.send_error = error_type("赠送故障")

    with pytest.raises(error_type) as raised:
        solver.infra_main()

    assert raised.value is state.send_error
    assert state.sent == [(1, True, 0)]
    assert solver.tasks == [task]
    assert solver.task is task
    assert task.time == original_due
    assert solver.last_clue == previous_check
    solver.skip.assert_not_called()
