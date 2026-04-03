#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PURPOSE_TO_CAPTION = {
    "establish_person": "{subject}。这张图更适合放在开头，用来先建立人物印象。",
    "show_project": "{subject}相关项目或产品。放在这里，是为了让读者看到文章正在谈的对象。",
    "prove_process": "{subject}早期经历或工作现场。这类图适合放在人物来路之后，帮文字落地。",
    "show_achievement": "{subject}相关成绩或赛事现场。它的作用不是煽情，而是把高光时刻坐实。",
    "add_context": "{subject}相关背景资料图。它更像补证据，而不是装饰页面。",
}


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def placement_note(slot_name: str) -> str:
    if slot_name == "hero":
        return "建议插入在标题和摘要之后。"
    if slot_name == "origin_story":
        return "建议插入在人物来路或职业转折段之后。"
    if slot_name == "product_or_project":
        return "建议插入在品牌成立、产品发布或项目展开段之后。"
    if slot_name == "achievement":
        return "建议插入在写到成绩、赛事或阶段性证明的位置。"
    return "建议插入在与其锚点段落最近的位置。"


def build_caption(slot: dict) -> str:
    purpose = slot.get("purpose", "add_context")
    subject = slot.get("subject", "相关人物")
    template = PURPOSE_TO_CAPTION.get(purpose, PURPOSE_TO_CAPTION["add_context"])
    return template.format(subject=subject)


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print("usage: build_editorial_package.py <plan.json> <sources.json> <jobs.json> [assets.json]", file=sys.stderr)
        return 1

    plan = load_json(sys.argv[1])
    sources = load_json(sys.argv[2])
    jobs = load_json(sys.argv[3])
    assets = load_json(sys.argv[4]) if len(sys.argv) == 5 else {"assets": []}

    source_by_slot = {item["slot"]: item for item in sources.get("images", [])}
    job_by_slot = {item["slot"]: item for item in jobs.get("jobs", [])}
    asset_by_slot = {item["slot"]: item for item in assets.get("assets", [])}

    images = []
    for slot in plan.get("slots", []):
        slot_name = slot.get("slot", "unknown")
        source_entry = source_by_slot.get(slot_name, {})
        job_entry = job_by_slot.get(slot_name, {})
        asset_entry = asset_by_slot.get(slot_name, {})
        chosen = None
        for candidate in source_entry.get("candidates", []):
            if candidate.get("url") == job_entry.get("url"):
                chosen = candidate
                break
        if chosen is None:
            chosen = (source_entry.get("candidates") or [{}])[0]

        images.append(
            {
                "slot": slot_name,
                "caption": build_caption(slot),
                "placement_note": placement_note(slot_name),
                "anchor_text": slot.get("anchor_text", ""),
                "image_path": asset_entry.get("output_path", job_entry.get("output_path", "")),
                "source_url": job_entry.get("url", chosen.get("url", "")),
                "source_title": job_entry.get("title", chosen.get("title", "")),
                "source_tier": job_entry.get("source_tier", chosen.get("source_tier", "")),
                "page_kind": chosen.get("page_kind", ""),
                "asset_url": asset_entry.get("asset_url", ""),
            }
        )

    payload = {
        "title": plan.get("title", ""),
        "images": images,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
