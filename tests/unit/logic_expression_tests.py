import unittest

from arknights_mower.utils.logic_expression import get_logic_exp

dict_minus = {"left": "114514", "operator": "-", "right": "1919810"}


class TestLogicExpression(unittest.TestCase):
    def test_single(self):
        self.assertEqual(str(get_logic_exp({"left": "114514"})), "(114514  )")

    def test_flat(self):
        self.assertEqual(str(get_logic_exp(dict_minus)), "(114514 - 1919810)")

    def test_nested(self):
        self.assertEqual(
            str(get_logic_exp({"left": "hi", "operator": "and", "right": dict_minus})),
            "(hi and (114514 - 1919810))",
        )


if __name__ == "__main__":
    unittest.main()
