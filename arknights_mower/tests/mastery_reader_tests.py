import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np

from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils import skill_label as skill_label_mod
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.skill_label import (
    format_skill_label,
    panel_skill_matches,
    resolve_panel_skill,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


def make_plan(**overrides):
    plan = {
        "id": 1,
        "char_id": "char_test",
        "char_name": "测试干员",
        "skill_index": 1,  # 技能2
        "skill_name": "二技能·测试技能",
        "target_level": 3,
        "status": "idle",
        "priority": 1,
    }
    plan.update(overrides)
    return plan


def make_panel(**overrides):
    panel = reader.RoomPanel(
        operator_name="测试干员",
        skill_name="测试技能",
        mastery_tier=2,
        countdown=datetime.now() + timedelta(hours=2),
        countdown_state="active",
    )
    panel.__dict__.update(overrides)
    return panel


def make_room(state="empty", support_slot="", train_slot="", **panel_kwargs):
    return reader.RoomState(
        state=state,
        panel=make_panel(**panel_kwargs),
        support_slot=support_slot,
        train_slot=train_slot,
    )


# #95 resolve_panel_skill 用合成 skill_data（模拟 skill_data.json 结构，确定性）
SYNTH_SKILL_DATA = {
    "characters": {
        "char_test": {
            "name": "测试干员",
            "skills": [{"name": "多首野兽"}, {"name": "破坏与滋养"}],
        },
        "char_trunc": {
            "name": "截断干员",
            "skills": [{"name": "攻击力强化·γ型"}, {"name": "秘杖·反重力模式"}],
        },
        "char_ambiguous": {
            "name": "含混干员",
            "skills": [{"name": "破坏与滋养"}, {"name": "破坏之光"}],
        },
        "char_nameless": {
            "name": "无命名干员",
            "skills": [{"skillId": "sk_a"}, {"skillId": "sk_b"}],
        },
    }
}


class TestSkillLabel(unittest.TestCase):
    def test_canonical_format(self):
        self.assertEqual(format_skill_label(1, "飞翔瞪射"), "二技能·飞翔瞪射")
        self.assertEqual(format_skill_label(0, "冲锋号令·α型"), "一技能·冲锋号令·α型")

    def test_placeholder_fallback(self):
        self.assertEqual(format_skill_label(0, "技能1"), "技能1")
        self.assertEqual(format_skill_label(2, None), "技能3")

    def test_already_canonical_passthrough(self):
        self.assertEqual(format_skill_label(2, "二技能·飞翔瞪射"), "二技能·飞翔瞪射")

    def test_normalize_and_match(self):
        self.assertTrue(panel_skill_matches("飞翔瞪射", "二技能·飞翔瞪射"))
        self.assertTrue(panel_skill_matches("扫射模式", "一技能·扫射模式"))
        self.assertFalse(panel_skill_matches("过载模式", "二技能·扫射模式"))
        self.assertFalse(panel_skill_matches("", "二技能·飞翔瞪射"))
        # 长名截断（面板显示前缀）仍是包含匹配
        self.assertTrue(panel_skill_matches("秘杖", "二技能·秘杖·反重力模式"))
        # 分隔符归一化：・ vs ·
        self.assertTrue(panel_skill_matches("冲锋号令・α型", "一技能·冲锋号令·α型"))
        # OCR 尾部多读一个拉丁字母/数字 → 去尾兜底仍匹配
        self.assertTrue(panel_skill_matches("破坏与滋养A", "二技能·破坏与滋养"))
        self.assertTrue(panel_skill_matches("飞翔瞪射2", "二技能·飞翔瞪射"))
        # 合法尾部字母（红桃K）直接命中，不走兜底也不误伤
        self.assertTrue(panel_skill_matches("红桃K", "一技能·红桃K"))


def _patch_synth_skill_data():
    """patch get_skill_data 为合成数据，并重置 skill_label 反查缓存（setUp 用）。"""
    patcher = patch(
        "arknights_mower.utils.mastery_recommendation.get_skill_data",
        return_value=SYNTH_SKILL_DATA,
    )
    patcher.start()
    skill_label_mod._name_to_char_id_cache = None
    return patcher


class TestResolvePanelSkill(unittest.TestCase):
    """#95：面板技能文本对照干员已知技能表解析（互含，命中唯一才采纳）。"""

    def setUp(self):
        self._patcher = _patch_synth_skill_data()
        self.addCleanup(self._patcher.stop)

    def tearDown(self):
        skill_label_mod._name_to_char_id_cache = None

    def test_tail_noise_resolves_to_skill(self):
        # 事故案例：OCR 多读尾部拉丁字母 → 真名 ⊂ 面板 → 命中
        self.assertEqual(resolve_panel_skill("测试干员", "破坏与滋养A"), 1)

    def test_clean_name_resolves(self):
        self.assertEqual(resolve_panel_skill("测试干员", "破坏与滋养"), 1)
        self.assertEqual(resolve_panel_skill("测试干员", "多首野兽"), 0)

    def test_head_noise_resolves(self):
        self.assertEqual(resolve_panel_skill("测试干员", "X破坏与滋养"), 1)

    def test_truncated_name_resolves(self):
        self.assertEqual(resolve_panel_skill("截断干员", "秘杖"), 1)

    def test_unknown_operator_returns_none(self):
        self.assertIsNone(resolve_panel_skill("路人干员", "破坏与滋养"))

    def test_empty_inputs_return_none(self):
        self.assertIsNone(resolve_panel_skill("", "破坏与滋养"))
        self.assertIsNone(resolve_panel_skill("测试干员", ""))

    def test_no_named_skills_returns_none(self):
        self.assertIsNone(resolve_panel_skill("无命名干员", "任意文本"))

    def test_ambiguous_multiple_candidates_returns_none(self):
        # 「破坏」是两个已知技能共享的子串 → 含混不采纳（保守回退）
        self.assertIsNone(resolve_panel_skill("含混干员", "破坏"))

    def test_direct_char_id_supported(self):
        # dev 模式面板干员名可能直接是 char_id
        self.assertEqual(resolve_panel_skill("char_test", "破坏与滋养"), 1)


class TestResolvePanelSkillRealData(unittest.TestCase):
    """真实 skill_data.json 冒烟：#95 事故干员（char_4183_mortis，技能 [多首野兽, 破坏与滋养]）。"""

    def test_wakaba_musubi_tail_noise(self):
        self.assertEqual(resolve_panel_skill("若叶睦", "破坏与滋养A"), 1)

    def test_wakaba_musubi_clean(self):
        self.assertEqual(resolve_panel_skill("若叶睦", "破坏与滋养"), 1)
        self.assertEqual(resolve_panel_skill("若叶睦", "多首野兽"), 0)


class TestPanelParse(unittest.TestCase):
    def test_parse_bracketed(self):
        self.assertEqual(
            reader._parse_panel_text("[能天使]扫射模式"), ("能天使", "扫射模式")
        )

    def test_parse_no_bracket(self):
        self.assertEqual(reader._parse_panel_text("扫射模式"), ("", "扫射模式"))

    def test_parse_empty(self):
        self.assertEqual(reader._parse_panel_text(""), ("", ""))


class TestCountLitMainPanelIcons(unittest.TestCase):
    """主面板专精图标逐框判亮（MASTERY_ICON_PIPS）。"""

    def _canvas(self, lit_indexes):
        """构造 1080p 画布，按 lit_indexes 点亮主面板三颗星。"""
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for i, ((x0, y0), (x1, y1)) in enumerate(reader.MASTERY_ICON_PIPS):
            color = (255, 200, 92) if i in lit_indexes else (0, 0, 0)
            img[y0:y1, x0:x1] = color
        return img

    def _solver(self, img):
        s = unittest.mock.MagicMock()
        s.recog.img = img
        return s

    def test_zero(self):
        self.assertEqual(
            reader._count_lit_mastery_icons(self._solver(self._canvas([]))), 0
        )

    def test_one_top(self):
        self.assertEqual(
            reader._count_lit_mastery_icons(self._solver(self._canvas([0]))), 1
        )

    def test_two_top_and_second(self):
        self.assertEqual(
            reader._count_lit_mastery_icons(self._solver(self._canvas([0, 1]))), 2
        )

    def test_three_all(self):
        self.assertEqual(
            reader._count_lit_mastery_icons(self._solver(self._canvas([0, 1, 2]))), 3
        )

    def test_no_img_zero(self):
        self.assertEqual(reader._count_lit_mastery_icons(self._solver(None)), 0)


def _draw_circle(img, cx, cy, r, color):
    """在 RGB numpy 图上画实心圆（技能选择页星形测试用）。"""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    img[mask] = color


class TestReadSlotMasteryTier(unittest.TestCase):
    def _canvas(self, lit_indexes, skill_index=0):
        """构造覆盖该技能三颗星区域的画布，按 lit_indexes 画亮/灭圆。"""
        boxes = reader.SKILL_SLOT_PIPS[skill_index]
        img = np.zeros((900, 700, 3), dtype=np.uint8)
        for i, ((x0, y0), (x1, y1)) in enumerate(boxes):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r = (x1 - x0) * 0.44
            color = (255, 200, 92) if i in lit_indexes else (58, 64, 82)
            _draw_circle(img, cx, cy, r, color)
        return img

    def _solver(self, img):
        s = unittest.mock.MagicMock()
        s.recog.img = img
        return s

    def test_unknown_skill_returns_none(self):
        s = self._solver(self._canvas([]))
        self.assertIsNone(reader._read_slot_mastery_tier(s, 3))

    def test_no_img_returns_none(self):
        self.assertIsNone(reader._read_slot_mastery_tier(self._solver(None), 0))

    def test_tier_zero(self):
        tier = reader._read_slot_mastery_tier(self._solver(self._canvas([])), 0)
        self.assertEqual(tier, 0)

    def test_tier_one_top_lit(self):
        tier = reader._read_slot_mastery_tier(self._solver(self._canvas([0])), 0)
        self.assertEqual(tier, 1)

    def test_tier_two_top_and_second(self):
        tier = reader._read_slot_mastery_tier(self._solver(self._canvas([0, 1])), 0)
        self.assertEqual(tier, 2)

    def test_tier_three_all_lit(self):
        tier = reader._read_slot_mastery_tier(self._solver(self._canvas([0, 1, 2])), 0)
        self.assertEqual(tier, 3)

    def test_skill_two_uses_its_own_boxes(self):
        # 技能2（index 1）的三颗星位于不同 y，独立定位不应串到技能1
        tier = reader._read_slot_mastery_tier(
            self._solver(self._canvas([0, 1], skill_index=1)), 1
        )
        self.assertEqual(tier, 2)
        # 技能2 全亮时，技能1 区域保持空（各自独立）
        tier0 = reader._read_slot_mastery_tier(
            self._solver(self._canvas([0, 1], skill_index=1)), 0
        )
        self.assertEqual(tier0, 0)


class TestClassifyRoom(unittest.TestCase):
    """#73 状态矩阵（§16.2）：三态倒计时 × 干员/技能存在性 × 图标亮点。"""

    def test_train_finish_is_waiting_collect(self):
        self.assertEqual(
            reader.classify_room_state(Scene.TRAIN_FINISH, "failed", False, False),
            "waiting_collect",
        )

    def test_zero_countdown_is_waiting_collect(self):
        # §16.8：00:00:00 → 待收取（完成房间不再被当空房重置重开），与身份/图标无关
        self.assertEqual(
            reader.classify_room_state(Scene.TRAIN_MAIN, "zero", True, True),
            "waiting_collect",
        )
        self.assertEqual(
            reader.classify_room_state(Scene.TRAIN_MAIN, "zero", False, False),
            "waiting_collect",
        )

    def test_active_countdown_with_identity_and_icon_training(self):
        self.assertEqual(
            reader.classify_room_state(Scene.TRAIN_MAIN, "active", True, True),
            "training",
        )

    def test_empty_countdown_no_identity_no_icon_empty(self):
        # 倒计时为空 + 无名无亮点 → 空闲
        self.assertEqual(
            reader.classify_room_state(Scene.TRAIN_MAIN, "failed", False, False),
            "empty",
        )

    def test_inconsistent_combos_ocr_fail(self):
        # 其余 6 种不一致组合 → OCR/亮点计算失败（读取器原地重试 5 次）
        cases = [
            ("active", False, False),  # 非0 + 无身份 + 无亮点
            ("active", True, False),  # 非0 + 身份 + 无亮点
            ("active", False, True),  # 非0 + 无身份 + 有亮点
            ("failed", True, False),  # 空 + 身份 + 无亮点
            ("failed", True, True),  # 空 + 身份 + 有亮点
            ("failed", False, True),  # 空 + 无身份 + 有亮点
        ]
        for cd, ident, icon in cases:
            self.assertEqual(
                reader.classify_room_state(Scene.TRAIN_MAIN, cd, ident, icon),
                "ocr_fail",
                f"countdown={cd} identity={ident} icon={icon}",
            )

    def test_other_scene_conservative(self):
        self.assertEqual(
            reader.classify_room_state(
                Scene.TRAIN_SKILL_SELECT, "failed", False, False
            ),
            "training",
        )
        self.assertEqual(
            reader.classify_room_state(Scene.UNKNOWN, "failed", False, False),
            "training",
        )


class TestMatchPlan(unittest.TestCase):
    def test_match_by_operator_and_skill(self):
        room = make_room("training")
        plan = make_plan()
        self.assertEqual(reader._match_plan([plan], room), plan)

    def test_no_match_wrong_skill(self):
        room = make_room("training", skill_name="别的技能")
        plan = make_plan()
        self.assertIsNone(reader._match_plan([plan], room))

    def test_no_match_empty_operator(self):
        room = make_room("training", operator_name="")
        plan = make_plan()
        self.assertIsNone(reader._match_plan([plan], room))

    def test_match_falls_back_to_operator_when_skill_unreadable(self):
        room = make_room("training", skill_name="")
        plan = make_plan()
        self.assertEqual(reader._match_plan([plan], room), plan)

    def test_match_excludes_terminal(self):
        room = make_room("training")
        done = make_plan(status="completed")
        self.assertIsNone(reader._match_plan([done], room))

    def test_match_includes_failed(self):
        # #98：failed 也纳入匹配（reconcile 计划集含 failed，按截图恢复 training）
        room = make_room("training")
        failed = make_plan(status="failed")
        self.assertEqual(reader._match_plan([failed], room), failed)


class TestResolvePanelSkillIntegration(unittest.TestCase):
    """#95 集成：_plan_matches_room / _match_plan 优先用技能表解析，回退包含匹配。"""

    def setUp(self):
        self._patcher = _patch_synth_skill_data()
        self.addCleanup(self._patcher.stop)

    def tearDown(self):
        skill_label_mod._name_to_char_id_cache = None

    def test_plan_matches_room_tail_noise_resolves(self):
        plan = make_plan(
            char_id="char_test",
            char_name="测试干员",
            skill_index=1,
            skill_name="二技能·破坏与滋养",
        )
        room = make_room("training", skill_name="破坏与滋养A")
        self.assertTrue(reader._plan_matches_room(plan, room))

    def test_plan_matches_room_wrong_skill_mismatch(self):
        plan = make_plan(
            char_id="char_test",
            char_name="测试干员",
            skill_index=0,
            skill_name="一技能·多首野兽",
        )
        room = make_room("training", skill_name="破坏与滋养A")
        self.assertFalse(reader._plan_matches_room(plan, room))

    def test_match_plan_finds_correct_skill_plan(self):
        plan1 = make_plan(
            id=1,
            char_id="char_test",
            char_name="测试干员",
            skill_index=0,
            skill_name="一技能·多首野兽",
        )
        plan2 = make_plan(
            id=2,
            char_id="char_test",
            char_name="测试干员",
            skill_index=1,
            skill_name="二技能·破坏与滋养",
        )
        room = make_room("training", skill_name="破坏与滋养A")
        self.assertEqual(reader._match_plan([plan1, plan2], room), plan2)

    def test_match_plan_falls_back_for_unknown_operator(self):
        # 干员不在技能表 → resolve None → 回退 panel_skill_matches（现行为）
        plan = make_plan(char_name="陌生干员", skill_name="二技能·测试技能")
        room = make_room("training", operator_name="陌生干员", skill_name="测试技能")
        self.assertEqual(reader._match_plan([plan], room), plan)


class TestCanAdoptExpiry(unittest.TestCase):
    """B8 采纳门：只有面板干员名可读且匹配时才可采纳倒计时。"""

    def test_readable_and_matching_adopts(self):
        room = make_room("training")
        plan = make_plan()
        self.assertTrue(reader._can_adopt_expiry(plan, room))

    def test_unreadable_operator_rejects(self):
        # 与 _plan_matches_room（不可读=匹配）相反：采纳门不可读 → 不采纳
        room = make_room("training", operator_name="")
        plan = make_plan()
        self.assertFalse(reader._can_adopt_expiry(plan, room))

    def test_operator_mismatch_rejects(self):
        room = make_room("training", operator_name="别的干员")
        plan = make_plan()
        self.assertFalse(reader._can_adopt_expiry(plan, room))

    def test_skill_unreadable_rejects(self):
        # 用户 08-15 定案：采纳倒计时必须技能名也可读且匹配（不能认不可读的技能）
        room = make_room("training", skill_name="")
        plan = make_plan()
        self.assertFalse(reader._can_adopt_expiry(plan, room))

    def test_skill_mismatch_rejects(self):
        room = make_room("training", skill_name="别的技能")
        plan = make_plan()
        self.assertFalse(reader._can_adopt_expiry(plan, room))


class TestCanRecoverPlan(unittest.TestCase):
    """#98 恢复门：比 B8 采纳门更严——技能必须被解析器无歧义命中且等于计划 skill_index。

    恢复的后果重（failed→training 写库 + 清 failed_reason + 排收取/换人），不允许
    `_plan_matches_room` 的子串回退（OCR 退化片段如「技能」⊂ 所有技能名会把同干员
    另一技能的计划误恢复）；截断前缀由 resolve_panel_skill 正确解析，不受影响。
    """

    def setUp(self):
        self._patcher = _patch_synth_skill_data()
        self.addCleanup(self._patcher.stop)

    def tearDown(self):
        skill_label_mod._name_to_char_id_cache = None

    def _plan(self, char_name="测试干员", skill_index=1, skill_name="二技能·破坏与滋养"):
        return make_plan(
            char_id="char_test", char_name=char_name, skill_index=skill_index,
            skill_name=skill_name,
        )

    def test_resolves_unique_skill_adopts(self):
        # 截断/尾噪片段被解析器唯一命中且等于计划技能 → 可恢复（正控制）
        room = make_room("training", operator_name="测试干员", skill_name="破坏与滋养A")
        self.assertTrue(reader._can_recover_plan(self._plan(), room))

    def test_truncated_prefix_resolves_adopts(self):
        # 截断前缀（长名截断）由解析器正确解析 → 可恢复
        room = make_room("training", operator_name="截断干员", skill_name="秘杖")
        plan = make_plan(
            char_name="截断干员", skill_index=1, skill_name="二技能·秘杖·反重力模式"
        )
        self.assertTrue(reader._can_recover_plan(plan, room))

    def test_ambiguous_fragment_rejects(self):
        # 技能 OCR 退化片段「技能」⊂ 所有技能名 → 解析器含混 → 不恢复（#98 收紧核心）
        room = make_room("training", operator_name="测试干员", skill_name="技能")
        self.assertFalse(reader._can_recover_plan(self._plan(), room))

    def test_ambiguous_operator_skill_rejects(self):
        # 干员两个技能共享前缀「破坏」（破坏与滋养/破坏之光）→ 解析器含混 → 不恢复
        room = make_room("training", operator_name="含混干员", skill_name="破坏")
        plan = make_plan(char_name="含混干员", skill_index=0, skill_name="一技能·破坏与滋养")
        self.assertFalse(reader._can_recover_plan(plan, room))

    def test_operator_mismatch_rejects(self):
        room = make_room("training", operator_name="别的干员", skill_name="破坏与滋养A")
        self.assertFalse(reader._can_recover_plan(self._plan(), room))

    def test_unknown_operator_rejects(self):
        # 干员不在技能表 → 解析器 None → 不恢复（宁可漏恢复，不可误接管）
        room = make_room("training", operator_name="陌生干员", skill_name="破坏与滋养A")
        self.assertFalse(reader._can_recover_plan(self._plan(char_name="陌生干员"), room))

    def test_skill_unreadable_rejects(self):
        room = make_room("training", operator_name="测试干员", skill_name="")
        self.assertFalse(reader._can_recover_plan(self._plan(), room))


class TestReadRoomState(unittest.TestCase):
    """fake solver 驱动真实 read_room_state：进房读面板+三态倒计时+图标+分类。"""

    def _solver(
        self, countdown_seconds, panel_text="[测试干员]测试技能", tier_columns=(0, 1, 2)
    ):
        solver = MagicMock()
        solver.train_scene.side_effect = [Scene.TRAIN_MAIN]
        # #73 三态倒计时：read_time 返回秒（None=读失败 / 0=00:00:00 / >0=有值）
        solver.read_time.return_value = countdown_seconds
        solver.read_screen.return_value = panel_text
        solver.find.side_effect = lambda res, *a, **k: (
            None if res == "training_completed" else MagicMock()
        )
        solver.enter_room = MagicMock()
        solver.recog.w = 1920
        solver.recog.h = 1080
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        (x0, y0), (x1, y1) = reader.MASTERY_ICON_REGION
        slot_w = (x1 - x0) // 3
        for col in tier_columns:
            img[y0:y1, x0 + col * slot_w : x0 + (col + 1) * slot_w] = 255
        solver.recog.img = img
        solver.recog.update = MagicMock()
        return solver

    def test_training_state_reads_panel(self):
        solver = self._solver(7200)
        room = reader.read_room_state(solver)
        self.assertEqual(room.state, "training")
        self.assertEqual(room.panel.operator_name, "测试干员")
        self.assertEqual(room.panel.skill_name, "测试技能")
        self.assertEqual(room.panel.mastery_tier, 3)
        self.assertEqual(room.panel.countdown_state, "active")

    def test_empty_state_when_countdown_unreadable(self):
        # 倒计时读失败 + 无名无亮点 → 空闲
        solver = self._solver(None, panel_text="", tier_columns=())
        room = reader.read_room_state(solver)
        self.assertEqual(room.state, "empty")

    def test_zero_countdown_is_waiting_collect(self):
        # §16.8 修复点：完成房间（00:00:00）→ 待收取，不再被当空房重置重开
        solver = self._solver(0)
        room = reader.read_room_state(solver)
        self.assertEqual(room.state, "waiting_collect")

    def test_waiting_collect_when_finish_scene(self):
        solver = self._solver(0)
        solver.train_scene.side_effect = [Scene.TRAIN_FINISH]
        room = reader.read_room_state(solver)
        self.assertEqual(room.state, "waiting_collect")

    def test_ocr_fail_retries_then_conservative_training(self):
        # §16.2：active+身份+无图标 → 每次重读都 ocr_fail → 5 次后保守训练中（read_failed）
        solver = self._solver(7200, panel_text="[测试干员]测试技能", tier_columns=())
        room = reader.read_room_state(solver)
        self.assertEqual(room.state, "training")
        self.assertTrue(room.read_failed)

    def test_ocr_fail_resolves_on_retry(self):
        # 重读过程中出现图标亮点 → 恢复训练中（非保守）
        solver = self._solver(7200, panel_text="[测试干员]测试技能", tier_columns=())
        base = solver.recog.img.copy()
        lit = base.copy()
        (x0, y0), (x1, y1) = reader.MASTERY_ICON_REGION
        slot_w = (x1 - x0) // 3
        for col in (0, 1, 2):
            lit[y0:y1, x0 + col * slot_w : x0 + (col + 1) * slot_w] = 255
        frames = [base, base, lit]
        solver.recog.img = frames[0]

        def _update():
            solver.recog.img = frames.pop(0) if frames else solver.recog.img

        solver.recog.update.side_effect = _update
        room = reader.read_room_state(solver)
        self.assertEqual(room.state, "training")
        self.assertFalse(room.read_failed)

    def test_want_mood_collects_slots_and_mood_once(self):
        # #94：待收取开浮窗读槽位时顺带收集心情——get_agent_from_room 只开一次
        solver = self._solver(0)
        scan = [
            {"agent": "支援干员", "mood": 20.1234},
            {"agent": "训练干员", "mood": 15.5678},
        ]
        solver.get_agent_from_room.return_value = scan
        room, mood = reader.read_room_state(solver, want_mood=True)
        self.assertEqual(room.state, "waiting_collect")
        self.assertEqual(room.support_slot, "支援干员")
        self.assertEqual(room.train_slot, "训练干员")
        self.assertEqual(mood, scan)
        solver.get_agent_from_room.assert_called_once_with("train")

    def test_want_mood_training_state_reads_mood(self):
        # 训练中（倒计时非 0）也要读心情：开一次浮窗读全再关回 TRAIN_MAIN
        solver = self._solver(7200)
        scan = [
            {"agent": "支援干员", "mood": 20.1234},
            {"agent": "训练干员", "mood": 15.5678},
        ]
        solver.get_agent_from_room.return_value = scan
        room, mood = reader.read_room_state(solver, want_mood=True)
        self.assertEqual(room.state, "training")
        self.assertEqual(room.support_slot, "支援干员")
        self.assertEqual(room.train_slot, "训练干员")
        self.assertEqual(mood, scan)
        solver.get_agent_from_room.assert_called_once_with("train")

    def test_want_mood_finish_scene_empty_mood(self):
        # TRAIN_FINISH（完成横幅页）只读面板：浮窗不可靠 → 心情返回空列表
        solver = self._solver(0)
        solver.train_scene.side_effect = [Scene.TRAIN_FINISH]
        room, mood = reader.read_room_state(solver, want_mood=True)
        self.assertEqual(room.state, "waiting_collect")
        self.assertEqual(mood, [])
        solver.get_agent_from_room.assert_not_called()

    def test_want_mood_default_returns_room_only(self):
        # 不破坏现有调用：默认 want_mood=False 返回 RoomState（非元组）
        solver = self._solver(7200)
        room = reader.read_room_state(solver)
        self.assertIsInstance(room, reader.RoomState)

    def test_off_mode_skips_slot_read_for_waiting_collect(self):
        # 审计修复：enable_mastery OFF 时槽位/保护无人消费，待收取态不白开进驻浮窗
        solver = self._solver(0)
        with patch.object(reader.config.conf, "enable_mastery", False):
            room = reader.read_room_state(solver)
        self.assertEqual(room.state, "waiting_collect")
        solver.get_agent_from_room.assert_not_called()


class TestReconcileShort(unittest.TestCase):
    """reconcile_short：排班路径顺路短动作（不开始训练、不退出房间）。"""

    def test_training_consistent_updates_expiry_no_exit(self):
        solver = MagicMock()
        room = make_room("training")
        active = make_plan(status="training")
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=active
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[active]
            ),
            patch.object(reader, "_update_expiry") as ue,
            patch.object(reader, "_collect_plan"),
        ):
            reader.reconcile_short(solver, room)
        ue.assert_called_once_with(solver, active, room)
        solver.back.assert_not_called()  # 退出由调用方（gate）负责

    def test_waiting_collect_collects_no_exit(self):
        solver = MagicMock()
        room = make_room("waiting_collect")
        plan = make_plan(status="training")
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[plan]
            ),
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan"),
        ):
            reader.reconcile_short(solver, room)
        cp.assert_called_once()
        solver.back.assert_not_called()

    # --- #75 方案 C：gate-defer skip ---

    def test_defer_skips_collect_when_queue_has_plan_task(self):
        # gate（defer_collect=True）待收取格队列已有该计划收取任务 → 跳过本次收集，
        # 留给那条任务收（any-task 匹配的子集：同计划任务当然也算），`_collect_plan` 不被调。
        solver = MagicMock()
        room = make_room("waiting_collect")
        plan = make_plan(status="training")
        task = reader.SchedulerTask(
            time=datetime.now(), task_type=reader.TaskTypes.SKILL_UPGRADE
        )
        task.plan_key = str(plan["id"])
        solver.tasks = [task]
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[plan]
            ),
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan") as pp,
        ):
            reader.reconcile_short(solver, room, defer_collect=True)
        cp.assert_not_called()
        pp.assert_not_called()
        solver.back.assert_not_called()

    def test_defer_collects_when_queue_empty(self):
        # 队列无专精任务（如缓存清零重启丢了）→ 照常收集（恢复兜底）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("waiting_collect")
        plan = make_plan(status="training")
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[plan]
            ),
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan"),
        ):
            reader.reconcile_short(solver, room, defer_collect=True)
        cp.assert_called_once()
        solver.back.assert_not_called()

    def test_defer_skips_when_other_plan_task_queued(self):
        # 队列任务属于另一计划 → 同样跳过（any-task：只要队列有专精任务就留给队列任务收）
        solver = MagicMock()
        other = reader.SchedulerTask(
            time=datetime.now(), task_type=reader.TaskTypes.SKILL_UPGRADE
        )
        other.plan_key = str(2)
        solver.tasks = [other]
        room = make_room("waiting_collect")
        plan = make_plan(status="training")
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[plan]
            ),
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan") as pp,
        ):
            reader.reconcile_short(solver, room, defer_collect=True)
        cp.assert_not_called()
        pp.assert_not_called()
        solver.back.assert_not_called()


