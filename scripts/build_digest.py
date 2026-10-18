#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    TZ = timezone(timedelta(hours=8), name="CST")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/140 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9",
}

DEAL_FEED = "http://feed.smzdm.com"
ARTICLE_FEED = "https://post.smzdm.com/feed"
FOOD_CATEGORY_SOURCES = [
    ("禽蛋肉类", "https://www.smzdm.com/fenlei/xianrouqindan/"),
    ("蔬菜", "https://www.smzdm.com/fenlei/shucai/"),
    ("米面杂粮", "https://www.smzdm.com/fenlei/mimianzaliang/"),
    ("食用油", "https://www.smzdm.com/fenlei/shiyongyou/"),
    ("调味品", "https://www.smzdm.com/fenlei/diaoweipin/"),
    ("奶类制品", "https://www.smzdm.com/fenlei/naichanpin/"),
    ("坚果炒货", "https://www.smzdm.com/fenlei/jianguochaohuo/"),
    ("饼干糕点", "https://www.smzdm.com/fenlei/binggangaodian/"),
    ("肉干肉脯", "https://www.smzdm.com/fenlei/rouganroupu/"),
]

ALCOHOL_CATEGORY_SOURCES = [
    ("白酒", "https://www.smzdm.com/fenlei/baijiu/"),
    ("啤酒", "https://www.smzdm.com/fenlei/pijiu/"),
    ("洋酒", "https://www.smzdm.com/fenlei/yangjiu/"),
    ("葡萄酒", "https://www.smzdm.com/fenlei/putaojiu/"),
    ("黄酒/养生酒", "https://www.smzdm.com/fenlei/huangjiuyangshengjiu/"),
    ("其他酒类", "https://www.smzdm.com/fenlei/qitajiulei/"),
]

COMPUTER_CATEGORY_SOURCES = [
    ("CPU", "https://www.smzdm.com/fenlei/cpu/"),
    ("主板", "https://www.smzdm.com/fenlei/zhuban/"),
    ("显卡", "https://www.smzdm.com/fenlei/xianka/"),
    ("硬盘", "https://www.smzdm.com/fenlei/yingpan/"),
    ("内存", "https://www.smzdm.com/fenlei/neicun/"),
    ("机箱", "https://www.smzdm.com/fenlei/jixiang/"),
    ("电脑电源", "https://www.smzdm.com/fenlei/dianyuan/"),
    ("显示器", "https://www.smzdm.com/fenlei/xianshiqi/"),
    ("散热器", "https://www.smzdm.com/fenlei/sanreqi/"),
    ("网络存储", "https://www.smzdm.com/fenlei/wangluocunchu/"),
    ("U盘", "https://www.smzdm.com/fenlei/youpan/"),
    ("移动硬盘", "https://www.smzdm.com/fenlei/yidongyingpan/"),
    ("路由器", "https://www.smzdm.com/fenlei/luyouqi/"),
    ("鼠标", "https://www.smzdm.com/fenlei/shubiao/"),
    ("键盘", "https://www.smzdm.com/fenlei/jianpan/"),
]

COMPUTER_INTEREST_URL = "https://m.smzdm.com/interest/akl18dd/"
DAILY_RANK_URL = "https://post.smzdm.com/"
GARBAGE_SEARCH_QUERY = "垃圾佬"
DEAL_PROFILE_PATH = Path("config/hermes_deal_profile.example.json")

FOOD_KEYWORDS = [
    "禽蛋肉类",
    "鸡蛋",
    "牛肉",
    "猪肉",
    "鸡肉",
    "羊肉",
    "虾",
    "鱼",
    "蔬菜",
    "水果",
    "米面杂粮",
    "大米",
    "面粉",
    "食用油",
    "花生油",
    "玉米油",
    "橄榄油",
    "调味品",
    "酱油",
    "醋",
    "奶类",
    "牛奶",
    "酸奶",
    "咖啡",
    "坚果",
    "炒货",
    "饼干",
    "糕点",
    "肉干",
    "肉脯",
]

ALCOHOL_KEYWORDS = [
    "白酒",
    "啤酒",
    "葡萄酒",
    "红酒",
    "洋酒",
    "威士忌",
    "伏特加",
    "朗姆",
    "黄酒",
    "清酒",
    "香槟",
    "酒水",
]

COMPUTER_KEYWORDS = [
    "CPU",
    "主板",
    "显卡",
    "硬盘",
    "SSD",
    "固态",
    "机械硬盘",
    "内存",
    "机箱",
    "电源",
    "显示器",
    "散热器",
    "NAS",
    "网络存储",
    "存储卡",
    "U盘",
    "移动硬盘",
    "磁盘阵列",
    "路由器",
    "网卡",
    "交换机",
    "鼠标",
    "键盘",
    "摄像头",
    "数位板",
    "电脑支架",
]

AI_KEYWORDS = ["AI", "人工智能", "大模型", "智能体", "Agent", "GPT", "Gemini", "Claude"]
SOFTWARE_KEYWORDS = ["软件", "工具", "办公", "效率", "WPS", "剪映", "WorkBuddy", "Kimi"]

FRESH_SOURCE_NAMES = {"禽蛋肉类", "蔬菜"}
ALCOHOL_SOURCE_NAMES = {name for name, _ in ALCOHOL_CATEGORY_SOURCES}


