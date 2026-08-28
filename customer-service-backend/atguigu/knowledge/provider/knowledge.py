import asyncio
import json
import re
from typing import Any

from atguigu.domain.state import DialogueState
from atguigu.knowledge.provider.provider import Provider, KnowledgeChunk
from atguigu.task.action.customer.shared import (
    fetch_cohort,
    fetch_learning_summary,
    fetch_me,
    fetch_my_cohorts,
    fetch_my_exams,
    fetch_my_homeworks,
    fetch_my_orders,
    fetch_my_refunds,
    fetch_my_tickets,
    fetch_order,
    fetch_series_by_category,
    fetch_series_cohorts,
    fetch_series_detail,
    fetch_series_list,
    fetch_series_list_all,
    fetch_student_profile,
    resolve_cohort,
)


class ApiCourseProvider(Provider):
    provider_id = "api.course"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索课程系列信息；支持按关键字搜索或直接使用已点课程卡片，返回课程详情和班次价格。"""
        matched: list[dict[str, Any]] = []
        candidates = await self._resolve_candidates(state)
        for series in candidates[:3]:
            sid = str(series.get("seriesId"))
            detail = await fetch_series_detail(state, sid)
            cohorts = await fetch_series_cohorts(state, sid)
            if detail:
                matched.append({"seriesId": sid, "detail": detail, "cohorts": cohorts})

        if not matched:
            return [KnowledgeChunk(content="未检索到相关课程信息。")] + _faq_chunks()

        content = "课程与班次信息：\n" + json.dumps(matched, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]

    async def _resolve_candidates(self, state: DialogueState) -> list[dict[str, Any]]:
        """综合关键字、拆词、分类、Token匹配多种方式找到相关课程。"""
        if state.focused_object is not None and state.focused_object.type == "series":
            return [{"seriesId": str(state.focused_object.id)}]

        raw_text = state.pending_turn.user_message.text or ""
        keyword = _clean_course_keyword(_extract_keyword(state))

        candidates = await fetch_series_list(state, keyword) if keyword else []
        if not candidates and keyword:
            deduped: dict[str, dict[str, Any]] = {}
            for token in _split_keyword_tokens(keyword):
                for item in await fetch_series_list(state, token):
                    deduped.setdefault(str(item.get("seriesId")), item)
            candidates = list(deduped.values())

        if not candidates:
            candidates = await _search_series_by_category(state, raw_text or keyword)

        if not candidates and keyword:
            candidates = _rank_series(await fetch_series_list_all(state), keyword)

        return candidates


class ApiOrderProvider(Provider):
    provider_id = "api.order"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索订单信息；优先用卡片/文本中的订单号，否则列出当前学员的订单。"""
        order_key = None
        if state.focused_object is not None and state.focused_object.type == "order":
            order_key = state.focused_object.id
        if not order_key:
            order_key = _extract_order_no(state)

        if order_key:
            payload = await fetch_order(state, order_key)
            if payload:
                content = "订单信息：\n" + json.dumps(payload, ensure_ascii=False, indent=2)
                return [KnowledgeChunk(content=content)]

        # 没有明确订单号 -> 列出我的订单
        orders = await fetch_my_orders(state)
        if not orders:
            return [KnowledgeChunk(content="未检索到订单信息，请确认订单号或先下单。")]
        content = "我的订单列表：\n" + json.dumps(orders, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]


