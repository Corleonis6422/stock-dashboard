#!/usr/bin/env python3
"""Stress-test the layout code (usage: python3 tools/qa_stress.py) with adversarial payloads (the dashboard re-renders daily on new data).

Each variant perturbs today's JSON, renders the page and runs the same headless-Chrome QA as qa_render.py, with each chart view shown.

The combined chart draws the stored block ``stress_chart``, which a perturbed series does not change.  So each variant is
rendered twice: with the stored block (daily and weekly view), and without it, where the chart is rebuilt from the
perturbed series (daily view only).  The variants after ``big_prices`` exist for the chart and run without the block:
no spike, every session a spike, no VIX history, no crash index, and a rising market with a buy rating.  ``tiny`` without
the block is the view with fewer than 30 bars.
The page without the block also gets the first-screen measurement of qa_render.py (type ``first-screen``): no sideways
scroll in the chart, no label on a candle of the latest 20 bars, no placeholder token.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from soxl_quant import report_page  # noqa: E402
import qa_render as qa  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
base = json.loads((BASE / "soxl_analysis_data.json").read_text(encoding="utf-8"))
base.setdefault("schedule", {"installed": True, "times": ["07:30"], "weekday_text": "週二、三、四、五、六", "next_run_short": "10/21（三）07:30"})


def v_cluster(p):
  """Every key level piled within ±1.5% of the close."""
  t, o = p["technicals"], p["options"]
  c = t["close"]
  o["put_wall"], o["call_wall"], o["gamma_flip"] = round(c * 0.995, 2), round(c * 1.004, 2), round(c * 1.009, 2)
  sw = t.setdefault("swing", {})
  sw["kind"] = "down"
  sw["levels"] = {"fib_236": c * 1.002, "fib_382": c * 1.006, "fib_500": c * 1.012, "fib_618": c * 1.015}
  return p


def v_edges(p):
  """Levels hugging the top/bottom of the price panel; options markers at the strike-range edges."""
  t, o = p["technicals"], p["options"]
  cs = t["chart_series"]
  hi = max(r["high"] for r in cs)
  lo = min(r["low"] for r in cs)
  o["gamma_flip"], o["call_wall"], o["put_wall"] = hi * 1.0, hi * 0.995, lo * 1.0
  fs = o.get("focus_strikes") or []
  if fs:
    o["cboe_spot"] = fs[0]["strike"]
    o["gamma_flip"] = fs[-1]["strike"]
    o["near_max_pain"] = fs[1]["strike"] if len(fs) > 1 else fs[0]["strike"]
  return p


def v_dense_episodes(p):
  """20 crash markers incl. consecutive days and both chart ends."""
  ews = p["early_warning"]
  ch = ews.get("chart") or []
  dates = [c["date"] for c in ch]
  pick = sorted(set([dates[0], dates[1], dates[2], dates[-1], dates[-2]] + dates[10:40:2] + dates[60:64]))
  eps = ews.setdefault("event_study", {}).setdefault("episodes", [])
  proto = eps[0] if eps else {"close": 100, "fwd_min_pct": -25.0, "regime": "頂部型 (價在 200MA 上)", "score_max_prev5": 80, "flagged": True, "top_signals": [["ext20", 1.0]]}
  ews["event_study"]["episodes"] = [dict(proto, date=d) for d in pick]
  return p


def v_tiny(p):
  """Very short histories."""
  t = p["technicals"]
  t["chart_series"] = t["chart_series"][-12:]
  p["sentiment"]["fear_greed"]["history"] = (p["sentiment"]["fear_greed"].get("history") or [])[-3:]
  p["early_warning"]["chart"] = (p["early_warning"].get("chart") or [])[-9:]
  p["light_history"] = (p.get("light_history") or [])[-6:]
  return p


def v_big_prices(p):
  """4-digit prices (e.g. after a reverse split)."""
  t = p["technicals"]
  k = 25.0
  for r in t["chart_series"]:
    for key in ("open", "high", "low", "close", "sma20", "sma50", "sma200", "bb_upper", "bb_lower", "supertrend"):
      if r.get(key) is not None:
        r[key] = r[key] * k
  for key in ("close", "sma20", "sma50", "sma200"):
    t[key] = t[key] * k
  o = p["options"]
  for key in ("put_wall", "call_wall", "gamma_flip", "cboe_spot", "near_max_pain"):
    if o.get(key):
      o[key] = o[key] * k
  for s in o.get("focus_strikes") or []:
    s["strike"] = s["strike"] * k
  sw = t.get("swing") or {}
  for key in list((sw.get("levels") or {}).keys()):
    sw["levels"][key] = sw["levels"][key] * k
  for r in p["early_warning"].get("chart") or []:
    r["close"] = r["close"] * k
  for r in p.get("light_history") or []:
    r["close"] = r["close"] * k
  return p


def _reduced(p):
  """Drop the stored chart block: the chart is then rebuilt from the series of the payload (daily view only)."""
  p.pop("stress_chart", None)
  return p


def v_no_spike(p):
  """A view with no VIX spike: a flat VIX history."""
  for r in (p["sentiment"].get("vix") or {}).get("history") or []:
    r["vix"] = 18.0
  return _reduced(p)


def v_all_spike(p):
  """Every session of the view is a VIX spike: VIX rises 1.2% a session, so each close is above 1.4 times the median of the 60 before it."""
  for i, r in enumerate((p["sentiment"].get("vix") or {}).get("history") or []):
    r["vix"] = round(9.0 * 1.012 ** i, 2)
  return _reduced(p)


def v_no_vix(p):
  """Missing VIX history."""
  p["sentiment"]["vix"] = {"available": False}
  return _reduced(p)


def v_no_crash(p):
  """Missing crash index history."""
  p["early_warning"]["chart"] = []
  return _reduced(p)


def v_rising_buy(p):
  """A rising market with a buy rating: the price path runs backwards, the rating is a buy, the plan is a tradeable long."""
  t = p["technicals"]
  cs = t["chart_series"]
  keys = [k for k in cs[0] if k != "date"]
  flipped = [{k: r.get(k) for k in keys} for r in reversed(cs)]
  for r, f in zip(cs, flipped):
    f["open"], f["close"] = f["close"], f["open"]   # a falling day read backwards is a rising day
    r.update(f)
  last, prev = cs[-1], cs[-2]
  t["close"], t["ret_1d"] = last["close"], round((last["close"] / prev["close"] - 1) * 100, 2)
  for key in ("sma20", "sma50", "sma200", "macd", "macd_signal", "macd_hist", "k9", "d9", "j9"):
    if last.get(key) is not None:
      t[key] = last[key]
  for rows in (p.get("light_history") or [], p["early_warning"].get("chart") or []):
    closes = [r.get("close") for r in rows][::-1]
    for r, c in zip(rows, closes):
      r["close"] = c
  for r in p.get("light_history") or []:
    r["light"] = "bull"
  c = t["close"]
  sc, b = p["scoring"], p["playbook"].setdefault("beginner", {})
  sc.update({"rating_5": 5, "rating_label": "強力買進", "rating_emoji": "🟢🟢", "rating_pos": 92.0, "composite_score": 1.42, "trend_score": 1.6, "contrarian_score": 0.4})
  b.update({"verdict": "買進 / 持有", "color": "bull", "emoji": "🟢", "rating_5": 5, "rating_label": "強力買進", "rating_pos": 92.0, "size_pct": 100})
  p["trade_plan"] = dict(p.get("trade_plan") or {}, side="long", tradeable=True, rating_5=5, headline="買訊成立：次日開盤進場", rr_blend=2.4, min_rr=1.5, trade_if_entry=None,
                         entry={"type": "market", "price": round(c, 2), "rule": "驗證過的買訊今天成立，次日開盤進場", "signal": "breakout20"},
                         stop={"price": round(c * 0.88, 2), "dist_pct": -12.0, "k_atr": 1.2, "kind": "structural", "basis": "結構支撐 近 10 日最低"},
                         t1={"price": round(c * 1.15, 2), "label": "前高", "rr": 1.25, "synthetic": False}, t2={"price": round(c * 1.4, 2), "label": "52 週高", "rr": 3.3, "synthetic": False},
                         size={"pct": 8.3, "if_triggered_pct": 8.3, "risk_based_pct": 8.3, "verdict_cap_pct": 100.0, "risk_per_trade_pct": 1.0, "three_stops_pct": -3.0})
  return _reduced(p)


VARIANTS = {"cluster": v_cluster, "edges": v_edges, "dense_episodes": v_dense_episodes, "tiny": v_tiny, "big_prices": v_big_prices,
            "no_spike": v_no_spike, "all_spike": v_all_spike, "no_vix": v_no_vix, "no_crash": v_no_crash, "rising_buy": v_rising_buy}
KEPT = ("page-hscroll", "html-clipped", "html-escape")   # with every svg-* type: the check types this harness has always counted

if __name__ == "__main__":
  total, runs = 0, 0
  by_type: dict = {}
  for name, fn in VARIANTS.items():
    p = fn(copy.deepcopy(base))
    passes = [("", p)] + ([("reduced", _reduced(copy.deepcopy(p)))] if "stress_chart" in p else [])
    for label, payload in passes:
      tag = name + ("|" + label if label else "")
      src = qa.OUT / f"stress_{name}{'_' + label if label else ''}.html"
      src.write_text(report_page.render(payload), encoding="utf-8")
      for view in qa.page_views(str(src)) or [None]:
        v = qa.make_variant(str(src), view=view)
        for w in (1440, 900, 390):
          r = qa.measure(v, w)
          svg_issues = [i for i in r.get("issues", []) if i["type"].startswith("svg") or i["type"] in KEPT]
          r2 = dict(r, issues=svg_issues, scrollers=[])
          total += qa.summarize(f"{tag}|{view or 'no-chart'}|{w}", r2, verbose=8)
          runs += 1
          for i in svg_issues:
            by_type[i["type"]] = by_type.get(i["type"], 0) + 1
        if "stress_chart" in payload:
          continue
        f = qa.make_variant(str(src), view=view, script=qa.FS_JS, tag="fs")
        for w in (1440, 390):
          r = qa.measure(f, w, qa.NARROW_FOLD if w < 500 else qa.WIDE_FOLD)
          found = [{"type": "first-screen", "sec": "chart", "el": "", "text": "", "detail": x} for x in r.get("problems", [])]
          if "error" in r:
            found = [{"type": "first-screen", "sec": "chart", "el": "", "text": "", "detail": str(r)}]
          total += qa.summarize(f"{tag}|{view or 'no-chart'}|first-screen|{w}", {"vw": r.get("vw", w), "docW": r.get("docW", 0), "issues": found}, verbose=8)
          runs += 1
          for i in found:
            by_type[i["type"]] = by_type.get(i["type"], 0) + 1
  print("RUNS:", runs)
  print("BY TYPE:", ", ".join(f"{k}:{v}" for k, v in sorted(by_type.items())) or "none")
  print("STRESS TOTAL:", total)
  sys.exit(1 if total else 0)
