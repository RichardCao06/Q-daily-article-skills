import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_article_package.py"


class BuildArticlePackageTest(unittest.TestCase):
    def test_builds_full_editorial_package_from_markdown_draft(self) -> None:
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

        self.assertEqual(payload["title"], "张雪不太喜欢“创业者”这个词，他更想待在车间里做车 | 100 个有想法的人")
        self.assertEqual(payload["article_type"], "profile")
        self.assertIn("writing", payload)
        self.assertIn("images", payload)
        self.assertIn("layout", payload)
        self.assertGreaterEqual(len(payload["images"]), 3)
        self.assertEqual(payload["layout"]["output_format"], "markdown")
        self.assertIn("正式发稿", payload["writing"]["edit_goal"])


if __name__ == "__main__":
    unittest.main()
