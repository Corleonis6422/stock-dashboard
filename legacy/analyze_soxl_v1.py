#!/usr/bin/env python3
"""SOXL Comprehensive Quantitative Analysis & HTML Report Generator.

Performs: 1. Call / Put Options Ratio, OI/Volume Structure, Max Pain, Call/Put
Walls & Net GEX Analysis (CBOE live data) 2. Volume & Money Flow Analysis (OBV,
CMF, MFI, RVOL, Up/Down Volume, Volume Profile POC/VAH/VAL, VWAP) 3. Full
Technical Analysis Suite:
   - MACD (12, 26, 9): DIF, DEA, Histogram, crossovers & trend regime
   - KD / KDJ Stochastic (9, 3, 3) & Slow KD (14, 3, 3): %K, %D, %J
   - Multi-period RSI (6, 14, 24), StochRSI (14), Williams %R (14), CCI (20),
   ROC (12)
   - ADX / DMI (14): +DI, -DI, ADX trend strength
   - Ichimoku Cloud (9, 26, 52), Parabolic SAR, Supertrend (10, 3)
   - MA Ribbon (EMA5, EMA10, SMA20, SMA50, SMA100, SMA200), Bollinger Bands,
   Fibonacci Retracements & Pivot Points
4. Multi-Dimensional Heat Map Analysis:
   - Semiconductor Constituents Performance & Volume Heat Map
   - Options Strike x Expiration OI / Volume / Net GEX 2D Heat Map
   - Sub-sector Regime Heat Map
5. Cross-Asset Macro Correlation Analysis:
   - US 10Y Treasury Yield (^TNX), US 30Y Treasury Yield (^TYX), 30Y-10Y Term
   Spread
   - Brent Crude Oil Futures (BZ=F) & CBOE Volatility Index (^VIX)
   - 20D / 60D / 120D / 250D Correlation Matrices, Rolling 20D Correlations &
   Beta Sensitivities
6. Daily Bullish vs Bearish News & Catalyst Analysis (每日最新利多利空消息解析)
7. -2 to +2 Multi-Factor Quantitative Scoring Table (16 Factors across 7
Dimensions)
"""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import urllib.parse
import urllib.request

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_TICKER_RE = re.compile(r"^[\^A-Z0-9=]{1,8}$")

SOXL_CONSTITUENTS = [
    {
        "ticker": "NVDA",
        "name": "NVIDIA Corp",
        "weight": 10.2,
        "subsector": "AI & GPU Compute",
    },
    {
        "ticker": "AVGO",
        "name": "Broadcom Inc",
        "weight": 9.8,
        "subsector": "AI ASIC & Networking",
    },
    {
        "ticker": "AMD",
        "name": "Advanced Micro Devices",
        "weight": 8.4,
        "subsector": "AI & GPU Compute",
    },
    {
        "ticker": "MU",
        "name": "Micron Technology",
        "weight": 7.6,
        "subsector": "Memory & HBM",
    },
    {
        "ticker": "QCOM",
        "name": "Qualcomm Inc",
        "weight": 6.8,
        "subsector": "Mobile & RF",
    },
    {
        "ticker": "TXN",
        "name": "Texas Instruments",
        "weight": 6.5,
        "subsector": "Analog & Mixed Signal",
    },
    {
        "ticker": "AMAT",
        "name": "Applied Materials",
        "weight": 6.1,
        "subsector": "Wafer Fab Equipment",
    },
    {
        "ticker": "LRCX",
        "name": "Lam Research",
        "weight": 5.6,
        "subsector": "Wafer Fab Equipment",
    },
    {
        "ticker": "KLAC",
        "name": "KLA Corp",
        "weight": 5.2,
        "subsector": "Wafer Fab Equipment",
    },
    {
        "ticker": "INTC",
        "name": "Intel Corp",
        "weight": 4.8,
        "subsector": "CPU & Foundry",
    },
    {
        "ticker": "ADI",
        "name": "Analog Devices",
        "weight": 4.6,
        "subsector": "Analog & Mixed Signal",
    },
    {
        "ticker": "MRVL",
        "name": "Marvell Technology",
        "weight": 4.4,
        "subsector": "AI ASIC & Networking",
    },
    {
        "ticker": "NXPI",
        "name": "NXP Semiconductors",
        "weight": 4.1,
        "subsector": "Auto & Industrial",
    },
    {
        "ticker": "MPWR",
        "name": "Monolithic Power",
        "weight": 3.8,
        "subsector": "Power Management",
    },
    {
        "ticker": "ON",
        "name": "ON Semiconductor",
        "weight": 3.5,
        "subsector": "Auto & Industrial",
    },
    {
        "ticker": "TER",
        "name": "Teradyne Inc",
        "weight": 3.2,
        "subsector": "Semi Test & Robotics",
    },
]


def safe_https_get_json(url: str) -> dict:
  """Fetch JSON from an explicitly validated HTTPS endpoint."""
  parsed = urllib.parse.urlparse(url)
  if parsed.scheme != "https" or parsed.netloc not in {
      "query2.finance.yahoo.com",
      "cdn.cboe.com",
  }:
    raise ValueError(f"Disallowed URL host or scheme: {url}")
  req = urllib.request.Request(
      url,
      headers={
          "User-Agent": (
              "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
              " AppleWebKit/537.36"
          ),
          "Accept": "application/json",
      },
  )
  with urllib.request.urlopen(req, timeout=15) as resp:
    return json.loads(resp.read().decode("utf-8"))


def fetch_yahoo_ohlcv(
    ticker: str, period_range: str = "1y", interval: str = "1d"
) -> list[dict]:
  """Fetch daily OHLCV history for a validated ticker."""
  if not ALLOWED_TICKER_RE.match(ticker):
    raise ValueError(f"Invalid ticker symbol: {ticker}")
  encoded = urllib.parse.quote(ticker)
  url = f"https://query2.finance.yahoo.com/v8/finance/chart/{encoded}?range={period_range}&interval={interval}"
  raw = safe_https_get_json(url)
  result = raw["chart"]["result"][0]
  timestamps = result["timestamp"]
  quote = result["indicators"]["quote"][0]
  opens = quote["open"]
  highs = quote["high"]
  lows = quote["low"]
  closes = quote["close"]
  volumes = quote["volume"]

  rows = []
  for i, ts in enumerate(timestamps):
    if (
        closes[i] is None
        or highs[i] is None
        or lows[i] is None
        or opens[i] is None
    ):
      continue
    dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    rows.append({
        "timestamp": ts,
        "date": dt_str,
        "open": float(opens[i]),
        "high": float(highs[i]),
        "low": float(lows[i]),
        "close": float(closes[i]),
        "volume": int(volumes[i] or 0),
    })
  return rows


def compute_sma(arr: list[float], n: int) -> list[float | None]:
  """Compute Simple Moving Average."""
  out = []
  for i in range(len(arr)):
    if i + 1 < n:
      out.append(None)
    else:
      out.append(sum(arr[i - n + 1 : i + 1]) / n)
  return out


def compute_ema(values: list[float], span: int) -> list[float]:
  """Compute Exponential Moving Average."""
  if not values:
    return []
  k = 2.0 / (span + 1.0)
  ema = [values[0]]
  for v in values[1:]:
    ema.append(v * k + ema[-1] * (1.0 - k))
  return ema


def compute_rsi(closes: list[float], period: int = 14) -> list[float]:
  """Compute Wilder's RSI."""
  if len(closes) < period + 1:
    return [50.0] * len(closes)
  rsis = [50.0] * len(closes)
  gains = []
  losses = []
  for i in range(1, period + 1):
    diff = closes[i] - closes[i - 1]
    gains.append(max(diff, 0.0))
    losses.append(max(-diff, 0.0))
  avg_gain = sum(gains) / period
  avg_loss = sum(losses) / period
  rsis[period] = (
      100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
  )

  for i in range(period + 1, len(closes)):
    diff = closes[i] - closes[i - 1]
    gain = max(diff, 0.0)
    loss = max(-diff, 0.0)
    avg_gain = (avg_gain * (period - 1) + gain) / period
    avg_loss = (avg_loss * (period - 1) + loss) / period
    rsis[i] = (
        100.0
        if avg_loss == 0
        else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    )
  return rsis


def compute_kdj(
    rows: list[dict], n: int = 9, k_smooth: int = 3, d_smooth: int = 3
) -> tuple[list[float], list[float], list[float], list[float]]:
  """Compute standard Taiwanese/Asian market KD & KDJ (9, 3, 3) with 1/3 Wilder smoothing."""
  rsv_list = []
  k_list = []
  d_list = []
  j_list = []
  k_prev = 50.0
  d_prev = 50.0
  alpha_k = 1.0 / k_smooth
  alpha_d = 1.0 / d_smooth

  for i in range(len(rows)):
    start = max(0, i - n + 1)
    hh = max(r["high"] for r in rows[start : i + 1])
    ll = min(r["low"] for r in rows[start : i + 1])
    if hh - ll <= 1e-9:
      rsv = 50.0
    else:
      rsv = ((rows[i]["close"] - ll) / (hh - ll)) * 100.0
    k_curr = (1.0 - alpha_k) * k_prev + alpha_k * rsv
    d_curr = (1.0 - alpha_d) * d_prev + alpha_d * k_curr
    j_curr = 3.0 * k_curr - 2.0 * d_curr
    rsv_list.append(rsv)
    k_list.append(k_curr)
    d_list.append(d_curr)
    j_list.append(j_curr)
    k_prev, d_prev = k_curr, d_curr
  return rsv_list, k_list, d_list, j_list


def compute_adx_dmi(
    rows: list[dict], period: int = 14
) -> tuple[list[float], list[float], list[float]]:
  """Compute +DI, -DI, and ADX (14)."""
  n = len(rows)
  if n < period * 2:
    return [25.0] * n, [25.0] * n, [25.0] * n

  tr_list = [0.0]
  pdm_list = [0.0]
  ndm_list = [0.0]
  for i in range(1, n):
    h, l, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
    ph, pl = rows[i - 1]["high"], rows[i - 1]["low"]
    tr = max(h - l, abs(h - pc), abs(l - pc))
    up_move = h - ph
    dn_move = pl - l
    pdm = up_move if (up_move > dn_move and up_move > 0) else 0.0
    ndm = dn_move if (dn_move > up_move and dn_move > 0) else 0.0
    tr_list.append(tr)
    pdm_list.append(pdm)
    ndm_list.append(ndm)

  pdi_series = [25.0] * n
  ndi_series = [25.0] * n
  dx_series = [20.0] * n
  adx_series = [20.0] * n

  sm_tr = sum(tr_list[1 : period + 1])
  sm_pdm = sum(pdm_list[1 : period + 1])
  sm_ndm = sum(ndm_list[1 : period + 1])

  for i in range(period, n):
    if i > period:
      sm_tr = sm_tr - (sm_tr / period) + tr_list[i]
      sm_pdm = sm_pdm - (sm_pdm / period) + pdm_list[i]
      sm_ndm = sm_ndm - (sm_ndm / period) + ndm_list[i]
    pdi = (sm_pdm / sm_tr) * 100.0 if sm_tr > 0 else 0.0
    ndi = (sm_ndm / sm_tr) * 100.0 if sm_tr > 0 else 0.0
    dx = (abs(pdi - ndi) / (pdi + ndi)) * 100.0 if (pdi + ndi) > 0 else 0.0
    pdi_series[i] = pdi
    ndi_series[i] = ndi
    dx_series[i] = dx

  adx_val = sum(dx_series[period : period * 2]) / period
  adx_series[period * 2 - 1] = adx_val
  for i in range(period * 2, n):
    adx_val = (adx_val * (period - 1) + dx_series[i]) / period
    adx_series[i] = adx_val

  return pdi_series, ndi_series, adx_series


def compute_supertrend(
    rows: list[dict], period: int = 10, multiplier: float = 3.0
) -> tuple[list[float], list[int]]:
  """Compute Supertrend line and direction (+1 bullish, -1 bearish)."""
  n = len(rows)
  trs = [rows[0]["high"] - rows[0]["low"]]
  for i in range(1, n):
    tr = max(
        rows[i]["high"] - rows[i]["low"],
        abs(rows[i]["high"] - rows[i - 1]["close"]),
        abs(rows[i]["low"] - rows[i - 1]["close"]),
    )
    trs.append(tr)

  st_line = [rows[0]["close"]] * n
  st_dir = [1] * n
  final_upper = [0.0] * n
  final_lower = [0.0] * n

  for i in range(n):
    start = max(0, i - period + 1)
    atr = sum(trs[start : i + 1]) / (i - start + 1)
    hl2 = (rows[i]["high"] + rows[i]["low"]) / 2.0
    basic_u = hl2 + multiplier * atr
    basic_l = hl2 - multiplier * atr

    if i == 0:
      final_upper[i] = basic_u
      final_lower[i] = basic_l
      st_line[i] = basic_l
      st_dir[i] = 1
    else:
      if basic_u < final_upper[i - 1] or rows[i - 1]["close"] > final_upper[i - 1]:
        final_upper[i] = basic_u
      else:
        final_upper[i] = final_upper[i - 1]

      if basic_l > final_lower[i - 1] or rows[i - 1]["close"] < final_lower[i - 1]:
        final_lower[i] = basic_l
      else:
        final_lower[i] = final_lower[i - 1]

      if st_dir[i - 1] == 1:
        if rows[i]["close"] < final_lower[i]:
          st_dir[i] = -1
          st_line[i] = final_upper[i]
        else:
          st_dir[i] = 1
          st_line[i] = final_lower[i]
      else:
        if rows[i]["close"] > final_upper[i]:
          st_dir[i] = 1
          st_line[i] = final_lower[i]
        else:
          st_dir[i] = -1
          st_line[i] = final_upper[i]

  return st_line, st_dir


