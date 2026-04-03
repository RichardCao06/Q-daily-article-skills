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
    if "品牌" in text or "创始人" in text or "公司" in text:
        return "profile"
    return "feature"


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
    match = re.search(r"张雪机车|张雪", text)
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
        if match and match != (paragraphs[0] if paragraphs else ""):
            return match
    return first_matching(paragraphs, *(keyword_groups[-1] if keyword_groups else tuple()))


def build_slots(text: str) -> list[dict]:
    title = find_title(text)
    subject = infer_subject(title, text)
    paragraphs = clean_paragraphs(text)
    slots = []
    lead_paragraph = first_content_paragraph(paragraphs, title)

    if lead_paragraph:
        slots.append(
            {
                "slot": "hero",
                "purpose": "establish_person",
                "anchor_text": lead_paragraph,
                "subject": subject,
                "query": [f"{subject} 现场", f"{subject} 人物"],
                "source_hint": "优先官方现场图或媒体人物图",
            }
        )

    origin_anchor = first_matching(paragraphs, "车队", "机械师", "早年", "19 岁", "追")
    if origin_anchor:
        slots.append(
            {
                "slot": "origin_story",
                "purpose": "prove_process",
                "anchor_text": origin_anchor,
                "subject": subject,
                "query": [f"{subject} 早年", f"{subject} 赛车", f"{subject} 机械师"],
                "source_hint": "优先早年赛车或工作图",
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

    achievement_anchor = first_matching_group(
        paragraphs,
        [
            ("WSBK", "葡萄牙"),
            ("WSBK", "赛场"),
            ("夺冠", "冠军"),
            ("WSBK",),
        ],
    )
    if achievement_anchor:
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: plan_images.py <draft.md>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    text = read_text(path)
    payload = {
        "title": find_title(text),
        "article_type": article_type_for(text),
        "slots": build_slots(text),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
