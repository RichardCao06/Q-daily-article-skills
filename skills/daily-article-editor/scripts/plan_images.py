#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
PARA_SPLIT_RE = re.compile(r"\n\s*\n")
STRIP_MARKUP_RE = re.compile(r"[*`_#]+")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def article_type_for(text: str) -> str:
    lowered = text.lower()
    if "访谈" in text or "q：" in text or "q=" in lowered:
        return "interview"
    feature_score = sum(
        1
        for keyword in (
            "feature",
            "解释",
            "这一周",
            "放在一起看",
            "同一种信号",
            "工作流",
            "下一轮竞争",
            "意味着",
            "接口",
            "入口",
        )
        if keyword in text
    )
    profile_score = sum(
        1
        for keyword in (
            "人物稿",
            "人物特写",
            "母亲",
            "早年",
            "19 岁",
            "小时候",
            "回忆",
            "车手",
            "创始人",
        )
        if keyword in text
    )
    if feature_score >= 2 and feature_score >= profile_score:
        return "feature"
    if profile_score >= 2:
        return "profile"
    if "创始人" in text or "母亲" in text or "人物稿" in text or "人物特写" in text:
        return "profile"
    return "feature"


def feature_mode_for(text: str) -> str:
    if article_type_for(text) != "feature":
        return ""

    policy_keywords = (
        "协议",
        "规定",
        "要求",
        "监管",
        "规则",
        "合法",
        "披露",
        "透明化",
        "概率",
        "开发者",
        "边界",
    )
    company_keywords = (
        "业务",
        "会员",
        "预算",
        "投入",
        "商业片",
        "独立电影",
        "比例",
        "方向",
        "策略",
        "全球市场",
        "利润",
        "票房",
        "路线",
        "调整",
        "减少",
        "转向",
        "视频制作",
        "内容方向",
        "商业电影",
    )
    data_keywords = (
        "数据",
        "人均",
        "增长",
        "下降",
        "同比",
        "市值",
        "报告",
        "排名",
        "比例",
        "频率",
        "趋势",
        "超过",
        "日均",
        "花费",
        "渗透",
        "变量",
        "驱动",
    )
    news_keywords = (
        "近日",
        "昨日",
        "周二",
        "宣布",
        "要求",
        "规定",
        "通知",
        "下架",
        "移除",
        "公布",
        "更新",
        "决定",
        "辞职",
        "董事会",
        "估值",
        "融资",
        "路透社",
        "协议",
        "监管",
    )
    analysis_keywords = (
        "不只是",
        "真正重要",
        "真正值得注意",
        "真正值得写",
        "意味着",
        "影响",
        "关系",
        "问题",
        "规则",
        "机制",
        "平台",
        "分发",
        "监管",
        "为什么会",
        "为什么是现在",
    )
    general_feature_keywords = (
        "这一周",
        "放在一起看",
        "同一种信号",
        "下一轮竞争",
        "工作流",
        "接口",
        "入口",
        "代理层",
    )

    policy_score = sum(1 for keyword in policy_keywords if keyword in text)
    company_score = sum(1 for keyword in company_keywords if keyword in text)
    data_score = sum(1 for keyword in data_keywords if keyword in text)
    news_score = sum(1 for keyword in news_keywords if keyword in text)
    analysis_score = sum(1 for keyword in analysis_keywords if keyword in text)
    general_score = sum(1 for keyword in general_feature_keywords if keyword in text)

    if policy_score >= 3 and analysis_score >= 2:
        return "policy-rules"
    if company_score >= 3 and analysis_score >= 1:
        return "company-shift"
    if data_score >= 4 and analysis_score >= 1:
        return "data-trend"
    if news_score >= 3 and analysis_score >= 2 and news_score >= general_score:
        return "event-news"
    return "general"


def clean_paragraphs(text: str) -> list[str]:
    paragraphs = []
    for block in PARA_SPLIT_RE.split(text):
        line = " ".join(part.strip() for part in block.splitlines() if part.strip())
        line = STRIP_MARKUP_RE.sub("", line).strip()
        if line:
            paragraphs.append(line)
    return paragraphs


def find_title(text: str) -> str:
    match = HEADING_RE.search(text)
    return match.group(1).strip() if match else "Untitled"


