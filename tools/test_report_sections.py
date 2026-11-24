#!/usr/bin/env python3
"""Offline tests for the sections below the first screen (soxl_quant/report_sections.py).

Run: python3 tools/test_report_sections.py

No network.  Reads ``soxl_analysis_data.json`` and ``history/snapshots/*.json.gz``.  Writes nothing.

Covers
  1. ``clean``: stored strings with placeholder tokens, with known answers
  2. numbers: a missing value prints 暫缺 alone, never ``$暫缺`` or ``n/a%``
  3. links: only http(s) URLs become links
  4. takeaways: every branch of the plan line, and the missing line of every section on an empty payload
  5. every stored payload: no failed section, takeaways of at most 40 characters, no placeholder token
     in reader text with every fold open, at most one chart and no table over 8 rows in the default
     view, no text of 120 characters or more twice
  6. options: one missing line and nothing else when the chain is empty; chart and folds when it is there
  7. takeaways change with the data: at least 3 differ between two stored days
  8. escaping: script tags, event handlers, quotes and ``javascript:`` links in news text stay text
  9. the whole page (report_page.render): one disclaimer equal to the feed's string, section links that
     resolve, no placeholder token and no long text twice with every fold open, a script-nonce policy,
     no resource from another origin, and three page files with the same bytes
 10. docs/section_log.md: every position it names for a kept block exists on the page, every removal
     row gives one of the three allowed reasons, and every deleted file is gone
"""
from __future__ import annotations

import copy
import glob
import gzip
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from soxl_quant import brief, report_page  # noqa: E402
from soxl_quant import report_sections as rs  # noqa: E402

BAD = 0
# whole-word placeholder tokens, a "$" with no number, and empty brackets
TOKEN = re.compile(r"(?<![A-Za-z0-9_])(None|n/a|nan|null|undefined)(?![A-Za-z0-9_])|[$＄](?![\d+\-−.,])|\(\s*\)|（\s*）", re.I)
VOID = {"br", "img", "hr", "input", "meta", "link", "col", "source", "wbr"}


def check(cond, msg):
  global BAD
  if not cond:
    BAD += 1
  print(("PASS" if cond else "FAIL"), msg)


class Node:
  def __init__(self, tag, attrs, parent):
    self.tag, self.attrs, self.parent, self.kids = tag, attrs, parent, []

  def text(self):
    return re.sub(r"\s+", " ", "".join(k if isinstance(k, str) else k.text() for k in self.kids)).strip()

  def walk(self):
    yield self
    for k in self.kids:
      if not isinstance(k, str):
        yield from k.walk()

  def up(self):
    n = self.parent
    while n is not None:
      yield n
      n = n.parent

  def inside(self, tag=None, attr=None):
    return any((tag is None or n.tag == tag) and (attr is None or attr in n.attrs) for n in [self, *self.up()])


class Tree(HTMLParser):
  def __init__(self, html_text):
    super().__init__(convert_charrefs=True)
    self.root = Node("#root", {}, None)
    self.cur = self.root
    self.feed(html_text)

  def handle_starttag(self, tag, attrs):
    n = Node(tag, dict(attrs), self.cur)
    self.cur.kids.append(n)
    if tag not in VOID:
      self.cur = n

  def handle_endtag(self, tag):
    n = self.cur
    while n is not None and n.tag != tag:
      n = n.parent
    if n is not None and n.parent is not None:
      self.cur = n.parent

  def handle_data(self, data):
    self.cur.kids.append(data)


def section_of(n):
  for a in [n, *n.up()]:
    if a.tag == "section" and "data-sec" in a.attrs:
      return a.attrs["data-sec"]
    if a.tag == "footer":
      return "footer"
  return "?"


def text_nodes(root):
  """(text, parent node) of every text node outside script and style."""
  for n in root.walk():
    if n.tag in ("script", "style"):
      continue
    for k in n.kids:
      if isinstance(k, str) and k.strip():
        yield k, n


def page_of(p):
  return rs.nav_html() + rs.sections_html(p) + rs.footer_html(p)


