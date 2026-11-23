from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from arknights_mower.utils import rapidocr, selection_branch
from arknights_mower.utils.image import bytes2img, img2bytes
from arknights_mower.utils.performance import PERFORMANCE_PRESETS

FIXTURES = Path(__file__).parent / "fixtures" / "selection"


def frame(name):
    # 2026-11-23 国服标准分辨率，保留右侧菜单、展开箭头及选中标记。
    if isinstance(name, np.ndarray):
        return name
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    with Image.open(FIXTURES / f"branch_{name}.webp") as strip:
        image[:, 1570:] = np.asarray(strip.convert("RGB"))
    return image


@pytest.fixture(scope="module")
def engine():
    return rapidocr.create_engine(0.8, threads=2)


class MenuReplay:
    performance_profile = SimpleNamespace(transition_timeout=0.4)

    def __init__(self, first, responses):
        self.recog = SimpleNamespace(img=frame(first))
        self.responses = iter(responses)
        self.pending = []
        self.actions = []
        self.reads = 0

    def selection_transition_timing(self):
        return 0.1, 5

    def require_agent_selection_page(self):
        self.reads += 1

    def tap(self, location, interval):
        self.actions.append(("tap", location))
        self.pending = list(next(self.responses))

    def swipe(self, start, movement, duration, interval):
        self.actions.append(("swipe", start, movement, duration))
        self.pending = list(next(self.responses))

    def sleep(self, interval):
        if self.pending:
            self.recog.img = frame(self.pending.pop(0))


