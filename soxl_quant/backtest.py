#!/usr/bin/env python3
"""Signal library + walk-forward validation for SOXL (stdlib only).

Why this exists
  "Buy point" and "sell point" must be rules whose historical hit rate can be
  re-verified on every run, not adjectives.  Each signal here is a fixed rule
  (no run-time fitting).  For every signal the engine reports how often it
  worked, on how many independent trades, in-sample vs out-of-sample, year by
  year, and whether a parameter nudge destroys the edge.

Conventions (identical for every signal)
  * A signal is evaluated on bar ``i`` using data up to and including bar ``i``.
  * The trade enters at the next session's open (``open[i+1]``) and exits at the
    close ``h`` sessions after the signal (``close[i+h]``).  ``h`` is the
    signal's horizon.
  * Trades are de-clustered: after a signal fires, the next ``h`` bars cannot
    start a new trade, so N counts non-overlapping trades.
  * Long signals win when the trade return is > 0.  Exit signals "win" when the
    forward return is <= 0 (selling avoided a loss).
  * Base rate = the same statistic over every bar in the evaluation window.
  * Out-of-sample = the most recent 40% of the evaluation window; the signal
    rules were fixed before this run, so the split is a stability check, not a
    fit/validate split.
  * MAE (maximum adverse excursion) is measured on intraday lows after entry and
    expressed in ATR(14) units; the 75th percentile MAE of *winning* trades is
    the data-driven stop distance for that signal.

Grades (fixed thresholds, printed next to every number)
  A 可靠   N >= 30, OOS N >= 10, OOS win >= 60% and >= base + 5 pts, PF >= 1.5,
           |IS win - OOS win| <= 12 pts, every variant beats the base rate, AND the
           one-sided binomial test of wins against the base rate has p < 0.05.
  B 尚可   N >= 20, OOS N >= 8, OOS win >= base + 3 pts, PF >= 1.2.
  B* 顯著但樣本薄  p < 0.05 and N >= 20 but OOS N < 8 (significant, thin out-of-sample).
  C 無優勢 anything else with enough samples.
  — 樣本不足  N < 20 (or OOS N < 8 without significance).
  Every signal also carries ``p_value`` (exact binomial, one-sided, vs its own base rate) and
  ``q_value`` (Benjamini-Hochberg across all graded signals) so the reader can see how many of
  the "edges" survive multiple testing.

Two evaluation modes
  * fixed horizon (all signals): exit at close[i+h].
  * dynamic exit (mean-reversion buys, ``dyn``): exit at the first close above SMA5, capped at
    10 bars.  Its base rate is computed with the same exit rule on every bar, because the exit
    itself selects up-days (base ≈ 64% on SOXL, not 55%).
  Exit signals are additionally scored on ``dd15``: how often a drawdown of at least 15% from
  the next open happened within 20 bars (what a sell signal is supposed to avoid).
"""

from __future__ import annotations

import math
import statistics

from . import indicators as ind

OOS_FRACTION = 0.40
MIN_N_GRADE = 20
MIN_N_OOS = 8
WARMUP = 210  # bars needed before the first evaluation (SMA200 + slack)


# --------------------------------------------------------------------------- #
# statistics helpers
# --------------------------------------------------------------------------- #
def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
  """95% Wilson score interval for a proportion, in percent."""
  if n <= 0:
    return (0.0, 0.0)
  p = wins / n
  denom = 1.0 + z * z / n
  centre = (p + z * z / (2 * n)) / denom
  half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
  return (round(max(0.0, centre - half) * 100.0, 1), round(min(1.0, centre + half) * 100.0, 1))


def binom_p_greater(wins: int, n: int, p0: float) -> float | None:
  """Exact one-sided binomial p-value: P(X >= wins | n, p0)."""
  if n <= 0 or p0 is None or not (0.0 < p0 < 1.0):
    return None
  p = 0.0
  for k in range(wins, n + 1):
    p += math.comb(n, k) * (p0 ** k) * ((1.0 - p0) ** (n - k))
  return round(min(1.0, max(0.0, p)), 4)


def bh_qvalues(pvals: list[float | None]) -> list[float | None]:
  """Benjamini-Hochberg adjusted p-values (q); None entries stay None."""
  idx = [i for i, p in enumerate(pvals) if p is not None]
  m = len(idx)
  out: list[float | None] = [None] * len(pvals)
  if not m:
    return out
  order = sorted(idx, key=lambda i: pvals[i])
  prev = 1.0
  for rank in range(m, 0, -1):
    i = order[rank - 1]
    q = min(prev, pvals[i] * m / rank)
    out[i] = round(q, 4)
    prev = q
  return out


def _pf(rets: list[float]) -> float | None:
  gains = sum(r for r in rets if r > 0)
  losses = -sum(r for r in rets if r < 0)
  if losses <= 1e-12:
    return None if gains <= 0 else 99.0
  return round(gains / losses, 2)


def _stats(rets: list[float], good) -> dict:
  if not rets:
    return {"n": 0, "win_pct": None, "ci": None, "mean": None, "median": None, "pf": None, "worst": None, "best": None}
  wins = sum(1 for r in rets if good(r))
  lo, hi = wilson_ci(wins, len(rets))
  return {"n": len(rets), "win_pct": round(wins / len(rets) * 100.0, 1), "ci": [lo, hi],
          "mean": round(statistics.mean(rets), 2), "median": round(statistics.median(rets), 2),
          "pf": _pf(rets), "worst": round(min(rets), 1), "best": round(max(rets), 1)}


def _roll_max(arr: list[float], w: int, include_today: bool = True) -> list[float | None]:
  out: list[float | None] = []
  for i in range(len(arr)):
    end = i + 1 if include_today else i
    start = end - w
    out.append(max(arr[start:end]) if start >= 0 and end > start else None)
  return out


def _roll_min(arr: list[float], w: int, include_today: bool = True) -> list[float | None]:
  out: list[float | None] = []
  for i in range(len(arr)):
    end = i + 1 if include_today else i
    start = end - w
    out.append(min(arr[start:end]) if start >= 0 and end > start else None)
  return out


