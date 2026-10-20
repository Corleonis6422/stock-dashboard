#!/usr/bin/env python3
"""Market-pulse sentiment indicators favoured by professional desks and retail
communities (r/wallstreetbets, r/options, r/stocks):

  * CNN Fear & Greed Index (composite + 7 components, 1-year history)
  * VIX complex from official CBOE data: VIX, VIX9D, VIX3M, VIX6M, VIX1D,
    VVIX (vol-of-vol) and SKEW (tail-risk) + term-structure (contango /
    backwardation) state
  * CBOE market-wide put/call ratios (total / equity / index / SPX / VIX)
  * SOXL vs SOXS leveraged-ETF volume ratio (retail dip-buying / capitulation)
  * Cross-asset risk appetite: HYG (junk) vs TLT (safe haven), DXY, copper/gold,
    Bitcoin, MOVE (bond volatility)

Outputs a single 0-100 "Market Pulse" score (0 = extreme fear, 100 = extreme
greed) plus plain-language readings for each gauge.
"""

from __future__ import annotations

from datetime import datetime, timezone
import statistics

from . import datafeed
from . import indicators as ind


def _ts_to_date(ms: float) -> str:
  return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
  return max(lo, min(hi, v))


def _rating(score: float) -> str:
  if score < 25:
    return "極度恐懼 Extreme Fear"
  if score < 45:
    return "恐懼 Fear"
  if score <= 55:
    return "中性 Neutral"
  if score <= 75:
    return "貪婪 Greed"
  return "極度貪婪 Extreme Greed"


# --------------------------------------------------------------------------- #
# CNN Fear & Greed
# --------------------------------------------------------------------------- #
FG_COMPONENTS = {
    "market_momentum_sp500": "S&P 500 動能 (vs 125 日均線)",
    "stock_price_strength": "創 52 週新高 vs 新低家數",
    "stock_price_breadth": "上漲 vs 下跌成交量 (McClellan)",
    "put_call_options": "5 日 Put/Call 比率",
    "market_volatility_vix": "VIX 波動率 (vs 50 日均線)",
    "junk_bond_demand": "垃圾債需求 (信用利差)",
    "safe_haven_demand": "避險需求 (股票 vs 債券 20 日報酬)",
}


def cnn_fear_greed() -> dict | None:
  raw = datafeed.fetch_cnn_fear_greed()
  if not raw:
    return None
  comp = raw.get("fear_and_greed", {})
  hist = [
      {"date": _ts_to_date(p["x"]), "score": round(float(p["y"]), 1), "rating": p.get("rating", "")}
      for p in raw.get("fear_and_greed_historical", {}).get("data", [])
      if p.get("y") is not None
  ]
  components = []
  comp_hist: dict[str, list[dict]] = {}
  for key, label in FG_COMPONENTS.items():
    sub = raw.get(key, {})
    if not sub:
      continue
    # NOTE: the per-component "data" arrays carry the *raw* metric (e.g. S&P level,
    # net new highs, McClellan volume), not the 0-100 rating; keep them as raw.
    series = [{"date": _ts_to_date(p["x"]), "raw": round(float(p["y"]), 2)} for p in sub.get("data", []) if p.get("y") is not None]
    comp_hist[key] = series[-60:]
    components.append({
        "key": key, "label": label, "score": round(float(sub.get("score") or 0.0), 1),
        "rating": str(sub.get("rating", "")),
    })
  score = float(comp.get("score") or 0.0)
  return {
      "score": round(score, 1), "rating": str(comp.get("rating", "")), "rating_zh": _rating(score),
      "timestamp": comp.get("timestamp"),
      "previous_close": round(float(comp.get("previous_close") or 0.0), 1),
      "week_ago": round(float(comp.get("previous_1_week") or 0.0), 1),
      "month_ago": round(float(comp.get("previous_1_month") or 0.0), 1),
      "year_ago": round(float(comp.get("previous_1_year") or 0.0), 1),
      "components": components, "history": hist, "component_history": comp_hist,
  }