@dataclass
class Item:
    kind: str
    source: str
    title: str
    url: str
    published_at: str = ""
    category: str = ""
    description: str = ""
    price_text: str = ""
    price_value: float | None = None
    heat: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    editor_note: str = ""
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    rank: int = 0


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_price(text: str) -> tuple[str, float | None]:
    if not text:
        return "", None
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*元", text)
    if not match:
        match = re.search(r"[¥￥]\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return "", None
    value = float(match.group(1))
    return f"{value:g} 元", value


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    now = datetime.now(TZ)
    relative = re.fullmatch(r"(今天|昨天|前天)\s+(\d{1,2}:\d{2})", value)
    if relative:
        day = {"今天": 0, "昨天": 1, "前天": 2}[relative.group(1)]
        parsed_time = datetime.strptime(relative.group(2), "%H:%M").time()
        return datetime.combine(
            (now - timedelta(days=day)).date(),
            parsed_time,
            tzinfo=TZ,
        )
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%m-%d %H:%M",
        "%H:%M",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%m-%d %H:%M":
                parsed = parsed.replace(year=now.year, tzinfo=TZ)
                if parsed > now + timedelta(days=1):
                    parsed = parsed.replace(year=now.year - 1)
            elif fmt == "%H:%M":
                parsed = parsed.replace(year=now.year, month=now.month, day=now.day, tzinfo=TZ)
            elif parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=TZ)
            return parsed.astimezone(TZ)
        except ValueError:
            continue
    return None


def format_time(value: str) -> str:
    parsed = parse_datetime(value)
    if not parsed:
        return value
    return parsed.strftime("%m-%d %H:%M")


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    upper = text.upper()
    return any(keyword.upper() in upper for keyword in keywords)


def load_deal_profile() -> dict:
    try:
        profile = json.loads(DEAL_PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"delivery": {}, "groups": {}, "exclude_keywords": []}
    if not isinstance(profile, dict):
        return {"delivery": {}, "groups": {}, "exclude_keywords": []}
    profile.setdefault("delivery", {})
    profile.setdefault("groups", {})
    profile.setdefault("exclude_keywords", [])
    return profile


class Collector:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_text(self, url: str, retries: int = 3) -> str:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
            except Exception as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"请求失败: {url}: {last_error}")

    def fetch_feed(self, url: str, source: str, kind: str) -> list[Item]:
        raw = self.get_text(url)
        root = ET.fromstring(raw)
        items: list[Item] = []
        for node in root.findall(".//item"):
            title = clean_text(self._child_text(node, "title"))
            link = clean_text(self._child_text(node, "link"))
            description = clean_text(self._child_text(node, "description"))
            pub_date = clean_text(self._child_text(node, "pubDate"))
            category = clean_text(self._child_text(node, "category"))
            comments = clean_text(self._child_text(node, "comments"))
            price_text, price_value = parse_price(f"{title} {description}")
            heat = {}
            if comments.isdigit():
                heat["comments"] = int(comments)
            items.append(
                Item(
                    kind=kind,
                    source=source,
                    title=title,
                    url=link,
                    published_at=pub_date,
                    category=category,
                    description=description,
                    price_text=price_text,
                    price_value=price_value,
                    heat=heat,
                )
            )
        return items

    @staticmethod
    def _child_text(node: ET.Element, name: str) -> str:
        child = node.find(name)
        return child.text or "" if child is not None else ""

    def fetch_category_deals(self, url: str, category: str) -> list[Item]:
        raw = self.get_text(url)
        soup = BeautifulSoup(raw, "lxml")
        items: list[Item] = []
        seen: set[str] = set()
        for anchor in soup.select('a[href*="www.smzdm.com/p/"]'):
            href = anchor.get("href", "")
            if not re.search(r"https://www\.smzdm\.com/p/\d+/?", href):
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            parent = anchor.find_parent(["div", "li", "article"])
            context = clean_text(parent.get_text(" ", strip=True)) if parent else title
            if not title or title in seen:
                continue
            seen.add(title)
            price_text, price_value = parse_price(f"{title} {context}")
            items.append(
                Item(
                    kind="deal",
                    source=category,
                    title=title,
                    url=href,
                    category=category,
                    description=context[:280],
                    price_text=price_text,
                    price_value=price_value,
                )
            )
        return items

    def fetch_daily_ranking(self) -> list[Item]:
        raw = self.get_text(DAILY_RANK_URL)
        soup = BeautifulSoup(raw, "lxml")
        cards = soup.select(".feed-hot-list .feed-hot-card")
        items: list[Item] = []
        for order, card in enumerate(cards, 1):
            try:
                rank = int(card.get("data-position") or order)
            except ValueError:
                rank = order
            anchor = card.select_one(".feed-hot-title a[href]")
            if not anchor:
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            href = anchor.get("href", "").split("#", 1)[0]
            if not title or not href:
                continue
            if href.startswith("/"):
                href = f"https://post.smzdm.com{href}"
            text = clean_text(card.get_text(" ", strip=True))
            items.append(
                Item(
                    kind="article",
                    source="社区日榜",
                    title=title,
                    url=href,
                    description=text[:320],
                    rank=rank,
                    tags=["社区日榜", f"排名:{rank}"],
                )
            )
        return sorted(items, key=lambda item: item.rank)


