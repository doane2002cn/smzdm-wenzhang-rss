import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_digest import Item, TZ, parse_datetime, select_garbage_items


class GarbageSelectionTests(unittest.TestCase):
    def test_parse_datetime_keeps_full_month_day(self):
        parsed = parse_datetime("10-16 16:51")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.month, parsed.day, parsed.hour, parsed.minute), (10, 16, 16, 51))

    def test_parse_datetime_handles_relative_days(self):
        now = datetime.now(TZ)
        parsed = parse_datetime("昨天 13:42")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.date(), (now - timedelta(days=1)).date())

    def test_consecutive_days_do_not_reuse_urls(self):
        now = datetime.now(TZ)
        items = [
            Item(
                kind="article",
                source="搜索:垃圾佬",
                title=f"垃圾佬测试文章 {index}",
                url=f"https://post.smzdm.com/p/test{index}/",
                published_at=(now - timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                description="垃圾佬 捡垃圾 E5 X99 测试内容",
            )
            for index in range(1, 7)
        ]
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "garbage_state.json"
            day_one = select_garbage_items(items, state_file, now, count=3)
            day_two = select_garbage_items(
                items,
                state_file,
                now + timedelta(days=1),
                count=3,
            )
        day_one_urls = {item.url for item in day_one}
        day_two_urls = {item.url for item in day_two}
        self.assertEqual(len(day_one_urls), 3)
        self.assertEqual(len(day_two_urls), 3)
        self.assertFalse(day_one_urls & day_two_urls)


if __name__ == "__main__":
    unittest.main()
