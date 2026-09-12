from arknights_mower.solvers.credit import (
    CLUE_NEXT_REGION,
    ORANGE_RATIO,
    count_orange,
    region_size,
)
from arknights_mower.utils.image import loadres

ORANGE_THRESHOLD = region_size(CLUE_NEXT_REGION) * ORANGE_RATIO


def test_active_orange_button_passes_orange_ratio():
    # 橙色「访问下位」按钮（clue_next.png）作为激活态，橙色应占到区域 15% 以上
    active = count_orange(loadres("clue_next"))
    assert active >= ORANGE_THRESHOLD


def test_gray_disabled_button_below_orange_ratio():
    # 灰/禁用态按钮（clue_next_black.png，截自用户实际灰色的访问下位）几乎没有橙色
    disabled = count_orange(loadres("clue_next_black"))
    assert disabled < ORANGE_THRESHOLD


def test_count_orange_boundary_rejects_non_orange():
    # 纯色 / 无橙色的图不应误判为「橙色按钮亮着」
    assert count_orange(loadres("friend_list")) < ORANGE_THRESHOLD