def fetch_search_rows(
    keyword: str,
    link_selector: str,
    limit: int = 30,
) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 playwright，请先安装 requirements-digest.txt") from exc

    url = (
        "https://search.smzdm.com/?c=home"
        f"&s={quote(keyword)}&order=time&v=b"
    )
    with sync_playwright() as playwright:
        launch_options = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        channel = os.environ.get("PLAYWRIGHT_CHANNEL")
        if not channel and sys.platform == "win32":
            channel = "msedge"
        if channel:
            launch_options["channel"] = channel
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(locale="zh-CN", user_agent=USER_AGENT)
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        raw_items: list[dict] = []
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if attempt == 0:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                else:
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(7000)
                raw_items = page.evaluate(
                    """
                    ({ selector, limit }) => {
                      const rows = [];
                      const links = Array.from(document.querySelectorAll(selector)).slice(0, limit);
                      for (const link of links) {
                        if (link.closest('.feed-side, .global-nav, footer')) continue;
                        const title = (link.textContent || '').trim();
                        if (!title || title.length < 5) continue;
                        let container = link;
                        for (let depth = 0; depth < 6 && container.parentElement; depth += 1) {
                          container = container.parentElement;
                          const candidate = (container.innerText || '').trim();
                          if (
                            candidate.includes(title) &&
                            (
                              /(?:(?:今天|昨天|前天)\s+)?(?:\\d{1,2}-\\d{1,2}\s+)?\\d{1,2}:\\d{2}/.test(candidate) ||
                              candidate.length > 180
                            )
                          ) {
                            break;
                          }
                        }
                        const text = (container.innerText || '').trim();
                        const timeMatch = text.match(
                          /(?:(?:今天|昨天|前天)\s+)?(?:\\d{1,2}-\\d{1,2}\\s+)?\\d{1,2}:\\d{2}/
                        );
                        const numeric = Array.from(
                          container.querySelectorAll('a, span')
                        )
                          .map((node) => (node.textContent || '').trim())
                          .filter((value) => /^\\d+$/.test(value))
                          .map(Number);
                        rows.push({
                          title,
                          href: link.href,
                          time: timeMatch ? timeMatch[0] : '',
                          text: text.slice(0, 500),
                          numeric,
                        });
                      }
                      return rows;
                    }
                    """,
                    {"selector": link_selector, "limit": limit},
                )
                if raw_items:
                    break
            except Exception as exc:
                last_error = exc
                page.wait_for_timeout(4000)
        if not raw_items and last_error:
            print(f"  跳过搜索页 {keyword}: {last_error}")
        browser.close()
    return raw_items