def test_selects_exact_branch_and_waits_for_delayed_open_choice_and_close(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay(
        "tank_all_closed",
        [
            ["tank_all_closed", "tank_all_open"],
            ["tank_all_open", "tank_guardian_open"],
            ["tank_guardian_open", "tank_guardian_closed"],
        ],
    )
    assert selection_branch.select_visible_branch(solver, "TANK", "守护者")
    assert solver.actions[0] == solver.actions[2] == ("tap", (1813, 446))
    assert solver.actions[1][0] == "tap" and abs(solver.actions[1][1][1] - 269) <= 2
    assert len(solver.actions) == 3


def test_unknown_or_obscured_label_never_taps_a_branch(engine, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay("tank_all_open", [[], ["tank_all_closed"]])
    solver.recog.img[242:296, 1655:1792] = 0
    assert not selection_branch.select_visible_branch(solver, "TANK", "守护者")
    assert solver.actions == [
        ("swipe", (1630, 255), (0, 699), 139),
        ("tap", (1813, 446)),
    ]


def test_unacknowledged_selection_closes_menu_without_repeating_tap(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay("tank_all_open", [[], ["tank_all_closed"]])
    assert not selection_branch.select_visible_branch(solver, "TANK", "守护者")
    assert len(solver.actions) == 2
    assert solver.actions[-1] == ("tap", (1813, 446))


def test_scroll_to_hidden_liberator_reads_changed_rows_and_verifies_blue_label(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay(
        "warrior_top",
        [
            ["warrior_top", "warrior_bottom", "warrior_bottom"],
            ["warrior_liberator"],
        ],
    )
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert solver.actions[0] == ("swipe", (1630, 954), (0, -699), 139)
    assert len(solver.actions) == 2
    assert abs(solver.actions[1][1][1] - 609) <= 2


def test_stalled_menu_scroll_never_taps_an_unseen_label(engine, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay("warrior_top", [[], []])
    assert not selection_branch._select_menu_row(solver, "WARRIOR", "本源近卫")
    assert solver.actions == [
        ("swipe", (1630, 954), (0, -699), 139),
        ("swipe", (1630, 255), (0, 699), 139),
    ]
    assert solver.reads == 10


class SlowMenuReplay(MenuReplay):
    def __init__(self, responses, *, capture=0.5, poll=0.1, timeout=2.5):
        super().__init__("warrior_bottom", responses)
        self.performance_profile = replace(
            PERFORMANCE_PRESETS["low"], poll_interval=poll, transition_timeout=timeout
        )
        self.elapsed = 0
        self.capture = capture

    def selection_transition_timing(self):
        return (
            self.performance_profile.poll_interval,
            self.performance_profile.transition_attempts,
        )

    def require_agent_selection_page(self):
        self.elapsed += self.capture
        super().require_agent_selection_page()

    def sleep(self, interval):
        self.elapsed += interval
        super().sleep(interval)


def test_dropped_branch_swipe_on_500ms_capture_releases_search_at_deadline(monkeypatch):
    solver = SlowMenuReplay([[], ["warrior_top", "warrior_top"]])
    monkeypatch.setattr(selection_branch, "monotonic", lambda: solver.elapsed)
    assert not selection_branch._scroll_menu(solver, "WARRIOR", False)
    assert solver.elapsed == pytest.approx(2.5)
    assert solver.reads == 5
    assert [action[0] for action in solver.actions] == ["swipe"]

    assert selection_branch._scroll_menu(solver, "WARRIOR", False)
    assert solver.reads == 8
    assert [action[0] for action in solver.actions] == ["swipe", "swipe"]


def test_slow_branch_scroll_allows_old_frame_then_two_settled_samples(monkeypatch):
    solver = SlowMenuReplay(
        [["warrior_top", "warrior_top"]], capture=1.1, poll=1.0, timeout=1.0
    )
    monkeypatch.setattr(selection_branch, "monotonic", lambda: solver.elapsed)
    assert selection_branch._scroll_menu(solver, "WARRIOR", False)
    assert solver.reads == 3 and solver.elapsed == pytest.approx(3.3)


def test_slow_profile_keeps_its_longer_budget_for_delayed_motion(monkeypatch):
    solver = SlowMenuReplay(
        [["warrior_bottom"] * 5 + ["warrior_top"] * 2], poll=0.75, timeout=6.0
    )
    monkeypatch.setattr(selection_branch, "monotonic", lambda: solver.elapsed)
    assert selection_branch._scroll_menu(solver, "WARRIOR", False)
    assert solver.reads == 8 and solver.elapsed == pytest.approx(5.75)


def test_interrupted_motion_at_deadline_never_taps_visible_branch(monkeypatch):
    solver = SlowMenuReplay(
        [["warrior_bottom", "warrior_top", "tank_all_closed", "warrior_top"]]
    )
    monkeypatch.setattr(selection_branch, "monotonic", lambda: solver.elapsed)
    monkeypatch.setattr(selection_branch, "_visible_rows", lambda img: {"武者": 294})
    assert not selection_branch._select_menu_row(solver, "WARRIOR", "强攻手")
    assert solver.elapsed == pytest.approx(2.5)
    assert [action[0] for action in solver.actions] == ["swipe"]


def test_branch_scroll_wait_preserves_stop_after_first_slow_capture(monkeypatch):
    solver = SlowMenuReplay([[]])
    monkeypatch.setattr(selection_branch, "monotonic", lambda: solver.elapsed)
    monkeypatch.setattr(
        selection_branch.config.stop_mower, "is_set", lambda: solver.reads > 0
    )
    with pytest.raises(selection_branch.MowerExit):
        selection_branch._scroll_menu(solver, "WARRIOR", False)
    assert solver.reads == 1 and len(solver.actions) == 1


def test_target_appears_only_on_last_moving_frame(engine, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay(
        "warrior_top",
        [["warrior_top", "warrior_top", "warrior_top", "warrior_bottom"]],
    )
    assert not selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert solver.actions == [("swipe", (1630, 954), (0, -699), 139)]


def test_scroll_up_from_bottom_with_one_unreadable_row(engine, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", engine)
    bottom = frame("warrior_bottom")
    bottom[580:643, 1655:1792] = 0
    solver = MenuReplay(bottom, [["warrior_top", "warrior_top"]])
    y = selection_branch._find_branch_row(solver, "WARRIOR", "强攻手")
    assert y is not None and abs(y - 164) <= 2
    assert solver.actions == [("swipe", (1630, 255), (0, 699), 139)]


def test_middle_start_reverses_after_bottom_and_passes_original_rows(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    # 用实图下半页及上半页的下箭头构造中段，只有回到最上方后才出现强攻手。
    middle = frame("warrior_bottom").copy()
    upper = frame("warrior_top")
    middle[1027:1057, 1670:1700] = upper[1027:1057, 1670:1700]
    middle[441:752, 1655:1792] = upper[441:752, 1655:1792]
    solver = MenuReplay(
        middle,
        [
            ["warrior_bottom", "warrior_bottom"],
            [middle, middle],
            [upper, upper],
        ],
    )
    y = selection_branch._find_branch_row(solver, "WARRIOR", "强攻手")
    assert y is not None and abs(y - 164) <= 2
    assert [action[2][1] for action in solver.actions] == [-699, 699, 699]


def test_down_arrow_observed_after_upward_search_reopens_lower_rows(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    bottom = frame("warrior_bottom")
    bottom[580:643, 1655:1792] = 0
    solver = MenuReplay(
        bottom,
        [["warrior_top", "warrior_top"], [], ["warrior_bottom", "warrior_bottom"]],
    )
    y = selection_branch._find_branch_row(solver, "WARRIOR", "解放者")
    assert y is not None and abs(y - 609) <= 2
    assert [action[2][1] for action in solver.actions] == [699, 699, -699]


def test_highlighted_branch_can_move_after_a_single_tap(engine, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", engine)
    selected = frame("warrior_liberator")
    # 将实图中整个“解放者”选中行移至另一位置，保留点击前的原始菜单。
    shifted = selected.copy()
    shifted[394:814, 1570:1792] = np.roll(selected[394:814, 1570:1792], 105, axis=0)
    solver = MenuReplay("warrior_bottom", [["warrior_bottom", shifted]])
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert len(solver.actions) == 1 and abs(solver.actions[0][1][1] - 609) <= 2

    other = MenuReplay("warrior_bottom", [[shifted]])
    assert not selection_branch._select_menu_row(other, "WARRIOR", "撼地者")
    assert len(other.actions) == 1
    assert not getattr(other, "_branch_text_samples", {})


def test_training_menu_scrolls_during_opening_and_reads_dim_selected_label(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    # 训练位实图。首次展开时下箭头在 x1710，选中“解放者”后的蓝字亮度低于普通页。
    solver = MenuReplay(
        "train_warrior_opening",
        [["warrior_bottom", "warrior_bottom"], ["train_liberator"]],
    )
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert solver.actions[0] == ("swipe", (1630, 954), (0, -699), 139)
    assert len(solver.actions) == 2 and abs(solver.actions[1][1][1] - 609) <= 2
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert len(solver.actions) == 2


def test_opening_frame_without_readable_rows_checks_fresh_frame_before_input(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay("train_warrior_early", [])
    assert not selection_branch._visible_rows(solver.recog.img)
    solver.pending = ["warrior_top"]
    y = selection_branch._find_branch_row(solver, "WARRIOR", "术战者")
    assert y is not None and abs(y - 374) <= 2
    assert not solver.actions and solver.reads == 1
    stalled = MenuReplay("train_warrior_early", [])
    assert selection_branch._find_branch_row(stalled, "WARRIOR", "术战者") is None
    assert not stalled.actions and stalled.reads == 2


def test_branch_font_finds_white_and_dim_blue_labels_without_ocr(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("已确认的完整模板不应调用 OCR")

    monkeypatch.setattr(selection_branch, "_ocr", unexpected)
    solver = MenuReplay("warrior_bottom", [["train_liberator"]])
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert len(solver.actions) == 1 and abs(solver.actions[0][1][1] - 609) <= 2
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert len(solver.actions) == 1


def test_branch_font_rejects_duplicate_row_suffix_and_missing_glyph(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    panel = frame("tank_all_open")
    cropped = cv2.cvtColor(panel[100:1060, 1655:1792], cv2.COLOR_RGB2GRAY)
    assert abs(selection_branch._branch_rows(panel, "铁卫")["铁卫"] - 164) <= 2
    short = cv2.morphologyEx(cropped, cv2.MORPH_TOPHAT, np.ones((5, 5), np.uint8))[
        51:78, 41:93
    ].copy()
    assert selection_branch._template_row(cropped[40:90], "铁卫", short) is not None
    assert selection_branch._template_row(cropped[666:726], "铁卫", short) is None
    cropped[40:90] = 0
    assert selection_branch._template_row(cropped, "铁卫") is None
    assert selection_branch._branch_template("") is None
    assert selection_branch._branch_template("剑豪") is None
    assert (
        abs(selection_branch._branch_rows(frame("warrior_top"), "剑豪")["剑豪"] - 690)
        <= 2
    )

    single = frame("warrior_top")[100:1060, 1655:1792]
    duplicate = single.copy()
    duplicate[140:200] = single[35:95]
    assert (
        selection_branch._template_row(
            cv2.cvtColor(duplicate, cv2.COLOR_RGB2GRAY), "强攻手"
        )
        is None
    )


def test_confirmed_blue_sample_matches_another_rooms_white_label_with_missing_font(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    monkeypatch.setattr(selection_branch, "_branch_template", lambda name: None)
    solver = MenuReplay("train_liberator", [])
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert not solver.actions
    assert "解放者" in solver._branch_text_samples

    # 训练位确认的蓝字用于不同时段采集的生产房白字及普通亮蓝字。
    solver.recog.img = frame("warrior_bottom")
    solver.responses = iter([["warrior_liberator"]])
    monkeypatch.setattr(
        selection_branch, "_ocr", lambda *a, **kw: pytest.fail("重复 OCR")
    )
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert len(solver.actions) == 1 and abs(solver.actions[0][1][1] - 609) <= 2


def test_marginal_ocr_confirms_choice_without_teaching_a_template(engine, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", engine)
    monkeypatch.setattr(selection_branch, "_branch_template", lambda name: None)
    read = selection_branch._ocr
    monkeypatch.setattr(
        selection_branch,
        "_ocr",
        lambda roi, *, detect: read(roi, detect=True) if detect else [("解放者", 0.95)],
    )
    solver = MenuReplay("train_liberator", [])
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert not getattr(solver, "_branch_text_samples", {})


def test_selected_branch_rechecks_transient_ocr_failure_without_toggling(
    engine, monkeypatch
):
    monkeypatch.setattr(rapidocr, "engine", engine)
    monkeypatch.setattr(selection_branch, "_branch_template", lambda name: None)
    read = selection_branch._ocr
    blue_reads = iter([(), [("解放者", 0.99)]])
    monkeypatch.setattr(
        selection_branch,
        "_ocr",
        lambda roi, *, detect: read(roi, detect=True) if detect else next(blue_reads),
    )
    solver = MenuReplay("train_liberator", [])
    assert selection_branch._select_menu_row(solver, "WARRIOR", "解放者")
    assert not solver.actions
    assert "解放者" in solver._branch_text_samples


def test_arrow_is_bound_to_requested_profession_and_closed_dot():
    assert selection_branch.branch_filter_state(frame("tank_all_closed"), "TANK") == (
        False,
        False,
    )
    assert selection_branch.branch_filter_state(
        frame("tank_guardian_closed"), "TANK"
    ) == (False, True)
    assert (
        selection_branch.branch_filter_state(frame("tank_guardian_closed"), "WARRIOR")
        is None
    )
    assert selection_branch.branch_filter_state(frame("warrior_bottom"), "WARRIOR") == (
        True,
        False,
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("tank_all_closed", (False, False)),
        ("tank_all_open", (True, False)),
        ("tank_guardian_closed", (False, True)),
        ("tank_guardian_open", (True, True)),
    ],
)
def test_branch_state_survives_capture_jpeg(name, expected):
    captured = bytes2img(img2bytes(frame(name)))
    assert selection_branch.branch_filter_state(captured, "TANK") == expected


def test_unknown_profession_or_missing_arrow_sends_no_input():
    solver = MenuReplay("tank_all_closed", [])
    assert not selection_branch.select_visible_branch(solver, "WARRIOR", "教官")
    assert not solver.actions


def test_menu_opened_but_failed_to_close_releases_room_retry(engine, monkeypatch):
    from arknights_mower.solvers.base_mixin import AgentSelectionNotReady

    monkeypatch.setattr(rapidocr, "engine", engine)
    solver = MenuReplay("tank_guardian_open", [[]])
    with pytest.raises(AgentSelectionNotReady):
        selection_branch.select_visible_branch(solver, "TANK", "守护者")
    assert solver.actions == [("tap", (1813, 446))]
