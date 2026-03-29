# -*- coding: utf-8 -*-
"""
ClawBot plain-text bridge endpoint.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.v1.endpoints.agent import _build_executor
from api.v1.endpoints.analysis import _handle_sync_analysis, _resolve_and_normalize_input
from api.v1.schemas.analysis import AnalysisResultResponse, AnalyzeRequest
from api.v1.schemas.common import ErrorResponse
from bot.dispatcher import CommandDispatcher
from src.config import get_config

router = APIRouter()
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_DIRECT_STOCK_TOKEN_RE = re.compile(
    r"^(?:\d{5,6}|(?:SH|SZ|SS)\d{6}|HK\d{1,5}|\d{6}\.(?:SH|SZ|SS)|\d{1,5}\.HK|[A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?)$",
    re.IGNORECASE,
)


class ClawBotMessageRequest(BaseModel):
    """Request shape for the ClawBot text bridge."""

    message: str = Field(..., min_length=1, max_length=4000, description="微信/ClawBot 原始文本消息")
    mode: Literal["auto", "analysis", "agent"] = Field(
        "auto",
        description="auto=优先走分析，无法识别股票时回退 Agent；analysis=只走分析；agent=只走 Agent",
    )
    user_id: Optional[str] = Field(None, description="ClawBot 侧用户 ID，用于生成稳定 session_id")
    session_id: Optional[str] = Field(None, description="显式指定的会话 ID，优先于 user_id")
    stock_code: Optional[str] = Field(None, description="可选的显式股票代码；传入后优先使用")
    report_type: str = Field(
        "detailed",
        pattern="^(simple|detailed|full|brief)$",
        description="分析报告类型",
    )
    force_refresh: bool = Field(False, description="是否强制刷新行情与报告缓存")
    notify: bool = Field(False, description="是否复用现有通知链路发送推送，默认关闭")
    skills: Optional[List[str]] = Field(None, description="Agent 技能 ID 列表，可选")
    context: Optional[Dict[str, Any]] = Field(None, description="传递给 Agent 的上下文，可选")


class ClawBotMessageResponse(BaseModel):
    """Normalized ClawBot response."""

    success: bool = True
    mode: Literal["analysis", "agent"]
    text: str
    session_id: Optional[str] = None
    query_id: Optional[str] = None
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None


def _raise_clawbot_error(
    status_code: int,
    error: str,
    message: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error,
            "message": message,
            "detail": detail,
        },
    )


def _collapse_text(text: Optional[str], max_chars: int = 180) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _build_agent_session_id(request: ClawBotMessageRequest) -> str:
    if request.session_id:
        return request.session_id
    if request.user_id:
        return f"clawbot_{request.user_id}"
    return str(uuid.uuid4())


def _should_use_nl_stock_resolution(request: ClawBotMessageRequest) -> bool:
    if request.mode != "auto":
        return True
    return bool(_CJK_RE.search(request.message or ""))


def _resolve_direct_auto_stock_code(message: str) -> Optional[str]:
    stripped = (message or "").strip()
    if not stripped or re.search(r"\s", stripped):
        return None
    if not _DIRECT_STOCK_TOKEN_RE.fullmatch(stripped):
        return None

    normalized = stripped.upper()
    if normalized.isalpha() and "." not in normalized:
        from src.data.stock_mapping import STOCK_NAME_MAP

        if normalized not in STOCK_NAME_MAP:
            return None

    return _resolve_and_normalize_input(stripped)


def _resolve_stock_from_request(request: ClawBotMessageRequest) -> Optional[str]:
    if request.stock_code:
        return _resolve_and_normalize_input(request.stock_code)

    if request.mode == "auto":
        direct_code = _resolve_direct_auto_stock_code(request.message)
        if direct_code:
            return direct_code

    if not _should_use_nl_stock_resolution(request):
        return None

    from src.agent.orchestrator import _extract_stock_code

    extracted_code = _extract_stock_code(request.message)
    if extracted_code:
        return _resolve_and_normalize_input(extracted_code)

    resolved = CommandDispatcher._resolve_stock_code_from_text(request.message)
    if resolved:
        return _resolve_and_normalize_input(resolved)

    return None


def _format_analysis_text(result: AnalysisResultResponse) -> str:
    report = result.report if isinstance(result.report, dict) else {}
    meta = report.get("meta") or {}
    summary = report.get("summary") or {}
    strategy = report.get("strategy") or {}

    stock_code = result.stock_code or meta.get("stock_code") or ""
    stock_name = result.stock_name or meta.get("stock_name") or stock_code
    title = stock_name if not stock_code or stock_name == stock_code else f"{stock_name}（{stock_code}）"

    lines = [title]

    if summary.get("operation_advice"):
        lines.append(f"操作建议：{summary['operation_advice']}")
    if summary.get("trend_prediction"):
        lines.append(f"趋势判断：{summary['trend_prediction']}")
    if summary.get("sentiment_score") is not None:
        lines.append(f"情绪评分：{summary['sentiment_score']}")

    analysis_summary = _collapse_text(summary.get("analysis_summary"))
    if analysis_summary:
        lines.append(f"摘要：{analysis_summary}")

    key_levels: List[str] = []
    for label, key in (
        ("理想买点", "ideal_buy"),
        ("第二买点", "secondary_buy"),
        ("止损", "stop_loss"),
        ("止盈", "take_profit"),
    ):
        value = strategy.get(key)
        if value not in (None, "", "N/A"):
            key_levels.append(f"{label} {value}")
    if key_levels:
        lines.append("关键点位：" + "；".join(key_levels))

    return "\n".join(lines)


def _run_analysis(request: ClawBotMessageRequest, stock_code: str) -> ClawBotMessageResponse:
    analyze_request = AnalyzeRequest(
        stock_code=stock_code,
        report_type=request.report_type,
        force_refresh=request.force_refresh,
        async_mode=False,
        original_query=request.message,
        selection_source="manual",
        notify=request.notify,
    )

    result = _handle_sync_analysis(stock_code, analyze_request)

    return ClawBotMessageResponse(
        mode="analysis",
        text=_format_analysis_text(result),
        query_id=result.query_id,
        stock_code=result.stock_code,
        stock_name=result.stock_name,
    )


def _run_agent(request: ClawBotMessageRequest) -> ClawBotMessageResponse:
    config = get_config()
    if not config.is_agent_available():
        _raise_clawbot_error(
            400,
            "agent_unavailable",
            "Agent 模式未开启或未配置可用模型",
            {"source": "agent", "mode": request.mode},
        )

    skills = request.skills
    session_id = _build_agent_session_id(request)
    try:
        executor = _build_executor(config, skills or None)
        ctx = dict(request.context or {})
        if skills is not None:
            ctx["skills"] = skills

        result = executor.chat(
            message=request.message,
            session_id=session_id,
            context=ctx,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_clawbot_error(
            500,
            "agent_failed",
            str(exc) or "Agent 执行失败",
            {"source": "agent", "session_id": session_id},
        )

    if not result.success:
        _raise_clawbot_error(
            500,
            "agent_failed",
            result.error or "Agent 执行失败",
            {"source": "agent", "session_id": session_id},
        )

    return ClawBotMessageResponse(
        mode="agent",
        text=result.content,
        session_id=session_id,
    )


@router.post(
    "/message",
    response_model=ClawBotMessageResponse,
    responses={
        200: {"description": "ClawBot 文本响应", "model": ClawBotMessageResponse},
        400: {"description": "请求参数错误或能力不可用", "model": ErrorResponse},
        422: {"description": "请求体验证失败", "model": ErrorResponse},
        500: {"description": "分析或 Agent 执行失败", "model": ErrorResponse},
    },
    summary="ClawBot 文本桥接",
    description="为微信/openclaw ClawBot 提供稳定的文本入参与文本出参桥接层。",
)
def handle_clawbot_message(request: ClawBotMessageRequest) -> ClawBotMessageResponse:
    """
    Bridge WeChat/openclaw ClawBot requests to existing analysis/agent capabilities.
    """
    try:
        if not request.message.strip():
            _raise_clawbot_error(
                400,
                "validation_error",
                "message 不能为空或仅包含空白字符",
                {"field": "message"},
            )

        if request.mode in {"auto", "analysis"}:
            stock_code = _resolve_stock_from_request(request)
            if stock_code:
                return _run_analysis(request, stock_code)
            if request.mode == "analysis":
                _raise_clawbot_error(
                    400,
                    "unresolved_stock",
                    "未能从消息中识别股票代码或股票名称",
                    {"source": "analysis", "message": request.message},
                )

        if request.mode == "auto":
            config = get_config()
            if not config.is_agent_available():
                _raise_clawbot_error(
                    400,
                    "unsupported_request",
                    "未能从消息中识别股票代码或股票名称，且 Agent 模式未开启",
                    {"source": "clawbot", "mode": "auto"},
                )

        return _run_agent(request)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict) and "detail" not in detail:
            normalized_detail = {
                "error": detail.get("error") or "internal_error",
                "message": detail.get("message") or "请求处理失败",
                "detail": {
                    **{k: v for k, v in detail.items() if k not in ("error", "message")},
                    "source": detail.get("source") or "clawbot",
                    "mode": request.mode,
                },
            }
            raise HTTPException(status_code=exc.status_code, detail=normalized_detail) from exc
        raise
