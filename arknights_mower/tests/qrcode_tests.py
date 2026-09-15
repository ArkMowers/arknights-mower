import unittest

from PIL import Image

# map #169：导出图被第三方改过（放更大画布 / 缩小）后导入失败。回归测试覆盖三种情况。
# base 尺寸 3000x1230 略大于导出粘贴二维码的最大坐标（x≈2966 / y≈1210）。
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


@unittest.skipIf(qrcode is None, _SKIP_REASON)
class QRCodeDecodeTests(unittest.TestCase):
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
