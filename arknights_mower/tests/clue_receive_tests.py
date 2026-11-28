from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import pytest

from arknights_mower.tests.clue_gift_tests import clue_workflow as clue_workflow
from arknights_mower.tests.clue_gift_tests import frame
from arknights_mower.tests.clue_gift_tests import gift_ui as gift_ui
from arknights_mower.utils import rapidocr
from arknights_mower.utils.image import loadimg, loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def receive_workflow(clue_workflow, monkeypatch):
    solver, state = clue_workflow
    # 原图缺 5 号；仅在离线输入中补齐卡片，构造完整线索板。
    receive = frame("clue_receive_credit_capped.jpg")
    card = loadres("clue/5")
    receive[660 : 660 + card.shape[0], 495 : 495 + card.shape[1]] = card
    state.snapshots[Scene.CLUE_RECEIVE] = receive
    state.received = 0
    state.pending = 2
    state.credit_capped = True
    state.cap_after = None
    state.cap_score = 0.99
    state.sender_rows = [[[], "测试好友", 0.99]]
    state.receive_opened = False
    state.receive_exits = 0
    state.exit_delayed = False

    previous_find = solver.find

    def find(resource, **kwargs):
        if resource == "clue/badge_new" and kwargs["scope"] == (
            (1815, 360),
            (1895, 410),
        ):
            return (1850, 385) if not state.receive_opened else None
        return previous_find(resource, **kwargs)

    solver.find = find
    previous_scene = solver.scene

    def scene():
        current = previous_scene()
        solver.recog.gray = cv2.cvtColor(solver.recog.img, cv2.COLOR_RGB2GRAY)
        solver.recog.scene = current
        solver.recog._img = solver.recog.img
        return current

    solver.scene = scene
    previous_tap = solver.tap.side_effect

    def tap(point, **kwargs):
        if point == (1800, 430):
            state.receive_opened = True
            state.scene = Scene.CLUE_RECEIVE
        elif point == ((1580, 220), (1880, 255)):
            state.received += 1
            if state.cap_after == state.received:
                state.credit_capped = True
            if state.received == state.pending:
                receive[100:400, 1275:1920] = 0
        elif point == (1239, 144):
            state.receive_exits += 1
            if state.exit_delayed and state.receive_exits == 1:
                state.credit_capped = False
            else:
                state.scene = Scene.INFRA_CONFIDENTIAL
        else:
            previous_tap(point, **kwargs)

    solver.tap = MagicMock(side_effect=tap)
    solver.ctap = solver.tap
    solver._give_one_placed_clue = MagicMock(return_value=False)
    solver._read_clue_gift_capacity = MagicMock(return_value=(0, 10))

    def ocr(image, **kwargs):
        if image.shape[:2] == (75, 645):
            message = (
                "今日接受信用已达上限" if state.credit_capped else "接受线索可获得信用"
            )
            return [[[], message, state.cap_score]], None
        return state.sender_rows, None

    monkeypatch.setattr(rapidocr, "engine", MagicMock(side_effect=ocr))
    return solver, state


@pytest.mark.parametrize("leifeng", [False, True])
@pytest.mark.parametrize(
    "capped,cap_after,expected",
    [(True, None, 0), (False, None, 2), (False, 1, 1)],
)
def test_full_board_stops_receiving_only_after_daily_credit_cap(
    receive_workflow, caplog, leifeng, capped, cap_after, expected
):
    solver, state = receive_workflow
    solver.leifeng_mode = leifeng
    state.credit_capped = capped
    state.cap_after = cap_after

    solver.clue_new()

    assert state.received == expected
    assert state.receive_exits == 1
    solver._give_one_placed_clue.assert_called_once()
    solver._run_clue_shop.assert_called_once()
    assert (
        "线索板已填满，今日接受信用已达上限，暂不领取剩余好友线索" in caplog.text
    ) is (expected < 2)


def test_delayed_close_does_not_resume_receiving_after_credit_cap(receive_workflow):
    solver, state = receive_workflow
    state.exit_delayed = True

    solver.clue_new()

    assert state.received == 0
    assert state.receive_exits == 2
    solver._give_one_placed_clue.assert_called_once()
    solver._run_clue_shop.assert_called_once()


@pytest.mark.parametrize(
    "rows,display_name",
    [
        (None, "好友"),
        ([], "好友"),
        ([[[], "  ", 0.9]], "好友"),
        ([[[], "  测试好友  ", 0.9]], "测试好友"),
    ],
)
def test_sender_name_only_affects_receipt_log(
    receive_workflow, caplog, rows, display_name
):
    solver, state = receive_workflow
    state.credit_capped = False
    state.sender_rows = rows
    previous_check = solver.last_clue = datetime.now() - timedelta(hours=2)

    solver._run_clue_flow()

    assert state.received == 2
    assert f"接收{display_name}的" in caplog.text
    solver._give_one_placed_clue.assert_called_once()
    solver._run_clue_shop.assert_called_once()
    assert solver.last_clue > previous_check


