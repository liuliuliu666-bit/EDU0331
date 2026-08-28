from typing import Any

from atguigu.domain.state import DialogueState
from atguigu.task.action.base import Action, ActionResult
from atguigu.task.action.customer.shared import (
    ORDER_STATUS_LABEL,
    PREPAYMENT_STATUS_LABEL,
    fetch_order,
)


class ActionLookupOrderStatus(Action):
    name = "action_lookup_order_status"

    async def run(self, action_kwargs: dict[str, Any], state: DialogueState) -> ActionResult:
        """查询教育订单状态，并取出课程名 / 金额 / 支付时间 / 明细 ID。"""
        order_number = (state.active_task.slots.get("order_number") or "").strip()
        payload = await fetch_order(state, order_number)

        if payload is None:
            return ActionResult(
                updated_slots={
                    "order_status": "查询失败",
                    "order_summary": "暂时无法查到该订单信息，请确认订单号是否正确，稍后再试。",
                }
            )

        order_no = str(payload.get("orderNo") or order_number)
        status_code = str(payload.get("orderStatusCode") or "")
        status_label = ORDER_STATUS_LABEL.get(status_code, status_code or "未知")
        pay_status = None
        paid_at = None
        payment = payload.get("paymentSummary") or {}
        if isinstance(payment, dict):
            pay_status = PREPAYMENT_STATUS_LABEL.get(
                str(payment.get("paymentStatusCode") or ""),
                str(payment.get("paymentStatusCode") or ""),
            )
            paid_at = payment.get("paidAt")
        items = payload.get("orderItems") or []
        first_item = items[0] if items else {}
        course_name = first_item.get("itemName")
        order_item_id = first_item.get("orderItemId")
        payable_amount = payload.get("payableAmount")

        summary = _build_order_summary(
            order_no=order_no,
            status_label=status_label,
            course_name=course_name,
            paid_amount=payload.get("paidAmount"),
            paid_at=paid_at,
            pay_status=pay_status,
        )
        return ActionResult(
            updated_slots={
                "order_number": order_no,
                "order_status": status_label,
                "order_summary": summary,
                "order_id": str(payload.get("orderId") or ""),
                "order_item_id": str(order_item_id or ""),
                "course_name": str(course_name or ""),
            }
        )


def _build_order_summary(
    *,
    order_no: str,
    status_label: str,
    course_name: str | None,
    paid_amount,
    paid_at,
    pay_status: str | None,
) -> str:
    parts: list[str] = []
    if course_name:
        parts.append(f"报名课程：{course_name}")
    if paid_amount:
        parts.append(f"实付金额：￥{paid_amount}")
    if pay_status:
        parts.append(f"支付状态：{pay_status}")
    if paid_at:
        parts.append(f"支付时间：{paid_at}")
    return "；".join(parts) + "。" if parts else "暂无更多订单信息。"