class TestReconcileRecoverSwap(unittest.TestCase):
    """#77：重启恢复 training×一致 时补排丢失的 SWAP_SUPPORT。

    reconcile 只补排任务（短动作，铁律 4：不碰房间、不退出）；实际读协助位/纠错/换人
    由 SWAP dispatch 的 #79 `run_swap_support` 完成——补排直接复用
    `_schedule_swap_if_needed`（换人公式/路线判定口径与正常排程一致，不重复实现）。
    """

    def setUp(self):
        self.patch_follows = patch.object(
            reader.config.conf, "assistant_follows_schedule", False
        )
        self.patch_enable = patch.object(reader.config.conf, "enable_mastery", True)
        self.patch_follows.start()
        self.patch_enable.start()
        self.addCleanup(self.patch_follows.stop)
        self.addCleanup(self.patch_enable.stop)

    def _solver(self):
        solver = MagicMock()
        solver.tasks = []
        solver.task = None
        return solver

    def _training_plan(self):
        return make_plan(status="training", swap_frozen=0)

    def _room(self, countdown=datetime.now() + timedelta(hours=6), tier=2):
        return reader.RoomState(
            state="training",
            panel=make_panel(
                mastery_tier=tier, countdown=countdown, countdown_state="active"
            ),
        )

    # --- _maybe_recover_swap 门控 ---

    def test_recover_calls_swap_scheduler(self):
        # 门控全过（跟随排班关、非 frozen、队列无 SWAP、倒计时可读）→ 复用
        # _schedule_swap_if_needed 补排；step_level = 主面板图标（当前步目标级，#76）
        solver = self._solver()
        plan = self._training_plan()
        room = self._room(tier=2)
        with patch(
            "arknights_mower.solvers.mastery._schedule_swap_if_needed",
            return_value=NOW + timedelta(hours=4),
        ) as sched:
            reader._maybe_recover_swap(solver, plan, room)
        sched.assert_called_once_with(solver, plan, room.panel.countdown, 2)

    def test_recover_follows_schedule_skips(self):
        # 跟随排班开 → 协助位归排班系统管，任何补排都跳过（照搬 run_swap_support gate）
        solver = self._solver()
        with (
            patch.object(reader.config.conf, "assistant_follows_schedule", True),
            patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched,
        ):
            reader._maybe_recover_swap(solver, self._training_plan(), self._room())
        sched.assert_not_called()

    def test_recover_swap_frozen_skips(self):
        # 换人已完成（swap_frozen=1）→ 不补排
        solver = self._solver()
        plan = make_plan(status="training", swap_frozen=1)
        with patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched:
            reader._maybe_recover_swap(solver, plan, self._room())
        sched.assert_not_called()

    def test_recover_queued_swap_task_skips(self):
        # 队列已有同计划 SWAP 任务（重启恢复的队列可能还留着旧任务）→ 不重复补排
        solver = self._solver()
        task = reader.SchedulerTask(
            time=datetime.now(), task_type=reader.TaskTypes.SWAP_SUPPORT
        )
        task.plan_key = "1"
        solver.tasks = [task]
        with patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched:
            reader._maybe_recover_swap(solver, self._training_plan(), self._room())
        sched.assert_not_called()

    def test_recover_countdown_missing_skips(self):
        # 倒计时读不到 → 不补排（无法判剩余时间，铁律：以截图为准）
        solver = self._solver()
        room = self._room(countdown=None)
        with patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched:
            reader._maybe_recover_swap(solver, self._training_plan(), room)
        sched.assert_not_called()

    def test_recover_enable_off_skips(self):
        # enable_mastery OFF → 任何训练室动作/补排都不执行（铁律 10）
        solver = self._solver()
        with (
            patch.object(reader.config.conf, "enable_mastery", False),
            patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched,
        ):
            reader._maybe_recover_swap(solver, self._training_plan(), self._room())
        sched.assert_not_called()

    def test_recover_mastery_tier_zero_falls_back_target_level(self):
        # 图标读不到（tier=0）→ step_level 传 None，_get_plan_route 回退 target_level
        solver = self._solver()
        plan = self._training_plan()  # target_level=3
        room = self._room(tier=0)
        with patch(
            "arknights_mower.solvers.mastery._schedule_swap_if_needed",
            return_value=None,
        ) as sched:
            reader._maybe_recover_swap(solver, plan, room)
        sched.assert_called_once_with(solver, plan, room.panel.countdown, None)

    # --- #80 陌生人协助位纠错 ---

    def _correction_route(self, swap_target="逻各斯"):
        return {
            "operator": "夜半",
            "swap_target": swap_target,
            "central_bonus": 5,
            "efficiency": 75,
            "job_match": True,
        }

    def _slots(self, support):
        solver = self._solver()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.get_agent_from_room.return_value = [
            {"agent": support},
            {"agent": "能天使"},
        ]
        return solver

    def test_recover_stranger_schedules_correction(self):
        # 协助位是陌生人（∉ {operator, swap_target}）→ 排纠错 SWAP 任务（带 plan_key），
        # 不走 _schedule_swap_if_needed（纠错与减半合并为同一条任务，dispatch 时再判减半）
        solver = self._slots("陌生人")
        plan = self._training_plan()
        room = self._room()
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched,
        ):
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertTrue(result, "排了纠错任务 → 调用方不排收取")
        sched.assert_not_called()
        swaps = [t for t in solver.tasks if t.type == reader.TaskTypes.SWAP_SUPPORT]
        self.assertEqual(len(swaps), 1)
        self.assertEqual(swaps[0].plan_key, str(plan["id"]))
        self.assertIn("纠错为 夜半", swaps[0].meta_data)

    def test_recover_stranger_m3_step_correction(self):
        # 专三步（swap_target=None，铁律 7）：陌生人协助位仍纠成路线人（只纠不换减半）
        solver = self._slots("陌生人")
        plan = self._training_plan()
        room = self._room()
        with patch(
            "arknights_mower.solvers.mastery._get_plan_route",
            return_value=self._correction_route(swap_target=None),
        ) as route:
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertTrue(result)
        swaps = [t for t in solver.tasks if t.type == reader.TaskTypes.SWAP_SUPPORT]
        self.assertEqual(len(swaps), 1, "专三步陌生人协助位也应纠错")
        route.assert_called_once()

    def test_recover_assist_operator_falls_through_to_swap(self):
        # 协助位已是路线 operator（不是陌生人）→ 不纠错，走 _schedule_swap_if_needed 判减半
        solver = self._slots("夜半")
        plan = self._training_plan()
        room = self._room()
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch(
                "arknights_mower.solvers.mastery._schedule_swap_if_needed",
                return_value=NOW + timedelta(hours=4),
            ) as sched,
        ):
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertTrue(result)
        sched.assert_called_once()
        self.assertFalse(
            [t for t in solver.tasks if t.type == reader.TaskTypes.SWAP_SUPPORT],
            "协助位已是 operator 不纠错",
        )

    def test_recover_assist_swap_target_no_swap(self):
        # 已减半（协助位 == swap_target）→ 不纠错、不排换人，返回 False（调用方排收取）
        solver = self._slots("逻各斯")
        plan = self._training_plan()
        room = self._room()
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched,
        ):
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertFalse(result)
        sched.assert_not_called()

    def test_recover_empty_assist_slot_upserts_swap_task_now(self):
        # #101：协助位空着 → 确保一条 plan_key=id SWAP 任务现在执行（dispatch 时按
        # calc_swap_threshold(0,...) 一步定夺放 operator/swap_target），不再排独立
        # fill-{id} 补位任务
        solver = self._solver()
        solver.get_agent_from_room.return_value = [{"agent": ""}, {"agent": "能天使"}]
        plan = self._training_plan()
        room = self._room()
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch(
                "arknights_mower.solvers.mastery._schedule_swap_if_needed",
                return_value=None,
            ) as sched,
        ):
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertTrue(result, "排了补位任务 → 调用方不排收取")
        sched.assert_not_called()  # now-task 带 plan_key=id → 尾部去重不重复排阈值
        swaps = [
            t
            for t in solver.tasks
            if t.type == reader.TaskTypes.SWAP_SUPPORT
            and t.plan_key == str(plan["id"])
        ]
        self.assertEqual(len(swaps), 1)
        self.assertIn("补位为 夜半", swaps[0].meta_data)

    def test_recover_empty_assist_slot_retimes_queued_swap(self):
        # #101：队列已有该计划的半程换人任务 → 空位时把它改到「现在」执行（不排独立
        # fill-{id} 补位任务、不并存）——dispatch 自决放 operator/swap_target
        solver = self._solver()
        solver.get_agent_from_room.return_value = [{"agent": ""}, {"agent": "能天使"}]
        plan = self._training_plan()
        room = self._room()
        swap_task = reader.SchedulerTask(
            time=datetime.now() + timedelta(hours=3),
            task_type=reader.TaskTypes.SWAP_SUPPORT,
        )
        swap_task.plan_key = str(plan["id"])
        solver.tasks = [swap_task]
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch(
                "arknights_mower.solvers.mastery._schedule_swap_if_needed"
            ) as sched,
        ):
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertTrue(result)
        sched.assert_not_called()  # 已有 now-task → 不重复排阈值
        self.assertEqual(len(solver.tasks), 1, "不新增补位任务（改到 now 而非并存）")
        self.assertEqual(solver.tasks[0].plan_key, str(plan["id"]))
        self.assertLess(
            abs((solver.tasks[0].time - datetime.now()).total_seconds()), 5,
            "已有半程换人任务被改到 now",
        )

    def test_recover_unreliable_slot_read_no_fill(self):
        # #100 review 修复（major：读失败当空位）：get_agent_from_room 异常（OCR 坏名
        # KeyError）→ reliable=False → 不算空位，不排补位（稳为先：读不到就不动作）
        solver = self._solver()
        solver.get_agent_from_room.side_effect = KeyError("坏名")
        plan = self._training_plan()
        room = self._room()
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch(
                "arknights_mower.solvers.mastery._schedule_swap_if_needed",
                return_value=None,
            ) as sched,
        ):
            result = reader._maybe_recover_swap(solver, plan, room)
        self.assertFalse(result, "读失败不算空位 → 无任务可排")
        swaps = [
            t
            for t in solver.tasks
            if t.type == reader.TaskTypes.SWAP_SUPPORT
            and t.plan_key == str(plan["id"])
        ]
        self.assertEqual(len(swaps), 0, "读失败不补位（稳为先）")
        sched.assert_called_once()

    def test_recover_route_no_operator_no_correction(self):
        # 路线拿不到 operator → 不纠错（无法判期望协助位），走 _schedule_swap_if_needed
        solver = self._slots("陌生人")
        plan = self._training_plan()
        room = self._room()
        with (
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch("arknights_mower.solvers.mastery._schedule_swap_if_needed") as sched,
        ):
            reader._maybe_recover_swap(solver, plan, room)
        sched.assert_called_once()

    def test_reconcile_training_stranger_correction_skips_collect(self):
        # 接线：training×一致 + 陌生人协助位 → 排纠错 SWAP，不排收取（半重叠消除）
        solver = self._slots("陌生人")
        plan = self._training_plan()
        room = self._room()
        with (
            patch.object(reader, "_update_expiry"),
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value=self._correction_route(),
            ),
            patch.object(reader, "_schedule_collect") as sc,
        ):
            reader._reconcile_training(solver, room, plan, [plan])
        sc.assert_not_called()
        swaps = [t for t in solver.tasks if t.type == reader.TaskTypes.SWAP_SUPPORT]
        self.assertEqual(len(swaps), 1)

    # --- _reconcile_training 接线 ---

    def test_reconcile_training_recovers_swap_on_consistent(self):
        # training×一致（active 匹配）→ _update_expiry 后触发 _maybe_recover_swap
        solver = self._solver()
        room = self._room()
        active = self._training_plan()
        with (
            patch.object(reader, "_update_expiry") as ue,
            patch.object(reader, "_maybe_recover_swap") as rec,
        ):
            reader._reconcile_training(solver, room, active, [active])
        ue.assert_called_once_with(solver, active, room)
        rec.assert_called_once_with(solver, active, room)

    def test_reconcile_training_no_recover_when_not_adopted(self):
        # 面板不可读（B8 不采纳倒计时）→ 不补排（无法确认训练归属，静默等待）
        solver = self._solver()
        room = reader.RoomState(
            state="training",
            panel=make_panel(operator_name="", skill_name=""),
        )
        active = self._training_plan()
        with (
            patch.object(reader, "_update_expiry") as ue,
            patch.object(reader, "_maybe_recover_swap") as rec,
        ):
            reader._reconcile_training(solver, room, active, [active])
        ue.assert_not_called()
        rec.assert_not_called()

    # --- 端到端：reconcile_short 真实 _schedule_swap_if_needed 补排 ---

    def test_reconcile_short_training_recovery_enqueues_swap(self):
        # 重启恢复：training×一致 → 复用 _schedule_swap_if_needed 补排 SWAP（带 plan_key）
        solver = self._solver()
        room = self._room()
        plan = self._training_plan()
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[plan]
            ),
            patch.object(reader, "_update_expiry"),
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch(
                "arknights_mower.solvers.mastery.calc_swap_threshold",
                return_value=(True, 100.0),
            ),
        ):
            reader.reconcile_short(solver, room)
        swaps = [t for t in solver.tasks if t.type == reader.TaskTypes.SWAP_SUPPORT]
        self.assertEqual(len(swaps), 1, "剩余够 → 应补排 SWAP_SUPPORT")
        self.assertEqual(swaps[0].plan_key, str(plan["id"]))

    def test_reconcile_short_training_insufficient_time_no_swap(self):
        # 剩余不足（calc 判不换）→ 不补排
        solver = self._solver()
        room = self._room()
        plan = self._training_plan()
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[plan]
            ),
            patch.object(reader, "_update_expiry"),
            patch(
                "arknights_mower.solvers.mastery._get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch(
                "arknights_mower.solvers.mastery.calc_swap_threshold",
                return_value=(False, 10000.0),
            ),
        ):
            reader.reconcile_short(solver, room)
        self.assertFalse(
            [t for t in solver.tasks if t.type == reader.TaskTypes.SWAP_SUPPORT],
            "剩余不足 → 不补排",
        )


