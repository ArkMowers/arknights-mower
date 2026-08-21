import unittest

from PIL import Image

from arknights_mower.utils import qrcode

# map #169：导出图被第三方改过（放更大画布 / 缩小）后导入失败。回归测试覆盖三种情况。
# base 尺寸 3000x1230 略大于导出粘贴二维码的最大坐标（x≈2966 / y≈1210）。


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


class QRCodeDecodeTests(unittest.TestCase):
    def test_round_trip(self):
        plan = _plan()
        self.assertEqual(qrcode.decode(_export_img(plan)), plan)

    def test_larger_canvas_ordering(self):
        # 旧实现在图被加高/整体平移时用 `top*2 > 图高` 分排会误判底排 → 顺序错乱（Error -3）。
        # 触发条件是画布高 > 2*(底排原 y 995 + 垂直偏移 300) = 2590，故用 3000 高画布 + 偏移。
        plan = _plan()
        exported = _export_img(plan)
        big = Image.new(
            "RGB",
            (exported.width + 500, exported.height + 1770),
            (255, 255, 255),
        )
        big.paste(exported, (200, 300))
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
