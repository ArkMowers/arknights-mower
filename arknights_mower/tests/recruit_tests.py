# -!- coding: utf-8 -!-
import os
import sys
from unittest.mock import patch

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
import unittest
from arknights_mower.solvers.recruit import RecruitSolver

class TestRecruitCal(unittest.TestCase):
    @patch.object(RecruitSolver, "__init__", lambda x: None)
    def setUp(self):
        self.test_class = RecruitSolver()
        self.test_class.recruit_order = [6, 5, 1, 4, 3, 2]

    def test_recruit_cal_with_order_1(self):
        recruit_tags = ["重装干员", "先锋干员", "高级资深干员", "支援", "支援机械"]
        results = self.test_class.recruit_cal(recruit_tags)
        print(f"顺序为 {self.test_class.recruit_order}")
        print(results.keys())
        for i in results:
            for result in results[i]:
                for agent in result["result"]:
                    print(f"{i}  {result['tag']} {agent['name']}")


if __name__ == "__main__":
    unittest.main()