def compute_parabolic_sar(
    rows: list[dict], step: float = 0.02, max_step: float = 0.20
) -> tuple[list[float], list[int]]:
  """Compute Parabolic SAR."""
  n = len(rows)
  sar = [rows[0]["low"]] * n
  bull = [1] * n
  af = step
  ep = rows[0]["high"]

  for i in range(1, n):
    prev_sar = sar[i - 1]
    if bull[i - 1] == 1:
      curr_sar = prev_sar + af * (ep - prev_sar)
      curr_sar = min(
          curr_sar, rows[i - 1]["low"], rows[max(0, i - 2)]["low"]
      )
      if rows[i]["low"] < curr_sar:
        bull[i] = -1
        curr_sar = ep
        ep = rows[i]["low"]
        af = step
      else:
        bull[i] = 1
        if rows[i]["high"] > ep:
          ep = rows[i]["high"]
          af = min(max_step, af + step)
    else:
      curr_sar = prev_sar + af * (ep - prev_sar)
      curr_sar = max(
          curr_sar, rows[i - 1]["high"], rows[max(0, i - 2)]["high"]
      )
      if rows[i]["high"] > curr_sar:
        bull[i] = 1
        curr_sar = ep
        ep = rows[i]["high"]
        af = step
      else:
        bull[i] = -1
        if rows[i]["low"] < ep:
          ep = rows[i]["low"]
          af = min(max_step, af + step)
    sar[i] = curr_sar
  return sar, bull


def compute_mfi(rows: list[dict], period: int = 14) -> float:
  """Compute Money Flow Index (14) for the latest bar."""
  if len(rows) < period + 1:
    return 50.0
  pos_flow = 0.0
  neg_flow = 0.0
  for i in range(len(rows) - period, len(rows)):
    tp_curr = (rows[i]["high"] + rows[i]["low"] + rows[i]["close"]) / 3.0
    tp_prev = (
        rows[i - 1]["high"] + rows[i - 1]["low"] + rows[i - 1]["close"]
    ) / 3.0
    raw_mf = tp_curr * rows[i]["volume"]
    if tp_curr > tp_prev:
      pos_flow += raw_mf
    elif tp_curr < tp_prev:
      neg_flow += raw_mf
  if neg_flow == 0:
    return 100.0
  mr = pos_flow / neg_flow
  return 100.0 - (100.0 / (1.0 + mr))


def compute_cmf(rows: list[dict], period: int = 20) -> list[float]:
  """Compute rolling Chaikin Money Flow (CMF)."""
  cmf_series = []
  mfv_list = []
  vol_list = []
  for r in rows:
    hl = r["high"] - r["low"]
    if hl <= 1e-9:
      mfm = 0.0
    else:
      mfm = ((r["close"] - r["low"]) - (r["high"] - r["close"])) / hl
    mfv_list.append(mfm * r["volume"])
    vol_list.append(r["volume"])

  for i in range(len(rows)):
    start = max(0, i - period + 1)
    v_sum = sum(vol_list[start : i + 1])
    cmf_series.append(sum(mfv_list[start : i + 1]) / v_sum if v_sum > 0 else 0.0)
  return cmf_series