class TestReconcileCollectDefer(unittest.TestCase):
    """#75 方案 C：gate-defer skip 的 _reconcile 层行为。"""

    def _collect_task(self, plan_id):
        task = reader.SchedulerTask(
            time=datetime.now(), task_type=reader.TaskTypes.SKILL_UPGRADE
        )
        task.plan_key = str(plan_id)
        return task

    def test_dispatch_path_never_defers(self):
        # dispatch（reconcile_and_act，defer_collect 默认 False）：当前任务即收集任务，
        # 必须收——即便队列有专精任务也照常收集，永不跳过。
        solver = MagicMock()
        task = self._collect_task(1)
        solver.tasks = [task]
        solver.task = task  # dispatch：当前任务就是收集任务
        room = make_room("waiting_collect")
        plan = make_plan()
        with patch.object(reader, "_collect_plan") as cp:
            reader._reconcile(solver, room, None, [plan])
        cp.assert_called_once()

    def test_defer_excludes_current_task(self):
        # 排除当前任务：即便 defer=True，若队列里唯一任务就是当前 dispatch（被排除），
        # 查不到别的任务 → 照常收集（不 skip 死锁）。
        solver = MagicMock()
        task = self._collect_task(1)
        solver.tasks = [task]
        solver.task = task
        room = make_room("waiting_collect")
        plan = make_plan()
        with patch.object(reader, "_collect_plan") as cp:
            reader._reconcile(solver, room, None, [plan], defer_collect=True)
        cp.assert_called_once()

    def test_defer_skips_when_other_task_queued(self):
        # defer=True + 队列已有专精任务（非当前 dispatch）→ 跳过收集
        solver = MagicMock()
        solver.task = None
        task = self._collect_task(1)
        solver.tasks = [task]
        room = make_room("waiting_collect")
        plan = make_plan()
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan") as pp,
        ):
            start, arrange_support = reader._reconcile(
                solver, room, None, [plan], defer_collect=True
            )
        cp.assert_not_called()
        pp.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)

    def test_defer_magicmock_tasks_defensive(self):
        # 防御：solver.tasks 不可迭代（MagicMock）→ 按无任务处理，照常收集兜底
        solver = MagicMock()
        room = make_room("waiting_collect")
        plan = make_plan()
        with patch.object(reader, "_collect_plan") as cp:
            reader._reconcile(solver, room, None, [plan], defer_collect=True)
        cp.assert_called_once()

    def test_defer_skips_m3_when_task_queued(self):
        # 专三同样纳入 skip（用户撤回「gate 收专三」例外）→ 队列有任务时跳过，留给
        # 任务收（③ 邮件在任务 dispatch 收取时发，不丢）
        solver = MagicMock()
        solver.task = None
        task = self._collect_task(1)
        solver.tasks = [task]
        room = make_room("waiting_collect", mastery_tier=3)
        plan = make_plan()
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan") as pp,
        ):
            start, arrange_support = reader._reconcile(
                solver, room, None, [plan], defer_collect=True
            )
        cp.assert_not_called()
        pp.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)

    def test_defer_skips_when_plan_key_none_task_queued(self):
        # plan_key=None（占用重检 / OCR 失败重排）也算专精任务 → 同样跳过收集
        solver = MagicMock()
        solver.task = None
        task = reader.SchedulerTask(
            time=datetime.now(), task_type=reader.TaskTypes.SKILL_UPGRADE
        )
        solver.tasks = [task]
        room = make_room("waiting_collect")
        plan = make_plan()
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan") as pp,
        ):
            start, arrange_support = reader._reconcile(
                solver, room, None, [plan], defer_collect=True
            )
        cp.assert_not_called()
        pp.assert_not_called()
        self.assertIsNone(start)


