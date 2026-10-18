#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smzdm_digest.py — 《什么值得买文章精选》→ 飞书 interactive 卡片

数据源: https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.xml
上游: GitHub Actions `0 * * * *`(TZ=Asia/Shanghai) 重建 feed；实际落地常在 :25–:45。

只处理【非好价】内容:
  AI 应用探索 / 软件应用 / 垃圾佬每日精选 / 社区日榜 / 评测·攻略·资讯·经验·避坑·深度
严格排除: 食品生鲜好价 / 酒水好价 / 电脑配件好价 / 电脑配件精选（以及任何"好价"分类）

契约:
  · 成功 → stdout 为空(no_agent 任务保持静默)
  · 失败 → stdout 打印一行提示(会被投递给用户), 退出码 0
用法:
  python3 smzdm_digest.py            正常：拉数据 → 发卡
  python3 smzdm_digest.py --dry-run  不发送，只把卡片写到 /tmp 并打印摘要(自检用)
"""
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

FEED = "https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.xml"
ENV_FILE = "/opt/data/.env"
CARD_API = "/opt/data/workspace/scripts/feishu_card_api.py"
CARD_FILE = "/tmp/smzdm_card.json"
CHAT = "oc_b8559c55f250b54d396a8d8105bb1355"
CST = timezone(timedelta(hours=8))

# 11:05 若 lastBuildDate 还是上一小时 → 最多等到 11:10
WAIT_FROM = (11, 5)
WAIT_UNTIL = (11, 10)
POLL_S = 60

SEC_AI, SEC_SW, SEC_LAJI, SEC_RANK = "AI 应用探索", "软件应用", "垃圾佬每日精选", "社区日榜"
MAX_PER_SECTION = 5
RANK_EXPECT = 12
EXCLUDE_CATS = {
    "食品生鲜好价",
    "酒水好价",
    "电脑配件好价",
    "电脑配件精选",
    "好价候选池",
}
ARTICLE_CATS = ("评测", "攻略", "资讯", "经验", "避坑", "深度", "原创", "晒物", "好文", "指南", "科普", "教程")
# 仅对"未知分类"生效的价格兜底（社区日榜/垃圾佬讨论行情，不能被误杀）
PRICE_RE = re.compile(r"(好价|优惠券|领券|凑单|返\d*积分|返现|会员价|到手价|百亿补贴|限时折扣|秒杀|抢购|元包邮|元起|¥|￥)")

LLM_URL = "https://openrouter.ai/api/v1/chat/completions"
# 用户策略: openrouter/free 为首，固定免费模型兜底，禁止默认付费
LLM_MODELS = (
    "openrouter/free",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
)
LLM_KEYS = ("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3")

SYSTEM = ("你是《什么值得买》的消费内容编辑，服务一位爱折腾 AI 工作流与硬件的读者。"
          "只输出 JSON，不要解释、不要代码块围栏。")


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


def fetch_feed(timeout=30):
    req = urllib.request.Request(FEED, headers={"User-Agent": "smzdm-digest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_title(t):
    """去掉标题里重复的 [分类] 前缀。"""
    t = (t or "").strip()
    for _ in range(3):
        m = re.match(r"^\[[^\]]{1,12}\]\s*", t)
        if not m:
            break
        t = t[m.end():].strip()
    return t


def clean_desc(d, limit=300):
    """去掉 RSS 里的检索元信息行、尾部计数/作者样板，返回正文。"""
    d = re.sub(r"<[^>]+>", " ", d or "")
    d = re.sub(r"^[^\n]*推荐分[^\n]*\n?", " ", d)
    d = re.sub(r"^搜索[:：][^\n]*\n?", " ", d)
    d = re.sub(r"\s[\d\s\-]{3,}\d{1,2}:\d{2}\s+\S*\s*$", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    return d[:limit]


def clip_text(s, limit):
    """按句读边界截断，避免出现半句话。"""
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    head = s[:limit]
    m = list(re.finditer(r"[。！？；…]", head))
    if m and m[-1].end() >= limit * 0.5:
        return head[:m[-1].end()]
    m2 = list(re.finditer(r"[，、]", head))
    if m2 and m2[-1].end() >= limit * 0.6:
        return head[:m2[-1].end()] + "…"
    return head.rstrip("，、。 ") + "…"


def make_intro(text, title, limit=88):
    """从正文开头生成一句"介绍"：剥掉重复标题与紧随其后的标签串，再按句读截断。"""
    d = text or ""
    t = re.sub(r"\s+", " ", (title or "").strip())
    for n in range(len(t), 5, -1):
        if d.startswith(t[:n]):
            d = d[n:].strip()
            break
    parts = d.split(" ", 1)          # 丢掉 "AI新鲜事数码AI文本创作" 这类标签串（只剥一层，多剥会吃掉小标题）
    if len(parts) == 2 and len(parts[0]) >= 4 and \
            not re.search(r"[，。！？、：；,.]", parts[0]):
        d = parts[1].strip()
    return clip_text(d, limit)


def norm_link(link):
    link = (link or "").strip()
    link = re.sub(r"^http://", "https://", link, flags=re.I)
    link = link.split("#")[0].split("?")[0]
    return link.rstrip("/").lower()


def parse_feed(raw):
    """返回 (items, last_build_dt)。item: title/link/guid/cat/pub/desc/key"""
    root = ET.fromstring(raw)
    chan = root.find("channel") if root.find("channel") is not None else root
    last_build = None
    lb = chan.findtext("lastBuildDate")
    if lb:
        try:
            last_build = parsedate_to_datetime(lb.strip()).astimezone(CST)
        except Exception:                                      # noqa: BLE001
            last_build = None
    items = []
    for it in chan.findall("item"):
        title = clean_title(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or "").strip()
        cat = (it.findtext("category") or "").strip()
        pub = it.findtext("pubDate") or ""
        text = clean_desc(it.findtext("description"))
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "guid": guid, "cat": cat,
                      "pub": pub, "desc": text,
                      "intro": make_intro(text, title),
                      "key": guid or norm_link(link)})
    return items, last_build


# ── 分类 / 去重 ─────────────────────────────────────────────────────────────
def is_excluded(it):
    cat = it["cat"]
    if cat in EXCLUDE_CATS or cat.endswith("好价"):
        return True
    # 未知分类里，标题/摘要以价格促销为主的也排除（日榜与垃圾佬不受此限）
    if cat in (SEC_RANK, SEC_LAJI) or any(k in cat for k in ARTICLE_CATS):
        return False
    if cat in (SEC_AI, SEC_SW):
        return False
    return bool(PRICE_RE.search(it["title"]) or PRICE_RE.search(it["desc"][:60]))


def build_sections(items):
    seen, deduped, dropped = set(), [], 0
    for it in items:
        if it["key"] in seen:
            continue
        seen.add(it["key"])
        if is_excluded(it):
            dropped += 1
            continue
        deduped.append(it)

    sec = {SEC_AI: [], SEC_SW: [], SEC_LAJI: [], SEC_RANK: [], "editorial": []}
    for it in deduped:
        if it["cat"] in (SEC_AI, SEC_SW, SEC_LAJI, SEC_RANK):
            sec[it["cat"]].append(it)
        else:
            sec["editorial"].append(it)
    return sec, dropped


# ── 等待上游刷新 ────────────────────────────────────────────────────────────
def hour_start(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


def wait_for_fresh(now=None):
    """11:05–11:10 之间若 lastBuildDate 仍属上一小时，则轮询等待。"""
    now = now or datetime.now(CST)
    start_h, start_m = WAIT_FROM
    until_h, until_m = WAIT_UNTIL
    in_window = (now.hour == start_h and now.minute >= start_m) or \
                (now.hour == until_h and now.minute < until_m)
    deadline = now.replace(hour=until_h, minute=until_m, second=0, microsecond=0)
    waited = False
    while True:
        try:
            raw = fetch_feed()
        except Exception as e:                                 # noqa: BLE001
            if waited or not in_window:
                raise
            print(f"[warn] 拉取失败, 继续等到 {until_h:02d}:{until_m:02d}: {e}",
                  file=sys.stderr)
            time.sleep(POLL_S)
            waited = True
            continue
        items, last_build = parse_feed(raw)
        now2 = datetime.now(CST)
        fresh = bool(last_build and last_build >= hour_start(now2))
        if fresh or not in_window or now2 >= deadline:
            # 只有"本该更新却在 11:10 前没更新"才标注延迟；手动跑不加这个提示
            return items, last_build, (in_window and not fresh)
        time.sleep(POLL_S)
        waited = True


# ── AI 摘要 / 推荐理由 ──────────────────────────────────────────────────────
def build_prompt(pool, stamp):
    lines = [f"今日日期: {stamp}", "",
             "下面是今日【非好价】文章池（已剔除食品生鲜/酒水/电脑配件好价）：", ""]
    for i, it in enumerate(pool, 1):
        lines.append(f"[{i}] ({it['cat']}) {it['title']}")
        if it["desc"]:
            lines.append(f"    摘要: {it['desc'][:110]}")
    lines += [
        "",
        "请输出 JSON（不要其它文字）：",
        '{"must_read":[{"n":<池中编号>,"why":"一句推荐理由，≤40字，要具体说清看点，'
        '禁止\\"值得一读/内容不错\\"这类空话"},共3条],'
        '"summary":"2-3句今日总结，≤120字，点出今天最值得关注的信号"}',
        "",
        "要求：must_read 必须来自上面的池子，优先选有信息量/可操作的深度内容；编号不要重复。",
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
    picks = d.get("must_read")
    if not isinstance(picks, list) or not picks:
        return None
    ok = [p for p in picks if isinstance(p, dict) and str(p.get("n", "")).strip().isdigit()]
    if not ok:
        return None
    d["must_read"] = ok[:3]
    d["summary"] = (d.get("summary") or "").strip()
    return d


def call_llm(prompt):
    """失败返回 None（调用方走兜底）。openrouter/free 优先，固定免费模型兜底。"""
    body = {"messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
            "temperature": 0.3, "max_tokens": 900}
    last_err = None
    for model in LLM_MODELS:
        for key in LLM_KEYS:
            k = os.environ.get(key)
            if not k:
                continue
            body["model"] = model
            payload = json.dumps(body).encode()
            for attempt in (1, 2):
                req = urllib.request.Request(LLM_URL, data=payload, headers={
                    "Authorization": f"Bearer {k}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": FEED,
                    "X-Title": "SMZDM Digest",
                })
                try:
                    with urllib.request.urlopen(req, timeout=90) as r:
                        d = json.loads(r.read().decode())
                    ch = (d.get("choices") or [{}])[0]
                    txt = (ch.get("message") or {}).get("content")
                    if not txt:
                        last_err = f"{model} 空输出(finish={ch.get('finish_reason')})"
                        break
                    out = parse_json(txt)
                    if out:
                        print(f"[info] LLM={model} key={key}", file=sys.stderr)
                        return out
                    last_err = f"{model} JSON 解析失败"
                    break
                except urllib.error.HTTPError as e:
                    last_err = f"{model} HTTP {e.code}"
                    if e.code == 429 and attempt == 1:
                        time.sleep(20)
                        continue
                    break
                except Exception as e:                         # noqa: BLE001
                    last_err = f"{model} {type(e).__name__}: {e}"
                    break
    print(f"[warn] AI 不可用({last_err})，改用原始摘要兜底", file=sys.stderr)
    return None


def fallback_reads(pool):
    """AI 挂了也不能空手：按分区优先级取前 3 条，理由用原始摘要前缀。"""
    return [{"n": i + 1,
             "why": (it["desc"][:60] + "…") if it["desc"] else "原始摘要（AI 不可用）"}
            for i, it in enumerate(pool[:3])]


# ── 卡片 ────────────────────────────────────────────────────────────────────
def render_card(sections, reads, summary, last_build, delayed, ai_broken, pool):
    by_n = {i + 1: it for i, it in enumerate(pool)}
    stamp = datetime.now(CST).strftime("%Y-%m-%d")
    md = []

    if ai_broken:
        md += ["⚠️ **AI 分析暂不可用，以下为原始摘要**", ""]

    md += ["**📌 今日必读**"]
    if reads:
        for i, r in enumerate(reads, 1):
            it = by_n.get(int(r["n"]))
            if not it:
                continue
            md.append(f"{i}. [{it['title']}]({it['link']})")
            why = (r.get("why") or "").strip()
            if why:
                md.append(f"   推荐理由：{why}")
    else:
        md.append("（今日无）")
    md.append("")

    for emoji, title, key in (("🤖", SEC_AI, SEC_AI), ("💻", SEC_SW, SEC_SW),
                              ("🖥", SEC_LAJI, SEC_LAJI)):
        items = sections.get(key) or []
        md.append(f"**{emoji} {title}**（{len(items)} 条）")
        for i, it in enumerate(items[:MAX_PER_SECTION], 1):
            md.append(f"{i}. [{it['title']}]({it['link']})")
            if it.get("intro"):
                md.append(f"   简介：{it['intro']}")
        if not items:
            md.append("（今日无）")
        md.append("")

    rank = sections.get(SEC_RANK) or []
    md.append(f"**🏆 社区日榜完整榜单**（{len(rank)}/{RANK_EXPECT} 条）")
    for i, it in enumerate(rank, 1):
        line = f"{i}. [{it['title']}]({it['link']})"
        md.append(f"**{line}**" if i <= 3 else line)
    if not rank:
        md.append("（今日无）")
    md.append("")

    if summary:
        md += ["**🧭 今日总结**", summary, ""]

    ts = last_build.strftime("%Y-%m-%d %H:%M") if last_build else "未知"
    md.append(f"**🕐 数据更新时间**：{ts}（北京时间）")
    if delayed:
        md.append("⚠️ 数据可能延迟：RSS 尚未更新到当前小时那一版")

    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text",
                             "content": f"什么值得买文章精选｜{stamp}"},
                   "template": "blue"},
        "elements": [{"tag": "markdown", "content": "\n".join(md)}],
    }
    return card


def send_card(card):
    with open(CARD_FILE, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False)
    r = subprocess.run(["python3", CARD_API, "--card-file", CARD_FILE, "--chat", CHAT],
                       capture_output=True, text=True, timeout=90)
    ok = r.returncode == 0 and "OK message_id" in (r.stdout or "")
    if not ok:
        print(f"[warn] 卡片直发失败 rc={r.returncode} {r.stdout.strip()} {r.stderr.strip()}",
              file=sys.stderr)
    else:
        print(f"[info] 卡片已送达 {r.stdout.strip()}", file=sys.stderr)
    return ok


def main():
    dry = "--dry-run" in sys.argv
    load_env()
    try:
        items, last_build, delayed = wait_for_fresh()
    except Exception as e:                                     # noqa: BLE001
        print(f"⚠️ 什么值得买精选取数失败：{type(e).__name__} {e}")
        return 0
    if not items:
        print("⚠️ 什么值得买精选：RSS 里没有条目")
        return 0

    sections, dropped = build_sections(items)
    print(f"[info] 条目 {len(items)} 条 → 去重后保留，排除好价 {dropped} 条；"
          f"AI {len(sections[SEC_AI])}/软件 {len(sections[SEC_SW])}/"
          f"垃圾佬 {len(sections[SEC_LAJI])}/日榜 {len(sections[SEC_RANK])}/"
          f"其它 {len(sections['editorial'])}", file=sys.stderr)

    # 今日必读候选池：编辑类优先，其次 AI/软件/垃圾佬
    pool = (sections["editorial"] + sections[SEC_AI] + sections[SEC_SW]
            + sections[SEC_LAJI])[:14]
    stamp = datetime.now(CST).strftime("%Y-%m-%d")
    data = call_llm(build_prompt(pool, stamp)) if pool else None
    ai_broken = data is None
    if ai_broken:
        reads = fallback_reads(pool) if pool else []
        summary = ""
    else:
        reads = data.get("must_read") or fallback_reads(pool)
        summary = data.get("summary") or ""

    card = render_card(sections, reads, summary, last_build, delayed, ai_broken, pool)
    if dry:
        body = card["elements"][0]["content"]
        print("─" * 30 + " CARD PREVIEW (dry-run) " + "─" * 30)
        print(body)
        print("─" * 70)
        print(f"[dry-run] 未发送；卡片 JSON 见 {CARD_FILE}")
        return 0
    if not send_card(card):
        print("⚠️ 什么值得买文章精选：卡片发送失败（详见日志）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
