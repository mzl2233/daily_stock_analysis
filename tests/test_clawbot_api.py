# -*- coding: utf-8 -*-
"""Tests for the ClawBot bridge API."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from api.app import create_app
from api.v1.endpoints.clawbot import ClawBotMessageRequest, handle_clawbot_message


def _build_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/clawbot/message",
            "raw_path": b"/api/v1/clawbot/message",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


def _render_http_exception(exc: HTTPException) -> dict:
    app = create_app()
    handler = app.exception_handlers[HTTPException]
    response = asyncio.run(handler(_build_request(), exc))
    return json.loads(response.body)


def _render_validation_exception(exc: RequestValidationError) -> tuple[int, dict]:
    app = create_app()
    handler = app.exception_handlers[RequestValidationError]
    response = asyncio.run(handler(_build_request(), exc))
    return response.status_code, json.loads(response.body)


def test_openapi_includes_clawbot_message_path():
    app = create_app()
    schema = app.openapi()
    assert "/api/v1/clawbot/message" in schema["paths"]
    assert "422" in schema["paths"]["/api/v1/clawbot/message"]["post"]["responses"]


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
            _build_request(),
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
            _build_request(),
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


def test_clawbot_message_auto_mode_falls_back_to_agent_for_plain_english_text():
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True,
        content="请提供想分析的股票代码或名称，我再继续。",
        error=None,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config), \
         patch("api.v1.endpoints.clawbot._build_executor", return_value=executor), \
         patch("src.agent.orchestrator._extract_stock_code", return_value=None), \
         patch("api.v1.endpoints.clawbot.CommandDispatcher._resolve_stock_code_from_text", return_value=None), \
         patch("api.v1.endpoints.clawbot._handle_sync_analysis") as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message="I need advice", mode="auto", user_id="wx_user_002")
        )

    assert response.mode == "agent"
    assert response.session_id == "clawbot_wx_user_002"
    assert response.text == "请提供想分析的股票代码或名称，我再继续。"
    handle_analysis.assert_not_called()
    executor.chat.assert_called_once()


def test_clawbot_message_auto_mode_falls_back_to_agent_for_uppercase_english_text():
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True,
        content="请提供想分析的股票代码或名称，我再继续。",
        error=None,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config), \
         patch("api.v1.endpoints.clawbot._build_executor", return_value=executor), \
         patch("src.agent.orchestrator._extract_stock_code", return_value=None), \
         patch("api.v1.endpoints.clawbot.CommandDispatcher._resolve_stock_code_from_text", return_value=None), \
         patch("api.v1.endpoints.clawbot._handle_sync_analysis") as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message="I NEED ADVICE", mode="auto", user_id="wx_user_004")
        )

    assert response.mode == "agent"
    assert response.session_id == "clawbot_wx_user_004"
    assert response.text == "请提供想分析的股票代码或名称，我再继续。"
    handle_analysis.assert_not_called()
    executor.chat.assert_called_once()


@pytest.mark.parametrize(
    ("message", "analysis_code", "response_code", "stock_name"),
    [
        ("AAPL", "AAPL", "AAPL", "苹果"),
        ("NFLX", "NFLX", "NFLX", "Netflix"),
        ("PLTR", "PLTR", "PLTR", "Palantir"),
        ("hk00700", "HK00700", "00700", "腾讯控股"),
    ],
)
def test_clawbot_message_auto_mode_routes_direct_ascii_ticker_to_analysis(
    message: str,
    analysis_code: str,
    response_code: str,
    stock_name: str,
):
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_direct_ascii",
        stock_code=response_code,
        stock_name=stock_name,
        report={"summary": {}, "strategy": {}},
    )

    with patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message=message, mode="auto")
        )

    assert response.mode == "analysis"
    assert response.query_id == "query_clawbot_direct_ascii"
    assert response.stock_code == response_code
    assert response.stock_name == stock_name
    assert stock_name in response.text
    handle_analysis.assert_called_once()
    args, _ = handle_analysis.call_args
    assert args[0] == analysis_code


@pytest.mark.parametrize(
    ("message", "expected_code", "stock_name"),
    [
        ("analyze AAPL", "AAPL", "苹果"),
        ("analyze NFLX", "NFLX", "Netflix"),
    ],
)
def test_clawbot_message_auto_mode_routes_english_request_with_ascii_ticker_to_analysis(
    message: str,
    expected_code: str,
    stock_name: str,
):
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_english_ascii",
        stock_code=expected_code,
        stock_name=stock_name,
        report={"summary": {}, "strategy": {}},
    )

    with patch(
        "src.agent.orchestrator._extract_stock_code",
        return_value=expected_code,
    ), patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message=message, mode="auto")
        )

    assert response.mode == "analysis"
    assert response.query_id == "query_clawbot_english_ascii"
    assert response.stock_code == expected_code
    assert response.stock_name == stock_name
    assert stock_name in response.text
    handle_analysis.assert_called_once()
    args, _ = handle_analysis.call_args
    assert args[0] == expected_code


def test_clawbot_analysis_mode_rejects_plain_english_text():
    """mode=analysis should return unresolved_stock for non-stock plain text."""
    try:
        handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message="I need advice", mode="analysis")
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["error"] == "unresolved_stock"


def test_clawbot_message_returns_consistent_error_when_agent_unavailable():
    config = SimpleNamespace(is_agent_available=lambda: False)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config):
        with patch("api.v1.endpoints.clawbot._build_executor") as build_executor:
            try:
                handle_clawbot_message(
                    _build_request(),
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


def test_clawbot_message_validation_handler_returns_error_response_shape():
    status_code, body = _render_validation_exception(
        RequestValidationError(
            [{"loc": ("body", "message"), "msg": "Field required", "type": "missing"}]
        )
    )

    assert status_code == 422
    assert body["error"] == "validation_error"
    assert body["message"] == "请求参数验证失败"
    assert isinstance(body["detail"], list)


def test_clawbot_message_http_handler_normalizes_analysis_validation_error():
    try:
        handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message="??", mode="analysis", stock_code="??")
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert _render_http_exception(exc) == {
            "error": "validation_error",
            "message": "请输入有效的股票代码或股票名称",
            "detail": {"source": "clawbot", "mode": "analysis"},
        }


def test_clawbot_message_http_handler_wraps_executor_exception_as_agent_failed():
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config), \
         patch("api.v1.endpoints.clawbot._build_executor", side_effect=RuntimeError("executor boom")):
        try:
            handle_clawbot_message(
                _build_request(),
                ClawBotMessageRequest(
                    message="用缠论分析 600519",
                    mode="agent",
                    user_id="wx_user_003",
                )
            )
            assert False, "Expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 500
            assert _render_http_exception(exc) == {
                "error": "agent_failed",
                "message": "executor boom",
                "detail": {"source": "agent", "session_id": "clawbot_wx_user_003"},
            }


@pytest.mark.parametrize("word", ["hello", "HELLO", "Hello", "need", "NEED", "sorry", "ABOUT", "maybe"])
def test_clawbot_auto_mode_rejects_plain_english_word_as_direct_ticker(word: str):
    """Plain English words must not be treated as stock tickers (P1 fix)."""
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True, content="Fallback.", error=None,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.v1.endpoints.clawbot.get_config", return_value=config), \
         patch("api.v1.endpoints.clawbot._build_executor", return_value=executor), \
         patch("src.agent.orchestrator._extract_stock_code", return_value=None), \
         patch("api.v1.endpoints.clawbot.CommandDispatcher._resolve_stock_code_from_text", return_value=None), \
         patch("api.v1.endpoints.clawbot._handle_sync_analysis") as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message=word, mode="auto")
        )

    assert response.mode == "agent", f"'{word}' should NOT be routed to analysis"
    handle_analysis.assert_not_called()


def test_clawbot_analysis_mode_resolves_word_like_ticker():
    """mode=analysis should resolve word-like tickers (e.g. SHOP) that are
    also common English words, bypassing the exclusion list (P1 fix)."""
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_word_ticker",
        stock_code="SHOP",
        stock_name="Shopify",
        report={"summary": {}, "strategy": {}},
    )

    with patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message="SHOP", mode="analysis")
        )

    assert response.success is True
    assert response.mode == "analysis"
    assert response.stock_code == "SHOP"
    handle_analysis.assert_called_once()


def test_clawbot_auto_mode_routes_analyze_word_like_ticker_to_analysis():
    """In auto mode, 'analyze SHOP' should route to analysis, not Agent (P1 fix)."""
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_analyze_shop",
        stock_code="SHOP",
        stock_name="Shopify",
        report={"summary": {}, "strategy": {}},
    )

    with patch(
        "src.agent.orchestrator._extract_stock_code",
        return_value="SHOP",
    ), patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message="analyze SHOP", mode="auto")
        )

    assert response.mode == "analysis"
    assert response.stock_code == "SHOP"
    handle_analysis.assert_called_once()


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("analyze F", "F"),
        ("analyze T", "T"),
    ],
)
def test_clawbot_auto_mode_routes_single_letter_ticker_in_text(
    message: str,
    expected_code: str,
):
    """Single-letter tickers embedded in NL text should pass the stock-hint
    gate in auto mode (P2 fix)."""
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_single_letter",
        stock_code=expected_code,
        stock_name=expected_code,
        report={"summary": {}, "strategy": {}},
    )

    with patch(
        "src.agent.orchestrator._extract_stock_code",
        return_value=expected_code,
    ), patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message=message, mode="auto")
        )

    assert response.mode == "analysis"
    assert response.stock_code == expected_code
    handle_analysis.assert_called_once()


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("analyze aapl", "AAPL"),
        ("analyze nflx", "NFLX"),
    ],
)
def test_clawbot_auto_mode_resolves_lowercase_ticker_in_free_text(
    message: str,
    expected_code: str,
):
    """Lowercase tickers in NL text should be accepted by the stock-hint gate (P2 fix)."""
    analysis_result = SimpleNamespace(
        query_id="query_clawbot_lower",
        stock_code=expected_code,
        stock_name=expected_code,
        report={"summary": {}, "strategy": {}},
    )

    with patch(
        "src.agent.orchestrator._extract_stock_code",
        return_value=expected_code,
    ), patch(
        "api.v1.endpoints.clawbot._handle_sync_analysis",
        return_value=analysis_result,
    ) as handle_analysis:
        response = handle_clawbot_message(
            _build_request(),
            ClawBotMessageRequest(message=message, mode="auto")
        )

    assert response.mode == "analysis"
    assert response.stock_code == expected_code
    handle_analysis.assert_called_once()


def test_clawbot_message_rejects_request_when_secret_mismatch():
    """When CLAWBOT_SECRET is set, mismatched header should return 401."""
    import os
    from starlette.datastructures import Headers

    def _build_request_with_header(secret_value: str) -> Request:
        encoded = secret_value.encode()
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/clawbot/message",
                "raw_path": b"/api/v1/clawbot/message",
                "query_string": b"",
                "headers": [(b"x-clawbot-secret", encoded)],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            }
        )

    with patch.dict(os.environ, {"CLAWBOT_SECRET": "correct_secret"}):
        # Wrong secret → 401
        try:
            handle_clawbot_message(
                _build_request_with_header("wrong_secret"),
                ClawBotMessageRequest(message="分析茅台", mode="auto"),
            )
            assert False, "Expected HTTPException 401"
        except HTTPException as exc:
            assert exc.status_code == 401
            assert exc.detail["error"] == "unauthorized"

        # Correct secret → proceeds past auth (agent unavailable → 400 is fine)
        config = SimpleNamespace(is_agent_available=lambda: False)
        with patch("api.v1.endpoints.clawbot.get_config", return_value=config):
            try:
                handle_clawbot_message(
                    _build_request_with_header("correct_secret"),
                    ClawBotMessageRequest(message="分析茅台", mode="auto"),
                )
            except HTTPException as exc:
                assert exc.status_code != 401, "Should not get 401 with correct secret"


def test_clawbot_message_allows_request_when_no_secret_configured():
    """When CLAWBOT_SECRET is not set, all requests should proceed past auth."""
    import os

    env_without_secret = {k: v for k, v in os.environ.items() if k != "CLAWBOT_SECRET"}
    with patch.dict(os.environ, env_without_secret, clear=True):
        config = SimpleNamespace(is_agent_available=lambda: False)
        with patch("api.v1.endpoints.clawbot.get_config", return_value=config):
            try:
                handle_clawbot_message(
                    _build_request(),
                    ClawBotMessageRequest(message="分析茅台", mode="auto"),
                )
            except HTTPException as exc:
                assert exc.status_code != 401, "No secret configured, should not get 401"
