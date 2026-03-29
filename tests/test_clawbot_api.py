# -*- coding: utf-8 -*-
"""Tests for the ClawBot bridge API."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from fastapi import HTTPException

from api.app import create_app
from api.v1.endpoints.clawbot import ClawBotMessageRequest, handle_clawbot_message


def test_openapi_includes_clawbot_message_path():
    app = create_app()
    assert "/api/v1/clawbot/message" in app.openapi()["paths"]


def test_clawbot_message_routes_to_analysis_and_formats_text():
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_001",
        stock_code="600519",
        stock_name="贵州茅台",
        report={
            "summary": {
                "analysis_summary": "趋势保持强势，回调可分批关注。",
                "operation_advice": "持有",
                "trend_prediction": "看多",
                "sentiment_score": 78,
            },
            "strategy": {
                "ideal_buy": "1820",
                "stop_loss": "1760",
                "take_profit": "1950",
            },
        },
    )

    with patch(
        "api.v1.endpoints.clawbot.CommandDispatcher._resolve_stock_code_from_text",
        return_value="600519",
    ), patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            ClawBotMessageRequest(message="帮我分析贵州茅台", mode="analysis")
        )

    assert response.success is True
    assert response.mode == "analysis"
    assert response.query_id == "query_clawbot_001"
    assert response.stock_code == "600519"
    assert "贵州茅台（600519）" in response.text
    assert "操作建议：持有" in response.text
    assert "关键点位：理想买点 1820；止损 1760；止盈 1950" in response.text

    args, _ = handle_analysis.call_args
    assert args[0] == "600519"
    assert args[1].notify is False
    assert args[1].original_query == "帮我分析贵州茅台"


def test_clawbot_message_routes_to_agent_with_stable_session_id():
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True,
        content="缠论视角下 600519 当前更适合等回踩确认。",
        error=None,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config), \
         patch("api.v1.endpoints.clawbot._build_executor", return_value=executor):
        response = handle_clawbot_message(
            ClawBotMessageRequest(
                message="用缠论分析 600519",
                mode="agent",
                user_id="wx_user_001",
                skills=["chan_theory"],
            )
        )

    assert response.success is True
    assert response.mode == "agent"
    assert response.session_id == "clawbot_wx_user_001"
    assert response.text == "缠论视角下 600519 当前更适合等回踩确认。"

    executor.chat.assert_called_once()
    _, kwargs = executor.chat.call_args
    assert kwargs["session_id"] == "clawbot_wx_user_001"
    assert kwargs["context"]["skills"] == ["chan_theory"]


def test_clawbot_message_returns_consistent_error_when_agent_unavailable():
    config = SimpleNamespace(is_agent_available=lambda: False)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config):
        with patch("api.v1.endpoints.clawbot._build_executor") as build_executor:
            try:
                handle_clawbot_message(
                    ClawBotMessageRequest(message="用缠论分析 600519", mode="agent")
                )
                assert False, "Expected HTTPException"
            except HTTPException as exc:
                assert exc.status_code == 400
                assert exc.detail == {
                    "error": "agent_unavailable",
                    "message": "Agent 模式未开启或未配置可用模型",
                    "detail": {"source": "agent", "mode": "agent"},
                }

    build_executor.assert_not_called()
