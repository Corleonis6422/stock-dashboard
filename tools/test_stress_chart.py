#!/usr/bin/env python3
"""Tests for soxl_quant/stress_chart.py — no network; synthetic series with known answers, then the repo's stored payloads.

Run: python3 tools/test_stress_chart.py [extra payload .json / .json.gz files or folders ...]

Covers
  1. VIX spike rule: hand-computed marks, the tie at the threshold, sessions that cannot be judged
  2. no repaint: the mark of a session is the same on the series cut after it, on any tail that still
     holds its lookback, and on a 260-row store
  3. spike episodes (joining runs at most 5 unmarked sessions apart) and the spike statistics
  4. weekly bars: OHLCV, the ISO week across New Year, a holiday week, VIX / crash roll-up, the spike
     flag, the 20-week average volume, the session count
  5. the partial-week flag: mid-week, Friday, a Friday holiday, a session that is not final
  6. trend channel: end points, sigma and R^2 of constructed series; no channel below R^2 0.5 or 30 bars
  7. volume profile: both band spacings (equal width = the method of technicals.volume_profile on the
     daily view, equal ratio on the weekly view): band bounds, totals, up / down split, the busiest
     band and its runner-up, a typical price on a bound, ties, degenerate input
  8. evidence figures: entry at the next open and exit at close[i+h], the no-overlap rule, open episodes,
     the base rate over every session, the small-sample flag, the crash "rises to 80" condition
  9. the block: views, markers, legend lines, missing VIX / crash index / bars, every session a spike
 10. for_payload: block passthrough, the reduced block, the unavailable lines, junk input, the keys of
     an unavailable block, an exception inside the reduced build
 11. the stored payloads of the repo (and any path given on the command line): no exception, the
     reduced daily view holds the latest bars of the block's daily view, the crash index equals
     early_warning.chart, weekly bars and spike flags rebuild from the stored series, size and share limits
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
import gzip
import json
import math
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from soxl_quant import early_warning  # noqa: E402
from soxl_quant import marketclock  # noqa: E402
from soxl_quant import stress_chart as sc  # noqa: E402
from soxl_quant import technicals  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
  print(("  ok   " if cond else "  FAIL ") + msg)
  if not cond:
    FAILS.append(msg)


def close(a: float, b: float, tol: float = 1e-9) -> bool:
  return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def weekdays(start: str, n: int, skip: tuple[str, ...] = ()) -> list[str]:
  """n weekday dates from ``start`` on, leaving out the dates in ``skip``."""
  out, d = [], date.fromisoformat(start)
  while len(out) < n:
    if d.weekday() < 5 and d.isoformat() not in skip:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def bar(d: str, o: float, h: float, lo: float, c: float, v: int, **more) -> dict:
  return {"date": d, "open": o, "high": h, "low": lo, "close": c, "volume": v, **more}


def starts_week(d: str) -> bool:
  """True when no NYSE trading day precedes ``d`` inside its ISO week."""
  day = date.fromisoformat(d)
  return not any(marketclock.is_trading_day(day - timedelta(days=k)) for k in range(1, day.weekday() + 1))


def is_one_zh_line(s) -> bool:
  return isinstance(s, str) and 6 <= len(s) <= 140 and "\n" not in s and any("\u4e00" <= ch <= "\u9fff" for ch in s)


# --------------------------------------------------------------------------- #
def test_spike_rule() -> None:
  print("1. spike rule")
  s = [10.0] * 60 + [13.99, 14.0, 14.01, 10.0]
  m = sc.spike_marks(s)
  check(m[:60] == [None] * 60, "the first 60 sessions are not judged")
  check(m[60:] == [False, True, True, False], f"13.99 / 14.00 / 14.01 / 10.00 against a median of 10.00 → {m[60:]} (expect F T T F; 14.00 is the tie)")
  # threshold 23.17 = 1.4 x 16.55: the float product 1.4 * 16.55 is not exactly 23.17
  check(sc.spike_marks([16.55] * 60 + [23.17])[-1] is True and sc.spike_marks([16.55] * 60 + [23.16])[-1] is False, "tie at 1.4 x 16.55 = 23.17 is a spike, 23.16 is not")
  # even lookback: the median is the mean of the two middle closes, here (10.00 + 10.10) / 2 = 10.05 → threshold 14.07
  mix = [10.0, 10.1] * 30
  check(sc.spike_marks(mix + [14.07])[-1] is True and sc.spike_marks(mix + [14.06])[-1] is False, "median of 30 x 10.00 and 30 x 10.10 is 10.05 → 14.07 marks, 14.06 does not")
  check(sc.spike_marks([1, 2, 3, 6, 5.99], lookback=3, multiple=2.0) == [None, None, None, True, False], "lookback 3, multiple 2: [1,2,3,6,5.99] → [-,-,-,T,F]")
  check(sc.spike_marks([]) == [] and sc.spike_marks([12.0] * 60) == [None] * 60, "empty and too-short series give no judged session")
  check(sc.SPIKE_LOOKBACK <= 100, f"lookback {sc.SPIKE_LOOKBACK} <= 100 sessions")


def test_no_repaint() -> None:
  print("2. no repaint")
  rnd = random.Random(7)
  v, s = 16.0, []
  for _ in range(900):
    v = max(9.0, v * math.exp(rnd.gauss(0.0, 0.07)) * (1.6 if rnd.random() < 0.01 else 1.0) * (0.97 if v > 30 else 1.0))
    s.append(round(v, 2))
  full = sc.spike_marks(s)
  marked = sum(1 for f in full if f)
  check(20 < marked < 400, f"random series has marked and unmarked sessions ({marked} of {len(s)})")
  check(all(sc.spike_marks(s[:t + 1])[t] == full[t] for t in range(len(s))), "cutting the series after any session D leaves the mark of D unchanged (900 cuts)")
  check(all(sc.spike_marks(s[:m]) == full[:m] for m in (61, 100, 333, 899)), "appending later data never changes an earlier mark")
  ok = True
  for start in (1, 37, 250, 640):
    tail = sc.spike_marks(s[start:])
    ok = ok and all(tail[k] == full[start + k] for k in range(sc.SPIKE_LOOKBACK, len(tail))) and tail[:sc.SPIKE_LOOKBACK] == [None] * sc.SPIKE_LOOKBACK
  check(ok, "a tail of the series gives the same mark for every session that still has 60 sessions before it")
  check(sc.spike_marks(s[-260:])[-200:] == full[-200:], "a 260-row store gives the same marks for its latest 200 rows")
  mirror = [None if t < 60 else s[t] >= 1.4 * statistics.median(s[t - 60:t]) for t in range(len(s))]
  check(mirror == full, "plain float arithmetic (close >= 1.4 x statistics.median of the 60 before) gives the same marks on this series")


def test_episodes_and_stats() -> None:
  print("3. episodes and statistics")
  T, F, N = True, False, None
  marks = [F, F, F, T, T, F, F, F, F, F, T, F, F, F, F, F, F, T, N, N, T]
  check(sc.spike_episodes(marks) == [(3, 10), (17, 20)], f"gap of 5 joins, gap of 6 splits, unjudged counts as unmarked → {sc.spike_episodes(marks)}")
  check(sc.spike_episodes([F, N, F]) == [] and sc.spike_episodes([T]) == [(0, 0)], "no marks → no episode; one mark → one episode")
  check(sc.spike_episodes([T, F, F, T], max_gap=1) == [(0, 0), (3, 3)] and sc.spike_episodes([T, F, F, T], max_gap=2) == [(0, 3)], "max_gap parameter")
  vix = [{"date": d, "close": 10.0} for d in weekdays("2020-01-01", 200)]
  for k in (100, 101, 102, 103, 104, 150):
    vix[k]["close"] = 20.0
  st = sc.spike_statistics(vix)
  check((st["sessions"], st["evaluated"], st["marked"], st["episodes"]) == (200, 140, 6, 2), f"200 sessions, 140 judged, 6 marked, 2 episodes → {st['sessions']}, {st['evaluated']}, {st['marked']}, {st['episodes']}")
  check(st["share_pct"] == 3.0 and st["share_of_evaluated_pct"] == 4.29 and st["within_cap"] is True and st["first_date"] == vix[0]["date"] and st["last_date"] == vix[-1]["date"],
        f"share 6/200 = 3.0% (of judged 4.29%), within the 10% cap, dates {st['first_date']} to {st['last_date']}")
  hot = [{"date": d, "close": round(10.0 * 1.02 ** i, 4)} for i, d in enumerate(weekdays("2020-01-01", 200))]
  sh = sc.spike_statistics(hot)
  check(sh["marked"] == 140 and sh["share_pct"] == 70.0 and sh["within_cap"] is False, "a series that rises 2% every session marks every judged session and breaks the cap")
  check(sc.spike_statistics(hot, scope="stored_vix_rows")["within_cap"] is None, "the cap is only judged on the whole loaded history")
  cv = sc.clean_vix([{"date": "2026-01-05", "close": 15.0}, {"date": "2026-01-02", "vix": 14.0}, {"date": "2026-01-05", "close": 16.0}, {"date": "bad"}, {"date": "2026-01-06", "close": None}, None])
  check(cv == [{"date": "2026-01-02", "close": 14.0}, {"date": "2026-01-05", "close": 16.0}], "clean_vix sorts, keeps the last row of a repeated date, drops rows without a close")


def test_weekly_bars() -> None:
  print("4. weekly bars")
  # Christmas week (Thu 12-25 closed), the ISO week across New Year (Thu 01-01 closed), a full week, two sessions of a fourth week
  ds = weekdays("2025-12-22", 15, skip=("2025-12-25", "2026-01-01"))
  check(ds[:4] == ["2025-12-22", "2025-12-23", "2025-12-24", "2025-12-26"] and ds[4:8] == ["2025-12-29", "2025-12-30", "2025-12-31", "2026-01-02"] and ds[-2:] == ["2026-01-12", "2026-01-13"], "fixture dates")
  days = []
  for i, d in enumerate(ds):
    days.append(bar(d, 100.0 + i, 102.0 + i, 97.0 + i, 101.0 + i, 1000 * (i + 1), vix=20.0 + i, crash=50.0 + i, spike=False))
  days[5]["spike"] = True            # 2025-12-30, second week
  days[7]["vix"] = None              # 2026-01-02 has no VIX: the week takes 12-31
  days[7]["crash"] = None
  days[7]["spike"] = None
  for i in (8, 9, 10, 11, 12):       # third week: never judged, no VIX
    days[i]["vix"] = None
    days[i]["spike"] = None
  w = sc.weekly_bars(days, final=True)
  check(len(w) == 4 and [b["sessions"] for b in w] == [4, 4, 5, 2], f"4 bars with 4 / 4 / 5 / 2 sessions → {[b['sessions'] for b in w]}")
  b0, b1, b2, b3 = w
  check((b0["start"], b0["end"], b0["open"], b0["high"], b0["low"], b0["close"], b0["volume"]) == ("2025-12-22", "2025-12-26", 100.0, 105.0, 97.0, 104.0, 10000), f"holiday week OHLCV → {b0['open']}, {b0['high']}, {b0['low']}, {b0['close']}, {b0['volume']}")
  check((b1["start"], b1["end"], b1["open"], b1["high"], b1["low"], b1["close"], b1["volume"]) == ("2025-12-29", "2026-01-02", 104.0, 109.0, 101.0, 108.0, 26000), "the ISO week 2026-W01 across New Year is one bar: 12-29 to 01-02")
  check((b1["vix"], b1["crash"], b1["spike"]) == (26.0, 56.0, True), f"VIX and crash take the last session with a value (12-31: 26.0, 56.0); one marked session marks the week → {b1['vix']}, {b1['crash']}, {b1['spike']}")
  check((b0["vix"], b0["crash"], b0["spike"]) == (23.0, 53.0, False), "a judged week without a marked session is False")
  check((b2["vix"], b2["spike"], b2["crash"], b2["volume"]) == (None, None, 62.0, 55000), "a week that was never judged has spike None and VIX None; crash and volume still roll up")
  check((b3["start"], b3["end"], b3["open"], b3["close"], b3["high"], b3["low"]) == ("2026-01-12", "2026-01-13", 113.0, 115.0, 116.0, 110.0), "last bar from two sessions")
  check([b["partial"] for b in w] == [False, False, False, True], "only the last bar is partial (Tuesday 01-13: three trading days remain)")
  check(all(b["vol_avg20w"] is None for b in w), "no 20-week average before 20 weekly bars exist")
  # 25 full weeks, weekly volume (k+1) x 5000
  long = []
  for k, d in enumerate(weekdays("2024-01-01", 125)):
    long.append(bar(d, 50.0, 51.0, 49.0, 50.5, 1000 * (k // 5 + 1)))
  wl = sc.weekly_bars(long)
  check(len(wl) == 25 and [b["volume"] for b in wl[:3]] == [5000, 10000, 15000], "25 weekly bars with volumes 5000, 10000, 15000, …")
  check(wl[18]["vol_avg20w"] is None and wl[19]["vol_avg20w"] == 52500 and wl[24]["vol_avg20w"] == 77500, f"20-week average includes the current week: bar 20 → 52,500, bar 25 → 77,500 (got {wl[19]['vol_avg20w']}, {wl[24]['vol_avg20w']})")
  check(sc.weekly_bars([]) == [], "no sessions → no bars")
  check(sc.week_key("2025-12-29") == (2026, 1) == sc.week_key("2026-01-02") and sc.week_key("2026-01-04") == (2026, 1) and sc.week_key("2026-01-05") == (2026, 2), "ISO week keys run Monday to Sunday")


def test_partial_week() -> None:
  print("5. partial week")
  check(sc.week_is_partial("2026-01-14") is True, "Wednesday 2026-01-14: Thursday and Friday remain → partial")
  check(sc.week_is_partial("2026-01-16") is False, "Friday 2026-01-16 → complete")
  check(sc.week_is_partial("2026-04-02") is False, "Thursday 2026-04-02 before Good Friday (NYSE closed) → complete")
  check(sc.week_is_partial("2026-11-25") is True, "Wednesday 2026-11-25: Thanksgiving is closed but Friday trades → partial")
  check(sc.week_is_partial("2026-01-16", final=False) is True, "a Friday session that is still in progress → partial")
  days = [bar(d, 10.0, 11.0, 9.0, 10.5, 100) for d in weekdays("2026-01-05", 10)]
  check([b["partial"] for b in sc.weekly_bars(days)] == [False, False] and [b["partial"] for b in sc.weekly_bars(days, final=False)] == [False, True], "final=False marks only the last weekly bar")


def test_channel() -> None:
  print("6. trend channel")
  n = 40
  exact = [100.0 * 1.01 ** i for i in range(n)]
  ch = sc.trend_channel(exact)
  last = 100.0 * 1.01 ** (n - 1)
  check(ch["available"] and ch["direction"] == "up" and ch["r2"] == 1.0 and ch["sigma_log"] == 0.0 and ch["bars"] == 40, "exact 1% per bar: R² 1, sigma 0, rising")
  check(ch["upper"] == ch["mid"] == ch["lower"] == [100.0, round(last, 4)] and ch["slope_pct_per_bar"] == 1.0, f"all three lines run 100.00 → {last:.4f}, slope +1.000% per bar")
  # residuals +d, -d, -d, +d are orthogonal to the constant and to the trend, so the fit is known exactly
  d = 0.05
  b = math.log(1.01)
  wav = [100.0 * math.exp(b * i + d * (1 if i % 4 in (0, 3) else -1)) for i in range(n)]
  ch = sc.trend_channel(wav)
  sxx = n * (n * n - 1) / 12.0
  r2 = b * b * sxx / (b * b * sxx + n * d * d)
  check(ch["available"] and close(ch["sigma_log"], d, 1e-7) and close(ch["slope_log_per_bar"], b, 1e-7) and close(ch["r2"], r2, 1e-4), f"sigma {ch['sigma_log']} = {d}, slope {ch['slope_log_per_bar']} = ln 1.01, R² {ch['r2']} = {r2:.4f}")
  want_u, want_l = [100.0 * math.exp(2 * d), last * math.exp(2 * d)], [100.0 * math.exp(-2 * d), last * math.exp(-2 * d)]
  check(all(close(x, y, 1e-6) for x, y in zip(ch["upper"] + ch["lower"] + ch["mid"], want_u + want_l + [100.0, last])), f"upper {ch['upper']} and lower {ch['lower']} are the middle line x e^(±2 x 0.05)")
  check(sum(1 for i, c in enumerate(wav) if 100.0 * math.exp(b * i - 2 * d) <= c <= 100.0 * math.exp(b * i + 2 * d)) == n, "every close of the constructed series lies inside the band")
  down = sc.trend_channel([200.0 * 0.98 ** i for i in range(60)])
  check(down["available"] and down["direction"] == "down" and down["slope_pct_per_bar"] == -2.0 and down["upper"][0] == 200.0 and "下降" in down["text_zh"], "falling series → a falling channel")
  # R² = 0.5 exactly when slope² x Sxx = n x d²
  b_half = d * math.sqrt(n / sxx)
  above = sc.trend_channel([100.0 * math.exp(1.02 * b_half * i + d * (1 if i % 4 in (0, 3) else -1)) for i in range(n)])
  below = sc.trend_channel([100.0 * math.exp(0.98 * b_half * i + d * (1 if i % 4 in (0, 3) else -1)) for i in range(n)])
  check(above["available"] and above["r2"] >= 0.5 and not below["available"] and below["reason"] == "low_r2" and below["r2"] < 0.5 and is_one_zh_line(below["text_zh"]),
        f"R² {above['r2']} draws a channel, R² {below['r2']} does not: {below['text_zh']}")
  short = sc.trend_channel(exact[:29])
  check(not short["available"] and short["reason"] == "too_few_bars" and "29" in short["text_zh"] and sc.trend_channel(exact[:30])["available"], f"29 bars → no channel ({short['text_zh']}); 30 bars → channel")
  flat = sc.trend_channel([50.0] * 40)
  check(not flat["available"] and flat["reason"] == "low_r2", "a flat series has no trend to draw")
  check(sc.trend_channel([10.0] * 20 + [0.0] + [10.0] * 20)["reason"] == "bad_prices", "a non-positive close → no channel")


def test_volume_profile() -> None:
  print("7. volume profile")
  # ---- equal width (daily view): range 1 to 17 in 4 bands of width 4 → bounds 1, 5, 9, 13, 17
  bars = [
      bar("d1", 1.5, 3.0, 1.0, 2.0, 100),      # typical 2  → band 0; close >= own open → up
      bar("d2", 6.5, 8.0, 6.0, 7.0, 310),      # typical 7  → band 1; 7 >= 2 → up
      bar("d3", 6.8, 7.0, 5.0, 6.0, 50),       # typical 6  → band 1; 6 < 7 → down
      bar("d4", 14.0, 17.0, 13.0, 15.0, 340),  # typical 15 → band 3; up
      bar("d5", 11.5, 12.0, 10.0, 11.0, 10),   # typical 11 → band 2; 11 < 15 → down
  ]
  p = sc.volume_profile(bars, bins=4, spacing="equal_width")
  t = p["bands"]
  check(p["available"] and (p["spacing"], p["range_low"], p["range_high"], p["band_width"], p["band_ratio"]) == ("equal_width", 1.0, 17.0, 4.0, None), "equal width: range 1 to 17 in 4 bands of width 4")
  check(t["price_low"] == [1.0, 5.0, 9.0, 13.0] and t["price_high"] == [5.0, 9.0, 13.0, 17.0] and t["n"] == 4, f"every band carries its bounds: {t['price_low']} / {t['price_high']}")
  check(t["total_volume"] == [100, 360, 10, 340] and t["up_volume"] == [100, 310, 0, 340] and t["down_volume"] == [0, 50, 10, 0] and p["total_volume"] == 810, f"totals {t['total_volume']}, up {t['up_volume']}, down {t['down_volume']}")
  check(p["busiest"] == {"index": 1, "price_low": 5.0, "price_high": 9.0, "volume": 360, "share_pct": 44.4}, f"busiest band 5–9 with 360 of 810 = 44.4% → {p['busiest']}")
  check(p["runner_up"] == {"index": 3, "price_low": 13.0, "price_high": 17.0, "volume": 340, "share_pct": 42.0} and p["lead_pts"] == 2.5, f"runner-up 13–17 with 340 = 42.0%; lead 20 of 810 = 2.5 points → {p['runner_up']}, {p['lead_pts']}")
  edge = sc.volume_profile(bars + [bar("d6", 5.0, 6.0, 4.0, 5.0, 1000)], bins=4, spacing="equal_width")
  check(edge["bands"]["total_volume"] == [100, 1360, 10, 340], "a typical price exactly on a bound (5.0) goes to the band above it")
  top = sc.volume_profile([bar("a", 1.0, 1.0, 1.0, 1.0, 5), bar("b", 17.0, 17.0, 17.0, 17.0, 7)], bins=4, spacing="equal_width")
  check(top["bands"]["total_volume"] == [5, 0, 0, 7], "a typical price equal to the highest high falls in the top band")
  tie = sc.volume_profile([bar("a", 1.5, 3.0, 1.0, 2.0, 500), bar("b", 14.0, 17.0, 13.0, 15.0, 500)], bins=4, spacing="equal_width")
  check(tie["busiest"]["index"] == 0 and tie["runner_up"]["index"] == 3 and tie["lead_pts"] == 0.0, "two bands with the same volume: the lower-priced one is the busiest, the lead is 0")
  three = sc.volume_profile([bar("a", 1.5, 3.0, 1.0, 2.0, 500), bar("b", 6.5, 8.0, 6.0, 7.0, 500), bar("c", 14.0, 17.0, 13.0, 15.0, 500)], bins=4, spacing="equal_width")
  check((three["busiest"]["index"], three["runner_up"]["index"]) == (0, 1), "three equal bands: busiest and runner-up are the two lowest")
  # the daily rule is the method of technicals.volume_profile: same bands, same totals, same POC on the same 126 bars
  soxl = synthetic_history()[0]
  tech = technicals.analyze(soxl)
  mine = sc.volume_profile(soxl[-126:], spacing="equal_width")
  tb = tech["volume_profile"]
  same_bounds = all(round(mine["bands"]["price_low"][k], 2) == tb[k]["price_low"] and round(mine["bands"]["price_high"][k], 2) == tb[k]["price_high"] for k in range(24))
  same_vol = all((mine["bands"]["total_volume"][k], mine["bands"]["up_volume"][k], mine["bands"]["down_volume"][k]) == (tb[k]["total_volume"], tb[k]["up_volume"], tb[k]["down_volume"]) for k in range(24))
  bz = mine["busiest"]
  check(len(tb) == 24 and same_bounds and same_vol and tb[bz["index"]]["price_mid"] == tech["poc_price"] and bz["price_low"] <= tech["poc_price"] <= bz["price_high"],
        f"equal width on 126 bars reproduces technicals.volume_profile: 24 bands, same totals, POC {tech['poc_price']} inside the busiest band {bz['price_low']}–{bz['price_high']}")

  # ---- equal ratio (weekly view): range 1 to 16 in 4 bands of ratio 2 → bounds 1, 2, 4, 8, 16
  rbars = [
      bar("d1", 1.1, 1.5, 1.0, 1.2, 100),     # typical 1.233 → band 0; up
      bar("d2", 2.6, 3.5, 2.5, 3.0, 310),     # typical 3.0   → band 1; up
      bar("d3", 2.9, 3.0, 2.2, 2.3, 50),      # typical 2.5   → band 1; down
      bar("d4", 9.5, 16.0, 9.0, 10.0, 340),   # typical 11.67 → band 3; up
      bar("d5", 6.5, 7.0, 5.0, 6.0, 10),      # typical 6.0   → band 2; down
  ]
  r = sc.volume_profile(rbars, bins=4, spacing="equal_ratio")
  t = r["bands"]
  check(r["available"] and (r["spacing"], r["range_low"], r["range_high"], r["band_ratio"], r["band_width"]) == ("equal_ratio", 1.0, 16.0, 2.0, None), "equal ratio: range 1 to 16 in 4 bands of ratio 2")
  check(t["price_low"] == [1.0, 2.0, 4.0, 8.0] and t["price_high"] == [2.0, 4.0, 8.0, 16.0], f"band bounds 1, 2, 4, 8, 16 → {t['price_low']} / {t['price_high']}")
  check(t["total_volume"] == [100, 360, 10, 340] and t["up_volume"] == [100, 310, 0, 340] and t["down_volume"] == [0, 50, 10, 0], f"totals {t['total_volume']}, up {t['up_volume']}, down {t['down_volume']}")
  check(r["busiest"] == {"index": 1, "price_low": 2.0, "price_high": 4.0, "volume": 360, "share_pct": 44.4} and r["runner_up"]["index"] == 3 and r["lead_pts"] == 2.5, f"busiest band 2–4 with 360 of 810 = 44.4%, runner-up 8–16 → {r['busiest']}")
  # the same five bars under equal width: range 1 to 16, width 3.75 → typical 6.0 and 2.5, 3.0 move bands
  w = sc.volume_profile(rbars, bins=4, spacing="equal_width")
  check(w["bands"]["price_low"] == [1.0, 4.75, 8.5, 12.25] and w["bands"]["total_volume"] == [460, 10, 340, 0] and w["busiest"]["index"] == 0, f"the two spacings give different bands on the same bars: equal width totals {w['bands']['total_volume']}")
  rtie = sc.volume_profile([bar("a", 1.2, 1.5, 1.0, 1.2, 500), bar("b", 9.5, 16.0, 9.0, 10.0, 500)], bins=4, spacing="equal_ratio")
  check(rtie["busiest"]["index"] == 0, "equal ratio: on a tie the lower-priced band is the busiest")
  rtop = sc.volume_profile([bar("a", 1.0, 1.0, 1.0, 1.0, 5), bar("b", 16.0, 16.0, 16.0, 16.0, 7)], bins=4, spacing="equal_ratio")
  check(rtop["bands"]["total_volume"] == [5, 0, 0, 7], "equal ratio: a typical price equal to the highest high falls in the top band")
  e = math.e
  wide = [bar("a", 10.0, 10.0 * e ** 2.4, 10.0, 10.0 * e ** 0.55, 9)]   # sets the range: 10 to 10 x e^2.4, so each of the 24 bands is e^0.1 wide
  p24 = sc.volume_profile(wide + [bar("b", 0, 10.0 * e ** 0.56, 10.0 * e ** 0.54, 10.0 * e ** 0.55, 99)], spacing="equal_ratio")
  k = p24["busiest"]["index"]
  check(p24["bins"] == 24 and close(p24["band_ratio"], e ** 0.1, 1e-6) and k == 5 and close(p24["bands"]["price_low"][5], 10.0 * e ** 0.5, 1e-4) and close(p24["bands"]["price_high"][5], 10.0 * e ** 0.6, 1e-4),
        f"24 bands, ratio e^0.1 per band; a typical price of 10 x e^0.55 is in band 5 (10 x e^0.5 to 10 x e^0.6) → band {k}")
  check(len(p24["bands"]["price_low"]) == 24 and p24["bands"]["n"] == 24 and p24["bands"]["price_low"][0] == 10.0 and close(p24["bands"]["price_high"][23], 10.0 * e ** 2.4, 1e-6), "24 bands from the lowest low to the highest high")
  # ---- no profile
  check(not sc.volume_profile([])["available"] and sc.volume_profile([bar("a", 5.0, 5.0, 5.0, 5.0, 10)])["reason"] == "flat_range" and sc.volume_profile([bar("a", 1.0, 2.0, 1.0, 1.5, 0)])["reason"] == "no_volume",
        "no bars, a flat range and zero volume each give no profile")
  try:
    sc.volume_profile(bars, spacing="other")
    bad = False
  except ValueError:
    bad = True
  check(bad and sc.PROFILE_SPACING == {"daily": "equal_width", "weekly": "equal_ratio"} and sc.PROFILE_BINS == 24, "spacing is equal_width on the daily view and equal_ratio on the weekly view; anything else is refused")


def test_evidence_figures() -> None:
  print("8. evidence figures")
  n = 60
  dates = [f"D{i:03d}" for i in range(n)]
  opens = [100.0 + i for i in range(n)]
  closes = [100.5 + i for i in range(n)]
  starts = [i in (10, 13, 15, 40, 58) for i in range(n)]
  f = sc.forward_figure(opens, closes, dates, starts, 5, 59, 5)
  # return at i = (100.5 + i + 5) / (101 + i) - 1 = 4.5 / (101 + i)
  check(f["episode_dates"] == ["D010", "D015", "D040"] and f["skipped_overlap"] == 1 and f["open_dates"] == ["D058"], f"episodes at 10, 15, 40 are counted; 13 overlaps 10; 58 has no exit yet → {f['episode_dates']}, skipped {f['skipped_overlap']}, open {f['open_dates']}")
  check(f["n"] == 3 and f["wins"] == 3 and close(f["median_ret_pct"], 450.0 / 116.0, 1e-6) and f["gain_share_pct"] == 100.0, f"median of 4.5/111, 4.5/116, 4.5/141 = {450.0 / 116.0:.6f}% → {f['median_ret_pct']}; 3 of 3 gain")
  base_med = (450.0 / 130.0 + 450.0 / 131.0) / 2.0
  check(f["base"]["n"] == 50 and f["base"]["wins"] == 50 and close(f["base"]["median_ret_pct"], base_med, 1e-6) and f["period"] == {"start": "D005", "end": "D054"},
        f"base rate over sessions 5..54: n 50, median {base_med:.6f}% → {f['base']['median_ret_pct']}, period {f['period']}")
  check(f["small_sample"] is True and f["horizon"] == 5, "3 episodes → small sample")
  # entry at the next open (always 100), exit at close[i + 5]: returns +3, -2, +1, -5
  flat_o = [100.0] * 30
  cl = [100.0] * 30
  cl[5], cl[10], cl[15], cl[20] = 103.0, 98.0, 101.0, 95.0
  g = sc.forward_figure(flat_o, cl, dates[:30], [i in (0, 5, 10, 15) for i in range(30)], 0, 29, 5)
  check(g["n"] == 4 and g["wins"] == 2 and close(g["median_ret_pct"], -0.5) and g["gain_share_pct"] == 50.0, f"returns +3, −2, +1, −5 → median −0.5%, 2 of 4 gain → {g['median_ret_pct']}, {g['gain_share_pct']}")
  op = [100.0] * 12
  op[4] = 50.0                         # the session after the signal opens at 50
  one = sc.forward_figure(op, [100.0] * 12, dates[:12], [i == 3 for i in range(12)], 0, 11, 5)
  check(one["n"] == 1 and close(one["median_ret_pct"], 100.0), "the entry price is the open of the session after the signal (100 / 50 − 1 = +100%)")
  # no overlap, for random conditions
  rnd = random.Random(5)
  m = 1500
  o2 = [50.0 + rnd.random() for _ in range(m)]
  c2 = [50.0 + rnd.random() for _ in range(m)]
  d2 = [f"R{i:04d}" for i in range(m)]
  st2 = [rnd.random() < 0.15 for _ in range(m)]
  ok, counts = True, []
  for h in sc.EVIDENCE_HORIZONS:
    r = sc.forward_figure(o2, c2, d2, st2, 10, m - 1, h)
    idx = [int(x[1:]) for x in r["episode_dates"] + r["open_dates"]]
    ok = ok and all(b - a >= h for a, b in zip(idx, idx[1:])) and r["n"] + len(r["open_dates"]) + r["skipped_overlap"] == sum(st2[10:])
    base = [(c2[i + h] / o2[i + 1] - 1.0) * 100.0 for i in range(10, m - h)]
    ok = ok and r["base"]["n"] == len(base) and close(r["base"]["median_ret_pct"], statistics.median(base), 1e-6) and close(r["base"]["gain_share_pct"], sum(1 for x in base if x > 0) / len(base) * 100.0, 1e-6)
    counts.append(r["n"])
  check(ok, f"episodes never overlap within a horizon, every condition date is counted, skipped or open, and the base rate covers every session (n per horizon {counts})")
  every = [i % 5 == 0 for i in range(200)]
  n19 = sc.forward_figure([100.0] * 200, [101.0] * 200, d2[:200], every, 0, 94, 5)
  n20 = sc.forward_figure([100.0] * 200, [101.0] * 200, d2[:200], every, 0, 99, 5)
  check((n19["n"], n19["small_sample"], n20["n"], n20["small_sample"]) == (19, True, 20, False), "19 episodes are a small sample, 20 are not")
  check(sc.EVIDENCE_SMALL_N == 20 and sc.EVIDENCE_DEFAULT_HORIZON in sc.EVIDENCE_HORIZONS, "small-sample limit 20; the default horizon is one of the horizons")
  empty = sc.forward_figure([100.0] * 30, [101.0] * 30, dates[:30], [False] * 30, 0, 29, 10)
  check(empty["n"] == 0 and empty["median_ret_pct"] is None and empty["gain_share_pct"] is None and empty["small_sample"] is True and empty["base"]["n"] == 20, "no episode → null figures, base rate still given")
  sc80 = sc.crash_rise_starts([None, 70.0, 85.0, 90.0, 75.0, 80.0, 80.0, 79.9, 80.0, None, 85.0])
  check([i for i, x in enumerate(sc80) if x] == [2, 5, 8], f"crash index rises to 80 or more at 70→85, 75→80, 79.9→80; not after a missing value → {[i for i, x in enumerate(sc80) if x]}")


def synthetic_history(n: int = 1000, seed: int = 3) -> tuple[list[dict], list[dict], list[dict], dict]:
  """A SOXL-like history, a VIX history with two holiday-only rows and planted spikes, a crash series and an early_warning section."""
  rnd = random.Random(seed)
  ds = weekdays("2022-01-03", n)
  soxl, px = [], 40.0
  for i, d in enumerate(ds):
    o = px * (1 + rnd.gauss(0, 0.01))
    c = max(1.0, o * (1 + rnd.gauss(0.001, 0.04)))
    soxl.append({"date": d, "open": round(o, 4), "high": round(max(o, c) * 1.01, 4), "low": round(min(o, c) * 0.99, 4), "close": round(c, 4), "volume": 1_000_000 + 1000 * (i % 37)})
    px = c
  vix = []
  for i, d in enumerate(ds):
    vix.append({"date": d, "close": round(15.0 + 2.0 * math.sin(i / 9.0), 2)})
  for k in (400, 401, 402, 700, 705, 940, 941, 998, 999):
    vix[k]["close"] = 40.0
  extra = [(date.fromisoformat(ds[500]) - timedelta(days=2)).isoformat(), (date.fromisoformat(ds[800]) - timedelta(days=1)).isoformat()]
  vix = sorted(vix + [{"date": x, "close": 15.5} for x in extra if x not in ds], key=lambda r: r["date"])
  crash = [{"date": d, "score": round(50.0 + 45.0 * math.sin(i / 13.0), 1)} for i, d in enumerate(ds) if i >= 205]
  episodes = [{"date": ds[k], "close": soxl[k]["close"], "fwd_min_pct": -25.0, "top_type": True, "score_t": 88.0, "flagged": True} for k in (300, 600, 890, 940, 995)]
  ews = {"chart": [{"date": x["date"], "close": 1.0, "score": x["score"], "raw": 1.0} for x in crash[-130:]],
         "event_study": {"episodes": episodes, "drop_pct": -20.0, "horizon_days": 5, "threshold": 80.0, "n_days": 500, "stats_all_80": {"flag_days": 10, "precision_pct": 20.0, "base_rate_pct": 10.0}}}
  return soxl, vix, crash, ews


def test_small_rules() -> None:
  print("8b. rules that could be read two ways")
  # a return of exactly 0% is not a gain
  z = sc.forward_figure([100.0] * 12, [100.0] * 12, [f"Z{i:02d}" for i in range(12)], [i == 3 for i in range(12)], 0, 11, 5)
  check(z["n"] == 1 and z["wins"] == 0 and z["gain_share_pct"] == 0.0 and z["median_ret_pct"] == 0.0 and z["base"]["wins"] == 0 and z["base"]["n"] == 7,
        "a return of exactly 0% is not a gain, in the figure and in the base rate")
  # two sessions share the highest VIX close of an episode: the earlier one is the peak and carries the label
  sess = [{"date": f"P{i}", "vix": v, "spike": True} for i, v in enumerate([20.0, 30.0, 30.0, 25.0])]
  ep = sc._view_episodes(sess, [10, 11, 12, 13])
  check(len(ep) == 1 and (ep[0]["peak_vix"], ep[0]["peak_date"], ep[0]["anchor_bar"]) == (30.0, "P1", 11), "a tie for the peak VIX close of an episode goes to the earlier session")
  # early_warning.chart wins on a shared date; other dates keep the value of the whole series
  soxl, vix, crash, ews = synthetic_history()
  shifted = dict(ews, chart=[dict(x, score=round(x["score"] / 2.0, 1)) for x in ews["chart"]])
  blk = sc.build(soxl, vix, crash, shifted, soxl_long=None, final=True)
  got = {r["date"]: r["crash"] for r in sc.table_dicts(blk["daily"])}
  chart = {x["date"]: x["score"] for x in shifted["chart"]}
  series = {x["date"]: x["score"] for x in crash}
  outside = [k for k in got if k not in chart and k in series]
  check(all(got[k] == v for k, v in chart.items()) and len(outside) > 100 and all(got[k] == series[k] for k in outside) and any(chart[k] != series[k] for k in chart),
        f"where early_warning.chart and the whole score series disagree, the chart value is stored ({len(chart)} dates); the other {len(outside)} dates keep the series value")
  # the event-study figures are copies, so editing the block cannot reach early_warning
  es_in = ews["event_study"]["stats_all_80"]
  es_out = sc.build(soxl, vix, crash, ews, soxl_long=None, final=True)["evidence"]["event_study"]["stats_all_80"]
  check(es_out == es_in and es_out is not es_in, "evidence.event_study.stats_all_80 equals the early_warning figures and is a separate object")


def test_block() -> None:
  print("9. the block")
  soxl, vix, crash, ews = synthetic_history()
  blk = sc.build(soxl, vix, crash, ews, soxl_long=None, final=True)
  d, v, w = sc.table_dicts(blk["daily"]), sc.table_dicts(blk["vix"]), sc.table_dicts(blk["weekly"])
  check(blk["schema"] == sc.SCHEMA and blk["available"] and blk["source"] == "pipeline" and blk["as_of"] == soxl[-1]["date"], "schema, source and as_of")
  check(640 <= len(d) <= 650 and date.fromisoformat(d[0]["date"]).weekday() == 0 and d[-1]["date"] == soxl[-1]["date"], f"{len(d)} daily sessions (>= 640), the first one starts a week ({d[0]['date']})")
  check(all(len(blk[t][c]) == blk[t]["n"] for t in ("daily", "vix", "weekly") for c in blk[t]["columns"]) and blk["daily"]["columns"] == sc.DAILY_COLUMNS, "every column of a table has n values")
  src = {r["date"]: r for r in soxl}
  check(all((r["open"], r["high"], r["low"], r["close"], r["volume"]) == tuple(round(src[r["date"]][k], 2) for k in ("open", "high", "low", "close")) + (src[r["date"]]["volume"],) for r in d), "prices are the history rounded to 2 decimals, volume unchanged")
  vols = [r["volume"] for r in soxl]
  i_last = len(soxl) - 1
  check(d[-1]["vol_avg20"] == round(sum(vols[i_last - 19:i_last + 1]) / 20) and d[0]["vol_avg20"] is not None, "20-session average volume comes from the whole history, also for the first stored session")
  full = dict(zip([r["date"] for r in vix], sc.spike_marks([r["close"] for r in vix])))
  check(v[0]["spike"] is None and v[59]["spike"] is None and v[60]["date"] <= d[0]["date"] and all(r["spike"] == full[r["date"]] for r in v[60:]), "the stored VIX series starts 60 rows before the first daily session; its flags equal the marks on the whole history")
  check([r["spike"] for r in v] == sc.spike_marks([r["close"] for r in v]), "the stored flags are exactly what the rule gives on the stored series")
  check(all(r["spike"] is not None and r["vix"] is not None for r in d) and len(v) > len(d) + 60, "every daily session is judged; VIX-only dates stay in the VIX table")
  chart = {x["date"]: x["score"] for x in ews["chart"]}
  dd = {r["date"]: r["crash"] for r in d}
  check(all(dd[k] == s for k, s in chart.items()) and len(chart) == 130, "crash index equals early_warning.chart on all 130 shared dates")
  check(w == sc.weekly_bars(d, True) and len(w) >= 124, f"{len(w)} weekly bars equal weekly_bars(daily series)")
  vd, vw = blk["views"]["daily"], blk["views"]["weekly"]
  check((vd["bars"], vd["last"] - vd["first"] + 1, vd["end"]) == (126, 126, d[-1]["date"]) and sc.view_bars(blk, "daily") == d[-126:], "daily view = the latest 126 sessions")
  check(sc.DAILY_VIEW_SESSIONS == 126 and vd["start"] == soxl[-126]["date"], "the daily view starts on the first session of the model's 126-session POC window (technicals.volume_profile)")
  check((vw["bars"], vw["last"] - vw["first"] + 1) == (104, 104) and sc.view_bars(blk, "weekly") == w[-104:] and all(b["vol_avg20w"] is not None for b in w[-104:]), "weekly view = the latest 104 weekly bars, each with a 20-week average")
  check(vw["last_bar_partial"] is False and vw["last_bar_sessions"] == w[-1]["sessions"] and is_one_zh_line(vw["last_bar_text_zh"]), f"the weekly view states its last bar: {vw['last_bar_text_zh']}")
  eps = vd["spikes"]["episodes"]
  bars_d = d[-126:]
  check(vd["spikes"]["status"] == "ok" and [e["start"] for e in eps] == [soxl[940]["date"], soxl[998]["date"]] and eps[0]["marked_sessions"] == 2 and eps[1]["end"] == soxl[999]["date"],
        f"daily view episodes: the planted spikes at sessions 940–941 and 998–999 → {[(e['start'], e['end']) for e in eps]}")
  check(all(bars_d[e["first_bar"]]["date"] == e["start"] and bars_d[e["last_bar"]]["date"] == e["end"] and bars_d[e["anchor_bar"]]["date"] == e["peak_date"] and e["peak_vix"] == 40.0 for e in eps), "episode bar positions point at the right bars")
  check([m["date"] for m in vd["crash_drops"]] == [soxl[k]["date"] for k in (890, 940, 995)] and all(bars_d[m["bar"]]["date"] == m["date"] for m in vd["crash_drops"]), "crash-drop markers in the daily view are the event-study episodes in view, on their own bars")
  bars_w = w[-104:]
  check([m["date"] for m in vw["crash_drops"]] == [soxl[k]["date"] for k in (600, 890, 940, 995)] and all(bars_w[m["bar"]]["start"] <= m["date"] <= bars_w[m["bar"]]["end"] for m in vw["crash_drops"]), "weekly view markers sit on the week that holds their date")
  check(all(bars_w[e["first_bar"]]["start"] <= e["start"] <= bars_w[e["first_bar"]]["end"] and bars_w[e["last_bar"]]["start"] <= e["end"] <= bars_w[e["last_bar"]]["end"] and bars_w[e["anchor_bar"]]["spike"] for e in vw["spikes"]["episodes"]) and [e["start"] for e in vw["spikes"]["episodes"]] == [soxl[700]["date"], soxl[940]["date"], soxl[998]["date"]],
        "weekly view episodes (700 with 705 joined, 940, 998) map to the weeks that hold them; the one at 400 is outside the view")
  check(vd["channel"] == sc.trend_channel([b["close"] for b in bars_d]) and vw["channel"] == sc.trend_channel([b["close"] for b in bars_w]), "the channel of a view is computed from the bars in view only")
  check(vd["profile"] == {"rule": "volume_profile_daily", **sc.volume_profile(bars_d, spacing="equal_width")} and vw["profile"] == {"rule": "volume_profile_weekly", **sc.volume_profile(bars_w, spacing="equal_ratio")} and vd["profile"]["available"],
        "the volume profile of a view is computed from the bars in view only: equal width on the daily view, equal ratio on the weekly view")
  lt = blk["latest"]
  check(lt["date"] == d[-1]["date"] and lt["vix"]["same_session"] is True and lt["vix"]["spike"] is True and lt["session_spike"] is True and lt["spike_episode"] == {"start": soxl[998]["date"], "marked_sessions": 2}, "latest: the last session is a spike, in an episode that began one session earlier")
  check(lt["volume_vs_avg"] in ("above", "below", "equal") and close(lt["volume_ratio"], round(d[-1]["volume"] / d[-1]["vol_avg20"], 2)) and lt["vix"]["threshold"] == round(lt["vix"]["median_prev"] * 1.4, 2), "latest: volume against its average, VIX against its threshold")
  # rules and legend
  rl, lg = blk["rules"], blk["legend"]
  check(set(rl) == {"vix_spike", "trend_channel", "weekly_bars", "volume_profile_daily", "volume_profile_weekly"} and all(isinstance(r["params"], dict) and isinstance(r["text_zh"], str) and "\n" not in r["text_zh"] and len(r["text_zh"]) <= 130 for r in rl.values()),
        "five rules (the volume profile has one per view), each with parameters and one line of text")
  check(vd["rules"] == ["vix_spike", "trend_channel", "volume_profile_daily"] and vw["rules"] == ["weekly_bars", "vix_spike", "trend_channel", "volume_profile_weekly"] and all(k in rl for k in vd["rules"] + vw["rules"]) and vd["profile"]["rule"] in vd["rules"] and vw["profile"]["rule"] in vw["rules"],
        "each view lists the rules its own legend prints, and its profile names its rule")
  check("60" in rl["vix_spike"]["text_zh"] and "1.4" in rl["vix_spike"]["text_zh"] and "中位數" in rl["vix_spike"]["text_zh"] and "5" in rl["vix_spike"]["text_zh"] and rl["vix_spike"]["params"]["lookback_sessions"] == 60 and rl["vix_spike"]["params"]["multiple"] == 1.4,
        "the spike line names the lookback, the median, the multiple and the gap")
  check(all(x in rl["trend_channel"]["text_zh"] for x in ("自然對數", "最小平方", "2 倍", "0.5", "30")) and all(x in rl["volume_profile_daily"]["text_zh"] for x in ("24", "等分", "÷3", "同量")) and all(x in rl["volume_profile_weekly"]["text_zh"] for x in ("24", "等比", "÷3", "同量")) and all(x in rl["weekly_bars"]["text_zh"] for x in ("ISO", "20 週")),
        "the channel, weekly and both profile lines carry their parameters; each profile line states the tie-break")
  check(rl["volume_profile_daily"]["params"]["spacing"] == "equal_width" and rl["volume_profile_weekly"]["params"]["spacing"] == "equal_ratio" and rl["volume_profile_daily"]["text_zh"] != rl["volume_profile_weekly"]["text_zh"], "the two profile rules differ in band spacing")
  check(is_one_zh_line(lg["no_spike_in_view_zh"]) and is_one_zh_line(lg["no_channel_zh"]) and is_one_zh_line(lg["no_vix_zh"]) and is_one_zh_line(lg["no_crash_zh"]) and "5" in lg["crash_drop_zh"] and "20%" in lg["crash_drop_zh"], "legend lines for no spike, no channel, missing series and the crash-drop marker")
  check([x["value"] for x in lg["crash_lines"]] == [60, 80] and early_warning.zone(59.9).startswith("低風險") and early_warning.zone(60).startswith(lg["crash_lines"][0]["label_zh"]) and early_warning.zone(80).startswith(lg["crash_lines"][1]["label_zh"]),
        "crash index lines at 60 and 80 carry the zone names of early_warning.zone")
  # evidence on the synthetic history
  ev = blk["evidence"]
  spike, cr = ev["conditions"]
  ds = [r["date"] for r in soxl]
  check(ev["available"] and ev["horizons"] == [5, 10, 20] and ev["default_horizon"] == 10 and ev["price_history"] == {"symbol": "SOXL", "start": ds[0], "end": ds[-1], "sessions": 1000}, "evidence header")
  check(spike["key"] == "vix_spike_start" and spike["sample"]["start"] == ds[66] and spike["start_dates"] == [ds[400], ds[700], ds[940], ds[998]], f"spike condition: sample from the 67th session; episodes start at 400, 700 (705 joins), 940, 998 → {spike['start_dates']}")
  f5 = spike["figures"][0]
  want = [(soxl[k + 5]["close"] / soxl[k + 1]["open"] - 1.0) * 100.0 for k in (400, 700, 940)]
  check(f5["horizon"] == 5 and f5["episode_dates"] == [ds[400], ds[700], ds[940]] and f5["open_dates"] == [ds[998]] and close(f5["median_ret_pct"], statistics.median(want), 1e-6) and f5["wins"] == sum(1 for x in want if x > 0) and f5["small_sample"],
        "spike condition, 5 sessions: three counted episodes, the last one still open, median from raw prices")
  scores = {x["date"]: x["score"] for x in crash}
  rises = [dt for a, dt in zip(ds[205:], ds[206:]) if scores[dt] >= 80 > scores[a]]
  check(cr["key"] == "crash_ge80" and cr["sample"]["start"] == ds[206] and cr["start_dates"] == rises and len(rises) >= 5 and is_one_zh_line(cr["note_zh"]), f"crash condition: sample from the second scored session, {len(rises)} rises to 80 or more")
  check(all(fig["base"]["n"] == 1000 - 206 - fig["horizon"] for fig in cr["figures"]) and all(all(b >= a for a, b in zip(fig["episode_dates"], fig["episode_dates"][1:])) for fig in cr["figures"]), "crash condition: base rate over every scored session that has an exit")
  older = sc.table_dicts(ev["crash_before_daily"])
  check(len(older) == 145 and older == [x for x in crash if x["date"] < d[0]["date"]] and sc.crash_history(blk) == crash, f"the {len(older)} crash readings before the daily table are stored, so crash_history() rebuilds the whole scored series")
  check(ev["event_study"]["stats_all_80"] == ews["event_study"]["stats_all_80"] and ev["event_study"]["drop_pct"] == -20.0 and is_one_zh_line(ev["convention"]["text_zh"]), "event-study figures are carried unchanged; the convention has one line of text")
  long = sc.build(soxl[-300:], vix, crash, ews, soxl_long=soxl, final=True)
  check(long["evidence"]["price_history"]["sessions"] == 1000 and long["evidence"]["conditions"][0]["start_dates"] == spike["start_dates"] and sc.merge_history(soxl, soxl[-300:]) == soxl and sc.merge_history(None, soxl[-3:]) == soxl[-3:],
        "a longer history is put in front of the model history for the evidence strip")
  tail = sc.build(soxl, vix[-800:], crash, ews, soxl_long=None, final=True)
  check(tail["vix"] == blk["vix"] and tail["daily"]["spike"] == blk["daily"]["spike"] and tail["views"]["daily"]["spikes"] == vd["spikes"] and tail["views"]["weekly"]["spikes"] == vw["spikes"]
        and tail["latest"] == blk["latest"] and (tail["spike_stats"]["sessions"], blk["spike_stats"]["sessions"]) == (800, len(vix)),
        "a shorter loaded VIX history (the pipeline's fallback) stores the same VIX rows, flags and episodes; only the statistics cover fewer sessions")
  check(sc.block_bytes(blk) < 200_000 and "KB" in sc.describe(blk), f"block is {sc.block_bytes(blk)} bytes of compact JSON")

  # ---- variants
  def rows_for(k: int) -> list[dict]:
    return [{**r, "vol_avg20": 1_000_000, "crash": 50.0} for r in sc.daily_rows(soxl, {})[-k:]]

  calm = sc.assemble(rows_for(120), [{"date": r["date"], "close": 15.0} for r in vix], [], None, with_weekly=False)
  cs = calm["views"]["daily"]["spikes"]
  check(cs["status"] == "none" and cs["episodes"] == [] and cs["text_zh"] == lg["no_spike_in_view_zh"] and calm["latest"]["session_spike"] is False, f"a view with no spike says so: {cs['text_zh']}")
  hot = sc.assemble(rows_for(120), [{"date": r["date"], "close": round(10.0 * 1.02 ** i, 4)} for i, r in enumerate(vix)], [], None, with_weekly=False)
  hs = hot["views"]["daily"]["spikes"]
  check(hs["status"] == "ok" and len(hs["episodes"]) == 1 and hs["episodes"][0]["marked_sessions"] == 120 and (hs["episodes"][0]["first_bar"], hs["episodes"][0]["last_bar"]) == (0, 119), "a view where every session is a spike is one episode over all 120 bars")
  novix = sc.assemble(rows_for(120), [], [], None, with_weekly=False)
  nv = novix["views"]["daily"]
  check(nv["spikes"]["status"] == "no_vix" and nv["series"]["vix"] is False and lg["no_vix_zh"] in nv["missing_zh"] and nv["channel"]["available"] is not None and novix["latest"]["vix"] is None and novix["vix"]["n"] == 0,
        f"missing VIX history: no flags, and one line names the source: {nv['spikes']['text_zh']}")
  shortvix = sc.assemble(rows_for(120), vix[-40:], [], None, with_weekly=False)
  check(shortvix["views"]["daily"]["spikes"]["status"] == "too_short" and is_one_zh_line(shortvix["views"]["daily"]["spikes"]["text_zh"]), "a VIX history shorter than the lookback cannot be judged, and says so")
  nocrash = sc.assemble([{**r, "crash": None} for r in rows_for(120)], vix, [], None, with_weekly=False)
  check(nocrash["views"]["daily"]["series"]["crash"] is False and lg["no_crash_zh"] in nocrash["views"]["daily"]["missing_zh"] and nocrash["latest"]["crash"] is None, "a missing crash index is named in one line")
  few = sc.assemble(rows_for(12), vix, ews["event_study"]["episodes"], None, with_weekly=False)
  fv = few["views"]["daily"]
  check(fv["bars"] == 12 and not fv["channel"]["available"] and fv["channel"]["reason"] == "too_few_bars" and is_one_zh_line(fv["channel"]["text_zh"]) and fv["profile"]["available"], f"fewer than 30 bars: {fv['channel']['text_zh']}; the volume profile is still computed")
  check(not few["views"]["weekly"]["available"] and "12" in few["views"]["weekly"]["text_zh"] and is_one_zh_line(few["views"]["weekly"]["text_zh"]), f"no weekly view: {few['views']['weekly']['text_zh']}")
  lag = sc.assemble(rows_for(120), vix[:-1], [], None, with_weekly=False)
  check(lag["latest"]["session_spike"] is None and lag["latest"]["vix"]["same_session"] is False and lag["latest"]["vix"]["date"] == ds[-2] and lag["daily"]["vix"][-1] is None, "when the VIX close of the last session is not in yet, the last session has no flag and latest.vix names the earlier date")
  part = sc.assemble(rows_for(650), vix, [], None, final=False)
  check(part["views"]["weekly"]["last_bar_partial"] is True and part["weekly"]["partial"][-1] is True and sum(part["weekly"]["partial"]) == 1 and "還沒走完" in part["views"]["weekly"]["last_bar_text_zh"] and part["data_final"] is False,
        f"a last session that is not final makes the last weekly bar partial: {part['views']['weekly']['last_bar_text_zh']}")
  nothing = sc.assemble([], vix, [], None)
  check(nothing["available"] is False and nothing["reason"] == "no_bars" and is_one_zh_line(nothing["text_zh"]) and nothing["views"]["daily"]["available"] is False and nothing["daily"]["n"] == 0, f"no bars at all: {nothing['text_zh']}")
  no_ev = sc.evidence(soxl, [], [], None)
  check(no_ev["available"] is False and is_one_zh_line(no_ev["text_zh"]) and all(c["available"] is False and is_one_zh_line(c["text_zh"]) for c in no_ev["conditions"]), "evidence without VIX and without a crash index: each condition names what is missing")


def test_for_payload() -> None:
  print("10. for_payload")
  soxl, vix, crash, ews = synthetic_history()
  blk = sc.build(soxl, vix, crash, ews, final=True)
  chart_series = [{"date": r["date"], "open": round(r["open"], 2), "high": round(r["high"], 2), "low": round(r["low"], 2), "close": round(r["close"], 2), "volume": r["volume"],
                   "vol_sma20": blk["daily"]["vol_avg20"][len(blk["daily"]["date"]) - 120 + i], "sma20": 1.0} for i, r in enumerate(soxl[-120:])]
  payload = {"technicals": {"chart_series": chart_series}, "sentiment": {"vix": {"available": True, "history": [{"date": r["date"], "vix": r["close"], "vix3m": 20.0} for r in vix[-260:]]}},
             "early_warning": ews, "data_status": {"final": True}, "stress_chart": blk}
  check(sc.for_payload(payload) is blk, "a payload with the block returns the block")
  bare = {k: v for k, v in payload.items() if k != "stress_chart"}
  red = sc.for_payload(bare)
  check(red["available"] and red["source"] == "reduced" and red["schema"] == sc.SCHEMA and red["daily"]["n"] == 120 and red["weekly"]["n"] == 0, "a payload without the block returns a reduced block of 120 sessions")
  rb, bb = sc.view_bars(red, "daily"), sc.view_bars(blk, "daily")
  rv, bv = red["views"]["daily"], blk["views"]["daily"]
  check((len(rb), len(bb)) == (120, 126) and rb == bb[-120:], "the reduced daily view holds the latest 120 of the block's 126 bars: the same prices, VIX, crash index and spike flags")
  check((rv["rules"], rv["series"]) == (bv["rules"], bv["series"]) and [(m["date"], m["bar"] + 6) for m in rv["crash_drops"]] == [(m["date"], m["bar"]) for m in bv["crash_drops"]]
        and [(e["start"], e["end"], e["anchor_bar"] + 6) for e in rv["spikes"]["episodes"]] == [(e["start"], e["end"], e["anchor_bar"]) for e in bv["spikes"]["episodes"]],
        "its rules, series, markers and spike episodes are the block's (no marker or spike sits in the 6 sessions it lacks), 6 bar positions earlier")
  check(rv["channel"] == sc.trend_channel([b["close"] for b in rb]) and rv["profile"] == {"rule": "volume_profile_daily", **sc.volume_profile(rb, spacing="equal_width")}
        and rv["channel"] != bv["channel"] and rv["profile"] != bv["profile"], "its channel and profile are computed from its own 120 bars, so they differ from the block's")
  rw, re_ = red["views"]["weekly"], red["evidence"]
  check(rw["available"] is False and is_one_zh_line(rw["text_zh"]) and re_["available"] is False and is_one_zh_line(re_["text_zh"]), f"weekly view and evidence strip are unavailable, one line each: {rw['text_zh']} / {re_['text_zh']}")
  check(red["spike_stats"]["scope"] == "stored_vix_rows" and red["spike_stats"]["sessions"] == 260 and red["spike_stats"]["within_cap"] is None and sc.view_bars(red, "weekly") == [], "reduced spike statistics cover the stored rows only")
  check(sc.for_payload({**bare, "stress_chart": {}})["source"] == "reduced" and sc.for_payload({**bare, "stress_chart": {"schema": "other", "available": True}})["source"] == "reduced", "an empty or foreign block falls back to the reduced block")
  early = {k: v for k, v in bare.items() if k != "data_status"}
  check(sc.for_payload(early)["available"] and sc.for_payload(early)["data_final"] is True, "a payload without data_status still builds")
  for junk in (None, {}, {"technicals": None}, {"technicals": {"chart_series": [{"date": "2026-01-02"}, None, 5]}}, {"technicals": {"chart_series": "x"}}, {"sentiment": {"vix": {"history": [1, "a", {}]}}, "technicals": {"chart_series": chart_series[:5]}},
               "x", 5, [1], ("a", "b"), {"stress_chart": "x"}, {"stress_chart": {"schema": sc.SCHEMA, "available": True, "daily": "x"}}, {"stress_chart": {"schema": sc.SCHEMA, "available": True, "daily": [1]}}):
    out = sc.for_payload(junk)
    ok = isinstance(out, dict) and out["schema"] == sc.SCHEMA and set(out["views"]) == {"daily", "weekly"} and (out["available"] or is_one_zh_line(out.get("text_zh")))
    check(ok, f"junk payload {str(junk)[:48]!r} → {'reduced block' if out['available'] else out.get('reason')}, no exception")
  novix = copy.deepcopy(bare)
  novix["sentiment"] = {"vix": {"available": False}}
  check(sc.for_payload(novix)["views"]["daily"]["spikes"]["status"] == "no_vix", "a payload without VIX history builds, and its view says the VIX source is missing")
  empty = sc.for_payload({})
  check(empty["available"] is False and empty["reason"] == "no_bars" and set(empty) == set(blk) | {"reason", "text_zh"}
        and (empty["symbol"], empty["as_of"], empty["data_final"], empty["latest"], empty["spike_stats"]) == ("SOXL", None, None, None, None),
        "an unavailable block has every top-level key of an available block, plus reason and text_zh")
  real_reduced = sc.build_reduced

  def _boom(payload):  # noqa: ARG001 - stands in for a bug in the reduced build
    raise RuntimeError("planted failure")

  sc.build_reduced = _boom
  try:
    err = sc.for_payload(bare)
  finally:
    sc.build_reduced = real_reduced
  check(err["available"] is False and err["reason"] == "error" and err["error"] == "RuntimeError: planted failure" and is_one_zh_line(err["text_zh"]) and set(err) == set(empty) | {"error"},
        f"an exception inside the reduced build is caught: the block says so in one line ({err['text_zh']}) and keeps the exception under 'error'")


def load_payload(path: Path) -> dict:
  raw = gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
  return json.loads(raw.decode("utf-8"))


def test_stored_payloads(extra: list[str]) -> None:
  print("11. stored payloads")
  paths = [REPO / "soxl_analysis_data.json"] + sorted((REPO / "history" / "snapshots").glob("*.json.gz"))
  for x in extra:
    p = Path(x)
    paths += sorted(list(p.glob("*.json")) + list(p.glob("*.json.gz")) + list(p.glob("**/snapshots/*.json.gz"))) if p.is_dir() else [p]
  paths = [p for p in paths if p.exists()]
  check(len(paths) >= 1, f"{len(paths)} stored payload(s) found")
  n_block = n_reduced = 0
  bad: list[str] = []
  for p in paths:
    try:
      payload = load_payload(p)
      blk = sc.for_payload(payload)
      name = p.name
      has_block = blk.get("source") == "pipeline"
      bare = {k: v for k, v in payload.items() if k != "stress_chart"}
      red = sc.for_payload(bare)
      for b in (blk, red):
        vd = b["views"]["daily"]
        if not (b["available"] and vd["available"] and 110 <= vd["bars"] <= 130 and vd["profile"]["available"] and "available" in vd["channel"] and vd["spikes"]["status"] in ("ok", "none")):
          bad.append(f"{name}: daily view incomplete")
        if any(len(b[t][c]) != b[t]["n"] for t in ("daily", "vix", "weekly") for c in b[t]["columns"]):
          bad.append(f"{name}: ragged table")
        if [x for x in b["vix"]["spike"]] != sc.spike_marks(b["vix"]["close"]):
          bad.append(f"{name}: stored spike flags differ from the rule on the stored series")
      if not (red["views"]["weekly"]["available"] is False and is_one_zh_line(red["views"]["weekly"]["text_zh"]) and red["evidence"]["available"] is False and is_one_zh_line(red["evidence"]["text_zh"])):
        bad.append(f"{name}: reduced block lacks the unavailable lines")
      chart = {x["date"]: x["score"] for x in (payload.get("early_warning") or {}).get("chart") or []}
      rd = sc.table_dicts(red["daily"])
      if any(chart.get(r["date"]) != r["crash"] for r in rd):
        bad.append(f"{name}: reduced crash index differs from early_warning.chart")
      eps_in_view = [e["date"] for e in ((payload.get("early_warning") or {}).get("event_study") or {}).get("episodes") or [] if rd and rd[0]["date"] <= e["date"] <= rd[-1]["date"]]
      if [m["date"] for m in red["views"]["daily"]["crash_drops"]] != eps_in_view:
        bad.append(f"{name}: crash-drop markers differ from the event-study episodes in view")
      if has_block:
        n_block += 1
        d, w = sc.table_dicts(blk["daily"]), sc.table_dicts(blk["weekly"])
        rb, bb = sc.view_bars(red, "daily"), sc.view_bars(blk, "daily")
        checks = {
            "the reduced daily view holds the latest bars of the block's daily view": 0 < len(rb) <= len(bb) and rb == bb[-len(rb):] and red["views"]["daily"]["rules"] == blk["views"]["daily"]["rules"],
            "crash index equals early_warning.chart on shared dates": all(dict((r["date"], r["crash"]) for r in d).get(k) == s for k, s in chart.items()) and len(chart) > 0,
            "weekly bars rebuild from the daily series": w == sc.weekly_bars(d, blk["data_final"]),
            "at least 640 daily sessions, first one starts a week": len(d) >= 640 and starts_week(d[0]["date"]),
            "daily view 126 sessions, weekly view 104 weeks": blk["views"]["daily"]["bars"] == 126 and blk["views"]["weekly"]["bars"] == 104,
            "spike rule marks at most 10% of the loaded VIX history": blk["spike_stats"]["scope"] == "loaded_vix_history" and blk["spike_stats"]["share_pct"] <= 10.0 and blk["spike_stats"]["within_cap"] is True,
            "block under 200 KB (compact and indented)": sc.block_bytes(blk) < 200_000 and len(json.dumps(blk, ensure_ascii=False, indent=1).encode("utf-8")) < 200_000,
            "every evidence figure has base rate, count, period and small-sample flag": all(f["base"]["n"] > 0 and f["period"] and f["small_sample"] == (f["n"] < 20) for c in blk["evidence"]["conditions"] if c.get("available") for f in c["figures"]),
            "crash_history covers the crash evidence sample": [x["date"] for x in sc.crash_history(blk)][1] == blk["evidence"]["conditions"][1]["sample"]["start"],
        }
        for label, ok in checks.items():
          if not ok:
            bad.append(f"{name}: {label}")
        if p == paths[0]:
          for label, ok in checks.items():
            check(ok, f"{name}: {label}")
          st = blk["spike_stats"]
          print(f"       {name}: {sc.describe(blk)}")
          print(f"       spike share {st['share_pct']}% of {st['sessions']} sessions, {st['first_date']} to {st['last_date']}, {st['episodes']} episodes")
      else:
        n_reduced += 1
    except Exception as e:  # noqa: BLE001
      bad.append(f"{p.name}: {type(e).__name__}: {e}")
  check(not bad, f"{len(paths)} payloads served without exception ({n_block} with the block, {n_reduced} reduced)" + (f"; problems: {bad[:6]}" if bad else ""))


def main() -> int:
  print("test_stress_chart")
  test_spike_rule()
  test_no_repaint()
  test_episodes_and_stats()
  test_weekly_bars()
  test_partial_week()
  test_channel()
  test_volume_profile()
  test_evidence_figures()
  test_small_rules()
  test_block()
  test_for_payload()
  test_stored_payloads([a for a in sys.argv[1:] if not a.startswith("--")])
  print("FAILURES:" if FAILS else "ALL PASS", len(FAILS))
  return 1 if FAILS else 0


if __name__ == "__main__":
  sys.exit(main())