# --------------------------------------------------------------------------- #
# context: every series a rule may read, computed once
# --------------------------------------------------------------------------- #
def build_context(rows: list[dict], vix: dict[str, float] | None = None, vix3m: dict[str, float] | None = None,
                  ews_scores: dict[str, float] | None = None) -> dict:
  dates = [r["date"] for r in rows]
  o = [float(r["open"]) for r in rows]
  h = [float(r["high"]) for r in rows]
  l = [float(r["low"]) for r in rows]
  c = [float(r["close"]) for r in rows]
  v = [float(r["volume"]) for r in rows]
  n = len(rows)
  ctx: dict = {"dates": dates, "o": o, "h": h, "l": l, "c": c, "v": v, "n": n}
  ctx["sma5"], ctx["sma20"], ctx["sma50"], ctx["sma200"] = ind.sma(c, 5), ind.sma(c, 20), ind.sma(c, 50), ind.sma(c, 200)
  ctx["ema10"] = ind.ema(c, 10)
  ctx["rsi2"], ctx["rsi14"] = ind.rsi(c, 2), ind.rsi(c, 14)
  ctx["atr14"], ctx["atr22"] = ind.atr(rows, 14), ind.atr(rows, 22)
  bb = ind.bollinger(c, 20, 2.0)
  ctx["bb_lower"], ctx["bb_upper"], ctx["bb_pct_b"] = bb["lower"], bb["upper"], bb["pct_b"]
  _, _, ctx["macd_hist"] = ind.macd(c)
  _, ctx["k9"], ctx["d9"], _ = ind.kdj(rows, 9, 3, 3)
  ctx["v20"] = ind.sma(v, 20)
  ctx["hh20_prev"] = _roll_max(h, 20, include_today=False)
  ctx["hh22"] = _roll_max(h, 22, include_today=True)
  ctx["ll7_close"] = _roll_min(c, 7, include_today=True)
  ctx["ll20_low"] = _roll_min(l, 20, include_today=True)
  ctx["ll20_close_prev"] = _roll_min(c, 20, include_today=False)
  ret1 = [0.0] + [ind.pct_change(c[i], c[i - 1]) for i in range(1, n)]
  ctx["ret1"] = ret1
  ctx["ret20"] = [ind.pct_change(c[i], c[i - 20]) if i >= 20 else 0.0 for i in range(n)]
  # distribution days (O'Neil): down >= 0.2% on volume above the 20-day average
  ctx["dist"] = [1 if (i > 0 and c[i] < c[i - 1] * 0.998 and ctx["v20"][i] and v[i] > ctx["v20"][i]) else 0 for i in range(n)]
  # volatility complex aligned to SOXL dates (None when the series has no value that day)
  vix = vix or {}
  vix3m = vix3m or {}
  ctx["vix"] = [vix.get(d) for d in dates]
  ctx["vix_ratio"] = [(vix[d] / vix3m[d]) if (vix.get(d) and vix3m.get(d)) else None for d in dates]
  ctx["has_vix"] = sum(1 for x in ctx["vix_ratio"] if x is not None) >= 500
  ews_scores = ews_scores or {}
  ctx["ews"] = [ews_scores.get(d) for d in dates]
  ctx["has_ews"] = sum(1 for x in ctx["ews"] if x is not None) >= 500
  return ctx


# --------------------------------------------------------------------------- #
# rule helpers
# --------------------------------------------------------------------------- #
def _above200(ctx: dict, i: int) -> bool:
  s = ctx["sma200"][i]
  return bool(s) and ctx["c"][i] > s


def _below200(ctx: dict, i: int) -> bool:
  s = ctx["sma200"][i]
  return bool(s) and ctx["c"][i] < s


def _consec_down(ctx: dict, i: int, k: int) -> bool:
  c = ctx["c"]
  return i >= k and all(c[j] < c[j - 1] for j in range(i - k + 1, i + 1))


def _vix_ratio_max(ctx: dict, i: int, w: int) -> float | None:
  vals = [x for x in ctx["vix_ratio"][max(0, i - w + 1): i + 1] if x is not None]
  return max(vals) if vals else None


def _vix_max(ctx: dict, i: int, w: int) -> float | None:
  vals = [x for x in ctx["vix"][max(0, i - w + 1): i + 1] if x is not None]
  return max(vals) if vals else None


def _rally_attempt_day(ctx: dict, i: int) -> int:
  """IBD-style rally attempt counter. Day 1 = first close above the prior close after a 20-day
  closing low.  Returns 0 when no attempt is alive (the low was undercut or no low in 60 bars)."""
  c, l = ctx["c"], ctx["l"]
  j = i
  while j > 0 and not (ctx["ll20_close_prev"][j] is not None and c[j] <= ctx["ll20_close_prev"][j]):
    j -= 1
    if i - j > 60:
      return 0
  low_px = l[j]
  day = 0
  for k in range(j + 1, i + 1):
    if l[k] < low_px:  # undercut -> attempt resets
      return 0
    if day == 0:
      if c[k] > c[k - 1]:
        day = 1
    else:
      day += 1
  return day


# --------------------------------------------------------------------------- #
# trigger-price helpers (what close tomorrow would fire the rule)
# --------------------------------------------------------------------------- #
def _sma20_tomorrow_cross(ctx: dict) -> float:
  """Close C tomorrow such that C == SMA20(tomorrow): SMA20' = SMA20 + (C - c[-20]) / 20."""
  c, s = ctx["c"], ctx["sma20"][-1]
  return (s - c[-20] / 20.0) / (1.0 - 1.0 / 20.0)


def _rsi_threshold_close(ctx: dict, period: int, target: float) -> float:
  """Close tomorrow below which Wilder RSI(period) < target (assumes a down day)."""
  c = ctx["c"]
  n = len(c)
  gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, period + 1)]
  losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, period + 1)]
  ag, al = sum(gains) / period, sum(losses) / period
  for i in range(period + 1, n):
    d = c[i] - c[i - 1]
    ag = (ag * (period - 1) + max(d, 0.0)) / period
    al = (al * (period - 1) + max(-d, 0.0)) / period
  rs_t = target / (100.0 - target)  # RSI < target  <=>  RS < rs_t
  # down day: ag' = ag*(p-1)/p ; al' = (al*(p-1) + x)/p ; need ag'/al' < rs_t  ->  x > ag*(p-1)/rs_t - al*(p-1)
  x = max(0.0, ag * (period - 1) / rs_t - al * (period - 1))
  return c[-1] - x


# --------------------------------------------------------------------------- #
# signal library
# --------------------------------------------------------------------------- #
SHORT_NAMES = {
    "rsi2_lt10_above200": "RSI2<10 年線上", "rsi2_lt5_any": "RSI2<5", "rsi14_lt25": "RSI14<25", "bb_lower_reentry": "布林下軌回收",
    "three_down_sma5": "連3黑收5MA下", "double7_above200": "7日新低年線上", "capitulation_reversal": "投降量反轉", "ftd": "IBD跟進日",
    "reclaim_sma20": "站回20MA", "vix_term_normalize": "VIX倒掛回正", "vix_spike_fade": "VIX高峰回落", "macd_cross_up_below200": "MACD翻正年線下",
    "kd_golden_low": "KD低檔金叉", "golden_cross_20_50": "20MA上穿50MA", "breakout20_above200": "帶量破20日高",
    "first_close_below_sma20": "首破20MA", "chandelier_3atr": "吊燈3ATR", "distribution_4in25": "派發日第4個", "parabolic_blowoff": "拋物線噴出",
    "rsi14_gt80": "RSI14>80", "kd_death_high": "KD高檔死叉", "vix_term_invert_first": "VIX首次倒掛", "death_cross_50_200": "死亡交叉", "ews_ge80": "前兆分數≥80",
}


def _sig(key, name, family, side, horizon, rule, fn, trigger=None, variants=(), needs=()):
  return {"key": key, "name": name, "short_name": SHORT_NAMES.get(key, name[:10]), "family": family, "side": side, "horizon": horizon, "rule": rule,
          "fn": fn, "trigger": trigger, "variants": list(variants), "needs": tuple(needs)}