# --------------------------------------------------------------------------- #
# VIX complex (official CBOE CSV)
# --------------------------------------------------------------------------- #
def vix_complex() -> dict:
  series = {}
  for name in ("VIX", "VIX9D", "VIX3M", "VIX6M", "VIX1D", "VVIX", "SKEW"):
    try:
      series[name] = datafeed.fetch_cboe_index_history(name)
    except Exception:  # noqa: BLE001
      series[name] = []
  vix = series["VIX"]
  if not vix:
    return {"available": False}
  by = {k: {r["date"]: r["close"] for r in v} for k, v in series.items()}
  dates = [r["date"] for r in vix]
  latest_d = dates[-1]

  def last(name: str) -> float | None:
    s = series.get(name) or []
    return s[-1]["close"] if s else None

  def at(name: str, d: str) -> float | None:
    return by.get(name, {}).get(d)

  vix_closes = [r["close"] for r in vix]
  vix_1y = vix_closes[-252:]
  sma50 = ind.sma(vix_closes, 50)[-1]
  v, v9, v3, v6, v1 = last("VIX"), last("VIX9D"), last("VIX3M"), last("VIX6M"), last("VIX1D")
  vvix, skew = last("VVIX"), last("SKEW")
  ratio_9d_3m = (v9 / v3) if (v9 and v3) else None
  ratio_vix_3m = (v / v3) if (v and v3) else None
  if ratio_vix_3m is None:
    term_state, term_zh = "n/a", "無資料"
  elif ratio_vix_3m >= 1.05:
    term_state, term_zh = "backwardation", "倒掛 (近月恐慌 > 遠月)：恐慌高峰常伴隨短線底部，但趨勢仍脆弱"
  elif ratio_vix_3m >= 0.95:
    term_state, term_zh = "flat", "平坦：市場由自滿轉為警戒，是回檔前常見的『警訊區』"
  else:
    term_state, term_zh = "contango", "正價差 (遠月 > 近月)：常態、風險偏好穩定"

  vix_pct_1y = ind.percentile_rank(vix_1y, v)
  vix_5d_chg = ind.pct_change(v, vix_closes[-6]) if len(vix_closes) > 6 else 0.0
  vix_hi_5d = max((r.get("high") or r["close"]) for r in vix[-5:])

  # Daily derived history (last 260 days) for charts / backtests
  hist = []
  for d in dates[-260:]:
    r9, r3 = at("VIX9D", d), at("VIX3M", d)
    hist.append({
        "date": d, "vix": at("VIX", d), "vix9d": r9, "vix3m": r3, "vvix": at("VVIX", d), "skew": at("SKEW", d),
        "ratio_vix_3m": round(at("VIX", d) / r3, 3) if (r3 and at("VIX", d)) else None,
    })

  def regime_vix(x: float) -> str:
    if x < 13: return "極度自滿 (<13)"
    if x < 16: return "低波平穩 (13-16)"
    if x < 20: return "溫和警戒 (16-20)"
    if x < 25: return "恐慌升溫 (20-25)"
    if x < 35: return "高度恐慌 (25-35)"
    return "極端恐慌 (>35)"

  return {
      "available": True, "date": latest_d,
      "vix": v, "vix9d": v9, "vix3m": v3, "vix6m": v6, "vix1d": v1, "vvix": vvix, "skew": skew,
      "vix_sma50": round(sma50, 2) if sma50 else None,
      "vix_vs_sma50_pct": round(ind.pct_change(v, sma50), 1) if sma50 else None,
      "vix_percentile_1y": round(vix_pct_1y, 0), "vix_5d_chg_pct": round(vix_5d_chg, 1),
      "vix_intraday_high_5d": round(vix_hi_5d, 2),
      "ratio_vix_3m": round(ratio_vix_3m, 3) if ratio_vix_3m else None,
      "ratio_9d_3m": round(ratio_9d_3m, 3) if ratio_9d_3m else None,
      "term_state": term_state, "term_zh": term_zh, "vix_regime": regime_vix(v),
      "vvix_regime": ("壓力 (>110)" if (vvix or 0) > 110 else ("偏高 (95-110)" if (vvix or 0) > 95 else "平穩 (<95)")),
      "skew_regime": ("極高尾部風險定價 (>150)" if (skew or 0) > 150 else ("偏高 (135-150)" if (skew or 0) > 135 else "正常 (<135)")),
      "history": hist,
  }


# --------------------------------------------------------------------------- #
# CBOE market-wide put/call
# --------------------------------------------------------------------------- #
def cboe_put_call() -> dict:
  hist = datafeed.fetch_cboe_pc_history(60)
  if not hist:
    return {"available": False}
  latest = hist[-1]

  def avg(key: str, n: int) -> float | None:
    vals = [h[key] for h in hist[-n:] if h.get(key) is not None]
    return round(statistics.mean(vals), 3) if vals else None

  eq = latest.get("equity_pc")
  eq_read = ("散戶恐慌/投降 (>0.85)" if (eq or 0) >= 0.85 else ("偏防禦 (0.70-0.85)" if (eq or 0) >= 0.70 else
             ("中性 (0.55-0.70)" if (eq or 0) >= 0.55 else "自滿/追多 (<0.55)")))
  tot = latest.get("total_pc")
  tot_read = ("避險極重 (>1.1)" if (tot or 0) >= 1.1 else ("偏避險 (0.9-1.1)" if (tot or 0) >= 0.9 else
              ("中性 (0.75-0.9)" if (tot or 0) >= 0.75 else "偏樂觀 (<0.75)")))
  return {
      "available": True, "date": latest["date"],
      "total_pc": tot, "equity_pc": eq, "index_pc": latest.get("index_pc"),
      "spx_pc": latest.get("spx_pc"), "vix_pc": latest.get("vix_pc"), "etp_pc": latest.get("etp_pc"),
      "total_pc_5d": avg("total_pc", 5), "equity_pc_5d": avg("equity_pc", 5),
      "total_pc_20d": avg("total_pc", 20), "equity_pc_20d": avg("equity_pc", 20),
      "equity_pc_percentile": round(ind.percentile_rank([h["equity_pc"] for h in hist if h.get("equity_pc")], eq), 0) if eq else None,
      "equity_read": eq_read, "total_read": tot_read, "history": hist,
  }


