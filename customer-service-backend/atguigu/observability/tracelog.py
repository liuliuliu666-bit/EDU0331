"""轻量级轨迹日志。

核心思路：
- 使用 ``contextvars`` 绑定一次回复（turn）的 trace_id，且该值可随异步调用链自动传播，
  因此在 service / engine / action 任意一层记录日志，都能关联到同一条用户消息。
- 提供 ``start_turn`` / ``begin_stage`` / ``end_stage`` / ``trace`` / ``finish_turn``
  几个低侵入的钩子，在关键节点输出结构化日志（事件名 + 关键字段 + 耗时）。

该模块不引入任何第三方依赖，直接使用标准库 ``logging``。
"""

from __future__ import annotations

import contextvars
import logging
import time
from typing import Any, Mapping

logger = logging.getLogger("customer_service.trace")

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")
_turn_start: contextvars.ContextVar[float] = contextvars.ContextVar("turn_start", default=0.0)
_stage_start: contextvars.ContextVar[dict[str, float]] = contextvars.ContextVar(
    "stage_start", default={}
)


class _TraceFilter(logging.Filter):
    """向日志记录注入 trace_id，便于按一次对话聚合检索。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """在应用启动时调用，输出带 trace_id 的结构化行。可安全重复调用。"""
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "_trace_configured", False):
            return

    handler = logging.StreamHandler()
    handler.addFilter(_TraceFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s [trace=%(trace_id)s] %(message)s"
        )
    )
    handler._trace_configured = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if root.level > level or root.level == logging.WARNING:
        root.setLevel(level)


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id or "-")


def get_trace_id() -> str:
    return _trace_id.get()


def start_turn(trace_id: str, **context: Any) -> None:
    """开启一次对话的轨迹，记录本次消息的上下文。"""
    set_trace_id(trace_id)
    _turn_start.set(time.perf_counter())
    _stage_start.set({})
    logger.info("turn_start %s", _fmt(context))


def begin_stage(stage_name: str, **context: Any) -> None:
    """标记一个阶段的开始，重复调用会以最后一次为准。"""
    _stage_start.get()[stage_name] = time.perf_counter()
    logger.info("stage_begin stage=%s %s", stage_name, _fmt(context))


def end_stage(stage_name: str, **context: Any) -> None:
    """结束一个阶段并输出其耗时（毫秒）。"""
    starts = _stage_start.get()
    started = starts.pop(stage_name, None)
    duration_ms = (time.perf_counter() - started) * 1000 if started else None
    if duration_ms is not None:
        logger.info(
            "stage_end stage=%s duration_ms=%.1f %s",
            stage_name,
            duration_ms,
            _fmt(context),
        )
    else:
        logger.info("stage_end stage=%s %s", stage_name, _fmt(context))


def trace(event: str, **fields: Any) -> None:
    """记录一个关键事件。"""
    logger.info("%s %s", event, _fmt(fields))


def finish_turn(**summary: Any) -> None:
    """结束一次对话的轨迹，输出整轮耗时与结果概览。"""
    started = _turn_start.get()
    duration_ms = (time.perf_counter() - started) * 1000 if started else None
    if duration_ms is not None:
        logger.info("turn_end duration_ms=%.1f %s", duration_ms, _fmt(summary))
    else:
        logger.info("turn_end %s", _fmt(summary))


def _fmt(mapping: Mapping[str, Any] | None) -> str:
    if not mapping:
        return ""
    return " ".join(f"{k}={v!r}" for k, v in mapping.items())
