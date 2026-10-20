#!/usr/bin/env python3
"""Daily bullish vs bearish news classification for the semiconductor complex.

Headlines are pulled from Yahoo Finance search for SOXL plus the main
constituents, de-duplicated, keyword-classified into bullish / bearish /
neutral with a Chinese theme tag, and grouped by calendar day.  Each day is
paired with the realised SOXL / VIX / 10Y / Brent moves so readers can see
which narrative actually moved the market.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import datafeed
from . import indicators as ind

QUERIES = ["SOXL", "NVDA", "AVGO", "AMD", "MU", "TSM", "AMAT", "LRCX", "MRVL", "INTC", "QCOM", "semiconductor stocks"]

BULL_KW = [
    "surge", "soar", "jump", "rally", "rebound", "record high", "all-time high", "beats", "beat estimates", "raises guidance",
    "upgrade", "upgraded", "buy rating", "outperform", "strong demand", "demand surge", "wins", "contract", "deal", "partnership",
    "expands", "investment", "invests", "commits", "boost", "boosts", "bullish", "buy the dip", "oversold bounce", "recover",
    "recovers", "gains", "climbs", "rises", "higher", "top pick", "breakout", "tailwind", "accelerat", "approval", "backlog",
    "sold out", "capacity", "hbm", "ai demand", "capex", "stimulus", "rate cut", "cools", "eases", "yields fall", "oil slips",
]
BEAR_KW = [
    "plunge", "plunges", "tumble", "tumbles", "slump", "slumps", "sink", "sinks", "crash", "selloff", "sell-off", "rout", "drop",
    "drops", "falls", "fell", "slide", "slides", "lower", "downgrade", "downgraded", "cuts guidance", "misses", "miss",
    "warning", "warns", "fears", "fear", "concern", "concerns", "jitters", "risk", "risks", "bubble", "overvalued", "valuation",
    "export curbs", "export controls", "tariff", "tariffs", "ban", "probe", "antitrust", "lawsuit", "layoffs", "insider sold",
    "sells", "dumps", "scraps", "halts", "delay", "delays", "debt", "yields rise", "yields jump", "yield spike", "inflation",
    "hawkish", "oil surges", "oil jumps", "recession", "margin call", "liquidation", "wipes", "wiped", "loses", "lost",
    "bear market", "correction", "capitulation", "panic", "worst day", "worst week",
]
MACRO_KW = ["yield", "yields", "treasury", "fed", "fomc", "inflation", "cpi", "oil", "brent", "tariff", "dollar", "rates"]


def classify(title: str) -> tuple[str, str]:
  t = title.lower()
  b = sum(1 for k in BULL_KW if k in t)
  s = sum(1 for k in BEAR_KW if k in t)
  macro = any(k in t for k in MACRO_KW)
  if b > s:
    if macro:
      return "bullish", "宏觀緩和利多"
    if any(k in t for k in ("deal", "contract", "partnership", "invest", "commits", "capacity", "fab", "expands")):
      return "bullish", "訂單/資本支出利多"
    if any(k in t for k in ("upgrade", "buy rating", "top pick", "outperform")):
      return "bullish", "分析師升評利多"
    return "bullish", "個股動能/買盤利多"
  if s > b:
    if macro:
      return "bearish", "殖利率/通膨/關稅宏觀利空"
    if any(k in t for k in ("insider sold", "sells", "dumps", "exited")):
      return "bearish", "內部人/機構減持"
    if any(k in t for k in ("bubble", "overvalued", "valuation", "debt", "ipo", "scraps")):
      return "bearish", "AI 估值/融資疑慮"
    if any(k in t for k in ("export", "ban", "probe", "antitrust", "lawsuit")):
      return "bearish", "監管/地緣政治"
    return "bearish", "獲利了結/基本面利空"
  return "neutral", "產業觀點/市場焦點"


GOOGLE_QUERIES = [
    "semiconductor stocks", "chip stocks selloff", "Nvidia stock", "AMD stock", "Micron stock", "Broadcom stock",
    "SOXL ETF", "Philadelphia Semiconductor Index", "AI stocks bubble", "Treasury yields stocks", "Fed rate stocks",
]


def analyze(soxl_rows: list[dict], vix_rows: list[dict], tnx_rows: list[dict] | None, brent_rows: list[dict] | None, days: int = 14) -> dict:
  seen = {}
  sources = {"yahoo": 0, "google": 0}

  def ingest(items: list[dict], src: str) -> None:
    for n in items:
      key = n["title"].strip().lower()
      if not key or key in seen or not n.get("timestamp"):
        continue
      sent, tag = classify(n["title"])
      ts = n["timestamp"]
      seen[key] = {**n, "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
                   "time": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M"), "sentiment": sent, "zh_tag": tag, "source": src}
      sources[src] += 1

  for q in QUERIES:
    try:
      ingest(datafeed.fetch_yahoo_news(q, 25), "yahoo")
    except Exception:  # noqa: BLE001
      pass
  for q in GOOGLE_QUERIES:
    try:
      ingest(datafeed.fetch_google_news(q), "google")
    except Exception:  # noqa: BLE001
      pass
  items = sorted(seen.values(), key=lambda x: -x["timestamp"])

  def perf_map(rows: list[dict] | None) -> dict:
    out = {}
    if not rows:
      return out
    for i in range(1, len(rows)):
      out[rows[i]["date"]] = (rows[i]["close"], ind.pct_change(rows[i]["close"], rows[i - 1]["close"]))
    return out

  soxl_p, vix_p, tnx_p, brent_p = perf_map(soxl_rows), perf_map(vix_rows), perf_map(tnx_rows), perf_map(brent_rows)
  bucket = {"bullish": "bull", "bearish": "bear", "neutral": "neutral"}
  by_day: dict[str, dict] = {}
  for it in items:
    if not it["date"]:
      continue
    d = by_day.setdefault(it["date"], {"date": it["date"], "bull": [], "bear": [], "neutral": []})
    d[bucket[it["sentiment"]]].append(it)
  feed = []
  for d in sorted(by_day, reverse=True)[:days]:
    e = by_day[d]
    nb, ns = len(e["bull"]), len(e["bear"])
    sp, vp, tp, bp = soxl_p.get(d), vix_p.get(d), tnx_p.get(d), brent_p.get(d)
    feed.append({
        "date": d, "bull_count": nb, "bear_count": ns, "neutral_count": len(e["neutral"]),
        "net_sentiment_ratio": round((nb - ns) / max(1, nb + ns), 2),
        "soxl_perf": f"${sp[0]:.2f} ({sp[1]:+.2f}%)" if sp else "非交易日 / 尚未收盤",
        "soxl_ret": round(sp[1], 2) if sp else None,
        "vix_perf": f"{vp[0]:.2f} ({vp[1]:+.1f}%)" if vp else "",
        "tnx_perf": f"{tp[0]:.3f}%" if tp else "",
        "brent_perf": f"${bp[0]:.2f} ({bp[1]:+.1f}%)" if bp else "",
        "top_bull_headlines": [{k: h[k] for k in ("time", "query", "publisher", "title", "zh_tag", "link")} for h in e["bull"][:6]],
        "top_bear_headlines": [{k: h[k] for k in ("time", "query", "publisher", "title", "zh_tag", "link")} for h in e["bear"][:6]],
        "top_neutral_headlines": [{k: h[k] for k in ("time", "query", "publisher", "title", "zh_tag", "link")} for h in e["neutral"][:3]],
    })
  recent = [f for f in feed[:7]]
  rb, rs = sum(f["bull_count"] for f in recent), sum(f["bear_count"] for f in recent)
  # Theme tally (last 7 days)
  themes: dict[str, int] = {}
  for f in recent:
    for h in f["top_bull_headlines"] + f["top_bear_headlines"]:
      themes[h["zh_tag"]] = themes.get(h["zh_tag"], 0) + 1
  return {
      "total_unique_articles": len(items), "sources": sources, "recent_bull_count": rb, "recent_bear_count": rs,
      "bull_bear_ratio": round(rb / rs, 2) if rs else None,
      "themes_7d": sorted(({"tag": k, "count": v} for k, v in themes.items()), key=lambda x: -x["count"]),
      "daily_feed": feed,
  }
