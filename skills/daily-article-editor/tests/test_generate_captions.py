import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_captions.py"


class GenerateCaptionsTest(unittest.TestCase):
    def test_builds_concise_captions_and_placement_notes(self) -> None:
        plan = {
            "article_type": "profile",
            "slots": [
                {
                    "slot": "hero",
                    "purpose": "establish_person",
                    "anchor_text": "张雪在工厂和团队一起复盘。",
                    "subject": "张雪",
                    "source_hint": "官方现场图",
                },
                {
                    "slot": "product_or_project",
                    "purpose": "show_project",
                    "anchor_text": "500RR 在重庆摩博会上发布。",
                    "subject": "500RR",
                    "source_hint": "品牌发布图",
                },
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(plan, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = subprocess.run(
            ["python3", str(SCRIPT), tmp_path],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["images"]), 2)
        self.assertIn("张雪", payload["images"][0]["caption"])
        self.assertIn("建议插入", payload["images"][0]["placement_note"])


if __name__ == "__main__":
    unittest.main()
