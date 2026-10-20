#!/usr/bin/env python3
"""Stress-test the SVG layout code (usage: .venv/bin/python tools/qa_stress.py) with adversarial payloads (the dashboard re-renders daily on new data).

Each variant perturbs today's JSON, renders both pages and runs the same headless-Chrome QA as qa_render.py.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from soxl_quant import report_html, report_simple  # noqa: E402
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


VARIANTS = {"cluster": v_cluster, "edges": v_edges, "dense_episodes": v_dense_episodes, "tiny": v_tiny, "big_prices": v_big_prices}

if __name__ == "__main__":
  total = 0
  for name, fn in VARIANTS.items():
    p = fn(copy.deepcopy(base))
    for page, renderer in (("main", report_html.render), ("simple", report_simple.render)):
      html = renderer(p)
      src = qa.OUT / f"stress_{name}_{page}.html"
      src.write_text(html, encoding="utf-8")
      v = qa.make_variant(str(src), "pro")
      for w in (1440, 900, 390):
        r = qa.measure(v, w)
        svg_issues = [i for i in r.get("issues", []) if i["type"].startswith("svg") or i["type"] in ("page-hscroll", "html-clipped", "html-escape")]
        r2 = dict(r, issues=svg_issues, scrollers=[])
        total += qa.summarize(f"{name}|{page}|{w}", r2, verbose=8)
  print("STRESS TOTAL:", total)
  sys.exit(1 if total else 0)
