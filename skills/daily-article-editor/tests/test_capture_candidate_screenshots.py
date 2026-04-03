import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_candidate_screenshots.py"


class CaptureCandidateScreenshotsTest(unittest.TestCase):
    def test_builds_screenshot_jobs_for_top_official_candidates(self) -> None:
        payload = {
            "images": [
                {
                    "slot": "product_or_project",
                    "subject": "张雪",
                    "candidates": [
                        {
                            "title": "500RR",
                            "url": "https://www.zxmoto.com/index.php?c=show&id=56",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        },
                        {
                            "title": "媒体稿",
                            "url": "https://www.nbd.com.cn/articles/2026-03-30/4315618.html",
                            "domain": "www.nbd.com.cn",
                            "source_tier": "media",
                        },
                    ],
                }
            ]
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                tmp_path,
                "--output-dir",
                "/tmp/qdaily-shots",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["jobs"]), 1)
        job = data["jobs"][0]
        self.assertEqual(job["source_tier"], "official")
        self.assertTrue(job["output_path"].endswith("product_or_project-1.png"))
        self.assertEqual(job["session_name"], "qd-prorpr-1")

    def test_spreads_slots_across_different_urls_when_possible(self) -> None:
        payload = {
            "images": [
                {
                    "slot": "hero",
                    "subject": "张雪",
                    "candidates": [
                        {
                            "title": "张雪赛事",
                            "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        },
                        {
                            "title": "官方首页",
                            "url": "https://www.zxmoto.com/",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        },
                    ],
                },
                {
                    "slot": "product_or_project",
                    "subject": "张雪",
                    "candidates": [
                        {
                            "title": "张雪赛事",
                            "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        },
                        {
                            "title": "500RR",
                            "url": "https://www.zxmoto.com/index.php?c=show&id=56",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        },
                    ],
                },
            ]
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            ["python3", str(SCRIPT), tmp_path, "--output-dir", "/tmp/qdaily-shots", "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        jobs = {job["slot"]: job for job in data["jobs"]}
        self.assertEqual(jobs["hero"]["url"], "https://www.zxmoto.com/index.php?c=category&id=3")
        self.assertEqual(jobs["product_or_project"]["url"], "https://www.zxmoto.com/index.php?c=show&id=56")

    def test_prefers_reusing_official_candidate_over_dropping_to_unrelated_web(self) -> None:
        payload = {
            "images": [
                {
                    "slot": "hero",
                    "subject": "张雪",
                    "candidates": [
                        {
                            "title": "张雪赛事",
                            "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        }
                    ],
                },
                {
                    "slot": "achievement",
                    "subject": "张雪",
                    "candidates": [
                        {
                            "title": "张雪赛事",
                            "url": "https://www.zxmoto.com/index.php?c=category&id=3",
                            "domain": "www.zxmoto.com",
                            "source_tier": "official",
                        },
                        {
                            "title": "无关网页",
                            "url": "https://www.example.com/",
                            "domain": "www.example.com",
                            "source_tier": "web",
                        },
                    ],
                },
            ]
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            ["python3", str(SCRIPT), tmp_path, "--output-dir", "/tmp/qdaily-shots", "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        jobs = {job["slot"]: job for job in data["jobs"]}
        self.assertEqual(jobs["achievement"]["source_tier"], "official")
        self.assertEqual(jobs["achievement"]["url"], "https://www.zxmoto.com/index.php?c=category&id=3")


if __name__ == "__main__":
    unittest.main()
