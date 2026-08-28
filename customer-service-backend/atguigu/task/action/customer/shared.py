"""
封装教育业务后台（edu-data）通用的取数 / 写入函数。

所有需要用户身份的接口都通过 X-User-Id 请求头识别"当前学员"。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from atguigu.config.settings import settings
from atguigu.domain.state import DialogueState
from atguigu.infrastructure import http_client

logger = logging.getLogger("customer_service.edu_api")

# 教育业务 API 的请求超时（秒）：避免后端等待过久拖慢对话回复
_EDU_TIMEOUT = 15.0

# 全量在售课程列表缓存（短期，避免每次课程查询都翻多页）
_SERIES_LIST_CACHE: dict[str, Any] = {"ts": 0.0, "data": []}
_SERIES_LIST_TTL = 300.0


def _base_url() -> str:
    """获取教育业务后台的地址。"""
    return settings.edu_api_base_url.rstrip("/")


def resolve_user_id(state: DialogueState) -> str:
    """聊天 sender_id 若为纯数字则直接作为 X-User-Id，否则使用配置里的兜底学员 ID。"""
    sender_id = (state.sender_id or "").strip()
    if sender_id.isdigit():
        return sender_id
    return settings.edu_user_id


def _headers(state: DialogueState) -> dict[str, str]:
    return {"X-User-Id": resolve_user_id(state)}


def _extract_data(result: dict[str, Any] | None) -> Any:
    if isinstance(result, dict):
        return result.get("data")
    return None


async def _get(path: str, state: DialogueState) -> Any:
    """GET 教育接口，返回统一响应体里的 data。"""
    try:
        url = f"{_base_url()}{path}"
        response = await http_client.http_client.get(url, headers=_headers(state), timeout=_EDU_TIMEOUT)
        return _extract_data(response.json())
    except Exception as exc:
        logger.warning("edu-api GET failed. path=%s err=%s", path, exc)
        return None


async def _post(path: str, payload: dict[str, Any], state: DialogueState) -> dict[str, Any] | None:
    """POST 教育接口，返回统一响应体里的 data。"""
    try:
        url = f"{_base_url()}{path}"
        response = await http_client.http_client.post(
            url, json=payload, headers=_headers(state), timeout=_EDU_TIMEOUT
        )
        return _extract_data(response.json())
    except Exception as exc:
        logger.warning("edu-api POST failed. path=%s err=%s", path, exc)
        return None


def _list_of_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        value = data.get("list")
        if isinstance(value, list):
            return value
        return []
    if isinstance(data, list):
        return data
    return []


def _order_lookup_path(order_key: str) -> str:
    """订单号（ORD 开头）走按单号查询接口，纯数字走订单 ID 接口。"""
    key = (order_key or "").strip()
    if key.isdigit():
        return f"/api/v1/orders/{key}"
    return f"/api/v1/orders/by-no/{key}"


async def fetch_order(state: DialogueState, order_key: str) -> dict[str, Any] | None:
    """根据订单号 / 订单 ID 查询订单详情（含订单明细）。"""
    data = await _get(_order_lookup_path(order_key), state)
    return data if isinstance(data, dict) else None


async def fetch_my_orders(state: DialogueState) -> list[dict[str, Any]]:
    """查询当前学员的订单列表。"""
    return _list_of_payload(await _get("/api/v1/orders", state))


async def fetch_my_cohorts(state: DialogueState) -> list[dict[str, Any]]:
    """查询当前学员的班次列表。"""
    return _list_of_payload(await _get("/api/v1/me/cohorts", state))


async def resolve_cohort(state: DialogueState, cohort_key: str) -> dict[str, Any] | None:
    """把用户输入的班次（编号或名称）解析为一条班次记录。"""
    key = (cohort_key or "").strip()
    cohorts = await fetch_my_cohorts(state)
    if not cohorts:
        return None
    if key.isdigit():
        for cohort in cohorts:
            if str(cohort.get("cohortId")) == key:
                return cohort
        return None
    lowered = key.lower()
    for cohort in cohorts:
        name = str(cohort.get("cohortName") or "").lower()
        series = str(cohort.get("seriesName") or "").lower()
        if key in name or key in series or lowered in name or lowered in series:
            return cohort
    return None


async def fetch_progress(state: DialogueState, cohort_key: str) -> dict[str, Any] | None:
    """查询某个班次的学习进度（出勤/视频/作业/考试）。"""
    cohorts = await fetch_my_cohorts(state)
    cohort_id = None
    key = (cohort_key or "").strip()
    if key.isdigit():
        cohort_id = key
    else:
        matched = await resolve_cohort(state, cohort_key)
        if matched:
            cohort_id = str(matched.get("cohortId"))
    if cohort_id is None:
        return None
    data = await _get(f"/api/v1/me/cohorts/{cohort_id}/progress", state)
    return data if isinstance(data, dict) else None


async def fetch_series_list(state: DialogueState, keyword: str) -> list[dict[str, Any]]:
    """按关键字检索在售课程系列。"""
    from urllib.parse import quote

    kw = quote((keyword or "").strip())
    path = f"/api/v1/series?keyword={kw}" if kw else "/api/v1/series"
    return _list_of_payload(await _get(path, state))


async def fetch_series_by_category(state: DialogueState, category_id: int) -> list[dict[str, Any]]:
    """按课程分类 ID 检索课程系列。"""
    return _list_of_payload(
        await _get(f"/api/v1/series?categoryId={category_id}&pageSize=100", state)
    )


async def fetch_series_list_all(state: DialogueState) -> list[dict[str, Any]]:
    """分页拉取全部在售课程系列，用于本地相似匹配。"""
    now = time.time()
    if now - _SERIES_LIST_CACHE["ts"] < _SERIES_LIST_TTL and _SERIES_LIST_CACHE["data"]:
        return _SERIES_LIST_CACHE["data"]

    results: list[dict[str, Any]] = []
    total_hint = 0
    for page in range(1, 41):  # 最多取 40 页 * 100 = 4000 条，覆盖全量
        data = await _get(f"/api/v1/series?pageNo={page}&pageSize=100", state)
        page_list = _list_of_payload(data)
        if not page_list:
            break
        results.extend(page_list)
        if isinstance(data, dict) and data.get("total") is not None:
            total_hint = int(data["total"])
            if len(results) >= total_hint:
                break
    if results:
        _SERIES_LIST_CACHE["ts"] = now
        _SERIES_LIST_CACHE["data"] = results
    return results


async def fetch_cohort(state: DialogueState, cohort_id: str) -> dict[str, Any] | None:
    """查询某个班次的课程模块与课次安排（公开接口）。"""
    if not (cohort_id or "").strip():
        return None
    data = await _get(f"/api/v1/cohorts/{cohort_id}", state)
    return data if isinstance(data, dict) else None


async def fetch_me(state: DialogueState) -> dict[str, Any] | None:
    """查询当前登录学员的账号信息。"""
    data = await _get("/api/v1/me", state)
    return data if isinstance(data, dict) else None


async def fetch_student_profile(state: DialogueState) -> dict[str, Any] | None:
    """查询当前学员档案（身份/学习目标/学历/年级）。"""
    data = await _get("/api/v1/me/student-profile", state)
    return data if isinstance(data, dict) else None


async def fetch_learning_summary(state: DialogueState) -> dict[str, Any] | None:
    """查询学习总览（在学/已结课/退费班次数 + 近期学习记录）。"""
    data = await _get("/api/v1/me/learning-summary", state)
    return data if isinstance(data, dict) else None


async def fetch_my_homeworks(state: DialogueState) -> list[dict[str, Any]]:
    """查询当前学员的作业列表。"""
    return _list_of_payload(await _get("/api/v1/me/homeworks?pageSize=50", state))


async def fetch_my_exams(state: DialogueState) -> list[dict[str, Any]]:
    """查询当前学员的考试列表。"""
    return _list_of_payload(await _get("/api/v1/me/exams?pageSize=50", state))


async def fetch_my_refunds(state: DialogueState) -> list[dict[str, Any]]:
    """查询当前学员的退款申请列表。"""
    return _list_of_payload(await _get("/api/v1/refund-requests?pageSize=50", state))


async def fetch_my_tickets(state: DialogueState) -> list[dict[str, Any]]:
    """查询当前学员的工单列表。"""
    return _list_of_payload(await _get("/api/v1/service-tickets?pageSize=50", state))


async def fetch_series_detail(state: DialogueState, series_id: str) -> dict[str, Any] | None:
    data = await _get(f"/api/v1/series/{series_id}", state)
    return data if isinstance(data, dict) else None


async def fetch_series_cohorts(state: DialogueState, series_id: str) -> list[dict[str, Any]]:
    data = await _get(f"/api/v1/series/{series_id}/cohorts", state)
    return data if isinstance(data, list) else []


async def create_refund_request(
    state: DialogueState,
    *,
    order_item_id: int,
    refund_type: str,
    refund_reason: str,
    apply_amount: float,
) -> dict[str, Any] | None:
    """创建退款申请。"""
    return await _post(
        f"/api/v1/order-items/{order_item_id}/refund-requests",
        {
            "refundType": refund_type,
            "refundReason": refund_reason,
            "applyAmount": apply_amount,
        },
        state,
    )


async def create_service_ticket(
    state: DialogueState,
    *,
    ticket_type: str,
    priority_level: str,
    title: str,
    ticket_content: str,
    student_id: int,
    order_item_id: int,
    refund_request_id: int | None = None,
) -> dict[str, Any] | None:
    """创建售后 / 投诉 / 退款类工单。"""
    payload: dict[str, Any] = {
        "ticketType": ticket_type,
        "priorityLevel": priority_level,
        "ticketSource": "customer_service",
        "title": title,
        "ticketContent": ticket_content,
        "studentId": student_id,
        "orderItemId": order_item_id,
    }
    if refund_request_id is not None:
        payload["refundRequestId"] = refund_request_id
    return await _post("/api/v1/service-tickets", payload, state)


# ── 展示与归一化映射 ──────────────────────────────────────────────

ORDER_STATUS_LABEL: dict[str, str] = {
    "pending": "待支付",
    "paid": "已支付",
    "completed": "已完成",
    "cancelled": "已取消",
    "partial_refunded": "部分退款",
    "refunded": "已退款",
}

PREPAYMENT_STATUS_LABEL: dict[str, str] = {
    "pending": "待支付",
    "paid": "已支付",
    "failed": "支付失败",
    "closed": "已关闭",
}

TICKET_TYPE_LABEL: dict[str, str] = {
    "after_sales": "售后",
    "complaint": "投诉",
    "refund": "退款",
}

TICKET_TYPE_FROM_TEXT: dict[str, str] = {
    "售后": "after_sales",
    "投诉": "complaint",
    "退款": "refund",
}

TICKET_PRIORITY_FROM_TEXT: dict[str, str] = {
    "低": "low",
    "中": "medium",
    "高": "high",
    "紧急": "urgent",
}

REFUND_TYPE_LABEL: dict[str, str] = {
    "personal_reason": "个人原因",
    "course_unsatisfied": "对课程不满意",
    "schedule_conflict": "时间冲突",
    "duplicate_purchase": "重复购买",
}

REFUND_TYPE_FROM_TEXT: dict[str, str] = {
    "个人原因": "personal_reason",
    "个人": "personal_reason",
    "课程不满意": "course_unsatisfied",
    "不满意": "course_unsatisfied",
    "课程质量": "course_unsatisfied",
    "时间冲突": "schedule_conflict",
    "没时间": "schedule_conflict",
    "冲突": "schedule_conflict",
    "重复购买": "duplicate_purchase",
    "买重了": "duplicate_purchase",
    "重复": "duplicate_purchase",
}


def normalize_refund_type(text: str) -> str:
    """把用户口语化的退款类型归一化到接口枚举。"""
    value = (text or "").strip()
    if value in REFUND_TYPE_FROM_TEXT:
        return REFUND_TYPE_FROM_TEXT[value]
    lowered = value.lower()
    for keyword, code in REFUND_TYPE_FROM_TEXT.items():
        if keyword and keyword in value or keyword and keyword in lowered:
            return code
    return "personal_reason"


def normalize_ticket_type(text: str) -> str:
    """把用户口语化的工单类型归一化到接口枚举。"""
    value = (text or "").strip()
    if value in TICKET_TYPE_FROM_TEXT:
        return TICKET_TYPE_FROM_TEXT[value]
    for keyword, code in TICKET_TYPE_FROM_TEXT.items():
        if keyword and keyword in value:
            return code
    return "after_sales"


def normalize_priority(text: str) -> str:
    """把用户表达紧急程度归一化到接口枚举，默认普通。"""
    value = (text or "").strip()
    if value in TICKET_PRIORITY_FROM_TEXT:
        return TICKET_PRIORITY_FROM_TEXT[value]
    for keyword, code in TICKET_PRIORITY_FROM_TEXT.items():
        if keyword and keyword in value:
            return code
    return "medium"
