import sys
import unittest
from unittest.mock import MagicMock, patch

# Windows 中文控制台（GBK）打印干员名里的上标字符（如 ²）会 UnicodeEncodeError——
# 重配 stdout 为 UTF-8/replace，保证本机与 CI（UTF-8）都能跑。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 只 mock cv2：recruit 计算测试不需真实 OpenCV。numpy 不能 mock——import RecruitSolver
# 会连带 import arknights_mower.models，其导入时反序列化含 numpy 数组的 pickle
# （avatar.pkl 等），numpy 被 MagicMock 顶掉会炸「numpy is not a package」。
with patch.dict("sys.modules", {"cv2": MagicMock()}):
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