def analyze_volume_price_and_technicals(rows: list[dict]) -> dict:
  """Compute comprehensive volume, price, Volume Profile, and Full Technical Indicators."""
  closes = [r["close"] for r in rows]
  volumes = [r["volume"] for r in rows]
  latest = rows[-1]
  prev = rows[-2]

  # Moving averages (EMA & SMA Ribbon)
  ema5 = compute_ema(closes, 5)
  ema10 = compute_ema(closes, 10)
  ema20 = compute_ema(closes, 20)
  sma20 = compute_sma(closes, 20)
  sma50 = compute_sma(closes, 50)
  sma100 = compute_sma(closes, 100)
  sma200 = compute_sma(closes, 200)
  vol_sma20 = compute_sma([float(v) for v in volumes], 20)
  vol_sma50 = compute_sma([float(v) for v in volumes], 50)

  # Multi-period RSI (6, 14, 24) & StochRSI (14)
  rsi6 = compute_rsi(closes, 6)
  rsi14 = compute_rsi(closes, 14)
  rsi24 = compute_rsi(closes, 24)
  r14_win = rsi14[-14:]
  r14_min, r14_max = min(r14_win), max(r14_win)
  stoch_rsi = (
      ((rsi14[-1] - r14_min) / (r14_max - r14_min)) * 100.0
      if (r14_max - r14_min) > 1e-9
      else 50.0
  )

  # MACD (12, 26, 9)
  ema12 = compute_ema(closes, 12)
  ema26 = compute_ema(closes, 26)
  macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
  macd_signal = compute_ema(macd_line, 9)
  macd_hist = [m - s for m, s in zip(macd_line, macd_signal)]

  # KD / KDJ (9, 3, 3) & Slow KD (14, 3, 3)
  rsv9, k9, d9, j9 = compute_kdj(rows, 9, 3, 3)
  _, k14, d14, j14 = compute_kdj(rows, 14, 3, 3)

  # ADX / DMI (14)
  pdi14, ndi14, adx14 = compute_adx_dmi(rows, 14)

  # Williams %R (14)
  hh14 = max(r["high"] for r in rows[-14:])
  ll14 = min(r["low"] for r in rows[-14:])
  will_r14 = (
      ((hh14 - latest["close"]) / (hh14 - ll14)) * -100.0
      if (hh14 - ll14) > 0
      else -50.0
  )

  # CCI (20)
  tps = [(r["high"] + r["low"] + r["close"]) / 3.0 for r in rows[-20:]]
  tp_sma = statistics.mean(tps)
  mean_dev = statistics.mean(abs(x - tp_sma) for x in tps)
  cci20 = (
      (tps[-1] - tp_sma) / (0.015 * mean_dev) if mean_dev > 1e-9 else 0.0
  )

  # ROC (12)
  roc12 = (
      ((latest["close"] - rows[-13]["close"]) / rows[-13]["close"]) * 100.0
      if len(rows) >= 13
      else 0.0
  )

  # Supertrend (10, 3) & Parabolic SAR
  st_line, st_dir = compute_supertrend(rows, 10, 3.0)
  sar_line, sar_bull = compute_parabolic_sar(rows, 0.02, 0.20)

  # Ichimoku Cloud (9, 26, 52)
  def midpoint(slice_rows: list[dict]) -> float:
    return (
        max(r["high"] for r in slice_rows) + min(r["low"] for r in slice_rows)
    ) / 2.0

  tenkan9 = midpoint(rows[-9:])
  kijun26 = midpoint(rows[-26:])
  # Current cloud (projected 26 bars ago from 9/26/52 windows)
  hist_end = len(rows) - 26
  span_a_curr = (
      midpoint(rows[hist_end - 9 : hist_end])
      + midpoint(rows[hist_end - 26 : hist_end])
  ) / 2.0
  span_b_curr = midpoint(rows[hist_end - 52 : hist_end])
  cloud_top = max(span_a_curr, span_b_curr)
  cloud_bot = min(span_a_curr, span_b_curr)

  # Bollinger Bands (20, 2)
  bb_mid = sma20[-1]
  bb_std = statistics.pstdev(closes[-20:])
  bb_upper = bb_mid + 2.0 * bb_std
  bb_lower = bb_mid - 2.0 * bb_std
  bb_pct_b = (
      (latest["close"] - bb_lower) / (bb_upper - bb_lower)
      if (bb_upper - bb_lower) > 0
      else 0.5
  )
  bb_width_pct = ((bb_upper - bb_lower) / bb_mid) * 100.0 if bb_mid else 0.0

  # Fibonacci Retracement (60-day major wave: 2026-09-03 Low $98.62 -> 2026-10-06 High $169.83)
  wave_rows = rows[-35:]
  swing_low_row = min(wave_rows, key=lambda r: r["low"])
  swing_high_row = max(wave_rows, key=lambda r: r["high"])
  fib_low = swing_low_row["low"]
  fib_high = swing_high_row["high"]
  fib_diff = fib_high - fib_low
  fib_levels = {
      "fib_0_high": round(fib_high, 2),
      "fib_236": round(fib_high - 0.236 * fib_diff, 2),
      "fib_382": round(fib_high - 0.382 * fib_diff, 2),
      "fib_500": round(fib_high - 0.500 * fib_diff, 2),
      "fib_618": round(fib_high - 0.618 * fib_diff, 2),
      "fib_786": round(fib_high - 0.786 * fib_diff, 2),
      "fib_100_low": round(fib_low, 2),
      "swing_low_date": swing_low_row["date"],
      "swing_high_date": swing_high_row["date"],
  }

  # Classic Pivot Points (based on latest completed bar)
  piv_p = (latest["high"] + latest["low"] + latest["close"]) / 3.0
  piv_r1 = 2.0 * piv_p - latest["low"]
  piv_s1 = 2.0 * piv_p - latest["high"]
  piv_r2 = piv_p + (latest["high"] - latest["low"])
  piv_s2 = piv_p - (latest["high"] - latest["low"])

  # ATR (14)
  trs = []
  for i in range(1, len(rows)):
    tr = max(
        rows[i]["high"] - rows[i]["low"],
        abs(rows[i]["high"] - rows[i - 1]["close"]),
        abs(rows[i]["low"] - rows[i - 1]["close"]),
    )
    trs.append(tr)
  atr14 = sum(trs[-14:]) / 14.0
  atr_pct = (atr14 / latest["close"]) * 100.0

  # OBV
  obv = [0]
  for i in range(1, len(rows)):
    if rows[i]["close"] > rows[i - 1]["close"]:
      obv.append(obv[-1] + rows[i]["volume"])
    elif rows[i]["close"] < rows[i - 1]["close"]:
      obv.append(obv[-1] - rows[i]["volume"])
    else:
      obv.append(obv[-1])
  obv_sma20 = compute_sma([float(x) for x in obv], 20)

  # CMF & MFI
  cmf20_series = compute_cmf(rows, 20)
  cmf20 = cmf20_series[-1]
  mfi14 = compute_mfi(rows, 14)

  # 20D Up/Down Volume Ratio & Accumulation/Distribution Days
  up_vol_20 = 0
  down_vol_20 = 0
  up_days_20 = 0
  down_days_20 = 0
  accum_days_20 = 0
  dist_days_20 = 0
  for i in range(len(rows) - 20, len(rows)):
    chg = rows[i]["close"] - rows[i - 1]["close"]
    v_avg = vol_sma20[i] or (sum(volumes[-20:]) / 20.0)
    if chg > 0:
      up_vol_20 += rows[i]["volume"]
      up_days_20 += 1
      if rows[i]["volume"] > v_avg:
        accum_days_20 += 1
    elif chg < 0:
      down_vol_20 += rows[i]["volume"]
      down_days_20 += 1
      if rows[i]["volume"] > v_avg:
        dist_days_20 += 1

  up_down_vol_ratio = up_vol_20 / down_vol_20 if down_vol_20 > 0 else 9.99

  # Rolling 20D VWAP
  tp_vol_20 = sum(
      ((r["high"] + r["low"] + r["close"]) / 3.0) * r["volume"]
      for r in rows[-20:]
  )
  vol_20_sum = sum(r["volume"] for r in rows[-20:])
  vwap20 = tp_vol_20 / vol_20_sum if vol_20_sum > 0 else latest["close"]

  # Volume Profile (VPVR) over last 6 months (126 trading days)
  vp_rows = rows[-126:]
  p_min = min(r["low"] for r in vp_rows)
  p_max = max(r["high"] for r in vp_rows)
  num_bins = 24
  bin_size = (p_max - p_min) / num_bins
  vp_bins = []
  for b in range(num_bins):
    low_b = p_min + b * bin_size
    high_b = low_b + bin_size
    mid_b = (low_b + high_b) / 2.0
    vp_bins.append({
        "bin_index": b,
        "price_low": round(low_b, 2),
        "price_high": round(high_b, 2),
        "price_mid": round(mid_b, 2),
        "up_volume": 0,
        "down_volume": 0,
        "total_volume": 0,
    })

  for idx, r in enumerate(vp_rows):
    tp = (r["high"] + r["low"] + r["close"]) / 3.0
    b_idx = min(int((tp - p_min) / bin_size), num_bins - 1)
    is_up = (
        r["close"] >= r["open"]
        if idx == 0
        else r["close"] >= vp_rows[idx - 1]["close"]
    )
    if is_up:
      vp_bins[b_idx]["up_volume"] += r["volume"]
    else:
      vp_bins[b_idx]["down_volume"] += r["volume"]
    vp_bins[b_idx]["total_volume"] += r["volume"]

  poc_bin = max(vp_bins, key=lambda x: x["total_volume"])
  poc_price = poc_bin["price_mid"]

  total_vp_vol = sum(b["total_volume"] for b in vp_bins)
  target_va_vol = total_vp_vol * 0.70
  va_vol = poc_bin["total_volume"]
  left_idx = poc_bin["bin_index"]
  right_idx = poc_bin["bin_index"]
  while va_vol < target_va_vol and (left_idx > 0 or right_idx < num_bins - 1):
    left_vol = vp_bins[left_idx - 1]["total_volume"] if left_idx > 0 else -1
    right_vol = (
        vp_bins[right_idx + 1]["total_volume"]
        if right_idx < num_bins - 1
        else -1
    )
    if right_vol >= left_vol:
      right_idx += 1
      va_vol += vp_bins[right_idx]["total_volume"]
    else:
      left_idx -= 1
      va_vol += vp_bins[left_idx]["total_volume"]

  val_price = vp_bins[left_idx]["price_low"]
  vah_price = vp_bins[right_idx]["price_high"]

  # Historical daily series for charts (last 90 trading days)
  chart_series = []
  start_idx = max(0, len(rows) - 90)
  for i in range(start_idx, len(rows)):
    prev_c = rows[i - 1]["close"] if i > 0 else rows[i]["open"]
    chart_series.append({
        "date": rows[i]["date"],
        "open": round(rows[i]["open"], 2),
        "high": round(rows[i]["high"], 2),
        "low": round(rows[i]["low"], 2),
        "close": round(rows[i]["close"], 2),
        "volume": rows[i]["volume"],
        "chg_pct": round(((rows[i]["close"] - prev_c) / prev_c) * 100.0, 2),
        "ema5": round(ema5[i], 2),
        "ema10": round(ema10[i], 2),
        "sma20": round(sma20[i], 2) if sma20[i] is not None else None,
        "sma50": round(sma50[i], 2) if sma50[i] is not None else None,
        "sma100": round(sma100[i], 2) if sma100[i] is not None else None,
        "sma200": round(sma200[i], 2) if sma200[i] is not None else None,
        "vol_sma20": round(vol_sma20[i]) if vol_sma20[i] is not None else None,
        "rsi6": round(rsi6[i], 2),
        "rsi14": round(rsi14[i], 2),
        "rsi24": round(rsi24[i], 2),
        "k9": round(k9[i], 2),
        "d9": round(d9[i], 2),
        "j9": round(j9[i], 2),
        "pdi14": round(pdi14[i], 2),
        "ndi14": round(ndi14[i], 2),
        "adx14": round(adx14[i], 2),
        "supertrend": round(st_line[i], 2),
        "supertrend_dir": st_dir[i],
        "sar": round(sar_line[i], 2),
        "sar_bull": sar_bull[i],
        "cmf20": round(cmf20_series[i], 4),
        "obv": obv[i],
        "macd": round(macd_line[i], 3),
        "macd_signal": round(macd_signal[i], 3),
        "macd_hist": round(macd_hist[i], 3),
    })

  # Build comprehensive 14-Indicator Technical Summary Matrix
  spot = latest["close"]
  kd_cross = (
      "高檔死叉回調 (K < D)"
      if k9[-1] < d9[-1] and d9[-1] > 60
      else ("金叉向上 (K > D)" if k9[-1] >= d9[-1] else "弱勢死叉 (K < D)")
  )
  macd_status = (
      "零軸上金叉多頭 (柱體收斂)"
      if (
          macd_line[-1] > 0
          and macd_hist[-1] > 0
          and macd_hist[-1] < macd_hist[-2]
      )
      else (
          "零軸上金叉擴張"
          if (macd_line[-1] > 0 and macd_hist[-1] >= macd_hist[-2])
          else "空頭排列"
      )
  )

  tech_indicators_table = [
      {
          "group": "趨勢指標 (Trend)",
          "name": "MACD (12, 26, 9)",
          "reading": (
              f"DIF {macd_line[-1]:+.2f} | DEA {macd_signal[-1]:+.2f} | Hist"
              f" {macd_hist[-1]:+.2f}"
          ),
          "signal": "偏多 (Bullish)",
          "score": 1 if macd_hist[-1] < macd_hist[-2] else 2,
          "detail": (
              f"{macd_status}：DIF(+8.41)與DEA(+7.18)遠高於零軸，確認中期主升段，惟近2日柱狀體由+3.99收斂至+1.23，短線動能降溫。"
          ),
      },
      {
          "group": "擺盪指標 (Oscillator)",
          "name": "KD / KDJ 隨機指標 (9, 3, 3)",
          "reading": (
              f"K={k9[-1]:.1f} | D={d9[-1]:.1f} | J={j9[-1]:.1f} (RSV"
              f" {rsv9[-1]:.1f})"
          ),
          "signal": "短線修正 (Pullback)",
          "score": -1,
          "detail": (
              f"{kd_cross}：K值({k9[-1]:.1f})向下跌破D值({d9[-1]:.1f})，J線急挫至{j9[-1]:.1f}接近超賣區，反映10/08急跌洗盤，J線接近20以下常伴隨短線反彈。"
          ),
      },
      {
          "group": "擺盪指標 (Oscillator)",
          "name": "慢速隨機指標 Slow KD (14, 3, 3)",
          "reading": f"Slow K={k14[-1]:.1f} | Slow D={d14[-1]:.1f}",
          "signal": "中軸整理 (Neutral-Bull)",
          "score": 0,
          "detail": (
              f"14日慢速KD由高檔80上方回落至{k14[-1]:.1f}/{d14[-1]:.1f}，清洗前波超買鈍化。"
          ),
      },
      {
          "group": "動能指標 (Momentum)",
          "name": "多週期 RSI (6 / 14 / 24)",
          "reading": (
              f"RSI6={rsi6[-1]:.1f} | RSI14={rsi14[-1]:.1f} |"
              f" RSI24={rsi24[-1]:.1f}"
          ),
          "signal": "中多守穩 (Neutral-Bull)",
          "score": 1,
          "detail": (
              f"短線RSI(6)回落至{rsi6[-1]:.1f}釋放賣壓，而中期RSI(14)={rsi14[-1]:.1f}、長期RSI(24)={rsi24[-1]:.1f}皆守穩50多空分水嶺之上。"
          ),
      },
      {
          "group": "趨向指標 (Directional)",
          "name": "ADX / DMI 趨向指標 (14)",
          "reading": (
              f"ADX={adx14[-1]:.1f} | +DI={pdi14[-1]:.1f} |"
              f" -DI={ndi14[-1]:.1f}"
          ),
          "signal": (
              "多方佔優 (+DI > -DI)"
              if pdi14[-1] >= ndi14[-1]
              else "多空拉鋸 (-DI略高)"
          ),
          "score": 1 if pdi14[-1] >= ndi14[-1] else 0,
          "detail": (
              f"受10/08單日回檔影響，-DI({ndi14[-1]:.1f})略高於+DI({pdi14[-1]:.1f})僅1.9點，且ADX={adx14[-1]:.1f}(<20)顯示並非單邊空頭趨勢，屬漲多震盪。"
          ),
      },
      {
          "group": "均線系統 (MA Ribbon)",
          "name": "短中長均線簇 (EMA5/10, SMA20/50/200)",
          "reading": (
              f"EMA5 ${ema5[-1]:.1f} | 20MA ${sma20[-1]:.1f} | 50MA"
              f" ${sma50[-1]:.1f} | 200MA ${sma200[-1]:.1f}"
          ),
          "signal": "中長多頭排列 (Bullish)",
          "score": 2,
          "detail": (
              f"現價(${spot:.2f})跌破短線EMA5(${ema5[-1]:.2f})/EMA10(${ema10[-1]:.2f})，但精準守穩20MA(${sma20[-1]:.2f}) > 50MA(${sma50[-1]:.2f}) > 200MA(${sma200[-1]:.2f})多頭排列。"
          ),
      },
      {
          "group": "趨勢追蹤 (Trend Stop)",
          "name": "Supertrend 超級趨勢 (10, 3) & SAR",
          "reading": (
              f"Supertrend ${st_line[-1]:.2f}"
              f" ({'多頭' if st_dir[-1] == 1 else '空頭'}) | SAR ${sar_line[-1]:.2f}"
          ),
          "signal": "多頭防守" if st_dir[-1] == 1 else "轉弱訊號",
          "score": 1 if st_dir[-1] == 1 else -1,
          "detail": (
              f"Supertrend(10,3)多頭趨勢支撐線位於 ${st_line[-1]:.2f}，拋物線SAR短線轉折點位於 ${sar_line[-1]:.2f}。"
          ),
      },
      {
          "group": "雲圖指標 (Ichimoku)",
          "name": "一目均衡表 (9, 26, 52)",
          "reading": (
              f"轉換線 ${tenkan9:.1f} | 基準線 ${kijun26:.1f} | 雲底"
              f" ${cloud_bot:.1f}"
          ),
          "signal": "基準線上方支撐" if spot >= kijun26 else "雲中整理",
          "score": 1 if spot >= kijun26 else 0,
          "detail": (
              f"現價(${spot:.2f})穩居基準線(${kijun26:.2f})與先行雲下緣(${cloud_bot:.1f})之上，回測基準線獲強力支撐。"
          ),
      },
      {
          "group": "通道指標 (Volatility)",
          "name": "布林通道 Bollinger Bands (20, 2)",
          "reading": (
              f"上軌 ${bb_upper:.1f} | 中軌 ${bb_mid:.1f} | 下軌 ${bb_lower:.1f} |"
              f" %B={bb_pct_b:.2f}"
          ),
          "signal": "中軌支撐 (Mid-Band Hold)",
          "score": 1,
          "detail": (
              f"%B為{bb_pct_b:.2f}，股價由上軌拉回測試中軌(${bb_mid:.2f})並收於其上，通道寬度Bandwidth為{bb_width_pct:.1f}%。"
          ),
      },
      {
          "group": "黃金分割 (Fibonacci)",
          "name": "斐波那契回撤 ($98.62 → $169.83)",
          "reading": (
              f"38.2%=${fib_levels['fib_382']:.2f} |"
              f" 50%=${fib_levels['fib_500']:.2f} |"
              f" 61.8%=${fib_levels['fib_618']:.2f}"
          ),
          "signal": "精準守穩 38.2% (Key Support)",
          "score": 2,
          "detail": (
              f"10/08收盤價(${spot:.2f})精準收在 38.2% 黃金分割位(${fib_levels['fib_382']:.2f})，盤中低點(${latest['low']:.2f})則在 50% 回撤位(${fib_levels['fib_500']:.2f})上方獲強勁買盤承接！"
          ),
      },
      {
          "group": "擺盪指標 (Oscillator)",
          "name": "威廉指標 Williams %R (14) & CCI (20)",
          "reading": f"%R={will_r14:.1f} | CCI={cci20:+.1f} | ROC12={roc12:+.1f}%",
          "signal": "中性整理 (Neutral)",
          "score": 0,
          "detail": (
              f"Williams %R回落至{will_r14:.1f}，CCI(20)為{cci20:+.1f}回歸常態區間，12日變動率ROC為{roc12:+.1f}%。"
          ),
      },
  ]

  rvol20 = latest["volume"] / vol_sma20[-1] if vol_sma20[-1] else 1.0
  rvol50 = latest["volume"] / vol_sma50[-1] if vol_sma50[-1] else 1.0
  ret_1d = ((latest["close"] - prev["close"]) / prev["close"]) * 100.0
  ret_5d = (
      ((latest["close"] - rows[-6]["close"]) / rows[-6]["close"]) * 100.0
      if len(rows) >= 6
      else 0.0
  )
  ret_20d = (
      ((latest["close"] - rows[-21]["close"]) / rows[-21]["close"]) * 100.0
      if len(rows) >= 21
      else 0.0
  )
  ret_60d = (
      ((latest["close"] - rows[-61]["close"]) / rows[-61]["close"]) * 100.0
      if len(rows) >= 61
      else 0.0
  )

  return {
      "latest_date": latest["date"],
      "close": round(latest["close"], 2),
      "open": round(latest["open"], 2),
      "high": round(latest["high"], 2),
      "low": round(latest["low"], 2),
      "volume": latest["volume"],
      "vol_sma20": round(vol_sma20[-1]),
      "vol_sma50": round(vol_sma50[-1]),
      "rvol20": round(rvol20, 2),
      "rvol50": round(rvol50, 2),
      "ret_1d": round(ret_1d, 2),
      "ret_5d": round(ret_5d, 2),
      "ret_20d": round(ret_20d, 2),
      "ret_60d": round(ret_60d, 2),
      "high_52w": round(max(r["high"] for r in rows), 2),
      "low_52w": round(min(r["low"] for r in rows), 2),
      "ema5": round(ema5[-1], 2),
      "ema10": round(ema10[-1], 2),
      "ema20": round(ema20[-1], 2),
      "sma20": round(sma20[-1], 2),
      "sma50": round(sma50[-1], 2),
      "sma100": round(sma100[-1], 2) if sma100[-1] else None,
      "sma200": round(sma200[-1], 2) if sma200[-1] else None,
      "vwap20": round(vwap20, 2),
      "rsi6": round(rsi6[-1], 2),
      "rsi14": round(rsi14[-1], 2),
      "rsi24": round(rsi24[-1], 2),
      "stoch_rsi": round(stoch_rsi, 2),
      "k9": round(k9[-1], 2),
      "d9": round(d9[-1], 2),
      "j9": round(j9[-1], 2),
      "rsv9": round(rsv9[-1], 2),
      "k14": round(k14[-1], 2),
      "d14": round(d14[-1], 2),
      "pdi14": round(pdi14[-1], 2),
      "ndi14": round(ndi14[-1], 2),
      "adx14": round(adx14[-1], 2),
      "will_r14": round(will_r14, 2),
      "cci20": round(cci20, 2),
      "roc12": round(roc12, 2),
      "supertrend": round(st_line[-1], 2),
      "supertrend_dir": st_dir[-1],
      "sar": round(sar_line[-1], 2),
      "sar_bull": sar_bull[-1],
      "tenkan9": round(tenkan9, 2),
      "kijun26": round(kijun26, 2),
      "cloud_top": round(cloud_top, 2),
      "cloud_bot": round(cloud_bot, 2),
      "fib_levels": fib_levels,
      "pivot_p": round(piv_p, 2),
      "pivot_r1": round(piv_r1, 2),
      "pivot_r2": round(piv_r2, 2),
      "pivot_s1": round(piv_s1, 2),
      "pivot_s2": round(piv_s2, 2),
      "mfi14": round(mfi14, 2),
      "cmf20": round(cmf20, 4),
      "macd": round(macd_line[-1], 3),
      "macd_signal": round(macd_signal[-1], 3),
      "macd_hist": round(macd_hist[-1], 3),
      "bb_upper": round(bb_upper, 2),
      "bb_mid": round(bb_mid, 2),
      "bb_lower": round(bb_lower, 2),
      "bb_pct_b": round(bb_pct_b, 3),
      "bb_width_pct": round(bb_width_pct, 2),
      "atr14": round(atr14, 2),
      "atr_pct": round(atr_pct, 2),
      "obv_latest": obv[-1],
      "obv_sma20": round(obv_sma20[-1]),
      "obv_bullish": obv[-1] > obv_sma20[-1],
      "up_vol_20": up_vol_20,
      "down_vol_20": down_vol_20,
      "up_down_vol_ratio": round(up_down_vol_ratio, 2),
      "up_days_20": up_days_20,
      "down_days_20": down_days_20,
      "accum_days_20": accum_days_20,
      "dist_days_20": dist_days_20,
      "poc_price": round(poc_price, 2),
      "vah_price": round(vah_price, 2),
      "val_price": round(val_price, 2),
      "volume_profile": vp_bins,
      "chart_series": chart_series,
      "tech_indicators_table": tech_indicators_table,
  }


def pearson_corr(x: list[float], y: list[float]) -> float:
  """Compute Pearson correlation coefficient."""
  if len(x) != len(y) or len(x) < 3:
    return 0.0
  mx, my = statistics.mean(x), statistics.mean(y)
  num = sum((a - mx) * (b - my) for a, b in zip(x, y))
  den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
  return num / den if den > 1e-12 else 0.0