def _rsi2_rule(th: float, regime: str):
  def fn(ctx, i):
    ok = ctx["rsi2"][i] < th
    if regime == "above":
      return ok and _above200(ctx, i)
    return ok
  return fn


def _rsi14_rule(th: float):
  return lambda ctx, i: ctx["rsi14"][i] < th


def _bb_reentry(ctx, i):
  lo, lo_p = ctx["bb_lower"][i], ctx["bb_lower"][i - 1] if i else None
  return bool(lo and lo_p) and ctx["c"][i - 1] < lo_p and ctx["c"][i] > lo


def _three_down_sma5(ctx, i):
  s5 = ctx["sma5"][i]
  return bool(s5) and _consec_down(ctx, i, 3) and ctx["c"][i] < s5 and _above200(ctx, i)


def _double7(ctx, i):
  return ctx["ll7_close"][i] is not None and ctx["c"][i] <= ctx["ll7_close"][i] and _above200(ctx, i)


def _capitulation_reversal(ctx, i):
  """Within the last 3 bars a capitulation day (volume >= 2x 20d avg, close <= -8%); today closes above that day's high."""
  for j in range(max(1, i - 3), i):
    if ctx["v20"][j] and ctx["v"][j] >= 2.0 * ctx["v20"][j] and ctx["ret1"][j] <= -8.0 and ctx["c"][i] > ctx["h"][j]:
      return True
  return False


def _ftd(ctx, i, pct: float = 4.0):
  day = _rally_attempt_day(ctx, i)
  return day >= 4 and ctx["ret1"][i] >= pct and ctx["v"][i] > ctx["v"][i - 1]


def _reclaim_sma20(ctx, i, quiet: int = 10):
  s = ctx["sma20"]
  if not (s[i] and ctx["c"][i] > s[i]):
    return False
  return i >= quiet and all(s[j] and ctx["c"][j] <= s[j] for j in range(i - quiet, i))


def _vix_term_normalize(ctx, i, peak: float = 1.0, back: float = 0.95):
  r = ctx["vix_ratio"][i]
  if r is None or r >= back:
    return False
  mx = _vix_ratio_max(ctx, i - 1, 10)
  if mx is None or mx < peak:
    return False
  prev = ctx["vix_ratio"][i - 1]
  return prev is None or prev >= back  # first day back under the threshold


def _vix_spike_fade(ctx, i, spike: float = 30.0, fade: float = 0.8):
  v = ctx["vix"][i]
  mx = _vix_max(ctx, i - 1, 10)
  if v is None or mx is None or mx < spike or v > fade * mx:
    return False
  vp = ctx["vix"][i - 1]
  mxp = _vix_max(ctx, i - 2, 10)
  already = vp is not None and mxp is not None and mxp >= spike and vp <= fade * mxp
  return not already


def _macd_cross_up_below200(ctx, i):
  hst = ctx["macd_hist"]
  return hst[i - 1] <= 0 < hst[i] and _below200(ctx, i)


def _golden_cross_20_50(ctx, i):
  s20, s50 = ctx["sma20"], ctx["sma50"]
  return bool(s20[i] and s50[i] and s20[i - 1] and s50[i - 1]) and s20[i - 1] <= s50[i - 1] and s20[i] > s50[i]


def _breakout20(ctx, i, rvol: float = 1.2):
  hh = ctx["hh20_prev"][i]
  return bool(hh) and ctx["c"][i] > hh and _above200(ctx, i) and bool(ctx["v20"][i]) and ctx["v"][i] >= rvol * ctx["v20"][i]


def _kd_golden_low(ctx, i, lvl: float = 20.0):
  k, d = ctx["k9"], ctx["d9"]
  return k[i - 1] <= d[i - 1] and k[i] > d[i] and k[i - 1] < lvl


# ---- exits
def _first_close_below_sma20(ctx, i, quiet: int = 10):
  s = ctx["sma20"]
  if not (s[i] and ctx["c"][i] < s[i]):
    return False
  return i >= quiet and all(s[j] and ctx["c"][j] >= s[j] for j in range(i - quiet, i))


def _chandelier(ctx, i, k: float = 3.0):
  hh, a = ctx["hh22"][i], ctx["atr22"][i]
  if not hh or not a:
    return False
  lvl = hh - k * a
  if ctx["c"][i] >= lvl:
    return False
  hp, ap = ctx["hh22"][i - 1], ctx["atr22"][i - 1]
  return not (hp and ap and ctx["c"][i - 1] < hp - k * ap)  # first day below


def _distribution_cluster(ctx, i, k: int = 4, w: int = 25):
  if i < w:
    return False
  s50 = ctx["sma50"][i]
  return sum(ctx["dist"][i - w + 1: i + 1]) >= k and bool(s50) and ctx["c"][i] > s50 and sum(ctx["dist"][i - w: i]) < k


def _parabolic(ctx, i, run: float = 40.0, ext: float = 15.0):
  s = ctx["sma20"][i]
  return bool(s) and ctx["ret20"][i] >= run and ind.pct_change(ctx["c"][i], s) >= ext


def _rsi14_hot(ctx, i, th: float = 80.0):
  return ctx["rsi14"][i] > th and ctx["rsi14"][i - 1] <= th


def _kd_death_high(ctx, i, lvl: float = 75.0):
  k, d = ctx["k9"], ctx["d9"]
  return k[i - 1] >= d[i - 1] and k[i] < d[i] and d[i] > lvl


def _vix_term_invert_first(ctx, i, th: float = 1.0):
  r = ctx["vix_ratio"][i]
  if r is None or r < th:
    return False
  prev = [x for x in ctx["vix_ratio"][max(0, i - 5): i] if x is not None]
  return bool(prev) and all(x < th for x in prev)


def _death_cross_50_200(ctx, i):
  s50, s200 = ctx["sma50"], ctx["sma200"]
  return bool(s50[i] and s200[i] and s50[i - 1] and s200[i - 1]) and s50[i - 1] >= s200[i - 1] and s50[i] < s200[i]


def _ews_hot(ctx, i, th: float = 80.0):
  e = ctx["ews"][i]
  if e is None or e < th:
    return False
  prev = ctx["ews"][i - 1]
  return prev is None or prev < th


