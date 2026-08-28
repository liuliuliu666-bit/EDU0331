from typing import Any

from atguigu.domain.state import DialogueState
from atguigu.task.action.base import Action, ActionResult
from atguigu.task.action.customer.shared import fetch_progress


class ActionLookupLearningProgress(Action):
    name = "action_lookup_learning_progress"

    async def run(self, action_kwargs: dict[str, Any], state: DialogueState) -> ActionResult:
        """查询某个班次的学习进度：出勤、视频、作业、考试。"""
        cohort_key = (state.active_task.slots.get("cohort") or "").strip()
        payload = await fetch_progress(state, cohort_key)

        if payload is None:
            return ActionResult(
                updated_slots={
                    "progress_summary": "暂时无法查到该班次的学习进度，请确认班次名称是否正确，或者先确认你是否报名了该班次。",
                }
            )

        attendance = _lines("考勤", payload.get("attendance"), "totalSessions", "presentCount", "absentCount")
        video = _lines("视频", payload.get("video"), "totalVideos", "completedVideos")
        homework = _lines("作业", payload.get("homework"), "totalHomeworks", "submittedCount", "correctedCount")
        exam = _lines("考试", payload.get("exam"), "totalExams", "submittedCount", "absentCount")
        summary = "；".join(x for x in [attendance, video, homework, exam] if x) + "。"
        return ActionResult(updated_slots={"progress_summary": summary})


def _lines(title: str, data: Any, *count_keys: str) -> str:
    if not isinstance(data, dict):
        return ""
    values = [str(data.get(key) or 0) for key in count_keys]
    split = len(count_keys) // 2
    if len(count_keys) == 3:
        return f"{title}：总{values[0]}，完成/已交{values[1]}，缺勤/未交{values[2]}"
    if len(count_keys) == 2:
        return f"{title}：总{values[0]}，完成{values[1]}"
    return f"{title}：{'、'.join(values)}"
