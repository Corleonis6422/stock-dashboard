#!/usr/bin/env python3
"""Crash Early-Warning System (EWS), event study and historical-analog forecast.

The EWS converts ~20 well-known pre-crash symptoms into graded 0-1 signals,
combines them into a 0-100 *Crash Risk Score* for every trading day, and then
validates the score against realised SOXL drawdowns (event study).  Nothing is
curve-fitted: weights are fixed by design, and performance is reported honestly
(hit rate, false-alarm rate, lead time) with the sample sizes shown.

Signal families
  A. Over-extension / euphoria   (distance to 200MA & 20MA, 20-day run, RSI, Bollinger width)
  B. Momentum roll-over           (MACD fade, high-level KD death cross, first 20MA break, RSI divergence, distribution days)
  C. Volatility structure         (VIX/VIX3M term flattening, VIX awakening, VVIX, SKEW, VIX9D inversion)
  D. Macro pressure               (10Y shock, 30Y multi-year high, credit divergence HYG vs SPY)
  E. Sentiment / positioning      (CNN Fear & Greed greed or crack, equity P/C complacency, SOXL/SOXS dip-buying mania)
"""

from __future__ import annotations

import statistics

from . import indicators as ind


def _clip(x: float) -> float:
  return max(0.0, min(1.0, x))


WEIGHTS = {
    "ext200": 8, "ext20": 6, "parabolic20": 8, "rsi_hot": 4, "bbw_high": 4,
    "macd_fade": 6, "kd_death_high": 6, "break20": 8, "rsi_divergence": 5, "distribution": 5,
    "vix_term": 6, "vix_awaken": 5, "vvix_high": 3, "skew_high": 3, "vix9d_inverted": 3,
    "yield_shock": 5, "credit_divergence": 5,
    "fg_extreme_greed": 2, "fg_crack": 2, "pc_complacent": 3, "mania_flow": 3,
}
LABELS = {
    "ext200": "乖離過大：價格高於 200 日均線 >25%~60%",
    "ext20": "短線過熱：價格高於 20 日均線 >8%~20%",
    "parabolic20": "拋物線噴出：20 日漲幅 >20%~60%",
    "rsi_hot": "RSI(14) 超買 65→80",
    "bbw_high": "布林通道寬度處 1 年高檔 (波動擴張)",
    "macd_fade": "MACD 柱體連 3 日收斂 (動能衰竭)",
    "kd_death_high": "KD 高檔死叉 (D>70)",
    "break20": "首次跌破 20 日均線 (多頭停損線)",
    "rsi_divergence": "價創新高、RSI 未創高 (頂背離)",
    "distribution": "15 日內出現 3~6 個放量下跌『派發日』",
    "vix_term": "VIX 期限結構走平/倒掛 (VIX/VIX3M 0.88→1.00)",
    "vix_awaken": "VIX 從低檔 (≤18) 5 日急升 >25%",
    "vvix_high": "VVIX >95 (波動率的波動升溫)",
    "skew_high": "SKEW >140 (機構搶買尾部避險)",
    "vix9d_inverted": "VIX9D > VIX (近期事件恐慌)",
    "yield_shock": "10Y 殖利率 20 日急升 >20bps 且 >4.5%",
    "credit_divergence": "高收益債 HYG 10 日下跌而 SPY 未跌 (信用先行)",
    "fg_extreme_greed": "CNN Fear & Greed >60 (貪婪/極度貪婪)",
    "fg_crack": "Fear & Greed 5 日內從 ≥50 急跌 >12 分 (情緒裂縫)",
    "pc_complacent": "個股 Put/Call 5 日均 <0.60 (自滿)",
    "mania_flow": "SOXL/SOXS 資金比暴增且價格下跌 (散戶接刀狂潮)",
}
FAMILY = {
    "ext200": "A 過熱", "ext20": "A 過熱", "parabolic20": "A 過熱", "rsi_hot": "A 過熱", "bbw_high": "A 過熱",
    "macd_fade": "B 動能", "kd_death_high": "B 動能", "break20": "B 動能", "rsi_divergence": "B 動能", "distribution": "B 動能",
    "vix_term": "C 波動", "vix_awaken": "C 波動", "vvix_high": "C 波動", "skew_high": "C 波動", "vix9d_inverted": "C 波動",
    "yield_shock": "D 宏觀", "credit_divergence": "D 宏觀",
    "fg_extreme_greed": "E 情緒", "fg_crack": "E 情緒", "pc_complacent": "E 情緒", "mania_flow": "E 情緒",
}


