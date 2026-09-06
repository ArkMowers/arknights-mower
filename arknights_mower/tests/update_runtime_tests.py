"""update_runtime 的边界用例：代理大小写、登记文件瞬时读取、原子替换重试、子进程编码。"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from arknights_mower.utils import update_runtime as runtime


class LaunchEnvironmentProxyTests(unittest.TestCase):
    def test_小写优先并清重复大写(self):
        # POSIX 风格环境里大小写并存且值不同，小写应生效，大写副本被清除
        base = {"http_proxy": "http://lower", "HTTP_PROXY": "http://upper", "A": "1"}
        with mock.patch.object(runtime.os, "environ", base):
            env = runtime.launch_environment({})
        self.assertEqual(env["http_proxy"], "http://lower")
        self.assertNotIn("HTTP_PROXY", env)

    def test_windows仅大写时归一到小写(self):
        # Windows 的 os._Environ 会把键名归一成大写，复制后需还原成小写
        base = {"HTTPS_PROXY": "http://p", "A": "1"}
        with mock.patch.object(runtime.os, "environ", base):
            env = runtime.launch_environment({})
        self.assertEqual(env["https_proxy"], "http://p")
        self.assertNotIn("HTTPS_PROXY", env)

    def test_子进程编码固定utf8(self):
        with mock.patch.object(runtime.os, "environ", {}):
            env = runtime.launch_environment({})
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")


class InstancesTransientReadTests(unittest.TestCase):
    def test_瞬时读取失败不删活跃登记(self):
        with TemporaryDirectory() as d:
            state = Path(d)
            (state / "instances").mkdir()
            reg = state / "instances" / "abc.json"
            reg.write_text(json.dumps({"pid": os.getpid(), "kind": "instance"}))
            # 登记文件正被并发写者替换，读取瞬时抛 OSError（共享违规/锁）
            with mock.patch.object(runtime.json, "loads", side_effect=OSError("lock")):
                got = runtime.instances(state)
            self.assertEqual(got, [])
            self.assertTrue(reg.exists())  # 不得误删活进程的登记

    def test_死进程登记被清理(self):
        with TemporaryDirectory() as d:
            state = Path(d)
            (state / "instances").mkdir()
            reg = state / "instances" / "dead.json"
            reg.write_text(json.dumps({"pid": 2**31 - 1, "kind": "instance"}))
            got = runtime.instances(state)
            self.assertEqual(got, [])
            self.assertFalse(reg.exists())


class ReplaceWithRetryTests(unittest.TestCase):
    def test_win32共享违规重试后成功(self):
        # replace_with_retry 的重试分支只在 win32 触发；把 platform 固定到 win32，
        # 让该测试在 Windows 与 Linux/CI 上都走同一条重试路径。
        with mock.patch.object(runtime.sys, "platform", "win32"):
            with TemporaryDirectory() as d:
                src, dst = Path(d) / "src", Path(d) / "dst"
                src.write_text("x")
                real_replace = os.replace
                calls = {"n": 0}

                def flaky(source, destination):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        err = OSError("sharing violation")
                        err.winerror = 32
                        raise err
                    real_replace(source, destination)

                with mock.patch.object(runtime.os, "replace", flaky):
                    runtime.replace_with_retry(src, dst)
                self.assertEqual(calls["n"], 2)
                self.assertTrue(dst.exists())
                self.assertEqual(dst.read_text(), "x")


if __name__ == "__main__":
    unittest.main()