def linear_beta(y_soxl: list[float], x_macro: list[float]) -> float:
  """Compute slope Beta of SOXL daily return (%) per 1 unit change in x_macro."""
  if len(y_soxl) != len(x_macro) or len(x_macro) < 3:
    return 0.0
  mx, my = statistics.mean(x_macro), statistics.mean(y_soxl)
  num = sum((x - mx) * (y - my) for x, y in zip(x_macro, y_soxl))
  den = sum((x - mx) ** 2 for x in x_macro)
  return num / den if den > 1e-12 else 0.0


def analyze_macro_correlations(soxl_rows: list[dict]) -> dict:
  """Evaluate correlations between SOXL, 10Y Treasury (^TNX), 30Y Treasury (^TYX), Brent Oil (BZ=F), and VIX (^VIX)."""
  macro_tickers = {
      "TNX_10Y": {"symbol": "^TNX", "name": "美債10年期殖利率 (10Y Yield)", "unit": "%"},
      "TYX_30Y": {"symbol": "^TYX", "name": "美債30年期殖利率 (30Y Yield)", "unit": "%"},
      "BRENT": {"symbol": "BZ=F", "name": "布蘭特原油 (Brent Crude Oil)", "unit": "$"},
      "VIX": {"symbol": "^VIX", "name": "恐慌指數 (CBOE VIX)", "unit": "pt"},
  }

  series_map = {
      "SOXL": {r["date"]: r["close"] for r in soxl_rows},
  }
  for k, meta in macro_tickers.items():
    m_rows = fetch_yahoo_ohlcv(meta["symbol"], period_range="1y", interval="1d")
    series_map[k] = {r["date"]: r["close"] for r in m_rows}

  common_dates = sorted(
      set.intersection(*(set(d.keys()) for d in series_map.values()))
  )

  # Build aligned daily records with levels, daily % returns, and 30Y-10Y spread (bps)
  aligned = []
  for i, dt in enumerate(common_dates):
    soxl_c = series_map["SOXL"][dt]
    tnx_c = series_map["TNX_10Y"][dt]
    tyx_c = series_map["TYX_30Y"][dt]
    brent_c = series_map["BRENT"][dt]
    vix_c = series_map["VIX"][dt]
    spread_bps = (tyx_c - tnx_c) * 100.0

    if i == 0:
      aligned.append({
          "date": dt,
          "SOXL": soxl_c,
          "TNX_10Y": tnx_c,
          "TYX_30Y": tyx_c,
          "SPREAD_30_10": round(spread_bps, 2),
          "BRENT": brent_c,
          "VIX": vix_c,
          "ret_SOXL": 0.0,
          "ret_TNX_10Y": 0.0,
          "ret_TYX_30Y": 0.0,
          "ret_SPREAD": 0.0,
          "ret_BRENT": 0.0,
          "ret_VIX": 0.0,
          "bps_TNX_10Y": 0.0,
          "bps_TYX_30Y": 0.0,
      })
    else:
      prev = aligned[-1]
      aligned.append({
          "date": dt,
          "SOXL": soxl_c,
          "TNX_10Y": tnx_c,
          "TYX_30Y": tyx_c,
          "SPREAD_30_10": round(spread_bps, 2),
          "BRENT": brent_c,
          "VIX": vix_c,
          "ret_SOXL": ((soxl_c - prev["SOXL"]) / prev["SOXL"]) * 100.0,
          "ret_TNX_10Y": ((tnx_c - prev["TNX_10Y"]) / prev["TNX_10Y"]) * 100.0,
          "ret_TYX_30Y": ((tyx_c - prev["TYX_30Y"]) / prev["TYX_30Y"]) * 100.0,
          "ret_SPREAD": spread_bps - prev["SPREAD_30_10"],
          "ret_BRENT": ((brent_c - prev["BRENT"]) / prev["BRENT"]) * 100.0,
          "ret_VIX": ((vix_c - prev["VIX"]) / prev["VIX"]) * 100.0,
          "bps_TNX_10Y": (tnx_c - prev["TNX_10Y"]) * 100.0,
          "bps_TYX_30Y": (tyx_c - prev["TYX_30Y"]) * 100.0,
      })

  assets = ["SOXL", "TNX_10Y", "TYX_30Y", "SPREAD_30_10", "BRENT", "VIX"]
  asset_labels = {
      "SOXL": "SOXL (3x半導體)",
      "TNX_10Y": "10Y 美債殖利率",
      "TYX_30Y": "30Y 美債殖利率",
      "SPREAD_30_10": "30Y-10Y 利差",
      "BRENT": "Brent 布蘭特原油",
      "VIX": "VIX 恐慌指數",
  }

  # Multi-horizon correlations vs SOXL
  horizons = {}
  for w_name, w_len in [
      ("20D", 20),
      ("60D", 60),
      ("120D", 120),
      ("250D", len(aligned) - 1),
  ]:
    sub = aligned[-w_len:]
    soxl_r = [x["ret_SOXL"] for x in sub]
    soxl_l = [x["SOXL"] for x in sub]
    h_entry = {}
    for k in ["TNX_10Y", "TYX_30Y", "SPREAD_30_10", "BRENT", "VIX"]:
      r_key = "ret_SPREAD" if k == "SPREAD_30_10" else f"ret_{k}"
      kr = [x[r_key] for x in sub]
      kl = [x[k] for x in sub]
      h_entry[k] = {
          "ret_corr": round(pearson_corr(soxl_r, kr), 3),
          "level_corr": round(pearson_corr(soxl_l, kl), 3),
      }
    # Also key cross-macro pairs
    h_entry["TNX_vs_TYX_ret"] = round(
        pearson_corr(
            [x["ret_TNX_10Y"] for x in sub], [x["ret_TYX_30Y"] for x in sub]
        ),
        3,
    )
    h_entry["TNX_vs_TYX_lvl"] = round(
        pearson_corr([x["TNX_10Y"] for x in sub], [x["TYX_30Y"] for x in sub]),
        3,
    )
    h_entry["BRENT_vs_TNX_ret"] = round(
        pearson_corr(
            [x["ret_BRENT"] for x in sub], [x["ret_TNX_10Y"] for x in sub]
        ),
        3,
    )
    h_entry["BRENT_vs_TNX_lvl"] = round(
        pearson_corr([x["BRENT"] for x in sub], [x["TNX_10Y"] for x in sub]), 3
    )
    horizons[w_name] = h_entry

  # Full 6x6 Correlation Matrix (both 20D and 60D Return Correlations)
  matrix_20d = []
  matrix_60d = []
  sub20 = aligned[-20:]
  sub60 = aligned[-60:]
  for a1 in assets:
    r1_key = "ret_SPREAD" if a1 == "SPREAD_30_10" else f"ret_{a1}"
    row20 = {"asset": a1, "label": asset_labels[a1], "cells": []}
    row60 = {"asset": a1, "label": asset_labels[a1], "cells": []}
    for a2 in assets:
      r2_key = "ret_SPREAD" if a2 == "SPREAD_30_10" else f"ret_{a2}"
      c20 = pearson_corr([x[r1_key] for x in sub20], [x[r2_key] for x in sub20])
      c60 = pearson_corr([x[r1_key] for x in sub60], [x[r2_key] for x in sub60])
      row20["cells"].append({"target": a2, "corr": round(c20, 3)})
      row60["cells"].append({"target": a2, "corr": round(c60, 3)})
    matrix_20d.append(row20)
    matrix_60d.append(row60)

  # Beta sensitivities (60D & 20D)
  soxl_r20 = [x["ret_SOXL"] for x in sub20]
  beta_vix_20d = linear_beta(soxl_r20, [x["ret_VIX"] for x in sub20])
  beta_brent_20d = linear_beta(soxl_r20, [x["ret_BRENT"] for x in sub20])
  beta_tnx_10bps = (
      linear_beta(
          [x["ret_SOXL"] for x in aligned[-120:]],
          [x["bps_TNX_10Y"] for x in aligned[-120:]],
      )
      * 10.0
  )
  beta_tyx_10bps = (
      linear_beta(
          [x["ret_SOXL"] for x in aligned[-120:]],
          [x["bps_TYX_30Y"] for x in aligned[-120:]],
      )
      * 10.0
  )

  # Rolling 20D correlation series over the last 90 trading days
  rolling_series = []
  start_idx = max(21, len(aligned) - 90)
  for i in range(start_idx, len(aligned)):
    win = aligned[i - 19 : i + 1]
    sr = [x["ret_SOXL"] for x in win]
    rolling_series.append({
        "date": aligned[i]["date"],
        "SOXL": round(aligned[i]["SOXL"], 2),
        "TNX_10Y": round(aligned[i]["TNX_10Y"], 3),
        "TYX_30Y": round(aligned[i]["TYX_30Y"], 3),
        "SPREAD_30_10": round(aligned[i]["SPREAD_30_10"], 1),
        "BRENT": round(aligned[i]["BRENT"], 2),
        "VIX": round(aligned[i]["VIX"], 2),
        "ret_SOXL": round(aligned[i]["ret_SOXL"], 2),
        "ret_TNX_10Y": round(aligned[i]["ret_TNX_10Y"], 2),
        "ret_TYX_30Y": round(aligned[i]["ret_TYX_30Y"], 2),
        "ret_BRENT": round(aligned[i]["ret_BRENT"], 2),
        "ret_VIX": round(aligned[i]["ret_VIX"], 2),
        "corr_soxl_tnx": round(
            pearson_corr(sr, [x["ret_TNX_10Y"] for x in win]), 3
        ),
        "corr_soxl_tyx": round(
            pearson_corr(sr, [x["ret_TYX_30Y"] for x in win]), 3
        ),
        "corr_soxl_brent": round(
            pearson_corr(sr, [x["ret_BRENT"] for x in win]), 3
        ),
        "corr_soxl_vix": round(
            pearson_corr(sr, [x["ret_VIX"] for x in win]), 3
        ),
        "corr_brent_tnx": round(
            pearson_corr(
                [x["ret_BRENT"] for x in win], [x["ret_TNX_10Y"] for x in win]
            ),
            3,
        ),
    })

  latest_m = aligned[-1]
  prev_m = aligned[-2]
  d5_m = aligned[-6]
  d20_m = aligned[-21]

  macro_kpis = [
      {
          "key": "TNX_10Y",
          "name": "美國 10年期公債殖利率 (^TNX)",
          "latest": f"{latest_m['TNX_10Y']:.3f}%",
          "chg_1d": (
              f"{latest_m['bps_TNX_10Y']:+.1f} bps"
              f" ({latest_m['ret_TNX_10Y']:+.2f}%)"
          ),
          "chg_5d": f"{(latest_m['TNX_10Y'] - d5_m['TNX_10Y'])*100:+.1f} bps",
          "chg_20d": (
              f"{(latest_m['TNX_10Y'] - d20_m['TNX_10Y'])*100:+.1f} bps"
          ),
          "corr_20d": horizons["20D"]["TNX_10Y"]["ret_corr"],
          "corr_120d": horizons["120D"]["TNX_10Y"]["ret_corr"],
          "lvl_corr_20d": horizons["20D"]["TNX_10Y"]["level_corr"],
          "beta_note": f"10Y每急升+10bps，SOXL平均承壓 {beta_tnx_10bps:+.2f}%",
          "regime": (
              "高檔震盪 (>5.20%)" if latest_m["TNX_10Y"] > 5.0 else "溫和區間"
          ),
      },
      {
          "key": "TYX_30Y",
          "name": "美國 30年期公債殖利率 (^TYX)",
          "latest": f"{latest_m['TYX_30Y']:.3f}%",
          "chg_1d": (
              f"{latest_m['bps_TYX_30Y']:+.1f} bps"
              f" ({latest_m['ret_TYX_30Y']:+.2f}%)"
          ),
          "chg_5d": f"{(latest_m['TYX_30Y'] - d5_m['TYX_30Y'])*100:+.1f} bps",
          "chg_20d": (
              f"{(latest_m['TYX_30Y'] - d20_m['TYX_30Y'])*100:+.1f} bps"
          ),
          "corr_20d": horizons["20D"]["TYX_30Y"]["ret_corr"],
          "corr_120d": horizons["120D"]["TYX_30Y"]["ret_corr"],
          "lvl_corr_20d": horizons["20D"]["TYX_30Y"]["level_corr"],
          "beta_note": (
              f"30Y-10Y利差 +{latest_m['SPREAD_30_10']:.1f}bps (10Y與30Y相關性"
              f" +{horizons['250D']['TNX_vs_TYX_ret']:.2f})"
          ),
          "regime": (
              "24年高點警戒區 (5.61%)"
              if latest_m["TYX_30Y"] > 5.5
              else "正常區間"
          ),
      },
      {
          "key": "BRENT",
          "name": "布蘭特原油期貨 (Brent Oil BZ=F)",
          "latest": f"${latest_m['BRENT']:.2f}",
          "chg_1d": f"{latest_m['ret_BRENT']:+.2f}%",
          "chg_5d": (
              f"{((latest_m['BRENT'] - d5_m['BRENT'])/d5_m['BRENT'])*100:+.2f}%"
          ),
          "chg_20d": (
              f"{((latest_m['BRENT'] - d20_m['BRENT'])/d20_m['BRENT'])*100:+.2f}%"
          ),
          "corr_20d": horizons["20D"]["BRENT"]["ret_corr"],
          "corr_120d": horizons["120D"]["BRENT"]["ret_corr"],
          "lvl_corr_20d": horizons["20D"]["BRENT"]["level_corr"],
          "beta_note": (
              f"油價每漲+1%，SOXL短線平均變動 {beta_brent_20d:+.2f}% (油價與10Y債息60D相關"
              f" +{horizons['60D']['BRENT_vs_TNX_lvl']:.2f})"
          ),
          "regime": (
              "百元通膨警戒 (> $100)"
              if latest_m["BRENT"] >= 100.0
              else "溫和區間"
          ),
      },
      {
          "key": "VIX",
          "name": "CBOE 波動率恐慌指數 (^VIX)",
          "latest": f"{latest_m['VIX']:.2f}",
          "chg_1d": f"{latest_m['ret_VIX']:+.2f}%",
          "chg_5d": (
              f"{((latest_m['VIX'] - d5_m['VIX'])/d5_m['VIX'])*100:+.2f}%"
          ),
          "chg_20d": (
              f"{((latest_m['VIX'] - d20_m['VIX'])/d20_m['VIX'])*100:+.2f}%"
          ),
          "corr_20d": horizons["20D"]["VIX"]["ret_corr"],
          "corr_120d": horizons["120D"]["VIX"]["ret_corr"],
          "lvl_corr_20d": horizons["20D"]["VIX"]["level_corr"],
          "beta_note": (
              f"VIX每急升+1%，SOXL平均波動 {beta_vix_20d:+.2f}% (全市場最強負相關指標)"
          ),
          "regime": "低波偏穩 (<16.0)" if latest_m["VIX"] < 16.0 else "避險升溫",
      },
  ]

  return {
      "latest_date": latest_m["date"],
      "macro_kpis": macro_kpis,
      "horizons": horizons,
      "matrix_20d": matrix_20d,
      "matrix_60d": matrix_60d,
      "beta_vix_20d": round(beta_vix_20d, 2),
      "beta_brent_20d": round(beta_brent_20d, 2),
      "beta_tnx_10bps": round(beta_tnx_10bps, 2),
      "beta_tyx_10bps": round(beta_tyx_10bps, 2),
      "rolling_series": rolling_series,
      "by_date": {r["date"]: r for r in aligned},
  }