def prefer_longer_titles(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        href = (row.get("href") or "").split("#", 1)[0]
        if not href:
            continue
        current = best.get(href)
        current_title = current.get("title", "") if current else ""
        if not current or len(row.get("title", "")) > len(current_title):
            best[href] = row
    return list(best.values())


def fetch_search_items(keyword: str, limit: int = 10) -> list[Item]:
    raw_items = prefer_longer_titles(fetch_search_rows(
        keyword,
        'a[href*="post.smzdm.com/p/"], a[href*="post.smzdm.com/talk/p/"]',
        limit=limit * 4,
    ))
    items: list[Item] = []
    seen: set[str] = set()
    for row in raw_items:
        href = row.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        numeric = row.get("numeric") or []
        heat = {}
        if len(numeric) >= 2:
            heat["score"] = numeric[0]
            heat["comments"] = numeric[-1]
        items.append(
            Item(
                kind="article",
                source=f"搜索:{keyword}",
                title=clean_text(row.get("title", "")),
                url=href,
                published_at=row.get("time", ""),
                description=clean_text(row.get("text", ""))[:320],
                heat=heat,
                tags=[keyword],
            )
        )
        if len(items) >= limit:
            break
    return items


def fetch_search_deals(keyword: str, limit: int = 12) -> list[Item]:
    raw_items = prefer_longer_titles(fetch_search_rows(
        keyword,
        'a[href*="www.smzdm.com/p/"]',
        limit=limit * 4,
    ))
    items: list[Item] = []
    seen: set[str] = set()
    for row in raw_items:
        href = row.get("href", "").split("#", 1)[0]
        title = clean_text(row.get("title", ""))
        text = clean_text(row.get("text", ""))
        if not href or not title or not text or href in seen:
            continue
        price_text, price_value = parse_price(text)
        if not price_text:
            continue
        seen.add(href)
        items.append(
            Item(
                kind="deal",
                source=f"搜索:{keyword}",
                title=title,
                url=href,
                published_at=row.get("time", ""),
                category=keyword,
                description=text[:320],
                price_text=price_text,
                price_value=price_value,
            )
        )
        if len(items) >= limit:
            break
    return items


def dedupe(items: Iterable[Item]) -> list[Item]:
    result: list[Item] = []
    seen: set[str] = set()
    for item in items:
        key = item.url.split("#", 1)[0]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def freshness_score(published_at: str) -> float:
    parsed = parse_datetime(published_at)
    if not parsed:
        return 50.0
    age_hours = max(0.0, (datetime.now(TZ) - parsed).total_seconds() / 3600)
    if age_hours <= 2:
        return 100.0
    if age_hours <= 6:
        return 90.0
    if age_hours <= 12:
        return 80.0
    if age_hours <= 24:
        return 70.0
    if age_hours <= 48:
        return 50.0
    return 30.0


def heat_score(heat: dict[str, int]) -> float:
    if not heat:
        return 40.0
    value = max(heat.values())
    if value >= 100:
        return 100.0
    if value >= 30:
        return 80.0
    if value >= 10:
        return 65.0
    if value > 0:
        return 50.0
    return 30.0


def score_deal(item: Item) -> Item:
    text = f"{item.title} {item.description}"
    price_advantage = 55.0
    history_low = 0.0
    source_trust = 50.0
    freshness = freshness_score(item.published_at)
    heat = heat_score(item.heat)
    preference = 70.0
    reasons: list[str] = []

    drop_match = re.search(r"比上次发布低\s*(\d+(?:\.\d+)?)\s*%", text)
    if contains_any(text, ["新低", "历史低价", "最低价"]):
        price_advantage = 98.0
        history_low = 100.0
        reasons.append("出现历史低价或新低信号")
    elif drop_match:
        percent = float(drop_match.group(1))
        price_advantage = clamp(65 + percent * 2)
        history_low = 70.0
        reasons.append(f"比上次发布低 {percent:g}%")
    elif item.price_text:
        price_advantage = 62.0
    else:
        price_advantage = 30.0
        reasons.append("价格信息不完整")

    if contains_any(text, ["需用券", "券后", "领券"]):
        price_advantage -= 8
        reasons.append("需要领券确认最终价")
    if contains_any(text, ["凑单", "需买", "买2件", "买两件"]):
        price_advantage -= 10
        reasons.append("需要凑单或多件购买")
    if contains_any(text, ["88VIP", "会员", "PLUS"]):
        price_advantage -= 8
        reasons.append("包含会员权益或会员价")
    if contains_any(text, ["返积分", "返卡", "返现"]):
        price_advantage -= 5
        reasons.append("低价包含返现或积分条件")

    if contains_any(text, ["京东自营", "天猫超市", "天猫精选", "官方旗舰店", "百亿补贴"]):
        source_trust = 95.0
        reasons.append("来源可信度较高")
    elif contains_any(text, ["京东", "天猫", "拼多多", "苏宁"]):
        source_trust = 75.0
    else:
        source_trust = 45.0
        reasons.append("店铺来源不明确")

    if contains_any(text, ["方便面", "自热", "速食"]):
        preference -= 25
        reasons.append("方便食品降权")
    if contains_any(text, ["二手", "翻新", "工包", "拆机"]):
        preference -= 30
        reasons.append("非全新或非正规渠道降权")
    if item.category in FRESH_SOURCE_NAMES or item.source in FRESH_SOURCE_NAMES:
        preference += 15
        reasons.append("生鲜类优先")
    if item.category in ALCOHOL_SOURCE_NAMES or item.source in ALCOHOL_SOURCE_NAMES:
        preference += 15
        reasons.append("酒水类优先")
    if item.category == "咖啡" or item.source == "咖啡":
        preference -= 10
        reasons.append("咖啡类降权")
    if not item.published_at:
        reasons.append("缺少发布时间，时效按中性处理")
    if not item.heat:
        reasons.append("缺少互动数据，热度按中性处理")
    if not history_low:
        reasons.append("首轮暂无完整价格历史")

    item.score_breakdown = {
        "价格优势": clamp(price_advantage),
        "历史低价": history_low,
        "来源可信": source_trust,
        "更新时效": freshness,
        "互动热度": heat,
        "编辑偏好": clamp(preference),
    }
    item.score = round(
        item.score_breakdown["价格优势"] * 0.35
        + item.score_breakdown["历史低价"] * 0.20
        + item.score_breakdown["来源可信"] * 0.15
        + item.score_breakdown["更新时效"] * 0.15
        + item.score_breakdown["互动热度"] * 0.10
        + item.score_breakdown["编辑偏好"] * 0.05,
        1,
    )
    item.reasons = reasons[:4]
    return item


def score_article(item: Item) -> Item:
    text = f"{item.title} {item.description}"
    freshness = freshness_score(item.published_at)
    heat = heat_score(item.heat)
    relevance = 55.0
    depth = 45.0
    reasons: list[str] = []

    depth_terms = [
        "实测",
        "评测",
        "对比",
        "攻略",
        "教程",
        "避坑",
        "复盘",
        "指南",
        "为什么",
        "怎么选",
        "经验",
        "拆解",
        "数据",
        "完整",
        "深度",
    ]
    if contains_any(item.title, depth_terms):
        depth += 30
        relevance += 12
        reasons.append("标题呈现实测、对比或攻略属性")
    if item.category:
        relevance += 8
    if item.source.startswith("搜索:"):
        relevance += 10
        reasons.append("来自主题搜索结果")
    if contains_any(text, ["新闻", "快讯", "官宣", "发布会"]):
        depth -= 10
    if not item.heat:
        reasons.append("暂无互动数据，热度按中性处理")
    if not item.published_at:
        reasons.append("缺少发布时间，时效按中性处理")

    item.score_breakdown = {
        "时效性": freshness,
        "互动热度": heat,
        "主题相关": clamp(relevance),
        "内容深度": clamp(depth),
    }
    base_score = (
        item.score_breakdown["时效性"] * 0.25
        + item.score_breakdown["互动热度"] * 0.30
        + item.score_breakdown["主题相关"] * 0.25
        + item.score_breakdown["内容深度"] * 0.20
    )
    if item.rank:
        rank_bonus = max(0.0, 35.0 - (item.rank - 1) * 1.5)
        base_score += rank_bonus
        item.score_breakdown["日榜排名奖励"] = round(rank_bonus, 1)
        reasons.append(f"社区日榜第 {item.rank} 名")
    item.score = round(clamp(base_score), 1)
    item.reasons = reasons[:4]
    return item


def deal_group(item: Item, domain: str) -> str:
    text = f"{item.title} {item.description}".upper()
    if domain == "food":
        groups = [
            ("咖啡", ["咖啡"]),
            ("乳制品", ["牛奶", "酸奶", "奶类", "鲜奶", "奶酪"]),
            ("蔬菜", ["蔬菜", "青菜", "生菜", "菠菜", "西兰花", "番茄", "土豆"]),
            ("禽蛋肉类", ["鸡蛋", "鸭蛋", "牛肉", "猪肉", "鸡肉", "羊肉", "虾", "鱼", "水产"]),
            ("米面杂粮", ["大米", "米面", "杂粮", "面粉", "面条"]),
            ("食用油", ["食用油", "花生油", "玉米油", "橄榄油", "葵花籽油"]),
            ("调味品", ["酱油", "醋", "调味", "蚝油", "料酒"]),
            ("坚果炒货", ["坚果", "炒货", "腰果", "核桃", "开心果"]),
            ("饼干糕点", ["饼干", "糕点", "面包", "蛋糕"]),
            ("肉干肉脯", ["肉干", "肉脯", "牛肉干"]),
        ]
    elif domain == "alcohol":
        groups = [
            ("白酒", ["白酒", "浓香", "酱香"]),
            ("啤酒", ["啤酒", "精酿"]),
            ("葡萄酒", ["葡萄酒", "红酒", "干红", "香槟"]),
            ("洋酒", ["洋酒", "威士忌", "伏特加", "朗姆", "白兰地"]),
            ("黄酒/养生酒", ["黄酒", "养生酒", "花雕"]),
            ("其他酒类", ["清酒", "梅酒", "果酒", "鸡尾酒"]),
        ]
    else:
        groups = [
            ("CPU", ["CPU", "处理器"]),
            ("主板", ["主板"]),
            ("显卡", ["显卡", "RTX", "RX "]),
            ("硬盘", ["硬盘", "SSD", "固态", "M.2", "SATA"]),
            ("内存", ["内存", "DDR"]),
            ("机箱", ["机箱"]),
            ("电源", ["电源", "电源供应"]),
            ("显示器", ["显示器", "显示屏"]),
            ("散热器", ["散热器", "水冷"]),
            ("网络存储", ["NAS", "网络存储"]),
            ("U盘/存储卡", ["U盘", "存储卡", "TF卡"]),
            ("移动硬盘", ["移动硬盘"]),
            ("路由器", ["路由器"]),
            ("键盘", ["键盘"]),
            ("鼠标", ["鼠标"]),
        ]
    for label, keywords in groups:
        if any(keyword.upper() in text for keyword in keywords):
            return label
    if item.category and item.category not in {"食品生鲜", "电脑配件", "电脑配件精选"}:
        return item.category
    return "其他"


def top_items(
    items: Iterable[Item],
    count: int,
    keywords: Iterable[str] = (),
    scorer=None,
    max_per_group: int | None = None,
    group_key=None,
) -> list[Item]:
    candidates = dedupe(items)
    if keywords:
        candidates = [
            item
            for item in candidates
            if contains_any(f"{item.title} {item.category}", keywords)
        ]
    if scorer:
        candidates = [scorer(item) for item in candidates]
        candidates.sort(key=lambda item: item.score, reverse=True)
    if not max_per_group or not group_key:
        return candidates[:count]
    result: list[Item] = []
    group_counts: dict[str, int] = {}
    for item in candidates:
        group = group_key(item)
        if group_counts.get(group, 0) >= max_per_group:
            continue
        group_counts[group] = group_counts.get(group, 0) + 1
        result.append(item)
        if len(result) >= count:
            break
    return result


def load_garbage_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"urls": {}}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"urls": {}}
    if not isinstance(state, dict) or not isinstance(state.get("urls"), dict):
        return {"urls": {}}
    return state


