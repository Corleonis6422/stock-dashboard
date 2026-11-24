#!/usr/bin/env python3
"""Data for the combined stress chart: SOXL price, VIX spikes, volume and the crash index on one date axis.

The pipeline stores one block, ``payload["stress_chart"]``.  It carries a daily series, weekly
bars built from it, two views (daily ≈ 6 months, weekly ≈ 2 years) with their spike episodes,
crash-drop markers, trend channel and volume profile, the rules as data and as legend text, the
spike statistics, and the figures of the evidence strip.  ``docs/stress_chart_data.md`` names every
key and defines every rule and figure.

Fixed rules (no run-time fitting; every parameter is a constant below)
  VIX spike       a VIX session is marked when its close >= SPIKE_MULTIPLE x the median close of the
                  SPIKE_LOOKBACK sessions before it.  The mark of a session uses data up to that
                  session only, so appending later data never changes an earlier mark.  Runs of marked
                  sessions separated by at most SPIKE_MAX_GAP unmarked sessions form one episode.
  Trend channel   least-squares line through ln(close) of the bars in view, shifted by
                  +/- CHANNEL_SIGMAS x the root mean square of the residuals; no channel when R^2 is
                  under CHANNEL_MIN_R2 or the view has fewer than CHANNEL_MIN_BARS bars.
  Weekly bars     one bar per ISO week (Monday to Sunday) of the daily series.
  Volume profile  PROFILE_BINS price bands between the lowest low and the highest high of the bars in
                  view; a bar's whole volume goes to the band of (high + low + close) / 3.  The daily
                  view uses bands of equal width, the method of ``technicals.volume_profile`` that also
                  gives the model's POC level, over the same DAILY_VIEW_SESSIONS sessions (the view
                  rounds prices to 2 decimals and a reduced block has only 120 bars, so the two can
                  still differ); the weekly view uses bands of equal ratio, because its price range is
                  too wide for equal widths to resolve.

Nothing in this module feeds a rating, a score, a level or the trade plan.  It only describes.
The module does no file or network I/O.
"""

from __future__ import annotations

import bisect
import copy
from datetime import date, timedelta
from fractions import Fraction
import json
import math
import statistics

from . import indicators as ind
from . import marketclock

SCHEMA = "soxl-stress-chart/1"

# ---- VIX spike rule
SPIKE_LOOKBACK = 60        # sessions before the session; kept <= 100 so 260 stored VIX rows reproduce the marks of the latest 120 sessions
SPIKE_MULTIPLE = 1.4       # close >= multiple x median of the lookback closes
SPIKE_MAX_GAP = 5          # runs separated by at most this many unmarked sessions are one episode
SPIKE_CAP_PCT = 10.0       # the rule must mark at most this share of the loaded VIX history
# ---- trend channel
CHANNEL_SIGMAS = 2.0
CHANNEL_MIN_R2 = 0.5
CHANNEL_MIN_BARS = 30
# ---- volume profile
PROFILE_BINS = 24
PROFILE_SPACING = {"daily": "equal_width", "weekly": "equal_ratio"}  # daily = the method of technicals.volume_profile
# ---- the rules each view's legend prints, in order
VIEW_RULES = {"daily": ["vix_spike", "trend_channel", "volume_profile_daily"],
              "weekly": ["weekly_bars", "vix_spike", "trend_channel", "volume_profile_weekly"]}
# ---- series and views
DAILY_STORE_SESSIONS = 650  # stored daily sessions before trimming the head to the first session of a week (>= 640 remain)
DAILY_VIEW_SESSIONS = 126   # the window of the model's POC level (technicals.volume_profile); a reduced block has the 120 bars every payload stores
WEEKLY_VIEW_WEEKS = 104
WEEKLY_VIEW_MIN_WEEKS = 30  # fewer weekly bars than this: no weekly view
DAILY_VOLUME_AVG = 20       # sessions
WEEKLY_VOLUME_AVG = 20      # weekly bars, the current one included
# ---- evidence strip
EVIDENCE_HORIZONS = (5, 10, 20)
EVIDENCE_DEFAULT_HORIZON = 10
EVIDENCE_SMALL_N = 20
CRASH_ALERT = 80.0

DAILY_COLUMNS = ["date", "open", "high", "low", "close", "volume", "vol_avg20", "vix", "crash", "spike"]
VIX_COLUMNS = ["date", "close", "spike"]
WEEKLY_COLUMNS = ["start", "end", "open", "high", "low", "close", "volume", "vol_avg20w", "vix", "crash", "spike", "sessions", "partial"]
PROFILE_COLUMNS = ["price_low", "price_high", "total_volume", "up_volume", "down_volume"]
CRASH_COLUMNS = ["date", "score"]

_SCALE = 10_000  # closes are compared as integers in 1/10000 so that a tie is decided exactly

TEXT_NO_SPIKE = "視窗內沒有 VIX 急升"
TEXT_NO_VIX = "缺少 VIX 歷史資料（來源 CBOE），無法畫 VIX 線，也無法標記 VIX 急升"
TEXT_VIX_TOO_SHORT = f"VIX 歷史不足 {SPIKE_LOOKBACK} 個交易日，無法判定 VIX 急升"
TEXT_NO_CRASH = "缺少崩跌指數歷史，無法畫崩跌指數"
TEXT_NO_BARS = "缺少 SOXL 日線資料，無法畫組合圖"
TEXT_NO_EVIDENCE = "這份資料沒有長期歷史，無法統計 VIX 急升或崩跌指數升到 80 以上之後的表現"
TEXT_NO_CHANNEL = f"未畫趨勢通道（視窗內 R² 低於 {CHANNEL_MIN_R2:g} 或少於 {CHANNEL_MIN_BARS} 根）"


def text_no_weekly(sessions: int) -> str:
  """The one line shown in place of the weekly view when the payload has no long daily history."""
  return f"這份資料只有 {sessions} 個交易日的日線，湊不出兩年的週線，所以沒有週線檢視"


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _num(v) -> float | None:
  """A finite float, or None."""
  if isinstance(v, bool) or v is None:
    return None
  try:
    f = float(v)
  except (TypeError, ValueError):
    return None
  return f if math.isfinite(f) else None


def _r(v, nd: int):
  return None if v is None else round(v, nd)


def week_key(d: str) -> tuple[int, int]:
  """ISO (year, week) of an ISO date string; ISO weeks run Monday to Sunday."""
  iso = date.fromisoformat(d).isocalendar()
  return (iso[0], iso[1])