def signal_library() -> list[dict]:
  L_REV, L_TREND, X_EXIT = "反轉買點", "趨勢買點", "賣出 / 出場"
  S: list[dict] = []
  S.append(_sig("rsi2_lt10_above200", "RSI(2) < 10 且價在 200 日線上（Connors）", L_REV, "long", 5,
                "RSI(2) 跌破 10，且收盤仍在 200 日均線之上；5 個交易日後結算", _rsi2_rule(10.0, "above"),
                trigger=lambda ctx: {"price": _rsi_threshold_close(ctx, 2, 10.0), "op": "<=", "needs": "且收盤 > 200MA"} if _above200(ctx, ctx["n"] - 1) else None,
                variants=[("RSI(2) < 5", _rsi2_rule(5.0, "above")), ("RSI(2) < 15", _rsi2_rule(15.0, "above"))]))
  S.append(_sig("rsi2_lt5_any", "RSI(2) < 5（極度超賣，不分多空）", L_REV, "long", 5,
                "RSI(2) 跌破 5；不看均線；5 個交易日後結算", _rsi2_rule(5.0, "any"),
                trigger=lambda ctx: {"price": _rsi_threshold_close(ctx, 2, 5.0), "op": "<="},
                variants=[("RSI(2) < 3", _rsi2_rule(3.0, "any")), ("RSI(2) < 8", _rsi2_rule(8.0, "any"))]))
  S.append(_sig("rsi14_lt25", "RSI(14) < 25（極度超賣）", L_REV, "long", 10,
                "RSI(14) 跌破 25；10 個交易日後結算", _rsi14_rule(25.0),
                trigger=lambda ctx: {"price": _rsi_threshold_close(ctx, 14, 25.0), "op": "<="},
                variants=[("RSI(14) < 20", _rsi14_rule(20.0)), ("RSI(14) < 30", _rsi14_rule(30.0))]))
  S.append(_sig("bb_lower_reentry", "布林下軌回收（昨收在下軌外、今收回軌內）", L_REV, "long", 10,
                "昨日收盤 < 下軌，今日收盤 > 下軌；10 個交易日後結算", _bb_reentry,
                trigger=lambda ctx: {"price": ctx["bb_lower"][-1], "op": ">", "needs": "前提：今日收盤已在下軌之外"} if (ctx["bb_lower"][-1] and ctx["c"][-1] < ctx["bb_lower"][-1]) else None))
  S.append(_sig("three_down_sma5", "連 3 黑且收在 5 日線下、價在 200 日線上（Connors）", L_REV, "long", 5,
                "連續 3 日收黑、收盤 < 5MA、收盤 > 200MA；5 個交易日後結算", _three_down_sma5))
  S.append(_sig("double7_above200", "7 日新低、價在 200 日線上（Double 7s）", L_REV, "long", 7,
                "收盤創 7 日新低且仍在 200MA 之上；7 個交易日後結算", _double7,
                trigger=lambda ctx: {"price": ctx["ll7_close"][-1], "op": "<=", "needs": "且收盤 > 200MA"} if _above200(ctx, ctx["n"] - 1) else None))
  S.append(_sig("capitulation_reversal", "投降量反轉（爆量長黑後 3 日內收復該日高點）", L_REV, "long", 10,
                "某日量 ≥ 2 倍 20 日均量且跌 ≥ 8%，之後 3 日內收盤站上該日最高價；10 個交易日後結算", _capitulation_reversal,
                trigger=lambda ctx: next(({"price": ctx["h"][j], "op": ">", "needs": f"{ctx['dates'][j]} 為投降日"} for j in range(ctx["n"] - 3, ctx["n"]) if j > 0 and ctx["v20"][j] and ctx["v"][j] >= 2.0 * ctx["v20"][j] and ctx["ret1"][j] <= -8.0), None)))
  S.append(_sig("ftd", "IBD 跟進日（反彈第 4 日起單日 ≥ +4% 且量增）", L_REV, "long", 20,
                "20 日新低後反彈嘗試第 4 日起，單日收漲 ≥ 4% 且成交量 > 前一日；20 個交易日後結算", _ftd,
                trigger=lambda ctx: {"price": ctx["c"][-1] * 1.04, "op": ">=", "needs": f"反彈嘗試第 {_rally_attempt_day(ctx, ctx['n'] - 1) + 1} 日，量需 > {ctx['v'][-1] / 1e6:.0f}M"} if _rally_attempt_day(ctx, ctx["n"] - 1) >= 3 else None,
                variants=[("≥ +3%", lambda ctx, i: _ftd(ctx, i, 3.0)), ("≥ +5%", lambda ctx, i: _ftd(ctx, i, 5.0))]))
  S.append(_sig("reclaim_sma20", "站回 20 日線（之前連續 ≥ 10 日在線下）", L_TREND, "long", 20,
                "收盤站回 20MA，且先前至少 10 個交易日都收在 20MA 之下；20 個交易日後結算", _reclaim_sma20,
                trigger=lambda ctx: {"price": _sma20_tomorrow_cross(ctx), "op": ">"} if all(ctx["sma20"][j] and ctx["c"][j] <= ctx["sma20"][j] for j in range(ctx["n"] - 10, ctx["n"])) else None,
                variants=[("先前 ≥ 5 日在線下", lambda ctx, i: _reclaim_sma20(ctx, i, 5)), ("先前 ≥ 15 日在線下", lambda ctx, i: _reclaim_sma20(ctx, i, 15))]))
  S.append(_sig("vix_term_normalize", "VIX 期限結構由倒掛回正（10 日內曾 ≥ 1.0，今 < 0.95）", L_REV, "long", 20,
                "VIX/VIX3M 過去 10 日曾 ≥ 1.0（恐慌），今日首次回到 < 0.95；20 個交易日後結算", _vix_term_normalize,
                trigger=lambda ctx: ({"price": None, "op": "", "needs": "需 VIX/VIX3M < 0.95（目前 %.3f）" % ctx["vix_ratio"][-1]} if (ctx["vix_ratio"][-1] is not None and ctx["vix_ratio"][-1] >= 0.95 and (_vix_ratio_max(ctx, ctx["n"] - 1, 10) or 0) >= 1.0) else None),
                variants=[("回到 < 0.92", lambda ctx, i: _vix_term_normalize(ctx, i, 1.0, 0.92)), ("曾 ≥ 0.97 / 回到 < 0.93", lambda ctx, i: _vix_term_normalize(ctx, i, 0.97, 0.93))], needs=("vix",)))
  S.append(_sig("vix_spike_fade", "VIX 高峰回落 20%（10 日高 ≥ 30）", L_REV, "long", 20,
                "VIX 10 日最高 ≥ 30，今日 VIX ≤ 該高點的 80%（首日）；20 個交易日後結算", _vix_spike_fade,
                variants=[("高 ≥ 25", lambda ctx, i: _vix_spike_fade(ctx, i, 25.0, 0.8)), ("回落 25%", lambda ctx, i: _vix_spike_fade(ctx, i, 30.0, 0.75))], needs=("vix",)))
  S.append(_sig("macd_cross_up_below200", "MACD 柱翻正、價在 200 日線下（空頭反彈）", L_REV, "long", 10,
                "MACD 柱由負翻正，且收盤 < 200MA；10 個交易日後結算", _macd_cross_up_below200))
  S.append(_sig("kd_golden_low", "KD 低檔金叉（K < 20 上穿 D）", L_REV, "long", 10,
                "K 值在 20 以下由下往上穿越 D；10 個交易日後結算", _kd_golden_low,
                variants=[("K < 25", lambda ctx, i: _kd_golden_low(ctx, i, 25.0)), ("K < 15", lambda ctx, i: _kd_golden_low(ctx, i, 15.0))]))
  S.append(_sig("golden_cross_20_50", "20 日線上穿 50 日線", L_TREND, "long", 20,
                "SMA20 由下往上穿越 SMA50；20 個交易日後結算", _golden_cross_20_50))
  S.append(_sig("breakout20_above200", "帶量突破 20 日高、價在 200 日線上", L_TREND, "long", 20,
                "收盤 > 前 20 日最高價、收盤 > 200MA、成交量 ≥ 1.2 倍 20 日均量；20 個交易日後結算", _breakout20,
                trigger=lambda ctx: {"price": ctx["hh20_prev"][-1] if ctx["c"][-1] <= (ctx["hh20_prev"][-1] or 0) else max(ctx["h"][-20:]), "op": ">", "needs": "且量 ≥ 1.2 倍均量、收盤 > 200MA"} if _above200(ctx, ctx["n"] - 1) else None,
                variants=[("量 ≥ 1.0 倍", lambda ctx, i: _breakout20(ctx, i, 1.0)), ("量 ≥ 1.5 倍", lambda ctx, i: _breakout20(ctx, i, 1.5))]))
  # ---- exits
  S.append(_sig("first_close_below_sma20", "首次跌破 20 日線（之前連續 ≥ 10 日在線上）", X_EXIT, "exit", 10,
                "收盤跌破 20MA，且先前至少 10 個交易日都收在 20MA 之上；看 10 個交易日後是否更低", _first_close_below_sma20,
                trigger=lambda ctx: {"price": _sma20_tomorrow_cross(ctx), "op": "<"} if all(ctx["sma20"][j] and ctx["c"][j] >= ctx["sma20"][j] for j in range(ctx["n"] - 10, ctx["n"])) else None))
  S.append(_sig("chandelier_3atr", "吊燈出場（收盤 < 22 日高 − 3×ATR）", X_EXIT, "exit", 10,
                "收盤首次跌破『22 日最高 − 3 倍 ATR(22)』；看 10 個交易日後是否更低", _chandelier,
                trigger=lambda ctx: {"price": ctx["hh22"][-1] - 3.0 * ctx["atr22"][-1], "op": "<"} if (ctx["hh22"][-1] and ctx["c"][-1] >= ctx["hh22"][-1] - 3.0 * ctx["atr22"][-1]) else None,
                variants=[("2.5×ATR", lambda ctx, i: _chandelier(ctx, i, 2.5)), ("3.5×ATR", lambda ctx, i: _chandelier(ctx, i, 3.5))]))
  S.append(_sig("distribution_4in25", "25 日內第 4 個派發日（價在 50 日線上）", X_EXIT, "exit", 20,
                "25 個交易日內放量下跌日累計達 4 個且收盤仍在 50MA 之上（O'Neil）；看 20 個交易日後", _distribution_cluster,
                variants=[("第 5 個", lambda ctx, i: _distribution_cluster(ctx, i, 5)), ("第 3 個", lambda ctx, i: _distribution_cluster(ctx, i, 3))]))
  S.append(_sig("parabolic_blowoff", "拋物線噴出（20 日漲 ≥ 40% 且高於 20MA ≥ 15%）", X_EXIT, "exit", 10,
                "20 日漲幅 ≥ 40% 且收盤高於 20MA 達 15% 以上；看 10 個交易日後", _parabolic,
                variants=[("≥ 30% / 10%", lambda ctx, i: _parabolic(ctx, i, 30.0, 10.0)), ("≥ 50% / 20%", lambda ctx, i: _parabolic(ctx, i, 50.0, 20.0))]))
  S.append(_sig("rsi14_gt80", "RSI(14) 突破 80（過熱）", X_EXIT, "exit", 10,
                "RSI(14) 由下往上穿越 80；看 10 個交易日後", _rsi14_hot,
                variants=[("> 75", lambda ctx, i: _rsi14_hot(ctx, i, 75.0)), ("> 85", lambda ctx, i: _rsi14_hot(ctx, i, 85.0))]))
  S.append(_sig("kd_death_high", "KD 高檔死叉（D > 75）", X_EXIT, "exit", 10,
                "K 由上往下穿越 D 且 D > 75；看 10 個交易日後", _kd_death_high,
                variants=[("D > 70", lambda ctx, i: _kd_death_high(ctx, i, 70.0)), ("D > 80", lambda ctx, i: _kd_death_high(ctx, i, 80.0))]))
  S.append(_sig("vix_term_invert_first", "VIX 期限結構首次倒掛（VIX/VIX3M ≥ 1.0）", X_EXIT, "exit", 10,
                "VIX/VIX3M 首次升破 1.0（前 5 日皆 < 1.0）；看 10 個交易日後", _vix_term_invert_first,
                trigger=lambda ctx: ({"price": None, "op": "", "needs": "需 VIX/VIX3M ≥ 1.0（目前 %.3f）" % ctx["vix_ratio"][-1]} if (ctx["vix_ratio"][-1] is not None and ctx["vix_ratio"][-1] < 1.0) else None),
                variants=[("≥ 0.97", lambda ctx, i: _vix_term_invert_first(ctx, i, 0.97)), ("≥ 1.03", lambda ctx, i: _vix_term_invert_first(ctx, i, 1.03))], needs=("vix",)))
  S.append(_sig("death_cross_50_200", "50 日線下穿 200 日線（死亡交叉）", X_EXIT, "exit", 20,
                "SMA50 由上往下穿越 SMA200；看 20 個交易日後", _death_cross_50_200))
  S.append(_sig("ews_ge80", "崩跌前兆分數首次 ≥ 80", X_EXIT, "exit", 10,
                "21 項前兆加權分數（歷史百分位）首次升到 80 以上；看 10 個交易日後", _ews_hot,
                variants=[("≥ 70", lambda ctx, i: _ews_hot(ctx, i, 70.0)), ("≥ 90", lambda ctx, i: _ews_hot(ctx, i, 90.0))], needs=("ews",)))
  return S


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #
def _trades(ctx: dict, fn, horizon: int, start: int, end: int) -> list[dict]:
  """Non-overlapping trades: signal at i, enter open[i+1], exit close[i+h]."""
  o, c, h_, l_, atr = ctx["o"], ctx["c"], ctx["h"], ctx["l"], ctx["atr14"]
  out: list[dict] = []
  last = -10_000
  for i in range(start, end):
    if i - last < horizon:
      continue
    try:
      ok = bool(fn(ctx, i))
    except (IndexError, TypeError, ZeroDivisionError):
      ok = False
    if not ok:
      continue
    last = i
    if i + horizon >= ctx["n"]:
      out.append({"i": i, "date": ctx["dates"][i], "open_trade": True})
      continue
    entry = o[i + 1]
    exit_px = c[i + horizon]
    lows = l_[i + 1: i + horizon + 1]
    highs = h_[i + 1: i + horizon + 1]
    a = atr[i] or (entry * 0.05)
    out.append({"i": i, "date": ctx["dates"][i], "entry": entry, "exit": exit_px,
                "ret": (exit_px / entry - 1.0) * 100.0,
                "mae_pct": (min(lows) / entry - 1.0) * 100.0, "mfe_pct": (max(highs) / entry - 1.0) * 100.0,
                "mae_atr": (entry - min(lows)) / a, "mfe_atr": (max(highs) - entry) / a})
  return out