def audit(p):
  """Problems of the sections built from one payload, as a list of strings."""
  out = []
  tree = Tree(page_of(p))
  secs = [n for n in tree.root.walk() if n.tag == "section" and "data-sec" in n.attrs]
  if [n.attrs["data-sec"] for n in secs] != list(rs.SECTION_IDS):
    out.append("sections are not the ten ids in order")
  for n in secs:
    if n.attrs.get("data-state") not in ("ok", "missing"):
      out.append(f"section {n.attrs['data-sec']} has state {n.attrs.get('data-state')}")
    takes = [k for k in n.walk() if "data-takeaway" in k.attrs]
    if len(takes) != 1 or not takes[0].text():
      out.append(f"section {n.attrs['data-sec']} has no single takeaway")
    elif len(takes[0].text()) > rs.TAKEAWAY_MAX:
      out.append(f"takeaway of {n.attrs['data-sec']} has {len(takes[0].text())} characters")
  for sid, t in rs.takeaways(p).items():
    shown = next((k.text() for n in secs if n.attrs["data-sec"] == sid for k in n.walk() if "data-takeaway" in k.attrs), None)
    if shown != t["text"]:
      out.append(f"takeaway of {sid} on the page differs from takeaways()")
  # reader text: model text must hold no placeholder token (outside text is marked data-ext)
  for text, n in text_nodes(tree.root):
    if n.inside(attr="data-ext"):
      continue
    m = TOKEN.search(text)
    if m:
      out.append(f"token {m.group(0)!r} in {section_of(n)}: {text.strip()[:60]}")
  for n in tree.root.walk():
    for key in ("title", "aria-label"):
      if key in n.attrs and TOKEN.search(n.attrs[key] or ""):
        out.append(f"token in the {key} attribute of <{n.tag}> in {section_of(n)}")
    if n.tag == "a" and not re.match(r"(https?://|#)", n.attrs.get("href") or "", re.I):
      out.append(f"link with scheme outside http(s): {(n.attrs.get('href') or '')[:40]}")
    if any(k.lower().startswith("on") for k in n.attrs):
      out.append(f"event handler attribute on <{n.tag}>")
    if n.tag in ("script", "iframe", "object", "embed", "img", "form", "base"):
      out.append(f"<{n.tag}> element in the sections")
  # default view: what a closed fold does not hide
  for sec in secs:
    sid = sec.attrs["data-sec"]
    seen = [n for n in sec.walk() if not n.inside(tag="details")]
    charts = [n for n in seen if "data-viz" in n.attrs] + [n for n in seen if n.tag == "svg" and not n.inside(attr="data-viz")]
    if len(charts) > 1:
      out.append(f"default view of {sid} shows {len(charts)} charts")
    for tb in (n for n in seen if n.tag == "table"):
      rows = [r for r in tb.walk() if r.tag == "tr" and r.inside(tag="tbody")]
      if len(rows) > 8:
        out.append(f"default view of {sid} shows a table of {len(rows)} rows")
  # options: the missing line stands for every options block
  opt = next(n for n in secs if n.attrs["data-sec"] == "options")
  drawn = [n.tag for n in opt.walk() if n.tag in ("svg", "table", "details")]
  if rs.options_missing(p):
    if drawn or opt.attrs.get("data-state") != "missing":
      out.append(f"options chain is empty but the section draws {drawn}")
  elif "svg" not in drawn or drawn.count("details") < 1:
    out.append("options chain is there but the section has no chart or no fold")
  # no long text twice: an element counts once, wrappers with the same text as their parent are skipped
  texts = {}
  for n in tree.root.walk():
    if n.tag in ("script", "style", "#root"):
      continue
    t = n.text()
    if len(t) >= 120 and (n.parent is None or n.parent.text() != t):
      texts.setdefault(t, []).append(n)
  for t, nodes in texts.items():
    if len(nodes) > 1:
      out.append(f"text of {len(t)} characters appears {len(nodes)} times in {sorted({section_of(n) for n in nodes})}: {t[:40]}")
  return out