@pytest.mark.parametrize("kind", [TaskTypes.CLUE, TaskTypes.CLUE_PARTY, None])
def test_receipt_failure_keeps_work_until_room_observation(receive_workflow, kind):
    solver, state = receive_workflow
    state.credit_capped = False
    previous_check = solver.last_clue = datetime.now() - timedelta(hours=2)
    solver.task = None
    solver.op_data = SimpleNamespace(
        operators={}, plan={}, dorm=[], room_observations={}, run_order_rooms={}
    )
    solver.enable_party = True
    solver.planned = True
    solver.todo_task = False
    solver.collect_notification = True
    solver.drone_room = None
    solver.drone_time = None
    solver.reload_time = datetime.now()
    solver.handle_error = MagicMock()
    scheduled = SchedulerTask(previous_check, task_type=kind) if kind else None
    if scheduled:
        solver.task = scheduled
        solver.tasks.append(scheduled)
    failure = RuntimeError("领取线索失败")
    tap = solver.tap.side_effect

    def fail_receipt(point, **kwargs):
        if point == ((1580, 220), (1880, 255)):
            raise failure
        return tap(point, **kwargs)

    solver.tap.side_effect = fail_receipt
    solver.infra_main()

    (retained,) = solver.tasks
    assert retained.type == (kind or TaskTypes.CLUE)
    if scheduled:
        assert retained is scheduled
        assert retained.time == previous_check
    original_time = retained.time
    assert str(failure) in retained.execution_failure["reason"]
    assert not getattr(retained, "clue_access_record_pending", False)
    assert state.received == 0
    assert solver.last_clue == previous_check
    solver._run_clue_shop.assert_not_called()

    for other_page in (Scene.CLUE_RECEIVE, Scene.INFRA_MAIN):
        solver.recog.scene = other_page
        solver.op_data.room_observations["contact"] = 1
        solver.task = retained
        solver.todo_task = False
        solver.infra_main()
        assert solver.todo_task
        assert solver.tasks == [retained]
        assert retained.time == original_time
        assert retained.execution_failure
        assert solver.last_clue == previous_check
    solver.enter_room.assert_called_once()

    independent = SchedulerTask(datetime.now(), task_type=TaskTypes.NOT_SPECIFIC)
    solver.tasks.append(independent)
    solver.task = independent
    solver.infra_main()
    assert solver.tasks == [retained]

    if kind is None:
        solver.op_data.room_observations["meeting"] = 1
    elif kind == TaskTypes.CLUE:
        solver.recog.scene = Scene.CLUE_RECEIVE
        card = loadres("clue/5")
        frame = state.snapshots[Scene.CLUE_RECEIVE]
        frame[122 : 122 + card.shape[0], 1305 : 1305 + card.shape[1]] = card
    else:
        solver.recog.scene = Scene.INFRA_CONFIDENTIAL
    solver.tap.side_effect = tap
    state.receive_opened = False
    state.scene = Scene.INFRA_DETAILS
    solver.task = retained
    solver.infra_main()

    assert solver.tasks == []
    assert state.received == 2
    assert solver.last_clue > previous_check
    solver._run_clue_shop.assert_called_once()


@pytest.mark.parametrize("missing", [True, False], ids=["missing", "corrupt"])
def test_unreadable_card_template_keeps_original_failure(
    receive_workflow, tmp_path, monkeypatch, missing
):
    from arknights_mower.solvers import base_schedule, clue_gift

    solver, state = receive_workflow
    previous_check = solver.last_clue = datetime.now() - timedelta(hours=2)
    task = SchedulerTask(previous_check, task_type=TaskTypes.CLUE)
    solver.task, solver.tasks = task, [task]
    template = tmp_path / "clue.png"
    if not missing:
        template.write_bytes(b"invalid image")

    with monkeypatch.context() as broken:
        broken.setattr(clue_gift, "loadres", lambda _: loadimg(str(template)))
        solver.infra_main()
        (original_error,) = base_schedule.save_exception.call_args.args
        assert isinstance(original_error, FileNotFoundError if missing else cv2.error)
        assert str(original_error) in task.execution_failure["reason"]
        assert task.execution_failure["snapshot"]["card"] is None
        solver._resume_failed_tasks()
        assert task.execution_failure
        assert solver.tasks == [task]
        assert task.time == solver.last_clue == previous_check
        assert state.received == 0
        solver._run_clue_shop.assert_not_called()

    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)


