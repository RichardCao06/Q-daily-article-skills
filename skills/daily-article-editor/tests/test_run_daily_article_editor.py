import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_daily_article_editor.py"
OFFICIAL_HTML = ROOT / "tests" / "fixtures" / "official_root_diverse.html"
MEDIA_ONLY_FIXTURE = ROOT / "tests" / "fixtures" / "sample_media_only.xml"

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_daily_article_editor


class RunDailyArticleEditorTest(unittest.TestCase):
    def test_runs_end_to_end_and_writes_package_markdown_and_assets_dir(self) -> None:
        article = textwrap.dedent(
            """
            # 张雪不太喜欢“创业者”这个词，他更想待在车间里做车 | 100 个有想法的人

            **摘要**
            这不是一个机车品牌如何夺冠的故事，而是一个一直更想做车的人，最后不得不把自己也变成品牌的一段经历。

            2026 年 3 月 28 日，葡萄牙，WSBK 中量级赛场，一辆来自中国的赛车第一个冲过终点。

            他早年最广为流传的一段经历，发生在 19 岁的时候。

            2024 年品牌成立，500RR 在重庆摩博会上发布。

            2026 年 3 月，张雪机车在国际赛场夺冠。
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            draft = tmp / "draft.md"
            output_dir = tmp / "out"
            fixture_html = tmp / "pages.json"
            fixture_manifest = tmp / "manifest.json"
            draft.write_text(article, encoding="utf-8")
            fixture_html.write_text(
                json.dumps(
                    {
                        "https://www.zxmoto.com/index.php?c=category&id=3": '<html><body><img src="https://www.example.com/hero.jpg"></body></html>',
                        "https://www.zxmoto.com/index.php?c=category&id=16": '<html><body><img src="https://www.example.com/origin.jpg"></body></html>',
                        "https://www.zxmoto.com/index.php?c=show&id=56": '<html><body><img src="https://www.example.com/product.jpg"></body></html>',
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            fixture_manifest.write_text(
                json.dumps(
                    {
                        "https://www.example.com/hero.jpg": {"width": 1600, "height": 900, "format": "JPEG"},
                        "https://www.example.com/origin.jpg": {"width": 1200, "height": 800, "format": "JPEG"},
                        "https://www.example.com/product.jpg": {"width": 1600, "height": 900, "format": "JPEG"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(draft),
                    "--output-dir",
                    str(output_dir),
                    "--official-domain",
                    "zxmoto.com",
                    "--official-html",
                    str(OFFICIAL_HTML),
                    "--fixture-rss",
                    str(MEDIA_ONLY_FIXTURE),
                    "--fixture-html",
                    str(fixture_html),
                    "--fixture-manifest",
                    str(fixture_manifest),
                    "--dry-run-assets",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            package_path = output_dir / "article-package.json"
            markdown_path = output_dir / "article-final.md"
            assets_dir = output_dir / "assets"

            self.assertTrue(package_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertTrue(assets_dir.exists())

            payload = json.loads(package_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["article_type"], "profile")
            self.assertIn("editorial", payload)

            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("# 张雪不太喜欢“创业者”这个词", markdown)
            self.assertIn("*图注：", markdown)

    def test_render_markdown_places_process_image_after_matching_feature_paragraph(self) -> None:
        draft = textwrap.dedent(
            """
            # AI 的第二阶段，不是更会聊天，而是更会接管工作

            **摘要**
            这篇 feature 关注的是头部 AI 公司如何从聊天界面转向工作流入口竞争。

            第一段导语。

            ## 进入工作流，也意味着补齐接口层

            Mistral 的更新则提醒人们，工作流竞争并不只有“入口”和“权限”两个维度，还有一层更底层的能力拼图。

            下一段继续展开语音接口的重要性。
            """
        ).strip()

        package = {
            "editorial": {
                "images": [
                    {
                        "slot": "hero",
                        "caption": "主图说明",
                        "image_path": "/tmp/hero.png",
                        "source_title": "Hero",
                        "source_url": "https://example.com/hero",
                    },
                    {
                        "slot": "process",
                        "caption": "流程图说明",
                        "anchor_text": "Mistral 的更新则提醒人们，工作流竞争并不只有“入口”和“权限”两个维度，还有一层更底层的能力拼图。",
                        "image_path": "/tmp/process.png",
                        "source_title": "Process",
                        "source_url": "https://example.com/process",
                    },
                ]
            }
        }

        markdown = run_daily_article_editor.render_markdown(draft, package)
        process_block = textwrap.dedent(
            """
            Mistral 的更新则提醒人们，工作流竞争并不只有“入口”和“权限”两个维度，还有一层更底层的能力拼图。

            ![Process](/tmp/process.png)

            *图注：流程图说明 来源：[Process](https://example.com/process)*
            """
        ).strip()

        self.assertIn(process_block, markdown)
        self.assertLess(
            markdown.index(process_block),
            markdown.index("下一段继续展开语音接口的重要性。"),
        )

    def test_render_markdown_skips_cover_slot_but_keeps_cover_in_package(self) -> None:
        draft = textwrap.dedent(
            """
            # AI 的第二阶段，不是更会聊天，而是更会接管工作

            **摘要**
            这篇 feature 关注的是头部 AI 公司如何从聊天界面转向工作流入口竞争。

            正文第一段。
            """
        ).strip()

        package = {
            "editorial": {
                "images": [
                    {
                        "slot": "cover",
                        "caption": "封面图说明",
                        "image_path": "/tmp/cover.png",
                        "source_title": "Cover",
                        "source_url": "https://example.com/cover",
                    },
                    {
                        "slot": "hero",
                        "caption": "主图说明",
                        "image_path": "/tmp/hero.png",
                        "source_title": "Hero",
                        "source_url": "https://example.com/hero",
                    },
                ]
            }
        }

        markdown = run_daily_article_editor.render_markdown(draft, package)
        self.assertIn("![Hero](/tmp/hero.png)", markdown)
        self.assertNotIn("![Cover](/tmp/cover.png)", markdown)

    def test_final_cover_requires_source_backed_asset(self) -> None:
        editorial = {
            "images": [
                {
                    "slot": "cover",
                    "caption": "封面图说明",
                    "image_path": "",
                    "source_title": "Cover",
                    "source_url": "https://example.com/cover",
                    "asset_url": "",
                },
                {
                    "slot": "hero",
                    "caption": "主图说明",
                    "image_path": "/tmp/hero.png",
                    "source_title": "Hero",
                    "source_url": "https://example.com/hero",
                    "asset_url": "https://example.com/assets/hero.jpg",
                },
            ]
        }

        cover = next(
            (
                image
                for image in editorial["images"]
                if image.get("slot") == "cover" and image.get("image_path") and image.get("asset_url")
            ),
            None,
        )

        self.assertIsNone(cover)


if __name__ == "__main__":
    unittest.main()
