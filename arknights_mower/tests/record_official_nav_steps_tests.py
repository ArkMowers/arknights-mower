import importlib.util
import unittest
from pathlib import Path


def _load_script():
    path = (
        Path(__file__).resolve().parents[2] / "scripts" / "record_official_nav_steps.py"
    )
    spec = importlib.util.spec_from_file_location("record_official_nav_steps", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


rec = _load_script()


def _nav_ok(stage):
    return {"stage": stage, "stage_type": "ACTIVITY", "steps": [{"action": "tap"}]}


def _nav_none(stage):
    return None


def _nav_boom(stage):
    raise RuntimeError("boom")


def _nav_empty_steps(stage):
    return {"stage": stage, "stage_type": "ACTIVITY", "steps": []}


@unittest.skipIf(rec is None, "record_official_nav_steps.py 无法加载")
class TestCollectRecords(unittest.TestCase):
    """驱动层：navigate 注入假实现，测成功/失败/无步骤省略的分类与记录填充。"""

    def test_all_success(self):
        ok, failed, skipped = rec.collect_records(["PA-1", "PA-2"], _nav_ok)
        self.assertEqual([r["stage"] for r in ok], ["PA-1", "PA-2"])
        self.assertEqual(failed, [])
        self.assertEqual(skipped, [])

    def test_none_returns_failed(self):
        ok, failed, skipped = rec.collect_records(["PA-1"], _nav_none)
        self.assertEqual(ok, [])
        self.assertEqual(failed[0]["reason"], "navigation failed")
        self.assertEqual(skipped, [])

    def test_exception_returns_failed_with_reason(self):
        ok, failed, skipped = rec.collect_records(["PA-1"], _nav_boom)
        self.assertEqual(ok, [])
        self.assertEqual(failed[0]["reason"], "boom")
        self.assertEqual(skipped, [])

    def test_success_but_no_steps_skipped_not_failed(self):
        ok, failed, skipped = rec.collect_records(["PA-1"], _nav_empty_steps)
        self.assertEqual(ok, [])
        self.assertEqual(failed, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("未记录到步骤", skipped[0]["reason"])

    def test_updated_at_filled(self):
        ok, _, _ = rec.collect_records(["PA-1"], _nav_ok)
        self.assertTrue(ok[0]["updated_at"])

    def test_updated_at_preserved(self):
        def nav(stage):
            return {
                "stage": stage,
                "stage_type": "ACTIVITY",
                "steps": [{"action": "tap"}],
                "updated_at": "fixed-ts",
            }

        ok, _, _ = rec.collect_records(["PA-1"], nav)
        self.assertEqual(ok[0]["updated_at"], "fixed-ts")


if __name__ == "__main__":
    unittest.main()
