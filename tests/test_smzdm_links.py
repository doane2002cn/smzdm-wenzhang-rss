import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hermes"))

from smzdm_links import (  # noqa: E402
    InvalidSmzdmUrl,
    build_android_deeplink,
    build_open_url_behaviors,
    build_smzdm_button,
    is_waf_prone_url,
    normalize_smzdm_url,
)


class SmzdmLinkTests(unittest.TestCase):
    def test_android_deeplink_round_trips_original_url(self):
        target = "https://post.smzdm.com/p/abc/?from=feed&x=1"
        deeplink = build_android_deeplink(target)
        parsed = urlsplit(deeplink)
        payload = json.loads(parse_qs(parsed.query)["json"][0])
        self.assertEqual(parsed.scheme, "smzdm")
        self.assertEqual(parsed.netloc, "open")
        self.assertEqual(payload, {"url": target})

    def test_normalization_accepts_smzdm_subdomains_and_upgrades_http(self):
        self.assertEqual(
            normalize_smzdm_url("http://POST.smzdm.com/p/abc/#comments"),
            "https://post.smzdm.com/p/abc/",
        )

    def test_untrusted_or_non_http_urls_are_rejected(self):
        for url in (
            "javascript:alert(1)",
            "https://smzdm.com.evil.example/p/abc/",
            "https://user:pass@post.smzdm.com/p/abc/",
            "https://example.com/?next=https://post.smzdm.com/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidSmzdmUrl):
                    normalize_smzdm_url(url)

    def test_waf_prone_product_uses_article_as_web_fallback(self):
        behavior = build_open_url_behaviors(
            "https://go.smzdm.com/123",
            web_fallback="https://post.smzdm.com/p/abc/",
        )
        self.assertTrue(is_waf_prone_url("https://go.smzdm.com/123"))
        self.assertEqual(behavior["default_url"], "https://post.smzdm.com/p/abc/")
        self.assertEqual(behavior["ios_url"], "https://post.smzdm.com/p/abc/")
        self.assertEqual(behavior["pc_url"], "https://post.smzdm.com/p/abc/")
        app_payload = json.loads(
            parse_qs(urlsplit(behavior["android_url"]).query)["json"][0]
        )
        self.assertEqual(app_payload["url"], "https://go.smzdm.com/123")

    def test_feishu_button_contains_android_scheme(self):
        button = build_smzdm_button(
            "查看原文",
            "https://post.smzdm.com/p/abc/",
            button_type="primary",
        )
        self.assertEqual(button["tag"], "button")
        self.assertEqual(button["text"]["content"], "查看原文")
        behavior = button["behaviors"][0]
        self.assertTrue(behavior["android_url"].startswith("smzdm://open?json="))
        self.assertEqual(behavior["default_url"], "https://post.smzdm.com/p/abc/")


if __name__ == "__main__":
    unittest.main()
