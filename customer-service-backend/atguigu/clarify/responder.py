import json
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.plan.turn_plan import ClarifyReason
from atguigu.chat_history.builder import ChatHistoryBuilder
from atguigu.prompt.loader import load_prompt_template_content
from atguigu.infrastructure.llm_client import llm_client


class ClarifyResponder:
    async def respond(self,
                      reason: ClarifyReason,
                      dialogue_state: DialogueState) -> list[BotMessage]:
        """
        职责：根据错误原因码，生成对应的澄清话术 返回
        Args:
            reason:
            dialogue_state:

        Returns:

        """

        # 1. 构建澄清提示词模版的输入变量
        prompt_inputs = self._build_prompt_inputs(reason, dialogue_state)

        # 2. 调用LLM生成澄清话术
        rewritten = await self._invoke(prompt_inputs)

        return rewritten

    def _build_prompt_inputs(self,
                             reason: ClarifyReason,
                             state: DialogueState) -> dict[str, Any]:
        user_message_str = ChatHistoryBuilder.build_user_message_str(state.pending_turn.user_message)
        history_str = ChatHistoryBuilder.build(state.current_session().turns[-10:])
        focused_object_json = json.dumps(state.focused_object.to_dict(),
                                         ensure_ascii=False) if state.focused_object is not None else "null"

        clarify_message_str = self.build_clarify_message(reason, state)
        return {
            "user_message": user_message_str,
            "history": history_str,
            "focused_object": focused_object_json,
            "clarify_message": clarify_message_str,
            "reason": reason.value
        }

    def build_clarify_message(
            self,
            reason: ClarifyReason,
            state: DialogueState,
    ) -> str:
        if reason is ClarifyReason.MULTIPLE_TRACKS:
            return "你这次同时提到了多个方向。我们先处理一个，你想先咨询课程信息，还是先办理业务呢？"

        if reason is ClarifyReason.MISSING_FOCUSED_OBJECT:
            return "请先发送你想咨询的对象，我再继续帮你看。"

        if reason is ClarifyReason.MISSING_KNOWLEDGE_INTENT:
            return "你是想了解课程信息、订单信息，还是退款/开课政策呢？"

        if reason is ClarifyReason.MISSING_TRACK:
            return "你是想先处理业务问题，还是先咨询信息呢？"

        if reason is ClarifyReason.MISSING_TASK_COMMANDS:
            return "你这次是想办理什么业务呢？比如查订单、查学习进度、申请退款，或者提交工单。"

        if reason is ClarifyReason.OBJECT_REQUIRES_INTENT:
            focused_object = state.focused_object
            if focused_object is not None and focused_object.type == "order":
                return "我已经收到这个订单了。你想查订单状态、申请退款，还是提交售后工单呢？"
            if focused_object is not None and focused_object.type == "cohort":
                return "我已经收到这个班次了。你想查询学习进度，还是咨询相关课程呢？"
            if focused_object is not None and focused_object.type == "series":
                return "我已经收到这个课程了。你想了解课程详情、适合人群，还是班次与价格呢？"
            if focused_object is not None and focused_object.type == "product":
                return "我已经收到这个对象了。你想进一步了解它的相关信息，还是办理相关业务呢？"

        return "我还需要再确认一下你的意思，你可以换个更具体的说法告诉我。"

    async def _invoke(self, prompt_inputs: dict[str, Any]) -> list[BotMessage]:

        # 1. 加载提示词模版
        prompt_template_str = load_prompt_template_content("clarify_respond")

        # 2. 定义提示词模版对象
        prompt_template = PromptTemplate.from_template(template=prompt_template_str, template_format="jinja2")

        # 3. 定义chain
        chain = prompt_template | llm_client | StrOutputParser()

        # 4. 调用chain
        rewritten = await  chain.ainvoke(prompt_inputs)

        return [BotMessage(text=rewritten)]