class TestReconcileMatrix(unittest.TestCase):
    """#61 恢复矩阵核心分支：空房/训练中/待收取 × 各 DB 状态。"""

    def test_empty_room_hands_back_to_schedule(self):
        # #74 第2段：空闲×未保护 → 不自动开始（交还排班），不再取下一个 idle 计划
        solver = MagicMock()
        room = make_room("empty")
        with patch(
            "arknights_mower.utils.mastery_db.get_next_idle_plan",
            return_value=make_plan(),
        ) as g:
            plan, arrange_support = reader._reconcile(solver, room, None, [make_plan()])
        g.assert_not_called()
        self.assertIsNone(plan, "空闲×未保护不再自动开始，交还排班")
        self.assertTrue(arrange_support)

    def test_empty_room_scan_driven_starts_specified_plan(self):
        # #74 第3段：扫描驱动任务（scan_plan 非 None 且仍 idle）→ 空闲×未保护返回该计划
        solver = MagicMock()
        room = make_room("empty")
        scan_plan = make_plan(status="idle")
        start, arrange_support = reader._reconcile(
            solver, room, None, [scan_plan], scan_plan=scan_plan
        )
        self.assertIs(start, scan_plan, "只开始任务标识的那个计划")
        self.assertTrue(arrange_support)

    def test_empty_room_scan_driven_plan_no_longer_idle_skips(self):
        # 扫描任务指定的计划已不在 idle（被其它路径接管）→ 不开始
        solver = MagicMock()
        room = make_room("empty")
        scan_plan = make_plan(status="training")
        start, _ = reader._reconcile(
            solver, room, None, [scan_plan], scan_plan=scan_plan
        )
        self.assertIsNone(start, "计划已不在 idle 不得开始")

    def test_empty_room_scan_driven_protected_skips(self):
        # 受保护优先：扫描任务指定的计划在受保护空房也不开始（⑤ 通知）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("empty", support_slot="逻各斯", train_slot="能天使")
        room.protected = True
        scan_plan = make_plan(status="idle")
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan",
                return_value=scan_plan,
            ),
            patch.object(reader, "_notify_protected") as np_,
        ):
            start, _ = reader._reconcile(
                solver, room, None, [scan_plan], scan_plan=scan_plan
            )
        self.assertIsNone(start, "受保护时空闲房间不得开始训练")
        np_.assert_called_once_with(solver, room)

    def test_empty_room_with_active_resets_quietly(self):
        # 空房×training 计划：截图权威 → 静默重置 idle 重开，不误报「假记录」通知②
        solver = MagicMock()
        room = make_room("empty")
        active = make_plan(status="training")
        with (
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan", return_value=None
            ),
            patch.object(reader, "_reset_fake") as rf,
        ):
            reader._reconcile(solver, room, active, [active])
        rf.assert_not_called()
        upd.assert_called_once_with(1, "idle")

    def test_arranging_any_state_resets_idle(self):
        solver = MagicMock()
        for state in ("training", "waiting_collect", "empty"):
            room = make_room(state)
            active = make_plan(status="arranging")
            with (
                patch.object(reader, "_reset_to_idle") as ri,
                patch.object(reader, "_update_expiry"),
                patch.object(reader, "_collect_plan"),
                patch.object(reader, "_collect_silent"),
                patch.object(reader, "_promote_plan"),
                patch(
                    "arknights_mower.utils.mastery_db.get_next_idle_plan",
                    return_value=None,
                ),
            ):
                reader._reconcile(solver, room, active, [active])
            ri.assert_called_once_with(solver, active)

    def test_training_consistent_updates_expiry(self):
        solver = MagicMock()
        room = make_room("training")
        active = make_plan(status="training")
        with patch.object(reader, "_update_expiry") as ue:
            reader._reconcile(solver, room, active, [active])
        ue.assert_called_once_with(solver, active, room)

    def test_training_inconsistent_resets_fake(self):
        solver = MagicMock()
        room = make_room("training", operator_name="别的干员")
        active = make_plan(status="training")
        with (
            patch.object(reader, "_reset_fake") as rf,
            patch.object(reader, "_notify_blocked"),
            patch.object(reader, "_wait_for_training"),
        ):
            plan, _ = reader._reconcile(solver, room, active, [active])
        rf.assert_called_once()
        self.assertIsNone(plan)

    def test_training_unreadable_panel_no_adoption(self):
        # B8：面板干员名不可读 → 不采纳倒计时（不刷新、不改写状态），也不判「假记录」、
        # 不排重检——让排班系统下次自然进房重读（用户 08-15 定案）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", operator_name="")
        active = make_plan(status="training")
        with (
            patch.object(reader, "_reset_fake") as rf,
            patch.object(reader, "_update_expiry") as ue,
            patch.object(reader, "_notify_blocked") as nb,
        ):
            start, arrange_support = reader._reconcile(solver, room, active, [active])
        rf.assert_not_called()
        ue.assert_not_called()
        nb.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        self.assertEqual(solver.tasks, [], "不可读不排重检，等排班自然重读")

    def test_training_skill_unreadable_panel_no_adoption(self):
        # B8：干员名可读且匹配、但技能名不可读 → 不采纳（不认不可读技能）、
        # 不判假记录（干员对得上）、不排重检
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", skill_name="")
        active = make_plan(status="training")
        with (
            patch.object(reader, "_reset_fake") as rf,
            patch.object(reader, "_update_expiry") as ue,
        ):
            start, arrange_support = reader._reconcile(solver, room, active, [active])
        rf.assert_not_called()
        ue.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        self.assertEqual(solver.tasks, [], "技能不可读不排重检")

    def test_training_unreadable_no_downgrade_waiting_collect(self):
        # B8：DB 计划 status=waiting_collect + 面板干员名不可读 → 不被无校验刷新降回
        # training（update_plan_status 不写）。若有人回退成「不可读=匹配」采纳，
        # 真实 _update_expiry 会调用 update_plan_status(id,'training',...) → 本测试失败。
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", operator_name="")
        active = make_plan(status="waiting_collect")
        with (
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(reader, "_reset_fake") as rf,
        ):
            start, arrange_support = reader._reconcile(solver, room, active, [active])
        rf.assert_not_called()
        upd.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)

    def test_training_unreadable_no_notify_blocked(self):
        # 干员名不可读时不判计划外训练，不通知①
        solver = MagicMock()
        room = make_room("training", operator_name="")
        with (
            patch.object(reader, "_notify_blocked") as nb,
        ):
            reader._reconcile(solver, room, None, [])
        nb.assert_not_called()

    def test_training_unreadable_blocked_no_recheck(self):
        # B8：无 active、无命中 + 干员名不可读 → 不判计划外、不排重检（排班自然重读）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", operator_name="")
        with (
            patch.object(reader, "_notify_blocked") as nb,
        ):
            start, arrange_support = reader._reconcile(solver, room, None, [])
        nb.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        self.assertEqual(solver.tasks, [], "干员名不可读不排重检")

    def test_training_idle_hit_recovers(self):
        # #98：idle×🔴 命中 + 恢复门通过（面板干员可读 + 技能被解析器无歧义命中计划技能
        # + 倒计时 active）→ 恢复 training（截图为准），进入正常 active×训练中管理。
        solver = MagicMock()
        room = make_room("training")
        idle_plan = make_plan()
        with (
            patch.object(reader, "_can_recover_plan", return_value=True),
            patch.object(reader, "_recover_to_training") as rt,
            patch.object(reader, "_refresh_training_plan") as rf,
        ):
            reader._reconcile(solver, room, None, [idle_plan])
        rt.assert_called_once_with(solver, idle_plan, room)
        rf.assert_called_once_with(solver, idle_plan, room)

    def test_training_idle_hit_ambiguous_skill_rechecks(self):
        # #98 收紧门：idle×🔴 命中但技能含混（解析器无歧义命中失败）→ 不恢复（避免把
        # 同干员另一技能的计划误接管），技能可读时保留原重检（练完由 dispatch/gate 收）。
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training")  # 技能可读但含混
        idle_plan = make_plan()
        with (
            patch.object(reader, "_can_recover_plan", return_value=False),
            patch.object(reader, "_recover_to_training") as rt,
            patch.object(reader, "_wait_for_training") as wt,
        ):
            start, arrange_support = reader._reconcile(solver, room, None, [idle_plan])
        rt.assert_not_called()
        wt.assert_called_once_with(solver, room)
        self.assertIsNone(start)
        self.assertTrue(arrange_support)

    def test_training_idle_hit_skill_unreadable_no_recover(self):
        # #98/B8：idle×🔴 命中但技能不可读 → 不恢复、不重检（排班下次自然进房重读）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", skill_name="")
        idle_plan = make_plan()
        with (
            patch.object(reader, "_recover_to_training") as rt,
            patch.object(reader, "_wait_for_training") as wt,
        ):
            start, arrange_support = reader._reconcile(solver, room, None, [idle_plan])
        rt.assert_not_called()
        wt.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        self.assertEqual(solver.tasks, [], "技能不可读不排重检")

    # --- #98 failed/idle 截图为准恢复 training ---

    def test_training_failed_hit_recovers(self):
        # failed×🔴 命中 + 恢复门通过 → 恢复 training（截图为准），撤销 false-failure
        solver = MagicMock()
        room = make_room("training")
        failed_plan = make_plan(status="failed")
        with (
            patch.object(reader, "_can_recover_plan", return_value=True),
            patch.object(reader, "_recover_to_training") as rt,
            patch.object(reader, "_refresh_training_plan") as rf,
        ):
            reader._reconcile(solver, room, None, [failed_plan])
        rt.assert_called_once_with(solver, failed_plan, room)
        rf.assert_called_once_with(solver, failed_plan, room)

    def test_training_failed_hit_skill_unreadable_no_recover(self):
        # #98/B8：failed×🔴 命中但技能不可读 → 不恢复、不重检（静默等待）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", skill_name="")
        failed_plan = make_plan(status="failed")
        with patch.object(reader, "_recover_to_training") as rt:
            start, arrange_support = reader._reconcile(
                solver, room, None, [failed_plan]
            )
        rt.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        self.assertEqual(solver.tasks, [], "技能不可读不排重检")

    def test_training_failed_hit_not_blocked(self):
        # 恢复后不再走计划外 blocked（hit 命中 → 不通知①、不排占用重检）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training")
        failed_plan = make_plan(status="failed")
        with (
            patch.object(reader, "_can_recover_plan", return_value=True),
            patch.object(reader, "_recover_to_training"),
            patch.object(reader, "_refresh_training_plan"),
            patch.object(reader, "_notify_blocked") as nb,
        ):
            reader._reconcile(solver, room, None, [failed_plan])
        nb.assert_not_called()
        self.assertEqual(solver.tasks, [], "恢复管理不排占用重检")

    def test_waiting_collect_failed_not_collected(self):
        # #98：failed 计划待收取不接管（避免无材料强开下一级）→ 静默收取，不按计划记账；
        # 干员在 failed 计划里，「不在专精计划中」的帮收通知误导 → 抑制④。
        solver = MagicMock()
        room = make_room("waiting_collect")
        failed_plan = make_plan(status="failed")
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_collect_silent") as cs,
        ):
            reader._reconcile(solver, room, None, [failed_plan])
        cp.assert_not_called()
        cs.assert_called_once_with(solver, room, suppress_help=True)

    def test_recover_to_training_writes_status_expiry_clears_reason(self):
        # #98 恢复：同一 update_plan_status 写 training + expires_at + swap_frozen=0 + 清
        # failed_reason；本地 plan dict 同步更新（供 _refresh_training_plan 继续使用）
        solver = MagicMock()
        room = make_room("training")
        countdown = room.panel.countdown
        plan = make_plan(status="failed", failed_reason="材料不足", swap_frozen=1)
        with patch("arknights_mower.utils.mastery_db.update_plan_status") as upd:
            reader._recover_to_training(solver, plan, room)
        expires_at = countdown.strftime("%Y-%m-%d %H:%M:%S")
        upd.assert_called_once_with(
            1, "training", expires_at=expires_at, swap_frozen=0, failed_reason=""
        )
        self.assertEqual(plan["status"], "training")
        self.assertEqual(plan["swap_frozen"], 0)
        self.assertIsNone(plan["failed_reason"])
        self.assertEqual(plan["expires_at"], expires_at)

    def test_training_hit_plan_updates_expiry(self):
        # 无 active、但另一条 training 状态计划命中（面板可读且匹配）→ 采纳倒计时。
        # 正控制：B8 只挡「不可读」，可读匹配的正常刷新必须保留。
        solver = MagicMock()
        room = make_room("training")
        plan = make_plan(status="training")
        with patch.object(reader, "_update_expiry") as ue:
            reader._reconcile(solver, room, None, [plan])
        ue.assert_called_once_with(solver, plan, room)

    def test_training_hit_skill_unreadable_no_adoption(self):
        # B8：hit 命中（干员可读且匹配）但技能不可读 → 不采纳、不判计划外（不发①）、
        # 不排重检——_match_plan 把技能不可读当匹配，采纳门把它挡掉
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training", skill_name="")
        plan = make_plan(status="training")
        with (
            patch.object(reader, "_update_expiry") as ue,
            patch.object(reader, "_notify_blocked") as nb,
        ):
            start, arrange_support = reader._reconcile(solver, room, None, [plan])
        ue.assert_not_called()
        nb.assert_not_called()
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        self.assertEqual(solver.tasks, [], "技能不可读不排重检")

    def test_training_unmatched_notifies_blocked(self):
        solver = MagicMock()
        room = make_room("training", operator_name="路人")
        with (
            patch.object(reader, "_notify_blocked") as nb,
            patch.object(reader, "_wait_for_training"),
        ):
            reader._reconcile(solver, room, None, [])
        nb.assert_called_once_with(solver, room)

    def test_training_unmatched_schedules_one_future_recheck(self):
        # #66/B1：计划外占用（无 active、无匹配计划）→ 通知① + 排一条未来重检
        # （倒计时结束 + 2min）。队列不空则重启恢复 keepalive 不再每轮补 now-task，
        # 死循环（每 ~4s 进出训练室）从根上消失。
        solver = MagicMock()
        solver.tasks = []
        countdown = datetime.now() + timedelta(hours=2)
        room = make_room("training", operator_name="路人", countdown=countdown)
        with patch.object(reader, "_notify_blocked") as nb:
            start, _ = reader._reconcile(solver, room, None, [])
        nb.assert_called_once_with(solver, room)
        self.assertIsNone(start)
        self.assertEqual(len(solver.tasks), 1)
        task = solver.tasks[0]
        self.assertEqual(task.type, reader.TaskTypes.SKILL_UPGRADE)
        self.assertEqual(task.time, countdown + reader.ARRANGING_RETRY_BUFFER)

    def test_training_unmatched_recheck_converges_over_cycles(self):
        # #66/B1 收敛：多轮 dispatch 循环不新增重检任务——占用未变（倒计时结束时间
        # 不变）时每次改期同一条未来重检，队列恒 ≤1 条 SKILL_UPGRADE。
        solver = MagicMock()
        countdown = datetime.now() + timedelta(hours=2)
        room = make_room("training", operator_name="路人", countdown=countdown)
        with patch.object(reader, "_notify_blocked"):
            # 第一轮：dispatch 的 now-task 正在执行（solver.task），重检入队
            now_task = reader.SchedulerTask(
                time=datetime.now(), task_type=reader.TaskTypes.SKILL_UPGRADE
            )
            solver.tasks = [now_task]
            solver.task = now_task
            reader._reconcile(solver, room, None, [])
            solver.tasks.remove(now_task)  # dispatch 完成删除当前任务
            solver.task = None
            self.assertEqual(len(solver.tasks), 1)
            # 第二轮：未来重检到点 dispatch → 占用未变 → 改期同一条，不新增
            solver.task = solver.tasks[0]
            reader._reconcile(solver, room, None, [])
            solver.tasks.remove(solver.task)
            solver.task = None
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(
            solver.tasks[0].time, countdown + reader.ARRANGING_RETRY_BUFFER
        )

    def test_waiting_collect_matched_collects(self):
        solver = MagicMock()
        room = make_room("waiting_collect")
        plan = make_plan()
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_promote_plan"),
        ):
            reader._reconcile(solver, room, None, [plan])
        cp.assert_called_once()

    def test_waiting_collect_unmatched_silent(self):
        solver = MagicMock()
        room = make_room("waiting_collect", operator_name="路人")
        with (
            patch.object(reader, "_collect_silent") as cs,
            patch.object(reader, "_collect_plan"),
        ):
            reader._reconcile(solver, room, None, [])
        cs.assert_called_once()

    def test_collect_continue_returns_arrange_support(self):
        # 继续本级（#74 第3段「都去掉」后一律当场开）→ 返回计划 + arrange_support=True
        # （2026-08-17 用户拍板：收取→开下一级边界也照常安排路线 operator）
        solver = MagicMock()
        room = make_room("waiting_collect")
        plan = make_plan()
        with patch.object(reader, "_collect_plan", return_value=make_plan()):
            start, arrange_support = reader._reconcile(solver, room, None, [plan])
        self.assertIsNotNone(start)
        self.assertTrue(arrange_support)


