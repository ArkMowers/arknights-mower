import unittest
from unittest.mock import patch

from arknights_mower.solvers.recruit import RecruitSolver


class TestRecruitCal(unittest.TestCase):
    @patch.object(RecruitSolver, "__init__", lambda x: None)
    def setUp(self):
        self.test_class = RecruitSolver()
        self.test_class.recruit_order = [6, 5, 1, 4, 3, 2]

    def test_recruit_cal_with_order_1(self):
        recruit_tags = ["重装干员", "先锋干员", "高级资深干员", "支援", "支援机械"]
        results = self.test_class.recruit_cal(recruit_tags)
        by_tags = {
            item["tag"]: item["result"]
            for candidates in results.values()
            for item in candidates
        }

        self.assertEqual(set(results), {1, 2, 3, 4, 5, 6})
        self.assertEqual(
            by_tags[("重装干员", "高级资深干员", "支援")],
            [{"id": "char_202_demkni", "name": "塞雷娅", "star": 6}],
        )
        self.assertEqual(
            {agent["name"] for agent in by_tags[("先锋干员", "支援")]},
            {"凛冬", "极境"},
        )
        self.assertTrue(results[1])
        self.assertTrue(
            all(agent["star"] == 1 for item in results[1] for agent in item["result"])
        )

    def test_six_star_candidates_require_top_operator_tag(self):
        results = self.test_class.recruit_cal(["重装干员", "先锋干员", "支援"])

        self.assertEqual(results[6], [])
        self.assertTrue(results[5])
        self.assertTrue(
            all(
                agent["star"] < 6
                for candidates in results.values()
                for item in candidates
                for agent in item["result"]
            )
        )


if __name__ == "__main__":
    unittest.main()
