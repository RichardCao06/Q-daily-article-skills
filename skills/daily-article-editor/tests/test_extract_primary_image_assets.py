import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_primary_image_assets.py"


class ExtractPrimaryImageAssetsTest(unittest.TestCase):
    def test_prefers_content_image_over_logo_like_assets(self) -> None:
        jobs = {
            "jobs": [
                {
                    "slot": "product_or_project",
                    "title": "500RR",
                    "url": "https://www.example.com/product",
                    "domain": "www.example.com",
                    "source_tier": "official",
                    "output_path": "/tmp/product_or_project-1.png",
                }
            ]
        }

        html = """
        <html><body>
        <img src="/static/logo.svg">
        <img src="/uploadfile/qr.jpg">
        <img src="/uploadfile/500rr-main.jpg">
        </body></html>
        """
        manifest = {
            "https://www.example.com/static/logo.svg": {"width": 200, "height": 40, "format": "SVG"},
            "https://www.example.com/uploadfile/qr.jpg": {"width": 860, "height": 860, "format": "JPEG"},
            "https://www.example.com/uploadfile/500rr-main.jpg": {"width": 1600, "height": 900, "format": "JPEG"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_path = Path(tmpdir) / "jobs.json"
            html_path = Path(tmpdir) / "page.html"
            manifest_path = Path(tmpdir) / "manifest.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(jobs_path),
                    "--fixture-html",
                    str(html_path),
                    "--fixture-manifest",
                    str(manifest_path),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["assets"]), 1)
        asset = payload["assets"][0]
        self.assertIn("500rr-main.jpg", asset["asset_url"])
        self.assertTrue(asset["output_path"].endswith("product_or_project-1.jpg"))

    def test_avoids_reusing_same_asset_when_alternative_exists(self) -> None:
        jobs = {
            "jobs": [
                {
                    "slot": "hero",
                    "title": "人物首图",
                    "url": "https://www.example.com/hero",
                    "domain": "www.example.com",
                    "source_tier": "official",
                    "output_path": "/tmp/hero-1.png",
                },
                {
                    "slot": "origin_story",
                    "title": "人物来路",
                    "url": "https://www.example.com/origin",
                    "domain": "www.example.com",
                    "source_tier": "official",
                    "output_path": "/tmp/origin-1.png",
                },
            ]
        }

        hero_html = """
        <html><body>
        <img src="/uploadfile/shared-main.jpg">
        </body></html>
        """
        origin_html = """
        <html><body>
        <img src="/uploadfile/shared-main.jpg">
        <img src="/uploadfile/origin-alt.jpg">
        </body></html>
        """
        manifest = {
            "https://www.example.com/uploadfile/shared-main.jpg": {"width": 1600, "height": 900, "format": "JPEG"},
            "https://www.example.com/uploadfile/origin-alt.jpg": {"width": 1500, "height": 900, "format": "JPEG"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_path = Path(tmpdir) / "jobs.json"
            html_path = Path(tmpdir) / "pages.json"
            manifest_path = Path(tmpdir) / "manifest.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            html_path.write_text(
                json.dumps(
                    {
                        "https://www.example.com/hero": hero_html,
                        "https://www.example.com/origin": origin_html,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(jobs_path),
                    "--fixture-html",
                    str(html_path),
                    "--fixture-manifest",
                    str(manifest_path),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["assets"][0]["asset_url"], "https://www.example.com/uploadfile/shared-main.jpg")
        self.assertEqual(payload["assets"][1]["asset_url"], "https://www.example.com/uploadfile/origin-alt.jpg")

    def test_reads_og_image_for_media_pages_when_inline_images_are_missing(self) -> None:
        jobs = {
            "jobs": [
                {
                    "slot": "hero",
                    "title": "媒体现场图",
                    "url": "https://www.example.com/news/story",
                    "domain": "www.example.com",
                    "source_tier": "media",
                    "output_path": "/tmp/hero-1.png",
                }
            ]
        }

        html = """
        <html><head>
        <meta property="og:image" content="https://www.example.com/images/wsbk-celebration.jpg">
        <meta name="twitter:image" content="https://www.example.com/images/wsbk-twitter.jpg">
        </head><body>
        <article><p>news story</p></article>
        </body></html>
        """
        manifest = {
            "https://www.example.com/images/wsbk-celebration.jpg": {"width": 1600, "height": 900, "format": "JPEG"},
            "https://www.example.com/images/wsbk-twitter.jpg": {"width": 1200, "height": 675, "format": "JPEG"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_path = Path(tmpdir) / "jobs.json"
            html_path = Path(tmpdir) / "page.html"
            manifest_path = Path(tmpdir) / "manifest.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(jobs_path),
                    "--fixture-html",
                    str(html_path),
                    "--fixture-manifest",
                    str(manifest_path),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["assets"]), 1)
        asset = payload["assets"][0]
        self.assertEqual(asset["asset_url"], "https://www.example.com/images/wsbk-celebration.jpg")

    def test_decodes_html_escaped_image_urls(self) -> None:
        jobs = {
            "jobs": [
                {
                    "slot": "hero",
                    "title": "OpenAI workspace agents",
                    "url": "https://www.example.com/news/story",
                    "domain": "www.example.com",
                    "source_tier": "official",
                    "output_path": "/tmp/hero-1.png",
                }
            ]
        }

        html = """
        <html><head>
        <meta property="og:image" content="https://www.example.com/images/workspace-agents.webp?w=3840&amp;q=90&amp;fm=webp">
        </head><body>
        <article><p>workspace agents</p></article>
        </body></html>
        """
        manifest = {
            "https://www.example.com/images/workspace-agents.webp?w=3840&q=90&fm=webp": {
                "width": 3840,
                "height": 2160,
                "format": "WEBP",
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_path = Path(tmpdir) / "jobs.json"
            html_path = Path(tmpdir) / "page.html"
            manifest_path = Path(tmpdir) / "manifest.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(jobs_path),
                    "--fixture-html",
                    str(html_path),
                    "--fixture-manifest",
                    str(manifest_path),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["assets"]), 1)
        asset = payload["assets"][0]
        self.assertEqual(
            asset["asset_url"],
            "https://www.example.com/images/workspace-agents.webp?w=3840&q=90&fm=webp",
        )

    def test_reads_jsonld_images_for_news_pages(self) -> None:
        jobs = {
            "jobs": [
                {
                    "slot": "achievement",
                    "title": "媒体赛事报道",
                    "url": "https://www.example.com/news/story",
                    "domain": "www.example.com",
                    "source_tier": "media",
                    "output_path": "/tmp/achievement-1.png",
                }
            ]
        }

        html = """
        <html><head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "images": [
            "https://www.example.com/images/wsbk-podium.jpg",
            "https://www.example.com/images/wsbk-team.jpg"
          ]
        }
        </script>
        </head><body>
        <img src="/images/tiny-icon.png">
        </body></html>
        """
        manifest = {
            "https://www.example.com/images/wsbk-podium.jpg": {"width": 1600, "height": 900, "format": "JPEG"},
            "https://www.example.com/images/wsbk-team.jpg": {"width": 1200, "height": 800, "format": "JPEG"},
            "https://www.example.com/images/tiny-icon.png": {"width": 80, "height": 80, "format": "PNG"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_path = Path(tmpdir) / "jobs.json"
            html_path = Path(tmpdir) / "page.html"
            manifest_path = Path(tmpdir) / "manifest.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(jobs_path),
                    "--fixture-html",
                    str(html_path),
                    "--fixture-manifest",
                    str(manifest_path),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["assets"]), 1)
        self.assertEqual(payload["assets"][0]["asset_url"], "https://www.example.com/images/wsbk-podium.jpg")


if __name__ == "__main__":
    unittest.main()