class TestReconcile73(unittest.TestCase):
    """#73 状态矩阵对账：待收取 7 格动作（§16.3）/ 保护检查（§16.4-16.5）/ 恢复流程（§16.6）。"""

    # --- §16.3 待收取 7 格：图标 × 协助位 × 计划 ---

    def test_waiting_collect_m3_unmatched_silent(self):
        # 专三 + 无计划 → 正常收取，不通知④（③ 需计划；无计划专三静默）
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=3, operator_name="路人")
        with (
            patch.object(reader, "_notify_help_collect") as nh,
            patch.object(reader, "_collect_plan") as cp,
        ):
            start, _ = reader._reconcile(solver, room, None, [])
        nh.assert_not_called()
        cp.assert_not_called()
        self.assertIsNone(start)

    def test_waiting_collect_m3_matched_no_cascade(self):
        # 专三 + 都在计划 → 正常收取对账（收取完成不级联，#74 第2段；plan=None 无开始，
        # arrange_support 恒 True 但未消费）
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=3)
        plan = make_plan(target_level=3)
        with patch.object(reader, "_collect_plan", return_value=None) as cp:
            start, arrange_support = reader._reconcile(solver, room, None, [plan])
        cp.assert_called_once()
        self.assertTrue(arrange_support)
        self.assertIsNone(start, "收取完成不级联开始下一个计划")

    def test_waiting_collect_below_m3_unmatched_help_collect(self):
        # 非专三 + 不在计划 → 收取 + 通知④帮收
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=2, operator_name="路人")
        with (
            patch.object(reader, "_notify_help_collect") as nh,
            patch.object(reader, "_collect_plan") as cp,
        ):
            reader._reconcile(solver, room, None, [])
        nh.assert_called_once_with(solver, room)
        cp.assert_not_called()

    def test_waiting_collect_below_m3_matched_recovers_and_promotes(self):
        # 非专三 + 都在计划 → 恢复流程（§16.6）：收取 + 优先级排前 + 继续本级当场开
        # （#74 第3段「都去掉」后一律当场开，不分扫描链/重启；路线 operator 照常安排）
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=2)
        plan = make_plan(target_level=3)
        with (
            patch.object(reader, "_collect_plan", return_value=make_plan()) as cp,
            patch.object(reader, "_promote_plan") as pp,
        ):
            start, arrange_support = reader._reconcile(solver, room, None, [plan])
        cp.assert_called_once()
        pp.assert_called_once()
        self.assertTrue(arrange_support)
        self.assertIsNotNone(start)

    def test_waiting_collect_m3_completed_does_not_promote(self):
        # 专三完成（_collect_plan 返回 None，不级联）→ 不排前
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=3)
        plan = make_plan(target_level=3)
        with (
            patch.object(reader, "_collect_plan", return_value=None),
            patch.object(reader, "_promote_plan") as pp,
        ):
            reader._reconcile(solver, room, None, [plan])
        pp.assert_not_called()

    def test_waiting_collect_operator_only_partial_still_help_collect(self):
        # 干员在计划、技能不在 → 也走帮收④（§16.3 干员在、技能不在格）
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=2, skill_name="别的技能")
        plan = make_plan()  # 干员匹配但技能不匹配
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_notify_help_collect") as nh,
        ):
            reader._reconcile(solver, room, None, [plan])
        cp.assert_not_called()
        nh.assert_called_once_with(solver, room)

    def test_waiting_collect_unreadable_panel_still_reconciles_active(self):
        # 面板 OCR 不可读（operator=""）：_match_plan 判不了命中，但 active 计划
        # 视为匹配（稳为先），照常对账收取——不得退化成帮收④ 或丢掉对账
        solver = MagicMock()
        room = make_room("waiting_collect", mastery_tier=2, operator_name="")
        active = make_plan(status="training")
        with (
            patch.object(reader, "_collect_plan") as cp,
            patch.object(reader, "_collect_silent") as cs,
            patch.object(reader, "_notify_help_collect") as nh,
        ):
            reader._reconcile(solver, room, active, [active])
        cp.assert_called_once()
        cs.assert_not_called()
        nh.assert_not_called()

    # --- §16.4/§16.5 保护检查 ---

    def test_protected_empty_with_idle_plan_notifies_and_holds(self):
        # 空闲 + 受保护 + 有待开始计划 → mower 不能开始：⑤ + 保持 idle，不主动轮询
        # （保护解除靠「排班进训练室重读重判」，§16.5）
        solver = MagicMock()
        solver.tasks = []
        room = make_room("empty", support_slot="逻各斯", train_slot="能天使")
        room.protected = True
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan",
                return_value=make_plan(),
            ),
            patch.object(reader, "_notify_protected") as np_,
        ):
            start, _ = reader._reconcile(solver, room, None, [make_plan()])
        self.assertIsNone(start, "受保护时空闲房间不得开始训练")
        np_.assert_called_once_with(solver, room)
        self.assertEqual(solver.tasks, [], "受保护不主动轮询重试，等排班自然进房重判")

    def test_protected_empty_no_idle_plan_no_notify_no_poll(self):
        # 受保护但没有待开始计划 → 不通知⑤、不轮询
        solver = MagicMock()
        solver.tasks = []
        room = make_room("empty", support_slot="逻各斯", train_slot="能天使")
        room.protected = True
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan", return_value=None
            ),
            patch.object(reader, "_notify_protected") as np_,
        ):
            reader._reconcile(solver, room, None, [])
        np_.assert_not_called()
        self.assertEqual(solver.tasks, [])

    def test_empty_not_protected_no_start(self):
        # #74 第2段：空闲未受保护 → 交还排班，不返回开始计划
        solver = MagicMock()
        room = make_room("empty")
        with patch(
            "arknights_mower.utils.mastery_db.get_next_idle_plan",
            return_value=make_plan(),
        ) as g:
            start, arrange_support = reader._reconcile(solver, room, None, [])
        g.assert_not_called()
        self.assertIsNone(start, "空闲未受保护不再直开，交还排班")
        self.assertTrue(arrange_support)

    def test_ocr_fail_conservative_no_recheck(self):
        # 用户 08-15 定案：读不出（5 次重试仍不一致）→ 保守训练中，不排重检，
        # 静默等排班系统下次自然进房重读
        solver = MagicMock()
        solver.tasks = []
        room = make_room("training")
        room.read_failed = True
        with patch.object(reader, "_collect_silent") as cs:
            start, arrange_support = reader._reconcile(solver, room, None, [])
        self.assertIsNone(start)
        self.assertTrue(arrange_support)
        cs.assert_not_called()
        self.assertEqual(solver.tasks, [], "读失败不排重检")


