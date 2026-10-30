#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smzdm_deal_alert.py — 什么值得买每日精选好价 → 飞书 interactive 卡片

默认每天 11:10 运行一次，只处理用户 profile 中启用的好价分组。
数据源: https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.xml

设计原则（用户 2026-10-15 指定）:
  · 好价判定**先走确定性规则**（价格/新低天数/降幅/原价/平台/优惠条件），AI 只写
    "推荐理由 + 风险提示"，绝不参与是否推送的判定。
  · AI 全失败 → 不发付费模型、照发确定性卡片，末尾注"AI 优惠解读暂不可用"；
    价格/链接/优惠条件一律不因 AI 失败而省略。
  · 每日最多 1 张精选卡片；最多 2 条商品；每分组最多 1 条；没有达标好价保持沉默。

契约: 成功或无好价 → stdout 为空(静默)；出错 → 打印一行提示(会被投递)，退出码 0
用法: python3 smzdm_deal_alert.py [--dry-run] [--test-color green|orange|yellow]
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from smzdm_links import build_smzdm_button

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

FEED = "https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.xml"
ENV_FILE = "/opt/data/.env"
CARD_API = "/opt/data/workspace/scripts/feishu_card_api.py"
CARD_FILE = os.environ.get("SMZDM_DEAL_CARD_FILE", "/tmp/smzdm_deal_card.json")
CHAT = "oc_b8559c55f250b54d396a8d8105bb1355"
STATE_FILE = "/opt/data/scripts/state/smzdm_deal_alert.json"
CST = timezone(timedelta(hours=8))

DEAL_CATS = ("食品生鲜好价", "酒水好价", "电脑配件好价", "电脑配件精选", "好价候选池")
PROFILE_PATH = "/opt/data/scripts/state/smzdm_deal_profile.json"
QUIET_FROM_H, QUIET_TO_H = 23, 7          # 23:00–07:00 不推送
MAX_CARDS_PER_DAY = 1
MAX_CARDS_PER_RUN = 1
MAX_PER_CARD = 2                          # 每日精选最多 2 条，默认每分组 1 条
MAX_PER_GROUP = 1
MAX_AGE_H = 36                            # 只推最近 36 小时的爆料
DROP_THRESHOLD = 15.0                     # 降幅(%)达标线
SCORE_LOW = 75.0                          # 推荐分低于此 → 需二次确认(黄)
ALERTED_TTL_H = 336                       # 同一商品 14 天内不重复推

# 用户指定的免费模型链；禁止付费兜底
LLM_MODELS = (
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
)
LLM_RETRY_FIRST_AFTER_COOLDOWN = True     # 全挂后冷却再试一次 openrouter/free
COOLDOWN_S = 25
LLM_TIMEOUT = 25
AI_DEADLINE_S = 150
LLM_KEYS = ("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3")
LLM_URL = "https://openrouter.ai/api/v1/chat/completions"
SYSTEM = ("你是消费优惠编辑。只输出 JSON，不要解释、不要代码块围栏，"
          "严禁编造未提供的信息。")

RE_PRICE = re.compile(r"(\d+(?:\.\d+)?)\s*元")
RE_NEWLOW = re.compile(r"(\d+)\s*天新低")
RE_DROP = re.compile(r"(?:比上次发布低|本次降幅|降幅|降价)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%")
RE_ORIG = re.compile(r"(?:活动售价|降价前售价为|原价|日常价|售价)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元")
RE_PLATFORM = re.compile(r"(京东自营|京东|天猫超市|天猫精选|天猫|拼多多|淘宝|苏宁|唯品会|抖音)")
RE_SCORE = re.compile(r"推荐分\s*(\d+(?:\.\d+)?)")
RE_SPEC = re.compile(r"(\d+(?:\.\d+)?)\s*(GB|TB|MB|G|ml|L|kg|g|斤|英寸|寸|cm|mm|Hz|W|Wh|mAh|%vol|米)")
RE_META_SIGNAL = re.compile(r"^[^\n]*推荐分[^\n]*$", re.M)
# 需二次确认的复杂优惠条件（"下单1件"这种简单情形不算）
RE_COMPLEX = re.compile(r"(凑单|需会员|会员价|需领券|需叠加|限量|限时|前\d+名|抢购|任选|"
                        r"满\d+减|返\d*积分|下单[2-9]件|下单\d{2,}件|晒单|预约|定金)")


