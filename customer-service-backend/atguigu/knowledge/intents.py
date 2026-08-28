from dataclasses import dataclass


@dataclass(slots=True)
class KnowledgeIntent:
    id: str
    description: str
    provider_ids: list[str]
    requires_object_type: str | None = None


# 系统支持的所有知识意图（面向在线教育行业）
KNOWLEDGE_INTENTS: dict[str, KnowledgeIntent] = {
    "course_info": KnowledgeIntent(
        id="course_info", description="课程信息咨询：课程内容、适用人群、在售班次与价格",
        provider_ids=["api.course"],
    ),
    "cohort_info": KnowledgeIntent(
        id="cohort_info", description="班次安排咨询：某个班次的课程模块与课次安排",
        provider_ids=["api.cohort"],
    ),
    "order_info": KnowledgeIntent(
        id="order_info", description="订单信息咨询：查询某订单，或查看我的订单列表",
        provider_ids=["api.order"], requires_object_type="order",
    ),
    "learner_profile": KnowledgeIntent(
        id="learner_profile", description="我的学习档案/学习总览：学员身份、学习目标、在学班次、近期学习记录",
        provider_ids=["api.learner"],
    ),
    "study_tasks": KnowledgeIntent(
        id="study_tasks", description="我的待办作业与考试：查询还有哪些作业/考试要处理",
        provider_ids=["api.study_task"],
    ),
    "refund_status": KnowledgeIntent(
        id="refund_status", description="退款进度查询：查看我提交的退款申请与审核状态",
        provider_ids=["api.refund_status"],
    ),
    "ticket_status": KnowledgeIntent(
        id="ticket_status", description="工单进度查询：查看我提交的售后/投诉工单与处理状态",
        provider_ids=["api.ticket_status"],
    ),
    "enrollment_policy": KnowledgeIntent(
        id="enrollment_policy", description="报名/开课政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "refund_policy": KnowledgeIntent(
        id="refund_policy", description="退款政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "study_guide": KnowledgeIntent(
        id="study_guide", description="学习/使用指南咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "platform_rule": KnowledgeIntent(
        id="platform_rule", description="平台规则咨询",
        provider_ids=["rag.default"],
    ),
    "general_edu_info": KnowledgeIntent(
        id="general_edu_info", description="教育平台通用信息咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
}