class TestComputeProtected(unittest.TestCase):
    """§16.5 保护检查（现读现判）：逻各斯/艾丽妮 + 待收取/空闲的判定。"""

    def _room(self, state, support, train, tier):
        return reader.RoomState(
            state=state,
            panel=make_panel(mastery_tier=tier),
            support_slot=support,
            train_slot=train,
        )

    def test_waiting_collect_m3_not_protected(self):
        # §16.3 第1格：专三完成 → 无论如何不保护 → 可排班
        with patch.object(reader.config.conf, "enable_mastery", True):
            room = self._room("waiting_collect", "逻各斯", "", 3)
            self.assertFalse(reader._compute_protected(MagicMock(), room))

    def test_waiting_collect_below_m3_protected(self):
        # 非专三（链未走完）+ 逻各斯/艾丽妮 → 保护
        with patch.object(reader.config.conf, "enable_mastery", True):
            room = self._room("waiting_collect", "艾丽妮", "", 2)
            self.assertTrue(reader._compute_protected(MagicMock(), room))

    def test_empty_with_occupant_deep_read(self):
        # 空闲 + 逻各斯 + 训练位有人 → 深读技能页（有专一/专二 → 保护）
        with (
            patch.object(reader.config.conf, "enable_mastery", True),
            patch.object(reader, "_train_slot_has_mastery", return_value=True),
        ):
            room = self._room("empty", "逻各斯", "能天使", 0)
            self.assertTrue(reader._compute_protected(MagicMock(), room))
        with (
            patch.object(reader.config.conf, "enable_mastery", True),
            patch.object(reader, "_train_slot_has_mastery", return_value=False),
        ):
            room = self._room("empty", "逻各斯", "能天使", 0)
            self.assertFalse(reader._compute_protected(MagicMock(), room))

    def test_empty_no_train_slot_not_protected(self):
        # 空闲 + 逻各斯 + 训练位没人 → 可排班
        with patch.object(reader.config.conf, "enable_mastery", True):
            room = self._room("empty", "逻各斯", "", 0)
            self.assertFalse(reader._compute_protected(MagicMock(), room))

    def test_off_no_protection(self):
        # §16.11 OFF：保护全停
        with patch.object(reader.config.conf, "enable_mastery", False):
            room = self._room("waiting_collect", "逻各斯", "", 2)
            self.assertFalse(reader._compute_protected(MagicMock(), room))