def load_payloads():
  out = []
  cur = REPO / "soxl_analysis_data.json"
  if cur.exists():
    out.append(("current data", json.load(open(cur, encoding="utf-8"))))
  for f in sorted(glob.glob(str(REPO / "history" / "snapshots" / "*.json.gz"))):
    out.append((Path(f).name[5:15], json.load(gzip.open(f, "rt", encoding="utf-8"))))
  return out


# ---- 1. clean: stored strings with known answers
OPT = rs.OPT_NOTE
CASES = [
    ("籌碼：SOXL 期權 Put/Call 成交 None、淨 GEX +0.0M、大戶淨方向 None、Put 牆 $None / Call 牆 $None、IV30 None%。", OPT, f"籌碼：{OPT}。"),
    ("期權：n/a 到期（Max Pain $n/a，P/C n/a）；Gamma 翻正位 $None", OPT, f"期權：{OPT}"),
    ("板塊：16 檔成分股站上 20MA 比例 0% → 目標 >40%；大戶期權淨方向 n/a → 轉正", OPT, "板塊：16 檔成分股站上 20MA 比例 0% → 目標 >40%；大戶期權淨方向暫缺 → 轉正"),
    ("SOXL None，個股第 70 百分位", OPT, "SOXL 暫缺，個股第 70 百分位"),
    ("SOXL 成交 None（n/a）｜全市場個股 0.62（1 年第 70 百分位）", OPT, "SOXL 成交暫缺｜全市場個股 0.62（1 年第 70 百分位）"),
    ("SOXL 未平倉 P/C None；全市場總 P/C 1.01（偏避險 (0.9-1.1)）；個股 P/C 讀法 中性 (0.55-0.70)", OPT, "SOXL 未平倉 P/C 暫缺；全市場總 P/C 1.01（偏避險 (0.9-1.1)）；個股 P/C 讀法 中性 (0.55-0.70)"),
    ("None", OPT, "暫缺"),
    ("造市商淨 Gamma 目前 +0.0M (Gamma 翻正位 $None)，IV30 高達 None%。在負 Gamma 區，造市商順勢避險。", "今天的期權讀數暫缺", "今天的期權讀數暫缺。在負 Gamma 區，造市商順勢避險。"),
    ("淨分數 n/a | 大單 Call $0.0M vs Put $0.0M (C/P n/a)", OPT, OPT),
    ("0.68 (單日 0.62) | 全市場 1.01 | SPX None", OPT, "0.68 (單日 0.62) | 全市場 1.01 | SPX 暫缺"),
    ("年線濾網：持有（出場線 n/a）", OPT, "年線濾網：持有（出場線暫缺）"),
    ("期權：2026-11-06 到期（Max Pain $60，P/C 0.80）；Gamma 翻正位 $None", OPT, "期權：2026-11-06 到期（Max Pain $60，P/C 0.80）；Gamma 翻正位暫缺"),
    ("Put 牆 $ (OI 0)｜月選 Max Pain $ ()", OPT, "Put 牆 (OI 0)｜月選 Max Pain"),
    ("收盤站上 EMA5 $43.71 且量能 RVOL ≥ 1.2", OPT, "收盤站上 EMA5 $43.71 且量能 RVOL ≥ 1.2"),
    ("Nancy 談 financial 與 nanometer，結論是 nonetheless", OPT, "Nancy 談 financial 與 nanometer，結論是 nonetheless"),
    ("報酬 nan%，樣本 NaN 次", "資料暫缺", "資料暫缺"),
]
for src, note, want in CASES:
  got = rs.clean(src, note)
  check(got == want and not TOKEN.search(got), f"clean: {src[:34]}… → {got[:44]}")
check(rs.clean(None) == "" and rs.clean("") == "" and rs.clean(12.5) == "12.5", "clean: None and empty give an empty string, a number gives its text")

# ---- 2. numbers
check(rs.nv(None) == "暫缺" and rs.usd(None) == "暫缺" and rs.pct(None) == "暫缺" and rs.nv(float("nan"), suffix="%") == "暫缺" and rs.nv("x", prefix="$") == "暫缺",
      "numbers: a missing value prints 暫缺 with no unit and no currency sign")