# ── 基础设施 ────────────────────────────────────────────────────────────────
def load_env():
    try:
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                os.environ.setdefault(k.strip(), v)
    except Exception as e:                                     # noqa: BLE001
        print(f"[warn] 读取 .env 失败: {e}", file=sys.stderr)


def load_profile():
    """读取 Hermes 本地真实 profile；公开示例不参与运行时筛选。"""
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            profile = json.load(f)
    except Exception as e:                                     # noqa: BLE001
        print(f"[warn] 读取本地 profile 失败: {e}", file=sys.stderr)
        return {"delivery": {}, "groups": {}, "exclude_keywords": []}
    if not isinstance(profile, dict):
        return {"delivery": {}, "groups": {}, "exclude_keywords": []}
    profile.setdefault("delivery", {})
    profile.setdefault("groups", {})
    profile.setdefault("exclude_keywords", [])
    return profile


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:                                          # noqa: BLE001
        s = {}
    s.setdefault("min_price", {})
    s.setdefault("alerted", {})
    s.setdefault("sent", {})
    return s


def save_state(s):
    today = datetime.now(CST).strftime("%Y-%m-%d")
    cut = time.time() - ALERTED_TTL_H * 3600
    s["alerted"] = {k: v for k, v in s["alerted"].items() if v >= cut}
    s["sent"] = {d: n for d, n in s["sent"].items() if d >= today[:8] + "01"} \
        if len(s["sent"]) > 60 else s["sent"]
    s["updated"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def clean_title(t):
    t = (t or "").strip()
    for _ in range(3):
        m = re.match(r"^\[[^\]]{1,12}\]\s*", t)
        if not m:
            break
        t = t[m.end():].strip()
    return t


# ── RSS 解析 ────────────────────────────────────────────────────────────────
def parse_items(raw):
    root = ET.fromstring(raw)
    chan = root.find("channel") if root.find("channel") is not None else root
    out = []
    for it in chan.findall("item"):
        cat = (it.findtext("category") or "").strip()
        if cat not in DEAL_CATS:
            continue
        title = clean_title(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or "").strip()
        desc = (it.findtext("description") or "").replace("\r", "")
        pub = it.findtext("pubDate") or ""
        if not title or not link:
            continue
        try:
            pub_dt = parsedate_to_datetime(pub.strip()).astimezone(CST)
        except Exception:                                      # noqa: BLE001
            pub_dt = None
        body = re.sub(r"<[^>]+>", " ", desc)
        body = re.sub(r"\s+", " ", body).strip()
        meta = " ".join(RE_META_SIGNAL.findall(desc)) or ""
        out.append({"cat": cat, "title": title, "link": link, "guid": guid,
                    "desc": desc, "body": body, "meta": meta, "pub": pub_dt,
                    "key": guid or link})
    return out


def profile_match(it, profile):
    """返回匹配的 profile 分组；未启用或命中排除词返回 None。"""
    text = f"{it['title']} {it['body']}".upper()
    global_excludes = profile.get("exclude_keywords", [])
    if any(str(word).upper() in text for word in global_excludes if word):
        return None
    for group_name, group in profile.get("groups", {}).items():
        if not group.get("enabled", False):
            continue
        group_excludes = group.get("exclude", [])
        if any(str(word).upper() in text for word in group_excludes if word):
            continue
        includes = group.get("include", [])
        if includes and not any(str(word).upper() in text for word in includes if word):
            continue
        return group_name, group.get("label", group_name)
    return None


def parse_deal(it):
    """确定性解析：价格 / 新低 / 降幅 / 原价 / 平台 / 条件 / 规格 / 推荐分。"""
    body, meta = it["body"], it["meta"]
    text = f"{it['title']} {body}"
    price = None
    m = RE_PRICE.search(it["title"]) or RE_PRICE.search(body)
    if m:
        price = float(m.group(1))
    newlow_days = None
    m = RE_NEWLOW.search(text)
    if m:
        newlow_days = int(m.group(1))
    drops = [float(x) for x in RE_DROP.findall(text)]
    drop = max(drops) if drops else None
    orig = None
    m = RE_ORIG.search(body)
    if m:
        orig = float(m.group(1))
    platform = None
    m = RE_PLATFORM.search(body) or RE_PLATFORM.search(it["title"])
    if m:
        platform = m.group(1)
    if platform is None and "百亿补贴" in it["title"]:
        platform = "拼多多百亿补贴"
    score = None
    m = RE_SCORE.search(meta)
    if m:
        score = float(m.group(1))
    specs, seen = [], set()
    for num, unit in RE_SPEC.findall(f"{it['title']} {body}"):
        s = f"{num}{unit}"
        u = unit.lower()
        if u in seen and len(specs) > 3:
            continue
        seen.add(u)
        if s not in specs:
            specs.append(s)
    conds = []
    for seg in re.split(r"[。；;]", body):
        if re.search(r"(券|立减|下单|任选|实付|叠加|凑单|会员|补贴|限时|前\d+名|预约|定金|返)", seg):
            seg = seg.strip()
            if 6 <= len(seg) <= 70 and seg not in conds and "去购买" not in seg:
                conds.append(seg)
    complex_cond = bool(RE_COMPLEX.search(body))
    weak_source = ("来源不明确" in meta) or ("店铺来源不明确" in meta)
    newlow_meta = ("历史低价" in meta) or ("新低" in meta)
    return {"it": it, "price": price, "newlow_days": newlow_days, "drop": drop,
            "orig": orig, "platform": platform, "score": score, "specs": specs,
            "conds": conds[:2], "complex": complex_cond, "weak": weak_source,
            "newlow_meta": newlow_meta,
            "drop_calc": (round((1 - price / orig) * 100, 1) if price and orig and orig > price
                          else None)}


def judge(d):
    """确定性判定 → (是否推送, 颜色, 依据)  ; 颜色: green/orange/yellow"""
    if d["price"] is None:
        return False, None, "无价格，确定性规则无法判定"
    is_newlow = bool(d["newlow_days"]) or d["newlow_meta"]
    drop = d["drop_calc"] if d["drop_calc"] is not None else d["drop"]
    if not (is_newlow or (drop is not None and drop >= DROP_THRESHOLD)):
        return False, None, f"未达标(降幅 {drop}%，无新低信号)"
    if d["weak"] or d["complex"] or (d["score"] is not None and d["score"] < SCORE_LOW):
        color = "yellow"
    elif is_newlow:
        color = "green"
    else:
        color = "orange"
    tag = []
    if d["newlow_days"]:
        tag.append(f"新低{d['newlow_days']}天")
    elif d["newlow_meta"]:
        tag.append("历史低价信号")
    if drop is not None:
        tag.append(f"降幅 {drop:g}%")
    return True, color, "；".join(tag) or "确定性规则达标"


def rank_key(d):
    drop = d["drop_calc"] if d["drop_calc"] is not None else (d["drop"] or 0)
    return (1 if (d["newlow_days"] or d["newlow_meta"]) else 0, drop, d["score"] or 0)


# ── AI：只写推荐理由与风险提示 ──────────────────────────────────────────────
def pick_batch(cands, profile):
    """从排序后的候选里按分组去重，凑成一张最多 N 条的精选卡。"""
    if not cands:
        return []
    delivery = profile.get("delivery", {})
    max_items = int(delivery.get("max_items", MAX_PER_CARD))
    max_per_group = int(delivery.get("max_per_group", MAX_PER_GROUP))
    picked, counts = [], {}
    for d in cands:
        group = d.get("group") or d["it"]["cat"]
        label = d.get("group_label") or group
        if counts.get(group, 0) >= max_per_group:
            continue
        d["group_label"] = label
        picked.append(d)
        counts[group] = counts.get(group, 0) + 1
        if len(picked) >= max_items:
            break
    return picked


def build_prompt(batch):
    lines = ["下面是一批什么值得买爆料的**确定性解析结果**（数据准确，不要改动）：", ""]
    for n, d in enumerate(batch, 1):
        drop = d["drop_calc"] if d["drop_calc"] is not None else d["drop"]
        lines += [
            f"[{n}] 商品: {d['it']['title']}",
            f"    分类: {d['it']['cat']}｜平台: {d['platform'] or '未识别'}｜"
            f"现价: {d['price']:g} 元" + (f"（活动价 {d['orig']:g} 元）" if d["orig"] else ""),
            f"    降幅: {('%g%%' % drop) if drop else '未知'}｜"
            f"新低: {('%d天新低' % d['newlow_days']) if d['newlow_days'] else ('有历史低价信号' if d['newlow_meta'] else '无')}"
            f"｜规格: {'、'.join(d['specs']) or '见原文'}",
            f"    优惠条件: {'；'.join(d['conds']) or '见原文'}",
            "",
        ]
    lines += [
        '输出 JSON（每个编号一条，不要多不要少）：',
        '{"items":[{"n":编号,"why":"一句推荐理由≤45字，说清为什么值这个价，'
        '禁止\\"性价比高\\"这类空话","risk":"一句风险提示≤45字，指出这类商品最容易踩的坑'
        '（凑单/会员/型号/库存/时效）"}]}',
    ]
    return "\n".join(lines)


def parse_json(txt):
    if not txt:
        return None
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:                                          # noqa: BLE001
        return None
    arr = d.get("items")
    if not isinstance(arr, list):
        return None
    out = {}
    for x in arr:
        if not isinstance(x, dict):
            continue
        try:
            n = int(str(x.get("n", "")).strip())
        except Exception:                                      # noqa: BLE001
            continue
        why, risk = (x.get("why") or "").strip(), (x.get("risk") or "").strip()
        if why or risk:
            out[n] = {"why": why, "risk": risk}
    return out or None


def call_llm(prompt):
    """用户指定的免费模型链；全挂后冷却重试 openrouter/free。失败返回 None。"""
    started = time.time()
    chain = list(LLM_MODELS)
    if LLM_RETRY_FIRST_AFTER_COOLDOWN:
        chain.append("openrouter/free*")     # 带 * = 先冷却
    body = {"messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
            "temperature": 0.3, "max_tokens": 900,
            "reasoning": {"enabled": False}}   # 免费池里不少是推理模型，不关会把 token 烧光
    last, tried = None, []
    for model in chain:
        if time.time() - started > AI_DEADLINE_S:
            last = last or "AI 总预算超时"
            break
        if model.endswith("*"):
            time.sleep(COOLDOWN_S)
            model = model.rstrip("*")
        for key in LLM_KEYS:
            k = os.environ.get(key)
            if not k:
                continue
            body["model"] = model
            req = urllib.request.Request(LLM_URL, data=json.dumps(body).encode(), headers={
                "Authorization": f"Bearer {k}", "Content-Type": "application/json",
                "HTTP-Referer": FEED, "X-Title": "SMZDM Deal Alert"})
            try:
                with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                    resp = json.loads(r.read().decode())
                ch = (resp.get("choices") or [{}])[0]
                txt = (ch.get("message") or {}).get("content")
                out = parse_json(txt)
                if out:
                    print(f"[info] AI={model} key={key}", file=sys.stderr)
                    return out
                last = f"{model} 输出不可用(finish={ch.get('finish_reason')})"
                tried.append(last)
                break
            except urllib.error.HTTPError as e:
                last = f"{model} HTTP {e.code}"
                tried.append(last)
                if e.code in (401, 403, 404, 429):
                    break
            except Exception as e:                             # noqa: BLE001
                last = f"{model} {type(e).__name__}"
                tried.append(last)
                break
    print(f"[warn] AI 全失败({' | '.join(tried[-4:])}) → 只发确定性数据", file=sys.stderr)
    return None


# ── 卡片 ────────────────────────────────────────────────────────────────────
def buy_link(post_url):
    """从爆料页抓 go.smzdm.com 商品跳转；失败退回爆料页本身。"""
    try:
        page = html.unescape(fetch(post_url, timeout=15))
        m = re.search(r"(?:https?:)?//go\.smzdm\.com/[^\s\"'<>]+", page)
        if m:
            u = re.sub(r"[\\),\]}]+$", "", m.group(0))
            return ("https:" + u) if u.startswith("//") else u
    except Exception as e:                                     # noqa: BLE001
        print(f"[warn] 抓商品链接失败: {type(e).__name__}", file=sys.stderr)
    return post_url


def render_card(batch, ai, header_color):
    """多商品卡片：每项一段 markdown + 独立按钮行。header 取本卡头号好价的颜色，每项自带色标。"""
    ai_map = ai or {}
    ai_ok = ai is not None
    dot = {"green": "🟢", "orange": "🟠", "yellow": "🟡"}
    elements = [{"tag": "markdown",
                 "content": f"**本次 {len(batch)} 条好价**　🟢 新低/历史低价｜🟠 普通达标｜🟡 需二次确认"}]
    for i, d in enumerate(batch, 1):
        it = d["it"]
        drop = d["drop_calc"] if d["drop_calc"] is not None else d["drop"]
        a = ai_map.get(i)
        if a:
            why, risk = a["why"], a["risk"]
        else:
            bits = []
            if d["newlow_days"]:
                bits.append(f"{d['newlow_days']} 天新低")
            elif d["newlow_meta"]:
                bits.append("有历史低价信号")
            if drop:
                bits.append(f"降幅约 {drop:g}%")
            if d["platform"]:
                bits.append(d["platform"])
            why = "；".join(bits) + "，可对照原文核实后再下单" if bits else "确定性规则判定达标，详见原文"
            risk = ("价格为爆料时点数据，可能随时变动或售罄；" +
                    ("该优惠含凑单/会员等条件，下单前请二次确认。" if d["complex"]
                     else "优惠条件以原文为准。"))
        price_line = f"**{d['price']:g} 元**"
        if d["orig"]:
            price_line += f"（活动价 {d['orig']:g} 元）"
        if drop:
            price_line += f"｜降幅约 {drop:g}%"
        if d["newlow_days"]:
            price_line += f"｜{d['newlow_days']} 天新低"
        md = [
            f"**{i}. {dot.get(d['color'], '⚪')} 商品**：{it['title']}",
            f"**价格**：{price_line}",
            f"**来源**：{d['platform'] or '见原文'} · 什么值得买爆料",
            f"**优惠条件**：{'；'.join(d['conds']) or '见原文'}",
            f"**型号规格**：{'、'.join(d['specs']) or '见原文'}",
            f"**推荐理由**：{why}",
            f"**风险提示**：{risk}",
        ]
        elements.append({"tag": "markdown", "content": "\n".join(md)})
        elements.append({"tag": "action", "actions": [
            build_smzdm_button(
                "查看商品",
                d.get("buy") or it["link"],
                web_fallback=it["link"],
                button_type="primary",
            ),
            build_smzdm_button("查看原文", it["link"]),
        ]})
    if not ai_ok:
        elements.append({"tag": "markdown",
                         "content": "ℹ️ **AI 优惠解读暂不可用**"
                                    "（以上价格、链接、优惠条件均为确定性解析，未受影响）"})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text",
                             "content": f"今日精选好价｜{batch[0].get('group_label') or batch[0]['it']['cat']}"},
                   "template": header_color},
        "elements": elements,
    }


