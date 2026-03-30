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
# Stricter gate for NL stock resolution: require 2+ chars for alpha-only
# tokens so that single letters like "I" don't trigger stock code extraction.
# Uses IGNORECASE so lowercase tickers like "aapl" in free text are accepted.
_STOCK_HINT_TOKEN_RE = re.compile(
    r"^(?:\d{5,6}|(?:SH|SZ|SS)\d{6}|HK\d{1,5}|\d{6}\.(?:SH|SZ|SS)|\d{1,5}\.HK|[A-Za-z]{2,5}(?:\.[A-Za-z]{1,2})?)$",
    re.IGNORECASE,
)
# Frequent English words (1–5 letters) excluded from the direct single-token
# auto-resolution fast path so that conversational messages like "hello" or
# "need" are not misrouted to stock analysis.  The list intentionally trades
# recall for precision—an unlisted word still falls through to the NL
# heuristic path which handles it gracefully.
_PLAIN_WORD_EXCLUSIONS: frozenset = frozenset({
    # 1–2 letters
    "a", "am", "an", "as", "at", "be", "by", "do", "go", "he", "hi",
    "i", "if", "in", "is", "it", "me", "my", "no", "of", "oh", "ok",
    "on", "or", "so", "to", "up", "us", "we",
    # 3 letters
    "add", "ago", "all", "and", "any", "are", "ask", "bad", "big",
    "bit", "but", "buy", "can", "cut", "day", "did", "end", "eye",
    "far", "few", "fit", "fix", "fly", "for", "fun", "get", "god",
    "got", "guy", "had", "has", "her", "hey", "him", "his", "hit",
    "hot", "how", "its", "job", "joy", "key", "kid", "law", "lay",
    "led", "let", "lie", "lot", "low", "mad", "man", "map", "may",
    "men", "met", "mix", "mom", "net", "new", "nor", "not", "now",
    "odd", "off", "old", "one", "our", "out", "own", "pay", "per",
    "put", "ran", "raw", "red", "rid", "run", "sad", "sat", "saw",
    "say", "sea", "see", "set", "she", "sir", "sit", "six", "sky",
    "son", "sub", "sum", "sun", "tag", "tax", "ten", "the", "tie",
    "tip", "too", "top", "try", "two", "use", "van", "via", "war",
    "was", "way", "web", "who", "why", "win", "won", "yes", "yet",
    "you",
    # 4 letters
    "able", "also", "area", "away", "back", "base", "been", "best",
    "body", "book", "both", "call", "came", "card", "care", "case",
    "city", "code", "come", "cool", "copy", "cost", "data", "date",
    "deal", "dear", "deep", "does", "done", "down", "draw", "drop",
    "drug", "each", "earn", "ease", "east", "easy", "edit", "else",
    "even", "ever", "face", "fact", "fail", "fair", "fall", "fast",
    "fear", "feel", "file", "fill", "film", "find", "fine", "fire",
    "flat", "food", "foot", "form", "free", "from", "fuel", "full",
    "fund", "gain", "game", "gave", "girl", "give", "glad", "goes",
    "gold", "gone", "good", "grew", "grow", "guys", "half", "hand",
    "hang", "hard", "hate", "have", "head", "hear", "heat", "help",
    "here", "hero", "hide", "high", "hill", "hold", "hole", "home",
    "hope", "host", "hour", "huge", "hung", "hurt", "idea", "info",
    "into", "item", "join", "jump", "just", "keen", "keep", "kept",
    "kill", "kind", "king", "knew", "know", "lack", "lady", "laid",
    "land", "last", "late", "lead", "left", "lend", "less", "life",
    "lift", "like", "line", "link", "list", "live", "load", "lock",
    "logo", "long", "look", "lord", "lose", "loss", "lost", "lots",
    "love", "luck", "made", "mail", "main", "make", "male", "many",
    "mark", "mass", "mean", "meet", "mind", "mine", "miss", "mode",
    "mood", "more", "most", "move", "much", "must", "myth", "name",
    "near", "neat", "need", "news", "next", "nice", "nine", "node",
    "none", "norm", "nose", "note", "okay", "once", "only", "onto",
    "open", "oral", "over", "pace", "pack", "page", "paid", "pair",
    "park", "part", "pass", "past", "path", "peak", "pick", "plan",
    "play", "plus", "poem", "poll", "pool", "poor", "post", "pour",
    "pull", "pump", "pure", "push", "quit", "race", "rain", "rank",
    "rare", "rate", "read", "real", "rely", "rent", "rest", "rich",
    "ride", "ring", "rise", "risk", "road", "rock", "role", "roll",
    "room", "root", "rose", "rule", "rush", "safe", "said", "sake",
    "sale", "same", "sand", "sang", "save", "seal", "seat", "seed",
    "seek", "seem", "seen", "self", "sell", "send", "sent", "ship",
    "shop", "shot", "show", "shut", "sick", "side", "sign", "sing",
    "site", "size", "skin", "slip", "slow", "snow", "soft", "soil",
    "sold", "sole", "some", "song", "soon", "sort", "soul", "spin",
    "spot", "star", "stay", "stem", "step", "stop", "such", "suit",
    "sure", "swim", "tail", "take", "tale", "talk", "tall", "tank",
    "tape", "task", "team", "tear", "tell", "tend", "term", "test",
    "text", "than", "that", "them", "then", "they", "thin", "this",
    "thus", "till", "time", "tiny", "tire", "told", "tone", "took",
    "tool", "tops", "tore", "torn", "tour", "town", "trap", "tree",
    "trim", "trip", "true", "tube", "tune", "turn", "twin", "type",
    "ugly", "undo", "unit", "upon", "urge", "used", "user", "vary",
    "vast", "very", "view", "vote", "wage", "wait", "wake", "walk",
    "wall", "want", "warm", "warn", "wash", "wave", "weak", "wear",
    "week", "well", "went", "were", "west", "what", "when", "whom",
    "wide", "wife", "wild", "will", "wind", "wine", "wire", "wise",
    "wish", "with", "wood", "word", "wore", "work", "worn", "wrap",
    "yard", "yeah", "year", "your", "zero", "zone",
    # 5 letters
    "about", "above", "abuse", "added", "admit", "adopt", "adult",
    "after", "again", "agent", "agree", "ahead", "alarm", "album",
    "alert", "alive", "allow", "alone", "along", "alter", "among",
    "anger", "angle", "angry", "apart", "apply", "arena", "argue",
    "arise", "aside", "avoid", "awake", "award", "aware", "awful",
    "badly", "basic", "begin", "being", "below", "birth", "black",
    "blame", "blank", "blast", "bleed", "blend", "blind", "block",
    "blood", "blown", "board", "bonus", "bound", "brain", "brand",
    "brave", "bread", "break", "breed", "brief", "bring", "broad",
    "broke", "brown", "brush", "buddy", "build", "built", "bunch",
    "burst", "buyer", "carry", "catch", "cause", "chain", "chair",
    "chaos", "cheap", "check", "cheek", "chest", "chief", "child",
    "civil", "claim", "class", "clean", "clear", "climb", "clock",
    "clone", "close", "cloth", "cloud", "coach", "coast", "could",
    "count", "court", "cover", "crack", "craft", "crash", "crazy",
    "cream", "crime", "cross", "crowd", "cruel", "crush", "cycle",
    "daily", "dance", "death", "debug", "delay", "depth", "dirty",
    "doing", "donor", "doubt", "draft", "drain", "drama", "drawn",
    "dream", "dress", "drink", "drive", "drove", "dying", "eager",
    "early", "earth", "eight", "email", "empty", "enemy", "enjoy",
    "enter", "entry", "equal", "error", "essay", "event", "every",
    "exact", "exist", "extra", "faith", "false", "fault", "feast",
    "fewer", "fiber", "field", "fifty", "fight", "final", "first",
    "fixed", "flame", "flash", "flesh", "float", "flood", "floor",
    "fluid", "focus", "force", "forth", "found", "frame", "fraud",
    "fresh", "front", "fruit", "fully", "funny", "giant", "given",
    "glass", "globe", "going", "grace", "grade", "grain", "grand",
    "grant", "grasp", "grass", "grave", "great", "green", "greet",
    "gross", "group", "grown", "guard", "guess", "guest", "guide",
    "guilt", "habit", "happy", "harsh", "haven", "heart", "heavy",
    "hello", "hence", "honey", "honor", "horse", "hotel", "house",
    "human", "humor", "hurry", "ideal", "image", "imply", "index",
    "inner", "input", "issue", "joint", "judge", "juice", "known",
    "label", "labor", "large", "laser", "later", "laugh", "layer",
    "learn", "lease", "least", "leave", "legal", "level", "light",
    "limit", "lived", "lobby", "local", "logic", "loose", "lover",
    "lower", "loyal", "lucky", "lunch", "magic", "major", "maker",
    "match", "maybe", "mayor", "meant", "media", "mercy", "merit",
    "metal", "might", "minor", "mixed", "model", "money", "month",
    "moral", "mount", "mouse", "mouth", "moved", "movie", "music",
    "named", "naval", "nerve", "never", "newly", "night", "noble",
    "noise", "north", "noted", "novel", "nurse", "occur", "ocean",
    "offer", "often", "onset", "order", "other", "ought", "outer",
    "owned", "owner", "paint", "panel", "panic", "paper", "party",
    "paste", "patch", "pause", "peace", "penny", "phase", "phone",
    "photo", "piece", "pilot", "pitch", "place", "plain", "plane",
    "plant", "plate", "plaza", "plead", "point", "pound", "power",
    "press", "price", "pride", "prime", "print", "prior", "prize",
    "proof", "proud", "prove", "proxy", "pulse", "punch", "pupil",
    "queen", "query", "quest", "queue", "quick", "quiet", "quite",
    "quota", "quote", "radar", "radio", "raise", "rally", "range",
    "rapid", "ratio", "reach", "react", "ready", "realm", "rebel",
    "refer", "reign", "relax", "relay", "reply", "rider", "right",
    "rigid", "rival", "river", "robot", "rocky", "rough", "round",
    "route", "royal", "rumor", "rural", "sadly", "salad", "sauce",
    "scale", "scare", "scary", "scene", "scope", "score", "sense",
    "serve", "setup", "seven", "shade", "shake", "shall", "shame",
    "shape", "share", "sharp", "shave", "sheet", "shelf", "shell",
    "shift", "shine", "shirt", "shock", "shoot", "shore", "short",
    "shout", "shown", "sight", "silly", "since", "sixth", "sixty",
    "sized", "skill", "skull", "slate", "slave", "sleep", "slice",
    "slide", "slope", "smart", "smell", "smile", "smoke", "snake",
    "solar", "solid", "solve", "sorry", "sound", "south", "space",
    "spare", "spark", "speak", "speed", "spell", "spend", "spine",
    "spite", "split", "spoke", "sport", "spray", "squad", "stack",
    "staff", "stage", "stain", "stair", "stake", "stale", "stall",
    "stamp", "stand", "stare", "start", "state", "stays", "steam",
    "steel", "steep", "steer", "stick", "stiff", "still", "stock",
    "stole", "stone", "stood", "store", "storm", "story", "stove",
    "strip", "stuck", "study", "stuff", "style", "sugar", "suite",
    "sunny", "super", "surge", "swamp", "swear", "sweat", "sweep",
    "sweet", "swept", "swift", "swing", "sword", "swore", "sworn",
    "table", "taken", "taste", "teach", "teeth", "thank", "their",
    "theme", "there", "these", "thick", "thief", "thing", "think",
    "third", "those", "three", "threw", "throw", "thumb", "tight",
    "tired", "title", "toast", "today", "token", "topic", "total",
    "touch", "tough", "tower", "toxic", "trace", "track", "trade",
    "trail", "train", "trait", "trash", "treat", "trend", "trial",
    "tribe", "trick", "tried", "troop", "truck", "truly", "trunk",
    "trust", "truth", "tumor", "twice", "twist", "ultra", "under",
    "union", "unite", "unity", "until", "upper", "upset", "urban",
    "usage", "usual", "using", "utter", "valid", "value", "venue",
    "video", "vigor", "virus", "visit", "vital", "vivid", "vocal",
    "voice", "voter", "waste", "watch", "water", "weave", "weigh",
    "weird", "whale", "wheat", "wheel", "where", "which", "while",
    "white", "whole", "whose", "wider", "woman", "women", "world",
    "worry", "worse", "worst", "worth", "would", "wound", "write",
    "wrong", "wrote", "yield", "young", "yours", "youth",
})


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
    msg = request.message or ""
    if _CJK_RE.search(msg):
        return True

    for token in re.findall(r"[A-Za-z0-9.]+", msg):
        if token.lower() in _PLAIN_WORD_EXCLUSIONS:
            continue
        if _STOCK_HINT_TOKEN_RE.fullmatch(token):
            return True

    return False


def _resolve_direct_auto_stock_code(message: str) -> Optional[str]:
    stripped = (message or "").strip()
    if not stripped or re.search(r"\s", stripped):
        return None
    if not _DIRECT_STOCK_TOKEN_RE.fullmatch(stripped):
        return None
    # Reject common English words so "hello" / "need" are not misrouted.
    if stripped.lower() in _PLAIN_WORD_EXCLUSIONS:
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
