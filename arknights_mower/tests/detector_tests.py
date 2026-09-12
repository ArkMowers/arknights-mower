import unittest

import numpy as np

from arknights_mower.utils.detector import infra_notification


class TestInfraNotification(unittest.TestCase):
    """infra_notification 对全暗帧无边界保护——加 right 下限 + 全暗帧返回 None。"""

    def _blue_notification(self, x0, x1, y0, y1, color=(30, 150, 220)):
        """构造 1080p 画布，在 [x0, x1) × [y0, y1) 画一个蓝色通知，其余全暗。"""
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        img[y0:y1, x0:x1] = color
        return img

    def test_all_dark_frame_returns_none(self):
        # 场景切换过渡帧整屏全暗 → right-scan 扫到左边缘即停，返回 None，不再越界崩溃
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.assertIsNone(infra_notification(img))

    def test_normal_blue_notification_returns_point(self):
        img = self._blue_notification(300, 400, 200, 300)
        self.assertEqual(infra_notification(img), (389, 250))

    def test_notification_at_left_edge_not_swallowed(self):
        # 通知贴近 x=0：right-scan 在最右亮列（right=9）停下、不会扫到 right==0；
        # 全暗哨兵（right==0）只对整帧全暗触发，不会误吞左侧的通知
        img = self._blue_notification(0, 10, 200, 300)
        self.assertIsNotNone(infra_notification(img))


if __name__ == "__main__":
    unittest.main()