class TestPromotePlan(unittest.TestCase):
    """§16.6 恢复流程插队：已最前不动；未最前插到最前、原最前计划后移一位。"""

    def test_already_front_no_change(self):
        solver = MagicMock()
        plan = make_plan(priority=0)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[make_plan(priority=0), make_plan(id=2, priority=3)],
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_priority") as upd,
        ):
            reader._promote_plan(solver, plan)
        upd.assert_not_called()

    def test_insert_front_bumps_existing_front(self):
        solver = MagicMock()
        plan = make_plan(priority=3)  # 非最前
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[make_plan(id=2, priority=0), make_plan(id=3, priority=1)],
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_priority") as upd,
        ):
            reader._promote_plan(solver, plan)
        calls = [(c.args[0], c.args[1]) for c in upd.call_args_list]
        self.assertIn((1, 0), calls, "本计划应插到最前（优先级 0）")
        self.assertIn((2, 1), calls, "原最前计划(id=2, priority=0) 应后移到 1")
        self.assertNotIn((3, 2), calls, "priority=1 的计划不受影响")


class TestReconcileAndAct(unittest.TestCase):
    """reconcile_and_act：读房 → 矩阵对账 → 原样透传开始计划（无材料门控）。"""

    def _solver(self):
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.back = MagicMock()
        return solver

    def _enable(self):
        # 测试环境配置 enable_mastery=False（用户本地配置），这里显式开启
        return patch.object(reader.config.conf, "enable_mastery", True)

    def test_returns_reconcile_plan_unchanged(self):
        solver = self._solver()
        plan = make_plan()
        room = make_room("empty")
        with (
            self._enable(),
            patch.object(reader, "read_room_state", return_value=room),
            patch.object(reader, "_reconcile", return_value=(plan, True)),
        ):
            result, arrange_support, returned_room = reader.reconcile_and_act(solver)
        self.assertIs(result, plan, "对账返回的开始计划应原样透传给 dispatch 开始")
        self.assertTrue(arrange_support)
        self.assertIs(
            returned_room, room, "#93：已读房间状态应原样透传，供开始流程复用"
        )
        solver.back.assert_not_called()

    def test_passes_scan_plan_to_reconcile(self):
        # #74 第3段：扫描驱动 dispatch 把指定计划透传给 _reconcile（空闲格只开始它）
        solver = self._solver()
        scan_plan = make_plan()
        room = make_room("empty")
        with (
            self._enable(),
            patch.object(reader, "read_room_state", return_value=room),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
            patch("arknights_mower.utils.mastery_db.get_reconcile_plans", return_value=[]),
            patch.object(reader, "_reconcile", return_value=(scan_plan, True)) as rec,
        ):
            result, arrange_support, returned_room = reader.reconcile_and_act(
                solver, scan_plan=scan_plan
            )
        rec.assert_called_once_with(solver, room, None, [], scan_plan=scan_plan)
        self.assertIs(result, scan_plan)
        self.assertIs(returned_room, room)