def compute_daily_signals(
    soxl: list[dict],
    vix: dict[str, float], vix3m: dict[str, float], vix9d: dict[str, float], vvix: dict[str, float], skew: dict[str, float],
    treasury: list[dict] | None, fg_hist: list[dict] | None, pc_hist: list[dict] | None,
    hyg: list[dict] | None, spy: list[dict] | None, soxs: list[dict] | None,
) -> list[dict]:
  closes = [r["close"] for r in soxl]
  n = len(soxl)
  s20, s200 = ind.sma(closes, 20), ind.sma(closes, 200)
  rsi14 = ind.rsi(closes, 14)
  dif, dea, hist = ind.macd(closes)
  _, k9, d9, _ = ind.kdj(soxl, 9, 3, 3)
  bb = ind.bollinger(closes, 20, 2.0)
  v20 = ind.sma([float(r["volume"]) for r in soxl], 20)
  tre_by = {t["date"]: t for t in (treasury or [])}
  tre_dates = sorted(tre_by)
  fg_by = {f["date"]: f["score"] for f in (fg_hist or [])}
  fg_dates = sorted(fg_by)
  pc_by = {p["date"]: p for p in (pc_hist or []) if p.get("equity_pc")}
  pc_dates = sorted(pc_by)
  hyg_by = {r["date"]: r["close"] for r in (hyg or [])}
  spy_by = {r["date"]: r["close"] for r in (spy or [])}
  soxs_by = {r["date"]: r for r in (soxs or [])}
  dates = [r["date"] for r in soxl]

  def prev_val(by: dict, d: str, dates_sorted: list[str], back: int) -> float | None:
    # value `back` observations before date d within a sparse series
    import bisect
    i = bisect.bisect_right(dates_sorted, d) - 1 - back
    return by[dates_sorted[i]] if 0 <= i < len(dates_sorted) else None

  # Precompute distribution days & dollar-volume ratios
  dist_flag = [0] * n
  for i in range(1, n):
    if closes[i] < closes[i - 1] * 0.998 and v20[i] and soxl[i]["volume"] > v20[i]:
      dist_flag[i] = 1
  dv_ratio = [None] * n
  for i in range(n):
    s = soxs_by.get(dates[i])
    if s and s["close"] * s["volume"] > 0:
      dv_ratio[i] = closes[i] * soxl[i]["volume"] / (s["close"] * s["volume"])

  out = []
  start = max(205, n - 1300)
  for i in range(start, n):
    d = dates[i]
    c = closes[i]
    sig: dict[str, float | None] = {}
    # A. extension
    sig["ext200"] = _clip((ind.pct_change(c, s200[i]) - 25.0) / 35.0) if s200[i] else None
    sig["ext20"] = _clip((ind.pct_change(c, s20[i]) - 8.0) / 12.0) if s20[i] else None
    sig["parabolic20"] = _clip((ind.pct_change(c, closes[i - 20]) - 20.0) / 40.0)
    sig["rsi_hot"] = _clip((rsi14[i] - 65.0) / 15.0)
    bw_hist = [w for w in bb["width_pct"][max(0, i - 252) : i + 1] if w is not None]
    sig["bbw_high"] = _clip((ind.percentile_rank(bw_hist, bb["width_pct"][i]) - 80.0) / 20.0) if bb["width_pct"][i] is not None else None
    # B. roll-over
    fading = dif[i] > 0 and hist[i] < hist[i - 1] < hist[i - 2] and hist[i] < 0.6 * max(hist[i - 10 : i + 1])
    sig["macd_fade"] = 1.0 if fading else 0.0
    kd_dc = any((k9[j] < d9[j] and k9[j - 1] >= d9[j - 1] and d9[j] > 70) for j in range(i - 2, i + 1))
    sig["kd_death_high"] = 1.0 if kd_dc else 0.0
    first_break = False
    for j in range(i - 2, i + 1):
      if s20[j] and closes[j] < s20[j] and all((s20[m] and closes[m] > s20[m]) for m in range(j - 10, j)):
        first_break = True
    sig["break20"] = 1.0 if first_break else 0.0
    # RSI divergence: today (or within 5d) made a 20d closing high with RSI lower than at previous 20d-high (>= 10 days earlier)
    div = 0.0
    for j in range(i - 4, i + 1):
      win = closes[j - 20 : j + 1]
      if closes[j] >= max(win) and rsi14[j] < 70:
        # find prior local high in previous 10..40 days
        prior = max(range(j - 40, j - 9), key=lambda m: closes[m])
        if closes[j] > closes[prior] and rsi14[j] < rsi14[prior] - 4:
          div = 1.0
    sig["rsi_divergence"] = div
    sig["distribution"] = _clip((sum(dist_flag[i - 14 : i + 1]) - 2.0) / 4.0)
    # C. volatility structure
    v, v3, v9 = vix.get(d), vix3m.get(d), vix9d.get(d)
    sig["vix_term"] = _clip(((v / v3) - 0.88) / 0.12) if (v and v3) else None
    v_prev = vix.get(dates[i - 5]) if i >= 5 else None
    if v and v_prev:
      base_low = v_prev <= 18.0
      sig["vix_awaken"] = _clip((ind.pct_change(v, v_prev) - 10.0) / 30.0) if base_low else 0.0
    else:
      sig["vix_awaken"] = None
    vv, sk = vvix.get(d), skew.get(d)
    sig["vvix_high"] = _clip((vv - 95.0) / 20.0) if vv else None
    sig["skew_high"] = _clip((sk - 140.0) / 25.0) if sk else None
    sig["vix9d_inverted"] = _clip(((v9 / v) - 0.98) / 0.10) if (v and v9) else None
    # D. macro
    t_now = tre_by.get(d)
    if t_now and t_now.get("y10") is not None:
      y10_prev = prev_val({k: (tre_by[k]["y10"] or 0) for k in tre_by}, d, tre_dates, 20)
      chg_bps = (t_now["y10"] - y10_prev) * 100.0 if y10_prev else 0.0
      lvl_ok = t_now["y10"] >= 4.5
      y30_hist = [tre_by[k]["y30"] for k in tre_dates[max(0, tre_dates.index(d) - 252) : tre_dates.index(d) + 1] if tre_by[k].get("y30")]
      y30_high = ind.percentile_rank(y30_hist, t_now["y30"]) >= 97 if (y30_hist and t_now.get("y30")) else False
      sig["yield_shock"] = max(_clip((chg_bps - 10.0) / 30.0) if lvl_ok else 0.0, 1.0 if y30_high else 0.0)
    else:
      sig["yield_shock"] = None
    h_now, h_prev = hyg_by.get(d), hyg_by.get(dates[i - 10]) if i >= 10 else None
    p_now, p_prev = spy_by.get(d), spy_by.get(dates[i - 10]) if i >= 10 else None
    if h_now and h_prev and p_now and p_prev:
      h_ret, p_ret = ind.pct_change(h_now, h_prev), ind.pct_change(p_now, p_prev)
      sig["credit_divergence"] = _clip((-h_ret - 0.5) / 1.5) if p_ret >= -1.0 else 0.0
    else:
      sig["credit_divergence"] = None
    # E. sentiment
    f = fg_by.get(d)
    if f is not None:
      sig["fg_extreme_greed"] = _clip((f - 60.0) / 25.0)
      f_prev = prev_val(fg_by, d, fg_dates, 5)
      sig["fg_crack"] = _clip(((f_prev - f) - 8.0) / 15.0) if (f_prev is not None and f_prev >= 50) else 0.0
    else:
      sig["fg_extreme_greed"] = None
      sig["fg_crack"] = None
    if d in pc_by:
      idx = pc_dates.index(d)
      vals = [pc_by[k]["equity_pc"] for k in pc_dates[max(0, idx - 4) : idx + 1]]
      sig["pc_complacent"] = _clip((0.60 - statistics.mean(vals)) / 0.15)
    else:
      sig["pc_complacent"] = None
    if dv_ratio[i] and i >= 25:
      base = [x for x in dv_ratio[i - 20 : i] if x]
      if base:
        avg = statistics.mean(base)
        falling = ind.pct_change(c, closes[i - 5]) < 0
        sig["mania_flow"] = _clip((dv_ratio[i] / avg - 1.1) / 0.4) if falling else 0.0
      else:
        sig["mania_flow"] = None
    else:
      sig["mania_flow"] = None

    wsum = sum(WEIGHTS[k] for k, val in sig.items() if val is not None)
    raw = sum(WEIGHTS[k] * val for k, val in sig.items() if val is not None) / wsum * 100.0 if wsum else 0.0
    out.append({"date": d, "close": c, "raw": round(raw, 1), "score": round(raw, 1), "signals": sig,
                "n_active": sum(1 for val in sig.values() if val is not None and val >= 0.5),
                "above_200": bool(s200[i]) and c > s200[i]})
  return out