def infer_subject(title: str, text: str) -> str:
    for pattern in (r"何琼", r"张雪机车", r"张雪"):
        match = re.search(pattern, title)
        if match:
            return match.group(0)
    for pattern in (r"何琼", r"张雪机车", r"张雪"):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return title.split("，", 1)[0].split("|", 1)[0].strip()


def first_matching(paragraphs: list[str], *keywords: str) -> str:
    for paragraph in paragraphs:
        if paragraph == "摘要" or paragraph.startswith("摘要 "):
            continue
        if any(keyword in paragraph for keyword in keywords):
            return paragraph
    return paragraphs[0] if paragraphs else ""


def first_content_paragraph(paragraphs: list[str], title: str) -> str:
    for paragraph in paragraphs:
        if paragraph == title:
            continue
        if paragraph == "摘要" or paragraph.startswith("摘要 "):
            continue
        if len(paragraph) < 12:
            continue
        return paragraph
    return paragraphs[0] if paragraphs else ""


def first_matching_group(paragraphs: list[str], keyword_groups: list[tuple[str, ...]]) -> str:
    for group in keyword_groups:
        match = first_matching(paragraphs, *group)
        if match and all(keyword in match for keyword in group):
            return match
    return ""


def count_matching_paragraphs(paragraphs: list[str], keywords: tuple[str, ...]) -> int:
    return sum(1 for paragraph in paragraphs if any(keyword in paragraph for keyword in keywords))


def build_subject_queries(subject: str, *tails: str) -> list[str]:
    return [f"{subject} {tail}".strip() for tail in tails if tail.strip()]


def infer_anchor_subject(anchor_text: str, fallback: str) -> str:
    for keyword, label in (
        ("Muse Spark", "Muse Spark"),
        ("Meta", "Meta AI"),
        ("Perplexity", "Perplexity"),
        ("Plaid", "Perplexity"),
        ("Voxtral", "Voxtral TTS"),
        ("Mistral", "Mistral"),
        ("OpenAI", "OpenAI"),
        ("Codex", "OpenAI"),
        ("ChatGPT", "OpenAI"),
    ):
        if keyword in anchor_text:
            return label
    return fallback


def build_profile_slots(title: str, text: str) -> list[dict]:
    title = find_title(text)
    subject = infer_subject(title, text)
    paragraphs = clean_paragraphs(text)
    slots = []
    lead_paragraph = first_content_paragraph(paragraphs, title)

    if lead_paragraph:
        slots.append(
            {
                "slot": "cover",
                "purpose": "establish_cover",
                "anchor_text": lead_paragraph,
                "subject": subject,
                "query": build_subject_queries(subject, "封面", "现场", "人物"),
                "source_hint": "优先适合作为封面的强画面人物图、事件图或纪实场景图",
            }
        )

    if lead_paragraph:
        slots.append(
            {
                "slot": "hero",
                "purpose": "establish_person",
                "anchor_text": lead_paragraph,
                "subject": subject,
                "query": build_subject_queries(subject, "人物", "采访", "现场"),
                "source_hint": "优先媒体人物图、采访图或纪实现场图",
            }
        )

    origin_anchor = first_matching_group(
        paragraphs,
        [
            ("车队", "机械师"),
            ("早年", "报社"),
            ("小时候", "母亲"),
            ("回忆", "母亲"),
            ("早年",),
        ],
    )
    if origin_anchor:
        slots.append(
            {
                "slot": "origin_story",
                "purpose": "prove_process",
                "anchor_text": origin_anchor,
                "subject": subject,
                "query": build_subject_queries(subject, "早年", "工作", "采访", "人物"),
                "source_hint": "优先早年经历、工作现场或人物采访图",
            }
        )

    product_anchor = first_matching_group(
        paragraphs,
        [
            ("500RR", "重庆摩博会"),
            ("500RR",),
            ("交付", "品牌"),
            ("发布", "品牌"),
        ],
    )
    if product_anchor:
        slots.append(
            {
                "slot": "product_or_project",
                "purpose": "show_project",
                "anchor_text": product_anchor,
                "subject": subject,
                "query": [f"{subject} 500RR", f"{subject} 重庆摩博会", f"{subject} 发布"],
                "source_hint": "优先品牌产品图或发布现场图",
            }
        )

    archive_anchor = first_matching_group(
        paragraphs,
        [
            ("抵押", "房产"),
            ("贷款", "支持"),
            ("55 万元", "支持"),
            ("童车",),
            ("自行车", "母亲"),
        ],
    )
    if archive_anchor:
        slots.append(
            {
                "slot": "archive",
                "purpose": "add_context",
                "anchor_text": archive_anchor,
                "subject": subject,
                "query": build_subject_queries(subject, "张雪 母亲", "支持", "早年", "资料"),
                "source_hint": "优先资料图、媒体人物图或与母子关系相关的报道图片",
            }
        )

    achievement_anchor = first_matching_group(
        paragraphs,
        [
            ("WSBK", "葡萄牙"),
            ("WSBK", "赛场"),
            ("葡萄牙", "赛场"),
            ("夺冠", "冠军"),
            ("冲线",),
        ],
    )
    achievement_signals = count_matching_paragraphs(paragraphs, ("WSBK", "夺冠", "赛场", "冲线", "领奖台", "葡萄牙"))
    if achievement_anchor and (achievement_signals >= 2 or subject in {"张雪", "张雪机车"}):
        slots.append(
            {
                "slot": "achievement",
                "purpose": "show_achievement",
                "anchor_text": achievement_anchor,
                "subject": subject,
                "query": [f"{subject} WSBK", f"{subject} 葡萄牙 夺冠"],
                "source_hint": "优先赛事现场图或成绩截图",
            }
        )

    return slots


