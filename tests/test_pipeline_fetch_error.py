# -*- coding: utf-8 -*-
"""Regression tests for pipeline data-fetch error handling."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.enums import ReportType
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

    def test_analyze_stock_keeps_manual_name_when_realtime_name_is_normalized_placeholder(self):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.config = SimpleNamespace(
            stock_name_overrides={"600519": "贵州茅台"},
            agent_mode=False,
            agent_skills=[],
            fundamental_stage_timeout_seconds=1.5,
            enable_realtime_quote=False,
            report_language="zh",
        )
        pipeline.fetcher_manager = MagicMock()
        pipeline.fetcher_manager.get_realtime_quote.return_value = SimpleNamespace(
            name="600519",
            price=1688.0,
            source=SimpleNamespace(value="mock"),
        )
        pipeline.fetcher_manager.get_chip_distribution.return_value = None
        pipeline.fetcher_manager.get_fundamental_context.return_value = {
            "source_chain": [],
            "coverage": {},
        }
        pipeline.fetcher_manager.build_failed_fundamental_context.return_value = {
            "source_chain": [],
            "coverage": {},
        }
        pipeline.fetcher_manager.get_belong_boards.return_value = []
        pipeline.db = MagicMock()
        pipeline.db.get_data_range.return_value = []
        pipeline.db.get_analysis_context.return_value = {
            "code": "SH600519",
            "today": {},
            "yesterday": {},
        }
        pipeline.search_service = SimpleNamespace(is_available=False, news_window_days=3)
        pipeline.social_sentiment_service = SimpleNamespace(is_available=False)
        pipeline.trend_analyzer = MagicMock()
        pipeline.analyzer = MagicMock()
        pipeline.analyzer.analyze.return_value = None
        pipeline.save_context_snapshot = False

        result = StockAnalysisPipeline.analyze_stock(
            pipeline,
            "SH600519",
            ReportType.SIMPLE,
            "q1",
        )

        self.assertIsNone(result)
        pipeline.fetcher_manager.get_stock_name.assert_not_called()
        enhanced_context = pipeline.analyzer.analyze.call_args.args[0]
        self.assertEqual(enhanced_context["stock_name"], "贵州茅台")


if __name__ == "__main__":
    unittest.main()
