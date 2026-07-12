import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from arknights_mower.solvers.report import (
    get_report_data,
    read_csv_with_encoding_fallback,
)


class TestReadCsvWithEncodingFallback(unittest.TestCase):
    """测试 read_csv_with_encoding_fallback 编码兼容性"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_csv(self, encoding: str) -> str:
        path = os.path.join(self.temp_dir, "report.csv")
        df = pd.DataFrame(
            {"col1": ["数据1", "数据2"], "col2": [1, 2]},
            index=["2026-01-01", "2026-01-02"],
        )
        df.to_csv(path, encoding=encoding)
        return path

    def test_read_utf8_csv(self):
        """能正确读取 UTF-8 编码的 CSV"""
        path = self._make_csv("utf-8")
        df = read_csv_with_encoding_fallback(path)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["col1"], "数据1")

    def test_read_gbk_csv(self):
        """能正确读取 GBK 编码的 CSV（触发回退）"""
        path = self._make_csv("gbk")
        df = read_csv_with_encoding_fallback(path)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["col1"], "数据1")

    def test_fallback_actually_uses_gbk(self):
        """验证回退路径确实走了 GBK 编码"""
        path = self._make_csv("gbk")
        # GBK 文件用 UTF-8 读取必定失败
        with self.assertRaises(UnicodeDecodeError):
            pd.read_csv(path, encoding="utf-8")
        # 回退函数应能正常读取
        df = read_csv_with_encoding_fallback(path)
        self.assertEqual(len(df), 2)

    def test_passes_kwargs(self):
        """验证额外参数能透传给 pd.read_csv"""
        path = self._make_csv("utf-8")
        df = read_csv_with_encoding_fallback(path, on_bad_lines="skip")
        self.assertEqual(len(df), 2)

    def test_read_utf8_bom_csv(self):
        """带 BOM 的 UTF-8 CSV 应被正确读取，且与无 BOM 版本列名一致

        说明：旧顺序 ("utf-8", "utf-8-sig", "gbk") 在部分 pandas 版本下会因
        utf-8 先"成功"读入、首列名残留 ``\\ufeff`` 前缀而触发 server.py 的
        ``KeyError``。改为 utf-8-sig 优先后，BOM 会被正确去除。本测试验证
        BOM 文件与无 BOM 文件读取结果（列名）完全一致，确保编码回退正确。
        """
        df = pd.DataFrame(
            {"col1": ["数据1", "数据2"], "col2": [1, 2]},
            index=["2026-01-01", "2026-01-02"],
        )
        path_bom = os.path.join(self.temp_dir, "report_bom.csv")
        df.to_csv(path_bom, encoding="utf-8-sig")
        path_plain = os.path.join(self.temp_dir, "report_plain.csv")
        df.to_csv(path_plain, encoding="utf-8")

        df_bom = read_csv_with_encoding_fallback(path_bom)
        df_plain = read_csv_with_encoding_fallback(path_plain)

        self.assertEqual(len(df_bom), 2)
        self.assertEqual(df_bom.iloc[0]["col1"], "数据1")
        # 带 BOM 与无 BOM 读取结果应完全一致（列名不应残留 BOM 前缀）
        self.assertListEqual(list(df_bom.columns), list(df_plain.columns))
        self.assertNotIn("\ufeff", df_bom.columns[0])

    def test_gbk_fallback_after_utf8_sig_fails(self):
        """GBK 文件不走 utf-8-sig 路径，正确回退到 GBK"""
        path = os.path.join(self.temp_dir, "report_gbk2.csv")
        df = pd.DataFrame(
            {"col1": ["数据1", "数据2"], "col2": [1, 2]},
            index=["2026-01-01", "2026-01-02"],
        )
        df.to_csv(path, encoding="gbk")
        df = read_csv_with_encoding_fallback(path)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["col1"], "数据1")


class TestGetReportDataEncoding(unittest.TestCase):
    """测试 get_report_data() 实际使用了编码回退"""

    @patch("arknights_mower.solvers.report.get_path")
    @patch("arknights_mower.solvers.report.logger")
    def test_get_report_data_utf8(self, mock_logger, mock_get_path):
        """get_report_data 能读取 UTF-8 编码的报告（不报错）"""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            df = pd.DataFrame(
                {"col1": ["数据1", "数据2"], "col2": [1, 2]},
                index=["2026-01-01", "2026-01-02"],
            )
            df.to_csv(path, encoding="utf-8")
            mock_get_path.return_value = path

            # get_report_data 已无 print，能正常返回 dict 即说明编码回退工作正常
            # 只要不抛出异常就说明编码回退正常工作
            result = get_report_data()
            mock_logger.debug.assert_not_called()
        finally:
            os.unlink(path)

    @patch("arknights_mower.solvers.report.get_path")
    @patch("arknights_mower.solvers.report.logger")
    def test_get_report_data_gbk(self, mock_logger, mock_get_path):
        """get_report_data 能读取 GBK 编码的报告（触发回退）"""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            df = pd.DataFrame(
                {"col1": ["数据1", "数据2"], "col2": [1, 2]},
                index=["2026-01-01", "2026-01-02"],
            )
            df.to_csv(path, encoding="gbk")
            mock_get_path.return_value = path

            result = get_report_data()
            mock_logger.debug.assert_not_called()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()