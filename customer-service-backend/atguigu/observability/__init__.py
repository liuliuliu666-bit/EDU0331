"""对话可观测性。

对外暴露轻量级的轨迹日志能力，用于追踪一次对话（turn）内的：
意图 / 轨道路由、关键动作执行、回复生成结果与耗时。
"""

from atguigu.observability.tracelog import (
    setup_logging,
    set_trace_id,
    get_trace_id,
    start_turn,
    begin_stage,
    end_stage,
    trace,
    finish_turn,
)

__all__ = [
    "setup_logging",
    "set_trace_id",
    "get_trace_id",
    "start_turn",
    "begin_stage",
    "end_stage",
    "trace",
    "finish_turn",
]