def calibrate(daily: list[dict], holdout_days: int = 60) -> dict:
  """Convert the raw symptom load into a percentile-based 0-100 Crash Risk Score.

  The reference distribution excludes the most recent `holdout_days` so that the
  latest episode cannot shape its own scale (pseudo out-of-sample)."""
  ref = sorted(x["raw"] for x in daily[:-holdout_days]) if len(daily) > holdout_days + 50 else sorted(x["raw"] for x in daily)
  n = len(ref)

  def pct(v: float) -> float:
    import bisect
    return bisect.bisect_right(ref, v) / n * 100.0 if n else 0.0

  for x in daily:
    x["score"] = round(pct(x["raw"]), 1)
  return {"ref_days": n, "p50": ref[n // 2] if n else None, "p80": ref[int(n * 0.8)] if n else None, "p90": ref[int(n * 0.9)] if n else None,
          "p95": ref[int(n * 0.95)] if n else None}


def zone(score: float) -> str:
  if score < 60:
    return "低風險 (症狀負荷低於歷史 60%)"
  if score < 80:
    return "注意 (高於歷史 60~80%)"
  return "警戒 (歷史前 20%，建議減碼 3x 部位)"


def event_study(daily: list[dict], soxl: list[dict], drop_pct: float = -20.0, horizon: int = 5, threshold: float = 80.0) -> dict:
  """Evaluate whether the calibrated score was elevated before large forward drawdowns.

  Episodes are split into 'top-type' (price above 200MA at the start — the regime
  the symptom list is designed for) and 'downtrend continuation' crashes."""
  closes = {r["date"]: r["close"] for r in soxl}
  dates = [r["date"] for r in soxl]
  idx = {d: i for i, d in enumerate(dates)}
  score_by = {x["date"]: x["score"] for x in daily}
  key = "fwd_min_%dd" % horizon
  events = []
  for x in daily:
    i = idx[x["date"]]
    if i + horizon >= len(dates):
      continue
    fwd = min(closes[dates[j]] for j in range(i + 1, i + horizon + 1)) / x["close"] - 1.0
    x[key] = round(fwd * 100.0, 1)
    if fwd * 100.0 <= drop_pct:
      events.append(x)
  episodes, last_i = [], -100
  for e in events:
    i = idx[e["date"]]
    if i - last_i >= 10:
      episodes.append(e)
    last_i = i
  ep_rows = []
  for e in episodes:
    i = idx[e["date"]]
    pre = [score_by.get(dates[j]) for j in range(max(0, i - 5), i + 1) if dates[j] in score_by]
    pre = [p for p in pre if p is not None]
    ep_rows.append({
        "date": e["date"], "close": round(e["close"], 2), "fwd_min_pct": e[key],
        "regime": "頂部型 (價在 200MA 上)" if e["above_200"] else "下跌延續型 (價在 200MA 下)",
        "top_type": e["above_200"],
        "score_t": e["score"], "score_max_prev5": round(max(pre), 1) if pre else None,
        "flagged": (max(pre) >= threshold) if pre else False,
        "top_signals": sorted([(k, round(v, 2)) for k, v in e["signals"].items() if v], key=lambda kv: -kv[1])[:4],
    })
  evaluable = [x for x in daily if key in x]
  pos_all = [x for x in evaluable if x[key] <= drop_pct]
  top_days = [x for x in evaluable if x["above_200"]]
  pos_top = [x for x in top_days if x[key] <= drop_pct]

  def stats(sample: list[dict], thr: float) -> dict:
    flagged = [x for x in sample if x["score"] >= thr]
    tp = sum(1 for x in flagged if x[key] <= drop_pct)
    pos = sum(1 for x in sample if x[key] <= drop_pct)
    return {"threshold": thr, "flag_days": len(flagged), "precision_pct": round(tp / len(flagged) * 100.0, 1) if flagged else None,
            "recall_pct": round(tp / pos * 100.0, 1) if pos else None, "base_rate_pct": round(pos / len(sample) * 100.0, 1) if sample else None,
            "lift": round((tp / len(flagged)) / (pos / len(sample)), 2) if (flagged and pos and sample) else None}

  buckets = []
  for lo, hi in ((0, 60), (60, 80), (80, 90), (90, 101)):
    sub = [x for x in top_days if lo <= x["score"] < hi]
    if not sub:
      continue
    fw = [x[key] for x in sub]
    buckets.append({"bucket": f"{lo}-{min(hi, 100)}", "days": len(sub),
                    "pct_crash": round(sum(1 for v in fw if v <= drop_pct) / len(sub) * 100.0, 1),
                    "pct_drop10": round(sum(1 for v in fw if v <= -10.0) / len(sub) * 100.0, 1),
                    "median_fwd_min": round(statistics.median(fw), 1)})
  top_eps = [r for r in ep_rows if r["top_type"]]
  # Alert-episode view: cluster consecutive flagged days (gap >= 5) and ask whether a
  # >=20% drawdown (5-day window) started within the next 15 trading days.
  flagged_days = sorted((idx[x["date"]] for x in top_days if x["score"] >= threshold))
  alert_starts, last_i = [], -100
  for i in flagged_days:
    if i - last_i >= 5:
      alert_starts.append(i)
    last_i = i
  crash_starts = {idx[e["date"]] for e in events}
  alerts_followed = sum(1 for a in alert_starts if any((a <= c <= a + 15) for c in crash_starts))
  return {
      "alert_episodes": len(alert_starts), "alert_episodes_followed_by_crash": alerts_followed,
      "alert_hit_rate_pct": round(alerts_followed / len(alert_starts) * 100.0, 1) if alert_starts else None,
      "drop_pct": drop_pct, "horizon_days": horizon, "threshold": threshold,
      "n_days": len(evaluable), "n_event_days": len(pos_all), "n_episodes": len(episodes),
      "episodes_per_year": round(len(episodes) / (len(evaluable) / 252.0), 1) if evaluable else None,
      "episodes": ep_rows,
      "n_top_episodes": len(top_eps), "top_episodes_flagged": sum(1 for r in top_eps if r["flagged"]),
      "n_down_episodes": len(ep_rows) - len(top_eps), "down_episodes_flagged": sum(1 for r in ep_rows if (not r["top_type"]) and r["flagged"]),
      "stats_top_80": stats(top_days, 80.0), "stats_top_90": stats(top_days, 90.0), "stats_all_80": stats(evaluable, 80.0),
      "buckets_top": buckets,
  }


def analog_forecast(soxl: list[dict], vix: dict[str, float], fg_hist: list[dict] | None) -> dict:
  """Historical base rates: what happened after conditions similar to today."""
  closes = [r["close"] for r in soxl]
  dates = [r["date"] for r in soxl]
  n = len(closes)
  rsi14 = ind.rsi(closes, 14)
  s200 = ind.sma(closes, 200)
  s50 = ind.sma(closes, 50)
  s20 = ind.sma(closes, 20)
  _, k9, d9, _ = ind.kdj(soxl, 9, 3, 3)
  fg_by = {f["date"]: f["score"] for f in (fg_hist or [])}
  hi52 = [max(closes[max(0, i - 251) : i + 1]) for i in range(n)]
  today = n - 1
  cur = {
      "ret_5d": ind.pct_change(closes[today], closes[today - 5]),
      "ret_10d": ind.pct_change(closes[today], closes[today - 10]),
      "rsi14": rsi14[today],
      "dist200": ind.pct_change(closes[today], s200[today]) if s200[today] else 0.0,
      "dd52": ind.pct_change(closes[today], hi52[today]),
      "vix": vix.get(dates[today]),
      "fg": fg_by.get(dates[today]),
  }
  conds = {
      "【事前訊號】20 日漲幅 ≥40% 後出現單日跌 ≥8% (噴出後首根長黑)": lambda i: ind.pct_change(closes[i - 1], closes[i - 21]) >= 40.0 and ind.pct_change(closes[i], closes[i - 1]) <= -8.0,
      "【事前訊號】價格高於 200MA ≥30% 且首次跌破 20MA": lambda i: bool(s200[i]) and ind.pct_change(closes[i], s200[i]) >= 30.0 and bool(s20[i]) and closes[i] < s20[i] and all(bool(s20[m]) and closes[m] > s20[m] for m in range(i - 10, i)),
      "【事前訊號】KD 高檔死叉 (D>70) 且當日跌 ≥5%": lambda i: k9[i] < d9[i] and k9[i - 1] >= d9[i - 1] and d9[i] > 70 and ind.pct_change(closes[i], closes[i - 1]) <= -5.0,
      "5 日跌幅 ≤ -20% (急跌後)": lambda i: ind.pct_change(closes[i], closes[i - 5]) <= -20.0,
      "10 日跌幅 ≤ -30% (崩跌後)": lambda i: ind.pct_change(closes[i], closes[i - 10]) <= -30.0,
      "RSI(14) < 25 (極度超賣)": lambda i: rsi14[i] < 25.0,
      "距 52 週高點回撤 ≥ 40% 且 VIX ≥ 20": lambda i: ind.pct_change(closes[i], hi52[i]) <= -40.0 and (vix.get(dates[i]) or 0) >= 20.0,
      "跌破 200 日均線 >10% (趨勢受損)": lambda i: bool(s200[i]) and ind.pct_change(closes[i], s200[i]) <= -10.0,
      "CNN Fear & Greed < 20 (極度恐懼)": lambda i: (fg_by.get(dates[i]) is not None) and fg_by[dates[i]] < 20.0,
  }
  horizons = (5, 10, 20, 60)
  results = []
  for name, fn in conds.items():
    hits, episodes = [], []
    last = -100
    for i in range(210, n - 60):
      try:
        ok = fn(i)
      except Exception:  # noqa: BLE001
        ok = False
      if not ok:
        continue
      hits.append(i)
      if i - last >= 10:
        episodes.append(i)
      last = i
    row = {"condition": name, "n_days": len(hits), "n_episodes": len(episodes), "horizons": {}, "sufficient": len(hits) >= 8}
    try:
      row["active_today"] = bool(fn(today))
    except Exception:  # noqa: BLE001
      row["active_today"] = False
    for h in horizons:
      fw = [ind.pct_change(closes[i + h], closes[i]) for i in hits]
      if not fw:
        continue
      q = ind.quantiles(fw, (0.25, 0.5, 0.75))
      row["horizons"][f"{h}d"] = {"median": round(q["p50"], 1), "p25": round(q["p25"], 1), "p75": round(q["p75"], 1),
                                 "pct_positive": round(sum(1 for v in fw if v > 0) / len(fw) * 100.0, 0),
                                 "pct_up10": round(sum(1 for v in fw if v >= 10.0) / len(fw) * 100.0, 0),
                                 "pct_down10": round(sum(1 for v in fw if v <= -10.0) / len(fw) * 100.0, 0),
                                 "worst": round(min(fw), 1), "best": round(max(fw), 1)}
    results.append(row)
  # Unconditional baseline
  base = {"condition": "全部交易日 (基準)", "n_days": n - 270, "n_episodes": None, "active_today": True, "horizons": {}}
  for h in horizons:
    fw = [ind.pct_change(closes[i + h], closes[i]) for i in range(210, n - 60)]
    q = ind.quantiles(fw, (0.25, 0.5, 0.75))
    base["horizons"][f"{h}d"] = {"median": round(q["p50"], 1), "p25": round(q["p25"], 1), "p75": round(q["p75"], 1),
                                "pct_positive": round(sum(1 for v in fw if v > 0) / len(fw) * 100.0, 0),
                                "pct_up10": round(sum(1 for v in fw if v >= 10.0) / len(fw) * 100.0, 0),
                                "pct_down10": round(sum(1 for v in fw if v <= -10.0) / len(fw) * 100.0, 0),
                                "worst": round(min(fw), 1), "best": round(max(fw), 1)}
  results.append(base)
  return {"current": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in cur.items()}, "conditions": results,
          "sample_range": f"{dates[210]} ~ {dates[n - 61]}"}