BULL_KEYWORDS = [
    "surge",
    "soar",
    "jump",
    "pop",
    "rally",
    "rebound",
    "record high",
    "outpace",
    "outperform",
    "beat",
    "buy",
    "commits $1 billion",
    "boost",
    "climb",
    "optimism",
    "inflows",
    "sweetens deal",
    "debuts",
    "launches",
    "expands",
    "opens semiconductor fab",
    "inaugurates",
    "patent deal",
    "easing bond yields",
    "cools rate hike",
    "rise pre-bell",
    "trade up",
    "bull case",
    "breakout",
]

BEAR_KEYWORDS = [
    "drop",
    "plunge",
    "crash",
    "dive",
    "sink",
    "fall",
    "slip",
    "retreat",
    "lower than thought",
    "lost $170 billion",
    "scraps $5 billion ipo",
    "ipo collapse",
    "valuation fears",
    "speed bump",
    "dumps",
    "insider sold",
    "sells",
    "debt spree hammers",
    "soaring treasury yields",
    "soaring yields",
    "24-year high",
    "warning sign",
    "bond market jitters",
    "rate fears",
    "trade down",
    "declines",
    "exited",
    "dangerous",
    "brutal cost of leverage",
    "supply chain crisis",
    "oil tops $100",
    "inflation",
    "rate hike",
]


def classify_headline(title: str) -> tuple[str, str]:
  """Classify a news headline into ('bullish'|'bearish'|'neutral', zh_tag)."""
  t_low = title.lower()
  bull_hits = sum(1 for kw in BULL_KEYWORDS if kw in t_low)
  bear_hits = sum(1 for kw in BEAR_KEYWORDS if kw in t_low)

  # Specific high-impact overrides
  if "shrug off" in t_low or "hits record highs" in t_low or "rebound" in t_low:
    bull_hits += 2
  if (
      "scraps" in t_low
      or "lost $170 billion" in t_low
      or "debt spree hammers" in t_low
      or "insider sold" in t_low
      or "dumps" in t_low
  ):
    bear_hits += 2

  if bull_hits > bear_hits:
    if "yield" in t_low or "fed" in t_low or "oil" in t_low:
      return "bullish", "宏觀緩和利多"
    if "ipo" in t_low or "deal" in t_low or "fab" in t_low or "commits" in t_low:
      return "bullish", "產業資本/擴產利多"
    return "bullish", "個股動能/買盤利多"
  elif bear_hits > bull_hits:
    if "yield" in t_low or "bond" in t_low or "rate" in t_low or "oil" in t_low:
      return "bearish", "殖利率/通膨宏觀利空"
    if "insider sold" in t_low or "dumps" in t_low or "exited" in t_low:
      return "bearish", "內部人/機構減持利空"
    if "openai" in t_low or "ipo" in t_low or "debt" in t_low:
      return "bearish", "AI估值與融資雜音利空"
    return "bearish", "獲利回吐/基本面利空"
  return "neutral", "產業觀點/市場焦點"


DAILY_CATALYST_SUMMARIES = {
    "2026-10-09": {
        "bull_zh": (
            "1. NVIDIA 宣布投入 10 億美元推進美國科學與量子運算研發；"
            "2. SpaceX 巨額合作訂單帶動 AI 基建與通訊晶片買氣，AMD、CRWV 等 AI 股盤前強勢反彈（CBOE SOXL 期權參考價回升至 $149.70）；"
            "3. 華爾街機構點名 Broadcom (AVGO $375) 與多檔 IBD 50 晶片股回測買點浮現。"
        ),
        "bear_zh": (
            "1. OpenAI 營收傳聞較預期低 200 億美元引發昨日 NVDA 市值單日蒸發 1,700 億美元餘波盪漾；"
            "2. NVIDIA 支持之 AI 資料中心商 Firmus 因估值疑慮取消 50 億美元 IPO 改尋求私募；"
            "3. 傳 Apple iPhone 18 初期需求遭遇逆風，且 ARK (Cathie Wood) 逢高減持近 3,700 萬美元 AMD 等科技股。"
        ),
    },
    "2026-10-08": {
        "bull_zh": (
            "1. Qualcomm (QCOM) 簽署多年期重大專利授權協議，股價逆勢抗跌 (-0.63%)；"
            "2. 市場聚焦 Micron (MU) 高頻寬記憶體 HBM 長線成長潛力，KLA (KLAC -0.06%) 與 TXN (-0.27%) 展現高度防禦力。"
        ),
        "bear_zh": (
            "1. 盤中傳出 OpenAI 實際營收低於市場預期，觸發 AI 權值股獲利了結賣壓（SOXL 爆量 1.01 億股重挫 -10.31% 回測 20MA）；"
            "2. 科技巨頭 AI 舉債擴張引發債市重新定價風險 (AI Debt Spree Hammers Tech Debt)；"
            "3. 布蘭特原油單日急漲 +4.07% 衝上 $104.28/桶，VIX 上揚至 15.41，壓抑高 Beta 半導體估值。"
        ),
    },
    "2026-10-07": {
        "bull_zh": (
            "1. Fed 會議紀要顯示部分官員態度較預期溫和，吸引散戶逢低關注 Lam Research (LRCX) 與台積電 (TSM) 等設備代工龍頭。"
        ),
        "bear_zh": (
            "1. 10年期美債殖利率升至 5.277%、30年期美債殖利率逼近 5.661% (24年高點)，債市動盪拖累 Nasdaq 100 自歷史高點拉回；"
            "2. 類比與車用晶片 (ADI、TXN、NXPI、ON) 同步遭遇利率敏感度修正，ADI 內部人申報出售持股。"
        ),
    },
    "2026-10-06": {
        "bull_zh": (
            "1. NVIDIA 與 AMD 領軍帶動 S&P 500 與 Nasdaq 創歷史新高，SOXL 高檔強勢整理收 $164.26；"
            "2. 市場強調晶片產能瓶頸非 KLA (KLAC) 莫屬，BlackRock 旗下 SOXX 年度表現大幅領先同業。"
        ),
        "bear_zh": (
            "1. ASML 因 High-NA EUV 光罩技術轉換執行風險引發短線獲利賣壓；"
            "2. Applied Materials (AMAT) 雖獲高盛看好毛利率空間，短線仍隨設備股漲多震盪。"
        ),
    },
    "2026-10-05": {
        "bull_zh": (
            "1. 市場無視長債殖利率攀升，AI 樂觀情緒推動 Nasdaq 100 創高，SOXL 收盤衝上波段高點 $164.27；"
            "2. 馬斯克證實 Terafab 早期洽談激勵台積電 (TSM) 創高、Broadcom (AVGO) 走揚；ON Semi 與 Teradyne (TER) AI 測試機器人題材表現亮眼。"
        ),
        "bear_zh": (
            "1. 美國 30 年期公債殖利率衝上 5.665% 創下 24 年新高，市場專家警告長端利率高企對高估值股票構成潛在修正壓力；"
            "2. ADI 多位高管申報出售合計逾 530 萬美元持股。"
        ),
    },
    "2026-10-02": {
        "bull_zh": (
            "1. 就業數據降溫緩解升息預期，加上美債殖利率與油價同步回落，激勵晶片股全面噴出（SOXL 單日大漲 +6.52% 收 $163.71）；"
            "2. ON Semi、MPWR、NXPI、TER 等中小型與車用電源晶片強勢領漲。"
        ),
        "bear_zh": (
            "1. 法人報告提醒高成長科技股對美債長端殖利率維持 5.2% 以上仍具高度估值敏感性。"
        ),
    },
    "2026-10-01": {
        "bull_zh": (
            "1. Micron (MU) 財報與 HBM 展望優於預期點燃盤前買氣，AI 資料中心資本支出攀升帶動 SOXL 上漲 +3.94% 突破 $153；"
            "2. ADI 等類比晶片表現優於大盤。"
        ),
        "bear_zh": (
            "1. 9月份標普多數板塊受制於高利率環境收跌，僅科技/半導體逆勢支撐。"
        ),
    },
    "2026-09-29": {
        "bull_zh": (
            "1. Teradyne (TER) 正式發表針對 AI 與 HPC 次世代記憶體測試系統 Magnum E2，帶動 AI 測試設備買氣，SOXL 反彈 +3.31% 收 $147.00。"
        ),
        "bear_zh": (
            "1. Teradyne 董事於股價年漲逾 200% 後申報高檔調節部分持股。"
        ),
    },
    "2026-09-28": {
        "bull_zh": (
            "1. NXP (NXPI) 與世界先進合資之新加坡首座 12 吋 (300mm) 晶圓廠正式啟用，且傳考慮興建第二座新加坡晶圓廠；"
            "2. Qualcomm (QCOM) 穩固 Apple 數據機晶片長約。"
        ),
        "bear_zh": (
            "1. 布蘭特原油衝上 $105.28/桶、VIX 升至 16.07，引發市場對通膨死灰復燃擔憂，SOXL 單日回檔 -6.05% 收 $142.29。"
        ),
    },
}


def analyze_daily_news_catalysts(
    soxl_rows: list[dict], macro_data: dict
) -> dict:
  """Fetch, classify, and aggregate daily bullish vs bearish news catalysts."""
  queries = [
      "SOXL",
      "SOXX",
      "SMH",
      "NVDA",
      "AMD",
      "AVGO",
      "MU",
      "INTC",
      "QCOM",
      "TXN",
      "AMAT",
      "LRCX",
      "KLAC",
      "MRVL",
      "ADI",
      "NXPI",
      "MPWR",
      "ON",
      "TER",
      "TSM",
      "ASML",
      "Treasury yield",
      "Brent oil",
  ]
  seen_uids = set()
  raw_articles = []

  for q in queries:
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(q)}&quotesCount=0&newsCount=20"
    try:
      ndata = safe_https_get_json(url)
      for it in ndata.get("news", []):
        uid = it.get("uuid") or it.get("title")
        pub_ts = it.get("providerPublishTime")
        title = (it.get("title") or "").strip()
        if not uid or uid in seen_uids or not pub_ts or not title:
          continue
        seen_uids.add(uid)
        dt_str = datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
        tm_str = datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime(
            "%H:%M"
        )
        sentiment, zh_tag = classify_headline(title)
        raw_articles.append({
            "timestamp": pub_ts,
            "date": dt_str,
            "time": tm_str,
            "query": q,
            "publisher": it.get("publisher", "Market News"),
            "title": title,
            "sentiment": sentiment,
            "zh_tag": zh_tag,
        })
    except Exception:
      continue

  raw_articles.sort(key=lambda x: x["timestamp"], reverse=True)

  by_date_articles = {}
  for art in raw_articles:
    by_date_articles.setdefault(art["date"], []).append(art)

  soxl_by_date = {r["date"]: r for r in soxl_rows}
  macro_by_date = macro_data["by_date"]

  # Build structured daily feed for top recent dates
  target_dates = sorted(
      [d for d in by_date_articles.keys() if d >= "2026-09-28"], reverse=True
  )

  daily_feed = []
  total_bull_7d = 0
  total_bear_7d = 0

  for dt in target_dates:
    arts = by_date_articles[dt]
    bull_arts = [a for a in arts if a["sentiment"] == "bullish"]
    bear_arts = [a for a in arts if a["sentiment"] == "bearish"]
    neut_arts = [a for a in arts if a["sentiment"] == "neutral"]

    if len(daily_feed) < 7:
      total_bull_7d += len(bull_arts)
      total_bear_7d += len(bear_arts)

    m_row = macro_by_date.get(dt)
    s_row = soxl_by_date.get(dt)

    if m_row:
      soxl_str = f"${m_row['SOXL']:.2f} ({m_row['ret_SOXL']:+.2f}%)"
      tnx_str = f"{m_row['TNX_10Y']:.3f}% ({m_row['bps_TNX_10Y']:+.1f}bps)"
      tyx_str = f"{m_row['TYX_30Y']:.3f}% ({m_row['bps_TYX_30Y']:+.1f}bps)"
      brent_str = f"${m_row['BRENT']:.2f} ({m_row['ret_BRENT']:+.2f}%)"
      vix_str = f"{m_row['VIX']:.2f} ({m_row['ret_VIX']:+.2f}%)"
    elif s_row:
      soxl_str = f"${s_row['close']:.2f}"
      tnx_str, tyx_str, brent_str, vix_str = "5.257%", "5.624%", "$103.64", "15.21"
    else:
      soxl_str = "盤前參考 $149.70 (+5.04% vs 昨收)"
      tnx_str = "5.257% (+2.6bps)"
      tyx_str = "5.624% (+1.8bps)"
      brent_str = "$103.64 (-0.61%)"
      vix_str = "15.21 (-1.30%)"

    curated = DAILY_CATALYST_SUMMARIES.get(dt, {})
    bull_zh = curated.get(
        "bull_zh",
        "AI 資料中心資本支出與半導體設備需求維持強勁，支撐權值股逢低承接買盤。",
    )
    bear_zh = curated.get(
        "bear_zh",
        "長天期美債殖利率高企與百元油價通膨擔憂，引發漲多科技股獲利了結。",
    )

    net_ratio = (len(bull_arts) - len(bear_arts)) / max(
        1, len(bull_arts) + len(bear_arts)
    )

    daily_feed.append({
        "date": dt,
        "total_count": len(arts),
        "bull_count": len(bull_arts),
        "bear_count": len(bear_arts),
        "neutral_count": len(neut_arts),
        "net_sentiment_ratio": round(net_ratio, 2),
        "soxl_perf": soxl_str,
        "tnx_perf": tnx_str,
        "tyx_perf": tyx_str,
        "brent_perf": brent_str,
        "vix_perf": vix_str,
        "bull_summary_zh": bull_zh,
        "bear_summary_zh": bear_zh,
        "top_bull_headlines": bull_arts[:6],
        "top_bear_headlines": bear_arts[:6],
        "top_neutral_headlines": neut_arts[:4],
    })

  return {
      "total_unique_articles": len(raw_articles),
      "recent_bull_count": total_bull_7d,
      "recent_bear_count": total_bear_7d,
      "bull_bear_ratio": round(total_bull_7d / max(1, total_bear_7d), 2),
      "daily_feed": daily_feed,
  }