def table(columns: list[str], dict_rows: list[dict]) -> dict:
  """Pack row dicts into the columnar table form of the block.

  ``{"columns": [names], "n": row count, name: [n values], ...}``: one array per column, all of
  length ``n``; row i is the i-th element of every array.  (One array per column keeps the block
  small in the indented data file.)
  """
  out: dict = {"columns": list(columns), "n": len(dict_rows)}
  for c in columns:
    out[c] = [r.get(c) for r in dict_rows]
  return out


def table_dicts(tbl: dict | None) -> list[dict]:
  """Unpack a columnar table of the block into a list of row dicts, oldest first."""
  if not tbl:
    return []
  cols = tbl.get("columns") or []
  return [dict(zip(cols, vals)) for vals in zip(*(tbl.get(c) or [] for c in cols))] if cols else []


# --------------------------------------------------------------------------- #
# rule 1: VIX spike
# --------------------------------------------------------------------------- #
def spike_marks(closes: list[float], lookback: int = SPIKE_LOOKBACK, multiple: float = SPIKE_MULTIPLE) -> list[bool | None]:
  """Mark of every session of a VIX close series (oldest first).

  ``mark[t]`` is True when ``close[t] >= multiple x median(close[t-lookback .. t-1])`` and False
  otherwise.  It is None for the first ``lookback`` sessions, which have too few sessions before
  them to be judged.  The value at ``t`` reads ``close[t-lookback .. t]`` only: no later data, and
  nothing earlier than the lookback, so a series cut anywhere gives the same mark for every session
  that still has ``lookback`` sessions before it.  The comparison is exact (integers in 1/10000 and
  a rational multiple), so a close that equals the threshold counts as a spike on every machine.
  """
  m = Fraction(str(multiple))
  q = [round(float(c) * _SCALE) for c in closes]
  out: list[bool | None] = [None] * len(q)
  half = lookback // 2
  for t in range(lookback, len(q)):
    w = sorted(q[t - lookback:t])
    med2 = (w[half - 1] + w[half]) if lookback % 2 == 0 else 2 * w[half]  # twice the median
    out[t] = 2 * q[t] * m.denominator >= m.numerator * med2
  return out


def spike_episodes(marks: list[bool | None], max_gap: int = SPIKE_MAX_GAP) -> list[tuple[int, int]]:
  """Episodes as (first marked index, last marked index).

  A run of marked sessions is an episode; two runs with at most ``max_gap`` unmarked sessions
  between them are one episode.  A session that is not judged (None) counts as unmarked.
  """
  eps: list[tuple[int, int]] = []
  last = None
  for t, f in enumerate(marks):
    if f is True:
      if last is not None and t - last - 1 <= max_gap:
        eps[-1] = (eps[-1][0], t)
      else:
        eps.append((t, t))
      last = t
  return eps


def clean_vix(vix_rows: list[dict] | None) -> list[dict]:
  """VIX rows as [{"date", "close"}], oldest first: rows without a date or a close are dropped, a repeated date keeps its last row."""
  by: dict[str, float] = {}
  for r in vix_rows or []:
    if not isinstance(r, dict):
      continue
    d = r.get("date")
    c = _num(r.get("close", r.get("vix")))
    if isinstance(d, str) and len(d) == 10 and c is not None and c > 0:
      by[d] = c
  return [{"date": d, "close": by[d]} for d in sorted(by)]


def spike_statistics(vix: list[dict], scope: str = "loaded_vix_history") -> dict:
  """Share of sessions the rule marks over a cleaned VIX series, its date range and its episode count."""
  closes = [r["close"] for r in vix]
  marks = spike_marks(closes)
  n = len(closes)
  marked = sum(1 for f in marks if f is True)
  evaluated = sum(1 for f in marks if f is not None)
  share = marked / n * 100.0 if n else None
  whole = scope == "loaded_vix_history"
  return {
      "scope": scope, "first_date": vix[0]["date"] if vix else None, "last_date": vix[-1]["date"] if vix else None,
      "sessions": n, "evaluated": evaluated, "marked": marked,
      "share_pct": _r(share, 2), "share_of_evaluated_pct": _r(marked / evaluated * 100.0, 2) if evaluated else None,
      "episodes": len(spike_episodes(marks)),
      "cap_pct": SPIKE_CAP_PCT, "within_cap": (share <= SPIKE_CAP_PCT) if (whole and share is not None) else None,
  }


# --------------------------------------------------------------------------- #
# rule 2: trend channel
# --------------------------------------------------------------------------- #
def trend_channel(closes: list[float]) -> dict:
  """Log-linear regression channel over the closes of the bars in view (oldest first).

  x is the bar position 0 .. n-1, y = ln(close).  The middle line is the least-squares line
  y = a + b x.  sigma is the root mean square of the residuals (divide by n).  The upper and lower
  lines are the middle line shifted by +/- CHANNEL_SIGMAS x sigma.  A line is straight in ln(price);
  its price at bar i is exp(a + b i +/- CHANNEL_SIGMAS x sigma).  No channel when n is under
  CHANNEL_MIN_BARS, when a close is missing or not positive, or when R^2 is under CHANNEL_MIN_R2.
  """
  n = len(closes)
  if n < CHANNEL_MIN_BARS:
    return {"available": False, "reason": "too_few_bars", "bars": n, "text_zh": f"未畫趨勢通道：視窗內只有 {n} 根，少於 {CHANNEL_MIN_BARS} 根"}
  if any(_num(c) is None or c <= 0 for c in closes):
    return {"available": False, "reason": "bad_prices", "bars": n, "text_zh": "未畫趨勢通道：視窗內有缺漏的收盤價"}
  ys = [math.log(c) for c in closes]
  mx = (n - 1) / 2.0
  my = math.fsum(ys) / n
  sxx = math.fsum((i - mx) ** 2 for i in range(n))
  sxy = math.fsum((i - mx) * (y - my) for i, y in enumerate(ys))
  b = sxy / sxx
  a = my - b * mx
  sse = math.fsum((y - (a + b * i)) ** 2 for i, y in enumerate(ys))
  sst = math.fsum((y - my) ** 2 for y in ys)
  r2 = 1.0 - sse / sst if sst > 0 else 0.0
  if r2 < CHANNEL_MIN_R2:
    return {"available": False, "reason": "low_r2", "bars": n, "r2": round(r2, 4),
            "text_zh": f"未畫趨勢通道：視窗內 R² {r2:.2f}，低於 {CHANNEL_MIN_R2:g}"}
  sigma = math.sqrt(sse / n)
  k = CHANNEL_SIGMAS

  def ends(shift: float) -> list[float]:
    return [round(math.exp(a + shift), 4), round(math.exp(a + b * (n - 1) + shift), 4)]

  slope_pct = (math.exp(b) - 1.0) * 100.0
  return {
      "available": True, "bars": n, "direction": "up" if b > 0 else "down",
      "upper": ends(k * sigma), "mid": ends(0.0), "lower": ends(-k * sigma),
      "intercept_log": round(a, 8), "slope_log_per_bar": round(b, 8), "sigma_log": round(sigma, 8), "band_sigmas": k,
      "slope_pct_per_bar": round(slope_pct, 3), "r2": round(r2, 4),
      "text_zh": f"{'上升' if b > 0 else '下降'}通道：每根約 {slope_pct:+.2f}%，R² {r2:.2f}",
  }


