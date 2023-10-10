import unittest
from arknights_mower.utils.character_recognize import paddle_guess_agent


class TestPaddleGuessAgent(unittest.TestCase):
    def test_one_match(self):
        self.assertEqual(paddle_guess_agent("子"), None)
        self.assertEqual(paddle_guess_agent("森"), None)
        self.assertEqual(paddle_guess_agent("叶"), None)

    def test_two_match_two(self):
        self.assertEqual(paddle_guess_agent("愧影"), "傀影")

    def test_two_match_three(self):
        self.assertEqual(paddle_guess_agent("白面"), "白面鸮")

    def test_three_match_three(self):
        self.assertEqual(paddle_guess_agent("白面鹃"), "白面鸮")

    def long_match(self):
        self.assertEqual(paddle_guess_agent("罗比塔"), "罗比菈塔")
        self.assertEqual(paddle_guess_agent("屯艾雅法拉"), None)
        self.assertEqual(paddle_guess_agent("炎熔饸"), None)
        self.assertEqual(paddle_guess_agent("屯炽艾雅法拉"), "纯烬艾雅法拉")