@pytest.mark.parametrize("next_card", [3, 5])
def test_transition_observes_pending_receipt_before_navigation(
    receive_workflow, next_card
):
    solver, state = receive_workflow
    device = MagicMock()
    device.check_current_focus.return_value = False
    solver.recog = Recognizer(device)
    solver.scene = solver.recog.get_scene
    current = state.snapshots[Scene.CLUE_RECEIVE]
    solver.recog.set_frame((None, current, cv2.cvtColor(current, cv2.COLOR_RGB2GRAY)))
    assert solver.scene() == Scene.CLUE_RECEIVE
    task = SchedulerTask(datetime.now(), task_type=TaskTypes.CLUE)
    solver.tasks = [task]
    solver._retain_clue_receipt_failure(task, RuntimeError("领取线索失败"))
    assert task.execution_failure["snapshot"]["card"] == 3

    solver.recog.update()
    solver._resume_failed_tasks()
    assert task.execution_failure
    device.screencap.assert_not_called()
    updated = current.copy()
    if next_card != 3:
        template = loadres("clue/5")
        updated[122 : 122 + template.shape[0], 1305 : 1305 + template.shape[1]] = (
            template
        )
    device.screencap.return_value = (
        None,
        updated,
        cv2.cvtColor(updated, cv2.COLOR_RGB2GRAY),
    )
    solver.scene_graph_navigation.side_effect = lambda _: solver.recog.update()

    solver.transition()

    solver.scene_graph_navigation.assert_called_once_with(Scene.INFRA_MAIN)
    assert solver.recog.scene == Scene.UNDEFINED
    device.screencap.assert_called_once_with()
    assert bool(getattr(task, "execution_failure", None)) is (next_card == 3)
    assert solver.tasks == [task]


@pytest.mark.parametrize(
    "x,y",
    [
        (72, 228),
        (374, 334),
        (679, 198),
        (1003, 265),
        (495, 660),
        (805, 573),
        (154, 608),
    ],
)
def test_missing_any_board_card_keeps_receiving_at_credit_cap(receive_workflow, x, y):
    solver, state = receive_workflow
    state.snapshots[Scene.CLUE_RECEIVE][y - 16 : y + 232, x - 16 : x + 178] = 0

    solver.clue_new()

    assert state.received == 2
    assert state.receive_exits == 1
    solver._give_one_placed_clue.assert_called_once()


def test_low_confidence_cap_text_does_not_stop_receiving(receive_workflow):
    solver, state = receive_workflow
    state.cap_score = 0.5

    solver.clue_new()

    assert state.received == 2


def test_real_incomplete_board_keeps_receiving_at_credit_cap(receive_workflow):
    solver, state = receive_workflow
    state.snapshots[Scene.CLUE_RECEIVE][:] = frame("clue_receive_credit_capped.jpg")

    solver.clue_new()

    assert state.received == 2
    solver._run_clue_shop.assert_called_once()


def test_page_change_while_waiting_never_receives_on_another_page(receive_workflow):
    solver, state = receive_workflow

    def wait(*, log_group=None):
        assert log_group == "clue"
        if state.scene == Scene.CLUE_RECEIVE:
            state.scene = Scene.INFRA_CONFIDENTIAL

    solver.wait_product_complete.side_effect = wait

    solver.clue_new()

    assert state.received == 0
    assert state.receive_exits == 0
    solver._run_clue_shop.assert_called_once()


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("clue_receive_credit_capped.jpg", True),
        ("clue_live_receive_after.png", True),
        ("clue_live_credit_prompt.png", False),
    ],
)
def test_real_receive_credit_caption(receive_workflow, monkeypatch, filename, expected):
    solver, state = receive_workflow
    state.scene = Scene.CLUE_RECEIVE
    state.snapshots[Scene.CLUE_RECEIVE] = frame(filename)
    monkeypatch.setattr(rapidocr, "engine", rapidocr.create_engine())

    assert solver._clue_receive_credit_capped() is expected


@pytest.mark.parametrize(
    "result,expected",
    [
        (None, False),
        ([], False),
        ([[[], "信用已达上限", 0.99]], False),
        ([[[], "今日接受信用未达上限", 0.99]], False),
        ([[[], " 今日接受信用 已达上限 ", 0.99]], True),
    ],
)
def test_credit_cap_requires_complete_confirmed_caption(
    receive_workflow, result, expected
):
    solver, state = receive_workflow
    state.scene = Scene.CLUE_RECEIVE
    rapidocr.engine.return_value = (result, None)
    rapidocr.engine.side_effect = None

    assert solver._clue_receive_credit_capped() is expected


def test_credit_cap_is_not_read_on_other_pages(receive_workflow):
    solver, _ = receive_workflow

    assert solver._clue_receive_credit_capped() is False
    rapidocr.engine.assert_not_called()
