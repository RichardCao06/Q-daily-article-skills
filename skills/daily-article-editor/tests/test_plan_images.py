import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan_images.py"


class PlanImagesTest(unittest.TestCase):
    def test_extracts_visual_slots_from_markdown_article(self) -> None:
        article = textwrap.dedent(
            """
            # 张雪不太喜欢“创业者”这个词

            **摘要**
            这是一篇人物特写。

            2026 年 3 月 28 日，葡萄牙赛场上，一辆中国赛车冲线。

            张雪后来回到重庆，在工厂和团队一起复盘。

            ## 从车手到创始人

            2006 年到 2008 年，他在车队做特技车手兼机械师。

            ## 品牌开始成形

            2024 年，张雪机车成立，500RR 在重庆摩博会上发布。
            """
        ).strip()

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tmp:
            tmp.write(article)
            tmp_path = tmp.name

        result = subprocess.run(
            ["python3", str(SCRIPT), tmp_path],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)

        self.assertEqual(payload["article_type"], "profile")
        self.assertGreaterEqual(len(payload["slots"]), 3)

        slots = {slot["slot"]: slot for slot in payload["slots"]}
        self.assertIn("hero", slots)
        self.assertIn("origin_story", slots)
        self.assertIn("product_or_project", slots)
        self.assertIn("achievement", slots)
        self.assertEqual(slots["hero"]["purpose"], "establish_person")


if __name__ == "__main__":
    unittest.main()