def save_garbage_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def item_age_hours(item: Item, now: datetime) -> float | None:
    parsed = parse_datetime(item.published_at)
    if not parsed:
        return None
    return max(0.0, (now - parsed).total_seconds() / 3600)


def select_garbage_items(
    items: Iterable[Item],
    state_file: Path,
    now: datetime,
    count: int = 3,
) -> list[Item]:
    state = load_garbage_state(state_file)
    selected_by_url = state["urls"]
    today = now.date().isoformat()
    cutoff_date = (now.date() - timedelta(days=14)).isoformat()

    cleaned: dict[str, dict] = {}
    for url, value in selected_by_url.items():
        if not isinstance(value, dict):
            continue
        last_date = str(value.get("last_selected_date", ""))
        if last_date >= cutoff_date:
            cleaned[url] = value
    selected_by_url = cleaned

    unseen: list[Item] = []
    for item in dedupe(items):
        url = item.url.split("#", 1)[0]
        record = selected_by_url.get(url, {})
        last_date = str(record.get("last_selected_date", ""))
        if last_date and last_date != today and last_date >= cutoff_date:
            continue
        unseen.append(item)

    def pick(window_hours: int | None, remaining: int) -> list[Item]:
        candidates = []
        used_urls = {item.url.split("#", 1)[0] for item in result}
        for item in unseen:
            if item.url.split("#", 1)[0] in used_urls:
                continue
            age = item_age_hours(item, now)
            if window_hours is not None and (age is None or age > window_hours):
                continue
            candidates.append(item)
        picked = top_items(
            candidates,
            count=remaining,
            scorer=score_article,
        )
        if window_hours is None:
            for item in picked:
                age = item_age_hours(item, now)
                if age is None:
                    item.reasons.append("日期未知，按往期候选处理")
                elif age > 168:
                    item.reasons.append("超过7天，按往期候选处理")
        return picked

    result: list[Item] = []
    for window in (72, 168, None):
        if len(result) >= count:
            break
        result.extend(pick(window, count - len(result)))

    for item in result:
        url = item.url.split("#", 1)[0]
        record = selected_by_url.get(url, {})
        record["last_selected_date"] = today
        record.setdefault("first_seen_date", today)
        selected_by_url[url] = record

    state["urls"] = selected_by_url
    state["updated_at"] = now.isoformat()
    save_garbage_state(state_file, state)
    return result


