"""Cross-platform update coordination; all processes and files are test-owned."""

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.request import getproxies_environment

from arknights_mower.utils import update_runtime as runtime


class ProxyEnvironmentTests(unittest.TestCase):
    def test_lowercase_wins_even_when_empty_regardless_of_insertion_order(self):
        for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            for value in ("socks5h://127.0.0.1:7897", ""):
                for reverse in (False, True):
                    items = [(name.upper(), "old"), (name, value)]
                    if reverse:
                        items.reverse()
                    # A plain mapping deliberately models POSIX duplicate keys,
                    # even when this regression test runs on Windows.
                    with self.subTest(name=name, value=value, reverse=reverse):
                        with patch.object(runtime.os, "environ", dict(items)):
                            result = runtime.launch_environment({})
                        self.assertEqual(result[name], value)
                        self.assertNotIn(name.upper(), result)

    def test_only_uppercase_and_absent_variables(self):
        with patch.object(runtime.os, "environ", {"HTTPS_PROXY": "https://proxy:7897"}):
            result = runtime.launch_environment({})
        self.assertEqual(result["https_proxy"], "https://proxy:7897")
        self.assertNotIn("http_proxy", result)
        self.assertNotIn("HTTPS_PROXY", result)

    def test_real_environment_keeps_platform_proxy_semantics(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:18080"
            os.environ["http_proxy"] = "http://127.0.0.1:17897"
            before = getproxies_environment()
            result = runtime.launch_environment({})
            if os.name == "nt":
                self.assertEqual(os.environ["HTTP_PROXY"], os.environ["http_proxy"])
            else:
                self.assertNotEqual(os.environ["HTTP_PROXY"], os.environ["http_proxy"])
        with patch.dict(os.environ, result, clear=True):
            self.assertEqual(getproxies_environment(), before)

    def test_saved_proxy_override_and_clearing_restore_inherited_environment(self):
        from arknights_mower.utils import network_settings as network

        for proxy in (
            "http://127.0.0.1:7897",
            "socks5://127.0.0.1:7897",
            "socks5h://127.0.0.1:7897",
        ):
            with (
                self.subTest(proxy=proxy),
                patch.dict(
                    os.environ,
                    {
                        "HTTPS_PROXY": "http://inherited:7897",
                        "NO_PROXY": "internal.example",
                    },
                    clear=True,
                ),
                patch.object(network, "_base_environment", None),
                patch.object(network, "_effective_settings", None),
                patch.object(
                    network,
                    "get_settings",
                    return_value={"http_proxy": proxy, "github_proxy": ""},
                ) as settings,
            ):
                network.apply_http_proxy()
                result = runtime.launch_environment({})
                for name in ("http_proxy", "https_proxy", "all_proxy"):
                    self.assertEqual(result[name], proxy)
                self.assertIn("127.0.0.1", result["no_proxy"])
                settings.return_value = {"http_proxy": "", "github_proxy": ""}
                network.apply_http_proxy()
                result = runtime.launch_environment({})
                self.assertEqual(result["https_proxy"], "http://inherited:7897")
                self.assertNotIn("all_proxy", result)
                self.assertIn("internal.example", result["no_proxy"])


class InstanceScanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mower 登记 ")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "instances/live.json"
        self.record = {"id": "live", "pid": os.getpid(), "kind": "instance"}
        runtime.write_json(self.path, self.record)

    def test_transient_read_error_recovers_without_deleting_live_record(self):
        read_text = Path.read_text
        calls = []

        def read(path, *args, **kwargs):
            if path == self.path:
                calls.append(path)
                if len(calls) == 1:
                    raise PermissionError("temporarily locked")
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            self.assertEqual(runtime.instances(self.directory), [self.record])
        self.assertEqual(len(calls), 2)
        self.assertTrue(self.path.exists())

    def test_read_failures_share_one_scan_budget_and_preserve_all_files(self):
        other = self.path.with_name("second.json")
        runtime.write_json(other, self.record)
        clock = [0.0]
        with (
            patch.object(Path, "read_text", side_effect=PermissionError("locked")),
            patch.object(runtime.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(
                runtime.time,
                "sleep",
                side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
            ),
        ):
            with self.assertRaisesRegex(
                runtime.InstanceScanError, "无法完整读取实例登记"
            ):
                runtime.instances(self.directory)
        self.assertAlmostEqual(clock[0], 5)
        self.assertTrue(self.path.exists())
        self.assertTrue(other.exists())

    def test_invalid_content_is_preserved(self):
        for value in ("{", "[]", "{}", '{"pid":true}', '{"pid":0}', '{"pid":"123"}'):
            with self.subTest(value=value):
                self.path.write_text(value, encoding="utf-8")
                with self.assertRaises(runtime.InstanceScanError):
                    runtime.instances(self.directory, timeout=0)
                self.assertEqual(self.path.read_text(encoding="utf-8"), value)

    def test_file_removed_by_exiting_instance_is_ignored(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(runtime.instances(self.directory), [])
        self.assertTrue(self.path.exists())  # The scanner did not delete it.

    def test_only_confirmed_dead_process_is_cleaned_up(self):
        with patch.object(runtime, "process_alive", return_value=False):
            self.assertEqual(runtime.instances(self.directory), [])
        self.assertFalse(self.path.exists())

    def test_unreadable_directory_is_not_an_empty_snapshot(self):
        with patch.object(
            Path, "iterdir", side_effect=PermissionError("directory locked")
        ):
            with self.assertRaises(runtime.InstanceScanError):
                runtime.instances(self.directory, timeout=0)

    def test_tray_best_effort_scan_does_not_delete_unknown_registrations(self):
        self.path.write_text("{", encoding="utf-8")
        self.assertEqual(runtime.managed_instances(self.directory), [])
        self.assertEqual(runtime.unified_managers(self.directory), [])
        self.assertTrue(self.path.exists())


@contextmanager
def windows_read_handle(path):
    """Hold a real Windows handle which allows reads but denies replacement."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


class AtomicJsonTests(unittest.TestCase):
    def test_nonsharing_errors_are_not_retried_on_any_platform(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.json"
            runtime.write_json(path, {"packages": ["old"]})
            with patch.object(
                runtime.os, "replace", side_effect=OSError("disk error")
            ) as replace:
                with self.assertRaises(OSError):
                    runtime.write_json(path, {"packages": ["new"]})
            self.assertEqual(replace.call_count, 1)
            self.assertEqual(runtime.read_json(path), {"packages": ["old"]})
            self.assertEqual(list(Path(folder).iterdir()), [path])

    @unittest.skipIf(os.name == "nt", "POSIX open-file replacement semantics")
    def test_posix_can_replace_file_while_reader_keeps_old_handle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.json"
            runtime.write_json(path, {"version": "old"})
            with path.open(encoding="utf-8") as old:
                runtime.write_json(path, {"version": "new"})
                self.assertEqual(json.load(old), {"version": "old"})
            self.assertEqual(runtime.read_json(path), {"version": "new"})

    @unittest.skipUnless(os.name == "nt", "Windows native sharing locks")
    def test_windows_retries_until_reader_releases_handle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.json"
            runtime.write_json(path, {"version": "old"})
            attempted = threading.Event()
            errors = []
            replace = os.replace

            def observed_replace(source, destination):
                try:
                    return replace(source, destination)
                except OSError:
                    attempted.set()
                    raise

            def publish():
                try:
                    runtime.write_json(path, {"version": "new"})
                except Exception as exc:
                    errors.append(exc)

            with patch.object(runtime.os, "replace", side_effect=observed_replace):
                with windows_read_handle(path):
                    thread = threading.Thread(target=publish)
                    thread.start()
                    seen = attempted.wait(3)
                thread.join(10)
            self.assertTrue(seen, "writer never encountered the real sharing lock")
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(runtime.read_json(path), {"version": "new"})

    @unittest.skipUnless(os.name == "nt", "Windows native sharing locks")
    def test_windows_persistent_lock_keeps_old_json_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.json"
            runtime.write_json(path, {"version": "old"})
            with windows_read_handle(path):
                with self.assertRaises(PermissionError):
                    runtime.write_json(path, {"version": "new"})
            self.assertEqual(runtime.read_json(path), {"version": "old"})
            self.assertEqual(list(Path(folder).iterdir()), [path])


class Utf8OutputTests(unittest.TestCase):
    def test_existing_gbk_streams_are_reconfigured(self):
        buffers = [io.BytesIO(), io.BytesIO()]
        streams = [io.TextIOWrapper(buffer, encoding="gbk") for buffer in buffers]
        try:
            with (
                patch.object(sys, "stdout", streams[0]),
                patch.object(sys, "stderr", streams[1]),
            ):
                with runtime.utf8_output("unused.log"):
                    print("中文路径 🧪", flush=True)
                    print("更新错误 🧪", file=sys.stderr, flush=True)
            self.assertEqual(
                buffers[0].getvalue().decode("utf-8").strip(), "中文路径 🧪"
            )
            self.assertEqual(
                buffers[1].getvalue().decode("utf-8").strip(), "更新错误 🧪"
            )
        finally:
            for stream in streams:
                stream.close()

    def test_windowed_worker_uses_utf8_file_and_restores_missing_streams(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "更新 日志.log"
            with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
                with runtime.utf8_output(path):
                    print("正在更新 🧪")
                    print("错误详情", file=sys.stderr)
                self.assertIsNone(sys.stdout)
                self.assertIsNone(sys.stderr)
            self.assertEqual(
                path.read_text(encoding="utf-8"), "正在更新 🧪\n错误详情\n"
            )

    def test_source_child_overrides_gbk_and_keeps_explicit_gbk_csv(self):
        with tempfile.TemporaryDirectory(prefix="mower 中文 路径 ") as folder:
            csv_path = Path(folder) / "report.csv"
            csv_path.write_text(",作战录像,赤金\n2026-09-05,10,20\n", encoding="gbk")
            code = (
                "import sys\n"
                "from arknights_mower.utils.csv_utils import append_dated_row, read_dicts\n"
                "append_dated_row(sys.argv[1], '2026-09-06', {'作战录像': 30, '赤金': 40}, encoding='gbk')\n"
                "rows = read_dicts(sys.argv[1], encoding='gbk')\n"
                "assert len(rows) == 2 and rows[0]['赤金'] == '20' and rows[1]['赤金'] == '40'\n"
                "print(sys.argv[1] + ' 更新成功 🧪', flush=True)\n"
            )
            with patch.dict(os.environ, PYTHONIOENCODING="gbk", PYTHONUTF8="0"):
                output = subprocess.check_output(
                    [sys.executable, "-c", code, str(csv_path)],
                    env=runtime.launch_environment({}),
                    stderr=subprocess.STDOUT,
                    timeout=30,
                )
            self.assertIn(str(csv_path) + " 更新成功 🧪", output.decode("utf-8"))
            self.assertIn("作战录像", csv_path.read_bytes().decode("gbk"))


class LaunchEnvironmentProxyTests(unittest.TestCase):
    def test_小写优先并清重复大写(self):
        # POSIX 风格环境里大小写并存且值不同，小写应生效，大写副本被清除
        base = {"http_proxy": "http://lower", "HTTP_PROXY": "http://upper", "A": "1"}
        with patch.object(runtime.os, "environ", base):
            env = runtime.launch_environment({})
        self.assertEqual(env["http_proxy"], "http://lower")
        self.assertNotIn("HTTP_PROXY", env)

    def test_windows仅大写时归一到小写(self):
        # Windows 的 os._Environ 会把键名归一成大写，复制后需还原成小写
        base = {"HTTPS_PROXY": "http://p", "A": "1"}
        with patch.object(runtime.os, "environ", base):
            env = runtime.launch_environment({})
        self.assertEqual(env["https_proxy"], "http://p")
        self.assertNotIn("HTTPS_PROXY", env)

    def test_子进程编码固定utf8(self):
        with patch.object(runtime.os, "environ", {}):
            env = runtime.launch_environment({})
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")


class InstancesTransientReadTests(unittest.TestCase):
    def test_瞬时读取失败不删活跃登记(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            (state / "instances").mkdir()
            reg = state / "instances" / "abc.json"
            reg.write_text(json.dumps({"pid": os.getpid(), "kind": "instance"}))
            # 登记文件正被并发写者替换，读取瞬时抛 OSError（共享违规/锁）
            with patch.object(runtime.json, "loads", side_effect=OSError("lock")):
                got = runtime.instances(state, timeout=0, strict=False)
            self.assertEqual(got, [])
            self.assertTrue(reg.exists())  # 不得误删活进程的登记

    def test_死进程登记被清理(self):
        with tempfile.TemporaryDirectory() as d:
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
        with patch.object(runtime.sys, "platform", "win32"):
            with tempfile.TemporaryDirectory() as d:
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

                with patch.object(runtime.os, "replace", flaky):
                    runtime.replace_with_retry(src, dst)
                self.assertEqual(calls["n"], 2)
                self.assertTrue(dst.exists())
                self.assertEqual(dst.read_text(), "x")


if __name__ == "__main__":
    unittest.main()
