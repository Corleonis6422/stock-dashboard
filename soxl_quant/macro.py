#!/usr/bin/env python3
"""Cross-asset macro correlation analysis for SOXL.

Core set (always shown): 10Y (^TNX), 30Y (^TYX), 30Y-10Y spread, Brent (BZ=F),
VIX (official CBOE).  Extended set (if available): DXY, HYG, Gold, Copper, BTC.
"""

from __future__ import annotations

from . import datafeed
from . import indicators as ind

CORE = {
    "TNX_10Y": ("^TNX", "10Y 美債殖利率"),
    "TYX_30Y": ("^TYX", "30Y 美債殖利率"),
    "BRENT": ("BZ=F", "Brent 原油"),
}
EXTENDED = {
    "DXY": ("DX-Y.NYB", "美元指數"),
    "HYG": ("HYG", "高收益債 HYG"),
    "GOLD": ("GC=F", "黃金"),
    "COPPER": ("HG=F", "銅"),
    "BTC": ("BTC-USD", "比特幣"),
}


def analyze(soxl_rows: list[dict], vix_rows: list[dict]) -> dict:
  series = {"SOXL": {r["date"]: r["close"] for r in soxl_rows}}
  series["VIX"] = {r["date"]: r["close"] for r in vix_rows}
  labels = {"SOXL": "SOXL", "VIX": "VIX 恐慌指數", "SPREAD_30_10": "30Y-10Y 利差"}
  missing = []
  proxies = {}
  for key, (sym, label) in {**CORE, **EXTENDED}.items():
    try:
      rows, proxy_label = datafeed.fetch_history_with_proxy(sym, "2y")
      series[key] = {r["date"]: r["close"] for r in rows}
      labels[key] = proxy_label or label
      if proxy_label:
        proxies[key] = proxy_label
    except Exception:  # noqa: BLE001
      missing.append(key)
  core_keys = [k for k in ("SOXL", "TNX_10Y", "TYX_30Y", "BRENT", "VIX") if k in series]
  dates = sorted(set.intersection(*(set(series[k]) for k in core_keys)))
  dates = [d for d in dates if d >= soxl_rows[max(0, len(soxl_rows) - 400)]["date"]]

  aligned = []
  for i, d in enumerate(dates):
    rec = {"date": d}
    for k in series:
      rec[k] = series[k].get(d)
    if rec.get("TNX_10Y") is not None and rec.get("TYX_30Y") is not None:
      rec["SPREAD_30_10"] = (rec["TYX_30Y"] - rec["TNX_10Y"]) * 100.0
    aligned.append(rec)
  # returns
  for i in range(len(aligned)):
    cur = aligned[i]
    prev = aligned[i - 1] if i else None
    for k in list(series.keys()) + ["SPREAD_30_10"]:
      a, b = cur.get(k), (prev.get(k) if prev else None)
      if k == "SPREAD_30_10":
        cur["ret_" + k] = (a - b) if (a is not None and b is not None) else 0.0
      else:
        cur["ret_" + k] = ind.pct_change(a, b) if (a is not None and b) else 0.0
    cur["bps_TNX_10Y"] = ((cur.get("TNX_10Y") or 0) - (prev.get("TNX_10Y") or 0)) * 100.0 if prev else 0.0
    cur["bps_TYX_30Y"] = ((cur.get("TYX_30Y") or 0) - (prev.get("TYX_30Y") or 0)) * 100.0 if prev else 0.0

  assets = [k for k in ("TNX_10Y", "TYX_30Y", "SPREAD_30_10", "BRENT", "VIX", "DXY", "HYG", "GOLD", "COPPER", "BTC") if k in series or k == "SPREAD_30_10"]

  def corr_win(n: int, k: str, levels: bool = False) -> float:
    sub = [x for x in aligned[-n:] if x.get(k) is not None]
    if len(sub) < 5:
      return 0.0
    if levels:
      return round(ind.pearson([x["SOXL"] for x in sub], [x[k] for x in sub]), 3)
    return round(ind.pearson([x["ret_SOXL"] for x in sub], [x["ret_" + k] for x in sub]), 3)

  horizons = {}
  for name, n in (("20D", 20), ("60D", 60), ("120D", 120), ("250D", 250)):
    h = {k: {"ret_corr": corr_win(n, k), "level_corr": corr_win(n, k, True)} for k in assets}
    sub = aligned[-n:]
    h["TNX_vs_TYX_ret"] = round(ind.pearson([x["ret_TNX_10Y"] for x in sub], [x["ret_TYX_30Y"] for x in sub]), 3) if "TNX_10Y" in series and "TYX_30Y" in series else 0.0
    if "BRENT" in series and "TNX_10Y" in series:
      bsub = [x for x in sub if x.get("BRENT") is not None and x.get("TNX_10Y") is not None]
      h["BRENT_vs_TNX_ret"] = round(ind.pearson([x["ret_BRENT"] for x in bsub], [x["ret_TNX_10Y"] for x in bsub]), 3)
      h["BRENT_vs_TNX_lvl"] = round(ind.pearson([x["BRENT"] for x in bsub], [x["TNX_10Y"] for x in bsub]), 3)
    else:
      h["BRENT_vs_TNX_ret"] = 0.0
      h["BRENT_vs_TNX_lvl"] = 0.0
    horizons[name] = h

  matrix_keys = ["SOXL"] + [k for k in ("TNX_10Y", "TYX_30Y") if k in series] + ["SPREAD_30_10"] + [k for k in ("BRENT", "VIX", "DXY", "HYG", "GOLD", "COPPER", "BTC") if k in series]

  def matrix(n: int) -> list[dict]:
    sub = aligned[-n:]
    out = []
    for a in matrix_keys:
      row = {"asset": a, "label": labels.get(a, a), "cells": []}
      for b in matrix_keys:
        pairs = [(x["ret_" + a], x["ret_" + b]) for x in sub if x.get(a) is not None and x.get(b) is not None]
        row["cells"].append({"target": b, "corr": round(ind.pearson([p[0] for p in pairs], [p[1] for p in pairs]), 3) if len(pairs) > 5 else 0.0})
      out.append(row)
    return out

  sub20 = aligned[-20:]
  sub120 = aligned[-120:]
  beta_vix = ind.beta([x["ret_SOXL"] for x in sub20], [x.get("ret_VIX", 0.0) for x in sub20])
  beta_brent = ind.beta([x["ret_SOXL"] for x in sub20], [x.get("ret_BRENT", 0.0) for x in sub20])
  beta_tnx = ind.beta([x["ret_SOXL"] for x in sub120], [x.get("bps_TNX_10Y", 0.0) for x in sub120]) * 10.0
  beta_tyx = ind.beta([x["ret_SOXL"] for x in sub120], [x.get("bps_TYX_30Y", 0.0) for x in sub120]) * 10.0

  rolling = []
  for i in range(max(21, len(aligned) - 120), len(aligned)):
    w = aligned[i - 19 : i + 1]
    sr = [x["ret_SOXL"] for x in w]
    rolling.append({
        "date": aligned[i]["date"], "SOXL": round(aligned[i]["SOXL"], 2),
        "TNX_10Y": aligned[i].get("TNX_10Y"), "TYX_30Y": aligned[i].get("TYX_30Y"),
        "SPREAD_30_10": round(aligned[i].get("SPREAD_30_10") or 0.0, 1), "BRENT": aligned[i].get("BRENT"), "VIX": aligned[i].get("VIX"),
        "DXY": aligned[i].get("DXY"), "HYG": aligned[i].get("HYG"),
        "corr_soxl_vix": round(ind.pearson(sr, [x.get("ret_VIX", 0.0) for x in w]), 3),
        "corr_soxl_brent": round(ind.pearson(sr, [x.get("ret_BRENT", 0.0) for x in w]), 3),
        "corr_soxl_tnx": round(ind.pearson(sr, [x.get("ret_TNX_10Y", 0.0) for x in w]), 3),
        "corr_soxl_tyx": round(ind.pearson(sr, [x.get("ret_TYX_30Y", 0.0) for x in w]), 3),
    })

  L, P5, P20 = aligned[-1], aligned[-6], aligned[-21]

  def regime_yield(v: float, kind: str) -> str:
    if kind == "10Y":
      return "極端高檔 (>5.2%)" if v > 5.2 else ("高檔 (4.6-5.2%)" if v > 4.6 else ("中性 (4.0-4.6%)" if v > 4.0 else "寬鬆 (<4.0%)"))
    return "多年高點區 (>5.5%)" if v > 5.5 else ("高檔 (4.9-5.5%)" if v > 4.9 else "正常 (<4.9%)")

  kpis = []
  if L.get("TNX_10Y") is not None:
    kpis.append({"key": "TNX_10Y", "name": "美國 10 年期公債殖利率 (^TNX)", "latest": f"{L['TNX_10Y']:.3f}%",
                 "chg_1d": f"{L['bps_TNX_10Y']:+.1f} bps", "chg_5d": f"{(L['TNX_10Y'] - P5['TNX_10Y'])*100:+.1f} bps", "chg_20d": f"{(L['TNX_10Y'] - P20['TNX_10Y'])*100:+.1f} bps",
                 "corr_20d": horizons["20D"]["TNX_10Y"]["ret_corr"], "corr_60d": horizons["60D"]["TNX_10Y"]["ret_corr"], "corr_120d": horizons["120D"]["TNX_10Y"]["ret_corr"],
                 "beta_note": f"10Y 每升 10bps，SOXL 平均 {beta_tnx:+.2f}%", "regime": regime_yield(L["TNX_10Y"], "10Y")})
  if L.get("TYX_30Y") is not None:
    kpis.append({"key": "TYX_30Y", "name": "美國 30 年期公債殖利率 (^TYX)", "latest": f"{L['TYX_30Y']:.3f}%",
                 "chg_1d": f"{L['bps_TYX_30Y']:+.1f} bps", "chg_5d": f"{(L['TYX_30Y'] - P5['TYX_30Y'])*100:+.1f} bps", "chg_20d": f"{(L['TYX_30Y'] - P20['TYX_30Y'])*100:+.1f} bps",
                 "corr_20d": horizons["20D"]["TYX_30Y"]["ret_corr"], "corr_60d": horizons["60D"]["TYX_30Y"]["ret_corr"], "corr_120d": horizons["120D"]["TYX_30Y"]["ret_corr"],
                 "beta_note": f"30Y 每升 10bps，SOXL 平均 {beta_tyx:+.2f}%；30Y-10Y 利差 {L.get('SPREAD_30_10', 0):+.0f} bps", "regime": regime_yield(L["TYX_30Y"], "30Y")})
  if L.get("BRENT") is not None:
    b = L["BRENT"]
    is_proxy = "BRENT" in proxies
    kpis.append({"key": "BRENT", "name": labels.get("BRENT", "布蘭特原油 (BZ=F)") if is_proxy else "布蘭特原油 (BZ=F)", "latest": f"${b:.2f}", "chg_1d": f"{L['ret_BRENT']:+.2f}%",
                 "chg_5d": f"{ind.pct_change(b, P5['BRENT']):+.2f}%", "chg_20d": f"{ind.pct_change(b, P20['BRENT']):+.2f}%",
                 "corr_20d": horizons["20D"]["BRENT"]["ret_corr"], "corr_60d": horizons["60D"]["BRENT"]["ret_corr"], "corr_120d": horizons["120D"]["BRENT"]["ret_corr"],
                 "beta_note": f"油價每漲 1%，SOXL 短線平均 {beta_brent:+.2f}%；油價與 10Y 殖利率 60D 相關 {horizons['60D']['BRENT_vs_TNX_ret']:+.2f}",
                 "regime": ("20 日 " + f"{ind.pct_change(b, P20['BRENT']):+.1f}%") if is_proxy else ("通膨警戒 (>$100)" if b > 100 else ("偏高 ($85-100)" if b > 85 else "溫和 (<$85)"))})
  v = L.get("VIX")
  if v is not None:
    kpis.append({"key": "VIX", "name": "CBOE 恐慌指數 (VIX)", "latest": f"{v:.2f}", "chg_1d": f"{L['ret_VIX']:+.2f}%",
                 "chg_5d": f"{ind.pct_change(v, P5['VIX']):+.2f}%", "chg_20d": f"{ind.pct_change(v, P20['VIX']):+.2f}%",
                 "corr_20d": horizons["20D"]["VIX"]["ret_corr"], "corr_60d": horizons["60D"]["VIX"]["ret_corr"], "corr_120d": horizons["120D"]["VIX"]["ret_corr"],
                 "beta_note": f"VIX 每升 1%，SOXL 平均 {beta_vix:+.2f}%（全市場最強負相關）",
                 "regime": "恐慌 (>25)" if v > 25 else ("警戒 (20-25)" if v > 20 else ("溫和 (16-20)" if v > 16 else "低波 (<16)"))})
  for k in ("DXY", "HYG", "GOLD", "COPPER", "BTC"):
    if L.get(k) is not None and P20.get(k):
      kpis.append({"key": k, "name": labels[k], "latest": f"{L[k]:,.2f}", "chg_1d": f"{L['ret_' + k]:+.2f}%",
                   "chg_5d": f"{ind.pct_change(L[k], P5[k]):+.2f}%" if P5.get(k) else "n/a", "chg_20d": f"{ind.pct_change(L[k], P20[k]):+.2f}%",
                   "corr_20d": horizons["20D"][k]["ret_corr"], "corr_60d": horizons["60D"][k]["ret_corr"], "corr_120d": horizons["120D"][k]["ret_corr"],
                   "beta_note": "", "regime": ""})

  return {
      "latest_date": L["date"], "missing": missing, "proxies": proxies, "labels": labels, "macro_kpis": kpis, "horizons": horizons,
      "matrix_20d": matrix(20), "matrix_60d": matrix(60), "matrix_keys": matrix_keys,
      "beta_vix_20d": round(beta_vix, 2), "beta_brent_20d": round(beta_brent, 2),
      "beta_tnx_10bps": round(beta_tnx, 2), "beta_tyx_10bps": round(beta_tyx, 2),
      "rolling_series": rolling,
      "latest": {k: L.get(k) for k in matrix_keys},
  }