def peak_checklist(daily: list[dict], soxl: list[dict], lookback: int = 30) -> dict:
  """Signal states around the most recent top (highest close in the last `lookback` bars):
  2 sessions before the peak through 6 sessions after it."""
  recent = soxl[-lookback:]
  peak = max(recent, key=lambda r: r["close"])
  dates = [x["date"] for x in daily]
  if peak["date"] not in dates:
    return {}
  pi = dates.index(peak["date"])
  cols = [daily[j] for j in range(max(0, pi - 2), min(len(daily), pi + 7))]
  rows = []
  for key in WEIGHTS:
    vals = [c["signals"].get(key) for c in cols]
    if all(v is None for v in vals):
      continue
    first_on = next((c["date"] for c, v in zip(cols, vals) if (v or 0) >= 0.5), None)
    rows.append({"key": key, "family": FAMILY[key], "label": LABELS[key], "weight": WEIGHTS[key],
                 "values": [None if v is None else round(v, 2) for v in vals],
                 "flashed": any((v or 0) >= 0.5 for v in vals), "first_on": first_on})
  trough = min(soxl[soxl.index(peak):], key=lambda r: r["close"])
  return {
      "peak_date": peak["date"], "peak_close": round(peak["close"], 2),
      "trough_date": trough["date"], "trough_close": round(trough["close"], 2),
      "drawdown_pct": round(ind.pct_change(trough["close"], peak["close"]), 1),
      "columns": [c["date"] for c in cols], "scores": [c["score"] for c in cols], "raw_scores": [c["raw"] for c in cols],
      "rows": rows, "n_flashed": sum(1 for r in rows if r["flashed"]), "n_total": len(rows),
  }


