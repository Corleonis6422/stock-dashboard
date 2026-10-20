#!/usr/bin/env python3
"""Pure technical-indicator math (stdlib only, no third-party dependencies).

Every function is side-effect free and operates on plain Python lists of
floats or OHLCV row dicts ({"open","high","low","close","volume"}).
"""

from __future__ import annotations

import math
import statistics


# --------------------------------------------------------------------------- #
# Moving averages & oscillators
# --------------------------------------------------------------------------- #
def sma(arr: list[float], n: int) -> list[float | None]:
  out: list[float | None] = []
  run = 0.0
  for i, v in enumerate(arr):
    run += v
    if i >= n:
      run -= arr[i - n]
    out.append(run / n if i + 1 >= n else None)
  return out


def ema(values: list[float], span: int) -> list[float]:
  if not values:
    return []
  k = 2.0 / (span + 1.0)
  out = [values[0]]
  for v in values[1:]:
    out.append(v * k + out[-1] * (1.0 - k))
  return out


def rolling_std(arr: list[float], n: int) -> list[float | None]:
  out: list[float | None] = []
  for i in range(len(arr)):
    if i + 1 < n:
      out.append(None)
    else:
      out.append(statistics.pstdev(arr[i - n + 1 : i + 1]))
  return out


def rsi(closes: list[float], period: int = 14) -> list[float]:
  """Wilder's RSI."""
  n = len(closes)
  if n < period + 1:
    return [50.0] * n
  out = [50.0] * n
  gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, period + 1)]
  losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, period + 1)]
  ag, al = sum(gains) / period, sum(losses) / period
  out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
  for i in range(period + 1, n):
    d = closes[i] - closes[i - 1]
    ag = (ag * (period - 1) + max(d, 0.0)) / period
    al = (al * (period - 1) + max(-d, 0.0)) / period
    out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
  return out


def kdj(
    rows: list[dict], n: int = 9, k_smooth: int = 3, d_smooth: int = 3
) -> tuple[list[float], list[float], list[float], list[float]]:
  """Asian-market style KD / KDJ with 1/3 smoothing. Returns (RSV, K, D, J)."""
  rsv_l, k_l, d_l, j_l = [], [], [], []
  k_prev, d_prev = 50.0, 50.0
  ak, ad = 1.0 / k_smooth, 1.0 / d_smooth
  for i in range(len(rows)):
    s = max(0, i - n + 1)
    hh = max(r["high"] for r in rows[s : i + 1])
    ll = min(r["low"] for r in rows[s : i + 1])
    rsv = 50.0 if hh - ll <= 1e-9 else (rows[i]["close"] - ll) / (hh - ll) * 100.0
    k = (1 - ak) * k_prev + ak * rsv
    d = (1 - ad) * d_prev + ad * k
    rsv_l.append(rsv)
    k_l.append(k)
    d_l.append(d)
    j_l.append(3 * k - 2 * d)
    k_prev, d_prev = k, d
  return rsv_l, k_l, d_l, j_l


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
  ef, es = ema(closes, fast), ema(closes, slow)
  dif = [a - b for a, b in zip(ef, es)]
  dea = ema(dif, signal)
  hist = [a - b for a, b in zip(dif, dea)]
  return dif, dea, hist


def true_ranges(rows: list[dict]) -> list[float]:
  trs = [rows[0]["high"] - rows[0]["low"]]
  for i in range(1, len(rows)):
    trs.append(
        max(
            rows[i]["high"] - rows[i]["low"],
            abs(rows[i]["high"] - rows[i - 1]["close"]),
            abs(rows[i]["low"] - rows[i - 1]["close"]),
        )
    )
  return trs


def atr(rows: list[dict], period: int = 14) -> list[float]:
  """Wilder ATR series."""
  trs = true_ranges(rows)
  out = []
  val = None
  for i, tr in enumerate(trs):
    if i < period:
      out.append(sum(trs[: i + 1]) / (i + 1))
      val = out[-1]
    else:
      val = (val * (period - 1) + tr) / period
      out.append(val)
  return out


def adx_dmi(
    rows: list[dict], period: int = 14
) -> tuple[list[float], list[float], list[float]]:
  n = len(rows)
  if n < period * 2 + 1:
    return [25.0] * n, [25.0] * n, [20.0] * n
  tr_l, pdm_l, ndm_l = [0.0], [0.0], [0.0]
  for i in range(1, n):
    h, l, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
    ph, pl = rows[i - 1]["high"], rows[i - 1]["low"]
    tr_l.append(max(h - l, abs(h - pc), abs(l - pc)))
    up, dn = h - ph, pl - l
    pdm_l.append(up if (up > dn and up > 0) else 0.0)
    ndm_l.append(dn if (dn > up and dn > 0) else 0.0)
  pdi = [25.0] * n
  ndi = [25.0] * n
  dx = [20.0] * n
  adx = [20.0] * n
  s_tr, s_p, s_n = sum(tr_l[1 : period + 1]), sum(pdm_l[1 : period + 1]), sum(ndm_l[1 : period + 1])
  for i in range(period, n):
    if i > period:
      s_tr = s_tr - s_tr / period + tr_l[i]
      s_p = s_p - s_p / period + pdm_l[i]
      s_n = s_n - s_n / period + ndm_l[i]
    p = s_p / s_tr * 100.0 if s_tr > 0 else 0.0
    q = s_n / s_tr * 100.0 if s_tr > 0 else 0.0
    pdi[i], ndi[i] = p, q
    dx[i] = abs(p - q) / (p + q) * 100.0 if (p + q) > 0 else 0.0
  a = sum(dx[period : period * 2]) / period
  adx[period * 2 - 1] = a
  for i in range(period * 2, n):
    a = (a * (period - 1) + dx[i]) / period
    adx[i] = a
  return pdi, ndi, adx