# --------------------------------------------------------------------------- #
# Leveraged-ETF flows & cross-asset risk appetite
# --------------------------------------------------------------------------- #
def leveraged_flows(soxl_rows: list[dict]) -> dict:
  try:
    soxs = datafeed.fetch_history("SOXS", "1y")
  except Exception:  # noqa: BLE001
    return {"available": False}
  s_by = {r["date"]: r for r in soxs}
  hist = []
  for r in soxl_rows[-120:]:
    s = s_by.get(r["date"])
    if not s:
      continue
    dv_l = r["close"] * r["volume"]
    dv_s = s["close"] * s["volume"]
    hist.append({"date": r["date"], "soxl_dollar_vol_m": round(dv_l / 1e6, 1), "soxs_dollar_vol_m": round(dv_s / 1e6, 1),
                 "ratio": round(dv_l / dv_s, 2) if dv_s else None, "soxl_close": r["close"], "soxs_close": s["close"]})
  if not hist:
    return {"available": False}
  ratios = [h["ratio"] for h in hist if h["ratio"]]
  latest = hist[-1]
  avg20 = statistics.mean(ratios[-20:]) if len(ratios) >= 5 else ratios[-1]
  read = ("散戶瘋狂抄底 (SOXL 資金 >> SOXS)" if latest["ratio"] > avg20 * 1.3 else
          ("放空/避險需求升溫 (SOXS 資金增加)" if latest["ratio"] < avg20 * 0.7 else "多空資金均衡"))
  return {"available": True, "latest": latest, "ratio_avg20": round(avg20, 2), "read": read, "history": hist}


def cross_asset_risk() -> dict:
  out = {"available": True, "assets": []}
  specs = [
      ("HYG", "HYG 高收益債 (風險偏好)", "1y", "price"),
      ("TLT", "TLT 20年期美債 (避險)", "1y", "price"),
      ("DX-Y.NYB", "美元指數 DXY", "1y", "price"),
      ("HG=F", "銅期貨 (景氣)", "1y", "price"),
      ("GC=F", "黃金期貨 (避險)", "1y", "price"),
      ("BTC-USD", "比特幣 (風險偏好溫度計)", "1y", "price"),
      ("^MOVE", "MOVE 債券波動率", "1y", "level"),
  ]
  closes_map = {}
  for sym, label, rng, kind in specs:
    try:
      rows, proxy_label = datafeed.fetch_history_with_proxy(sym, rng)
      if proxy_label:
        label = proxy_label
    except Exception:  # noqa: BLE001
      out["assets"].append({"symbol": sym, "label": label, "available": False})
      continue
    c = [r["close"] for r in rows]
    closes_map[sym] = c
    out["assets"].append({
        "symbol": sym, "label": label, "available": True, "date": rows[-1]["date"], "last": round(c[-1], 2),
        "chg_5d_pct": round(ind.pct_change(c[-1], c[-6]), 2) if len(c) > 6 else None,
        "chg_20d_pct": round(ind.pct_change(c[-1], c[-21]), 2) if len(c) > 21 else None,
        "percentile_1y": round(ind.percentile_rank(c[-252:], c[-1]), 0),
    })
  # Derived ratios
  if "HG=F" in closes_map and "GC=F" in closes_map:
    n = min(len(closes_map["HG=F"]), len(closes_map["GC=F"]))
    cg = [closes_map["HG=F"][-n + i] / closes_map["GC=F"][-n + i] for i in range(n)]
    out["copper_gold_20d_pct"] = round(ind.pct_change(cg[-1], cg[-21]), 2) if n > 21 else None
  if "HYG" in closes_map and "TLT" in closes_map:
    h, t = closes_map["HYG"], closes_map["TLT"]
    out["hyg_minus_tlt_20d_pct"] = round(ind.pct_change(h[-1], h[-21]) - ind.pct_change(t[-1], t[-21]), 2) if min(len(h), len(t)) > 21 else None
  return out


