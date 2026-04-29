import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_editorial_package.py"


class BuildEditorialPackageTest(unittest.TestCase):
    def test_merges_plan_sources_and_captions_into_editorial_package(self) -> None:
        plan = {
            "title": "张雪人物稿",
            "slots": [
                {
                    "slot": "hero",
                    "purpose": "establish_person",
                    "anchor_text": "张雪在赛场边观赛。",
                    "subject": "张雪",
                    "source_hint": "官方现场图",
                },
                {
                    "slot": "product_or_project",
                    "purpose": "show_project",
                    "anchor_text": "500RR 在重庆摩博会上发布。",
                    "subject": "张雪",
                    "source_hint": "品牌产品图",
                },
            ],
        }
        sources = {
            "images": [
                {
                    "slot": "hero",
                    "candidates": [
                        {
                            "title": "张雪赛事",
                            "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                            "domain": "www.zxmoto.com",
                            "page_kind": "event",
                            "source_tier": "official",
                        }
                    ],
                },
                {
                    "slot": "product_or_project",
                    "candidates": [
                        {
                            "title": "500RR",
                            "url": "https://www.zxmoto.com/index.php?c=show&id=56",
                            "domain": "www.zxmoto.com",
                            "page_kind": "product",
                            "source_tier": "official",
                        }
                    ],
                },
            ]
        }
        jobs = {
            "jobs": [
                {
                    "slot": "hero",
                    "output_path": "/tmp/hero-1.png",
                    "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                    "title": "张雪赛事",
                    "source_tier": "official",
                },
                {
                    "slot": "product_or_project",
                    "output_path": "/tmp/product_or_project-1.png",
                    "url": "https://www.zxmoto.com/index.php?c=show&id=56",
                    "title": "500RR",
                    "source_tier": "official",
                },
            ]
        }
        assets = {
            "assets": [
                {
                    "slot": "hero",
                    "source_page": "https://www.zxmoto.com/index.php?c=category&id=3",
                    "asset_url": "https://www.zxmoto.com/uploadfile/hero-main.jpg",
                    "output_path": "/tmp/assets/hero-1.jpg",
                },
                {
                    "slot": "product_or_project",
                    "source_page": "https://www.zxmoto.com/index.php?c=show&id=56",
                    "asset_url": "https://www.zxmoto.com/uploadfile/500rr-main.jpg",
                    "output_path": "/tmp/assets/product_or_project-1.jpg",
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "plan.json"
            sources_path = Path(tmpdir) / "sources.json"
            jobs_path = Path(tmpdir) / "jobs.json"
            assets_path = Path(tmpdir) / "assets.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            sources_path.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            assets_path.write_text(json.dumps(assets, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(plan_path),
                    str(sources_path),
                    str(jobs_path),
                    str(assets_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["title"], "张雪人物稿")
        self.assertEqual(len(payload["images"]), 2)
        self.assertIn("张雪", payload["images"][0]["caption"])
        self.assertEqual(payload["images"][1]["page_kind"], "product")
        self.assertEqual(payload["images"][1]["image_path"], "/tmp/assets/product_or_project-1.jpg")

    def test_prefers_extracted_asset_path_over_screenshot_path_when_assets_exist(self) -> None:
        plan = {
            "title": "张雪人物稿",
            "slots": [
                {
                    "slot": "hero",
                    "purpose": "establish_person",
                    "anchor_text": "张雪在赛场边观赛。",
                    "subject": "张雪",
                    "source_hint": "官方现场图",
                }
            ],
        }
        sources = {
            "images": [
                {
                    "slot": "hero",
                    "candidates": [
                        {
                            "title": "张雪赛事",
                            "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                            "domain": "www.zxmoto.com",
                            "page_kind": "event",
                            "source_tier": "official",
                        }
                    ],
                }
            ]
        }
        jobs = {
            "jobs": [
                {
                    "slot": "hero",
                    "output_path": "/tmp/hero-1.png",
                    "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                    "title": "张雪赛事",
                    "source_tier": "official",
                }
            ]
        }
        assets = {
            "assets": [
                {
                    "slot": "hero",
                    "source_page": "https://www.zxmoto.com/index.php?c=category&id=3",
                    "asset_url": "https://www.zxmoto.com/uploadfile/hero-main.jpg",
                    "output_path": "/tmp/assets/hero-1.jpg",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "plan.json"
            sources_path = Path(tmpdir) / "sources.json"
            jobs_path = Path(tmpdir) / "jobs.json"
            assets_path = Path(tmpdir) / "assets.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            sources_path.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            assets_path.write_text(json.dumps(assets, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(plan_path),
                    str(sources_path),
                    str(jobs_path),
                    str(assets_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["images"][0]["image_path"], "/tmp/assets/hero-1.jpg")
        self.assertEqual(payload["images"][0]["asset_url"], "https://www.zxmoto.com/uploadfile/hero-main.jpg")

    def test_does_not_fall_back_to_page_screenshot_when_no_asset_was_extracted(self) -> None:
        plan = {
            "title": "AI 工作流稿",
            "slots": [
                {
                    "slot": "cover",
                    "purpose": "establish_cover",
                    "anchor_text": "这张图应当来自信息源抓取。",
                    "subject": "AI 工作流",
                    "source_hint": "优先新闻现场图",
                }
            ],
        }
        sources = {
            "images": [
                {
                    "slot": "cover",
                    "candidates": [
                        {
                            "title": "媒体报道页",
                            "url": "https://example.com/story",
                            "domain": "example.com",
                            "page_kind": "event",
                            "source_tier": "media",
                        }
                    ],
                }
            ]
        }
        jobs = {
            "jobs": [
                {
                    "slot": "cover",
                    "output_path": "/tmp/screens/cover-1.png",
                    "url": "https://example.com/story",
                    "title": "媒体报道页",
                    "source_tier": "media",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "plan.json"
            sources_path = Path(tmpdir) / "sources.json"
            jobs_path = Path(tmpdir) / "jobs.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            sources_path.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(plan_path),
                    str(sources_path),
                    str(jobs_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["images"][0]["image_path"], "")
        self.assertEqual(payload["images"][0]["asset_url"], "")


if __name__ == "__main__":
    unittest.main()