def supertrend(
    rows: list[dict], period: int = 10, mult: float = 3.0
) -> tuple[list[float], list[int]]:
  n = len(rows)
  trs = true_ranges(rows)
  line = [rows[0]["close"]] * n
  direction = [1] * n
  fu = [0.0] * n
  fl = [0.0] * n
  for i in range(n):
    s = max(0, i - period + 1)
    a = sum(trs[s : i + 1]) / (i - s + 1)
    hl2 = (rows[i]["high"] + rows[i]["low"]) / 2.0
    bu, bl = hl2 + mult * a, hl2 - mult * a
    if i == 0:
      fu[i], fl[i], line[i], direction[i] = bu, bl, bl, 1
      continue
    fu[i] = bu if (bu < fu[i - 1] or rows[i - 1]["close"] > fu[i - 1]) else fu[i - 1]
    fl[i] = bl if (bl > fl[i - 1] or rows[i - 1]["close"] < fl[i - 1]) else fl[i - 1]
    if direction[i - 1] == 1:
      if rows[i]["close"] < fl[i]:
        direction[i], line[i] = -1, fu[i]
      else:
        direction[i], line[i] = 1, fl[i]
    else:
      if rows[i]["close"] > fu[i]:
        direction[i], line[i] = 1, fl[i]
      else:
        direction[i], line[i] = -1, fu[i]
  return line, direction


def parabolic_sar(
    rows: list[dict], step: float = 0.02, max_step: float = 0.20
) -> tuple[list[float], list[int]]:
  n = len(rows)
  sar = [rows[0]["low"]] * n
  bull = [1] * n
  af, ep = step, rows[0]["high"]
  for i in range(1, n):
    prev = sar[i - 1]
    if bull[i - 1] == 1:
      cur = prev + af * (ep - prev)
      cur = min(cur, rows[i - 1]["low"], rows[max(0, i - 2)]["low"])
      if rows[i]["low"] < cur:
        bull[i], cur, ep, af = -1, ep, rows[i]["low"], step
      else:
        bull[i] = 1
        if rows[i]["high"] > ep:
          ep, af = rows[i]["high"], min(max_step, af + step)
    else:
      cur = prev + af * (ep - prev)
      cur = max(cur, rows[i - 1]["high"], rows[max(0, i - 2)]["high"])
      if rows[i]["high"] > cur:
        bull[i], cur, ep, af = 1, ep, rows[i]["high"], step
      else:
        bull[i] = -1
        if rows[i]["low"] < ep:
          ep, af = rows[i]["low"], min(max_step, af + step)
    sar[i] = cur
  return sar, bull


def mfi(rows: list[dict], period: int = 14) -> float:
  if len(rows) < period + 1:
    return 50.0
  pos = neg = 0.0
  for i in range(len(rows) - period, len(rows)):
    tp = (rows[i]["high"] + rows[i]["low"] + rows[i]["close"]) / 3.0
    tpp = (rows[i - 1]["high"] + rows[i - 1]["low"] + rows[i - 1]["close"]) / 3.0
    raw = tp * rows[i]["volume"]
    if tp > tpp:
      pos += raw
    elif tp < tpp:
      neg += raw
  if neg == 0:
    return 100.0
  return 100.0 - 100.0 / (1.0 + pos / neg)


def cmf(rows: list[dict], period: int = 20) -> list[float]:
  mfv, vol = [], []
  for r in rows:
    hl = r["high"] - r["low"]
    m = 0.0 if hl <= 1e-9 else ((r["close"] - r["low"]) - (r["high"] - r["close"])) / hl
    mfv.append(m * r["volume"])
    vol.append(r["volume"])
  out = []
  for i in range(len(rows)):
    s = max(0, i - period + 1)
    vs = sum(vol[s : i + 1])
    out.append(sum(mfv[s : i + 1]) / vs if vs > 0 else 0.0)
  return out


def obv(rows: list[dict]) -> list[float]:
  out = [0.0]
  for i in range(1, len(rows)):
    if rows[i]["close"] > rows[i - 1]["close"]:
      out.append(out[-1] + rows[i]["volume"])
    elif rows[i]["close"] < rows[i - 1]["close"]:
      out.append(out[-1] - rows[i]["volume"])
    else:
      out.append(out[-1])
  return out