class ApiCohortProvider(Provider):
    provider_id = "api.cohort"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索某个班次的模块/课次安排（适合“这个班次学什么/上什么课”）。"""
        cohort_id = None
        if state.focused_object is not None and state.focused_object.type == "cohort":
            cohort_id = str(state.focused_object.id)
        if not cohort_id:
            text = _clean_course_keyword(_extract_keyword(state))
            matched = await resolve_cohort(state, text)
            if matched:
                cohort_id = str(matched.get("cohortId"))
        if not cohort_id:
            return [KnowledgeChunk(content="未找到对应的班次，请选择一个班次或提供班次名称。")]
        detail = await fetch_cohort(state, cohort_id)
        if detail is None:
            return [KnowledgeChunk(content="未查到该班次的课程安排。")]
        content = "班次详情：\n" + json.dumps(detail, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]


class ApiLearnerProvider(Provider):
    provider_id = "api.learner"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索当前学员的档案与学习总览（身份/学习目标/在学班次/近期学习记录）。"""
        me, profile, summary = await asyncio.gather(
            fetch_me(state),
            fetch_student_profile(state),
            fetch_learning_summary(state),
        )
        payload: dict[str, Any] = {"user": me, "studentProfile": profile, "learningSummary": summary}
        content = "我的学习档案：\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]


class ApiStudyTaskProvider(Provider):
    provider_id = "api.study_task"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索待办作业与考试（我还有什么作业/考试要处理）。"""
        homeworks, exams = await asyncio.gather(
            fetch_my_homeworks(state),
            fetch_my_exams(state),
        )
        pending_hw = [h for h in homeworks if h.get("homeworkStatus") == "pending"]
        expired_hw = [h for h in homeworks if h.get("homeworkStatus") == "expired_unsubmitted"]
        submitted_hw = [h for h in homeworks if h.get("homeworkStatus") == "submitted"]
        not_started_exam = [e for e in exams if e.get("attemptStatus") == "not_started"]
        in_progress_exam = [e for e in exams if e.get("attemptStatus") == "in_progress"]
        submitted_exam = [e for e in exams if e.get("attemptStatus") == "submitted"]

        payload = {
            "homework": {
                "pending": [{"homeworkId": h.get("homeworkId"), "name": h.get("homeworkName"), "dueAt": h.get("dueAt")} for h in pending_hw[:10]],
                "expiredUnsubmitted": [{"homeworkId": h.get("homeworkId"), "name": h.get("homeworkName")} for h in expired_hw[:10]],
                "submittedCount": len(submitted_hw),
            },
            "exam": {
                "notStarted": [{"examId": e.get("examId"), "name": e.get("examName"), "deadlineAt": e.get("deadlineAt")} for e in not_started_exam[:10]],
                "inProgress": [{"examId": e.get("examId"), "name": e.get("examName")} for e in in_progress_exam[:10]],
                "submittedCount": len(submitted_exam),
            },
        }
        content = "待办作业与考试：\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]


class ApiRefundStatusProvider(Provider):
    provider_id = "api.refund_status"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索当前学员的退款申请进度。"""
        refunds = await fetch_my_refunds(state)
        if not refunds:
            return [KnowledgeChunk(content="当前没有退款申请记录。")]
        content = "我的退款申请：\n" + json.dumps(refunds, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]


