import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from arknights_mower.solvers import navigation as nav_module
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.utils import nav_steps as ns


def _entry(success: bool, steps=None):
    return {
        "updated_at": "t",
        "stage_type": "ACTIVITY",
        "success": success,
        "steps": steps or [{"action": "x"}],
    }


class TestEmptyNavSteps(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(
            ns.empty_nav_steps(), {"version": 1, "stages": {}, "patterns": {}}
        )

    def test_no_shared_mutable(self):
        a = ns.empty_nav_steps()
        a["stages"]["S"] = {}
        self.assertEqual(ns.empty_nav_steps()["stages"], {})


class TestLoadNavFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_missing_returns_empty(self):
        self.assertEqual(
            ns.load_nav_file(self.dir / "missing.json"), ns.empty_nav_steps()
        )

    def test_corrupt_returns_empty(self):
        p = self.dir / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        self.assertEqual(ns.load_nav_file(p), ns.empty_nav_steps())

    def test_malformed_shape_returns_empty(self):
        p = self.dir / "list.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        self.assertEqual(ns.load_nav_file(p), ns.empty_nav_steps())

    def test_missing_stages_patterns_normalized(self):
        p = self.dir / "partial.json"
        p.write_text(json.dumps({"version": 1}), encoding="utf-8")
        got = ns.load_nav_file(p)
        self.assertEqual(got["stages"], {})
        self.assertEqual(got["patterns"], {})

    def test_valid_roundtrip(self):
        p = self.dir / "ok.json"
        payload = {"version": 1, "stages": {"PA-1": _entry(True)}, "patterns": {}}
        p.write_text(json.dumps(payload), encoding="utf-8")
        got = ns.load_nav_file(p)
        self.assertEqual(got["stages"]["PA-1"]["success"], True)


class TestMergeNavSteps(unittest.TestCase):
    """官方打底 + 本机优先：用户已学会(success=true)条目不被官方覆盖，官方只补缺。"""

    def test_both_empty(self):
        got = ns.merge_nav_steps({}, {})
        self.assertEqual(got, {"version": 1, "stages": {}, "patterns": {}})

    def test_official_only(self):
        official = {"stages": {"PA-1": _entry(True, [{"action": "tap"}])}}
        got = ns.merge_nav_steps(official, {})
        self.assertEqual(got["stages"]["PA-1"]["steps"], [{"action": "tap"}])

    def test_user_learned_wins_over_official(self):
        official = {"stages": {"PA-1": _entry(True, [{"action": "tap", "src": "off"}])}}
        user = {"stages": {"PA-1": _entry(True, [{"action": "swipe", "src": "usr"}])}}
        got = ns.merge_nav_steps(official, user)
        self.assertEqual(
            got["stages"]["PA-1"]["steps"], [{"action": "swipe", "src": "usr"}]
        )

    def test_official_fills_gap(self):
        official = {"stages": {"PA-1": _entry(True)}}
        user = {"stages": {"PA-2": _entry(True)}}
        got = ns.merge_nav_steps(official, user)
        self.assertIn("PA-1", got["stages"])
        self.assertIn("PA-2", got["stages"])

    def test_user_non_learned_does_not_shadow_official_success(self):
        official = {"stages": {"PA-3": _entry(True, [{"action": "tap"}])}}
        user = {"stages": {"PA-3": _entry(False, [{"action": "swipe"}])}}
        got = ns.merge_nav_steps(official, user)
        self.assertEqual(got["stages"]["PA-3"]["steps"], [{"action": "tap"}])

    def test_user_learned_but_empty_steps_does_not_shadow_official(self):
        # 用户 success=true 但步骤为空 -> 不该盖掉官方有步骤的（官方补缺）
        official = {"stages": {"PA-5": _entry(True, [{"action": "tap"}])}}
        user = {
            "stages": {
                "PA-5": {
                    "updated_at": "t",
                    "stage_type": "ACTIVITY",
                    "success": True,
                    "steps": [],
                }
            }
        }
        got = ns.merge_nav_steps(official, user)
        self.assertEqual(got["stages"]["PA-5"]["steps"], [{"action": "tap"}])

    def test_user_non_learned_preserved_when_official_lacks(self):
        user = {"stages": {"PA-4": _entry(False)}}
        got = ns.merge_nav_steps({}, user)
        self.assertIn("PA-4", got["stages"])
        self.assertIs(got["stages"]["PA-4"]["success"], False)

    def test_separate_storage_no_overwrite_inputs(self):
        official = {"stages": {"PA-1": _entry(True)}}
        user = {"stages": {"PA-1": _entry(False)}}
        ns.merge_nav_steps(official, user)
        # 输入未被就地修改（分开存储、互不覆盖的底线断言）
        self.assertEqual(official["stages"]["PA-1"]["success"], True)
        self.assertEqual(user["stages"]["PA-1"]["success"], False)

    def test_patterns_merge(self):
        official = {"patterns": {"PA-*": _entry(True)}}
        user = {
            "patterns": {
                "PA-*": _entry(True, [{"action": "usr"}]),
                "TO-*": _entry(True),
            }
        }
        got = ns.merge_nav_steps(official, user)
        self.assertEqual(got["patterns"]["PA-*"]["steps"], [{"action": "usr"}])
        self.assertIn("TO-*", got["patterns"])

    def test_non_dict_entries_ignored(self):
        got = ns.merge_nav_steps({"stages": {"S": "nope"}}, {"stages": {"T": 3}})
        self.assertNotIn("S", got["stages"])
        self.assertNotIn("T", got["stages"])


class TestSelectReplaySteps(unittest.TestCase):
    """AI 兜底触发：合并视图里没有可回放的 success=true 步骤集就返回空。"""

    def _data(self, **kw):
        return {
            "version": 1,
            "stages": kw.get("stages", {}),
            "patterns": kw.get("patterns", {}),
        }

    def test_stage_success_returns_steps(self):
        data = self._data(stages={"PA-1": _entry(True, [{"action": "tap"}])})
        self.assertEqual(
            ns.select_replay_steps(data, "PA-1", None), [{"action": "tap"}]
        )

    def test_pattern_fallback(self):
        data = self._data(patterns={"PA-*": _entry(True, [{"action": "swipe"}])})
        self.assertEqual(
            ns.select_replay_steps(data, "PA-2", "PA-*"), [{"action": "swipe"}]
        )

    def test_exact_stage_precedes_pattern(self):
        data = self._data(
            stages={"PA-1": _entry(True, [{"action": "exact"}])},
            patterns={"PA-*": _entry(True, [{"action": "pattern"}])},
        )
        self.assertEqual(
            ns.select_replay_steps(data, "PA-1", "PA-*"), [{"action": "exact"}]
        )

    def test_nothing_learned_returns_empty_triggers_ai_fallback(self):
        data = self._data()
        self.assertEqual(ns.select_replay_steps(data, "PA-9", "PA-*"), [])

    def test_non_success_stage_ignored(self):
        data = self._data(stages={"PA-1": _entry(False, [{"action": "bad"}])})
        self.assertEqual(ns.select_replay_steps(data, "PA-1", None), [])


class TestSolverMergedWiring(unittest.TestCase):
    """solver 接线：内置官方步骤 + 本机步骤合并，persist 不吸收官方。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.data = self.dir / "data"
        self.data.mkdir()
        (self.data / "nav_trie_steps.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "stages": {"AP-1": _entry(True, [{"action": "usr"}])},
                    "patterns": {},
                }
            ),
            encoding="utf-8",
        )

    def _solver(self):
        return object.__new__(NavigationSolver)

    def _patch(self):
        stack = ExitStack()
        stack.enter_context(patch.object(nav_module, "__rootdir__", self.dir))
        return stack

    def test_official_uses_bundled(self):
        (self.data / "nav_steps.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "stages": {"AP-1": _entry(True, [{"action": "bundled"}])},
                    "patterns": {},
                }
            ),
            encoding="utf-8",
        )
        with self._patch():
            off = self._solver().load_official_nav_steps()
        self.assertEqual(off["stages"]["AP-1"]["steps"], [{"action": "bundled"}])

    def test_none_official_returns_empty(self):
        with self._patch():
            off = self._solver().load_official_nav_steps()
        self.assertEqual(off, ns.empty_nav_steps())

    def test_merged_user_wins_official_fills(self):
        (self.data / "nav_steps.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "stages": {
                        "AP-1": _entry(True, [{"action": "off"}]),
                        "AP-2": _entry(True, [{"action": "off2"}]),
                    },
                    "patterns": {},
                }
            ),
            encoding="utf-8",
        )
        with self._patch():
            merged = self._solver().load_merged_nav_steps()
        self.assertEqual(merged["stages"]["AP-1"]["steps"], [{"action": "usr"}])
        self.assertEqual(merged["stages"]["AP-2"]["steps"], [{"action": "off2"}])

    def test_persist_does_not_absorb_official(self):
        (self.data / "nav_steps.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "stages": {"OFF": _entry(True, [{"action": "x"}])},
                    "patterns": {},
                }
            ),
            encoding="utf-8",
        )
        with self._patch():
            solver = self._solver()
            solver.nav_route_success = True
            solver.name = "NEW"
            solver.stageType = "ACTIVITY"
            solver.nav_steps = [{"action": "tap"}]
            solver.persist_nav_steps()
        raw = json.loads(
            (self.data / "nav_trie_steps.json").read_text(encoding="utf-8")
        )
        self.assertIn("NEW", raw["stages"])
        self.assertNotIn("OFF", raw["stages"])


class TestStoryEntryExclusion(unittest.TestCase):
    """剧情入口按钮（"Story >>"）不是关卡入口，应从导航候选剔除。"""

    def test_story_button_excluded(self):
        for text in ["Story >>", "Story>>", "STORY >>", "剧情 >>", "剧情>>"]:
            self.assertTrue(
                nav_module._is_story_entry(text), f"should exclude: {text!r}"
            )

    def test_chapter_name_kept(self):
        # "Story Line · XX" 是章节名（不带 >>），不能误杀
        for text in ["Story Line · TS", "Story Line·LE", "Story", "剧情回顾"]:
            self.assertFalse(nav_module._is_story_entry(text), f"should keep: {text!r}")

    def test_other_entries_kept(self):
        for text in ["关卡 >>", "墟", "AT-8", "进入", "开放", ""]:
            self.assertFalse(nav_module._is_story_entry(text), f"should keep: {text!r}")

    def test_non_string_kept(self):
        self.assertFalse(nav_module._is_story_entry(None))
        self.assertFalse(nav_module._is_story_entry(123))


class TestReplaySteps(unittest.TestCase):
    """回放步骤时不会把旧路线再次写入自学数据。"""

    _ROUTE = [
        {"action": "tap", "payload": {"pos": [490, 1014], "text": "main_entry"}},
        {"action": "swipe", "payload": {"start": [960, 700], "vector": [0, -910]}},
    ]

    def _solver(self):
        s = object.__new__(NavigationSolver)
        s.name = "AT-8"
        s.nav_steps = []
        s._suppress_nav_recording = False
        return s

    def _patch(self, s, verify: callable = None, stage_code: bool = False):
        stack = ExitStack()
        stack.enter_context(patch.object(s, "back_to_terminal_main", return_value=True))
        stack.enter_context(
            patch.object(s, "get_replay_steps", return_value=self._ROUTE)
        )
        stack.enter_context(patch.object(s, "is_stage_code", return_value=stage_code))
        stack.enter_context(patch.object(s, "tap"))
        stack.enter_context(patch.object(s, "swipe_noinertia"))
        stack.enter_context(patch.object(s, "wait_for_scene_stable"))
        if verify is not None:
            stack.enter_context(
                patch.object(s, "find_target_stage_after_entry", side_effect=verify)
            )
        return stack

    def test_replay_does_not_capture_existing_route(self):
        s = self._solver()
        with self._patch(s):
            ok = s.try_replay_nav_steps()
        self.assertFalse(ok)
        self.assertEqual(s.nav_steps, [])

    def test_verify_suppresses_recording(self):
        # 验证阶段的定位滑动不该混入自学步骤。
        s = self._solver()
        observed = {}

        def _verify(*args, **kwargs):
            observed["suppress"] = s._suppress_nav_recording
            return False

        with self._patch(s, verify=_verify, stage_code=True):
            ok = s.try_replay_nav_steps()
        self.assertFalse(ok)
        self.assertTrue(observed["suppress"])
        self.assertEqual(s.nav_steps, [])


if __name__ == "__main__":
    unittest.main()
