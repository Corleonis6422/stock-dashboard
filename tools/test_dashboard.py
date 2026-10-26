#!/usr/bin/env python3
"""Offline tests for soxl_quant.dashboard: add-on decision matrix, SOXX trend labels, grades, lights, voices."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soxl_quant import dashboard as dz  # noqa: E402

BAD = 0


def check(cond, msg):
  global BAD
  print(("PASS" if cond else "FAIL"), msg)
  BAD += not cond


def rows(closes):
  return [{"date": f"d{i}", "close": c} for i, c in enumerate(closes)]


def base_payload(**over):
  p = {
      "technicals": {"close": 100.0, "sma20": 90.0},
      "options": {"pc_vol_ratio": 0.85, "pc_oi_ratio": 1.2, "whale": {"whale_net_score": 0.3, "whale_count": 10, "whale_call_prem_m": 30.0, "whale_put_prem_m": 10.0, "whale_cp_ratio": 3.0, "retail_cp_ratio": 0.8,
                                                                        "top_whale_trades": [{"expiration": "2027-01-15", "strike": 50, "type": "C", "premium_m": 5.0, "bias": "偏多"}]}},
      "sentiment": {"vix": {"ratio_vix_3m": 0.9}, "put_call": {"equity_pc": 0.6, "equity_pc_percentile": 50.0, "total_pc": 0.9, "total_read": "x", "equity_read": "y"}, "flows": {"latest": {"ratio": 2.0}, "ratio_avg20": 3.0}},
      "heatmap": {"breadth_above_sma50_pct": 60.0, "breadth_above_sma200_pct": 70.0},
      "macro": {"macro_kpis": [{"key": "TNX_10Y", "latest": "4.5%", "chg_1d": "+1 bps"}, {"key": "VIX", "latest": "15", "chg_1d": "-1%"}]},
      "early_warning": {"today": {"score": 30.0, "above_200": True, "zone": "低"}, "contributions": [], "event_study": {"stats_top_80": {"precision_pct": 12, "base_rate_pct": 9}}},
      "scoring": {"rating_5": 4, "rating_label": "買進", "rating_emoji": "🟢", "composite_score": 0.8, "category_scores": [{"category": "1. 期權籌碼 (Options Flow)", "weight": 20, "avg_score": 1.6}, {"category": "3. 技術趨勢 (Technicals)", "weight": 26, "avg_score": -1.2}]},
      "trade_plan": {"side": "no_trade", "tradeable": False, "entry": {"price": 105.0}, "stop": {"price": 88.0}, "size": {"pct": 0, "if_triggered_pct": 8.0, "verdict_cap_pct": 25},
                     "holder": {"trail_breached": False, "reduce_into": [{"price": 110.0}, {"price": 115.0}]}, "regime": {"underlying": {"in_market": True, "sma200": 450.0, "exit_below": 440.0}}},
      "newsflash": {"label": "中性", "net": 0.0, "top": [{"category": "聯準會與利率", "title": "Fed holds", "publisher": "Reuters", "emoji": "🏦", "why_zh": "x：y"}], "flags": {}},
      "playbook": {"beginner": {"size_pct": 25}},
      "benchmarks_recent": {"SOXX": rows([400 + i for i in range(40)])},
      "data_as_of": "2026-01-01",
  }
  for k, v in over.items():
    p[k] = v
  return p


# ---- grades
check(dz.grade(1.6) == "A+" and dz.grade(1.0) == "A" and dz.grade(0.65) == "B+" and dz.grade(0.3) == "B" and dz.grade(0.15) == "C+", "grade upper steps")
check(dz.grade(0.0) == "C" and dz.grade(-0.2) == "C-" and dz.grade(-0.5) == "D" and dz.grade(-0.8) == "D-" and dz.grade(-1.5) == "F" and dz.grade(None) == "—", "grade lower steps")

# ---- SOXX trend labels
up = [100 * (1.001 ** i) for i in range(260)]
sx = dz.soxx_stats(rows(up))
check(sx["available"] and sx["light"] == "green" and sx["trend"].startswith("多頭"), f"uptrend → green ({sx['trend']})")
down = [100 * (0.999 ** i) for i in range(260)]
sx = dz.soxx_stats(rows(down))
check(sx["light"] == "red" and sx["trend"].startswith("空頭"), f"downtrend → red ({sx['trend']})")
up2 = [100 * (1.0015 ** i) for i in range(230)]
corr = up2 + [up2[-1] * (0.995 ** i) for i in range(1, 16)]  # long uptrend then a 7% pullback: still above 200MA, below 20 / 50MA
sx = dz.soxx_stats(rows(corr))
check(sx["light"] == "yellow" and "修正中" in sx["trend"], f"pullback above 200MA → yellow 修正中 ({sx['trend']}, dist200 {sx['dist_sma200_pct']})")
sx = dz.soxx_stats(None, rows([400 + i for i in range(40)]), {"sma200": 300.0})
check(sx["available"] and sx["source"] == "benchmarks_recent" and sx["sma200"] == 300.0 and sx["sma50"] is None, "fallback to 40-close series + regime sma200")
check(dz.soxx_stats(None, rows([1, 2, 3]))["available"] is False, "too short → unavailable")

# ---- add-on decision matrix
g = dz.build(base_payload())["gauges"][0]
check(g["key"] == "add_on" and g["value"] == "可小量加碼" and g["light"] == "green", f"rating 4 + above 20MA + index in market → 可小量加碼 ({g['value']})")
p = base_payload(); p["technicals"]["close"] = 80.0  # below 20MA
g = dz.build(p)["gauges"][0]
check(g["value"] == "先不加碼" and g["light"] == "yellow", f"rating 4 below 20MA → 先不加碼 ({g['value']})")
p = base_payload(); p["scoring"]["rating_5"] = 2
g = dz.build(p)["gauges"][0]
check(g["value"] == "不能加碼" and g["light"] == "red" and "$88.00" in g["detail"], f"rating 2 → 不能加碼 with stop ({g['value']})")
p = base_payload(); p["scoring"]["rating_5"] = 3
g = dz.build(p)["gauges"][0]
check(g["value"] == "先不加碼", f"rating 3 → 先不加碼 ({g['value']})")
p = base_payload(); p["trade_plan"]["side"] = "long"; p["trade_plan"]["tradeable"] = True; p["trade_plan"]["size"]["pct"] = 8.0
g = dz.build(p)["gauges"][0]
check(g["value"] == "可以加碼" and g["light"] == "green" and "8.0%" in g["meaning"], f"validated long → 可以加碼 ({g['value']})")
p = base_payload(); p["trade_plan"]["side"] = "long_pending"
g = dz.build(p)["gauges"][0]
check(g["value"] == "先不加碼" and "$105.00" in g["meaning"], f"long_pending → 先不加碼 with trigger ({g['value']})")
p = base_payload(); p["trade_plan"]["side"] = "long"; p["trade_plan"]["tradeable"] = True; p["early_warning"]["today"]["score"] = 85.0
g = dz.build(p)["gauges"][0]
check(g["value"] == "不能加碼" and "85" in g["meaning"], f"crash ≥ 80 overrides a validated long ({g['value']})")
p = base_payload(); p["sentiment"]["vix"]["ratio_vix_3m"] = 1.05
g = dz.build(p)["gauges"][0]
check(g["value"] == "不能加碼" and "倒掛" in g["meaning"], f"VIX term inversion → 不能加碼 ({g['value']})")

# ---- other gauges + lights
d = dz.build(base_payload())
keys = [g["key"] for g in d["gauges"]]
check(keys == ["add_on", "macro", "soxx", "whales", "put_call", "crash"], f"gauge order {keys}")
check(all(g["light"] in ("green", "yellow", "red", "grey") for g in d["gauges"]), "lights valid")
check(all(g["fields"] for g in d["gauges"]), "every gauge names its source fields")
check(all(g.get("short") for g in d["gauges"]), "every gauge has a short value")
gw = d["gauges"][3]
check(gw["light"] == "green" and "+0.30" in gw["value"], f"whale net 0.3 → green ({gw['value']})")
p = base_payload(); p["options"]["whale"]["whale_net_score"] = -0.4
check(dz.build(p)["gauges"][3]["light"] == "red", "whale net −0.4 → red")
gp = d["gauges"][4]
check(gp["light"] == "green", f"neutral put/call → green ({gp['value']})")
p = base_payload(); p["sentiment"]["put_call"]["equity_pc_percentile"] = 95.0
gp = dz.build(p)["gauges"][4]
check(gp["light"] == "yellow" and "恐慌" in gp["short"], f"equity P/C 95th pct → yellow 恐慌 ({gp['short']})")
gc = d["gauges"][5]
check(gc["light"] == "green" and gc["short"].startswith("30/100"), f"crash 30 → green ({gc['short']})")
p = base_payload(); p["early_warning"]["today"]["score"] = 65.0
check(dz.build(p)["gauges"][5]["light"] == "yellow", "crash 65 → yellow")
gm = d["gauges"][1]
check(gm["light"] == "yellow" and "Fed holds" in gm["value"], f"neutral flash → yellow with headline ({gm['value'][:40]})")
p = base_payload(); p["newsflash"]["flags"] = {"geo_escalation_24h": True}
check(dz.build(p)["gauges"][1]["light"] == "red", "a flag → macro red")

# ---- grades + voices
fg = d["factor_grades"]
check([x["grade"] for x in fg] == ["A+", "F"] and fg[0]["short"] == "期權籌碼" and fg[1]["short"] == "技術趨勢", f"factor grades {[(x['short'], x['grade']) for x in fg]}")
check(d["overall_grade"] == "B+", f"overall grade from composite 0.8 → B+ ({d['overall_grade']})")
vc = d["voices"]
check(len(vc["rows"]) == 4 and vc["n_bull"] >= 1 and "四個聲音" in vc["summary"], f"voices: {vc['summary']}")
p = base_payload(); p["scoring"]["rating_5"] = 2; p["newsflash"]["label"] = "偏空"
vc = dz.build(p)["voices"]
check(vc["n_bull"] == 0 and "不加碼" in vc["summary"], f"no bullish voice → 不加碼 ({vc['summary']})")

# ---- refresh_macro keeps the other gauges
d2 = dz.refresh_macro(d, dict(base_payload(), newsflash={"label": "偏多", "net": 0.5, "top": [], "flags": {}}), [])
check(d2["gauges"][1]["light"] == "green" and d2["gauges"][0] == d["gauges"][0] and "宏觀：🟢" in d2["one_liner"], "refresh_macro updates only macro + one_liner")

# ---- missing data degrades, never raises
d3 = dz.build({"technicals": {}, "options": {}, "sentiment": {}, "heatmap": {}, "macro": {}, "early_warning": {}, "scoring": {}, "trade_plan": {}, "newsflash": {}, "benchmarks_recent": {}})
check(len(d3["gauges"]) == 6 and all(g["light"] in ("grey", "yellow", "red", "green") for g in d3["gauges"]), "empty payload → six grey/yellow gauges, no exception")

print("dashboard tests:", "ALL PASS" if BAD == 0 else f"{BAD} FAILED")
sys.exit(1 if BAD else 0)
