#!/usr/bin/env python3
import argparse
import io
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image


NOISE_TOKENS = ("logo", "ewm", "qr", "wx", "xhs", "dy", "icon", "svg", "mt.svg")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs_json")
    parser.add_argument("--output-dir", default="output/playwright/qdaily-image-editor/assets")
    parser.add_argument("--fixture-html", default="")
    parser.add_argument("--fixture-manifest", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_text(url: str, fixture_html: str) -> str:
    if fixture_html:
        raw = Path(fixture_html).read_text(encoding="utf-8")
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(mapping, dict):
            return mapping.get(url, "")
        return raw
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", "ignore")


def image_meta(url: str, manifest: dict) -> tuple[int, int, str]:
    if manifest and url in manifest:
        item = manifest[url]
        return item["width"], item["height"], item["format"]

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()
    img = Image.open(io.BytesIO(data))
    return img.size[0], img.size[1], img.format or "PNG"


def candidate_score(asset_url: str, width: int, height: int) -> int:
    lowered = asset_url.lower()
    if any(token in lowered for token in NOISE_TOKENS):
        return -100
    score = 0
    if width < 300 or height < 180:
        score -= 8
    if width < 120 or height < 80:
        score -= 12
    if "/uploadfile/" in lowered:
        score += 6
    if "wx_article_img" in lowered or "article" in lowered or "news" in lowered:
        score += 5
    area = width * height
    if area >= 800 * 450:
        score += 4
    if area >= 1200 * 700:
        score += 2
    ratio = width / max(height, 1)
    if 1.2 <= ratio <= 2.2:
        score += 2
    if lowered.endswith(".jpg") or lowered.endswith(".jpeg") or lowered.endswith(".png"):
        score += 1
    return score


def collect_assets(page_url: str, fixture_html: str, manifest: dict) -> list[dict]:
    html = fetch_text(page_url, fixture_html)
    srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    meta_candidates = re.findall(
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    jsonld_candidates = []
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            payload = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if not isinstance(record, dict):
                continue
            images = record.get("images") or record.get("image") or []
            if isinstance(images, str):
                jsonld_candidates.append(images)
            elif isinstance(images, list):
                jsonld_candidates.extend([item for item in images if isinstance(item, str)])

    srcs = jsonld_candidates + meta_candidates + srcs
    seen = set()
    items = []
    for src in srcs:
        asset_url = urljoin(page_url, src)
        if asset_url in seen:
            continue
        seen.add(asset_url)
        try:
            width, height, fmt = image_meta(asset_url, manifest)
        except Exception:
            continue
        score = candidate_score(asset_url, width, height)
        if score < 0:
            continue
        item = {
            "asset_url": asset_url,
            "width": width,
            "height": height,
            "format": fmt.lower(),
            "score": score,
        }
        items.append(item)
    return sorted(items, key=lambda item: item["score"], reverse=True)


def choose_asset(page_url: str, fixture_html: str, manifest: dict, used_asset_urls: set[str]) -> dict | None:
    candidates = collect_assets(page_url, fixture_html, manifest)
    for item in candidates:
        if item["asset_url"] not in used_asset_urls:
            return item
    return candidates[0] if candidates else None


def extension_for(fmt: str, asset_url: str) -> str:
    ext = Path(urlparse(asset_url).path).suffix.lower().lstrip(".")
    if ext:
        return ext
    return {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}.get(fmt.lower(), "png")


def save_asset(asset_url: str, output_path: Path, manifest: dict) -> None:
    if manifest and asset_url in manifest:
        output_path.touch()
        return
    request = urllib.request.Request(asset_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def main() -> int:
    args = parse_args()
    jobs_payload = load_json(args.jobs_json)
    manifest = load_json(args.fixture_manifest) if args.fixture_manifest else {}
    output_dir = Path(args.output_dir)

    assets = []
    used_asset_urls = set()
    for job in jobs_payload.get("jobs", []):
        chosen = choose_asset(job["url"], args.fixture_html, manifest, used_asset_urls)
        if chosen is None:
            continue
        used_asset_urls.add(chosen["asset_url"])
        ext = extension_for(chosen["format"], chosen["asset_url"])
        output_path = output_dir / f"{job['slot']}-1.{ext}"
        if not args.dry_run:
            save_asset(chosen["asset_url"], output_path, manifest)
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

    print(json.dumps({"assets": assets}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