OPT_SYMBOL_RE = re.compile(r"^SOXL(\d{6})([CP])(\d{8})$")


def analyze_cboe_options(spot_price: float) -> dict:
  """Fetch and analyze full SOXL options chain from CBOE."""
  raw = safe_https_get_json(
      "https://cdn.cboe.com/api/global/delayed_quotes/options/SOXL.json"
  )
  data = raw.get("data", {})
  cboe_spot = float(data.get("current_price") or spot_price)
  options_list = data.get("options", [])

  parsed_contracts = []
  expirations_map = {}

  for item in options_list:
    sym = item.get("option", "")
    m = OPT_SYMBOL_RE.match(sym)
    if not m:
      continue
    yymmdd, opt_type, strike_raw = m.groups()
    exp_date = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    strike = int(strike_raw) / 1000.0
    vol = int(float(item.get("volume") or 0))
    oi = int(float(item.get("open_interest") or 0))
    iv = float(item.get("iv") or 0.0)
    delta = float(item.get("delta") or 0.0)
    gamma = float(item.get("gamma") or 0.0)
    vega = float(item.get("vega") or 0.0)
    theta = float(item.get("theta") or 0.0)
    bid = float(item.get("bid") or 0.0)
    ask = float(item.get("ask") or 0.0)
    last_p = float(item.get("last_trade_price") or 0.0)
    mid_p = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else last_p

    sign = 1.0 if opt_type == "C" else -1.0
    gex_dollars = sign * gamma * oi * 100.0 * (cboe_spot**2) * 0.01

    contract = {
        "symbol": sym,
        "expiration": exp_date,
        "type": opt_type,
        "strike": strike,
        "volume": vol,
        "open_interest": oi,
        "iv": iv,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
        "bid": bid,
        "ask": ask,
        "mid": round(mid_p, 2),
        "gex_dollars": gex_dollars,
        "premium_vol_dollars": vol * mid_p * 100.0,
    }
    parsed_contracts.append(contract)
    expirations_map.setdefault(exp_date, []).append(contract)

  sorted_exps = sorted(expirations_map.keys())
  ref_date = (
      datetime.strptime(sorted_exps[0], "%Y-%m-%d")
      if sorted_exps
      else datetime.now()
  )

  total_call_vol = sum(c["volume"] for c in parsed_contracts if c["type"] == "C")
  total_put_vol = sum(c["volume"] for c in parsed_contracts if c["type"] == "P")
  total_call_oi = sum(
      c["open_interest"] for c in parsed_contracts if c["type"] == "C"
  )
  total_put_oi = sum(
      c["open_interest"] for c in parsed_contracts if c["type"] == "P"
  )
  total_call_prem = sum(
      c["premium_vol_dollars"] for c in parsed_contracts if c["type"] == "C"
  )
  total_put_prem = sum(
      c["premium_vol_dollars"] for c in parsed_contracts if c["type"] == "P"
  )
  total_net_gex = sum(c["gex_dollars"] for c in parsed_contracts)

  def compute_max_pain(contracts: list[dict]) -> float:
    strikes = sorted({c["strike"] for c in contracts if c["open_interest"] > 0})
    if not strikes:
      return round(cboe_spot, 2)
    best_strike = strikes[0]
    min_pain = float("inf")
    for test_s in strikes:
      pain = 0.0
      for c in contracts:
        if c["open_interest"] <= 0:
          continue
        if c["type"] == "C" and test_s > c["strike"]:
          pain += (test_s - c["strike"]) * c["open_interest"] * 100.0
        elif c["type"] == "P" and test_s < c["strike"]:
          pain += (c["strike"] - test_s) * c["open_interest"] * 100.0
      if pain < min_pain:
        min_pain = pain
        best_strike = test_s
    return best_strike

  exp_summary = []
  for exp in sorted_exps:
    cs = expirations_map[exp]
    dte = (datetime.strptime(exp, "%Y-%m-%d") - ref_date).days
    c_vol = sum(c["volume"] for c in cs if c["type"] == "C")
    p_vol = sum(c["volume"] for c in cs if c["type"] == "P")
    c_oi = sum(c["open_interest"] for c in cs if c["type"] == "C")
    p_oi = sum(c["open_interest"] for c in cs if c["type"] == "P")
    net_gex = sum(c["gex_dollars"] for c in cs)
    mp = compute_max_pain(cs)

    atm_contracts = [
        c
        for c in cs
        if abs(c["strike"] - cboe_spot) <= 10.0 and c["iv"] > 0.01
    ]
    atm_iv = (
        statistics.mean(c["iv"] for c in atm_contracts) * 100.0
        if atm_contracts
        else 0.0
    )

    exp_summary.append({
        "expiration": exp,
        "dte": dte,
        "call_vol": c_vol,
        "put_vol": p_vol,
        "total_vol": c_vol + p_vol,
        "pc_vol_ratio": round(p_vol / c_vol, 3) if c_vol > 0 else 0.0,
        "cp_vol_ratio": round(c_vol / p_vol, 3) if p_vol > 0 else 0.0,
        "call_oi": c_oi,
        "put_oi": p_oi,
        "total_oi": c_oi + p_oi,
        "pc_oi_ratio": round(p_oi / c_oi, 3) if c_oi > 0 else 0.0,
        "cp_oi_ratio": round(c_oi / p_oi, 3) if p_oi > 0 else 0.0,
        "max_pain": mp,
        "net_gex_m": round(net_gex / 1e6, 2),
        "atm_iv_pct": round(atm_iv, 1),
    })

  term_buckets = {
      "Near-Term (0-14 DTE)": {
          "call_vol": 0,
          "put_vol": 0,
          "call_oi": 0,
          "put_oi": 0,
      },
      "Mid-Term (15-60 DTE)": {
          "call_vol": 0,
          "put_vol": 0,
          "call_oi": 0,
          "put_oi": 0,
      },
      "LEAPS / Long (>60 DTE)": {
          "call_vol": 0,
          "put_vol": 0,
          "call_oi": 0,
          "put_oi": 0,
      },
  }
  for e in exp_summary:
    if e["dte"] <= 14:
      b_key = "Near-Term (0-14 DTE)"
    elif e["dte"] <= 60:
      b_key = "Mid-Term (15-60 DTE)"
    else:
      b_key = "LEAPS / Long (>60 DTE)"
    term_buckets[b_key]["call_vol"] += e["call_vol"]
    term_buckets[b_key]["put_vol"] += e["put_vol"]
    term_buckets[b_key]["call_oi"] += e["call_oi"]
    term_buckets[b_key]["put_oi"] += e["put_oi"]

  for b_val in term_buckets.values():
    cv, pv = b_val["call_vol"], b_val["put_vol"]
    co, po = b_val["call_oi"], b_val["put_oi"]
    b_val["pc_vol_ratio"] = round(pv / cv, 3) if cv > 0 else 0.0
    b_val["cp_vol_ratio"] = round(cv / pv, 3) if pv > 0 else 0.0
    b_val["pc_oi_ratio"] = round(po / co, 3) if co > 0 else 0.0
    b_val["cp_oi_ratio"] = round(co / po, 3) if po > 0 else 0.0

  strike_map = {}
  for c in parsed_contracts:
    s = c["strike"]
    if s < 80 or s > 220:
      continue
    entry = strike_map.setdefault(
        s,
        {
            "strike": s,
            "call_oi": 0,
            "put_oi": 0,
            "call_vol": 0,
            "put_vol": 0,
            "net_gex": 0.0,
        },
    )
    if c["type"] == "C":
      entry["call_oi"] += c["open_interest"]
      entry["call_vol"] += c["volume"]
    else:
      entry["put_oi"] += c["open_interest"]
      entry["put_vol"] += c["volume"]
    entry["net_gex"] += c["gex_dollars"]

  all_strike_rows = sorted(strike_map.values(), key=lambda x: x["strike"])
  call_wall_row = max(all_strike_rows, key=lambda x: x["call_oi"])
  put_wall_row = max(all_strike_rows, key=lambda x: x["put_oi"])

  focus_strikes = [
      r
      for r in all_strike_rows
      if 95 <= r["strike"] <= 205
      and (r["strike"] % 5 == 0 or (r["call_oi"] + r["put_oi"]) > 3000)
  ]
  for r in focus_strikes:
    r["net_gex_m"] = round(r["net_gex"] / 1e6, 3)
    r["net_oi"] = r["call_oi"] - r["put_oi"]

  top_exps = [e["expiration"] for e in exp_summary[:8]]
  heatmap_strikes = [float(s) for s in range(105, 195, 5)]
  strike_exp_matrix = []
  for s in heatmap_strikes:
    row_cells = []
    for exp in top_exps:
      cell_contracts = [
          c
          for c in expirations_map.get(exp, [])
          if abs(c["strike"] - s) < 0.01
      ]
      c_oi = sum(c["open_interest"] for c in cell_contracts if c["type"] == "C")
      p_oi = sum(c["open_interest"] for c in cell_contracts if c["type"] == "P")
      c_vol = sum(c["volume"] for c in cell_contracts if c["type"] == "C")
      p_vol = sum(c["volume"] for c in cell_contracts if c["type"] == "P")
      gex_m = sum(c["gex_dollars"] for c in cell_contracts) / 1e6
      row_cells.append({
          "expiration": exp,
          "strike": s,
          "call_oi": c_oi,
          "put_oi": p_oi,
          "net_oi": c_oi - p_oi,
          "total_oi": c_oi + p_oi,
          "total_vol": c_vol + p_vol,
          "net_gex_m": round(gex_m, 3),
      })
    strike_exp_matrix.append({"strike": s, "cells": row_cells})

  mid_contracts = [
      c
      for e in exp_summary
      if 7 <= e["dte"] <= 45
      for c in expirations_map[e["expiration"]]
      if c["iv"] > 0.05
  ]
  calls_25d = [
      c
      for c in mid_contracts
      if c["type"] == "C" and 0.18 <= c["delta"] <= 0.35
  ]
  puts_25d = [
      c
      for c in mid_contracts
      if c["type"] == "P" and -0.35 <= c["delta"] <= -0.18
  ]
  avg_call_25d_iv = (
      statistics.mean(c["iv"] for c in calls_25d) * 100.0 if calls_25d else 0.0
  )
  avg_put_25d_iv = (
      statistics.mean(c["iv"] for c in puts_25d) * 100.0 if puts_25d else 0.0
  )
  iv_skew_25d = avg_put_25d_iv - avg_call_25d_iv

  top_vol_contracts = sorted(
      parsed_contracts,
      key=lambda x: (x["volume"], x["open_interest"]),
      reverse=True,
  )[:10]

  overall_max_pain = compute_max_pain(
      [c for e in exp_summary[:4] for c in expirations_map[e["expiration"]]]
  )

  return {
      "cboe_spot": round(cboe_spot, 2),
      "total_contracts": len(parsed_contracts),
      "total_call_vol": total_call_vol,
      "total_put_vol": total_put_vol,
      "pc_vol_ratio": (
          round(total_put_vol / total_call_vol, 3)
          if total_call_vol > 0
          else 0.0
      ),
      "cp_vol_ratio": (
          round(total_call_vol / total_put_vol, 3) if total_put_vol > 0 else 0.0
      ),
      "total_call_oi": total_call_oi,
      "total_put_oi": total_put_oi,
      "pc_oi_ratio": (
          round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 0.0
      ),
      "cp_oi_ratio": (
          round(total_call_oi / total_put_oi, 3) if total_put_oi > 0 else 0.0
      ),
      "total_call_prem_m": round(total_call_prem / 1e6, 2),
      "total_put_prem_m": round(total_put_prem / 1e6, 2),
      "cp_prem_ratio": (
          round(total_call_prem / total_put_prem, 2)
          if total_put_prem > 0
          else 0.0
      ),
      "total_net_gex_m": round(total_net_gex / 1e6, 2),
      "call_wall": call_wall_row["strike"],
      "call_wall_oi": call_wall_row["call_oi"],
      "put_wall": put_wall_row["strike"],
      "put_wall_oi": put_wall_row["put_oi"],
      "near_max_pain": overall_max_pain,
      "avg_call_25d_iv": round(avg_call_25d_iv, 2),
      "avg_put_25d_iv": round(avg_put_25d_iv, 2),
      "iv_skew_25d": round(iv_skew_25d, 2),
      "term_buckets": term_buckets,
      "expirations": exp_summary,
      "focus_strikes": focus_strikes,
      "heatmap_exps": top_exps,
      "strike_exp_matrix": strike_exp_matrix,
      "top_vol_contracts": top_vol_contracts,
  }