check(rs.usd(1234.5) == "$1,234.50" and rs.pct(-3.14159) == "-3.1%" and rs.pct(5, 0, False) == "5%" and rs.nv(True) == "暫缺", "numbers: formats of a present value; a bool is not a number")
check(rs.sx("短字") == '<span class="nw">短字</span>' and "<span" not in rs.sx("這是一段超過十六個字的說明文字不需要包住") and rs.sx(None) == "", "sx: a text of at most 16 characters stays on one line")

# ---- 3. links
check(rs._link("https://example.com/a?b=1&c=2", "t") == '<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">t</a>', "link: an https URL becomes a link, escaped")
for bad in ("javascript:alert(1)", "JAVASCRIPT:alert(1)", " javascript:alert(1)", "data:text/html,<script>1</script>", "//evil.example", "https://a.example/\" onmouseover=\"x", "", None, "vbscript:x", "https://a b"):
  check(rs._link(bad, "t") == "t", f"link: {str(bad)[:34]!r} stays plain text")

# ---- 4. takeaways on small payloads
def plan_take(tp):
  return rs.takeaways({"trade_plan": tp})["plan"]


check(plan_take({"side": "long", "tradeable": True, "entry": {"price": 90.5}, "stop": {"price": 75.49}}) == {"state": "ok", "text": "可以進場 $90.50；停損 $75.49"}, "plan takeaway: tradeable long")
check(plan_take({"side": "long", "tradeable": False, "rr_blend": 1.2}) == {"state": "ok", "text": "買訊成立但風報比 1.20R 不到門檻；先等"}, "plan takeaway: long below the reward-to-risk gate")
check(plan_take({"side": "long_pending", "entry": {"price": 43.71}}) == {"state": "ok", "text": "買點未觸發；收盤站上 $43.71 才進場"}, "plan takeaway: pending trigger")
check(plan_take({"side": "no_trade", "stop": {"price": 29.82}}) == {"state": "ok", "text": "不開新倉；持有者停損 $29.82"}, "plan takeaway: no trade")
check(plan_take({"side": "no_trade"}) == {"state": "ok", "text": "不開新倉；今天沒有買點"}, "plan takeaway: no trade and no stop")
empty = rs.takeaways({})
check(all(empty[k] == {"state": "missing", "text": rs.MISSING[k]} for k in rs.SECTION_IDS), "empty payload: every section gives its missing line")
check(all(len(v) <= rs.TAKEAWAY_MAX for v in rs.MISSING.values()) and len(rs.ERROR_LINE) <= rs.TAKEAWAY_MAX, "every missing line has at most 40 characters")
tree = Tree(page_of({}))
check(not [n for n in tree.root.walk() if n.tag in ("svg", "table")] and len([n for n in tree.root.walk() if n.tag == "section"]) == 10, "empty payload: ten sections, no chart, no table")
broken = rs.takeaways({"trade_plan": "x", "scoring": 5, "playbook": [1], "early_warning": "y", "sentiment": 3, "options": "z", "heatmap": 1, "newsflash": 2, "backtest": 3, "postmortem": 4})
check(all(v["state"] in ("missing", "error") and v["text"] for v in broken.values()), "wrong types in the payload: takeaways still return a line for every section")
check(page_of({"trade_plan": "x", "scoring": 5, "playbook": [1], "early_warning": "y", "sentiment": 3, "options": "z", "heatmap": 1, "newsflash": 2, "backtest": 3, "postmortem": 4, "news": 5, "technicals": 6}).count("<section") == 10,
      "wrong types in the payload: the sections still build")

# ---- 5 and 6. every stored payload
payloads = load_payloads()
check(len(payloads) >= 2, f"{len(payloads)} stored payloads found (the current data file and the daily snapshots)")
n_missing_opt = n_with_opt = 0
for name, p in payloads:
  problems = audit(p)
  n_missing_opt += rs.options_missing(p)
  n_with_opt += not rs.options_missing(p)
  check(not problems, f"{name}: sections build clean" + ("" if not problems else " | " + " | ".join(problems[:4])))
