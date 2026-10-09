import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

# 回归覆盖回收站区域、旧版布局及第三方扩大或缩小后的图片导入。
#
# pyzbar 依赖系统 libzbar，CI 的 ubuntu-latest 没装。qrcode 模块顶层 `from pyzbar import
# pyzbar` 在缺 zbar 时直接抛异常 → 会拖垮整个 unittest job。这里把 import 包起来，失败时
# 把整组测试跳过（本机/有 zbar 时照常运行并守护回归）。

try:
    from arknights_mower.utils import qrcode
except Exception as e:  # 无 libzbar 环境
    qrcode = None
    _SKIP_REASON = f"pyzbar/libzbar 不可用，跳过二维码回归测试: {e}"
else:
    _SKIP_REASON = None


def _plan():
    return {
        "default": {
            "agents": {"room_1": ["德克萨斯", "能天使"], "room_2": ["伊芙利特"]}
        },
        "conf": {"free_blacklist": [], "resting_priority": [], "workaholic": []},
        "backup_plans": [],
    }


def _export_img(plan):
    base = Image.new("RGB", (3000, 1230), (255, 255, 255))
    return qrcode.export(plan, base)


def _legacy_export_img(plan):
    img = Image.new("RGB", (3000, 1230), "white")
    codes = qrcode.encode(json.dumps(plan), n=16)
    positions = [(40 + i * 231, 40) for i in range(7)]
    positions += [(40 + i * 231, 995) for i in range(7)]
    positions += [(2520 + i * 231, 995) for i in range(2)]
    for code, position in zip(codes, positions):
        img.paste(code, position)
    return img


@unittest.skipIf(qrcode is None, _SKIP_REASON)
class QRCodeDecodeTests(unittest.TestCase):
    def test_export_keeps_right_side_facilities(self):
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                base = Image.new(
                    "RGB", (2940, 1248), "white" if theme == "light" else "black"
                )
                region = (2500, 960, 2940, 1248)
                base.paste((80, 160, 96), region)
                original = base.copy()
                exported = qrcode.export(_plan(), base, theme)
                self.assertIsNone(ImageChops.difference(base, original).getbbox())
                self.assertIsNone(
                    ImageChops.difference(
                        exported.crop(region), original.crop(region)
                    ).getbbox()
                )
                self.assertEqual(exported.size, base.size)
                self.assertEqual(len(qrcode.encode(json.dumps(_plan()))), 14)
                self.assertEqual(qrcode.decode(exported), _plan())

    def test_narrow_export_keeps_all_qrcodes(self):
        base = Image.new("RGB", (200, 100), "white")
        exported = qrcode.export(_plan(), base)
        self.assertGreater(exported.width, base.width)
        self.assertEqual(qrcode.decode(exported), _plan())

    def test_legacy_fixed_layout_still_imports(self):
        plan = _plan()
        self.assertEqual(qrcode.decode(_legacy_export_img(plan)), plan)

    def test_partial_legacy_scan_retries_before_accepting_fourteen_codes(self):
        plan = _plan()
        img = _legacy_export_img(plan)
        complete = qrcode._scan_and_cover(img.copy())
        self.assertEqual(len(complete), 16)

        def scan_partial_then_complete(work):
            if work.size == img.size:
                work.paste("white", (0, 0, work.width, work.height))
                return complete[:14]
            self.assertIsNotNone(
                ImageChops.difference(
                    work, Image.new("RGB", work.size, "white")
                ).getbbox()
            )
            return complete

        with patch.object(
            qrcode, "_scan_and_cover", side_effect=scan_partial_then_complete
        ) as scan:
            self.assertEqual(qrcode.decode(img), plan)
            self.assertEqual(scan.call_count, 2)

    def test_large_recycling_plan_survives_jpeg(self):
        plan = json.loads(
            (
                Path(__file__).parent / "fixtures/local_backup_plan_20260927.json"
            ).read_text()
        )
        plan["plan1"]["recycle"] = {
            "plans": [{"agent": "艾雅法拉"}, {"agent": "安洁莉娜"}]
        }
        for backup in plan["backup_plans"]:
            backup["plan"]["recycle"] = {"plans": [{"agent": "阿米娅"}]}
            backup["task"]["recycle"] = ["Current", "阿米娅"]
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                base = Image.new(
                    "RGB", (2940, 1248), "white" if theme == "light" else "black"
                )
                img = qrcode.export(plan, base, theme)
                buffer = BytesIO()
                img.save(buffer, format="JPEG")
                buffer.seek(0)
                self.assertEqual(qrcode.decode(Image.open(buffer)), plan)

    def test_round_trip(self):
        plan = _plan()
        self.assertEqual(qrcode.decode(_export_img(plan)), plan)

    def test_larger_canvas_ordering(self):
        # 旧实现在图被加高/整体平移时用 top*2 > 图高 分排会误判底排 → 顺序错乱
        plan = _plan()
        exported = _export_img(plan)
        w, h = exported.size
        big = Image.new("RGB", (w + 400, h + 700), (255, 255, 255))
        big.paste(exported, (120, 300))
        self.assertEqual(qrcode.decode(big), plan)

    def test_downscaled_scale_resilience(self):
        plan = _plan()
        exported = _export_img(plan)
        small = exported.resize(
            (int(exported.width * 0.4), int(exported.height * 0.4)), Image.LANCZOS
        )
        self.assertEqual(qrcode.decode(small), plan)

    def test_blank_image_returns_none(self):
        self.assertIsNone(
            qrcode.decode(Image.new("RGB", (1000, 1000), (255, 255, 255)))
        )


if __name__ == "__main__":
    unittest.main()