# --------------------------------------------------------------------------- #
# Composite Market Pulse (0 = extreme fear, 100 = extreme greed)
# --------------------------------------------------------------------------- #
def market_pulse(fg: dict | None, vx: dict, pc: dict, flows: dict, xa: dict) -> dict:
  parts = []

  def add(label: str, score: float | None, weight: float, note: str) -> None:
    if score is None:
      return
    parts.append({"label": label, "score": round(_clamp(score), 0), "weight": weight, "note": note})

  if fg:
    add("CNN Fear & Greed", fg["score"], 0.30, f"{fg['score']:.0f} ({fg['rating_zh']})；一週前 {fg['week_ago']:.0f}")
  if vx.get("available"):
    v = vx["vix"]
    # Piecewise map: VIX 12→95, 15→75, 20→45, 25→25, 30→10, 40→0 (greed → fear)
    pts = [(12.0, 95.0), (15.0, 75.0), (20.0, 45.0), (25.0, 25.0), (30.0, 10.0), (40.0, 0.0)]
    if v <= pts[0][0]:
      s_vix = pts[0][1]
    elif v >= pts[-1][0]:
      s_vix = pts[-1][1]
    else:
      s_vix = 50.0
      for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= v <= x1:
          s_vix = y0 + (y1 - y0) * (v - x0) / (x1 - x0)
          break
    add("VIX 水位", s_vix, 0.20, f"VIX {v:.2f}，{vx['vix_regime']}，1 年百分位 {vx['vix_percentile_1y']:.0f}%")
    if vx.get("ratio_vix_3m"):
      r = vx["ratio_vix_3m"]
      s_term = 100.0 - _clamp((r - 0.80) / 0.35 * 100.0)  # 0.80 contango -> 100, 1.15 backwardation -> 0
      add("VIX 期限結構", s_term, 0.10, f"VIX/VIX3M = {r:.2f} → {vx['term_state']}")
    if vx.get("skew"):
      s_skew = 100.0 - _clamp((vx["skew"] - 120.0) / 50.0 * 100.0)
      add("SKEW 尾部風險", s_skew, 0.05, f"SKEW {vx['skew']:.0f}，{vx['skew_regime']}")
    if vx.get("vvix"):
      s_vvix = 100.0 - _clamp((vx["vvix"] - 80.0) / 50.0 * 100.0)
      add("VVIX 波動率的波動", s_vvix, 0.05, f"VVIX {vx['vvix']:.0f}，{vx['vvix_regime']}")
  if pc.get("available") and pc.get("equity_pc"):
    e = pc["equity_pc_5d"] or pc["equity_pc"]
    s_pc = 100.0 - _clamp((e - 0.45) / 0.55 * 100.0)  # 0.45 -> 100 greed, 1.00 -> 0 fear
    add("CBOE 個股 Put/Call (5日)", s_pc, 0.15, f"個股 P/C 5 日均 {e:.2f}（單日 {pc['equity_pc']:.2f}）→ {pc['equity_read']}")
  if xa.get("available"):
    h = xa.get("hyg_minus_tlt_20d_pct")
    if h is not None:
      add("信用 vs 避險 (HYG-TLT 20日)", 50.0 + _clamp(h * 8.0, -50, 50), 0.10, f"HYG 相對 TLT 20 日 {h:+.2f}%")
    cg = xa.get("copper_gold_20d_pct")
    if cg is not None:
      add("銅金比 (景氣溫度)", 50.0 + _clamp(cg * 4.0, -50, 50), 0.05, f"銅/金 20 日 {cg:+.2f}%")
  if flows.get("available"):
    lr = flows["latest"]["ratio"] or 0
    a20 = flows["ratio_avg20"] or 1
    s_fl = 50.0 + _clamp((lr / a20 - 1.0) * 60.0, -40, 40)
    add("SOXL/SOXS 資金流", s_fl, 0.05, f"SOXL vs SOXS 成交金額比 {lr:.2f}（20 日均 {a20:.2f}）→ {flows['read']}")

  wsum = sum(p["weight"] for p in parts) or 1.0
  score = sum(p["score"] * p["weight"] for p in parts) / wsum
  return {"score": round(score, 0), "rating_zh": _rating(score), "parts": parts}


def analyze(soxl_rows: list[dict]) -> dict:
  fg = cnn_fear_greed()
  vx = vix_complex()
  pc = cboe_put_call()
  flows = leveraged_flows(soxl_rows)
  xa = cross_asset_risk()
  pulse = market_pulse(fg, vx, pc, flows, xa)
  return {"fear_greed": fg, "vix": vx, "put_call": pc, "flows": flows, "cross_asset": xa, "pulse": pulse}
