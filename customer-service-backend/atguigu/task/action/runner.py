"""
负责：从注册中心根据action的名字找具体的Action对象，在执行找到Action对象的run方法
"""
from typing import Any
from dataclasses import dataclass, field
import time

from atguigu.domain.state import DialogueState
from atguigu.task.action.base import ActionResult
from atguigu.task.action.register import ActionRegister
from atguigu.observability import tracelog


@dataclass(slots=True)
class ActionCall:
    action_name: str
    action_kwargs: dict[str, Any] = field(default_factory=dict)


class ActionRunner:

    def __init__(self, action_register: ActionRegister):
        self.action_register = action_register

    async def run(self, action_call: ActionCall, state: DialogueState) -> ActionResult:
        """
        调用时机：流程推进器在推进流程且流程步骤是action类型的时候，会调用到
        Args:
            action_call:
            state:

        Returns:

        """
        action = self.action_register.get_action(action_call.action_name)
        started = time.perf_counter()
        try:
            action_result = await action.run(action_call.action_kwargs, state)
        except Exception:
            tracelog.trace(
                "action",
                name=action_call.action_name,
                status="error",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            raise
        tracelog.trace(
            "action",
            name=action_call.action_name,
            status="ok",
            duration_ms=(time.perf_counter() - started) * 1000,
            messages=len(action_result.messages),
            slots_updated=list(action_result.updated_slots.keys()),
        )
        return action_result