def analyze(soxl: list[dict], vixc: dict, treasury: list[dict] | None, fg_hist: list[dict] | None, pc_hist: list[dict] | None,
            hyg: list[dict] | None, spy: list[dict] | None, soxs: list[dict] | None) -> dict:
  def series(name: str) -> dict[str, float]:
    return {r["date"]: r["close"] for r in vixc.get(name, [])}

  vix, vix3m, vix9d, vvix, skew = series("VIX"), series("VIX3M"), series("VIX9D"), series("VVIX"), series("SKEW")
  daily = compute_daily_signals(soxl, vix, vix3m, vix9d, vvix, skew, treasury, fg_hist, pc_hist, hyg, spy, soxs)
  calib = calibrate(daily)
  study = event_study(daily, soxl)
  analogs = analog_forecast(soxl, vix, fg_hist)
  check = peak_checklist(daily, soxl)
  today = daily[-1]
  contributions = sorted(
      [{"key": k, "label": LABELS[k], "family": FAMILY[k], "value": round(v, 2), "weight": WEIGHTS[k], "points": round(v * WEIGHTS[k], 1)}
       for k, v in today["signals"].items() if v is not None],
      key=lambda x: -x["points"])
  chart = [{"date": x["date"], "close": round(x["close"], 2), "score": x["score"], "raw": x["raw"]} for x in daily[-130:]]
  z = zone(today["score"])
  if not today["above_200"]:
    z += "；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆"
  return {
      "today": {"date": today["date"], "score": today["score"], "raw": today["raw"], "zone": z, "n_active": today["n_active"],
                "above_200": today["above_200"]},
      "calibration": calib,
      "contributions": contributions, "chart": chart, "event_study": study, "analogs": analogs, "peak_checklist": check,
      "weights": WEIGHTS, "labels": LABELS, "family": FAMILY,
      "score_history_90d": [{"date": x["date"], "score": x["score"], "raw": x["raw"]} for x in daily[-90:]],
  }