class ApiTicketStatusProvider(Provider):
    provider_id = "api.ticket_status"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索当前学员的工单列表与进度。"""
        tickets = await fetch_my_tickets(state)
        if not tickets:
            return [KnowledgeChunk(content="当前没有工单记录。")]
        content = "我的工单：\n" + json.dumps(tickets, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=content)]


class RagDefaultProvider(Provider):
    provider_id = "rag.default"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """通用知识库检索（当前为占位，后续可接入向量检索）。"""
        return [KnowledgeChunk(content="未检索到相关知识库内容")]


class FaqDefaultProvider(Provider):
    provider_id = "faq.default"

    async def retrival(self, state: DialogueState) -> list[KnowledgeChunk]:
        """基于规则的常见问题 / 政策检索（退款、报名开课、学习使用、考试、优惠等）。"""
        text = state.pending_turn.user_message.text or ""
        return _faq_chunks(text)


def _extract_order_no(state: DialogueState) -> str | None:
    text = state.pending_turn.user_message.text or ""
    match = re.search(r"ORD\w*", text, re.IGNORECASE)
    return match.group(0) if match else None


def _extract_keyword(state: DialogueState) -> str:
    text = (state.pending_turn.user_message.text or "").strip()
    if state.focused_object is not None and state.focused_object.type in ("series", "cohort"):
        return ""
    return text


_NOISE_TOKENS = [
    "这门课", "这门", "这门班", "课程", "内容", "怎么样", "咋样", "大概", "什么", "情况",
    "介绍", "了解一下", "了解", "咨询", "想", "请问", "麻烦", "帮我", "看看",
    "上课", "上", "课", "学", "学习", "是", "的", "吗", "呢", "啊", "呀", "吧", "哦", "噢",
    "讲", "看", "知道", "了解下", "能", "可以",
    "？", "?", "。", "！", "!", "，", ",", "\t", "\n",
]


def _clean_course_keyword(text: str) -> str:
    """去掉口语化的疑问词/语气词，保留课程名作为检索关键字。"""
    value = (text or "").strip()
    if not value:
        return ""
    for token in _NOISE_TOKENS:
        value = value.replace(token, "")
    return value.strip()


def _best_match_series(series_list: list[dict[str, Any]], keyword: str) -> list[dict[str, Any]]:
    """在全部在售课程里，按关键字 Token 与课程名的匹配度择优返回。"""
    if not series_list:
        return []
    return _rank_series(series_list, keyword)


def _split_keyword_tokens(keyword: str) -> list[str]:
    """把关键字拆成有意义的检索词，例如 'Python 全栈' -> ['Python', '全栈']。
    同时处理中英文连写的情况，如 'Python全栈' -> ['Python', '全栈']。"""
    raw = (keyword or "").strip()
    if not raw:
        return []
    # 先按空格切，再在 中文/英文/数字 交界处切开
    parts: list[str] = []
    for chunk in re.split(r"\s+", raw):
        pieces = re.split(
            r"(?<=[0-9A-Za-z\u00c0-\u024f])(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])(?=[0-9A-Za-z\u00c0-\u024f])",
            chunk,
        )
        parts.extend(p for p in pieces if p)
    # 去重、去掉单字干扰词（如 '上'、'课'）
    seen: list[str] = []
    for p in parts:
        if len(p) >= 2 and p not in seen:
            seen.append(p)
    return seen


def _rank_series(series_list: list[dict[str, Any]], keyword: str, limit: int = 6) -> list[dict[str, Any]]:
    """按相关性给课程排序，总是返回前 N 门（关键词命中优先，字符重合次之）。
    当没有同名课程时，也能返回“最相关”的几门，而不是空结果。"""
    tokens = _split_keyword_tokens(keyword)
    token_chars = set("".join(tokens))

    def score(item: dict[str, Any]) -> int:
        name = str(item.get("seriesName") or "")
        # 1) 关键词整体/部分命中的权重最大
        hit = sum(len(tok) for tok in tokens if tok and tok in name)
        # 2) 字符级重合作为弱相关信号
        char_overlap = len(set(name) & token_chars)
        return hit * 1000 + char_overlap

    ranked = sorted(series_list, key=score, reverse=True)
    # 若连字符级都无重合，则保留“最热门”的课程作为兜底推荐
    return ranked[:limit]


# 关键词 -> 课程分类 ID（dim_course_category）
_QUERY_CATEGORIES: dict[str, list[int]] = {
    "python": [24, 25, 26, 27, 28],
    "java": [24, 25, 26, 27, 28],
    "c++": [24, 25, 28],
    "c语言": [24, 25, 28],
    "go": [25, 28],
    "编程": [24, 25, 26, 27, 28],
    "代码": [24],
    "程序": [24, 27],
    "全栈": [31],
    "前端": [29, 27],
    "javascript": [29, 27],
    "js": [29, 27],
    "vue": [29],
    "react": [29],
    "后端": [30],
    "数据库": [34],
    "sql": [34],
    "ai": [39, 40, 41],
    "人工智能": [39, 40, 41],
    "机器学习": [39],
    "深度学习": [40],
    "大模型": [41],
    "算法": [38, 39],
    "操作系统": [33],
    "linux": [33],
    "网络": [32],
    "考研": [15, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60],
    "数学": [46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60],
    "公考": [16],
    "证书": [17],
    "教师": [17],
    "资格": [17],
    "管理": [18, 19, 20],
    "企业培训": [20, 21],
    "大学生": [22],
    "升学": [15, 16, 23],
}


async def _search_series_by_category(state: DialogueState, text: str) -> list[dict[str, Any]]:
    """当查询包含技术关键词时，按对应课程分类检索（解决课程名不含技术词的问题）。"""
    lowered = (text or "").lower()
    category_ids: set[int] = set()
    for keyword, ids in _QUERY_CATEGORIES.items():
        if keyword.lower() in lowered:
            category_ids.update(ids)
    if not category_ids:
        return []

    deduped: dict[str, dict[str, Any]] = {}
    for category_id in category_ids:
        for item in await fetch_series_by_category(state, category_id):
            deduped.setdefault(str(item.get("seriesId")), item)
    return list(deduped.values())[:6]


def _faq_chunks(text: str = "") -> list[KnowledgeChunk]:
    """教育平台常见政策文本；根据关键词返回最贴近的条目。"""
    faqs: list[dict[str, Any]] = [
        {
            "keywords": ["退款", "退费", "退"],
            "title": "退款政策",
            "content": (
                "退款政策：已支付订单可在开课前申请退款。课程开始后按已上进度核减退款金额，"
                "直播/录播课与面授课的退款规则略有差异。退款类型包括个人原因、课程不满意、"
                "时间冲突、重复购买。已提交的退款申请可在“退款进度”中查看审核状态。"
            ),
        },
        {
            "keywords": ["开课", "报名", "入学", "开班", "上课时间"],
            "title": "报名/开课政策",
            "content": (
                "报名与开课政策：下单支付后即完成报名，系统会在开班前通知上课时间。"
                "开班后通常 3 个工作日内可进入班次学习，课件、作业与考试会随教学进度逐步开放。"
            ),
        },
        {
            "keywords": ["学习", "视频", "作业", "考试", "进度", "怎么看"],
            "title": "学习使用指南",
            "content": (
                "学习指南：报名后可在“我的班次”进入学习。视频支持倍速与断点续播，作业需在截止时间前提交，"
                "考试在开放窗口内作答。进度可在“学习进度”中查看出勤、视频、作业与考试情况。"
            ),
        },
        {
            "keywords": ["考试", "测验", "补考", "缺考"],
            "title": "考试规则",
            "content": "考试在开放窗口内作答，超时自动交卷；缺席记为缺考。成绩与作答记录可在“我的考试”中查看。",
        },
        {
            "keywords": ["优惠券", "优惠", "折扣", "券", "领券"],
            "title": "优惠券规则",
            "content": "优惠券有领取与有效期限制，且需满足使用门槛，仅适用于指定课程/班次。下单前可用优惠券抵扣金额。",
        },
        {
            "keywords": ["结课", "毕业", "证书", "证明"],
            "title": "结课与证书",
            "content": "完成班次要求的课次与作业/考试后即视为结课，可申请结课证明；具体以授课机构政策为准。",
        },
    ]
    if not text:
        return [
            KnowledgeChunk(
                content="\n".join("【" + str(f["title"]) + "】" + str(f["content"]) for f in faqs)
            )
        ]
    matched = [f for f in faqs if any(str(k) in text for k in f["keywords"])]
    if matched:
        return [
            KnowledgeChunk(
                content="\n".join("【" + str(f["title"]) + "】" + str(f["content"]) for f in matched)
            )
        ]
    return [KnowledgeChunk(content="未检索到相关问题")]