check(n_with_opt >= 1, f"options content was exercised on {n_with_opt} payloads and the missing line on {n_missing_opt}")

# a payload with an options chain, emptied: the section must fall back to its one line
with_opt = next((p for _, p in payloads if not rs.options_missing(p)), None)
if with_opt is not None:
  q = copy.deepcopy(with_opt)
  q["options"] = {"cboe_spot": q["technicals"]["close"], "total_contracts": 0, "focus_strikes": [], "whale": {}, "forecast": {}, "secondary": {}, "total_net_gex_m": 0.0}
  problems = audit(q)
  check(rs.takeaways(q)["options"] == {"state": "missing", "text": rs.MISSING["options"]} and not problems, "a payload whose options chain is emptied shows the missing line and nothing else" + ("" if not problems else " | " + " | ".join(problems[:3])))
  html_q = page_of(q)
  check("data-block=\"options-scored-blank\"" in html_q and html_q.count('data-blank="1"') >= 1, "with the chain emptied, the scorecard marks the option factors 資料暫缺 and says the model still counts them")

# ---- 7. takeaways change with the data
by_name = dict(payloads)
other = by_name.get("2026-10-27") or next((p for n, p in payloads if n != "current data" and p.get("data_as_of") != payloads[0][1].get("data_as_of")), None)
if other is not None:
  a, b = rs.takeaways(payloads[0][1]), rs.takeaways(other)
  diff = [k for k in rs.SECTION_IDS if a[k]["text"] != b[k]["text"]]
  check(len(diff) >= 3, f"{len(diff)} of 10 takeaways differ between {payloads[0][1].get('data_as_of')} and {other.get('data_as_of')}")

# ---- 8. escaping
EVIL_TITLE = '<script>alert("x")</script><img src=x onerror="alert(1)"> "quoted" \'single\''
EVIL_PUB = '<b onmouseover="alert(2)">pub</b>"'
EVIL_LINK = "javascript:alert(document.domain)"
base = copy.deepcopy(next((p for _, p in payloads if p.get("newsflash") and p.get("news")), payloads[0][1]))
fl = base.setdefault("newsflash", {})
fl.setdefault("label", "偏空")
fl["top"] = [{"title": EVIL_TITLE, "publisher": EVIL_PUB, "link": EVIL_LINK, "time_tpe": "11/23 13:47", "category": "地緣政治", "emoji": "🌍", "impact": -2, "why_zh": EVIL_TITLE} for _ in range(6)]
fl["seeking_alpha"] = [{"title": EVIL_TITLE, "link": EVIL_LINK, "symbol": "SOXL", "kind": "分析", "time_tpe": "11/23", "tone": "偏空", "impact": -1}]
fl["cautions"] = [{"flag": "geo_escalation_24h", "text": EVIL_TITLE, "evidence": {"title": EVIL_TITLE, "publisher": EVIL_PUB}}]
fl["beginner_line"] = "今天最大的事：" + EVIL_TITLE
for d in base.setdefault("news", {}).setdefault("daily_feed", [{"date": "2026-11-20", "bull_count": 1, "bear_count": 1, "net_sentiment_ratio": 0}]):
  d["top_bull_headlines"] = [{"zh_tag": "<i>tag</i>", "title": EVIL_TITLE, "publisher": EVIL_PUB}]
  d["top_bear_headlines"] = [{"zh_tag": "tag", "title": EVIL_TITLE, "publisher": EVIL_PUB}]
