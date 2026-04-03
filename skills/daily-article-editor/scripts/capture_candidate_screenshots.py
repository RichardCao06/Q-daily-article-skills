#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path


TIER_ORDER = {"official": 0, "media": 1, "web": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_json")
    parser.add_argument("--output-dir", default="output/playwright/qdaily-image-editor")
    parser.add_argument("--per-slot", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return slug or "shot"


def session_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "shot"


def compact_session_name(slot: str, index: int) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", slot.replace("_", "-"))
    short = "".join(part[:2].lower() for part in parts if part)[:8]
    short = short or "shot"
    return f"qd-{short}-{index}"


def build_jobs(payload: dict, output_dir: str, per_slot: int) -> list[dict]:
    jobs = []
    output_root = Path(output_dir)
    used_urls = set()
    for image in payload.get("images", []):
        slot = image.get("slot", "slot")
        candidates = sorted(
            image.get("candidates", []),
            key=lambda item: TIER_ORDER.get(item.get("source_tier", "web"), 9),
        )
        picked = []
        if candidates:
            best_tier_value = TIER_ORDER.get(candidates[0].get("source_tier", "web"), 9)
            same_tier = [
                candidate
                for candidate in candidates
                if TIER_ORDER.get(candidate.get("source_tier", "web"), 9) == best_tier_value
            ]
            lower_tier = [
                candidate
                for candidate in candidates
                if TIER_ORDER.get(candidate.get("source_tier", "web"), 9) != best_tier_value
            ]
            selection_order = (
                [candidate for candidate in same_tier if candidate.get("url") not in used_urls]
                + same_tier
                + [candidate for candidate in lower_tier if candidate.get("url") not in used_urls]
                + lower_tier
            )
        else:
            selection_order = []

        for candidate in selection_order:
            if candidate in picked:
                continue
            picked.append(candidate)
            used_urls.add(candidate.get("url"))
            if len(picked) >= per_slot:
                break
        for index, candidate in enumerate(picked, start=1):
            output_path = output_root / f"{slugify(slot)}-{index}.png"
            jobs.append(
                {
                    "slot": slot,
                    "title": candidate.get("title", ""),
                    "url": candidate.get("url", ""),
                    "domain": candidate.get("domain", ""),
                    "source_tier": candidate.get("source_tier", "web"),
                    "output_path": str(output_path),
                    "session_name": compact_session_name(slot, index),
                }
            )
    return jobs


def run_screenshot(job: dict) -> None:
    output_path = Path(job["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    codex_home = os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    pwcli = Path(codex_home) / "skills" / "playwright" / "scripts" / "playwright_cli.sh"
    session = job["session_name"]

    env = os.environ.copy()
    env["PLAYWRIGHT_CLI_SESSION"] = session

    subprocess.run(
        [str(pwcli), "close"],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    open_error = None
    for attempt in range(2):
        result = subprocess.run(
            [str(pwcli), "open", job["url"]],
            check=False,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            open_error = None
            break
        open_error = result.stderr or result.stdout
        time.sleep(1.0)
    if open_error is not None:
        raise RuntimeError(f"failed to open {job['url']}: {open_error.strip()}")
    subprocess.run(
        [str(pwcli), "screenshot", "--filename", str(output_path)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    subprocess.run(
        [str(pwcli), "close"],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    args = parse_args()
    payload = load_json(args.source_json)
    jobs = build_jobs(payload, args.output_dir, args.per_slot)
    if not args.dry_run:
        for job in jobs:
            run_screenshot(job)
    print(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
