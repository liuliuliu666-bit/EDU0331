"""
定义路由
"""
import uuid
import asyncio
import json
from dataclasses import dataclass
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from atguigu.api.schemas import (
    ChatResponse,
    ChatRequest,
    ChatBotMessage,
    ChatObject,
    ChatHistoryResponse,
    NewSessionResponse,
    ChatSessionsResponse,
    SessionSummary,
)
from atguigu.domain.messages import UserMessage, ProcessedResult, MessageType, FocusedObject
from atguigu.api.dependencies import DialogueStateServiceDep

router = APIRouter()


@router.get("/")
def hello_endpoint():
    """
    接口响应层：FASTAPI自动会将接口返回的对象序列化为json格式字符串:序列化
    接口请求处理层： FASTAPI自动的将前端发送的json格式字符串反序列化成数据模型对象【数据模型出来】：反序列化

    Returns:

    """

    return {"success": "ok"}


@dataclass(slots=True)
class User:
    name: str
    age: int
    address: str


@router.get("/test", response_model=User)
def test_endpoint():
    """
    response_model:
    作用1：校验器作用
    作用2：过滤器作用
    作用3：生成丰富的接口文档信息（作用）
    Returns:

    """
    return {
        "name": "zs",
        "age": "18",
        "address": "sz",
        "card_no": "xxxxxxxabcdddddddd"
    }


@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest,
                        service: DialogueStateServiceDep):
    # 1.将接口数据模型转成领域数据模型
    user_message = _build_user_message(chat_request)

    # 2.调用service处理领域数据模型---返回的还是领域数据模型
    processed_result = await service.process_message(user_message)

    # 3. 将处理后的领域数据 模型转成接口数据模型
    chat_response = _build_chat_response(processed_result)

    return chat_response


def _build_user_message(chat_request: ChatRequest) -> UserMessage:
    """
    职责：接口数据模型转成领域数据模型
    Args:
        chat_request:

    Returns:

    """

    return UserMessage(
        sender_id=chat_request.sender_id,
        message_id=str(uuid.uuid4().hex),
        type=MessageType.OBJECT if chat_request.object is not None else MessageType.TEXT,
        text=chat_request.text,
        object=FocusedObject(
            id=chat_request.object.id,
            type=chat_request.object.type,
            title=chat_request.object.title,
            attributes=chat_request.object.attributes,
        ) if chat_request.object is not None else None
    )


def _build_chat_response(processed_result: ProcessedResult) -> ChatResponse:
    """
     职责：处理后的领域数据模型转成接口数据模型
    Args:
        processed_result:

    Returns:

    """

    return ChatResponse(
        message_id=processed_result.message_id,
        messages=[
            ChatBotMessage(
                text=bot_message.text,
                object=ChatObject(
                    id=bot_message.object.id,
                    type=bot_message.object.type,
                    title=bot_message.object.title,
                    attributes=bot_message.object.attributes
                ) if bot_message.object is not None else None
            )
            for bot_message in processed_result.messages
        ]
    )


@router.get("/api/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history_endpoint(sender_id: str,
                                    service: DialogueStateServiceDep):
    chat_history_messages = await service.get_chat_history(sender_id)

    return ChatHistoryResponse(sender_id=sender_id, messages=chat_history_messages)


@router.delete("/api/chat/turn")
async def delete_turn_endpoint(sender_id: str,
                               turn_id: str,
                               service: DialogueStateServiceDep):
    """删除该用户指定的某一轮对话记录。"""
    await service.delete_turn(sender_id, turn_id)
    return {"sender_id": sender_id, "turn_id": turn_id, "status": "cleared"}


@router.get("/api/chat/state")
async def get_chat_state_endpoint(sender_id: str,
                                  service: DialogueStateServiceDep):
    """查询当前会话状态：当前激活的业务流程、已收集槽位、被挂起的流程。"""
    return await service.get_session_state(sender_id)


@router.post("/api/chat/session", response_model=NewSessionResponse)
async def create_chat_session_endpoint(sender_id: str,
                                       service: DialogueStateServiceDep,
                                       close_current: bool = True):
    """显式开启一个新会话（默认关闭当前会话）。"""
    return await service.create_new_session(sender_id, close_current=close_current)


@router.get("/api/chat/sessions", response_model=ChatSessionsResponse)
async def list_chat_sessions_endpoint(sender_id: str,
                                      service: DialogueStateServiceDep):
    """列出该用户的全部历史会话摘要。"""
    sessions = await service.list_sessions(sender_id)
    return ChatSessionsResponse(
        sender_id=sender_id,
        sessions=[SessionSummary(**session) for session in sessions],
    )


@router.post("/api/chat/session/switch", response_model=NewSessionResponse)
async def switch_chat_session_endpoint(sender_id: str,
                                       session_id: str,
                                       service: DialogueStateServiceDep):
    """切换 / 恢复到一个历史会话作为当前会话。"""
    result = await service.switch_session(sender_id, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return NewSessionResponse(**result)


@router.post("/api/chat/stream")
async def chat_stream_endpoint(chat_request: ChatRequest,
                               service: DialogueStateServiceDep):
    """SSE 流式接口：先完整计算回复，再按字符流式返回，满足前端逐字展示需求。"""
    user_message = _build_user_message(chat_request)
    processed_result = await service.process_message(user_message)
    chat_response = _build_chat_response(processed_result)

    async def event_generator():
        yield _sse_event("meta", {"message_id": chat_response.message_id})
        for bot_message in chat_response.messages:
            text = bot_message.text or ""
            # 按小段切分，模拟逐字返回
            for i in range(0, len(text), 2):
                yield _sse_event("delta", {"text": text[i:i + 2]})
                await asyncio.sleep(0.02)
            yield _sse_event("done", {"text": text})
        yield _sse_event("finish", {"message_id": chat_response.message_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_event(event: str, data: dict) -> str:
    """构建一个 SSE 事件帧：event: xxx\\ndata: {...}\\n\\n"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