def _base_rets(ctx: dict, horizon: int, start: int, end: int) -> list[float]:
  o, c = ctx["o"], ctx["c"]
  return [(c[i + horizon] / o[i + 1] - 1.0) * 100.0 for i in range(start, min(end, ctx["n"] - horizon - 1))]


def _grade(n_all: int, n_oos: int, win_is, win_oos, base_win, pf, variants_ok: bool, p_value: float | None = None) -> tuple[str, str]:
  significant = p_value is not None and p_value < 0.05
  if n_all < MIN_N_GRADE or base_win is None:
    return "—", "樣本不足"
  if n_oos < MIN_N_OOS or win_oos is None:
    return ("B*", "顯著但樣本薄") if significant else ("—", "樣本不足")
  stable = win_is is not None and abs(win_is - win_oos) <= 12.0
  if n_all >= 30 and n_oos >= 10 and win_oos >= 60.0 and win_oos >= base_win + 5.0 and (pf or 0) >= 1.5 and stable and variants_ok and significant:
    return "A", "可靠"
  if win_oos >= base_win + 3.0 and (pf or 0) >= 1.2:
    return "B", "尚可"
  return "C", "無優勢"


def _stop_calibration(trades: list[dict]) -> dict:
  closed = [t for t in trades if "ret" in t]
  winners = [t for t in closed if t["ret"] > 0]
  if len(winners) < 8:
    return {"k_atr": 2.0, "basis": "預設 2.0×ATR（勝利樣本 < 8）", "winners": len(winners)}
  maes = sorted(t["mae_atr"] for t in winners)
  p75 = maes[int(len(maes) * 0.75)]
  p90 = maes[min(len(maes) - 1, int(len(maes) * 0.90))]
  k = max(1.2, min(3.0, round(p75 + 0.2, 1)))
  return {"k_atr": k, "winner_mae_p75_atr": round(p75, 2), "winner_mae_p90_atr": round(p90, 2), "winners": len(winners),
          "basis": f"勝利交易 75% 的最大逆向波動 ≤ {p75:.1f}×ATR → 停損 {k}×ATR"}


