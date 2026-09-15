import unittest

from arknights_mower.utils import nav_steps as ns


def _record(stage="PA-1", steps=None, **kw):
    return {
        "stage": stage,
        "stage_type": "ACTIVITY",
        "steps": steps if steps is not None else [{"action": "tap", "payload": {}}],
        "updated_at": "2026-08-22T12:00:00",
        **kw,
    }


class TestBuildOfficialSteps(unittest.TestCase):
    """官方层 nav_steps.json 的构建：格式与 persist_nav_steps 写的条目一致。"""

    def test_empty_records(self):
        got = ns.build_official_steps([])
        self.assertEqual(got, {"version": 1, "stages": {}, "patterns": {}})

    def test_single_stage_record(self):
        got = ns.build_official_steps([_record(stage="PA-1")])
        self.assertIn("PA-1", got["stages"])
        entry = got["stages"]["PA-1"]
        self.assertEqual(entry["success"], True)
        self.assertEqual(entry["stage_type"], "ACTIVITY")
        self.assertEqual(entry["updated_at"], "2026-08-22T12:00:00")
        self.assertEqual(entry["steps"], [{"action": "tap", "payload": {}}])

    def test_pattern_key_derivation(self):
        # EP-EX-3 -> EP-EX-*；0-1 -> 0-*
        got = ns.build_official_steps([_record(stage="EP-EX-3")])
        self.assertIn("EP-EX-*", got["patterns"])
        for stage, key in [("0-1", "0-*"), ("1-7", "1-*")]:
            got = ns.build_official_steps([_record(stage=stage)])
            self.assertIn(key, got["patterns"])
            self.assertEqual(got["patterns"][key]["source_stage"], stage)

    def test_non_stage_code_has_no_pattern(self):
        # "Annihilation" 不是关卡代号（无连字符段）-> 只有 stages 条目、无 patterns
        got = ns.build_official_steps([_record(stage="Annihilation")])
        self.assertIn("Annihilation", got["stages"])
        self.assertEqual(got["patterns"], {})

    def test_empty_steps_skipped(self):
        # 无有效步骤的记录不该产出（官方只录有用的，与 persist 只在有步骤时写入一致）
        got = ns.build_official_steps([_record(steps=[])])
        self.assertEqual(got["stages"], {})
        self.assertEqual(got["patterns"], {})

    def test_non_list_steps_skipped(self):
        got = ns.build_official_steps([_record(steps="nope")])
        self.assertEqual(got["stages"], {})

    def test_missing_stage_skipped(self):
        got = ns.build_official_steps([{"stage": None, "steps": [{"action": "x"}]}])
        self.assertEqual(got["stages"], {})

    def test_non_dict_record_skipped(self):
        got = ns.build_official_steps(["nope", 3])
        self.assertEqual(got["stages"], {})

    def test_pattern_entry_shape(self):
        got = ns.build_official_steps([_record(stage="PA-1")])
        p = got["patterns"]["PA-*"]
        self.assertEqual(p["source_stage"], "PA-1")
        self.assertEqual(p["success"], True)
        self.assertEqual(p["steps"], [{"action": "tap", "payload": {}}])
        self.assertEqual(p["stage_type"], "ACTIVITY")

    def test_multiple_records(self):
        got = ns.build_official_steps(
            [_record(stage="PA-1"), _record(stage="PA-2"), _record(stage="EP-EX-3")]
        )
        self.assertEqual(set(got["stages"]), {"PA-1", "PA-2", "EP-EX-3"})
        self.assertEqual(set(got["patterns"]), {"PA-*", "EP-EX-*"})


class TestMergeOfficialSteps(unittest.TestCase):
    """官方层自身合并：官方是权威，同 key 覆盖；保留 existing 其它 key；不改入参。"""

    def test_both_empty(self):
        self.assertEqual(
            ns.merge_official_steps({}, {}),
            {"version": 1, "stages": {}, "patterns": {}},
        )

    def test_fresh_overwrites_same_key(self):
        existing = {"stages": {"PA-1": _record(steps=[{"action": "old"}])}}
        fresh = {"stages": {"PA-1": _record(steps=[{"action": "new"}])}}
        got = ns.merge_official_steps(existing, fresh)
        self.assertEqual(got["stages"]["PA-1"]["steps"], [{"action": "new"}])

    def test_existing_keys_retained(self):
        existing = {"stages": {"PA-1": _record()}, "patterns": {"PA-*": _record()}}
        got = ns.merge_official_steps(existing, {})
        self.assertIn("PA-1", got["stages"])
        self.assertIn("PA-*", got["patterns"])

    def test_fresh_adds_missing_keys(self):
        got = ns.merge_official_steps(
            {"stages": {"PA-1": _record()}}, {"patterns": {"PA-*": _record()}}
        )
        self.assertIn("PA-1", got["stages"])
        self.assertIn("PA-*", got["patterns"])

    def test_non_dict_entries_filtered(self):
        got = ns.merge_official_steps(
            {"stages": {"S": "nope"}}, {"stages": {"T": 3}, "patterns": {"P": 1}}
        )
        self.assertNotIn("S", got["stages"])
        self.assertNotIn("T", got["stages"])
        self.assertEqual(got["patterns"], {})

    def test_does_not_mutate_inputs(self):
        existing = {"stages": {"PA-1": _record(steps=[{"action": "old"}])}}
        fresh = {"stages": {"PA-1": _record(steps=[{"action": "new"}])}}
        ns.merge_official_steps(existing, fresh)
        self.assertEqual(existing["stages"]["PA-1"]["steps"], [{"action": "old"}])
        self.assertEqual(fresh["stages"]["PA-1"]["steps"], [{"action": "new"}])

    def test_roundtrip_with_build_and_load(self):
        # build_official_steps 的产物能 back feed 进 load_nav_file + merge 保持稳定
        built = ns.build_official_steps([_record(stage="PA-1")])
        merged = ns.merge_official_steps(built, built)
        self.assertEqual(
            merged["stages"]["PA-1"]["steps"], [{"action": "tap", "payload": {}}]
        )


if __name__ == "__main__":
    unittest.main()
