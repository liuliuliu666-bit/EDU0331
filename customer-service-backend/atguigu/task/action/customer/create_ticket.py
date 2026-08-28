from typing import Any

from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.task.action.base import Action, ActionResult
from atguigu.task.action.customer.shared import (
    TICKET_TYPE_LABEL,
    create_refund_request,
    create_service_ticket,
    fetch_order,
    normalize_priority,
    normalize_ticket_type,
)


class ActionCreateTicket(Action):
    name = "action_create_ticket"

    async def run(self, action_kwargs: dict[str, Any], state: DialogueState) -> ActionResult:
        slots = state.active_task.slots
        order_number = (slots.get("order_number") or "").strip()
        issue = (slots.get("issue_description") or "").strip()
        ticket_type = normalize_ticket_type(slots.get("ticket_type") or "")
        priority = normalize_priority(slots.get("priority") or "")

        payload = await fetch_order(state, order_number)
        if payload is None:
            return ActionResult(
                messages=[BotMessage(text="我暂时没有查到该订单，请确认订单号是否正确，稍后再试。")]
            )

        items = payload.get("orderItems") or []
        item = items[0] if items else {}
        order_item_id = item.get("orderItemId")
        student_id = payload.get("studentId") or item.get("studentId")
        if order_item_id is None:
            return ActionResult(
                messages=[BotMessage(text="该订单没有可关联的明细，暂时无法创建工单。")]
            )
        if student_id is None:
            return ActionResult(
                messages=[BotMessage(text="该订单没有可关联的学员，暂时无法创建工单。")]
            )
        student_id_int = int(student_id)
        order_item_id_int = int(order_item_id)

        refund_request_id = None
        if ticket_type == "refund":
            refund = await create_refund_request(
                state,
                order_item_id=int(order_item_id),
                refund_type="personal_reason",
                refund_reason=issue or "用户申请退款",
                apply_amount=float(item.get("payableAmount") or 0),
            )
            if refund is None:
                return ActionResult(
                    messages=[
                        BotMessage(
                            text="退款工单需要先有一条可关联的退款申请，但当前订单无法创建退款申请。"
                            "你可以先走“退款申请”流程。"
                        )
                    ]
                )
            refund_request_id = int(refund.get("refundRequestId"))

        result = await create_service_ticket(
            state,
            ticket_type=ticket_type,
            priority_level=priority,
            title=f"{TICKET_TYPE_LABEL.get(ticket_type, ticket_type)}-{order_number}",
            ticket_content=issue or "用户未补充问题描述",
            student_id=student_id_int,
            order_item_id=order_item_id_int,
            refund_request_id=refund_request_id,
        )
        if result is None:
            return ActionResult(
                messages=[BotMessage(text="工单提交失败，请稍后再试。")]
            )

        ticket_no = str(result.get("ticketNo") or "")
        ticket_status = str(result.get("ticketStatus") or "pending")
        type_label = TICKET_TYPE_LABEL.get(ticket_type, ticket_type)
        text = (
            f"好的，已为你创建{type_label}工单（工单编号：{ticket_no}）。"
            "客服会尽快跟进处理，你可以在“工单”里查看进度。"
        )
        return ActionResult(
            messages=[BotMessage(text=text)],
            updated_slots={
                "ticket_no": ticket_no,
                "ticket_status": ticket_status,
                "ticket_type": ticket_type,
            },
        )
