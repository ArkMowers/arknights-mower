import unittest

from arknights_mower.solvers.mastery import calc_swap_threshold


class TestSwapFormula(unittest.TestCase):
    def test_normal_swap_triggered(self):
        # 当前效率75%, 无职业匹配, 无中枢加成, 剩余400分钟
        # threshold = 310 * (100+5+0+0) / (100+75+5+0) = 310 * 105 / 180 = 180.83
        should, threshold = calc_swap_threshold(75, False, 0, 180)
        self.assertTrue(should)

    def test_normal_swap_not_yet(self):
        # 剩余500分钟, 还没到阈值
        should, threshold = calc_swap_threshold(75, False, 0, 500)
        self.assertFalse(should)

    def test_with_job_match(self):
        # 减半对象有职业匹配(+30%), threshold 会更大
        _, threshold_match = calc_swap_threshold(75, True, 0, 500)
        _, threshold_no_match = calc_swap_threshold(75, False, 0, 500)
        self.assertGreater(threshold_match, threshold_no_match)

    def test_with_central_bonus(self):
        # 中枢加成5%, threshold 变化
        _, threshold_5 = calc_swap_threshold(75, False, 5, 500)
        _, threshold_0 = calc_swap_threshold(75, False, 0, 500)
        # 中枢加成同时影响分子分母, 但分子增比更大(基底更小), 所以threshold略大
        self.assertNotEqual(threshold_5, threshold_0)

    def test_not_enough_time_no_swap(self):
        # 剩余真实时间不足5小时 → 不换
        # 当前效率75%, 剩余200分钟
        # 换入后真实时间 = 200 * 180/105 = 342.8 > 300, 够
        should_200, _ = calc_swap_threshold(75, False, 0, 200)
        # 剩余100分钟
        # 换入后真实时间 = 100 * 180/105 = 171.4 < 300, 不够
        should_100, _ = calc_swap_threshold(75, False, 0, 100)
        self.assertFalse(should_100)

    def test_exact_5_hours_boundary(self):
        # 换入后真实时间刚好300分钟，仍不足301 → 不换（#73 用户拍板：底线 301）
        # real_time = remaining * (100+75+5) / (100+5) = remaining * 180 / 105
        # 300 = remaining * 180/105 → remaining = 300*105/180 = 175
        should, _ = calc_swap_threshold(75, False, 0, 175)
        self.assertFalse(should)

    def test_just_above_5_hours(self):
        # remaining = 176 → real_time = 176*180/105 = 301.7 >= 301, 够（≥301 才换）
        # 但还要看是否到了阈值
        # threshold = 310*105/180 = 180.83
        # 176 < 180.83 → should swap = True
        should, _ = calc_swap_threshold(75, False, 0, 176)
        self.assertTrue(should)

    def test_high_efficiency_current(self):
        # 当前95%高效率, threshold更小(分母更大)
        _, threshold_95 = calc_swap_threshold(95, False, 0, 500)
        _, threshold_75 = calc_swap_threshold(75, False, 0, 500)
        self.assertLess(threshold_95, threshold_75)

    def test_custom_buffer(self):
        # buffer=20 → N=320, threshold更大
        _, threshold_20 = calc_swap_threshold(75, False, 0, 500, buffer=20)
        _, threshold_10 = calc_swap_threshold(75, False, 0, 500, buffer=10)
        self.assertGreater(threshold_20, threshold_10)


if __name__ == "__main__":
    unittest.main()