class TestCollectFlow(unittest.TestCase):
    def _solver(self, tier_img=None):
        solver = MagicMock()
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.recog.update = MagicMock()
        solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # find 默认返回 None → 走兜底坐标；training_completed 也 None
        solver.find.return_value = None
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        return solver

    def test_collect_flow_sends_no_mail_below_m3(self):
        solver = self._solver()
        panel = make_panel(mastery_tier=2)
        with (
            patch("arknights_mower.utils.email.send_message") as send,
            patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        ):
            reader.collect_flow(solver, make_plan(), panel)
        send.assert_not_called()

    def test_collect_flow_sends_mail_at_m3(self):
        solver = self._solver()
        panel = make_panel(mastery_tier=3)
        with (
            patch("arknights_mower.utils.email.send_message") as send,
            patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        ):
            reader.collect_flow(solver, make_plan(), panel)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["level"], "INFO")
        self.assertIsNotNone(send.call_args.kwargs["attach_image"])

    def test_collect_flow_m3_dedup(self):
        solver = self._solver()
        panel = make_panel(mastery_tier=3)
        with (
            patch("arknights_mower.utils.email.send_message") as send,
            patch("arknights_mower.utils.mastery_db.should_notify", return_value=False),
        ):
            reader.collect_flow(solver, make_plan(), panel)
        send.assert_not_called()

    def test_collect_flow_taps_finish_mark_fallback(self):
        solver = self._solver()
        with (
            patch("arknights_mower.utils.email.send_message"),
            patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        ):
            reader.collect_flow(solver, make_plan(), make_panel())
        taps = [c.args[0] for c in solver.tap.call_args_list]
        self.assertIn((solver.recog.w * 0.05, solver.recog.h * 0.95), taps)
        self.assertIn((solver.recog.w * 0.5, solver.recog.h * 0.5), taps)
        # #61 流程第 8 步：点勾确认（confirm_train 模板或兜底坐标）
        self.assertIn((solver.recog.w * 0.5, solver.recog.h * 0.85), taps)

    def test_collect_flow_prefers_template(self):
        solver = self._solver()
        finish_pos = ((50, 900), (130, 980))
        solver.find.side_effect = lambda res, *a, **k: (
            finish_pos if res == "skill_collect_confirm" else None
        )
        with (
            patch("arknights_mower.utils.email.send_message"),
            patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        ):
            reader.collect_flow(solver, make_plan(), make_panel())
        self.assertIn(finish_pos, [c.args[0] for c in solver.tap.call_args_list])


class TestReconcileAfterCollect(unittest.TestCase):
    def test_meets_target_completes_no_cascade(self):
        # #74 第2段：收取到目标 → completed，但不再级联开始下一个计划（等扫描）
        panel = make_panel(mastery_tier=3)
        plan = make_plan(target_level=3)
        with (
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.mastery_db.get_next_idle_plan") as g,
        ):
            result = reader._reconcile_after_collect(MagicMock(), plan, panel)
        upd.assert_called_once_with(1, "completed")
        g.assert_not_called()
        self.assertIsNone(result, "收取到目标后不再级联开始下一个计划")

    def test_below_target_continues_same_plan(self):
        panel = make_panel(mastery_tier=2)
        plan = make_plan(target_level=3)
        with (
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.mastery_db.get_next_idle_plan"),
        ):
            result = reader._reconcile_after_collect(MagicMock(), plan, panel)
        upd.assert_called_once_with(1, "idle")
        self.assertIs(result, plan)

    def test_above_target_collect_not_completed(self):
        # #67/B6：专二收取关掉专一计划 → 不得完成（档位高于目标时本次收取不属于该计划）
        panel = make_panel(mastery_tier=2)
        plan = make_plan(target_level=1)
        with (
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.mastery_db.get_next_idle_plan"),
        ):
            result = reader._reconcile_after_collect(MagicMock(), plan, panel)
        statuses = [c.args[1] for c in upd.call_args_list]
        self.assertNotIn("completed", statuses, "高于目标的收取不得把计划标记完成")
        upd.assert_called_once_with(1, "idle")
        self.assertIs(result, plan)

    def test_no_plan_returns_none(self):
        self.assertIsNone(
            reader._reconcile_after_collect(MagicMock(), None, make_panel())
        )


class TestGetTrainSceneFloatingWindow(unittest.TestCase):
    """#78 浮窗识别盲区：get_train_scene 识别 room_detail → 205，且不误用 arrange_check_in。

    浮窗开着时 room_detail（浮窗头）须在 train_main/training_support 之前判 205，
    否则浮窗被误标 217/219、_read_slots 关浮窗死代码永不触发。
    """

    def _recog(self, find_hits):
        """构造 Recognizer，find 按资源名命中返回真值、未命中返回 None。"""
        from arknights_mower.utils.recognize import Recognizer

        rec = Recognizer(MagicMock())
        rec.find = MagicMock(
            side_effect=lambda res, *a, **k: object() if res in find_hits else None
        )
        return rec

    def test_room_detail_open_returns_205(self):
        rec = self._recog({"room_detail", "train_main"})
        self.assertEqual(rec.get_train_scene(), Scene.INFRA_DETAILS)

    def test_room_detail_closed_returns_217(self):
        rec = self._recog({"train_main"})
        self.assertEqual(rec.get_train_scene(), Scene.TRAIN_MAIN)

    def test_room_detail_closed_returns_219(self):
        # 技能选择页（training_support 命中）也要正常识别
        rec = self._recog({"training_support"})
        self.assertEqual(rec.get_train_scene(), Scene.TRAIN_SKILL_SELECT)

    def test_arrange_check_in_alone_not_205(self):
        # 裸主页面也有 arrange_check_in——不得用当浮窗探针，否则恒 205、217 永远不出来
        rec = self._recog({"arrange_check_in", "train_main"})
        self.assertEqual(rec.get_train_scene(), Scene.TRAIN_MAIN)


class TestReadSlotsCloseFloatingWindow(unittest.TestCase):
    """#78 复活 _read_slots 的关浮窗死代码：读完进驻详情后浮窗必须确定关掉，无二次 back。"""

    def test_closes_floating_window_after_read(self):
        solver = MagicMock()
        solver.get_agent_from_room.return_value = [
            {"agent": "逻各斯"},
            {"agent": "能天使"},
        ]
        solver.train_scene.return_value = Scene.INFRA_DETAILS
        support, train = reader._read_slots(solver)
        self.assertEqual((support, train), ("逻各斯", "能天使"))
        # 205 放大视角关浮窗应点关闭按钮（arrange_check_in_on），不是 back（会退到基建）
        solver.find.assert_any_call("arrange_check_in_on")
        solver.tap.assert_called()
        solver.back.assert_not_called()

    def test_no_double_back_when_window_closed(self):
        solver = MagicMock()
        solver.get_agent_from_room.return_value = [
            {"agent": "逻各斯"},
            {"agent": "能天使"},
        ]
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        reader._read_slots(solver)
        solver.back.assert_not_called()
        solver.tap.assert_not_called()

    def test_read_failure_returns_empty_no_back(self):
        solver = MagicMock()
        solver.get_agent_from_room.side_effect = Exception("read fail")
        self.assertEqual(reader._read_slots(solver), ("", ""))
        solver.back.assert_not_called()


class TestUpdateExpirySkipWrite(unittest.TestCase):
    """#82：_update_expiry 只写 expires_at（拆出排收取），倒计时未变时跳过 DB 写。"""

    def _plan(self, expires_at):
        return make_plan(status="training", expires_at=expires_at)

    def _room(self, countdown):
        return reader.RoomState(
            state="training",
            panel=make_panel(countdown=countdown, countdown_state="active"),
        )

    def test_same_expires_at_skips_write(self):
        solver = MagicMock()
        countdown = datetime.now() + timedelta(hours=2)
        plan = self._plan(countdown.strftime("%Y-%m-%d %H:%M:%S"))
        with patch("arknights_mower.utils.mastery_db.update_plan_status") as upd:
            reader._update_expiry(solver, plan, self._room(countdown))
        upd.assert_not_called()

    def test_changed_expires_at_writes(self):
        solver = MagicMock()
        countdown = datetime.now() + timedelta(hours=2)
        plan = self._plan("2000-01-01 00:00:00")
        with patch("arknights_mower.utils.mastery_db.update_plan_status") as upd:
            reader._update_expiry(solver, plan, self._room(countdown))
        upd.assert_called_once_with(
            1, "training", expires_at=countdown.strftime("%Y-%m-%d %H:%M:%S")
        )

    def test_countdown_missing_no_write(self):
        solver = MagicMock()
        plan = self._plan(None)
        room = self._room(None)
        room.panel.countdown_state = "failed"
        with patch("arknights_mower.utils.mastery_db.update_plan_status") as upd:
            reader._update_expiry(solver, plan, room)
        upd.assert_not_called()


class TestRefreshTrainingHalfOverlap(unittest.TestCase):
    """#82：半重叠消除——先换人判定，排了换人就不排收取；没排换人才排收取（§16.10）。"""

    def setUp(self):
        self.patch_follows = patch.object(
            reader.config.conf, "assistant_follows_schedule", False
        )
        self.patch_enable = patch.object(reader.config.conf, "enable_mastery", True)
        self.patch_follows.start()
        self.patch_enable.start()
        self.addCleanup(self.patch_follows.stop)
        self.addCleanup(self.patch_enable.stop)

    def _room(self):
        return reader.RoomState(
            state="training",
            panel=make_panel(
                mastery_tier=2,
                countdown=datetime.now() + timedelta(hours=6),
                countdown_state="active",
            ),
        )

    def test_no_swap_schedules_collect(self):
        solver = MagicMock()
        solver.tasks = []
        plan = make_plan(status="training", swap_frozen=0)
        with (
            patch.object(reader, "_update_expiry"),
            patch.object(reader, "_maybe_recover_swap", return_value=False),
            patch.object(reader, "_schedule_collect") as sc,
        ):
            reader._refresh_training_plan(solver, plan, self._room())
        sc.assert_called_once()

    def test_swap_scheduled_skips_collect(self):
        solver = MagicMock()
        solver.tasks = []
        plan = make_plan(status="training", swap_frozen=0)
        with (
            patch.object(reader, "_update_expiry"),
            patch.object(reader, "_maybe_recover_swap", return_value=True),
            patch.object(reader, "_schedule_collect") as sc,
        ):
            reader._refresh_training_plan(solver, plan, self._room())
        sc.assert_not_called()

    def test_queued_swap_task_skips_collect(self):
        # 队列已有同计划 SWAP 任务 → _maybe_recover_swap 返回 True（不重复排）→ 不排收取
        solver = MagicMock()
        task = reader.SchedulerTask(
            time=datetime.now(), task_type=reader.TaskTypes.SWAP_SUPPORT
        )
        task.plan_key = "1"
        solver.tasks = [task]
        plan = make_plan(status="training", swap_frozen=0)
        with (
            patch.object(reader, "_update_expiry"),
            patch.object(reader, "_maybe_recover_swap", return_value=True),
            patch.object(reader, "_schedule_collect") as sc,
        ):
            reader._refresh_training_plan(solver, plan, self._room())
        sc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
