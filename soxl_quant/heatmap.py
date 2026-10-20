#!/usr/bin/env python3
"""Semiconductor constituents heat map & breadth (16 core SOXX / SOXL holdings)."""

from __future__ import annotations

from . import datafeed
from . import indicators as ind

CONSTITUENTS = [
    {"ticker": "NVDA", "name": "NVIDIA", "weight": 10.2, "subsector": "AI & GPU Compute"},
    {"ticker": "AVGO", "name": "Broadcom", "weight": 9.8, "subsector": "AI ASIC & Networking"},
    {"ticker": "AMD", "name": "AMD", "weight": 8.4, "subsector": "AI & GPU Compute"},
    {"ticker": "MU", "name": "Micron", "weight": 7.6, "subsector": "Memory & HBM"},
    {"ticker": "QCOM", "name": "Qualcomm", "weight": 6.8, "subsector": "Mobile & RF"},
    {"ticker": "TXN", "name": "Texas Instruments", "weight": 6.5, "subsector": "Analog & Mixed Signal"},
    {"ticker": "AMAT", "name": "Applied Materials", "weight": 6.1, "subsector": "Wafer Fab Equipment"},
    {"ticker": "LRCX", "name": "Lam Research", "weight": 5.6, "subsector": "Wafer Fab Equipment"},
    {"ticker": "KLAC", "name": "KLA", "weight": 5.2, "subsector": "Wafer Fab Equipment"},
    {"ticker": "INTC", "name": "Intel", "weight": 4.8, "subsector": "CPU & Foundry"},
    {"ticker": "ADI", "name": "Analog Devices", "weight": 4.6, "subsector": "Analog & Mixed Signal"},
    {"ticker": "MRVL", "name": "Marvell", "weight": 4.4, "subsector": "AI ASIC & Networking"},
    {"ticker": "NXPI", "name": "NXP", "weight": 4.1, "subsector": "Auto & Industrial"},
    {"ticker": "MPWR", "name": "Monolithic Power", "weight": 3.8, "subsector": "Power Management"},
    {"ticker": "ON", "name": "ON Semi", "weight": 3.5, "subsector": "Auto & Industrial"},
    {"ticker": "TER", "name": "Teradyne", "weight": 3.2, "subsector": "Semi Test & Robotics"},
]


def analyze(soxl_rows: list[dict]) -> dict:
  soxl_r20 = [ind.pct_change(soxl_rows[i]["close"], soxl_rows[i - 1]["close"]) for i in range(len(soxl_rows) - 20, len(soxl_rows))]
  items, subs, failed = [], {}, []
  for c in CONSTITUENTS:
    try:
      rows = datafeed.fetch_history(c["ticker"], "1y")
    except Exception as e:  # noqa: BLE001
      failed.append({"ticker": c["ticker"], "error": str(e)[:80]})
      continue
    if len(rows) < 60:
      failed.append({"ticker": c["ticker"], "error": "insufficient history"})
      continue
    closes = [r["close"] for r in rows]
    vols = [float(r["volume"]) for r in rows]
    last = rows[-1]
    s20 = sum(closes[-20:]) / 20.0
    s50 = sum(closes[-50:]) / 50.0
    s200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else sum(closes) / len(closes)
    v20 = sum(vols[-20:]) / 20.0
    r14 = ind.rsi(closes, 14)[-1]
    c_r20 = [ind.pct_change(rows[i]["close"], rows[i - 1]["close"]) for i in range(len(rows) - 20, len(rows))]
    hi52 = max(r["high"] for r in rows[-252:])
    entry = {
        "ticker": c["ticker"], "name": c["name"], "weight": c["weight"], "subsector": c["subsector"],
        "close": round(last["close"], 2),
        "ret_1d": round(ind.pct_change(last["close"], rows[-2]["close"]), 2),
        "ret_5d": round(ind.pct_change(last["close"], rows[-6]["close"]), 2),
        "ret_20d": round(ind.pct_change(last["close"], rows[-21]["close"]), 2),
        "ret_60d": round(ind.pct_change(last["close"], rows[-61]["close"]), 2),
        "drawdown_52w_pct": round(ind.pct_change(last["close"], hi52), 1),
        "rvol": round(last["volume"] / v20, 2) if v20 else 1.0,
        "rsi14": round(r14, 1),
        "above_sma20": last["close"] >= s20, "above_sma50": last["close"] >= s50, "above_sma200": last["close"] >= s200,
        "dist_sma20_pct": round(ind.pct_change(last["close"], s20), 2),
        "dist_sma50_pct": round(ind.pct_change(last["close"], s50), 2),
        "dist_sma200_pct": round(ind.pct_change(last["close"], s200), 2),
        "corr_soxl_20d": round(ind.pearson(c_r20, soxl_r20), 2) if len(c_r20) == len(soxl_r20) else None,
        "oversold": r14 < 30,
    }
    items.append(entry)
    s = subs.setdefault(c["subsector"], {"subsector": c["subsector"], "weight": 0.0, "w1": 0.0, "w5": 0.0, "w20": 0.0, "wr": 0.0, "n": 0})
    s["weight"] += c["weight"]; s["w1"] += entry["ret_1d"] * c["weight"]; s["w5"] += entry["ret_5d"] * c["weight"]
    s["w20"] += entry["ret_20d"] * c["weight"]; s["wr"] += r14 * c["weight"]; s["n"] += 1

  n = len(items) or 1
  tw = sum(i["weight"] for i in items) or 1.0
  subsectors = sorted([{
      "subsector": s["subsector"], "weight": round(s["weight"], 1), "count": s["n"],
      "ret_1d": round(s["w1"] / s["weight"], 2), "ret_5d": round(s["w5"] / s["weight"], 2),
      "ret_20d": round(s["w20"] / s["weight"], 2), "avg_rsi": round(s["wr"] / s["weight"], 1),
  } for s in subs.values()], key=lambda x: -x["weight"])
  pct = lambda k: round(sum(1 for i in items if i[k]) / n * 100.0, 1)  # noqa: E731
  return {
      "constituents": items, "subsectors": subsectors, "failed": failed,
      "breadth_above_sma20_pct": pct("above_sma20"), "breadth_above_sma50_pct": pct("above_sma50"),
      "breadth_above_sma200_pct": pct("above_sma200"), "breadth_oversold_pct": pct("oversold"),
      "breadth_pos_1d_pct": round(sum(1 for i in items if i["ret_1d"] > 0) / n * 100.0, 1),
      "breadth_pos_5d_pct": round(sum(1 for i in items if i["ret_5d"] > 0) / n * 100.0, 1),
      "weighted_ret_1d": round(sum(i["ret_1d"] * i["weight"] for i in items) / tw, 2),
      "weighted_ret_5d": round(sum(i["ret_5d"] * i["weight"] for i in items) / tw, 2),
      "weighted_ret_20d": round(sum(i["ret_20d"] * i["weight"] for i in items) / tw, 2),
      "avg_rsi14": round(sum(i["rsi14"] for i in items) / n, 1),
  }