html_e = page_of(base)
tree = Tree(html_e)
tags = {n.tag for n in tree.root.walk()}
check(not ({"script", "img"} & tags), "escaping: news text creates no script and no img element")
check(not [n for n in tree.root.walk() if any(k.lower().startswith("on") for k in n.attrs)], "escaping: no event handler attribute")
check("javascript:" not in " ".join((n.attrs.get("href") or "") for n in tree.root.walk() if n.tag == "a").lower() and 'href="javascript' not in html_e.lower(), "escaping: no javascript: link")
check(html_e.count("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;") >= 8 and "<script>alert" not in html_e, "escaping: the script text is shown as text")
shown = [t for t, _ in text_nodes(tree.root) if 'alert("x")' in t]
check(len(shown) >= 8 and all("<script>" in t for t in shown), f"escaping: the reader sees the raw title text in {len(shown)} places")
bad_links = [n for n in tree.root.walk() if n.tag == "a" and not re.match(r"(https?://|#)", n.attrs.get("href") or "", re.I)]
check(not bad_links, "escaping: every link is http(s) or an in-page anchor")

# ---- the page script of the sections uses no HTML sink
check(not re.search(r"innerHTML|outerHTML|document\.write|insertAdjacentHTML|eval\(|new Function", rs.JS), "page script: no innerHTML, outerHTML, document.write, insertAdjacentHTML or eval")

# ---- 9. the whole page
def audit_page(p):
  """Problems of the whole page built from one payload, as a list of strings."""
  out = []
  page = report_page.render(p)
  tree = Tree(page)
  nodes = list(tree.root.walk())
  dis = [n for n in nodes if "data-disclaimer" in n.attrs]
  if len(dis) != 1 or dis[0].text() != brief.DISCLAIMER or page.count(rs.esc(brief.DISCLAIMER)) != 1:
    out.append("the disclaimer of the feed is not on the page exactly once")
  ids = {n.attrs["id"] for n in nodes if n.attrs.get("id")}
  nav = [n for n in nodes if n.tag == "a" and n.inside(attr="data-section-nav")]
  if [n.attrs.get("href") for n in nav] != [f"#sec-{k}" for k in rs.SECTION_IDS] or any(n.attrs["href"][1:] not in ids for n in nav):
    out.append("the section links are not the ten sections in order")
  for n in nodes:
    href = n.attrs.get("href") or ""
    if href.startswith("#") and len(href) > 1 and not href.startswith("#view=") and href[1:] not in ids:
      out.append(f"in-page link {href} has no target")
  for text, n in text_nodes(tree.root):
    if n.inside(attr="data-ext"):
      continue
    m = TOKEN.search(text)
    if m:
      out.append(f"token {m.group(0)!r} on the page: {text.strip()[:60]}")
  texts = {}
  for n in nodes:
    if n.tag in ("script", "style", "#root", "html", "body"):
      continue
    t = n.text()
    if len(t) >= 120 and (n.parent is None or n.parent.text() != t):
      texts.setdefault(t, []).append(n)
  for t, same in texts.items():
    if len(same) > 1:
      out.append(f"text of {len(t)} characters appears {len(same)} times: {t[:40]}")
  csp = next((n.attrs.get("content") or "" for n in nodes if n.tag == "meta" and (n.attrs.get("http-equiv") or "").lower() == "content-security-policy"), "")
  for part in ("default-src 'none'", "connect-src 'none'", "base-uri 'none'", "form-action 'none'", "script-src 'nonce-"):
    if part not in csp:
      out.append(f"the Content-Security-Policy lacks {part}")
  for n in nodes:
    if n.tag == "script" and (not n.attrs.get("nonce") or "src" in n.attrs):
      out.append("a script without a nonce, or with a src")
    if n.tag in ("link", "img", "iframe", "object", "embed", "video", "audio", "source", "base", "form"):
      out.append(f"<{n.tag}> element on the page")
    if n.tag != "a" and re.match(r"\s*(https?:)?//", n.attrs.get("src") or n.attrs.get("href") or "", re.I):
      out.append(f"<{n.tag}> loads from another origin")
    if any(k.lower().startswith("on") for k in n.attrs):
      out.append(f"event handler attribute on <{n.tag}>")
  if re.search(r"@import|url\(\s*['\"]?(?!data:)", " ".join(k for n in nodes if n.tag == "style" for k in n.kids if isinstance(k, str)), re.I):
    out.append("a style rule loads a resource")
  return out


