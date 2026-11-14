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

    def test_roberta_is_available_with_supporter_and_defense_tags(self):
        results = self.test_class.recruit_cal(["辅助干员", "防护"])
        by_tags = {item["tag"]: item["result"] for item in results[4]}

        self.assertEqual(
            by_tags[("辅助干员", "防护")],
            [{"id": "char_484_robrta", "name": "罗比菈塔", "star": 4}],
        )

    def test_mulberry_is_available_with_senior_medic_tags(self):
        results = self.test_class.recruit_cal(["资深干员", "医疗干员"])
        by_tags = {item["tag"]: item["result"] for item in results[5]}

        self.assertIn(
            {"id": "char_473_mberry", "name": "桑葚", "star": 5},
            by_tags[("资深干员", "医疗干员")],
        )

    def test_saileach_requires_top_operator_tag(self):
        results = self.test_class.recruit_cal(["高级资深干员", "先锋干员", "支援"])
        by_tags = {item["tag"]: item["result"] for item in results[6]}

        self.assertEqual(
            by_tags[("高级资深干员", "先锋干员", "支援")],
            [{"id": "char_479_sleach", "name": "琴柳", "star": 6}],
        )
        without_top_operator = self.test_class.recruit_cal(["先锋干员", "支援"])
        self.assertEqual(without_top_operator[6], [])
        self.assertTrue(
            all(
                agent["id"] != "char_479_sleach"
                for candidates in without_top_operator.values()
                for item in candidates
                for agent in item["result"]
            )
        )


if __name__ == "__main__":
    unittest.main()