def editor_note(item: Item) -> str:
    if item.kind == "deal":
        if item.price_text:
            return f"关注点：现价 {item.price_text}，需要核对券后价、会员价和是否需要凑单。"
        return "关注点：价格没有在标题中明确，建议进入详情确认券后价。"
    if item.category:
        return f"关注点：来自{ item.category }，适合快速判断是否值得深入阅读。"
    return "关注点：优先看发布时间、评论量和是否包含可执行结论。"


def render_markdown(
    generated_at: datetime,
    ai_items: list[Item],
    software_items: list[Item],
    garbage_items: list[Item],
    food_deals: list[Item],
    alcohol_deals: list[Item],
    computer_interest_items: list[Item],
    computer_deals: list[Item],
    deep_reads: list[Item],
) -> str:
    lines = [
        "# 什么值得买每日精选本地样例",
        "",
        f"- 生成时间：{generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "- 计划推送时间：每天 11:00",
        "- 轮询频率：每小时静默采集",
        "- 说明：这份样例只用于确认编辑口味和字段结构，尚未接入 Hermes。",
        "",
    ]

    sections = [
        ("AI 应用探索", ai_items),
        ("软件应用", software_items),
        ("垃圾佬每日精选", garbage_items),
        ("食品生鲜好价", food_deals),
        ("酒水好价", alcohol_deals),
        ("电脑配件好价", computer_deals),
        ("电脑配件精选", computer_interest_items),
        ("社区日榜", deep_reads),
    ]
    for title, items in sections:
        lines.extend([f"## {title}", ""])
        if not items:
            lines.extend(["本轮没有筛选出合适条目。", ""])
            continue
        for index, item in enumerate(items, 1):
            meta = [item.source]
            if item.published_at:
                meta.append(format_time(item.published_at))
            if item.category:
                meta.append(item.category)
            if item.price_text:
                meta.append(item.price_text)
            if item.heat:
                heat_text = " / ".join(f"{key}:{value}" for key, value in item.heat.items())
                meta.append(heat_text)
            lines.append(f"{index}. [{item.title}]({item.url})")
            lines.append(f"   - 来源：{' | '.join(meta)}")
            if item.description:
                lines.append(f"   - 摘要：{item.description[:180]}")
            if item.score:
                lines.append(f"   - 推荐分：{item.score:.1f}")
            if item.score_breakdown:
                breakdown = " / ".join(
                    f"{name}:{value:g}"
                    for name, value in item.score_breakdown.items()
                )
                lines.append(f"   - 评分构成：{breakdown}")
            if item.reasons:
                lines.append(f"   - 推荐理由：{'；'.join(item.reasons)}")
            lines.append(f"   - {editor_note(item)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_rank_markdown(generated_at: datetime, items: list[Item]) -> str:
    lines = [
        "# 社区日榜完整榜单",
        "",
        f"- 抓取时间：{generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "- 来源：https://post.smzdm.com/ 首页社区榜日榜",
        f"- 条目数：{len(items)}",
        "",
    ]
    for item in items:
        lines.append(f"{item.rank}. [{item.title}]({item.url})")
        if item.description:
            lines.append(f"   - {item.description[:220]}")
    return "\n".join(lines).rstrip() + "\n"


def rss_date(value: str, fallback: datetime) -> str:
    parsed = parse_datetime(value)
    return format_datetime(parsed or fallback)


def render_rss(
    generated_at: datetime,
    sections: dict[str, list[Item]],
    public_url: str,
) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "什么值得买每日精选"
    ET.SubElement(channel, "link").text = public_url.rstrip("/") + "/"
    ET.SubElement(channel, "description").text = (
        "什么值得买每日精选，包含 AI、软件、垃圾佬精选、食品生鲜、"
        "酒水、电脑配件和社区日榜。"
    )
    ET.SubElement(channel, "language").text = "zh-cn"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(generated_at)
    ET.SubElement(channel, "generator").text = "smzdm-wenzhang-rss"

    seen: set[str] = set()
    for section, items in sections.items():
        for item in items:
            key = item.url.split("#", 1)[0]
            if not key or key in seen:
                continue
            seen.add(key)
            entry = ET.SubElement(channel, "item")
            ET.SubElement(entry, "title").text = f"[{section}] {item.title}"
            ET.SubElement(entry, "link").text = item.url
            ET.SubElement(entry, "guid", isPermaLink="false").text = (
                f"smzdm-daily:{section}:{key}"
            )
            ET.SubElement(entry, "category").text = section
            ET.SubElement(entry, "pubDate").text = rss_date(
                item.published_at,
                generated_at,
            )
            score_text = f"推荐分 {item.score:.1f}" if item.score else "未评分"
            reason_text = "；".join(item.reasons)
            ET.SubElement(entry, "description").text = (
                f"{item.source} | {score_text}"
                + (f" | {reason_text}" if reason_text else "")
                + (f"\n{item.description}" if item.description else "")
            )
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True).decode("utf-8")


