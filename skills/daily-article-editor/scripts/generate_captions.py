#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PURPOSE_TO_CAPTION = {
    "establish_cover": "{subject}。这张图用于文章封面，需要先把主题和张力建立起来。",
    "establish_person": "{subject}。这张图更适合放在开头，用来先建立人物印象。",
    "establish_shift": "{subject}。这张图放在开头，是为了先把这篇文章讨论的核心变化建立起来。",
    "show_project": "{subject}相关项目或产品。放在这里，是为了让读者看到文章正在谈的对象。",
    "show_object": "{subject}相关产品或界面。它用来把上文讨论的入口、产品或系统落到具体对象上。",
    "prove_process": "{subject}早期经历或工作现场。这类图适合放在人物来路之后，帮文字落地。",
    "show_process": "{subject}相关能力或流程示意。它更适合跟在对应论点后面，用来把抽象判断落到具体机制上。",
    "show_achievement": "{subject}相关成绩或赛事现场。它的作用不是煽情，而是把高光时刻坐实。",
    "add_context": "{subject}相关背景资料图。它更像补证据，而不是装饰页面。",
}


def placement_note(slot_name: str) -> str:
    if slot_name == "cover":
        return "用于 CMS、列表页或分享封面，不插入正文。"
    if slot_name == "hero":
        return "建议插入在标题和摘要之后。"
    if slot_name == "origin_story":
        return "建议插入在人物来路或职业转折段之后。"
    if slot_name == "object":
        return "建议插入在首次具体展开产品、项目或界面的段落之后。"
    if slot_name == "process":
        return "建议插入在解释工作方式、接口层或能力机制的对应论点后面。"
    if slot_name == "product_or_project":
        return "建议插入在品牌成立、产品发布或项目展开段之后。"
    if slot_name == "achievement":
        return "建议插入在写到成绩、赛事或阶段性证明的位置。"
    return "建议插入在与其锚点段落最近的位置。"


def build_caption(slot: dict) -> dict:
    purpose = slot.get("purpose", "add_context")
    template = PURPOSE_TO_CAPTION.get(purpose, PURPOSE_TO_CAPTION["add_context"])
    subject = slot.get("subject", "相关人物")
    return {
        "slot": slot.get("slot", "unknown"),
        "caption": template.format(subject=subject),
        "placement_note": placement_note(slot.get("slot", "")),
        "anchor_text": slot.get("anchor_text", ""),
        "source_hint": slot.get("source_hint", ""),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_captions.py <plan.json>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    images = [build_caption(slot) for slot in payload.get("slots", [])]
    print(json.dumps({"images": images}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
