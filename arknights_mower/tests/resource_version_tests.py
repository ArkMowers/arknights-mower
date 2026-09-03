import unittest
from contextlib import ExitStack
from unittest.mock import patch

from arknights_mower.utils import resource_version as rv
from arknights_mower.utils.res_version import parse_version, version_newer


def _version(res_version="2026.08.23-31a240b", name="墟·复刻", time=1724068800):
    return {
        "res_version": res_version,
        "activity": {"name": name, "time": time, "endTime": time + 86400},
        "gacha": {},
        "last_updated": "2026-08-23",
    }


class TestParseResVersion(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_version("2026.08.23-31a240b"), (2026, 8, 23, "31a240b"))
        self.assertEqual(parse_version("v2026.08.23-31a240b"), (2026, 8, 23, "31a240b"))

    def test_invalid(self):
        for bad in [
            "2026.08.23",
            "2026-08-23-31a240b",
            "vv2026.08.23-31a240b",
            "",
            None,
            "2026.08.23-zzz",
        ]:
            self.assertIsNone(parse_version(bad), f"should reject: {bad!r}")


class TestResVersionNewer(unittest.TestCase):
    def test_same_date_diff_hash_is_newer(self):
        self.assertTrue(version_newer("2026.08.23-bbbbbbb", "2026.08.23-aaaaaaa"))

    def test_later_date_is_newer(self):
        self.assertTrue(version_newer("2026.08.24-aaaaaaa", "2026.08.23-aaaaaaa"))

    def test_earlier_date_is_not_newer(self):
        self.assertFalse(version_newer("2026.08.22-aaaaaaa", "2026.08.23-aaaaaaa"))

    def test_equal_is_not_newer(self):
        self.assertFalse(version_newer("2026.08.23-aaaaaaa", "2026.08.23-aaaaaaa"))

    def test_absent_local_is_always_newer(self):
        self.assertTrue(version_newer("2026.08.23-aaaaaaa", ""))

    def test_v_prefix_ignored(self):
        self.assertFalse(version_newer("v2026.08.23-aaaaaaa", "2026.08.23-aaaaaaa"))
        self.assertTrue(version_newer("v2026.08.24-aaaaaaa", "2026.08.23-aaaaaaa"))

    def test_unparsable_falls_back_to_inequality(self):
        self.assertTrue(version_newer("nope", "2026.08.23-aaaaaaa"))
        self.assertFalse(version_newer("nope", "nope"))


class TestCheckResourceUpdate(unittest.TestCase):
    def _patch(self, remote=None, local=None, cache=None):
        stack = ExitStack()
        stack.enter_context(
            patch(
                "arknights_mower.utils.resource_version._fetch_remote_version_json",
                return_value=remote,
            )
        )
        stack.enter_context(
            patch(
                "arknights_mower.utils.resource_version._read_local_version_json",
                return_value=local,
            )
        )
        stack.enter_context(
            patch(
                "arknights_mower.utils.resource_version._read_tmp_cache",
                return_value=cache,
            )
        )
        stack.enter_context(
            patch("arknights_mower.utils.resource_version._write_tmp_cache")
        )
        return stack

    def test_remote_newer_than_local(self):
        local = _version(res_version="2026.08.22-aaaaaaa")
        remote = _version(res_version="2026.08.23-31a240b")
        with self._patch(remote=remote, local=local):
            got = rv.check_resource_update()
        self.assertEqual(got["current_version"], "2026.08.22-aaaaaaa")
        self.assertEqual(got["remote_version"], "2026.08.23-31a240b")
        self.assertTrue(got["update_available"])
        self.assertIsNone(got["error"])
        self.assertTrue(got["current_display"].startswith("墟·复刻#"))

    def test_remote_newer_no_local(self):
        with self._patch(remote=_version(), local=None):
            got = rv.check_resource_update()
        self.assertEqual(got["current_version"], "")
        self.assertEqual(got["current_display"], "")
        self.assertTrue(got["update_available"])

    def test_local_is_latest(self):
        local = _version(res_version="2026.08.23-31a240b")
        remote = _version(res_version="2026.08.23-31a240b")
        with self._patch(remote=remote, local=local):
            got = rv.check_resource_update()
        self.assertFalse(got["update_available"])
        self.assertIsNone(got["error"])

    def test_fetch_fail_no_cache(self):
        local = _version(res_version="2026.08.22-aaaaaaa")
        with self._patch(remote=None, local=local, cache=None):
            got = rv.check_resource_update()
        self.assertIsNone(got["update_available"])
        self.assertIn("网络错误", got["error"])
        self.assertEqual(got["remote_version"], "")

    def test_fetch_fail_uses_cache(self):
        local = _version(res_version="2026.08.22-aaaaaaa")
        cache = _version(res_version="2026.08.23-31a240b")
        with self._patch(remote=None, local=local, cache=cache):
            got = rv.check_resource_update()
        self.assertTrue(got["update_available"])
        self.assertEqual(got["remote_version"], "2026.08.23-31a240b")
        self.assertIsNone(got["error"])

    def test_remote_missing_res_version_is_error(self):
        with self._patch(remote={"activity": {}}, local=None):
            got = rv.check_resource_update()
        self.assertIsNone(got["update_available"])
        self.assertEqual(got["error"], "远程版本号缺失")


if __name__ == "__main__":
    unittest.main()
