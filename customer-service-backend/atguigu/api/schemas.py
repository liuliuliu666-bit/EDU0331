"""
定义接口数据模型：和前端进行交互
继承BaseModel:在运行期间完成类型的校验和类型的转换
"""
from typing import Any

from pydantic import BaseModel, field_validator

from atguigu.domain.messages import ChatHistoryMessage


class ChatObject(BaseModel):
    id: str  # 商品编号 or  订单编号
    title: str  # 商品标题 or  订单标题
    type: str  # 点击的商品卡片 type:"product" 点击的是订单卡片 type:"order"
    attributes: dict[str, Any]  # 商品or订单的额外信息

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, value: Any) -> str:
        """兼容前端把班次/课程 ID 以数字直接发送的情况。"""
        return str(value) if value is not None else ""


class ChatBotMessage(BaseModel):
    text: str  # 机器人回复的内容（当下用的属性）
    object: ChatObject | None = None  # 后续扩展集成的属性


class ChatRequest(BaseModel):
    """
    聊天请求接口数据模型
    """
    sender_id: str
    text: str | None = None
    object: ChatObject | None = None


class ChatResponse(BaseModel):
    """
    聊天响应接口数据模型
    """
    message_id: str
    messages: list[ChatBotMessage]


class ChatHistoryResponse(BaseModel):
    sender_id: str
    messages: list[ChatHistoryMessage]


class NewSessionResponse(BaseModel):
    sender_id: str
    session_id: str
    created_at: float | None = None


class SessionSummary(BaseModel):
    session_id: str
    current: bool
    started_at: float
    activated_at: float
    closed_at: float | None = None
    turn_count: int


class ChatSessionsResponse(BaseModel):
    sender_id: str
    sessions: list[SessionSummary]