for name, p in payloads[:1] + [x for x in payloads[1:] if x[0] in ("2026-10-27", "2026-11-18")]:
  problems = audit_page(p)
  check(not problems, f"{name}: the whole page builds clean" + ("" if not problems else " | " + " | ".join(problems[:4])))
check(audit_page({}) == [], "empty payload: the whole page builds clean")
files = [REPO / f for f in report_page.PAGE_FILES]
if all(f.exists() for f in files):
  check(len({f.read_bytes() for f in files}) == 1, "the three page files hold the same bytes: " + ", ".join(f.name for f in files))

# ---- 10. the section log names positions that exist, reasons that are allowed, and files that are gone
LOG = REPO / "docs" / "section_log.md"
if LOG.exists():
  union = []   # nodes of the pages built from the current data and from one stored day with an options chain
  for _, p in payloads[:1] + ([("", with_opt)] if with_opt is not None else []):
    union += list(Tree(report_page.render(p)).root.walk())
  folds = {n.attrs["data-fold"] for n in union if n.tag == "details" and "data-fold" in n.attrs}
  secs_on_page = {n.attrs["data-sec"] for n in union if n.tag == "section" and "data-sec" in n.attrs}

  def on_page(tok):
    """True, False, or None when the token is not a marker this test understands."""
    m = re.fullmatch(r"\[?(data-[a-z0-9-]+)(?:=\"([^\"]*)\")?\]?", tok)
    if m:
      return any(m.group(1) in n.attrs and (m.group(2) is None or n.attrs[m.group(1)] == m.group(2)) for n in union)
    if re.fullmatch(r"[a-z]+-\d+", tok):
      return tok in folds
    if tok in rs.SECTION_IDS:
      return tok in secs_on_page
    return None

  rows = []
  for line in LOG.read_text(encoding="utf-8").splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
    if len(cells) == 5 and re.fullmatch(r"[FS]\d+[a-zA-Z]?|F0W", cells[0]):
      rows.append(cells)
  check(len(rows) >= 80, f"section log: {len(rows)} block rows found")
  kept = [r for r in rows if r[2] in ("重建", "合併", "摺疊")]
  removed = [r for r in rows if r[2] == "移除"]
  check(len(kept) + len(removed) == len(rows), "section log: every row has one of the four outcomes")
  missing, unknown, no_pos = [], [], []
  for rid, _title, _res, pos, _why in kept:
    toks = re.findall(r"`([^`]+)`", pos)
    known = [t for t in toks if on_page(t) is not None]
    missing += [f"{rid}:{t}" for t in known if not on_page(t)]
    unknown += [f"{rid}:{t}" for t in toks if on_page(t) is None]
    if not known and not re.search(r"第一屏|組合圖|頁首|頁尾", pos):
      no_pos.append(rid)
  check(not missing, "section log: every position named for a kept block exists on the page" + ("" if not missing else " | missing " + ", ".join(missing[:8])))
  check(not unknown, "section log: every position is written as a marker" + ("" if not unknown else " | not understood " + ", ".join(unknown[:8])))
  check(not no_pos, "section log: every kept block names where it is now" + ("" if not no_pos else " | " + ", ".join(no_pos[:8])))
  bad_reason = [r[0] for r in removed if not re.search(r"重複|空殼|沒有用到", r[4])]
  check(not bad_reason and all(r[3] == "無" for r in removed), "section log: every removal row gives 重複, 空殼 or 沒有用到" + ("" if not bad_reason else " | " + ", ".join(bad_reason)))
  deleted = re.findall(r"^\| `([^`]+)` \| 移除 \| (.*) \|$", LOG.read_text(encoding="utf-8"), re.M)
  check(len(deleted) >= 1 and all(not (REPO / f).exists() and "沒有用到" in why for f, why in deleted), f"section log: the {len(deleted)} deleted files are gone and each row gives the reason")

print("report sections tests:", "ALL PASS" if BAD == 0 else f"{BAD} FAILED")
sys.exit(1 if BAD else 0)