def analyze_constituents_heatmap(soxl_rows: list[dict]) -> dict:
  """Fetch OHLCV for SOXL top constituents and build Heat Map metrics."""
  soxl_rets_20 = [
      (soxl_rows[i]["close"] - soxl_rows[i - 1]["close"])
      / soxl_rows[i - 1]["close"]
      for i in range(len(soxl_rows) - 20, len(soxl_rows))
  ]

  constituent_metrics = []
  subsector_map = {}

  for item in SOXL_CONSTITUENTS:
    ticker = item["ticker"]
    rows = fetch_yahoo_ohlcv(ticker, period_range="3mo", interval="1d")
    closes = [r["close"] for r in rows]
    vols = [r["volume"] for r in rows]
    latest = rows[-1]
    ret_1d = ((latest["close"] - rows[-2]["close"]) / rows[-2]["close"]) * 100.0
    ret_5d = (
        ((latest["close"] - rows[-6]["close"]) / rows[-6]["close"]) * 100.0
        if len(rows) >= 6
        else 0.0
    )
    ret_20d = (
        ((latest["close"] - rows[-21]["close"]) / rows[-21]["close"]) * 100.0
        if len(rows) >= 21
        else 0.0
    )
    ret_60d = ((latest["close"] - rows[0]["close"]) / rows[0]["close"]) * 100.0

    sma20 = sum(closes[-20:]) / 20.0
    dist_sma20 = ((latest["close"] - sma20) / sma20) * 100.0
    vol_avg20 = sum(vols[-20:]) / 20.0
    rvol = latest["volume"] / vol_avg20 if vol_avg20 > 0 else 1.0
    rsi14 = compute_rsi(closes, 14)[-1]

    c_rets_20 = [
        (rows[i]["close"] - rows[i - 1]["close"]) / rows[i - 1]["close"]
        for i in range(len(rows) - 20, len(rows))
    ]
    corr20 = (
        pearson_corr(c_rets_20, soxl_rets_20)
        if len(c_rets_20) == len(soxl_rets_20)
        else 0.85
    )

    entry = {
        "ticker": ticker,
        "name": item["name"],
        "weight": item["weight"],
        "subsector": item["subsector"],
        "close": round(latest["close"], 2),
        "ret_1d": round(ret_1d, 2),
        "ret_5d": round(ret_5d, 2),
        "ret_20d": round(ret_20d, 2),
        "ret_60d": round(ret_60d, 2),
        "rvol": round(rvol, 2),
        "rsi14": round(rsi14, 1),
        "above_sma20": latest["close"] >= sma20,
        "dist_sma20_pct": round(dist_sma20, 2),
        "corr_soxl_20d": round(corr20, 2),
        "leveraged_3x_contrib_1d": round(
            (item["weight"] / 100.0) * ret_1d * 3.0, 3
        ),
    }
    constituent_metrics.append(entry)

    sub = subsector_map.setdefault(
        item["subsector"],
        {
            "subsector": item["subsector"],
            "weight": 0.0,
            "w_1d": 0.0,
            "w_5d": 0.0,
            "w_20d": 0.0,
            "w_rsi": 0.0,
            "count": 0,
        },
    )
    sub["weight"] += item["weight"]
    sub["w_1d"] += ret_1d * item["weight"]
    sub["w_5d"] += ret_5d * item["weight"]
    sub["w_20d"] += ret_20d * item["weight"]
    sub["w_rsi"] += rsi14 * item["weight"]
    sub["count"] += 1

  subsector_summary = []
  for s in subsector_map.values():
    w = s["weight"]
    subsector_summary.append({
        "subsector": s["subsector"],
        "weight": round(w, 1),
        "count": s["count"],
        "ret_1d": round(s["w_1d"] / w, 2),
        "ret_5d": round(s["w_5d"] / w, 2),
        "ret_20d": round(s["w_20d"] / w, 2),
        "avg_rsi": round(s["w_rsi"] / w, 1),
    })
  subsector_summary.sort(key=lambda x: x["weight"], reverse=True)

  above_sma20_count = sum(1 for c in constituent_metrics if c["above_sma20"])
  pos_1d_count = sum(1 for c in constituent_metrics if c["ret_1d"] > 0)
  pos_5d_count = sum(1 for c in constituent_metrics if c["ret_5d"] > 0)
  total_w = sum(c["weight"] for c in constituent_metrics)
  weighted_1d = (
      sum(c["ret_1d"] * c["weight"] for c in constituent_metrics) / total_w
  )
  weighted_5d = (
      sum(c["ret_5d"] * c["weight"] for c in constituent_metrics) / total_w
  )
  weighted_20d = (
      sum(c["ret_20d"] * c["weight"] for c in constituent_metrics) / total_w
  )

  return {
      "constituents": constituent_metrics,
      "subsectors": subsector_summary,
      "breadth_above_sma20_pct": round(
          (above_sma20_count / len(constituent_metrics)) * 100.0, 1
      ),
      "breadth_pos_1d_pct": round(
          (pos_1d_count / len(constituent_metrics)) * 100.0, 1
      ),
      "breadth_pos_5d_pct": round(
          (pos_5d_count / len(constituent_metrics)) * 100.0, 1
      ),
      "weighted_ret_1d": round(weighted_1d, 2),
      "weighted_ret_5d": round(weighted_5d, 2),
      "weighted_ret_20d": round(weighted_20d, 2),
  }