def build_feature_slots(title: str, text: str) -> list[dict]:
    subject = infer_subject(title, text)
    paragraphs = clean_paragraphs(text)
    slots = []
    lead_paragraph = first_content_paragraph(paragraphs, title)

    if lead_paragraph:
        slots.append(
            {
                "slot": "cover",
                "purpose": "establish_cover",
                "anchor_text": lead_paragraph,
                "subject": subject,
                "query": build_subject_queries(subject, "封面", "官方", "界面"),
                "source_hint": "优先适合作为封面的高识别度主视觉、产品演示图或事件图",
            }
        )

    if lead_paragraph:
        slots.append(
            {
                "slot": "hero",
                "purpose": "establish_shift",
                "anchor_text": lead_paragraph,
                "subject": subject,
                "query": build_subject_queries(subject, "官方", "产品", "界面"),
                "source_hint": "优先能建立这篇文章核心变化的官方产品演示图、事件图或界面图",
            }
        )

    object_anchor = first_matching_group(
        paragraphs,
        [
            ("开始驱动", "扩展到"),
            ("接进产品",),
            ("默认分发", "入口"),
            ("工作流", "基础设施"),
        ],
    )
    if object_anchor:
        object_subject = infer_anchor_subject(object_anchor, subject)
        slots.append(
            {
                "slot": "object",
                "purpose": "show_object",
                "anchor_text": object_anchor,
                "subject": object_subject,
                "query": build_subject_queries(object_subject, "官方 产品", "app", "界面"),
                "source_hint": "优先官方产品图、界面图或能把入口竞争落到具体对象上的图片",
            }
        )

    process_anchor = first_matching_group(
        paragraphs,
        [
            ("文本转语音",),
            ("语音", "接口"),
            ("输入输出", "接口"),
            ("工作流", "接口层"),
        ],
    )
    if process_anchor:
        process_subject = infer_anchor_subject(process_anchor, subject)
        slots.append(
            {
                "slot": "process",
                "purpose": "show_process",
                "anchor_text": process_anchor,
                "subject": process_subject,
                "query": build_subject_queries(process_subject, "官方 能力", "信息图", "产品"),
                "source_hint": "优先官方能力图、流程图或说明接口层变化的产品图",
            }
        )

    return slots


def build_slots(text: str) -> list[dict]:
    title = find_title(text)
    article_type = article_type_for(text)
    if article_type == "feature":
        return build_feature_slots(title, text)
    return build_profile_slots(title, text)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: plan_images.py <draft.md>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    text = read_text(path)
    payload = {
        "title": find_title(text),
        "article_type": article_type_for(text),
        "feature_mode": feature_mode_for(text),
        "slots": build_slots(text),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
