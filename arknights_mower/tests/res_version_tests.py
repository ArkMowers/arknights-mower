import tempfile
import unittest
from pathlib import Path

from arknights_mower.utils.res_version import (
    RES_PACKAGE_DATA,
    RES_PACKAGE_MODELS,
    content_hash,
    display_version,
    package_file_paths,
    pick_latest_activity,
    pick_latest_gacha,
)


class TestPickLatestActivity(unittest.TestCase):
    def test_最新活动取开启时间最大(self):
        table = {
            "basicInfo": {
                "act_1": {
                    "name": "签到",
                    "type": "CHECKIN",
                    "startTime": 100,
                    "endTime": 200,
                },
                "act_2": {
                    "name": "复刻",
                    "type": "ACTIVITY",
                    "startTime": 300,
                    "endTime": 400,
                },
                "act_3": {
                    "name": "新活动",
                    "type": "ACTIVITY",
                    "startTime": 500,
                    "endTime": 600,
                },
            }
        }
        self.assertEqual(
            pick_latest_activity(table),
            {"name": "新活动", "time": 500, "endTime": 600},
        )

    def test_签到类被过滤(self):
        table = {
            "basicInfo": {
                "act": {
                    "name": "签到",
                    "type": "CHECKIN",
                    "startTime": 100,
                    "endTime": 200,
                }
            }
        }
        self.assertEqual(pick_latest_activity(table), {})

    def test_空表返回空(self):
        self.assertEqual(pick_latest_activity({}), {})
        self.assertEqual(pick_latest_activity({"basicInfo": {}}), {})


class TestPickLatestGacha(unittest.TestCase):
    def test_最新卡池取开启时间最大(self):
        table = {
            "gachaPoolClient": [
                {"gachaPoolName": "旧卡池", "openTime": 100, "endTime": 200},
                {"gachaPoolName": "新卡池", "openTime": 300, "endTime": 400},
            ]
        }
        self.assertEqual(
            pick_latest_gacha(table),
            {"name": "新卡池", "time": 300, "endTime": 400},
        )

    def test_标准池被过滤(self):
        table = {
            "gachaPoolClient": [
                {
                    "gachaPoolName": "适合多种场合的强力干员",
                    "openTime": 100,
                    "endTime": 200,
                },
            ]
        }
        self.assertEqual(pick_latest_gacha(table), {})

    def test_空表返回空(self):
        self.assertEqual(pick_latest_gacha({}), {})
        self.assertEqual(pick_latest_gacha({"gachaPoolClient": []}), {})


class TestContentHash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_同内容同哈希顺序无关(self):
        a = Path("a.bin")
        b = Path("b.bin")
        (self.dir / a).write_bytes(b"hello")
        (self.dir / b).write_bytes(b"world")
        self.assertEqual(
            content_hash(self.dir, [a, b]),
            content_hash(self.dir, [b, a]),
        )

    def test_内容变哈希变(self):
        rel = Path("f.bin")
        (self.dir / rel).write_bytes(b"v1")
        h1 = content_hash(self.dir, [rel])
        (self.dir / rel).write_bytes(b"v2")
        h2 = content_hash(self.dir, [rel])
        self.assertNotEqual(h1, h2)

    def test_同字节不同路径哈希不同(self):
        (self.dir / "x.bin").write_bytes(b"same")
        (self.dir / "y.bin").write_bytes(b"same")
        self.assertNotEqual(
            content_hash(self.dir, [Path("x.bin")]),
            content_hash(self.dir, [Path("y.bin")]),
        )

    def test_文件缺失抛出(self):
        with self.assertRaises(FileNotFoundError):
            content_hash(self.dir, [Path("nope.bin")])

    def test_declared_text_normalizes_crlf_across_chunk_boundary(self):
        rel = Path(RES_PACKAGE_DATA[0])
        path = self.dir / rel
        path.parent.mkdir(parents=True)
        crlf = b"x" * ((1 << 20) - 1) + b"\r\nnext\r\nlast\r"
        path.write_bytes(crlf)
        windows_hash = content_hash(self.dir, [rel])
        path.write_bytes(crlf.replace(b"\r\n", b"\n"))
        self.assertEqual(windows_hash, content_hash(self.dir, [rel]))

    def test_binary_without_nul_and_undeclared_text_keep_exact_bytes(self):
        for name in (
            RES_PACKAGE_MODELS[0],
            "ui/public/avatar/test.webp",
            "unknown.json",
        ):
            with self.subTest(name=name):
                rel = Path(name)
                path = self.dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"\x01\r\n\x02")
                original = content_hash(self.dir, [rel])
                path.write_bytes(b"\x01\n\x02")
                self.assertNotEqual(original, content_hash(self.dir, [rel]))

    def test_声明的文本资源按换行归一化(self):
        # 声明的文本资源在 LF/CRLF 检出下应得到同一摘要。
        rel = Path(RES_PACKAGE_DATA[0])
        (self.dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.dir / rel).write_bytes(b'{"a":1}\r\n{"b":2}\r\n')
        h_crlf = content_hash(self.dir, [rel])
        (self.dir / rel).write_bytes(b'{"a":1}\n{"b":2}\n')
        h_lf = content_hash(self.dir, [rel])
        self.assertEqual(h_crlf, h_lf)

    def test_二进制后缀不过换行归一化(self):
        # 非文本类型即便不含 NUL 也按原始字节参与，内容不同的二进制样例不致同摘要
        rel = Path("blob.bin")
        (self.dir / rel).write_bytes(b"a\r\nb\r\n")
        h_crlf = content_hash(self.dir, [rel])
        (self.dir / rel).write_bytes(b"a\nb\n")
        h_lf = content_hash(self.dir, [rel])
        self.assertNotEqual(h_crlf, h_lf)


class TestPackageFilePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_展开目录与显式文件并按路径排序(self):
        # 只搭两个目录 + 一个显式文件，验证收集与排序（含子目录递归）
        (self.dir / "ui/public/depot/sub").mkdir(parents=True)
        (self.dir / "ui/public/depot/z.webp").write_bytes(b"z")
        (self.dir / "ui/public/depot/a.webp").write_bytes(b"a")
        (self.dir / "ui/public/depot/sub/n.webp").write_bytes(b"n")
        (self.dir / "ui/public/avatar").mkdir(parents=True)
        (self.dir / "ui/public/avatar/1.webp").write_bytes(b"1")
        target = self.dir / RES_PACKAGE_MODELS[0]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"m")

        rels = [p.as_posix() for p in package_file_paths(self.dir)]
        self.assertEqual(rels, sorted(rels))
        self.assertIn("ui/public/depot/a.webp", rels)
        self.assertIn("ui/public/depot/z.webp", rels)
        self.assertIn("ui/public/depot/sub/n.webp", rels)
        self.assertIn("ui/public/avatar/1.webp", rels)
        self.assertIn(RES_PACKAGE_MODELS[0], rels)

    def test_不存在的显式文件被跳过(self):
        # RES_PACKAGE_DATA 里都不存在 → 只收目录里的文件
        (self.dir / "ui/public/depot").mkdir(parents=True)
        (self.dir / "ui/public/depot/x.webp").write_bytes(b"x")
        rels = [p.as_posix() for p in package_file_paths(self.dir)]
        self.assertEqual(rels, ["ui/public/depot/x.webp"])
        self.assertNotIn(RES_PACKAGE_DATA[0], rels)


class TestDisplayVersion(unittest.TestCase):
    def test_取较晚开启者加MMDD(self):
        # 1787342400 = 2026-08-22（北京时区），1785538800 更早
        info = {
            "activity": {"name": "墟·复刻", "time": 1787342400, "endTime": 0},
            "gacha": {"name": "车辙与风的归所", "time": 1785538800, "endTime": 0},
        }
        self.assertEqual(display_version(info), "墟·复刻#0822")

    def test_卡池更晚则取卡池(self):
        info = {
            "activity": {"name": "旧活动", "time": 100, "endTime": 0},
            "gacha": {"name": "新卡池", "time": 1787342400, "endTime": 0},
        }
        self.assertEqual(display_version(info), "新卡池#0822")

    def test_构建日期优先于开启日期(self):
        # res_version 的日期（构建日期）优先于 activity/gacha 开启日期
        info = {
            "res_version": "v2026.09.05-12ab34",
            "activity": {"name": "活动甲", "time": 1787342400, "endTime": 0},
            "gacha": {"name": "卡池乙", "time": 1785538800, "endTime": 0},
        }
        self.assertEqual(display_version(info), "活动甲#0905")

    def test_空表返回空(self):
        self.assertEqual(display_version({}), "")
        self.assertEqual(display_version({"activity": {}, "gacha": {}}), "")
