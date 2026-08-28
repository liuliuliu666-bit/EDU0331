import logging
import time

from atguigu.domain.messages import UserMessage, ProcessedResult, ChatHistoryMessage

from atguigu.engines.dialogue_engine import DialogueEngine
from atguigu.repository.dialogue_repository import DialogueRepository
from atguigu.chat_history.builder import ChatHistoryBuilder
from atguigu.domain.contexts import TaskContext
from atguigu.domain.state import DialogueState
from atguigu.observability import tracelog

logger = logging.getLogger("customer_service.service")


class DialogueStateService:

    def __init__(self,
                 engine: DialogueEngine,
                 repository: DialogueRepository):
        self._engine = engine
        self._repository = repository

    async def process_message(self, user_message: UserMessage) -> ProcessedResult:
        """
        职责：处理对话消息的核心入口(service)
        Args:
            user_message:

        Returns:

        """
        trace_id = user_message.message_id
        tracelog.start_turn(
            trace_id,
            sender_id=user_message.sender_id,
            type=user_message.type.value,
            text=_preview(user_message.text),
            object=_preview(user_message.object.type if user_message.object else None),
        )

        # 1. 从数据库中读取当前用户的对话状态  I/O（失败时降级为全新状态，不阻断会话）
        dialogue_state = await self._load_state_safely(user_message.sender_id)

        # 2. 引擎层使用（修改对话状态中的内容）计算
        tracelog.begin_stage("engine")
        try:
            processed_result = await self._engine.handle_message(user_message, dialogue_state)
        finally:
            tracelog.end_stage("engine")

        # 3. 修改后的对话状态内容保存到数据库中 I/O（失败时降级为告警，不影响本次回复）
        await self._save_state_safely(user_message.sender_id, dialogue_state)

        tracelog.finish_turn(
            message_count=len(processed_result.messages),
            reply=_preview(processed_result.messages[0].text if processed_result.messages else ""),
        )
        return processed_result

    async def _load_state_safely(self, sender_id: str) -> DialogueState:
        """读取会话状态；失败时降级为全新状态并记录告警，避免读库异常中断对话。"""
        try:
            return await self._repository.load_state(sender_id)
        except Exception:
            logger.warning("load_state failed, fallback to empty state. sender=%s", sender_id, exc_info=True)
            return DialogueState(sender_id=sender_id)

    async def _save_state_safely(self, sender_id: str, dialogue_state: DialogueState) -> None:
        """持久化会话状态；失败时记录告警但不向上抛，保证本次回复正常返回。"""
        try:
            await self._repository.save_state(sender_id, dialogue_state)
        except Exception:
            logger.warning("save_state failed, reply still returned. sender=%s", sender_id, exc_info=True)

    async def create_new_session(self, sender_id: str, close_current: bool = True) -> dict:
        """显式开启一个新会话，可选关闭当前会话。返回新的会话信息。"""
        state = await self._load_state_safely(sender_id)
        if close_current and state.current_session() is not None:
            state.close_current_session()
            state.reset_runtime_state_for_new_session()
        state.start_session()
        await self._save_state_safely(sender_id, state)
        return {
            "sender_id": sender_id,
            "session_id": state.current_session_id,
            "created_at": state.current_session().started_at if state.current_session() else None,
        }

    async def list_sessions(self, sender_id: str) -> list[dict]:
        """列出该用户的全部历史会话摘要。"""
        state = await self._load_state_safely(sender_id)
        current_session_id = state.current_session_id
        sessions = []
        for session in state.sessions:
            sessions.append({
                "session_id": session.session_id,
                "current": session.session_id == current_session_id,
                "started_at": session.started_at,
                "activated_at": session.activated_at,
                "closed_at": session.closed_at,
                "turn_count": len(session.turns),
            })
        return sessions

    async def switch_session(self, sender_id: str, session_id: str) -> dict | None:
        """切换 / 恢复到一个历史会话作为当前会话。会话不存在时返回 None。"""
        state = await self._load_state_safely(sender_id)
        target = next((s for s in state.sessions if s.session_id == session_id), None)
        if target is None:
            return None
        # 切到目标会话：保留历史，重置运行期任务/卡片状态，避免旧流程残留
        state.current_session_id = target.session_id
        target.activated_at = time.time()
        state.reset_runtime_state_for_new_session()
        await self._save_state_safely(sender_id, state)
        return {
            "sender_id": sender_id,
            "session_id": target.session_id,
            "created_at": target.started_at,
        }

    async def get_chat_history(self, sender_id: str) -> list[ChatHistoryMessage]:
        """
        职责： 查询该用户所有会话下的聊天内容（当前session下的历史对话）
        Args:
            sender_id:

        Returns:

        """
        state = await self._repository.load_state(sender_id)

        final_chat_history_messages = []

        for session in state.sessions:

            for turn in session.turns:
                user_message = turn.user_message

                user_chat_history_message = ChatHistoryBuilder.build_chat_history(
                    session.session_id, turn.turn_id, "user",
                    user_message.text, user_message.object)

                final_chat_history_messages.append(user_chat_history_message)

                for bot_message in turn.bot_messages:
                    bot_chat_history_message = ChatHistoryBuilder.build_chat_history(
                        session.session_id, turn.turn_id, "bot",
                        bot_message.text, bot_message.object)

                    final_chat_history_messages.append(bot_chat_history_message)

        return final_chat_history_messages

    async def get_session_state(self, sender_id: str) -> dict:
        """查询当前会话状态：当前激活的业务流程、已收集的槽位、被挂起的流程。"""
        state = await self._repository.load_state(sender_id)
        active_task: TaskContext | None = state.active_task
        return {
            "sender_id": sender_id,
            "active_flow": active_task.flow_id if active_task is not None else None,
            "slots": active_task.slots if active_task is not None else {},
            "paused_flows": [paused.flow_id for paused in state.paused_tasks],
            "session_id": state.current_session_id,
        }

    async def clear_chat_history(self, sender_id: str):
        """删除该用户的对话状态与历史记录。"""
        await self._repository.delete_state(sender_id)

    async def delete_turn(self, sender_id: str, turn_id: str):
        """删除该用户的某一轮对话记录。"""
        await self._repository.delete_turn(sender_id, turn_id)


def _preview(value: str | None, limit: int = 80) -> str | None:
    if value is None or value == "":
        return value
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
