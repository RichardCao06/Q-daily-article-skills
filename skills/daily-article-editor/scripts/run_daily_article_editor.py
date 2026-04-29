#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_article_package as article_package  # noqa: E402
import build_editorial_package as editorial_package  # noqa: E402
import extract_primary_image_assets as asset_extractor  # noqa: E402
import plan_images  # noqa: E402
import source_images  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("draft")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--official-domain", default="")
    parser.add_argument("--official-html", default="")
    parser.add_argument("--fixture-rss", default="")
    parser.add_argument("--fixture-html", default="")
    parser.add_argument("--fixture-manifest", default="")
    parser.add_argument("--dry-run-assets", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def slugify(title: str) -> str:
    lowered = title.lower()
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", lowered).strip("-")
    return slug or "article"


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolved_image_path(asset_entry: dict) -> str:
    if not asset_entry.get("asset_url"):
        return ""
    return asset_entry.get("output_path", "")


def build_plan(draft_path: Path) -> dict:
    text = load_text(draft_path)
    return {
        "title": plan_images.find_title(text),
        "article_type": plan_images.article_type_for(text),
        "feature_mode": plan_images.feature_mode_for(text),
        "slots": plan_images.build_slots(text),
    }


def build_sources(plan: dict, args: argparse.Namespace) -> dict:
    return {
        "images": [
            source_images.build_image_candidates(
                slot,
                args.official_domain,
                args.official_html,
                args.fixture_rss,
                args.limit,
            )
            for slot in plan.get("slots", [])
        ]
    }


def build_jobs(sources: dict, output_dir: Path) -> dict:
    jobs = []
    for image in sources.get("images", []):
        candidates = image.get("candidates", [])
        if not candidates:
            continue
        chosen = candidates[0]
        jobs.append(
            {
                "slot": image["slot"],
                "title": chosen.get("title", ""),
                "url": chosen.get("url", ""),
                "domain": chosen.get("domain", ""),
                "source_tier": chosen.get("source_tier", ""),
                "output_path": str(output_dir / "screens" / f"{image['slot']}-1.png"),
            }
        )
    return {"jobs": jobs}


def build_assets(jobs: dict, output_dir: Path, args: argparse.Namespace) -> dict:
    manifest = asset_extractor.load_json(args.fixture_manifest) if args.fixture_manifest else {}
    fixture_html = args.fixture_html or args.official_html
    output_assets_dir = output_dir / "assets"
    output_assets_dir.mkdir(parents=True, exist_ok=True)

    assets = []
    used_asset_urls = set()
    for job in jobs.get("jobs", []):
        chosen = asset_extractor.choose_asset(job["url"], fixture_html, manifest, used_asset_urls)
        if chosen is None:
            continue
        used_asset_urls.add(chosen["asset_url"])
        ext = asset_extractor.extension_for(chosen["format"], chosen["asset_url"])
        output_path = output_assets_dir / f"{job['slot']}-1.{ext}"
        if not args.dry_run_assets:
            asset_extractor.save_asset(chosen["asset_url"], output_path, manifest)
        assets.append(
            {
                "slot": job["slot"],
                "source_page": job["url"],
                "asset_url": chosen["asset_url"],
                "width": chosen["width"],
                "height": chosen["height"],
                "format": chosen["format"],
                "output_path": str(output_path),
            }
        )
    return {"assets": assets}


def render_markdown(draft_text: str, package: dict) -> str:
    lines = draft_text.splitlines()
    summary_end = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("**摘要**"):
            cursor = idx + 1
            while cursor < len(lines) and lines[cursor].strip():
                cursor += 1
            summary_end = cursor
            break

    hero_image = next((image for image in package["editorial"]["images"] if image["slot"] == "hero" and image["image_path"]), None)
    hero_block = []
    if hero_image:
        hero_block = [
            f"![{hero_image['source_title']}]({hero_image['image_path']})",
            "",
            f"*图注：{hero_image['caption']} 来源：[{hero_image['source_title']}]({hero_image['source_url']})*",
            "",
        ]

    rendered = []
    for idx, line in enumerate(lines):
        rendered.append(line)
        if summary_end is not None and idx + 1 == summary_end and hero_block:
            rendered.append("")
            rendered.extend(hero_block)

    markdown = "\n".join(rendered).strip() + "\n"
    for image in package["editorial"]["images"]:
        if image["slot"] in {"cover", "hero"} or not image["image_path"]:
            continue
        anchor = image.get("anchor_text", "").strip()
        if not anchor or anchor not in markdown:
            continue
        block = (
            f"{anchor}\n\n"
            f"![{image['source_title']}]({image['image_path']})\n\n"
            f"*图注：{image['caption']} 来源：[{image['source_title']}]({image['source_url']})*"
        )
        markdown = markdown.replace(anchor, block, 1)
    return markdown


def main() -> int:
    args = parse_args()
    draft_path = Path(args.draft)
    draft_text = load_text(draft_path)
    title = plan_images.find_title(draft_text)
    output_dir = Path(args.output_dir) if args.output_dir else Path("output/daily-article-editor") / slugify(title)
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(draft_path)
    writing_package = {
        "title": plan["title"],
        "article_type": plan["article_type"],
        "feature_mode": plan.get("feature_mode", ""),
        "writing": article_package.infer_writing_package(
            draft_text,
            plan["article_type"],
            plan.get("feature_mode", ""),
        ),
        "images": [article_package.build_caption(slot) for slot in plan["slots"]],
        "layout": article_package.infer_layout_package(plan["article_type"], [article_package.build_caption(slot) for slot in plan["slots"]]),
    }
    sources = build_sources(plan, args)
    jobs = build_jobs(sources, output_dir)
    assets = build_assets(jobs, output_dir, args)

    plan_path = output_dir / "plan.json"
    sources_path = output_dir / "sources.json"
    jobs_path = output_dir / "jobs.json"
    assets_path = output_dir / "assets.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    assets_path.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")

    editorial = {
        "title": plan["title"],
        "images": [],
    }
    source_by_slot = {item["slot"]: item for item in sources.get("images", [])}
    job_by_slot = {item["slot"]: item for item in jobs.get("jobs", [])}
    asset_by_slot = {item["slot"]: item for item in assets.get("assets", [])}
    for slot in plan.get("slots", []):
        slot_name = slot.get("slot", "")
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
        editorial["images"].append(
            {
                "slot": slot_name,
                "caption": editorial_package.build_caption(slot),
                "placement_note": editorial_package.placement_note(slot_name),
                "anchor_text": slot.get("anchor_text", ""),
                "image_path": resolved_image_path(asset_entry),
                "source_url": job_entry.get("url", chosen.get("url", "")),
                "source_title": job_entry.get("title", chosen.get("title", "")),
                "source_tier": job_entry.get("source_tier", chosen.get("source_tier", "")),
                "page_kind": chosen.get("page_kind", ""),
                "asset_url": asset_entry.get("asset_url", ""),
            }
        )

    final_payload = {
        "title": plan["title"],
        "article_type": plan["article_type"],
        "feature_mode": plan.get("feature_mode", ""),
        "writing": writing_package["writing"],
        "layout": writing_package["layout"],
        "cover": next(
            (
                image
                for image in editorial["images"]
                if image.get("slot") == "cover" and image.get("image_path") and image.get("asset_url")
            ),
            None,
        ),
        "editorial": editorial,
    }
    package_path = output_dir / "article-package.json"
    package_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    final_markdown = render_markdown(draft_text, final_payload)
    markdown_path = output_dir / "article-final.md"
    markdown_path.write_text(final_markdown, encoding="utf-8")

    print(json.dumps({"output_dir": str(output_dir), "package": str(package_path), "markdown": str(markdown_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