def _sim_with_stop(ctx: dict, trades: list[dict], horizon: int, k_atr: float, rr: float = 1.5) -> dict:
  """Re-run the long trades with a stop at entry - k*ATR, a target at entry + rr*k*ATR and the time stop."""
  o, h_, l_, c, atr = ctx["o"], ctx["h"], ctx["l"], ctx["c"], ctx["atr14"]
  rs: list[float] = []
  for t in trades:
    if "ret" not in t:
      continue
    i = t["i"]
    entry = o[i + 1]
    a = atr[i] or entry * 0.05
    stop, tgt = entry - k_atr * a, entry + rr * k_atr * a
    r = None
    for j in range(i + 1, i + horizon + 1):
      if l_[j] <= stop:  # stop first when both are touched in one bar (conservative)
        r = -1.0
        break
      if h_[j] >= tgt:
        r = rr
        break
    if r is None:
      r = (c[i + horizon] - entry) / (k_atr * a)
    rs.append(r)
  if not rs:
    return {"n": 0}
  wins = sum(1 for r in rs if r > 0)
  return {"n": len(rs), "win_pct": round(wins / len(rs) * 100.0, 1), "expectancy_r": round(statistics.mean(rs), 2),
          "pf": _pf(rs), "stop_atr": k_atr, "target_r": rr}


DYN_CAP = 10


def _dyn_trades(ctx: dict, fn, start: int, end: int) -> list[dict]:
  """Mean-reversion mode: enter open[i+1], exit at the first close > SMA5 (cap DYN_CAP bars); no new trade while in one."""
  o, c, s5 = ctx["o"], ctx["c"], ctx["sma5"]
  out: list[dict] = []
  last = -10_000
  for i in range(start, min(end, ctx["n"] - DYN_CAP - 1)):
    if i <= last:
      continue
    try:
      ok = bool(fn(ctx, i))
    except (IndexError, TypeError, ZeroDivisionError):
      ok = False
    if not ok:
      continue
    entry = o[i + 1]
    exit_j = next((j for j in range(i + 1, i + DYN_CAP + 1) if s5[j] and c[j] > s5[j]), i + DYN_CAP)
    out.append({"i": i, "date": ctx["dates"][i], "ret": (c[exit_j] / entry - 1.0) * 100.0, "bars": exit_j - i})
    last = exit_j
  return out


def _dyn_base(ctx: dict, start: int, end: int) -> dict:
  if "_dyn_base" not in ctx:
    tr = _dyn_trades(ctx, lambda _c, _i: True, start, end)
    split = start + int((end - start) * (1.0 - OOS_FRACTION))
    rets = [t["ret"] for t in tr]
    oos = [t["ret"] for t in tr if t["i"] >= split]
    ctx["_dyn_base"] = {"n": len(rets), "win_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100.0, 1) if rets else None,
                        "mean": round(statistics.mean(rets), 2) if rets else None,
                        "oos_win_pct": round(sum(1 for r in oos if r > 0) / len(oos) * 100.0, 1) if oos else None}
  return ctx["_dyn_base"]


def _dd15(ctx: dict, trades: list[dict], window: int = 20, thr: float = -15.0) -> float | None:
  """Share of trades whose next-open-to-low drawdown within ``window`` bars reached ``thr`` percent."""
  o, l_ = ctx["o"], ctx["l"]
  vals = []
  for t in trades:
    i = t["i"]
    if i + 1 >= ctx["n"]:
      continue
    entry = o[i + 1]
    lows = l_[i + 1: min(ctx["n"], i + window + 1)]
    vals.append(1 if lows and (min(lows) / entry - 1.0) * 100.0 <= thr else 0)
  return round(sum(vals) / len(vals) * 100.0, 1) if vals else None


def _dd15_base(ctx: dict, start: int, end: int) -> float | None:
  if "_dd15_base" not in ctx:
    ctx["_dd15_base"] = _dd15(ctx, [{"i": i} for i in range(start, end - 1)])
  return ctx["_dd15_base"]