def send_card(card):
    os.makedirs(os.path.dirname(CARD_FILE), exist_ok=True)
    with open(CARD_FILE, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False)
    r = subprocess.run(["python3", CARD_API, "--card-file", CARD_FILE, "--chat", CHAT],
                       capture_output=True, text=True, timeout=90)
    ok = r.returncode == 0 and "OK message_id" in (r.stdout or "")
    print(f"[{'info' if ok else 'warn'}] 发卡 {'成功 ' + r.stdout.strip() if ok else '失败 ' + r.stderr.strip()}",
          file=sys.stderr)
    return ok


# ── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    test_color = None
    if "--test-color" in args:
        test_color = args[args.index("--test-color") + 1]
    now = datetime.now(CST)
    load_env()
    profile = load_profile()
    delivery = profile.get("delivery", {})
    max_cards_per_day = int(delivery.get("max_cards_per_day", MAX_CARDS_PER_DAY))
    max_age_h = float(delivery.get("max_age_hours", MAX_AGE_H))
    min_score = float(delivery.get("min_score", 0))

    # 静默时段（--dry-run / --test-color 自检不受限）
    if (now.hour >= QUIET_FROM_H or now.hour < QUIET_TO_H) and not (dry or test_color):
        print(f"[info] 静默时段({now.hour}点)，不推送", file=sys.stderr)
        return 0

    state = load_state()
    today = now.strftime("%Y-%m-%d")
    sent_today = int(state["sent"].get(today, 0))
    if sent_today >= max_cards_per_day and not dry and not test_color:
        print(f"[info] 今日已发 {sent_today} 条（上限 {max_cards_per_day}），静默",
              file=sys.stderr)
        return 0

    try:
        items = parse_items(fetch(FEED, timeout=30))
    except Exception as e:                                     # noqa: BLE001
        print(f"⚠️ 好价提醒取数失败：{type(e).__name__} {e}")
        return 0
    fresh = [i for i in items if not i["pub"] or (now - i["pub"]).total_seconds() <= max_age_h * 3600]
    cands = []
    for it in fresh:
        if it["key"] in state["alerted"]:
            continue
        match = profile_match(it, profile)
        if not match:
            continue
        d = parse_deal(it)
        if d["score"] is not None and d["score"] < min_score:
            continue
        ok, color, why = judge(d)
        if ok:
            d["color"], d["verdict"] = color, why
            d["group"], d["group_label"] = match
            cands.append(d)
    cands.sort(key=rank_key, reverse=True)
    print(f"[info] 好价条目 {len(items)} 条 → {max_age_h:g}h 内 {len(fresh)} 条 → 达标 {len(cands)} 条"
          f"；今日已发 {sent_today}", file=sys.stderr)

    if not cands and not test_color:
        print("[info] 无达标好价，保持沉默", file=sys.stderr)
        return 0

    batch = pick_batch(cands, profile)
    if test_color and not batch:            # 自检：没有达标样本就拿一条能解析的
        pool = [parse_deal(i) for i in (fresh or items)]
        batch = [d for d in pool if d["price"] is not None][:1]
        if not batch:
            print("[info] 自检：没有可用样本", file=sys.stderr)
            return 0
    if test_color:
        for d in batch:
            d["color"], d["verdict"] = test_color, "自检"
    print(f"[info] 本卡 {len(batch)} 条（{batch[0].get('group_label') or batch[0]['it']['cat']}）: "
          + "；".join(f"{d['it']['title'][:14]}→{d['color']}" for d in batch), file=sys.stderr)

    for d in batch:
        d["buy"] = buy_link(d["it"]["link"])
    ai = call_llm(build_prompt(batch))
    header_color = batch[0]["color"]
    card = render_card(batch, ai, header_color)
    if dry:
        os.makedirs(os.path.dirname(CARD_FILE), exist_ok=True)
        with open(CARD_FILE, "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=1)
        print(json.dumps(card, ensure_ascii=False, indent=1))
        print(f"\n[dry] header={header_color} 条数={len(batch)} 卡片 JSON 见 {CARD_FILE}")
        return 0
    sent = send_card(card)
    if sent and not test_color:
        state["sent"][today] = sent_today + 1
        for d in batch:
            state["alerted"][d["it"]["key"]] = time.time()
            key = re.sub(r"[^\w\u4e00-\u9fff]", "", d["it"]["title"])[:24]
            rec = state["min_price"].get(key)
            if not rec or d["price"] < rec.get("price", 1e18):
                state["min_price"][key] = {"price": d["price"], "ts": time.time(),
                                           "title": d["it"]["title"][:60],
                                           "cat": d["it"]["cat"]}
    elif sent:
        print(f"[info] 自检卡片已发送({len(batch)} 条，不计当日额度)", file=sys.stderr)
    else:
        print("⚠️ 好价提醒：卡片发送失败（详见日志）")
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
