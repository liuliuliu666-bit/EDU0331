from typing import Any

from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.task.action.base import Action, ActionResult
from atguigu.task.action.customer.shared import (
    REFUND_TYPE_LABEL,
    create_refund_request,
    fetch_order,
    normalize_refund_type,
)


class ActionCreateRefund(Action):
    name = "action_create_refund"

    async def run(self, action_kwargs: dict[str, Any], state: DialogueState) -> ActionResult:
        slots = state.active_task.slots
        order_number = (slots.get("order_number") or "").strip()
        refund_reason = (slots.get("refund_reason") or "").strip()
        refund_type = normalize_refund_type(slots.get("refund_type") or "")

        payload = await fetch_order(state, order_number)
        if payload is None:
            return ActionResult(
                messages=[BotMessage(text="我暂时没有查到该订单，请确认订单号是否正确，稍后再试。")]
            )

        items = payload.get("orderItems") or []
        item = items[0] if items else {}
        order_item_id = item.get("orderItemId")
        if order_item_id is None:
            return ActionResult(
                messages=[BotMessage(text="该订单还没有可退款的明细，暂时无法提交退款申请。")]
            )
        payable_amount = float(item.get("payableAmount") or 0)

        result = await create_refund_request(
            state,
            order_item_id=int(order_item_id),
            refund_type=refund_type,
            refund_reason=refund_reason or "用户主动申请",
            apply_amount=payable_amount,
        )
        if result is None:
            return ActionResult(
                messages=[
                    BotMessage(
                        text="退款申请提交失败，可能是该订单当前状态不允许退款，或已存在处理中的退款申请。"
                    )
                ]
            )

        refund_no = str(result.get("refundNo") or "")
        status = str(result.get("refundStatusCode") or "pending")
        type_label = REFUND_TYPE_LABEL.get(refund_type, refund_type)
        text = (
            f"好的，订单 {order_number} 的退款申请已提交（退款编号：{refund_no}，"
            f"类型：{type_label}，原因：{refund_reason or '用户主动申请'}）。"
            "退款金额和到账时间会由客服审核后处理，请耐心等待。"
        )
        return ActionResult(
            messages=[BotMessage(text=text)],
            updated_slots={
                "refund_no": refund_no,
                "refund_status": status,
                "refund_type": refund_type,
            },
        )
