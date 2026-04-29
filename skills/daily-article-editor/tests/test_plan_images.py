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
        self.assertIn("cover", slots)
        self.assertIn("hero", slots)
        self.assertIn("origin_story", slots)
        self.assertIn("product_or_project", slots)
        self.assertIn("achievement", slots)
        self.assertEqual(slots["hero"]["purpose"], "establish_person")

    def test_extracts_supporting_profile_slots_without_forcing_product_slots(self) -> None:
        article = textwrap.dedent(
            """
            # 何琼没有把张雪养在身边，但她在很多关键时刻都接住了他

            **摘要**
            这是一篇关于母子关系和支撑角色的人物稿。

            2026 年 3 月，张雪机车在 WSBK 葡萄牙站夺冠之后，关于张雪的报道突然变多了。人们重新注意到另一个名字：何琼。

            据界面新闻和新浪财经等报道，何琼早年因为生计曾远赴外地报社做采编，收入不高。

            张雪后来回忆过，小时候母亲给他买过一辆儿童自行车。

            公开流传最广的一件事，是她曾抵押房产贷款 55 万元支持张雪创业。
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

        slots = {slot["slot"]: slot for slot in payload["slots"]}
        self.assertIn("hero", slots)
        self.assertIn("origin_story", slots)
        self.assertIn("archive", slots)
        self.assertEqual(slots["hero"]["subject"], "何琼")
        self.assertNotIn("product_or_project", slots)

    def test_extracts_feature_slots_and_keeps_process_anchor_on_matching_paragraph(self) -> None:
        article = textwrap.dedent(
            """
            # AI 的第二阶段，不是更会聊天，而是更会接管工作

            **摘要**
            这是一篇解释 AI 如何进入真实工作流的 feature。

            2026 年 4 月的这一周，几家最重要的 AI 公司几乎同时发出了同一种信号：下一轮竞争的重点，正在从“谁的模型更强”转向“谁能更早进入真实工作流”。

            Meta 在官方 Newsroom 发布了 Muse Spark，表示这套模型已经开始驱动 Meta AI app 与网站，并将继续扩展到 WhatsApp、Instagram、Facebook 以及 AI 眼镜。

            Mistral 的更新则提醒人们，工作流竞争并不只有“入口”和“权限”两个维度，还有一层更底层的能力拼图。几天后，Mistral 又发布了 Speaking of Voxtral，把多语种文本转语音能力补到自己的产品堆栈里。语音看起来像是一个边缘功能，但如果把 AI 理解成会进入真实工作流的代理层，语音根本不是边角料，而是一种关键接口。
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

        self.assertEqual(payload["article_type"], "feature")
        slots = {slot["slot"]: slot for slot in payload["slots"]}
        self.assertIn("cover", slots)
        self.assertIn("hero", slots)
        self.assertIn("object", slots)
        self.assertIn("process", slots)
        self.assertEqual(slots["hero"]["purpose"], "establish_shift")
        self.assertEqual(slots["cover"]["purpose"], "establish_cover")
        self.assertIn("Mistral", slots["process"]["anchor_text"])
        self.assertIn("语音", slots["process"]["anchor_text"])

    def test_marks_news_driven_feature_as_event_news_mode(self) -> None:
        article = textwrap.dedent(
            """
            # 苹果 App Store 下架了越来越多的网络访问工具，只针对中国

            **摘要**
            这不是一次单独下架，而是平台规则、监管环境和产品分发权力开始一起起作用的信号。

            近日，苹果商店又移除了中国区里的一批主流 VPN 应用。

            根据路透社的消息，知名 VPN 服务供应商 ExpressVPN 昨日发布通知称，收到苹果的紧急通知。

            今年 1 月 22 日，工信部发布通知，宣布在全国范围内对互联网接入服务市场开展清理。

            苹果对此不予置评，但这次动作真正值得注意的地方，不只是某几个工具下架，而是平台、监管和分发之间的关系变得更直接了。
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

        self.assertEqual(payload["article_type"], "feature")
        self.assertEqual(payload["feature_mode"], "event-news")
        self.assertGreaterEqual(len(payload["slots"]), 2)

    def test_marks_policy_explainer_feature_as_policy_rules_mode(self) -> None:
        article = textwrap.dedent(
            """
            # 游戏越来越像赌博，苹果开始要求游戏公布开箱率

            **摘要**
            这不只是一次开发者协议更新，而是平台开始把原本模糊的抽卡和开箱机制，往更接近规则约束的方向推。

            在最新的苹果开发者协议中，应用内购买板块增加了新要求：凡是在应用中提供开箱或随机虚拟物品回报的机制，开发者都必须公布获得每个物品的概率。

            这条规定看起来只是披露要求，但它背后对应的是一个更大的争议：当游戏越来越像赌博，平台到底要不要承担更明确的约束责任。

            过去欧美市场并没有统一规则，但中国监管者和 Google 等平台已经开始要求相关透明化披露。

            所以真正值得注意的，不只是苹果改了一条协议，而是平台、开发商和玩家之间围绕规则边界的关系正在变化。
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

        self.assertEqual(payload["article_type"], "feature")
        self.assertEqual(payload["feature_mode"], "policy-rules")

    def test_marks_company_direction_feature_as_company_shift_mode(self) -> None:
        article = textwrap.dedent(
            """
            # 亚马逊电影部门决定减少独立电影的比例，要拍更多商业片

            **摘要**
            这不是一次普通片单调整，而是亚马逊在视频业务里重新计算品牌名声、会员增长和全球市场之间的取舍。

            据路透社，亚马逊视频制作部门决定以后将投入更多精力在商业大电影上，减少独立电影的制作比例。

            电视剧方面也采取同样策略，亚马逊已经高价争取更大体量的系列内容。

            真正值得写的不是它拍什么，而是这家公司为什么会在这个时间点改变内容方向，以及这种调整会怎样改变它原来的业务位置。

            独立电影帮助亚马逊建立起名声，但全球票房和更广泛受众最终还是把它推向了另一种更重规模的路线。
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

        self.assertEqual(payload["article_type"], "feature")
        self.assertEqual(payload["feature_mode"], "company-shift")

    def test_marks_data_trend_feature_as_data_trend_mode(self) -> None:
        article = textwrap.dedent(
            """
            # 去年中国人均使用快递 23 件，花费 287.4 元

            **摘要**
            这不只是一个行业统计数字，而是消费密度、物流基础设施和平台习惯一起变化之后留下来的截面。

            根据最新发布的行业数据，去年中国人均使用快递 23 件，年花费 287.4 元。

            如果只看这个数字，它像是一条普通统计新闻；但把它放回过去几年的电商渗透、城市层级差异和物流网络扩张里，它其实更像一种消费趋势的结果。

            真正值得解释的，不是 23 件这个数字本身，而是为什么快递已经变成一种被日常化的生活基础设施，以及这种增长具体由哪些变量推动。

            数据背后能拆开的因素至少包括平台促销密度、下沉市场覆盖、配送网络效率和人们对即时购物的习惯变化。
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

        self.assertEqual(payload["article_type"], "feature")
        self.assertEqual(payload["feature_mode"], "data-trend")


if __name__ == "__main__":
    unittest.main()
