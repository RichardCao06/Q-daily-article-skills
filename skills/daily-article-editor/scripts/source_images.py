#!/usr/bin/env python3
import argparse
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse


MEDIA_DOMAINS = {
    "www.nbd.com.cn",
    "k.sina.com.cn",
    "www.thepaper.cn",
    "36kr.com",
    "www.jiemian.com",
    "www.yicai.com",
}

TIER_PRIORITY = {"official": 0, "media": 1, "web": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json")
    parser.add_argument("--official-domain", default="")
    parser.add_argument("--official-html", default="")
    parser.add_argument("--fixture-rss", default="")
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify_page_content(text: str, url: str) -> str:
    haystack = f"{text} {url}".lower()
    scores = {"product": 0, "event": 0, "person": 0, "brand": 0}

    for token in ("500rr", "500f", "820rr", "产品", "车型", "参数", "show&id="):
        if token in haystack:
            scores["product"] += 2
    for token in ("赛事", "比赛", "赛道", "wsbk", "夺冠", "冠军", "category&id=3"):
        if token in haystack:
            scores["event"] += 2
    for token in ("人物", "创始人", "故事", "访谈", "张雪"):
        if token in haystack:
            scores["person"] += 1
    for token in ("品牌", "首页", "活动", "about", "category&id=10"):
        if token in haystack:
            scores["brand"] += 1

    best_kind = max(scores, key=scores.get)
    return best_kind if scores[best_kind] > 0 else "generic"


def source_tier_for(domain: str, official_domain: str) -> str:
    clean_domain = domain.lower()
    clean_official = official_domain.lower().lstrip(".")
    if clean_official and clean_domain.endswith(clean_official):
        return "official"
    if clean_domain in MEDIA_DOMAINS:
        return "media"
    return "web"


def build_queries(slot: dict, official_domain: str) -> list[tuple[str, str]]:
    base_queries = slot.get("query", [])
    subject = slot.get("subject", "").strip()
    anchor_text = slot.get("anchor_text", "")
    source_hint = slot.get("source_hint", "")
    context_text = " ".join(base_queries + [anchor_text, source_hint])
    enriched_queries = []

    for query in base_queries:
        enriched_queries.append(query)
        if (
            subject
            and subject in query
            and "机车" not in query
            and any(token in context_text for token in ("500RR", "WSBK", "赛场", "赛车", "品牌", "产品", "摩博会"))
        ):
            enriched_queries.append(query.replace(subject, f"{subject} 机车 创始人"))

    slot_name = slot.get("slot", "")
    event_tokens = []
    for token in ("WSBK", "夺冠", "赛场", "领奖台", "庆祝", "葡萄牙", "冠军"):
        if token in anchor_text or token in source_hint:
            event_tokens.append(token)
    if slot_name in {"hero", "achievement"} and subject and event_tokens:
        token_text = " ".join(dict.fromkeys(event_tokens))
        enriched_queries.append(f"{subject} {token_text}")
        enriched_queries.append(f"{subject} 机车 创始人 {token_text}")

    base_queries = list(dict.fromkeys(enriched_queries))
    queries: list[tuple[str, str]] = []
    if official_domain:
        for query in base_queries:
            queries.append(("official", f"site:{official_domain} {query}"))
    for query in base_queries:
        queries.append(("open", query))
    return queries


def fetch_rss(query: str, fixture_rss: str) -> str:
    if fixture_rss:
        return Path(fixture_rss).read_text(encoding="utf-8")

    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_official_html(official_domain: str, official_html: str) -> tuple[str, str]:
    if official_html:
        return f"https://www.{official_domain.strip('.')}/", Path(official_html).read_text(encoding="utf-8")

    root_url = f"https://www.{official_domain.strip('.')}/"
    return root_url, fetch_text(root_url)


def official_keyword_score(text: str, slot: dict) -> int:
    haystack = text.lower()
    score = 0
    for query in slot.get("query", []):
        for token in query.split():
            token = token.strip().lower()
            if token and token in haystack:
                score += 2
    for token in (slot.get("subject", ""), "机车", "创始人"):
        token = token.strip().lower()
        if token and token in haystack:
            score += 1
    slot_name = slot.get("slot", "")
    if slot_name == "product_or_project":
        for token in ("500rr", "产品", "车型", "show&id=", "摩博会", "发布"):
            if token in haystack:
                score += 3
        for token in ("赛事", "wsbk", "夺冠", "赛场", "category&id=3"):
            if token in haystack:
                score -= 1
    if slot_name == "achievement":
        for token in ("赛事", "wsbk", "夺冠", "赛场", "category&id=3"):
            if token in haystack:
                score += 3
        for token in ("500rr", "车型", "产品", "show&id="):
            if token in haystack:
                score -= 1
    if slot_name == "origin_story":
        for token in ("故事", "创始人", "人物", "早年", "机械师"):
            if token in haystack:
                score += 3
        for token in ("赛事", "wsbk", "夺冠", "赛场", "category&id=3"):
            if token in haystack:
                score -= 2
    if slot_name == "hero":
        for token in ("首页", "人物", "品牌", "现场"):
            if token in haystack:
                score += 1
    return score


def slot_kind_bonus(slot_name: str, page_kind: str) -> int:
    if slot_name == "product_or_project":
        return {"product": 4, "brand": 1, "event": -1, "person": 0}.get(page_kind, 0)
    if slot_name == "achievement":
        return {"event": 4, "brand": 0, "product": -1, "person": 0}.get(page_kind, 0)
    if slot_name == "origin_story":
        return {"person": 10, "brand": 2, "event": -2, "product": 0}.get(page_kind, 0)
    if slot_name == "hero":
        return {"event": 4, "person": 3, "brand": -1, "product": -2}.get(page_kind, 0)
    return 0


def slot_tier_bonus(slot_name: str, source_tier: str, page_kind: str) -> int:
    if slot_name == "hero":
        return {
            ("media", "event"): 14,
            ("media", "person"): 9,
            ("official", "event"): 3,
            ("official", "person"): 2,
            ("official", "brand"): -3,
            ("official", "product"): -4,
            ("web", "event"): 1,
        }.get((source_tier, page_kind), 0)
    if slot_name == "achievement":
        return {
            ("media", "event"): 12,
            ("official", "event"): 4,
            ("official", "brand"): -4,
            ("official", "product"): -4,
            ("web", "event"): 1,
        }.get((source_tier, page_kind), 0)
    if slot_name == "origin_story":
        return {
            ("media", "person"): 5,
            ("official", "person"): 6,
            ("official", "brand"): 1,
            ("official", "event"): -3,
            ("official", "product"): -2,
        }.get((source_tier, page_kind), 0)
    if slot_name == "product_or_project":
        return {
            ("official", "product"): 8,
            ("media", "product"): 3,
            ("media", "event"): 1,
            ("official", "event"): -2,
            ("official", "brand"): -2,
        }.get((source_tier, page_kind), 0)
    return 0


def parse_official_candidates(html_text: str, root_url: str, official_domain: str, slot: dict) -> list[dict]:
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    candidates = []
    for href, label in pattern.findall(html_text):
        clean_label = re.sub(r"<[^>]+>", " ", label)
        clean_label = re.sub(r"\s+", " ", clean_label).strip()
        full_url = urljoin(root_url, href)
        domain = urlparse(full_url).netloc
        if not domain.endswith(official_domain.strip(".")):
            continue
        page_kind = classify_page_content(f"{clean_label} {href}", full_url)
        score = official_keyword_score(f"{clean_label} {href}", slot) + slot_kind_bonus(slot.get("slot", ""), page_kind)
        if score <= 0:
            continue
        candidates.append(
            {
                "title": clean_label or href,
                "url": full_url,
                "domain": domain,
                "page_kind": page_kind,
                "source_tier": "official",
                "matched_query": "official-site-link",
                "_score": score,
            }
        )

    if official_keyword_score(html_text, slot) > 0:
        root_kind = classify_page_content(html_text, root_url)
        candidates.append(
            {
                "title": f"{official_domain} 官方首页",
                "url": root_url,
                "domain": urlparse(root_url).netloc,
                "page_kind": root_kind,
                "source_tier": "official",
                "matched_query": "official-site-root",
                "_score": 1 + slot_kind_bonus(slot.get("slot", ""), root_kind),
            }
        )
    return candidates


def parse_candidates(xml_text: str, official_domain: str, matched_query: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    candidates = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not link:
            continue
        domain = urlparse(link).netloc
        candidates.append(
            {
                "title": title,
                "url": link,
                "domain": domain,
                "page_kind": classify_page_content(title, link),
                "source_tier": source_tier_for(domain, official_domain),
                "matched_query": matched_query,
            }
        )
    return candidates


def dedupe_and_rank(candidates: list[dict], limit: int) -> list[dict]:
    seen = set()
    unique = []
    for candidate in candidates:
        url = candidate["url"]
        if url in seen:
            continue
        seen.add(url)
        unique.append(candidate)
    unique.sort(
        key=lambda item: (
            TIER_PRIORITY[item["source_tier"]],
            -item.get("_score", 0),
            item["domain"],
            item["title"],
        )
    )
    trimmed = unique[:limit]
    for candidate in trimmed:
        candidate.pop("_score", None)
    return trimmed


def dedupe_and_rank_for_slot(candidates: list[dict], slot: dict, limit: int) -> list[dict]:
    slot_name = slot.get("slot", "")
    seen = set()
    unique = []
    for candidate in candidates:
        url = candidate["url"]
        if url in seen:
            continue
        seen.add(url)
        candidate["_editorial_score"] = (
            candidate.get("_score", 0)
            + slot_tier_bonus(slot_name, candidate["source_tier"], candidate.get("page_kind", "generic"))
        )
        unique.append(candidate)
    unique.sort(
        key=lambda item: (
            -item.get("_editorial_score", 0),
            TIER_PRIORITY[item["source_tier"]],
            item["domain"],
            item["title"],
        )
    )
    trimmed = unique[:limit]
    for candidate in trimmed:
        candidate.pop("_score", None)
        candidate.pop("_editorial_score", None)
    return trimmed


def build_image_candidates(
    slot: dict,
    official_domain: str,
    official_html: str,
    fixture_rss: str,
    limit: int,
) -> dict:
    searches = []
    search_errors = []
    raw_candidates = []
    if official_domain:
        root_url, html_text = fetch_official_html(official_domain, official_html)
        raw_candidates.extend(parse_official_candidates(html_text, root_url, official_domain, slot))
    for label, query in build_queries(slot, official_domain):
        searches.append(
            {
                "tier": label,
                "query": query,
                "search_url": "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query),
            }
        )
        try:
            xml_text = fetch_rss(query, fixture_rss)
        except Exception as exc:
            search_errors.append({"query": query, "error": str(exc)})
            continue
        raw_candidates.extend(parse_candidates(xml_text, official_domain, query))

    return {
        "slot": slot.get("slot", "unknown"),
        "subject": slot.get("subject", ""),
        "purpose": slot.get("purpose", ""),
        "anchor_text": slot.get("anchor_text", ""),
        "source_hint": slot.get("source_hint", ""),
        "searches": searches,
        "search_errors": search_errors,
        "candidates": dedupe_and_rank_for_slot(raw_candidates, slot, limit),
    }


def main() -> int:
    args = parse_args()
    payload = load_json(args.plan_json)
    images = [
        build_image_candidates(
            slot,
            args.official_domain,
            args.official_html,
            args.fixture_rss,
            args.limit,
        )
        for slot in payload.get("slots", [])
    ]
    print(json.dumps({"images": images}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
