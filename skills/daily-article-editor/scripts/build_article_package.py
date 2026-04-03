#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from plan_images import article_type_for, build_slots, find_title, read_text  # noqa: E402
from generate_captions import build_caption  # noqa: E402


def infer_writing_package(text: str, article_type: str) -> dict:
    title = find_title(text)
    summary_match = re.search(r"\*\*摘要\*\*\s*(.+)", text)
    summary = summary_match.group(1).strip() if summary_match else ""

    if article_type == "profile":
        structure = ["开头事件", "人物来路", "方法与代价", "品牌与产品", "结尾问题"]
    elif article_type == "interview":
        structure = ["人物导语", "背景搭建", "问答主体", "结尾回收"]
    else:
        structure = ["开头事件", "背景解释", "案例展开", "结尾判断"]

    return {
        "title": title,
        "summary": summary,
        "article_type": article_type,
        "edit_goal": "整理成正式发稿版，统一标题、摘要、小标题、段落节奏、图注和结尾收束。",
        "structure": structure,
        "tone": "克制、明确、信息密度高，不过度抒情。",
    }


def infer_layout_package(article_type: str, images: list[dict]) -> dict:
    recommended_slots = [image["slot"] for image in images]
    return {
        "output_format": "markdown",
        "article_type": article_type,
        "hero_after_summary": True,
        "recommended_image_slots": recommended_slots,
        "layout_rules": [
            "摘要后可插首图。",
            "中段只在产品、项目或关键事实出现时插图。",
            "结尾段落保持收紧，避免为凑图破坏节奏。",
        ],
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_article_package.py <draft.md>", file=sys.stderr)
        return 1

    draft_path = Path(sys.argv[1])
    text = read_text(draft_path)
    article_type = article_type_for(text)
    slots = build_slots(text)
    images = [build_caption(slot) for slot in slots]

    payload = {
        "title": find_title(text),
        "article_type": article_type,
        "writing": infer_writing_package(text, article_type),
        "images": images,
        "layout": infer_layout_package(article_type, images),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