def williams_r(rows: list[dict], period: int = 14) -> float:
  hh = max(r["high"] for r in rows[-period:])
  ll = min(r["low"] for r in rows[-period:])
  return -50.0 if hh - ll <= 0 else (hh - rows[-1]["close"]) / (hh - ll) * -100.0


def cci(rows: list[dict], period: int = 20) -> float:
  tps = [(r["high"] + r["low"] + r["close"]) / 3.0 for r in rows[-period:]]
  m = statistics.mean(tps)
  md = statistics.mean(abs(x - m) for x in tps)
  return 0.0 if md <= 1e-9 else (tps[-1] - m) / (0.015 * md)


def bollinger(closes: list[float], n: int = 20, k: float = 2.0) -> dict:
  mid = sma(closes, n)
  sd = rolling_std(closes, n)
  upper = [None if m is None else m + k * s for m, s in zip(mid, sd)]
  lower = [None if m is None else m - k * s for m, s in zip(mid, sd)]
  width = [
      None if (m is None or not m) else (u - l) / m * 100.0
      for m, u, l in zip(mid, upper, lower)
  ]
  pct_b = [
      None if (u is None or (u - l) <= 0) else (c - l) / (u - l)
      for c, u, l in zip(closes, upper, lower)
  ]
  return {"mid": mid, "upper": upper, "lower": lower, "width_pct": width, "pct_b": pct_b}


def detect_swing(rows: list[dict], lookback: int = 120) -> dict:
  """Detect the dominant recent swing (last major low -> high, or high -> low) for Fibonacci.

  Returns dict(kind, low_price, low_date, high_price, high_date, levels{...}).
  kind == "up" means retracement of an up-swing (support levels below the high);
  kind == "down" means retracement of a down-swing (resistance levels above the low).
  """
  win = rows[-lookback:]
  hi_i = max(range(len(win)), key=lambda i: win[i]["high"])
  lo_i = min(range(len(win)), key=lambda i: win[i]["low"])
  hi, lo = win[hi_i], win[lo_i]
  if lo_i < hi_i:
    # Up-swing low -> high, retracement levels measured down from the high
    kind = "up"
    rng = hi["high"] - lo["low"]
    levels = {
        "fib_236": hi["high"] - 0.236 * rng,
        "fib_382": hi["high"] - 0.382 * rng,
        "fib_500": hi["high"] - 0.500 * rng,
        "fib_618": hi["high"] - 0.618 * rng,
        "fib_786": hi["high"] - 0.786 * rng,
    }
  else:
    # Down-swing high -> low, rebound levels measured up from the low
    kind = "down"
    rng = hi["high"] - lo["low"]
    levels = {
        "fib_236": lo["low"] + 0.236 * rng,
        "fib_382": lo["low"] + 0.382 * rng,
        "fib_500": lo["low"] + 0.500 * rng,
        "fib_618": lo["low"] + 0.618 * rng,
        "fib_786": lo["low"] + 0.786 * rng,
    }
  return {
      "kind": kind,
      "low_price": lo["low"],
      "low_date": lo["date"],
      "high_price": hi["high"],
      "high_date": hi["date"],
      "levels": {k: round(v, 2) for k, v in levels.items()},
  }


# --------------------------------------------------------------------------- #
# Statistics helpers
# --------------------------------------------------------------------------- #
def pearson(x: list[float], y: list[float]) -> float:
  if len(x) != len(y) or len(x) < 3:
    return 0.0
  mx, my = statistics.mean(x), statistics.mean(y)
  num = sum((a - mx) * (b - my) for a, b in zip(x, y))
  den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
  return num / den if den > 1e-12 else 0.0


def beta(y: list[float], x: list[float]) -> float:
  if len(x) != len(y) or len(x) < 3:
    return 0.0
  mx, my = statistics.mean(x), statistics.mean(y)
  num = sum((a - mx) * (b - my) for a, b in zip(x, y))
  den = sum((a - mx) ** 2 for a in x)
  return num / den if den > 1e-12 else 0.0


def zscore(series: list[float], window: int = 60) -> float:
  win = [v for v in series[-window:] if v is not None]
  if len(win) < 5:
    return 0.0
  sd = statistics.pstdev(win)
  return 0.0 if sd <= 1e-12 else (win[-1] - statistics.mean(win)) / sd


def percentile_rank(series: list[float], value: float) -> float:
  vals = [v for v in series if v is not None]
  if not vals:
    return 50.0
  return sum(1 for v in vals if v <= value) / len(vals) * 100.0


def pct_change(a: float, b: float) -> float:
  return 0.0 if not b else (a - b) / b * 100.0


def max_drawdown(closes: list[float]) -> float:
  peak = closes[0]
  mdd = 0.0
  for c in closes:
    peak = max(peak, c)
    mdd = min(mdd, (c - peak) / peak * 100.0)
  return mdd


def norm_cdf(x: float) -> float:
  return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def quantiles(vals: list[float], qs: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9)) -> dict:
  if not vals:
    return {f"p{int(q*100)}": None for q in qs}
  s = sorted(vals)
  out = {}
  for q in qs:
    idx = q * (len(s) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    out[f"p{int(q*100)}"] = s[lo] + (s[hi] - s[lo]) * (idx - lo)
  return out
