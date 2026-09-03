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

    def test_空表返回空(self):
        self.assertEqual(display_version({}), "")
        self.assertEqual(display_version({"activity": {}, "gacha": {}}), "")
