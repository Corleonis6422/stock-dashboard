#!/usr/bin/env python3
"""News flash — what happened in the last 36 hours that moves SOXL, explained for a beginner.

Why
  The daily bull / bear tally in ``news.py`` answers "what is the mood this week".  A beginner
  (and an agent writing a morning note) also needs "what is the ONE thing that happened overnight
  and what does it mean for a 3x semiconductor ETF": a Trump statement on Iran, an FOMC decision,
  a tariff or export-control headline, a leader's capex cut.  This module ranks those headlines,
  tags each with a category, an impact score (−2 … +2) and a one-line Chinese explanation, and
  raises flags the brief and the trade plan can quote.

How (rule based, no LLM, fully reproducible)
  * sources: Google News RSS searches on ~24 macro / geopolitical / policy / semiconductor topics,
    the Federal Reserve press-release feed, CNBC markets, MarketWatch top stories, and Seeking Alpha's public RSS
    (Wall Street Breakfast, Market Outlook, Macro View, plus the SOXL / SOXX / NVDA symbol feeds; contributor
    articles are tagged 'Seeking Alpha 分析' and weighted below the news desk).  All free, no keys.
  * window: last 36 hours (headline age is part of the ranking).
  * category: first matching trigger list in CATEGORIES (whole-word matching; ``word*`` = prefix stem).
  * impact: category-specific negative / positive phrase lists, clamped to [−2, +2].  Geopolitics and
    policy headlines with more negative than positive phrases are forced to −2 (they hit semis hardest).
  * weight: recency (≤ 12 h 1.0, ≤ 24 h 0.8, else 0.5) × publisher weight (Fed 1.0, wires 0.9, others 0.6).
  * ranking: |impact| × weight, then recency; at most 2 headlines per category in the top list.
  * flags (need a weighted source, weight ≥ 0.7, inside 24 h): fed_statement_24h, geo_escalation_24h,
    tariff_shock_24h, capex_warning_24h, fed_hawkish_24h.  ``flag_evidence`` names the headline.
  * net: weighted mean impact / 2 → label 偏空 / 中性 / 偏多.

Everything here is a reading aid.  It does not change the 24-factor verdict; the trade plan only
quotes the flags as cautions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

from . import datafeed

TPE = ZoneInfo("Asia/Taipei")
WINDOW_H = 36
TOP_N = 8
PER_CATEGORY = 2
MORE_N = 12
FLAG_MIN_WEIGHT = 0.7

GOOGLE_QUERIES = [
    "Iran", "Israel Iran strike", "Taiwan China military", "Russia Ukraine", "oil prices",
    "Trump tariffs", "Trump chips", "semiconductor export controls", "China rare earths", "government shutdown",
    "Federal Reserve", "Powell interest rates", "FOMC decision",
    "inflation report CPI", "jobs report payrolls", "US GDP",
    "Nvidia", "TSMC", "AI capex spending", "chip stocks",
    "stock market futures", "Wall Street selloff", "VIX volatility",
]
RSS_FEEDS = ["fed_press", "cnbc_markets", "marketwatch_top", "sa_wall_street_breakfast", "sa_market_outlook", "sa_macro_view"]
SA_SYMBOLS = ["SOXL", "SOXX", "NVDA"]   # Seeking Alpha per-symbol news + analysis feeds
SA_TAKES_WINDOW_H = 72
SA_TAKES_N = 8

PUBLISHER_WEIGHT = {
    "federal reserve": 1.0, "reuters": 0.9, "bloomberg": 0.9, "the wall street journal": 0.9, "wsj": 0.9, "ap news": 0.9, "associated press": 0.9,
    "cnbc": 0.9, "financial times": 0.9, "the new york times": 0.85, "washington post": 0.85, "marketwatch": 0.8, "barron's": 0.8, "axios": 0.8,
    "politico": 0.75, "bbc": 0.8, "the economist": 0.8, "nikkei": 0.8, "the guardian": 0.75, "the hill": 0.7, "fox business": 0.7,
    "south china morning post": 0.7, "yahoo finance": 0.7, "investing.com": 0.6, "forbes": 0.6, "business insider": 0.6, "investopedia": 0.6,
    "seeking alpha 分析": 0.6, "seeking alpha": 0.8, "the motley fool": 0.5, "benzinga": 0.5, "wccftech": 0.4,
}

# (category, trigger phrases, negative phrases, positive phrases).  ``word*`` matches any continuation
# (hike* = hike / hikes / hiked); everything else is whole-word so "war" no longer matches "software"
# and "dow" no longer matches "down".
CATEGORIES: list[tuple[str, list[str], list[str], list[str]]] = [
    ("聯準會與利率",
     ["fed", "fed's", "federal reserve", "fomc", "powell", "rate cut*", "rate hike*", "interest rate*", "central bank*", "rate decision", "fed official*", "fed chair"],
     ["hike*", "raise* rates", "raising rates", "hawkish", "higher for longer", "no cut", "skip*", "hold* rates", "holds steady", "delay* cut*", "fewer cuts", "inflation worr*", "bad news", "warns", "warning", "pushes back", "pushback", "not ready", "patient", "too soon"],
     ["cut* rates", "rate cut*", "dovish", "pause*", "ease*", "easing", "lower rates", "stimulus", "liquidity", "signals cut*", "open to cut*", "ready to cut*", "emergency cut*", "qe", "ends qt", "end of qt", "stop* balance sheet runoff"]),
    ("政策與關稅",
     ["tariff*", "export control*", "export curb*", "chip ban*", "entity list", "sanction*", "rare earth*", "trade war", "trade deal", "trade talks", "shutdown", "antitrust", "executive order", "chip curb*", "chips act", "export licens*"],
     ["impose*", "new tariff*", "raise* tariff*", "hike*", "100%", "threat*", "ban", "bans", "banned", "curb*", "restrict*", "retaliat*", "shutdown", "halt*", "block*", "probe*", "tighten*", "crackdown", "escalat*", "revoke*", "suspend* license*", "deadline"],
     ["exempt*", "lift*", "remov*", "delay*", "pause*", "roll* back", "rolled back", "trade deal", "reach* a deal", "reached a deal", "agreement", "truce", "approv*", "grant* license*", "ease*", "easing", "reopen*", "ends shutdown", "end the shutdown", "funding bill passes", "signs funding", "relief", "cut* tariff*", "lower* tariff*", "scrap* tariff*"]),
    ("地緣政治",
     ["iran*", "israel*", "tehran", "strait of hormuz", "houthi*", "missile*", "airstrike*", "air strike*", "strike on", "strikes on", "war", "wars", "troops", "military", "taiwan strait", "china taiwan", "taiwan china", "ukrain*", "russia*", "north korea*", "cuba", "attack*", "ceasefire", "cease-fire", "pentagon", "nato"],
     ["strike*", "attack*", "escalat*", "not negotiating", "something will happen", "military intervention", "invasion", "invade*", "blockade", "retaliat*", "warship*", "mobiliz*", "advanced stages", "planning attacks", "killed", "explosion*", "ultimatum", "bomb*", "drone*", "evacuat*", "departure order*", "oil jumps", "oil surges", "oil spikes", "war with", "threat*", "nuclear"],
     ["ceasefire", "cease-fire", "truce", "peace talks", "negotiations resume", "resume* talks", "de-escalat*", "peace deal", "reach* a deal", "reached a deal", "agreement", "withdraw*", "calm", "stand down", "oil falls", "oil drops", "oil slides", "pulls back from", "backs off", "ease* tension*", "easing tension*"]),
    ("半導體與 AI",
     ["nvidia", "nvda", "tsmc", "taiwan semi*", "amd", "micron", "broadcom", "asml", "lam research", "applied materials", "kla", "intel", "qualcomm", "arm holdings", "semiconductor*", "chipmaker*", "chip maker*", "chip manufacturer*", "chip sector", "chip industry", "chip stocks", "chips", "capex", "data center*", "datacenter*", "gpu*", "hbm", "ai spending", "ai bubble", "openai", "meta earnings", "microsoft earnings", "alphabet earnings", "amazon earnings", "hyperscaler*", "soxx", "soxl", "sox index", "philadelphia semiconductor"],
     ["miss", "misses", "missed", "cut* guidance", "weak guidance", "lower* capex", "capex cut*", "cut* capex", "trim* capex", "freeze* capex", "barely raised", "slows", "slowdown", "slowing", "bubble", "overvalued", "downgrade*", "plunge*", "tumble*", "slump*", "delay*", "glut", "oversupply", "cracks", "pullback", "pulls back", "scrap*", "reality check", "default risk", "sell rating", "reiterates sell", "mounting", "didn't", "did not", "backfire*", "burn*", "lose*", "loses", "lost", "losses", "crash*", "selloff", "sell-off", "fall*", "drop*", "sinks", "sink", "warns", "warning", "layoff*", "record low*", "record drop*", "record outflow*", "antitrust", "probe*", "ban", "bans", "banned", "curb*", "restrict*"],
     ["beat", "beats", "raise* guidance", "record high*", "record revenue", "record profit*", "record sales", "record quarter", "record demand", "record order*", "surge*", "soar*", "jump*", "rally", "rallies", "upgrade*", "raise* capex", "boost*", "strong demand", "sold out", "expand*", "invest", "invests", "investment", "investments", "investing", "order", "orders", "deal", "partnership", "breakthrough", "buyback", "approv*", "license granted", "resume* sales", "lifts ban", "lifted ban"]),
    ("經濟數據",
     ["cpi", "pce", "inflation", "jobs report", "payrolls", "unemployment", "gdp", "retail sales", "ism", "pmi", "consumer confidence", "jobless claims", "housing starts", "treasury yield*", "10-year yield*", "bond yield*", "ppi", "nonfarm"],
     ["hotter", "hot", "higher than expected", "jumps", "accelerat*", "sticky", "rises", "rose more", "surge*", "yields jump*", "yields rise", "yields climb*", "spike*", "weak jobs", "layoffs", "contraction", "recession", "misses", "worse than expected", "stagflation", "plunge*"],
     ["cooler", "cools", "cooling", "slows", "lower than expected", "ease*", "easing", "falls", "fell", "yields fall", "yields drop", "yields slip", "soft landing", "beats expectations", "resilient", "in line", "as expected", "steady"]),
    ("市場波動",
     ["futures", "stocks", "stock market", "wall street", "nasdaq", "s&p 500", "s&p", "dow jones", "the dow", "dow futures", "vix", "selloff", "sell-off", "bear market", "market correction", "tech stocks", "megacap*", "big tech", "treasuries", "risk-off", "risk off", "margin call*"],
     ["tumble*", "crushed", "plunge*", "slide*", "sink*", "sank", "selloff", "sell-off", "rout", "fall*", "fell", "drop*", "spike*", "fear*", "jitters", "correction", "bear market", "worst", "slump*", "losses", "lose*", "loses", "lost", "dump*", "crash*", "wipe* out", "haunt*", "pressure", "retreat*", "pull* back", "pullback", "bubble", "credit fears", "margin call*"],
     ["rally", "rallies", "rallied", "rebound*", "surge*", "jump*", "gain*", "record high*", "all-time high*", "relief", "best", "climb*", "rise*", "soar*", "recover*", "bounce*", "advance*", "higher"]),
]
AMPLIFY_NEGATIVE = ("地緣政治", "政策與關稅")
CATEGORY_EMOJI = {"聯準會與利率": "🏦", "政策與關稅": "🏛️", "地緣政治": "🌍", "半導體與 AI": "🔧", "經濟數據": "📊", "市場波動": "📉"}
WHY = {
    ("聯準會與利率", -1): "聯準會偏鷹（升息、延後降息、利率維持高檔）：殖利率上升壓縮高估值成長股，半導體首當其衝。",
    ("聯準會與利率", 1): "聯準會偏鴿（降息、暫停、放鬆）：殖利率回落，成長股與半導體最受惠。",
    ("聯準會與利率", 0): "聯準會相關但方向未定：留意會後聲明與記者會措辭。",
    ("政策與關稅", -1): "關稅或出口管制收緊：半導體供應鏈首當其衝（NVDA、AMAT、LRCX 的中國營收），SOXL 的跌幅通常是 SOXX 的 3 倍。",
    ("政策與關稅", 1): "關稅或管制放寬 / 達成協議：供應鏈壓力解除，半導體常領漲。",
    ("政策與關稅", 0): "政策面消息，方向未定：看實際條文與生效日。",
    ("地緣政治", -1): "地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。",
    ("地緣政治", 1): "地緣降溫：風險偏好回升，半導體與 SOXL 常是最先反彈的一群。",
    ("地緣政治", 0): "地緣新聞，尚未升級為市場事件：盯油價與 VIX 就夠。",
    ("半導體與 AI", -1): "龍頭財報、訂單或資本支出轉弱：AI 資本支出是這輪半導體行情的核心，轉弱會壓低整個 SOXX。",
    ("半導體與 AI", 1): "龍頭財報、訂單或資本支出轉強：直接推升 SOXX 成分股。",
    ("半導體與 AI", 0): "半導體產業消息，方向中性：記下來但不用動作。",
    ("經濟數據", -1): "數據偏熱或通膨黏著：市場把降息往後推、殖利率上升，對成長股不利。",
    ("經濟數據", 1): "數據降溫：降息預期升高、殖利率回落，對成長股有利。",
    ("經濟數據", 0): "經濟數據公布，方向中性：看殖利率怎麼反應。",
    ("市場波動", -1): "整體風險偏好惡化：SOXL 的 Beta 約是大盤的 3 到 4 倍，大盤跌 1% 它常跌 3% 以上。",
    ("市場波動", 1): "整體風險偏好改善：大盤反彈時 SOXL 的彈幅也放大。",
    ("市場波動", 0): "大盤消息，方向中性。",
}
CAUTIONS = {
    "geo_escalation_24h": "地緣風險 24 小時內升溫：進場前先看開盤 30 分鐘與 VIX/VIX3M，倒掛（≥ 1.0）就不進。",
    "tariff_shock_24h": "關稅 / 出口管制收緊：半導體是直接受害者，當天的反彈單勝率沒有歷史依據，寧可晚一天。",
    "capex_warning_24h": "有龍頭下修或凍結資本支出：這是這輪半導體行情的核心假設鬆動，計畫的 T1 / T2 當作減碼點而非目標。",
    "fed_statement_24h": "聯準會剛公布決議：記者會後一小時的方向常反轉，不在決議日追價。",
    "fed_hawkish_24h": "聯準會偏鷹的消息在 24 小時內：殖利率若續升，成長股反彈空間受限。",
}
NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")
STEM = "*"


def _compile(phrases: list[str]) -> list[tuple[str, re.Pattern]]:
  """``*`` anywhere in a phrase means "any word continuation": ``cut* rates`` matches "cuts rates",
  ``hike*`` matches hike / hikes / hiked.  Whole-word boundaries are applied at both ends otherwise."""
  out = []
  for ph in phrases:
    stem = ph.endswith(STEM)
    p = ph[:-1] if stem else ph
    body = r"\w*".join(re.escape(part) for part in p.split(STEM))
    pat = (r"\b" if p[0].isalnum() else "") + body
    if not stem and p[-1].isalnum():
      pat += r"\b"
    out.append((p.replace(STEM, ""), re.compile(pat)))
  return out


COMPILED = [(cat, _compile(trig), _compile(neg), _compile(pos)) for cat, trig, neg, pos in CATEGORIES]


def _norm(title: str) -> str:
  t = (title or "").lower().replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
  return " " + re.sub(r"\s+", " ", t).strip() + " "


def _matches(compiled: list[tuple[str, re.Pattern]], t: str) -> list[str]:
  """Phrases found in ``t``; a phrase contained in another matched phrase is dropped (no double count)."""
  found = [p for p, rx in compiled if rx.search(t)]
  return [p for p in found if not any(p != q and p in q for q in found)]


def _pub_weight(publisher: str) -> float:
  p = (publisher or "").strip().lower()
  for k, w in PUBLISHER_WEIGHT.items():
    if k in p:
      return w
  return 0.6


def classify(title: str) -> tuple[str | None, int]:
  """Return (category, impact −2..+2) or (None, 0) when no category triggers."""
  t = _norm(title)
  for cat, trig, neg, pos in COMPILED:
    if not _matches(trig, t):
      continue
    n = len(_matches(neg, t))
    p = len(_matches(pos, t))
    raw = p - n
    if n > p and cat in AMPLIFY_NEGATIVE:
      impact = -2  # these two families hit semiconductors hardest; a net-negative headline is a full-size warning
    elif raw == 0 and n:
      impact = -1 if cat == "地緣政治" else 0  # mixed geopolitics wording still reads risk-off; mixed policy wording is undecided
    else:
      impact = raw
    return cat, max(-2, min(2, impact))
  return None, 0


def _recency_weight(age_h: float) -> float:
  return 1.0 if age_h <= 12 else (0.8 if age_h <= 24 else 0.5)


def _dedupe_key(title: str) -> str:
  words = NORMALIZE_RE.sub(" ", title.lower()).split()
  return " ".join(words[:7])


def _fetch(errors: list[str]) -> list[dict]:
  raw: list[dict] = []
  for q in GOOGLE_QUERIES:
    try:
      raw += [dict(it, source=f"google:{q}") for it in datafeed.fetch_google_news(q)]
    except Exception as e:  # noqa: BLE001
      errors.append(f"google:{q}: {e}")
  for src in RSS_FEEDS:
    try:
      raw += [dict(it, source=src) for it in datafeed.fetch_rss(src)]
    except Exception as e:  # noqa: BLE001
      errors.append(f"{src}: {e}")
  for sym in SA_SYMBOLS:
    try:
      raw += [dict(it, source=f"sa_symbol:{sym}", symbol=sym) for it in datafeed.fetch_rss("seekingalpha_symbol", sym)]
    except Exception as e:  # noqa: BLE001
      errors.append(f"sa_symbol:{sym}: {e}")
  for it in raw:  # Seeking Alpha: contributor articles (/article/) are opinion → lighter weight than the news desk
    if str(it.get("source", "")).startswith("sa_") and "/article/" in str(it.get("link") or ""):
      it["publisher"] = "Seeking Alpha 分析"
    elif str(it.get("source", "")).startswith("sa_"):
      it["publisher"] = "Seeking Alpha"
  return raw


def _sa_takes(raw: list[dict], now_ts: float) -> list[dict]:
  """Latest Seeking Alpha items on SOXL / SOXX / NVDA (news desk + contributor analysis), newest first, de-duplicated."""
  out, seen = [], set()
  for it in sorted((x for x in raw if str(x.get("source", "")).startswith("sa_symbol:")), key=lambda x: -(x.get("timestamp") or 0)):
    ts = it.get("timestamp") or 0
    if ts < now_ts - SA_TAKES_WINDOW_H * 3600:
      continue
    key = _dedupe_key(it.get("title") or "")
    if not key or key in seen:
      continue
    seen.add(key)
    cat, impact = classify(it.get("title") or "")
    out.append({"title": it.get("title"), "link": it.get("link"), "symbol": it.get("symbol"), "kind": ("分析" if it.get("publisher") == "Seeking Alpha 分析" else "新聞"),
                "time_tpe": datetime.fromtimestamp(ts, tz=TPE).strftime("%m/%d %H:%M"), "age_h": round(max(0.0, (now_ts - ts) / 3600.0), 1),
                "category": cat, "impact": impact, "tone": ("利空" if impact < 0 else ("利多" if impact > 0 else "中性"))})
    if len(out) >= SA_TAKES_N:
      break
  return out


def _public(r: dict) -> dict:
  return {k: r[k] for k in ("title", "publisher", "link", "time_tpe", "age_h", "category", "emoji", "impact", "why_zh")}


def analyze(now: datetime | None = None, window_h: int = WINDOW_H, raw: list[dict] | None = None) -> dict:
  """Rank the last ``window_h`` hours of headlines.  ``raw`` lets tests inject items (no network)."""
  now = now or datetime.now(timezone.utc)
  cutoff = now.timestamp() - window_h * 3600
  errors: list[str] = []
  if raw is None:
    raw = _fetch(errors)
  seen: dict[str, dict] = {}
  for it in raw:
    ts = it.get("timestamp") or 0
    title = (it.get("title") or "").strip()
    if not title or ts < cutoff or ts > now.timestamp() + 3600:
      continue
    cat, impact = classify(title)
    if cat is None:
      continue
    key = _dedupe_key(title)
    age_h = max(0.0, (now.timestamp() - ts) / 3600.0)
    pub = it.get("publisher") or ("Federal Reserve" if it.get("source") == "fed_press" else "")
    w = _recency_weight(age_h) * _pub_weight(pub)
    rec = {"title": title, "publisher": pub, "link": it.get("link"), "timestamp": ts,
           "time_tpe": datetime.fromtimestamp(ts, tz=TPE).strftime("%m/%d %H:%M"), "age_h": round(age_h, 1),
           "category": cat, "emoji": CATEGORY_EMOJI.get(cat, ""), "impact": impact, "weight": round(w, 2),
           "rank_score": round(abs(impact) * w + (0.1 if impact else 0) * w, 3),
           "why_zh": WHY.get((cat, (impact > 0) - (impact < 0)), ""), "source": it.get("source")}
    prev = seen.get(key)
    if prev is None or rec["rank_score"] > prev["rank_score"] or (rec["rank_score"] == prev["rank_score"] and ts > prev["timestamp"]):
      seen[key] = rec
  items = sorted(seen.values(), key=lambda r: (-r["rank_score"], -r["timestamp"]))
  top: list[dict] = []
  top_ids: set[int] = set()
  per_cat: dict[str, int] = {}
  for pass_major in (True, False):  # pass 1: weighted publishers only; pass 2: fill up if fewer than 4 made it
    if not pass_major and len(top) >= 4:
      break
    for r in items:
      if id(r) in top_ids or per_cat.get(r["category"], 0) >= PER_CATEGORY:
        continue
      if pass_major and _pub_weight(r["publisher"]) < FLAG_MIN_WEIGHT:
        continue
      top.append(r)
      top_ids.add(id(r))
      per_cat[r["category"]] = per_cat.get(r["category"], 0) + 1
      if len(top) >= TOP_N:
        break
  more = [r for r in items if id(r) not in top_ids and r["impact"]][:MORE_N]
  by_cat: dict[str, dict] = {}
  for r in items:
    c = by_cat.setdefault(r["category"], {"category": r["category"], "emoji": r["emoji"], "n": 0, "neg": 0, "pos": 0})
    c["n"] += 1
    c["neg"] += r["impact"] < 0
    c["pos"] += r["impact"] > 0
  wsum = sum(r["weight"] for r in items if r["impact"]) or 0.0
  net = round(sum(r["impact"] * r["weight"] for r in items) / (2.0 * wsum), 2) if wsum else 0.0
  label = "偏空" if net <= -0.25 else ("偏多" if net >= 0.25 else "中性")
  recent = [r for r in items if r["age_h"] <= 24 and r["weight"] >= FLAG_MIN_WEIGHT]

  def first(pred):
    for r in recent:
      if pred(r):
        return r
    return None

  fed_words = ("fomc statement", "federal reserve issues fomc", "fomc", "federal open market committee")
  evidence = {
      "fed_statement_24h": first(lambda r: r["source"] == "fed_press" and any(k in r["title"].lower() for k in fed_words)),
      "geo_escalation_24h": first(lambda r: r["category"] == "地緣政治" and r["impact"] <= -2),
      "tariff_shock_24h": first(lambda r: r["category"] == "政策與關稅" and r["impact"] <= -2),
      "capex_warning_24h": first(lambda r: r["category"] == "半導體與 AI" and r["impact"] < 0 and "capex" in r["title"].lower()),
      "fed_hawkish_24h": first(lambda r: r["category"] == "聯準會與利率" and r["impact"] < 0),
  }
  flags = {k: v is not None for k, v in evidence.items()}
  flag_evidence = {k: {"title": v["title"], "publisher": v["publisher"], "time_tpe": v["time_tpe"]} for k, v in evidence.items() if v}
  cautions = [{"flag": k, "text": CAUTIONS[k], "evidence": flag_evidence[k]} for k in ("geo_escalation_24h", "tariff_shock_24h", "capex_warning_24h", "fed_statement_24h", "fed_hawkish_24h") if flags[k]]
  top1 = top[0] if top else None
  beginner = (f"今天最大的事：{top1['title']}（{top1['publisher']}，{top1['time_tpe']} 台北）→ {top1['emoji']} {top1['category']}，對 SOXL {'利空' if top1['impact'] < 0 else ('利多' if top1['impact'] > 0 else '中性')}：{top1['why_zh']}"
              if top1 else "過去 36 小時沒有抓到會影響半導體方向的大新聞。")
  return {
      "as_of_utc": now.strftime("%Y-%m-%d %H:%M"), "fetched_at_tpe": now.astimezone(TPE).strftime("%Y-%m-%d %H:%M"), "window_h": window_h,
      "n_candidates": len(raw), "n_relevant": len(items), "net": net, "label": label,
      "top": [_public(r) for r in top], "more": [_public(r) for r in more],
      "by_category": sorted(by_cat.values(), key=lambda c: -c["n"]), "flags": flags, "flag_evidence": flag_evidence,
      "cautions": cautions, "beginner_line": beginner,
      "seeking_alpha": _sa_takes(raw, now.timestamp()),
      "sources": {"google_queries": len(GOOGLE_QUERIES), "rss": RSS_FEEDS, "seeking_alpha_symbols": SA_SYMBOLS}, "errors": errors[:5],
      "method": "Google News RSS 搜尋 + Fed 新聞稿 + CNBC / MarketWatch + Seeking Alpha（Wall Street Breakfast、Market Outlook、Macro View、SOXL / SOXX / NVDA 個股）；關鍵字分類（整字比對，非 LLM）；影響分 −2…+2；排序 = |影響| × 新鮮度 × 來源權重；每類最多 2 則；旗標需 24 小時內且來源權重 ≥ 0.7。",
  }