# --------------------------------------------------------------------------- #
# rule 3: weekly bars
# --------------------------------------------------------------------------- #
def week_is_partial(last_session: str, final: bool = True) -> bool:
  """True when the ISO week of ``last_session`` is not over yet.

  That is the case when the session itself is still in progress (``final`` is False), or when a
  NYSE trading day (``marketclock.is_trading_day``: a weekday that is not a listed full-day holiday)
  follows it inside the same ISO week.
  """
  if not final:
    return True
  d = date.fromisoformat(last_session)
  key = d.isocalendar()[:2]
  nxt = d + timedelta(days=1)
  while nxt.isocalendar()[:2] == key:
    if marketclock.is_trading_day(nxt):
      return True
    nxt += timedelta(days=1)
  return False


def weekly_bars(daily: list[dict], final: bool = True) -> list[dict]:
  """Weekly bars from daily row dicts (oldest first).  One bar per ISO week that has a session.

  open = open of the first session, high / low = extremes of the week, close = close of the last
  session, volume = sum.  vix and crash = value of the last session of the week that has one.
  spike = True when any session of the week is marked, False when at least one session was judged
  and none is marked, None when no session of the week was judged.  vol_avg20w = mean volume of the
  latest WEEKLY_VOLUME_AVG weekly bars including this one, rounded to an integer (None for the
  first 19 bars).  sessions = number of sessions.  partial = True only on the last bar, when its
  week is not over (``week_is_partial``).
  """
  bars: list[dict] = []
  keys: list[tuple[int, int]] = []
  for r in daily:
    k = week_key(r["date"])
    if keys and keys[-1] == k:
      b = bars[-1]
      b["end"] = r["date"]
      b["high"] = max(b["high"], r["high"])
      b["low"] = min(b["low"], r["low"])
      b["close"] = r["close"]
      b["volume"] += r.get("volume") or 0
      b["sessions"] += 1
    else:
      b = {"start": r["date"], "end": r["date"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"],
           "volume": r.get("volume") or 0, "vol_avg20w": None, "vix": None, "crash": None, "spike": None, "sessions": 1, "partial": False}
      bars.append(b)
      keys.append(k)
    if r.get("vix") is not None:
      b["vix"] = r["vix"]
    if r.get("crash") is not None:
      b["crash"] = r["crash"]
    if r.get("spike") is not None:
      b["spike"] = bool(b["spike"]) or bool(r["spike"])
  for i, b in enumerate(bars):
    if i + 1 >= WEEKLY_VOLUME_AVG:
      b["vol_avg20w"] = round(sum(x["volume"] for x in bars[i + 1 - WEEKLY_VOLUME_AVG:i + 1]) / WEEKLY_VOLUME_AVG)
  if bars:
    bars[-1]["partial"] = week_is_partial(bars[-1]["end"], final)
  return bars


# --------------------------------------------------------------------------- #
# rule 4: volume profile
# --------------------------------------------------------------------------- #
def volume_profile(bars: list[dict], bins: int = PROFILE_BINS, spacing: str = "equal_width") -> dict:
  """Volume by price band over the bars in view (dicts with open / high / low / close / volume).

  lo = lowest low and hi = highest high of the bars.  ``spacing`` sets the band bounds:

  * ``"equal_width"`` — the exact method of ``technicals.volume_profile``.  w = (hi - lo) / bins;
    band k (0 = lowest) runs from lo + k w to lo + (k + 1) w; a bar goes to band
    k = floor((tp - lo) / w), at most bins - 1.
  * ``"equal_ratio"`` — every band is the same percentage wide.  w = (ln hi - ln lo) / bins; band k
    runs from exp(ln lo + k w) to exp(ln lo + (k + 1) w); a bar goes to band
    k = floor((ln tp - ln lo) / w), at most bins - 1.

  In both, tp is the bar's typical price ((high + low) + close) / 3 and the bar's whole volume goes
  to the one band that holds tp; a tp that sits exactly on a bound goes to the band above it.  A bar
  counts as up volume when its close >= the previous bar's close (the first bar: >= its own open),
  else as down volume.  The busiest band has the largest total volume; when two bands hold the same
  volume the lower-priced one wins.  The runner-up is the largest of the other bands, by the same tie-break.
  Every band carries its own price bounds, so nothing here assumes a price-axis scale.
  """
  if spacing not in ("equal_width", "equal_ratio"):
    raise ValueError(f"unknown band spacing: {spacing}")
  rows = [b for b in bars if all((_num(b.get(k)) or 0) > 0 for k in ("high", "low", "close"))]
  if not rows:
    return {"available": False, "reason": "no_bars", "text_zh": "視窗內沒有 K 棒，無法計算成交量分布"}
  lo = min(b["low"] for b in rows)
  hi = max(b["high"] for b in rows)
  if not hi > lo:
    return {"available": False, "reason": "flat_range", "text_zh": "視窗內最高價與最低價相同，無法計算成交量分布"}
  ratio = spacing == "equal_ratio"
  origin = math.log(lo) if ratio else lo
  width = ((math.log(hi) if ratio else hi) - origin) / bins
  total = [0] * bins
  up = [0] * bins
  down = [0] * bins
  for i, b in enumerate(rows):
    tp = (b["high"] + b["low"] + b["close"]) / 3.0
    k = max(0, min(int(((math.log(tp) if ratio else tp) - origin) / width), bins - 1))
    vol = b.get("volume") or 0
    ref = rows[i - 1]["close"] if i else (b.get("open") if _num(b.get("open")) is not None else b["close"])
    total[k] += vol
    if b["close"] >= ref:
      up[k] += vol
    else:
      down[k] += vol
  all_vol = sum(total)
  if all_vol <= 0:
    return {"available": False, "reason": "no_volume", "text_zh": "視窗內沒有成交量資料，無法計算成交量分布"}

  def edge(k: int) -> float:
    if k == 0:
      return round(lo, 4)
    if k == bins:
      return round(hi, 4)
    return round(math.exp(origin + k * width) if ratio else origin + k * width, 4)

  def band(k: int) -> dict:
    return {"index": k, "price_low": edge(k), "price_high": edge(k + 1), "volume": total[k], "share_pct": round(total[k] / all_vol * 100.0, 1)}

  busiest = max(range(bins), key=lambda k: total[k])
  second = max((k for k in range(bins) if k != busiest), key=lambda k: total[k]) if bins > 1 else None
  bands = [{"price_low": edge(k), "price_high": edge(k + 1), "total_volume": total[k], "up_volume": up[k], "down_volume": down[k]} for k in range(bins)]
  return {
      "available": True, "spacing": spacing, "bins": bins, "range_low": round(lo, 4), "range_high": round(hi, 4),
      "band_width": None if ratio else round(width, 6), "band_ratio": round(math.exp(width), 6) if ratio else None,
      "total_volume": all_vol, "bands": table(PROFILE_COLUMNS, bands),
      "busiest": band(busiest), "runner_up": None if second is None else band(second),
      "lead_pts": None if second is None else round((total[busiest] - total[second]) / all_vol * 100.0, 1),
  }


# --------------------------------------------------------------------------- #
# evidence strip
# --------------------------------------------------------------------------- #
def _ret_stats(rets: list[float]) -> dict:
  if not rets:
    return {"n": 0, "wins": 0, "median_ret_pct": None, "gain_share_pct": None}
  wins = sum(1 for r in rets if r > 0)
  return {"n": len(rets), "wins": wins, "median_ret_pct": round(statistics.median(rets), 6), "gain_share_pct": round(wins / len(rets) * 100.0, 6)}


def forward_figure(opens: list[float], closes: list[float], dates: list[str], starts: list[bool], first: int, last: int, horizon: int) -> dict:
  """What price did after a condition, against the base rate of the same sample and horizon.

  ``starts[i]`` says whether the condition holds on session i, judged with data up to i.  Sessions
  ``first .. last`` are the sample.  Episodes are taken in date order; after an episode at i the next
  one must sit at j >= i + horizon, so holding periods never overlap.  An episode is counted when
  its exit exists (i + horizon <= final index); a later one is reported as open and not counted.
  Return of an episode at i = (close[i + horizon] / open[i + 1] - 1) x 100: buy the next session's
  open, sell the close ``horizon`` sessions after the signal (the convention of ``backtest.py``).
  The base rate is the same return for every session i of the sample whose exit exists.
  """
  n = len(closes)
  taken: list[int] = []
  skipped = 0
  open_eps: list[int] = []
  prev = None
  for i in range(max(first, 0), min(last, n - 1) + 1):
    if not starts[i]:
      continue
    if prev is not None and i - prev < horizon:
      skipped += 1
      continue
    prev = i
    if i + horizon > n - 1:
      open_eps.append(i)
    else:
      taken.append(i)

  def ret(i: int) -> float:
    return (closes[i + horizon] / opens[i + 1] - 1.0) * 100.0

  base_idx = list(range(max(first, 0), min(last, n - 1 - horizon) + 1))
  st = _ret_stats([ret(i) for i in taken])
  return {
      "horizon": horizon, **st, "small_sample": st["n"] < EVIDENCE_SMALL_N,
      "base": _ret_stats([ret(i) for i in base_idx]),
      "period": {"start": dates[base_idx[0]], "end": dates[base_idx[-1]]} if base_idx else None,
      "episode_dates": [dates[i] for i in taken], "skipped_overlap": skipped, "open_dates": [dates[i] for i in open_eps],
  }


def crash_rise_starts(scores: list[float | None], level: float = CRASH_ALERT) -> list[bool]:
  """True on session i when the crash index is >= level and the session before it had a value below level."""
  out = [False] * len(scores)
  for i in range(1, len(scores)):
    out[i] = scores[i] is not None and scores[i - 1] is not None and scores[i] >= level > scores[i - 1]
  return out


def merge_history(older: list[dict] | None, recent: list[dict] | None) -> list[dict]:
  """The recent rows, with the rows of ``older`` that precede them put in front."""
  recent = list(recent or [])
  if not older:
    return recent
  if not recent:
    return list(older)
  first = recent[0]["date"]
  return [r for r in older if r["date"] < first] + recent


def evidence(price_rows: list[dict], vix: list[dict], crash_series: list[dict] | None, event_study: dict | None, daily_first: str | None = None) -> dict:
  """Figures of the evidence strip: SOXL after a VIX spike episode starts, and after the crash index rises to 80 or more.

  ``price_rows``: SOXL daily history (raw prices), oldest first.  ``vix``: cleaned VIX rows.
  ``crash_series``: [{"date", "score"}] for every scored session.  ``daily_first``: first date of the
  stored daily table; the scores before it are returned in ``crash_before_daily`` so that the whole
  crash sample can be rebuilt from the block.
  """
  rows = [r for r in price_rows or [] if (_num(r.get("open")) or 0) > 0 and (_num(r.get("close")) or 0) > 0]
  dates = [r["date"] for r in rows]
  opens = [float(r["open"]) for r in rows]
  closes = [float(r["close"]) for r in rows]
  n = len(rows)
  conditions: list[dict] = []

  def figures(starts: list[bool], first: int, last: int) -> dict:
    return {"available": True,
            "sample": {"start": dates[first], "end": dates[last], "sessions": last - first + 1},
            "start_dates": [dates[i] for i in range(first, last + 1) if starts[i]],
            "figures": [forward_figure(opens, closes, dates, starts, first, last, h) for h in EVIDENCE_HORIZONS]}

  # ---- condition 1: a VIX spike episode starts
  mark_by = {r["date"]: f for r, f in zip(vix, spike_marks([x["close"] for x in vix]))}
  flags = [mark_by.get(d) for d in dates]
  judged = [i for i, f in enumerate(flags) if f is not None]
  spike = {"key": "vix_spike_start", "label_zh": "VIX 急升開始",
           "definition_zh": f"當日是 VIX 急升，而且之前 {SPIKE_MAX_GAP + 1} 個交易日都不是（一段急升的第一天）"}
  if judged and judged[0] + SPIKE_MAX_GAP + 1 <= judged[-1]:
    ep_first = {a for a, _ in spike_episodes(flags)}
    spike.update(figures([i in ep_first for i in range(n)], judged[0] + SPIKE_MAX_GAP + 1, judged[-1]))
  else:
    spike.update({"available": False, "reason": "no_vix", "text_zh": "缺少 VIX 歷史資料（來源 CBOE），無法統計 VIX 急升之後的表現"})
  conditions.append(spike)

  # ---- condition 2: the crash index rises to 80 or more
  crash_rows = [{"date": x["date"], "score": _num(x.get("score"))} for x in crash_series or [] if isinstance(x, dict) and x.get("date") and _num(x.get("score")) is not None]
  score_by = {x["date"]: x["score"] for x in crash_rows}
  scores = [score_by.get(d) for d in dates]
  scored = [i for i, s in enumerate(scores) if s is not None]
  crash = {"key": "crash_ge80", "label_zh": f"崩跌指數升到 {CRASH_ALERT:g} 以上",
           "definition_zh": f"當日崩跌指數 ≥ {CRASH_ALERT:g}，而且前一個交易日低於 {CRASH_ALERT:g}",
           "note_zh": "崩跌指數是拿整段樣本排出來的百分位（最近 60 個交易日不列入排序基準），過去的分數不是當時就算得出來的"}
  if len(scored) >= 2:
    crash.update(figures(crash_rise_starts(scores), scored[0] + 1, scored[-1]))
  else:
    crash.update({"available": False, "reason": "no_crash_index", "text_zh": "缺少崩跌指數歷史，無法統計分數升到 80 以上之後的表現"})
  conditions.append(crash)

  out = {
      "available": any(c.get("available") for c in conditions),
      "horizons": list(EVIDENCE_HORIZONS), "default_horizon": EVIDENCE_DEFAULT_HORIZON, "small_sample_below": EVIDENCE_SMALL_N,
      "price_history": {"symbol": "SOXL", "start": dates[0] if dates else None, "end": dates[-1] if dates else None, "sessions": n},
      "convention": {
          "signal": "the condition is judged on session i with data up to and including session i",
          "entry": "open of session i+1", "exit": "close of session i+h", "return_pct": "(close[i+h] / open[i+1] - 1) * 100", "gain": "return_pct > 0",
          "no_overlap": "after a counted or open episode at i the next episode must be at j >= i + h",
          "base": "the same return for every session i of the sample with i + h <= last index",
          "text_zh": "條件成立後的下一個交易日開盤買進，成立後第 h 個交易日收盤賣出；前一次事件的持有期間還沒結束時，不另計新事件；基準是同一段樣本裡每個交易日都照這個方式買賣的結果",
      },
      "conditions": conditions,
      "crash_before_daily": table(CRASH_COLUMNS, [x for x in crash_rows if daily_first is None or x["date"] < daily_first]),
  }
  if not out["available"]:
    out["text_zh"] = TEXT_NO_EVIDENCE
  es = event_study or {}
  if es.get("stats_all_80") or es.get("stats_top_80"):
    out["event_study"] = {
        "source": "early_warning.event_study, copied unchanged", "unit": "sessions (windows overlap; not an episode count)",
        # deep copies: a later edit of this block must not reach the figures of early_warning
        **{k: copy.deepcopy(es.get(k)) for k in ("threshold", "drop_pct", "horizon_days", "n_days", "n_event_days", "n_episodes", "alert_episodes",
                                                 "alert_episodes_followed_by_crash", "alert_hit_rate_pct", "stats_all_80", "stats_top_80")},
        "score_period": {"start": crash_rows[0]["date"], "end": crash_rows[-1]["date"]} if crash_rows else None,
    }
  return out


# --------------------------------------------------------------------------- #
# rules and legend text
# --------------------------------------------------------------------------- #
def rules() -> dict:
  """The rules as parameters and as the one legend line each (Traditional Chinese).

  The volume profile has one rule per view (``PROFILE_SPACING``); ``views.<view>.rules`` lists the
  rules that a view's legend prints.
  """
  assign_zh = "每根的成交量全數算進（最高＋最低＋收盤）÷3 所在的價帶；合計最多的是最大量價帶，同量時取價位較低的那一帶"
  busiest = "largest total volume; when two bands hold the same volume, the lower-priced band"
  return {
      "vix_spike": {
          "params": {"series": "VIX close on VIX's own sessions", "lookback_sessions": SPIKE_LOOKBACK, "statistic": "median", "multiple": SPIKE_MULTIPLE, "comparison": ">=",
                     "not_judged": f"a session with fewer than {SPIKE_LOOKBACK} sessions before it", "join_max_gap_sessions": SPIKE_MAX_GAP, "cap_share_pct": SPIKE_CAP_PCT},
          "text_zh": (f"VIX 急升：VIX 收盤 ≥ 之前 {SPIKE_LOOKBACK} 個交易日收盤中位數的 {SPIKE_MULTIPLE:g} 倍（只用到當日為止的資料）；"
                      f"兩次標記之間沒被標記的交易日不超過 {SPIKE_MAX_GAP} 個時，算同一段"),
      },
      "trend_channel": {
          "params": {"input": "close of the bars in view", "x": "bar position 0..n-1", "y": "ln(close)", "fit": "least squares", "band_sigmas": CHANNEL_SIGMAS,
                     "sigma": "root mean square of the residuals (divide by n)", "min_r2": CHANNEL_MIN_R2, "min_bars": CHANNEL_MIN_BARS},
          "text_zh": (f"趨勢通道：視窗內各根收盤價取自然對數，對根序做最小平方直線，再上下各平移 {CHANNEL_SIGMAS:g} 倍殘差均方根；"
                      f"R² 低於 {CHANNEL_MIN_R2:g} 或少於 {CHANNEL_MIN_BARS} 根時不畫"),
      },
      "weekly_bars": {
          "params": {"week": "ISO week, Monday to Sunday", "open": "first session open", "high": "max high", "low": "min low", "close": "last session close", "volume": "sum",
                     "vol_avg_weeks": WEEKLY_VOLUME_AVG, "vol_avg_includes_current_week": True, "vix": "last session of the week with a value", "crash": "last session of the week with a value",
                     "spike": "any session of the week marked", "partial": "last bar only: its session is not final, or a NYSE trading day remains in its ISO week"},
          "text_zh": (f"週線：同一個 ISO 週（週一至週日）的交易日合成一根；開＝首日開盤、高低＝週內最高與最低、收＝末日收盤、量＝各日合計、均量＝連同當週的最近 {WEEKLY_VOLUME_AVG} 週平均；"
                      "VIX 與崩跌指數取週內最後一個有值的交易日；週內任一日是 VIX 急升，該週就標記"),
      },
      "volume_profile_daily": {
          "params": {"view": "daily", "input": "bars in view", "bins": PROFILE_BINS, "spacing": PROFILE_SPACING["daily"], "method": "technicals.volume_profile",
                     "band_bounds": "lo + k*w to lo + (k+1)*w, w = (hi - lo) / bins, lo = lowest low, hi = highest high",
                     "assign": "whole bar volume to band k = floor((tp - lo) / w), at most bins - 1, tp = ((high + low) + close) / 3", "busiest": busiest},
          "text_zh": f"成交量分布：視窗內最低價到最高價等分成 {PROFILE_BINS} 個價帶（每一帶的價差相同）；{assign_zh}",
      },
      "volume_profile_weekly": {
          "params": {"view": "weekly", "input": "bars in view", "bins": PROFILE_BINS, "spacing": PROFILE_SPACING["weekly"],
                     "band_bounds": "exp(ln lo + k*w) to exp(ln lo + (k+1)*w), w = (ln hi - ln lo) / bins, lo = lowest low, hi = highest high",
                     "assign": "whole bar volume to band k = floor((ln tp - ln lo) / w), at most bins - 1, tp = ((high + low) + close) / 3", "busiest": busiest},
          "text_zh": f"成交量分布：視窗內最低價到最高價切成 {PROFILE_BINS} 個等比價帶（相鄰邊界的比值相同）；{assign_zh}",
      },
  }


def legend(event_study: dict | None = None) -> dict:
  """Legend lines that are not rules: labels, the lines for a missing element, the crash-drop marker."""
  es = event_study or {}
  drop, hz = _num(es.get("drop_pct")), es.get("horizon_days")
  out = {
      "spike_label_zh": "VIX 急升",
      "no_spike_in_view_zh": TEXT_NO_SPIKE,
      "no_channel_zh": TEXT_NO_CHANNEL,
      "no_vix_zh": TEXT_NO_VIX,
      "no_crash_zh": TEXT_NO_CRASH,
      "crash_lines": [{"value": 60, "label_zh": "注意"}, {"value": 80, "label_zh": "警戒"}],
      "crash_drop_zh": None,
  }
  if drop is not None and hz:
    out["crash_drop_zh"] = f"崩跌起點：其後 {int(hz)} 個交易日內的最低收盤，比當日收盤低 {abs(drop):g}% 以上"
  return out


# --------------------------------------------------------------------------- #
# views
# --------------------------------------------------------------------------- #
def _view_episodes(sessions: list[dict], bar_of: list[int]) -> list[dict]:
  """Spike episodes among the sessions of a view; ``bar_of[i]`` is the view position of the bar that holds session i."""
  out = []
  for a, b in spike_episodes([s.get("spike") for s in sessions]):
    marked = [i for i in range(a, b + 1) if sessions[i].get("spike") is True]
    peak = max(marked, key=lambda i: (sessions[i]["vix"], -i))
    out.append({"start": sessions[a]["date"], "end": sessions[b]["date"], "marked_sessions": len(marked), "span_sessions": b - a + 1,
                "peak_vix": sessions[peak]["vix"], "peak_date": sessions[peak]["date"],
                "first_bar": bar_of[a], "last_bar": bar_of[b], "anchor_bar": bar_of[peak]})
  return out


def _view(kind: str, bars: list[dict], first: int, sessions: list[dict], bar_of: list[int], drops: list[dict], date_to_bar: dict[str, int]) -> dict:
  """One view: its bar range, spike episodes, crash-drop markers, trend channel and volume profile."""
  n = len(bars)
  start = bars[0]["start" if kind == "weekly" else "date"]
  end = bars[-1]["end" if kind == "weekly" else "date"]
  has_vix = any(s.get("vix") is not None for s in sessions)
  judged = sum(1 for s in sessions if s.get("spike") is not None)
  has_crash = any(s.get("crash") is not None for s in sessions)
  avg_key = "vol_avg20w" if kind == "weekly" else "vol_avg20"
  episodes = _view_episodes(sessions, bar_of) if judged else []
  if not has_vix:
    status, text = "no_vix", TEXT_NO_VIX
  elif not judged:
    status, text = "too_short", TEXT_VIX_TOO_SHORT
  elif not episodes:
    status, text = "none", TEXT_NO_SPIKE
  else:
    status, text = "ok", None
  markers = []
  for e in drops:
    pos = date_to_bar.get(e.get("date"))
    if pos is not None:
      markers.append({"date": e["date"], "bar": pos, "close": e.get("close"), "fwd_min_pct": e.get("fwd_min_pct"), "top_type": e.get("top_type"),
                      "score_t": e.get("score_t"), "flagged": e.get("flagged")})
  missing = [t for t, absent in ((TEXT_NO_VIX, not has_vix), (TEXT_NO_CRASH, not has_crash)) if absent]
  return {
      "available": True, "kind": kind, "first": first, "last": first + n - 1, "bars": n, "start": start, "end": end,
      "rules": list(VIEW_RULES[kind]),
      "series": {"price": True, "volume": True, "volume_avg": any(b.get(avg_key) is not None for b in bars), "vix": has_vix, "crash": has_crash},
      "spikes": {"status": status, "judged_sessions": judged, "episodes": episodes, "text_zh": text},
      "crash_drops": markers,
      "channel": trend_channel([b["close"] for b in bars]),
      "profile": {"rule": f"volume_profile_{kind}", **volume_profile(bars, spacing=PROFILE_SPACING[kind])},
      "missing_zh": missing,
  }


# --------------------------------------------------------------------------- #
# the block
# --------------------------------------------------------------------------- #
def _unavailable(reason: str, text: str, source: str) -> dict:
  """A block with nothing to draw.  It has every top-level key of an available block, plus ``reason`` and ``text_zh``."""
  return {"schema": SCHEMA, "available": False, "source": source, "symbol": "SOXL", "as_of": None, "data_final": None,
          "reason": reason, "text_zh": text,
          "daily": table(DAILY_COLUMNS, []), "vix": table(VIX_COLUMNS, []), "weekly": table(WEEKLY_COLUMNS, []),
          "views": {"daily": {"available": False, "kind": "daily", "reason": reason, "text_zh": text},
                    "weekly": {"available": False, "kind": "weekly", "reason": reason, "text_zh": text}},
          "rules": rules(), "legend": legend(), "latest": None, "spike_stats": None,
          "evidence": {"available": False, "reason": reason, "text_zh": TEXT_NO_EVIDENCE}}


def assemble(daily: list[dict], vix_rows: list[dict] | None, drop_episodes: list[dict] | None, event_study: dict | None = None,
             final: bool = True, with_weekly: bool = True, source: str = "pipeline") -> dict:
  """Build the block from a daily series, a VIX series and the crash-drop episodes.

  ``daily``: row dicts, oldest first, with date / open / high / low / close / volume / vol_avg20 / crash.
  ``vix_rows``: VIX rows on VIX's own sessions ({"date", "close"}), oldest first.  The spike marks
  are computed on exactly these rows, so the stored flags are what the rule gives on the stored series.
  ``drop_episodes``: ``early_warning.event_study.episodes``, used as they are.
  The caller adds ``spike_stats`` and ``evidence``.
  """
  days = []
  for r in daily or []:
    o, h, lo, c = (_num(r.get(k)) for k in ("open", "high", "low", "close"))
    if not isinstance(r.get("date"), str) or None in (o, h, lo, c) or min(o, h, lo, c) <= 0:
      continue
    vol = _num(r.get("volume"))
    avg = _num(r.get("vol_avg20"))
    days.append({"date": r["date"], "open": o, "high": h, "low": lo, "close": c, "volume": int(vol) if vol is not None else 0,
                 "vol_avg20": None if avg is None else int(round(avg)), "vix": None, "crash": _num(r.get("crash")), "spike": None})
  if not days:
    return _unavailable("no_bars", TEXT_NO_BARS, source)
  vix = clean_vix(vix_rows)
  marks = spike_marks([r["close"] for r in vix])
  vix_tbl = [{"date": r["date"], "close": r["close"], "spike": f} for r, f in zip(vix, marks)]
  by_date = {r["date"]: r for r in vix_tbl}
  for d in days:
    v = by_date.get(d["date"])
    if v:
      d["vix"], d["spike"] = v["close"], v["spike"]
  drops = [e for e in (drop_episodes or []) if isinstance(e, dict) and e.get("date")]

  # ---- daily view: the latest DAILY_VIEW_SESSIONS sessions
  d_first = max(0, len(days) - DAILY_VIEW_SESSIONS)
  d_bars = days[d_first:]
  views = {"daily": _view("daily", d_bars, d_first, d_bars, list(range(len(d_bars))), drops, {b["date"]: i for i, b in enumerate(d_bars)})}

  # ---- weekly view: the latest WEEKLY_VIEW_WEEKS weekly bars
  weeks = weekly_bars(days, final) if with_weekly else []
  if len(weeks) >= WEEKLY_VIEW_MIN_WEEKS:
    w_first = max(0, len(weeks) - WEEKLY_VIEW_WEEKS)
    w_bars = weeks[w_first:]
    w_sessions = [d for d in days if d["date"] >= w_bars[0]["start"]]
    pos_of_week = {week_key(b["start"]): i for i, b in enumerate(w_bars)}
    bar_of = [pos_of_week[week_key(s["date"])] for s in w_sessions]
    wv = _view("weekly", w_bars, w_first, w_sessions, bar_of, drops, {s["date"]: bar_of[i] for i, s in enumerate(w_sessions)})
    lastb = w_bars[-1]
    wv["last_bar_partial"] = bool(lastb["partial"])
    wv["last_bar_sessions"] = lastb["sessions"]
    wv["last_bar_text_zh"] = (f"最後一根週線還沒走完（{lastb['start']} 起，目前 {lastb['sessions']} 個交易日）" if lastb["partial"]
                              else f"最後一根週線是完整的一週（{lastb['start']} 至 {lastb['end']}，{lastb['sessions']} 個交易日）")
    views["weekly"] = wv
  else:
    views["weekly"] = {"available": False, "kind": "weekly", "reason": "no_long_history", "text_zh": text_no_weekly(len(days))}

  # ---- the latest session, and the latest VIX reading at or before it
  lastd = days[-1]
  vix_dates = [r["date"] for r in vix]
  j = bisect.bisect_right(vix_dates, lastd["date"]) - 1
  latest_vix = None
  if j >= 0:
    row = vix_tbl[j]
    med = statistics.median(x["close"] for x in vix[j - SPIKE_LOOKBACK:j]) if j >= SPIKE_LOOKBACK else None
    latest_vix = {"date": row["date"], "close": row["close"], "same_session": row["date"] == lastd["date"], "spike": row["spike"],
                  "median_prev": _r(med, 3), "lookback_sessions": SPIKE_LOOKBACK,
                  "multiple": _r(row["close"] / med, 2) if med else None, "threshold": _r(med * SPIKE_MULTIPLE, 2) if med else None}
  eps_all = spike_episodes([d["spike"] for d in days])
  cur_ep = None
  if eps_all and latest_vix and latest_vix["spike"]:
    a, b = eps_all[-1]
    if days[b]["date"] == latest_vix["date"]:
      cur_ep = {"start": days[a]["date"], "marked_sessions": sum(1 for i in range(a, b + 1) if days[i]["spike"] is True)}
  ratio = lastd["volume"] / lastd["vol_avg20"] if lastd["vol_avg20"] else None
  latest = {"date": lastd["date"], "close": lastd["close"], "volume": lastd["volume"], "vol_avg20": lastd["vol_avg20"],
            "volume_ratio": _r(ratio, 2), "volume_vs_avg": None if ratio is None else ("above" if ratio > 1 else "below" if ratio < 1 else "equal"),
            "crash": lastd["crash"], "session_spike": lastd["spike"], "vix": latest_vix, "spike_episode": cur_ep}

  return {
      "schema": SCHEMA, "available": True, "source": source, "symbol": "SOXL", "as_of": lastd["date"], "data_final": bool(final),
      "daily": table(DAILY_COLUMNS, days), "vix": table(VIX_COLUMNS, vix_tbl), "weekly": table(WEEKLY_COLUMNS, weeks),
      "views": views, "rules": rules(), "legend": legend(event_study), "latest": latest,
      "spike_stats": None, "evidence": None,
  }


def daily_rows(soxl: list[dict], crash_by: dict[str, float]) -> list[dict]:
  """The stored daily series from the loaded SOXL history.

  The latest DAILY_STORE_SESSIONS sessions, minus the leading sessions that do not start an ISO
  week, so the first weekly bar is whole.  Prices are rounded to 2 decimals and the 20-session
  average volume is ``indicators.sma`` on the whole history rounded to an integer, exactly as in
  ``technicals.chart_series``.
  """
  n = len(soxl)
  v20 = ind.sma([float(r["volume"]) for r in soxl], DAILY_VOLUME_AVG)
  i0 = max(0, n - DAILY_STORE_SESSIONS)
  while 0 < i0 < n and week_key(soxl[i0]["date"]) == week_key(soxl[i0 - 1]["date"]):
    i0 += 1
  out = []
  for i in range(i0, n):
    r = soxl[i]
    out.append({"date": r["date"], "open": round(r["open"], 2), "high": round(r["high"], 2), "low": round(r["low"], 2), "close": round(r["close"], 2),
                "volume": r["volume"], "vol_avg20": None if v20[i] is None else round(v20[i]), "crash": crash_by.get(r["date"])})
  return out


def build(soxl: list[dict], vix_rows: list[dict] | None, crash_series: list[dict] | None, ews: dict | None,
          soxl_long: list[dict] | None = None, final: bool = True) -> dict:
  """The full block, from the histories the pipeline has loaded.

  ``soxl``: the daily SOXL history the model runs on.  ``vix_rows``: the whole loaded VIX history.
  ``crash_series``: [{"date", "score"}] for every scored session (``early_warning.analyze_with_series``).
  ``ews``: the ``early_warning`` section; its ``chart`` wins on a shared date, so the crash index of
  the block equals ``early_warning.chart`` wherever both have a value.  ``soxl_long``: a longer SOXL
  history for the evidence strip, when one was loaded.
  """
  ews = ews or {}
  crash_by = {x["date"]: x["score"] for x in crash_series or [] if x.get("score") is not None}
  for c in ews.get("chart") or []:
    if c.get("score") is not None:
      crash_by[c["date"]] = c["score"]
  days = daily_rows(soxl, crash_by)
  vix = clean_vix(vix_rows)
  es = ews.get("event_study") or {}
  stored = vix
  if vix and days:
    j0 = bisect.bisect_left([r["date"] for r in vix], days[0]["date"])
    stored = vix[max(0, j0 - SPIKE_LOOKBACK):]
  block = assemble(days, stored, es.get("episodes"), es, final=final, with_weekly=True, source="pipeline")
  block["spike_stats"] = spike_statistics(vix)
  full_crash = [{"date": d, "score": crash_by[d]} for d in sorted(crash_by)]
  block["evidence"] = evidence(merge_history(soxl_long, soxl), vix, full_crash, es, daily_first=days[0]["date"] if days else None)
  return block


def build_reduced(payload: dict) -> dict:
  """A reduced block for a payload that has none: the daily view only.

  Bars come from ``technicals.chart_series``, VIX from ``sentiment.vix.history``, the crash index
  from ``early_warning.chart`` and the crash-drop markers from ``early_warning.event_study.episodes``.
  The weekly view and the evidence strip are marked unavailable with one line each.
  """
  payload = payload or {}
  tech = payload.get("technicals") or {}
  ews = payload.get("early_warning") or {}
  crash_by = {c.get("date"): c.get("score") for c in (ews.get("chart") or []) if isinstance(c, dict)}
  days = [{**r, "vol_avg20": r.get("vol_sma20"), "crash": crash_by.get(r.get("date"))} for r in (tech.get("chart_series") or []) if isinstance(r, dict)]
  vix_hist = ((payload.get("sentiment") or {}).get("vix") or {}).get("history") or []
  es = ews.get("event_study") or {}
  final = bool((payload.get("data_status") or {}).get("final", True))
  block = assemble(days, vix_hist, es.get("episodes"), es, final=final, with_weekly=False, source="reduced")
  if block.get("available"):
    block["spike_stats"] = spike_statistics(clean_vix(vix_hist), scope="stored_vix_rows")
    block["evidence"] = {"available": False, "reason": "no_long_history", "text_zh": TEXT_NO_EVIDENCE}
  return block


def for_payload(payload: dict | None) -> dict:
  """The chart data for any payload.  Never raises.

  A payload that carries the block returns it.  Any other payload (an older snapshot, a run whose
  chart step failed) returns the reduced block built from the series every payload stores.  A value
  that is not a dict counts as an empty payload.
  """
  payload = payload if isinstance(payload, dict) else {}
  blk = payload.get("stress_chart")
  daily = blk.get("daily") if isinstance(blk, dict) else None
  if isinstance(daily, dict) and blk.get("schema") == SCHEMA and blk.get("available") and daily.get("n"):
    return blk
  try:
    return build_reduced(payload)
  except Exception as e:  # noqa: BLE001 - a page must still build; the block says what went wrong
    out = _unavailable("error", "組合圖資料計算失敗，暫時無法顯示", "reduced")
    out["error"] = f"{type(e).__name__}: {e}"
    return out


def view_bars(block: dict, view: str) -> list[dict]:
  """The bars of a view ("daily" or "weekly") as row dicts, oldest first; [] when the view is unavailable."""
  v = ((block or {}).get("views") or {}).get(view) or {}
  if not v.get("available"):
    return []
  return table_dicts(block.get(view))[v["first"]:v["last"] + 1]


def crash_history(block: dict) -> list[dict]:
  """Every crash index reading the block holds, oldest first: the scores before the daily table, then the daily table's own."""
  older = table_dicts(((block or {}).get("evidence") or {}).get("crash_before_daily"))
  return older + [{"date": r["date"], "score": r["crash"]} for r in table_dicts((block or {}).get("daily")) if r.get("crash") is not None]


def block_bytes(block: dict) -> int:
  """Size of the block as compact UTF-8 JSON."""
  return len(json.dumps(block, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def describe(block: dict | None) -> str:
  """One line about a block for the pipeline log (English)."""
  block = block or {}
  if not block.get("available"):
    return f"stress chart unavailable ({block.get('reason')})"
  st = block.get("spike_stats") or {}
  parts = [f"daily {block['daily']['n']} sessions, weekly {block['weekly']['n']} bars, VIX {block['vix']['n']} rows",
           f"spike rule marks {st.get('share_pct')}% of {st.get('sessions')} VIX sessions ({st.get('episodes')} episodes)"]
  for name in ("daily", "weekly"):
    v = (block.get("views") or {}).get(name) or {}
    if not v.get("available"):
      parts.append(f"{name} view unavailable")
      continue
    ch = v["channel"]
    ch_txt = f"channel {ch['direction']} R2 {ch['r2']}" if ch.get("available") else f"no channel ({ch.get('reason')})"
    band = v["profile"].get("busiest") or {}
    parts.append(f"{name} view {v['bars']} bars: {len(v['spikes']['episodes'])} spike episode(s), {len(v['crash_drops'])} drop marker(s), {ch_txt}, "
                 f"busiest band {band.get('price_low')}-{band.get('price_high')}")
  parts.append(f"{block_bytes(block) / 1024:.0f} KB")
  return "; ".join(parts)