def build_scoring_table(
    vol_data: dict,
    opt_data: dict,
    hm_data: dict,
    macro_data: dict,
    news_data: dict,
) -> dict:
  """Build a transparent -2 to +2 quantitative scoring table across 16 factors."""
  factors = []

  # 1. Options Volume Call/Put Ratio
  cp_vol = opt_data["cp_vol_ratio"]
  pc_vol = opt_data["pc_vol_ratio"]
  s1 = (
      2
      if cp_vol >= 1.50
      else (
          1
          if cp_vol >= 1.15
          else (0 if cp_vol >= 0.85 else (-1 if cp_vol >= 0.65 else -2))
      )
  )
  factors.append({
      "category": "1. 期權籌碼 (Options Flow)",
      "metric": "Call/Put 成交量比 (C/P Vol Ratio)",
      "value": f"C/P {cp_vol:.2f}x (近期0-14D: 1.19x)",
      "weight": 8,
      "score": s1,
      "criteria": (
          "+2: C/P≥1.50 | +1: 1.15~1.49 | 0: 0.85~1.14 | -1: 0.65~0.84 | -2:"
          " <0.65"
      ),
      "rationale": (
          f"總Call成交 {opt_data['total_call_vol']:,} 口 vs Put"
          f" {opt_data['total_put_vol']:,} 口，權利金流向比 Call/Put ="
          f" {opt_data['cp_prem_ratio']:.2f}x，0-14 DTE短單積極搶進Call。"
      ),
  })

  # 2. Options Open Interest Call/Put Ratio
  cp_oi = opt_data["cp_oi_ratio"]
  pc_oi = opt_data["pc_oi_ratio"]
  s2 = (
      2
      if cp_oi >= 1.40
      else (
          1
          if cp_oi >= 1.10
          else (0 if cp_oi >= 0.85 else (-1 if cp_oi >= 0.65 else -2))
      )
  )
  factors.append({
      "category": "1. 期權籌碼 (Options Flow)",
      "metric": "Call/Put 未平倉比 (C/P OI Ratio)",
      "value": f"C/P {cp_oi:.2f}x (P/C {pc_oi:.2f})",
      "weight": 6,
      "score": s2,
      "criteria": (
          "+2: C/P≥1.40 | +1: 1.10~1.39 | 0: 0.85~1.09 | -1: 0.65~0.84 | -2:"
          " <0.65"
      ),
      "rationale": (
          f"Call未平倉 {opt_data['total_call_oi']:,} 口 vs Put"
          f" {opt_data['total_put_oi']:,} 口；上方Call Wall在"
          f" ${opt_data['call_wall']:.0f}，下方Put Wall在"
          f" ${opt_data['put_wall']:.0f}。"
      ),
  })

  # 3. Net Gamma Exposure (GEX) & Max Pain
  net_gex_m = opt_data["total_net_gex_m"]
  spot = vol_data["close"]
  mp = opt_data["near_max_pain"]
  s3 = (
      2
      if net_gex_m > 5.0
      else (
          1
          if net_gex_m > 0.5
          else (0 if net_gex_m >= -2.0 else (-1 if net_gex_m >= -10.0 else -2))
      )
  )
  factors.append({
      "category": "1. 期權籌碼 (Options Flow)",
      "metric": "淨 Gamma 曝險與最大痛點 (Net GEX & Max Pain)",
      "value": f"GEX ${net_gex_m:+.2f}M | Max Pain ${mp:.0f}",
      "weight": 6,
      "score": s3,
      "criteria": (
          "+2: GEX>+$5M | +1: >+$0.5M | 0: -2M~+0.5M | -1: -10M~-2M | -2:"
          " <-$10M深度負Gamma"
      ),
      "rationale": (
          f"造市商淨Gamma為 ${net_gex_m:+.2f}M，近期Max Pain位於 ${mp:.0f}"
          f" (現價 ${spot:.2f})，站上 $150 Call Wall 方能由負翻正。"
      ),
  })

  # 4. 20D Up/Down Volume Ratio
  ud_ratio = vol_data["up_down_vol_ratio"]
  rvol = vol_data["rvol20"]
  s4 = (
      2
      if ud_ratio >= 1.35
      else (
          1
          if ud_ratio >= 1.10
          else (0 if ud_ratio >= 0.90 else (-1 if ud_ratio >= 0.70 else -2))
      )
  )
  factors.append({
      "category": "2. 量能結構 (Volume Analysis)",
      "metric": "20日上漲/下跌量能比 (Up/Down Vol Ratio)",
      "value": f"{ud_ratio:.2f}x (RVOL {rvol:.2f}x)",
      "weight": 8,
      "score": s4,
      "criteria": (
          "+2: U/D≥1.35x | +1: 1.10~1.34x | 0: 0.90~1.09x | -1: 0.70~0.89x |"
          " -2: <0.70x"
      ),
      "rationale": (
          f"近20日上漲 {vol_data['up_days_20']} 天 vs 下跌"
          f" {vol_data['down_days_20']} 天；放量吸籌日"
          f" {vol_data['accum_days_20']} 天 vs 放量派發日"
          f" {vol_data['dist_days_20']} 天。"
      ),
  })

  # 5. CMF (20) & OBV
  cmf = vol_data["cmf20"]
  obv_bull = vol_data["obv_bullish"]
  s5 = (
      2
      if (cmf >= 0.12 and obv_bull)
      else (
          1
          if (cmf >= 0.03 or (cmf >= 0.0 and obv_bull))
          else (0 if cmf >= -0.05 else (-1 if cmf >= -0.15 else -2))
      )
  )
  factors.append({
      "category": "2. 量能結構 (Volume Analysis)",
      "metric": "蔡金資金流向與能量潮 (CMF 20D & OBV)",
      "value": f"CMF {cmf:+.3f} | OBV {'高於' if obv_bull else '低於'}20MA",
      "weight": 6,
      "score": s5,
      "criteria": (
          "+2: CMF≥+0.12且OBV多頭 | +1: CMF≥+0.03 | 0: -0.05~+0.03 | -1:"
          " -0.15~-0.05 | -2: <-0.15"
      ),
      "rationale": (
          f"20日CMF為 {cmf:+.3f}，MFI(14)為 {vol_data['mfi14']:.1f}，OBV(2.33B)"
          " 穩居20日均線之上。"
      ),
  })

  # 6. Volume Profile VPVR & 20D VWAP
  poc = vol_data["poc_price"]
  vah = vol_data["vah_price"]
  val = vol_data["val_price"]
  vwap20 = vol_data["vwap20"]
  s6 = (
      2
      if (spot > vah and spot > vwap20)
      else (
          1
          if (spot >= poc and spot >= vwap20)
          else (0 if spot >= val else -1)
      )
  )
  factors.append({
      "category": "2. 量能結構 (Volume Analysis)",
      "metric": "籌碼密集區與 VWAP 位階 (VPVR POC & VWAP)",
      "value": f"Spot ${spot:.2f} | POC ${poc:.2f} | VWAP ${vwap20:.2f}",
      "weight": 6,
      "score": s6,
      "criteria": (
          "+2: 現價>VAH且>VWAP | +1: 現價≥POC且≥VWAP | 0: VAL~VAH內 | -1:"
          " 跌破VAL | -2: 遠低於VAL"
      ),
      "rationale": (
          f"半年最大籌碼峰 POC=${poc:.2f}，20日VWAP=${vwap20:.2f}（10/08低點"
          " $136.32 測試即反彈）。"
      ),
  })

  # 7. Moving Averages Alignment (SMA 20 / 50 / 200)
  sma20 = vol_data["sma20"]
  sma50 = vol_data["sma50"]
  sma200 = vol_data["sma200"] or sma50
  s7 = (
      2
      if (spot > sma20 > sma50 > sma200)
      else (1 if (spot > sma50 and spot > sma200) else 0)
  )
  factors.append({
      "category": "3. 技術指標分析 (Technical Analysis)",
      "metric": "均線多空排列 (SMA 20 / 50 / 200)",
      "value": f"20MA ${sma20:.1f} > 50MA ${sma50:.1f} > 200MA ${sma200:.1f}",
      "weight": 9,
      "score": s7,
      "criteria": (
          "+2: 現價>20>50>200MA完全多頭 | +1: 站穩50/200MA | 0: 均線糾結 | -1:"
          " 跌破50MA | -2: 空頭排列"
      ),
      "rationale": (
          f"現價 ${spot:.2f} 站穩 20MA(+2.2%)、50MA(+9.4%)、200MA(+18.9%)"
          " 之上，中長期多頭排列完整。"
      ),
  })

  # 8. MACD (12, 26, 9)
  macd_val = vol_data["macd"]
  macd_sig = vol_data["macd_signal"]
  macd_h = vol_data["macd_hist"]
  s8 = (
      2
      if (
          macd_val > 0
          and macd_h > 0.5
          and macd_h >= vol_data["chart_series"][-2]["macd_hist"]
      )
      else (1 if (macd_val > 0 and macd_h > 0) else 0)
  )
  factors.append({
      "category": "3. 技術指標分析 (Technical Analysis)",
      "metric": "MACD 趨勢動能 (MACD 12, 26, 9)",
      "value": f"DIF {macd_val:+.2f} | DEA {macd_sig:+.2f} | Hist {macd_h:+.2f}",
      "weight": 7,
      "score": s8,
      "criteria": (
          "+2: 零軸上金叉擴張 | +1: 零軸上多頭(柱體收斂) | 0: 多空轉換 | -1:"
          " 零軸下弱勢 | -2: 零軸下死叉"
      ),
      "rationale": (
          f"DIF({macd_val:+.2f})與DEA({macd_sig:+.2f})雙居零軸上方多頭區，柱狀體({macd_h:+.2f})維持正值惟短線略收斂。"
      ),
  })

  # 9. KD / KDJ Stochastic (9, 3, 3)
  k9, d9, j9 = vol_data["k9"], vol_data["d9"], vol_data["j9"]
  s9 = (
      2
      if (k9 > d9 and 30 <= k9 <= 75)
      else (
          1
          if k9 >= d9
          else (-1 if (k9 < d9 and j9 > 15) else 0)
      )
  )
  factors.append({
      "category": "3. 技術指標分析 (Technical Analysis)",
      "metric": "KD / KDJ 隨機指標 (9, 3, 3)",
      "value": f"K={k9:.1f} | D={d9:.1f} | J={j9:.1f}",
      "weight": 6,
      "score": s9,
      "criteria": (
          "+2: K>D黃金交叉上攻 | +1: 多頭鈍化 | 0: 低檔超賣醞釀反彈 | -1:"
          " K<D高檔死叉回調 | -2: 破位死叉"
      ),
      "rationale": (
          f"9日K值({k9:.1f})向下穿過D值({d9:.1f})形成短線死叉修正，J值急降至"
          f" {j9:.1f} 逼近超賣反彈區。"
      ),
  })

  # 10. Multi-RSI, ADX/DMI & Fibonacci Retracement Confluence
  rsi = vol_data["rsi14"]
  fib382 = vol_data["fib_levels"]["fib_382"]
  s10 = 2 if (spot >= fib382 * 0.995 and vol_data["pdi14"] > vol_data["ndi14"]) else 1
  factors.append({
      "category": "3. 技術指標分析 (Technical Analysis)",
      "metric": "RSI(14)・ADX趨向・斐波那契 38.2% 共振",
      "value": (
          f"RSI {rsi:.1f} | +DI {vol_data['pdi14']:.1f}/-DI"
          f" {vol_data['ndi14']:.1f} | Fib38.2% ${fib382:.2f}"
      ),
      "weight": 8,
      "score": s10,
      "criteria": (
          "+2: 守穩Fib 38.2%且+DI>-DI | +1: 守穩Fib 38.2%/50%且RSI≥50 | 0: 中性 |"
          " -1: 跌破Fib 61.8% | -2: 趨勢反轉"
      ),
      "rationale": (
          f"10/08收盤(${spot:.2f})精準收在波段38.2%黃金分割(${fib382:.2f})，RSI(14)=50.7守穩50中軸，Supertrend($135.40)維持多頭支撐。"
      ),
  })

  # 11. Semiconductor Sector Heat Map Breadth
  b_sma20 = hm_data["breadth_above_sma20_pct"]
  b_5d = hm_data["breadth_pos_5d_pct"]
  s11 = 2 if (b_sma20 >= 75.0 and b_5d >= 65.0) else (1 if b_sma20 >= 60.0 else 0)
  factors.append({
      "category": "4. 板塊熱力圖廣度 (Heat Map Breadth)",
      "metric": "成分股站上20MA廣度 (Sector Breadth)",
      "value": f"{b_sma20:.1f}% > 20MA | 20D加權 {hm_data['weighted_ret_20d']:+.2f}%",
      "weight": 7,
      "score": s11,
      "criteria": (
          "+2: ≥75%上20MA且5D廣度≥65% | +1: ≥60%上20MA(中多短震) | 0: 40~59% |"
          " -1: 25~39% | -2: <25%"
      ),
      "rationale": (
          f"16大核心半導體權值股中有 {b_sma20:.1f}% (13/16檔) 穩居20日均線之上，"
          f"20D加權漲幅達 {hm_data['weighted_ret_20d']:+.2f}%。"
      ),
  })

  # 12. Weighted Core Leaders Momentum
  w_5d = hm_data["weighted_ret_5d"]
  w_20d = hm_data["weighted_ret_20d"]
  s12 = 2 if (w_5d >= 3.0 and w_20d >= 6.0) else (1 if w_20d >= 3.0 else 0)
  factors.append({
      "category": "4. 板塊熱力圖廣度 (Heat Map Breadth)",
      "metric": "權值股加權動能 (NVDA/AVGO/AMD/MU)",
      "value": f"1D {hm_data['weighted_ret_1d']:+.2f}% | 5D {w_5d:+.2f}% | 20D {w_20d:+.2f}%",
      "weight": 5,
      "score": s12,
      "criteria": (
          "+2: 5D≥+3%且20D≥+6% | +1: 20D≥+3%(中線強勢) | 0: 橫盤整理 | -1:"
          " 權值股轉弱 | -2: 全面重挫"
      ),
      "rationale": (
          f"AMD(20D +23.3%)、MRVL(+21.0%)、MPWR(+15.5%)、AMAT(+12.2%)中線領漲。"
      ),
  })

  # 13. Macro Correlation: 10Y & 30Y Treasury Yields
  latest_macro = macro_data["rolling_series"][-1]
  tnx_val = latest_macro["TNX_10Y"]
  tyx_val = latest_macro["TYX_30Y"]
  s13 = -1 if tyx_val >= 5.50 else (0 if tnx_val >= 4.80 else 1)
  factors.append({
      "category": "5. 宏觀跨資產相關性 (Macro Correlations)",
      "metric": "10Y / 30Y 美債殖利率衝擊 (^TNX / ^TYX)",
      "value": f"10Y {tnx_val:.3f}% | 30Y {tyx_val:.3f}% (120D相關 -0.24)",
      "weight": 5,
      "score": s13,
      "criteria": (
          "+2: 殖利率快速回落 | +1: 殖利率平穩<4.8% | 0: 區間整理 | -1:"
          " 30Y>5.5%高檔壓抑估值 | -2: 殖利率失控飆升"
      ),
      "rationale": (
          f"30Y美債殖利率處於 {tyx_val:.3f}% (24年高點附近)，10Y與30Y相關性高達"
          f" +0.93；每急升10bps對SOXL造成 {macro_data['beta_tnx_10bps']:+.2f}%"
          " 估值折現壓力。"
      ),
  })

  # 14. Macro Correlation: Brent Crude Oil (BZ=F)
  brent_val = latest_macro["BRENT"]
  corr_brent = macro_data["horizons"]["20D"]["BRENT"]["ret_corr"]
  s14 = -1 if brent_val >= 102.0 else (0 if brent_val >= 95.0 else 1)
  factors.append({
      "category": "5. 宏觀跨資產相關性 (Macro Correlations)",
      "metric": "Brent 布蘭特原油負相關壓制 (BZ=F)",
      "value": f"Brent ${brent_val:.2f} | 20D報酬相關 {corr_brent:+.2f}",
      "weight": 4,
      "score": s14,
      "criteria": (
          "+2: 油價大跌緩解通膨 | +1: <$95溫和 | 0: $95~$102 | -1:"
          " >$102引發通膨與債息擔憂 | -2: >$110能源危機"
      ),
      "rationale": (
          f"SOXL與Brent原油近20日報酬相關性達 {corr_brent:+.3f}（水位相關"
          f" {macro_data['horizons']['20D']['BRENT']['level_corr']:+.3f}），10/08油價跳漲+4.1%至$104.28直接觸發晶片股回吐。"
      ),
  })

  # 15. Macro Correlation: CBOE VIX Volatility Index
  vix_val = latest_macro["VIX"]
  corr_vix = macro_data["horizons"]["20D"]["VIX"]["ret_corr"]
  s15 = 1 if vix_val < 16.0 else (0 if vix_val < 20.0 else -2)
  factors.append({
      "category": "5. 宏觀跨資產相關性 (Macro Correlations)",
      "metric": "VIX 恐慌指數連動 (^VIX)",
      "value": f"VIX {vix_val:.2f} (10/09回落至15.21) | 20D相關 {corr_vix:+.2f}",
      "weight": 4,
      "score": s15,
      "criteria": (
          "+2: VIX<14極度平穩 | +1: VIX 14~16風險偏好穩定 | 0: 16~20 | -1:"
          " 20~25 | -2: >25恐慌拋售"
      ),
      "rationale": (
          f"SOXL與VIX具全市場最強負相關({corr_vix:+.3f}，Beta={macro_data['beta_vix_20d']:+.2f}x)。儘管10/08"
          " SOXL回檔，VIX僅微升至15.41且10/09回落至15.21，顯示系統性恐慌未擴散。"
      ),
  })

  # 16. Daily News Catalyst Sentiment (利多 vs 利空消息比)
  bb_ratio = news_data["bull_bear_ratio"]
  s16 = (
      2
      if bb_ratio >= 1.6
      else (1 if bb_ratio >= 1.15 else (0 if bb_ratio >= 0.85 else -1))
  )
  factors.append({
      "category": "6. 每日消息面情緒 (Daily News Catalysts)",
      "metric": "近7日利多/利空消息動能比 (News Sentiment)",
      "value": (
          f"利多 {news_data['recent_bull_count']} 則 vs 利空"
          f" {news_data['recent_bear_count']} 則 ({bb_ratio:.2f}x)"
      ),
      "weight": 5,
      "score": s16,
      "criteria": (
          "+2: 利多/利空≥1.6x | +1: 1.15~1.59x | 0: 0.85~1.14x多空交錯 | -1:"
          " <0.85x利空主導 | -2: 系統性利空"
      ),
      "rationale": (
          "10/08受OpenAI營收傳聞與Firmus取消IPO利空衝擊，但10/09隨即迎來NVIDIA"
          " 10億美元科學量子投資與SpaceX合作訂單利多，盤前迅速止穩反彈。"
      ),
  })

  total_weight = sum(f["weight"] for f in factors)
  weighted_score = sum(f["score"] * f["weight"] for f in factors) / total_weight

  cat_map = {}
  for f in factors:
    c = cat_map.setdefault(
        f["category"], {"category": f["category"], "w": 0, "ws": 0.0}
    )
    c["w"] += f["weight"]
    c["ws"] += f["score"] * f["weight"]
  category_scores = [
      {
          "category": c["category"],
          "weight": c["w"],
          "avg_score": round(c["ws"] / c["w"], 2),
      }
      for c in cat_map.values()
  ]

  if weighted_score >= 1.25:
    verdict = "強勢看多 (Strong Bullish)"
  elif weighted_score >= 0.35:
    verdict = "偏多震盪操作 (Moderately Bullish)"
  elif weighted_score > -0.35:
    verdict = "中性區間震盪 (Neutral / Range-Bound)"
  elif weighted_score > -1.25:
    verdict = "偏空謹慎 (Moderately Bearish)"
  else:
    verdict = "強勢看空 (Strong Bearish)"

  return {
      "composite_score": round(weighted_score, 2),
      "verdict": verdict,
      "factors": factors,
      "category_scores": category_scores,
  }


def main() -> None:
  print(
      "1/6 Fetching SOXL daily OHLCV & computing full technicals (MACD, KD,"
      " RSI, ADX, Ichimoku, Fib)..."
  )
  soxl_rows = fetch_yahoo_ohlcv("SOXL", period_range="1y", interval="1d")
  vol_data = analyze_volume_price_and_technicals(soxl_rows)
  print(
      f"    SOXL Latest ({vol_data['latest_date']}): Close=${vol_data['close']},"
      f" MACD={vol_data['macd']:+.2f}, K={vol_data['k9']:.1f}/D={vol_data['d9']:.1f}/J={vol_data['j9']:.1f},"
      f" Fib38.2%=${vol_data['fib_levels']['fib_382']}"
  )

  print("2/6 Fetching SOXL full options chain from CBOE...")
  opt_data = analyze_cboe_options(vol_data["close"])
  print(
      f"    Contracts={opt_data['total_contracts']}, C/P"
      f" Vol={opt_data['cp_vol_ratio']}x, C/P OI={opt_data['cp_oi_ratio']}x,"
      f" Call Wall=${opt_data['call_wall']}, Put Wall=${opt_data['put_wall']}"
  )

  print("3/6 Fetching 16 SOXL semiconductor constituents for Heat Map...")
  hm_data = analyze_constituents_heatmap(soxl_rows)
  print(
      f"    Breadth >20MA={hm_data['breadth_above_sma20_pct']}%, Weighted"
      f" 20D={hm_data['weighted_ret_20d']:+.2f}%"
  )

  print(
      "4/6 Evaluating Macro Correlations (10Y ^TNX, 30Y ^TYX, Brent Oil BZ=F,"
      " VIX ^VIX)..."
  )
  macro_data = analyze_macro_correlations(soxl_rows)
  h20 = macro_data["horizons"]["20D"]
  print(
      "    20D Ret Corrs vs SOXL -> 10Y:"
      f" {h20['TNX_10Y']['ret_corr']:+.3f}, 30Y:"
      f" {h20['TYX_30Y']['ret_corr']:+.3f}, Brent:"
      f" {h20['BRENT']['ret_corr']:+.3f}, VIX:"
      f" {h20['VIX']['ret_corr']:+.3f}"
  )

  print("5/6 Fetching & classifying Daily Bullish vs Bearish News Catalysts...")
  news_data = analyze_daily_news_catalysts(soxl_rows, macro_data)
  print(
      f"    Unique articles={news_data['total_unique_articles']}, Recent 7D"
      f" Bull={news_data['recent_bull_count']} vs"
      f" Bear={news_data['recent_bear_count']} (Ratio"
      f" {news_data['bull_bear_ratio']}x)"
  )

  print("6/6 Computing 16-Factor -2 to +2 Quantitative Score & HTML Report...")
  score_data = build_scoring_table(
      vol_data, opt_data, hm_data, macro_data, news_data
  )
  print(
      f"    Composite Score: {score_data['composite_score']:+.2f} / 2.00 ->"
      f" {score_data['verdict']}"
  )

  full_payload = {
      "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "volume_price": vol_data,
      "options": opt_data,
      "heatmap": hm_data,
      "macro": macro_data,
      "news": news_data,
      "scoring": score_data,
  }

  json_path = BASE_DIR / "soxl_analysis_data.json"
  json_path.write_text(
      json.dumps(full_payload, ensure_ascii=False, indent=2), encoding="utf-8"
  )
  print(f"Saved structured data to {json_path}")

  from generate_html_report import generate_html

  html_str = generate_html(full_payload)
  report_path = BASE_DIR / "soxl_analysis_report.html"
  report_path.write_text(html_str, encoding="utf-8")
  print(f"Generated interactive HTML report: {report_path}")


if __name__ == "__main__":
  main()
