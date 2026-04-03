import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import importlib.util


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "source_images.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_search.xml"
OFFICIAL_HTML = Path(__file__).resolve().parent / "fixtures" / "official_root.html"
MEDIA_ONLY_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_media_only.xml"
OFFICIAL_DIVERSE_HTML = Path(__file__).resolve().parent / "fixtures" / "official_root_diverse.html"
SPEC = importlib.util.spec_from_file_location("source_images_module", SCRIPT)
SOURCE_IMAGES = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SOURCE_IMAGES)


class SourceImagesTest(unittest.TestCase):
    def test_build_queries_enriches_hero_with_event_terms_from_anchor_text(self) -> None:
        slot = {
            "slot": "hero",
            "purpose": "establish_person",
            "anchor_text": "2026 年 3 月 28 日，葡萄牙，WSBK 中量级赛场，一辆来自中国的赛车第一个冲过终点。",
            "subject": "张雪",
            "query": ["张雪 现场", "张雪 人物"],
            "source_hint": "优先赛事现场图或媒体人物图",
        }

        queries = SOURCE_IMAGES.build_queries(slot, "zxmoto.com")
        texts = [query for _, query in queries]

        self.assertTrue(any("WSBK" in query for query in texts))
        self.assertTrue(any("夺冠" in query or "赛场" in query for query in texts))

    def test_classifies_page_content_by_title_url_and_text(self) -> None:
        product = SOURCE_IMAGES.classify_page_content(
            "500RR_摩托车系列_产品世界_ZXMOTO张雪机车 产品 车型 参数",
            "https://www.zxmoto.com/index.php?c=show&id=56",
        )
        event = SOURCE_IMAGES.classify_page_content(
            "张雪赛事_ZXMOTO张雪机车 赛事 比赛 赛道",
            "https://www.zxmoto.com/index.php?c=category&id=3",
        )
        person = SOURCE_IMAGES.classify_page_content(
            "品牌故事 ZXMOTO 张雪 创始人 人物 故事",
            "https://www.zxmoto.com/index.php?c=category&id=16",
        )

        self.assertEqual(product, "product")
        self.assertEqual(event, "event")
        self.assertEqual(person, "person")

    def test_builds_candidates_and_prioritizes_official_domain(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "product_or_project",
                    "purpose": "show_project",
                    "anchor_text": "500RR 在重庆摩博会上发布。",
                    "subject": "张雪",
                    "query": ["张雪 500RR", "张雪 重庆摩博会"],
                    "source_hint": "优先品牌产品图或发布现场图",
                }
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(plan, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                tmp_path,
                "--official-domain",
                "zxmoto.com",
                "--fixture-rss",
                str(FIXTURE),
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["images"]), 1)
        searches = payload["images"][0]["searches"]
        self.assertTrue(any("机车" in item["query"] for item in searches))
        candidates = payload["images"][0]["candidates"]
        self.assertEqual(candidates[0]["domain"], "www.zxmoto.com")
        self.assertEqual(candidates[0]["source_tier"], "official")
        self.assertEqual(candidates[0]["page_kind"], "product")
        self.assertLessEqual(len(candidates), 2)

    def test_uses_official_site_links_even_when_search_results_are_media_only(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "product_or_project",
                    "purpose": "show_project",
                    "anchor_text": "500RR 在重庆摩博会上发布。",
                    "subject": "张雪",
                    "query": ["张雪 500RR"],
                    "source_hint": "优先品牌产品图或发布现场图",
                }
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(plan, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                tmp_path,
                "--official-domain",
                "zxmoto.com",
                "--official-html",
                str(OFFICIAL_HTML),
                "--fixture-rss",
                str(MEDIA_ONLY_FIXTURE),
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        candidates = payload["images"][0]["candidates"]
        self.assertEqual(candidates[0]["source_tier"], "official")
        self.assertIn("500RR", candidates[0]["title"])

    def test_slot_specific_official_scoring_prefers_product_page_for_product_slot(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "product_or_project",
                    "purpose": "show_project",
                    "anchor_text": "500RR 在重庆摩博会上发布。",
                    "subject": "张雪",
                    "query": ["张雪 500RR", "张雪 重庆摩博会"],
                    "source_hint": "优先品牌产品图或发布现场图",
                },
                {
                    "slot": "achievement",
                    "purpose": "show_achievement",
                    "anchor_text": "WSBK 葡萄牙赛场夺冠。",
                    "subject": "张雪",
                    "query": ["张雪 WSBK", "张雪 葡萄牙 夺冠"],
                    "source_hint": "优先赛事现场图或成绩截图",
                },
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(plan, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                tmp_path,
                "--official-domain",
                "zxmoto.com",
                "--official-html",
                str(OFFICIAL_DIVERSE_HTML),
                "--fixture-rss",
                str(MEDIA_ONLY_FIXTURE),
                "--limit",
                "3",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        product_candidates = payload["images"][0]["candidates"]
        achievement_candidates = payload["images"][1]["candidates"]
        self.assertIn("500RR", product_candidates[0]["title"])
        self.assertIn("赛事", achievement_candidates[0]["title"])

    def test_origin_story_prefers_person_page_over_event_page(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "origin_story",
                    "purpose": "prove_process",
                    "anchor_text": "他早年在车队做特技车手兼机械师，后来才开始做产品。",
                    "subject": "张雪",
                    "query": ["张雪 赛车", "张雪 机械师", "张雪 创始人"],
                    "source_hint": "优先人物来路或职业转折相关页面",
                }
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(plan, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                tmp_path,
                "--official-domain",
                "zxmoto.com",
                "--official-html",
                str(OFFICIAL_DIVERSE_HTML),
                "--fixture-rss",
                str(MEDIA_ONLY_FIXTURE),
                "--limit",
                "3",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        candidates = payload["images"][0]["candidates"]
        self.assertEqual(candidates[0]["page_kind"], "person")
        self.assertIn("品牌故事", candidates[0]["title"])

    def test_search_failure_does_not_break_official_candidates(self) -> None:
        slot = {
            "slot": "product_or_project",
            "purpose": "show_project",
            "anchor_text": "500RR 在重庆摩博会上发布。",
            "subject": "张雪",
            "query": ["张雪 500RR"],
            "source_hint": "优先品牌产品图或发布现场图",
        }

        with mock.patch.object(SOURCE_IMAGES, "fetch_rss", side_effect=RuntimeError("timeout")):
            result = SOURCE_IMAGES.build_image_candidates(
                slot,
                "zxmoto.com",
                str(OFFICIAL_DIVERSE_HTML),
                "",
                3,
            )

        self.assertGreaterEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["source_tier"], "official")

    def test_hero_slot_prefers_media_event_photo_over_official_brand_page(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "hero",
                    "purpose": "establish_person",
                    "anchor_text": "WSBK 夺冠后的庆祝现场。",
                    "subject": "张雪",
                    "query": ["张雪 WSBK 庆祝"],
                    "source_hint": "优先赛事现场图或媒体现场图",
                }
            ],
        }
        hero_rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>张雪机车在 WSBK 赛后庆祝</title>
            <link>https://www.nbd.com.cn/articles/2026-03-30/4315618.html</link>
          </item>
          <item>
            <title>张雪机车品牌介绍</title>
            <link>https://example.com/brand-story</link>
          </item>
        </channel></rss>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "plan.json"
            rss_path = Path(tmpdir) / "hero.xml"
            tmp_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            rss_path.write_text(hero_rss, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(tmp_path),
                    "--official-domain",
                    "zxmoto.com",
                    "--official-html",
                    str(OFFICIAL_DIVERSE_HTML),
                    "--fixture-rss",
                    str(rss_path),
                    "--limit",
                    "3",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        top = payload["images"][0]["candidates"][0]
        self.assertEqual(top["source_tier"], "media")
        self.assertEqual(top["page_kind"], "event")

    def test_product_slot_still_prefers_official_product_page_over_media(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "product_or_project",
                    "purpose": "show_project",
                    "anchor_text": "500RR 在重庆摩博会上发布。",
                    "subject": "张雪",
                    "query": ["张雪 500RR"],
                    "source_hint": "优先品牌产品图或发布现场图",
                }
            ],
        }
        product_rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>张雪机车 500RR 发布现场</title>
            <link>https://www.nbd.com.cn/articles/2026-03-30/4315618.html</link>
          </item>
        </channel></rss>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "plan.json"
            rss_path = Path(tmpdir) / "product.xml"
            tmp_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            rss_path.write_text(product_rss, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(tmp_path),
                    "--official-domain",
                    "zxmoto.com",
                    "--official-html",
                    str(OFFICIAL_DIVERSE_HTML),
                    "--fixture-rss",
                    str(rss_path),
                    "--limit",
                    "3",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        top = payload["images"][0]["candidates"][0]
        self.assertEqual(top["source_tier"], "official")
        self.assertEqual(top["page_kind"], "product")


if __name__ == "__main__":
    unittest.main()