def evaluate_signal(ctx: dict, sig: dict) -> dict:
  n, hzn = ctx["n"], sig["horizon"]
  start, end = WARMUP, n
  split = start + int((end - start) * (1.0 - OOS_FRACTION))
  good = (lambda r: r > 0) if sig["side"] == "long" else (lambda r: r <= 0)
  trades = _trades(ctx, sig["fn"], hzn, start, end)
  closed = [t for t in trades if "ret" in t]
  rets = [t["ret"] for t in closed]
  is_r = [t["ret"] for t in closed if t["i"] < split]
  oos_r = [t["ret"] for t in closed if t["i"] >= split]
  base = _base_rets(ctx, hzn, start, end)
  base_oos = [(ctx["c"][i + hzn] / ctx["o"][i + 1] - 1.0) * 100.0 for i in range(split, n - hzn - 1)]
  st_all, st_is, st_oos = _stats(rets, good), _stats(is_r, good), _stats(oos_r, good)
  st_base, st_base_oos = _stats(base, good), _stats(base_oos, good)
  by_year: dict[str, list[float]] = {}
  for t in closed:
    by_year.setdefault(t["date"][:4], []).append(t["ret"])
  years = [{"year": y, "n": len(v), "win_pct": round(sum(1 for r in v if good(r)) / len(v) * 100.0, 0), "mean": round(statistics.mean(v), 1)} for y, v in sorted(by_year.items())]
  variants = []
  for label, vfn in sig["variants"]:
    vt = [t for t in _trades(ctx, vfn, hzn, start, end) if "ret" in t]
    vs = _stats([t["ret"] for t in vt], good)
    variants.append({"label": label, "n": vs["n"], "win_pct": vs["win_pct"], "mean": vs["mean"]})
  variants_ok = all((v["win_pct"] or 0) >= (st_base["win_pct"] or 0) for v in variants if v["n"] >= 8) if variants else True
  wins_all = sum(1 for r in rets if good(r))
  p_value = binom_p_greater(wins_all, len(rets), (st_base["win_pct"] or 0) / 100.0) if rets and st_base["win_pct"] else None
  grade, grade_zh = _grade(st_all["n"], st_oos["n"], st_is["win_pct"], st_oos["win_pct"], st_base["win_pct"], st_all["pf"], variants_ok, p_value)
  closed_is = [t for t in closed if t["i"] < split]
  closed_oos = [t for t in closed if t["i"] >= split]
  stop = _stop_calibration(closed_is) if sig["side"] == "long" else {}
  if stop:
    stop["basis"] = "（以樣本內交易校準）" + stop["basis"]
  sim = _sim_with_stop(ctx, closed_oos, hzn, stop.get("k_atr", 2.0)) if sig["side"] == "long" else {}
  if sim:
    sim["scope"] = "樣本外（停損以樣本內校準）"
  sim_all = _sim_with_stop(ctx, closed, hzn, stop.get("k_atr", 2.0)) if sig["side"] == "long" else {}
  dyn = None
  if sig["side"] == "long" and sig["family"] == "反轉買點" and hzn <= 10:
    dt = _dyn_trades(ctx, sig["fn"], start, end)
    db = _dyn_base(ctx, start, end)
    d_rets = [t["ret"] for t in dt]
    d_oos = [t["ret"] for t in dt if t["i"] >= split]
    if d_rets:
      d_wins = sum(1 for r in d_rets if r > 0)
      dyn = {"n": len(d_rets), "win_pct": round(d_wins / len(d_rets) * 100.0, 1), "mean": round(statistics.mean(d_rets), 2),
             "avg_bars": round(statistics.mean(t["bars"] for t in dt), 1), "oos_n": len(d_oos),
             "oos_win_pct": round(sum(1 for r in d_oos if r > 0) / len(d_oos) * 100.0, 1) if d_oos else None,
             "base_win_pct": db["win_pct"], "base_oos_win_pct": db["oos_win_pct"],
             "p_value": binom_p_greater(d_wins, len(d_rets), (db["win_pct"] or 0) / 100.0) if db["win_pct"] else None,
             "exit_rule": f"首次收盤站上 5 日線出場（最多 {DYN_CAP} 日）"}
  dd15 = None
  if sig["side"] == "exit":
    rate = _dd15(ctx, closed)
    base_rate = _dd15_base(ctx, start, end)
    if rate is not None and base_rate is not None and closed:
      k_hits = round(rate / 100.0 * len(closed))
      dd15 = {"rate_pct": rate, "base_pct": base_rate, "p_value": binom_p_greater(k_hits, len(closed), base_rate / 100.0) if 0 < base_rate < 100 else None,
              "definition": "訊號後 20 個交易日內自次日開盤回撤 ≥ 15% 的比例"}
  i_today = n - 1
  try:
    fired_today = bool(sig["fn"](ctx, i_today))
  except (IndexError, TypeError, ZeroDivisionError):
    fired_today = False
  recent = [t["date"] for t in trades if t["i"] >= n - 10]
  pending = None
  if not fired_today and sig.get("trigger"):
    try:
      pending = sig["trigger"](ctx)
    except (IndexError, TypeError, ZeroDivisionError, ValueError):
      pending = None
    if pending and pending.get("price") is not None:
      pending["price"] = round(pending["price"], 2)
      pending["dist_pct"] = round((pending["price"] / ctx["c"][-1] - 1.0) * 100.0, 1)
  state = "fired" if fired_today else ("recent" if recent else ("pending" if pending else "off"))
  last_trade = closed[-1] if closed else None
  return {
      "key": sig["key"], "name": sig["name"], "short_name": sig["short_name"], "family": sig["family"], "side": sig["side"], "horizon": hzn, "rule": sig["rule"],
      "n": st_all["n"], "win_pct": st_all["win_pct"], "ci": st_all["ci"], "mean": st_all["mean"], "median": st_all["median"], "pf": st_all["pf"],
      "worst": st_all["worst"], "best": st_all["best"],
      "is": {"n": st_is["n"], "win_pct": st_is["win_pct"], "mean": st_is["mean"]},
      "oos": {"n": st_oos["n"], "win_pct": st_oos["win_pct"], "ci": st_oos["ci"], "mean": st_oos["mean"], "pf": st_oos["pf"]},
      "base": {"n": st_base["n"], "win_pct": st_base["win_pct"], "mean": st_base["mean"]},
      "base_oos": {"n": st_base_oos["n"], "win_pct": st_base_oos["win_pct"], "mean": st_base_oos["mean"]},
      "edge_pts": round((st_all["win_pct"] or 0) - (st_base["win_pct"] or 0), 1) if st_all["win_pct"] is not None else None,
      "p_value": p_value, "significant": bool(p_value is not None and p_value < 0.05),
      "by_year": years, "variants": variants, "variants_ok": variants_ok,
      "grade": grade, "grade_zh": grade_zh, "stop": stop, "sim": sim, "sim_all_in_sample": sim_all, "dyn": dyn, "dd15": dd15,
      "today": {"state": state, "fired": fired_today, "recent_dates": recent, "pending": pending},
      "last_signal": ({"date": last_trade["date"], "ret": round(last_trade["ret"], 1)} if last_trade else None),
      "open_trades": [t["date"] for t in trades if t.get("open_trade")],
  }


