# -*- coding: utf-8 -*-
"""Regression tests for pipeline data-fetch error handling."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.core.pipeline import StockAnalysisPipeline


class PipelineFetchErrorTestCase(unittest.TestCase):
    """`fetch_and_save_stock_data` should preserve the original exception."""

    def test_fetch_and_save_handles_stock_name_lookup_failure(self):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.side_effect = RuntimeError("name lookup failed")

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(pipeline, "600519")

        self.assertFalse(success)
        self.assertIn("name lookup failed", error or "")

    def test_fetch_and_save_uses_manual_stock_name_without_remote_lookup(self):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.config = SimpleNamespace(stock_name_overrides={"600519": "贵州茅台"})
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.db.has_today_data.return_value = True

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(pipeline, "600519")

        self.assertTrue(success)
        self.assertIsNone(error)
        pipeline.fetcher_manager.get_stock_name.assert_not_called()


if __name__ == "__main__":
    unittest.main()