def build_digest(
    output: Path,
    json_output: Path,
    skip_browser: bool,
    public_url: str,
    state_file: Path,
) -> None:
    collector = Collector()
    generated_at = datetime.now(TZ)
    profile = load_deal_profile()

    print("抓取优惠精选 RSS...")
    deal_feed = collector.fetch_feed(DEAL_FEED, "优惠精选 RSS", "deal")
    print(f"  获得 {len(deal_feed)} 条")

    print("抓取社区文章 RSS...")
    article_feed = collector.fetch_feed(ARTICLE_FEED, "社区文章 RSS", "article")
    print(f"  获得 {len(article_feed)} 条")

    print("抓取社区日榜...")
    daily_rank = collector.fetch_daily_ranking()
    print(f"  获得 {len(daily_rank)} 条")

    print("抓取食品生鲜子类...")
    food_category: list[Item] = []

    print("抓取酒水子类...")
    alcohol_category: list[Item] = []

    print("抓取电脑配件子类...")
    computer_category: list[Item] = []

    print("抓取电脑配件精选页...")
    try:
        computer_interest = collector.fetch_category_deals(
            COMPUTER_INTEREST_URL,
            "电脑配件精选",
        )
    except Exception as exc:
        computer_interest = []
        print(f"  跳过（{exc}）")
    print(f"  获得 {len(computer_interest)} 条候选")

    ai_items: list[Item] = []
    software_items: list[Item] = []
    computer_search_deals: list[Item] = []
    food_search_deals: list[Item] = []
    alcohol_search_deals: list[Item] = []
    garbage_search_items: list[Item] = []
    watch_deals: list[Item] = []
    if skip_browser:
        print("跳过浏览器搜索页抓取")
    else:
        print("抓取 AI 应用探索搜索页...")
        ai_items = fetch_search_items("AI应用探索", limit=8)
        print(f"  获得 {len(ai_items)} 条")
        print("抓取软件应用搜索页...")
        software_items = fetch_search_items("软件应用", limit=8)
        print(f"  获得 {len(software_items)} 条")
        print("抓取电脑配件搜索页...")
        computer_search_deals = fetch_search_deals("电脑配件", limit=20)
        print(f"  获得 {len(computer_search_deals)} 条")
        for group_name, group in profile.get("groups", {}).items():
            if not group.get("enabled", False):
                continue
            excludes = profile.get("exclude_keywords", []) + group.get("exclude", [])
            includes = group.get("include", [])
            for query in group.get("search_queries", []):
                print(f"抓取好价监控搜索页: {group.get('label', group_name)} / {query}...")
                found = fetch_search_deals(query, limit=8)
                accepted = 0
                for item in found:
                    text = f"{item.title} {item.description}"
                    if contains_any(text, excludes):
                        continue
                    if includes and not contains_any(text, includes):
                        continue
                    item.category = "好价候选池"
                    item.tags.append(group_name)
                    watch_deals.append(item)
                    accepted += 1
                print(f"  获得 {accepted} 条")

        three_c = profile.get("groups", {}).get("three_c", {})
        if three_c.get("enabled", False):
            excludes = profile.get("exclude_keywords", []) + three_c.get("exclude", [])
            includes = three_c.get("include", [])
            for item in computer_search_deals:
                text = f"{item.title} {item.description}"
                if contains_any(text, excludes):
                    continue
                if includes and not contains_any(text, includes):
                    continue
                item.category = "好价候选池"
                item.tags.append("three_c")
                watch_deals.append(item)
        print(f"抓取垃圾佬搜索页: {GARBAGE_SEARCH_QUERY}...")
        garbage_search_items = fetch_search_items(GARBAGE_SEARCH_QUERY, limit=20)
        print(f"  获得 {len(garbage_search_items)} 条")
        for query in ["禽蛋肉类", "蔬菜"]:
            print(f"抓取食品搜索页: {query}...")
            found = fetch_search_deals(query, limit=12)
            food_search_deals.extend(found)
            print(f"  获得 {len(found)} 条")
        for query in ["白酒", "啤酒", "葡萄酒", "洋酒"]:
            print(f"抓取酒水搜索页: {query}...")
            found = fetch_search_deals(query, limit=12)
            alcohol_search_deals.extend(found)
            print(f"  获得 {len(found)} 条")

    food_deals = top_items(
        [*deal_feed, *food_search_deals, *food_category],
        count=3,
        keywords=FOOD_KEYWORDS,
        scorer=score_deal,
        max_per_group=1,
        group_key=lambda item: deal_group(item, "food"),
    )
    alcohol_deals = top_items(
        [*deal_feed, *alcohol_search_deals, *alcohol_category],
        count=3,
        keywords=ALCOHOL_KEYWORDS,
        scorer=score_deal,
        max_per_group=1,
        group_key=lambda item: deal_group(item, "alcohol"),
    )
    computer_deals = top_items(
        [
            *deal_feed,
            *computer_search_deals,
            *computer_interest,
            *computer_category,
        ],
        count=3,
        keywords=COMPUTER_KEYWORDS,
        scorer=score_deal,
        max_per_group=1,
        group_key=lambda item: deal_group(item, "computer"),
    )
    computer_interest_items = top_items(
        computer_interest,
        count=2,
        scorer=score_deal,
        max_per_group=1,
        group_key=lambda item: deal_group(item, "computer"),
    )
    deep_reads = [score_article(item) for item in daily_rank]
    rank_map = {
        item.url.split("#", 1)[0]: item.rank
        for item in daily_rank
    }
    for item in garbage_search_items:
        item.rank = rank_map.get(item.url.split("#", 1)[0], item.rank)
    garbage_pool = dedupe(garbage_search_items)
    if not garbage_pool:
        garbage_pool = [
            item
            for item in daily_rank
            if contains_any(
                f"{item.title} {item.description}",
                ["垃圾佬", "捡垃圾", "洋垃圾", "E5", "X99", "矿渣"],
            )
        ]
    garbage_items = select_garbage_items(
        garbage_pool,
        state_file,
        generated_at,
        count=3,
    )

    ai_items = top_items(ai_items, count=3, keywords=AI_KEYWORDS, scorer=score_article) or ai_items[:3]
    software_items = top_items(
        software_items,
        count=2,
        keywords=SOFTWARE_KEYWORDS,
        scorer=score_article,
    ) or software_items[:2]

    markdown = render_markdown(
        generated_at,
        ai_items,
        software_items,
        garbage_items,
        food_deals,
        alcohol_deals,
        computer_interest_items,
        computer_deals,
        deep_reads,
    )
    payload = {
        "generated_at": generated_at.isoformat(),
        "scheduled_push_time": "11:00 Asia/Shanghai",
        "polling": "hourly",
        "rss_url": public_url.rstrip("/") + "/daily_digest.xml",
        "sections": {
            "ai": [asdict(item) for item in ai_items],
            "software": [asdict(item) for item in software_items],
            "garbage": [asdict(item) for item in garbage_items],
            "food_deals": [asdict(item) for item in food_deals],
            "alcohol_deals": [asdict(item) for item in alcohol_deals],
            "computer_deals": [asdict(item) for item in computer_deals],
            "computer_interest": [
                asdict(item) for item in computer_interest_items
            ],
            "watch_deals": [asdict(item) for item in dedupe(watch_deals)],
            "community_daily_rank": [asdict(item) for item in deep_reads],
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rank_output = output.parent / "community_daily_rank.md"
    rank_json_output = output.parent / "community_daily_rank.json"
    rank_output.write_text(
        render_rank_markdown(generated_at, daily_rank),
        encoding="utf-8",
    )
    rank_json_output.write_text(
        json.dumps(
            [asdict(item) for item in daily_rank],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    rss_output = output.parent / "daily_digest.xml"
    rss_output.write_text(
        render_rss(
            generated_at,
            {
                "AI 应用探索": ai_items,
                "软件应用": software_items,
                "垃圾佬每日精选": garbage_items,
                "食品生鲜好价": food_deals,
                "酒水好价": alcohol_deals,
                "电脑配件好价": computer_deals,
                "电脑配件精选": computer_interest_items,
                "好价候选池": dedupe(watch_deals),
                "社区日榜": deep_reads,
            },
            public_url,
        ),
        encoding="utf-8",
    )
    print(f"Markdown: {output.resolve()}")
    print(f"JSON: {json_output.resolve()}")
    print(f"RSS: {rss_output.resolve()}")
    print(f"日榜 Markdown: {rank_output.resolve()}")
    print(f"日榜 JSON: {rank_json_output.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成什么值得买每日精选本地样例")
    parser.add_argument(
        "--output",
        default="outputs/daily_digest_sample.md",
        help="Markdown 输出路径",
    )
    parser.add_argument(
        "--json-output",
        default="outputs/daily_digest_sample.json",
        help="JSON 输出路径",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="跳过 AI/软件搜索页浏览器抓取",
    )
    parser.add_argument(
        "--public-url",
        default="https://doane2002cn.github.io/smzdm-wenzhang-rss",
        help="GitHub Pages 公共地址",
    )
    parser.add_argument(
        "--state-file",
        default="state/garbage_selection_state.json",
        help="垃圾佬 URL 跨天去重状态文件",
    )
    args = parser.parse_args()
    build_digest(
        Path(args.output),
        Path(args.json_output),
        skip_browser=args.skip_browser,
        public_url=args.public_url,
        state_file=Path(args.state_file),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