def regime_test(ctx: dict, band_pct: float = 0.0, confirm: int = 1, series: dict[str, float] | None = None, series_name: str = "SOXL") -> dict:
  """Gayed-style 200-day MA switch: hold SOXL when yesterday's signal close > its SMA200, else cash.

  ``series`` (date -> close) lets the signal come from the underlying index (SOXX / SPY / QQQ) while
  the position is always SOXL; the r/LETFs convention is to read the signal on the index, not on the
  3x fund.  ``band_pct`` adds hysteresis (enter above +band, exit below -band) and ``confirm`` requires
  that many consecutive closes beyond the band before switching.  No costs or slippage."""
  c = ctx["c"]
  dates = ctx["dates"]
  if series:
    sig_dates = sorted(series)
    sig_close = [series[d] for d in sig_dates]
    sig_sma = ind.sma(sig_close, 200)
    lookup = {d: (sig_close[k], sig_sma[k]) for k, d in enumerate(sig_dates)}
  else:
    lookup = {d: (c[k], ctx["sma200"][k]) for k, d in enumerate(dates)}
  start = WARMUP
  eq_s = eq_b = peak_s = peak_b = 1.0
  dd_s = dd_b = 0.0
  days_in = switches = 0
  pos_prev = None
  streak = 0
  pos = 0
  for i in range(start, ctx["n"]):
    px, ma = lookup.get(dates[i - 1], (None, None))
    if not ma or not px:
      pos = pos_prev or 0
    else:
      up = px > ma * (1.0 + band_pct / 100.0)
      dn = px < ma * (1.0 - band_pct / 100.0)
      if pos_prev is None:
        pos = 1 if up else 0
      else:
        want = pos_prev
        if pos_prev == 1 and dn:
          want = 0
        elif pos_prev == 0 and up:
          want = 1
        if want != pos_prev:
          streak += 1
          pos = want if streak >= confirm else pos_prev
        else:
          streak = 0
          pos = pos_prev
    if pos_prev is not None and pos != pos_prev:
      switches += 1
      streak = 0
    pos_prev = pos
    r = c[i] / c[i - 1] - 1.0
    eq_s *= (1.0 + r) if pos else 1.0
    eq_b *= (1.0 + r)
    days_in += pos
    peak_s, peak_b = max(peak_s, eq_s), max(peak_b, eq_b)
    dd_s, dd_b = min(dd_s, eq_s / peak_s - 1.0), min(dd_b, eq_b / peak_b - 1.0)
  years = (ctx["n"] - start) / 252.0

  def cagr(e: float) -> float:
    return (e ** (1.0 / years) - 1.0) * 100.0 if years > 0 and e > 0 else 0.0

  last_px, last_ma = lookup.get(dates[-1], (None, None))
  return {"series": series_name, "band_pct": band_pct, "confirm_days": confirm, "years": round(years, 1), "sample": f"{dates[start]} ~ {dates[-1]}",
          "strategy": {"cagr_pct": round(cagr(eq_s), 1), "max_dd_pct": round(dd_s * 100.0, 1), "final_multiple": round(eq_s, 2)},
          "buy_hold": {"cagr_pct": round(cagr(eq_b), 1), "max_dd_pct": round(dd_b * 100.0, 1), "final_multiple": round(eq_b, 2)},
          "time_in_market_pct": round(days_in / (ctx["n"] - start) * 100.0, 0), "switches": switches,
          "today": {"position": "持有 SOXL" if pos else "空手 / 現金", "in_market": bool(pos), "signal_close": round(last_px, 2) if last_px else None,
                    "sma200": round(last_ma, 2) if last_ma else None, "dist_pct": round(ind.pct_change(last_px, last_ma), 1) if (last_px and last_ma) else None,
                    "exit_below": round(last_ma * (1.0 - band_pct / 100.0), 2) if last_ma else None, "enter_above": round(last_ma * (1.0 + band_pct / 100.0), 2) if last_ma else None}}


def run(rows: list[dict], vix: dict[str, float] | None = None, vix3m: dict[str, float] | None = None,
        ews_scores: dict[str, float] | None = None, underlying_rows: list[dict] | None = None, underlying_name: str = "SOXX") -> dict:
  ctx = build_context(rows, vix, vix3m, ews_scores)
  results = []
  skipped = []
  for sig in signal_library():
    if "vix" in sig["needs"] and not ctx["has_vix"]:
      skipped.append({"key": sig["key"], "reason": "缺少 VIX/VIX3M 歷史"})
      continue
    if "ews" in sig["needs"] and not ctx["has_ews"]:
      skipped.append({"key": sig["key"], "reason": "缺少崩跌前兆分數歷史"})
      continue
    results.append(evaluate_signal(ctx, sig))
  qs = bh_qvalues([r["p_value"] if r["n"] >= MIN_N_GRADE else None for r in results])
  for r, q in zip(results, qs):
    r["q_value"] = q
  split_i = WARMUP + int((ctx["n"] - WARMUP) * (1.0 - OOS_FRACTION))
  fired = [r for r in results if r["today"]["state"] == "fired"]
  pending = [r for r in results if r["today"]["state"] == "pending"]
  summary = {
      "n_signals": len(results), "n_graded_a": sum(1 for r in results if r["grade"] == "A"), "n_graded_b": sum(1 for r in results if r["grade"] == "B"),
      "fired_today": [r["key"] for r in fired], "pending": [r["key"] for r in pending],
      "fired_long_ab": [r["key"] for r in fired if r["side"] == "long" and r["grade"] in ("A", "B", "B*")],
      "fired_exit_ab": [r["key"] for r in fired if r["side"] == "exit" and r["grade"] in ("A", "B", "B*")],
      "n_significant": sum(1 for r in results if r.get("significant")), "n_graded": sum(1 for r in results if r["n"] >= MIN_N_GRADE),
      "n_q_lt_10": sum(1 for r in results if r.get("q_value") is not None and r["q_value"] < 0.10),
      "exits_predictive": [r["key"] for r in results if r["side"] == "exit" and r.get("significant")],
      "dyn_base_win_pct": (ctx.get("_dyn_base") or {}).get("win_pct"),
  }
  regime_grid = [regime_test(ctx, 0.0), regime_test(ctx, 3.0), regime_test(ctx, 3.0, 2)]
  if underlying_rows:
    series = {r["date"]: float(r["close"]) for r in underlying_rows}
    for band, conf in ((0.0, 1), (3.0, 1), (5.0, 1), (3.0, 2)):
      regime_grid.append(regime_test(ctx, band, conf, series, underlying_name))
  return {
      "method": {"entry": "訊號日次一交易日開盤價", "exit": "訊號後第 h 個交易日收盤價（h = 各訊號 horizon）", "declustered": True,
                 "oos": f"最近 {int(OOS_FRACTION * 100)}% 樣本（{ctx['dates'][split_i]} 起）", "ci": "Wilson 95%",
                 "sample": f"{ctx['dates'][WARMUP]} ~ {ctx['dates'][-1]}", "bars": ctx["n"], "data_as_of": ctx["dates"][-1],
                 "grades": "A 可靠：N≥30、OOS N≥10、OOS 勝率≥60% 且 ≥ 基準+5、PF≥1.5、IS/OOS 差≤12、鄰近參數皆優於基準；B 尚可：OOS ≥ 基準+3 且 PF≥1.2；C 無優勢；— 樣本不足（N<20 或 OOS<8）"},
      "signals": results, "skipped": skipped, "summary": summary,
      "regime": {"sma200": regime_grid[0], "sma200_band3": regime_grid[1], "grid": regime_grid,
                 "note": "同一套 200 日線濾網，分別用 SOXL 自身與標的指數當訊號；無交易成本，帶寬敏感度高，請看整張表而非單一數字"},
      "atr14": round(ctx["atr14"][-1], 2), "atr_pct": round(ctx["atr14"][-1] / ctx["c"][-1] * 100.0, 2),
  }
