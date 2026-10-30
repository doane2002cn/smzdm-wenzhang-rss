import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hermes"))

from smzdm_deal_alert import render_card as render_deal_card  # noqa: E402
from smzdm_digest import (  # noqa: E402
    SEC_AI,
    SEC_LAJI,
    SEC_RANK,
    SEC_SW,
    render_card as render_digest_card,
)


def article(index, section):
    return {
        "title": f"{section}文章 {index}",
        "link": f"https://post.smzdm.com/p/{section}{index}/",
        "intro": "测试简介",
        "cat": section,
    }


class SmzdmCardTests(unittest.TestCase):
    def test_digest_uses_text_headings_and_app_first_buttons(self):
        ai = [article(1, "ai")]
        software = [article(1, "software")]
        garbage = [article(1, "garbage")]
        rank = [article(index, "rank") for index in range(1, 13)]
        sections = {
            SEC_AI: ai,
            SEC_SW: software,
            SEC_LAJI: garbage,
            SEC_RANK: rank,
            "editorial": [],
        }
        card = render_digest_card(
            sections,
            reads=[{"n": 1, "why": "值得关注"}],
            summary="今日总结",
            last_build=datetime.now(),
            delayed=False,
            ai_broken=False,
            pool=ai,
        )

        actions = [
            action
            for element in card["elements"]
            if element.get("tag") == "action"
            for action in element.get("actions", [])
        ]
        self.assertTrue(actions)
        self.assertTrue(all(
            action["behaviors"][0]["android_url"].startswith("smzdm://open?json=")
            for action in actions
        ))
        rendered = json.dumps(card, ensure_ascii=False)
        self.assertNotIn("](https://", rendered)

    def test_deal_product_button_uses_article_as_web_fallback(self):
        deal = {
            "it": {
                "title": "测试商品",
                "link": "https://post.smzdm.com/p/deal/",
                "cat": "电脑配件好价",
            },
            "buy": "https://go.smzdm.com/product",
            "price": 99.0,
            "orig": 129.0,
            "drop": 23.3,
            "drop_calc": 23.3,
            "newlow_days": 30,
            "newlow_meta": False,
            "platform": "京东",
            "complex": False,
            "conds": ["下单 1 件"],
            "specs": ["16GB"],
            "color": "green",
            "group_label": "电脑配件",
        }
        card = render_deal_card([deal], ai=None, header_color="green")
        buttons = card["elements"][2]["actions"]

        product = buttons[0]["behaviors"][0]
        self.assertEqual(product["default_url"], deal["it"]["link"])
        self.assertTrue(product["android_url"].startswith("smzdm://open?json="))
        original = buttons[1]["behaviors"][0]
        self.assertTrue(original["android_url"].startswith("smzdm://open?json="))


if __name__ == "__main__":
    unittest.main()
