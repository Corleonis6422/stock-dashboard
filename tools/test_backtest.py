#!/usr/bin/env python3
"""Unit tests for soxl_quant/backtest.py — no network, synthetic series only.

Run: .venv/bin/python tools/test_backtest.py

Covers
  1. no lookahead: every rule gives the same value on a truncated context rows[:i+1] as on the full one
  2. de-clustering: an always-on signal produces non-overlapping trades spaced >= horizon bars apart
  3. known outcomes: a monotonic up-trend makes every long trade a winner and every exit trade a loser;
     a monotonic down-trend does the reverse
  4. statistics: Wilson CI, exact binomial p and Benjamini-Hochberg q against hand-computed values
  5. trigger prices: the SMA20 crossing close and the RSI threshold close reproduce the rule boundary
  6. dynamic-exit base rate and dd15 base are computed once per context and are bounded
  7. regime test on an external series: position follows the external SMA200, not SOXL's own
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from soxl_quant import backtest as bt  # noqa: E402
from soxl_quant import indicators as ind  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
  print(("  ok   " if cond else "  FAIL ") + msg)
  if not cond:
    FAILS.append(msg)


def synth_rows(n: int = 700, seed: int = 11, drift: float = 0.0, vol: float = 0.03, start: float = 50.0) -> list[dict]:
  rnd = random.Random(seed)
  rows = []
  px = start
  for k in range(n):
    r = drift + rnd.gauss(0.0, vol)
    o = px * (1 + rnd.gauss(0.0, vol / 3))
    c = max(0.5, px * (1 + r))
    h = max(o, c) * (1 + abs(rnd.gauss(0.0, vol / 2)))
    lo = min(o, c) * (1 - abs(rnd.gauss(0.0, vol / 2)))
    rows.append({"date": f"2020-{(k // 28) % 12 + 1:02d}-{k % 28 + 1:02d}" if False else f"D{k:05d}", "open": round(o, 4), "high": round(h, 4), "low": round(lo, 4), "close": round(c, 4), "volume": int(1e6 * (1 + abs(rnd.gauss(0, 0.5))))})
    px = c
  return rows


def trend_rows(n: int = 600, step: float = 0.01) -> list[dict]:
  rows = []
  px = 20.0
  for k in range(n):
    o = px
    c = px * (1 + step)
    rows.append({"date": f"T{k:05d}", "open": round(o, 4), "high": round(max(o, c) * 1.001, 4), "low": round(min(o, c) * 0.999, 4), "close": round(c, 4), "volume": 1_000_000 + (k % 7) * 50_000})
    px = c
  return rows


def main() -> int:
  print("test_backtest")
  rows = synth_rows()
  vix = {r["date"]: 15.0 + 10.0 * math.sin(k / 9.0) for k, r in enumerate(rows)}
  vix3m = {r["date"]: 17.0 + 6.0 * math.sin(k / 11.0) for k, r in enumerate(rows)}
  ctx = bt.build_context(rows, vix, vix3m)
  lib = [s for s in bt.signal_library() if "ews" not in s["needs"]]

  # 1. lookahead
  rnd = random.Random(3)
  probes = sorted(rnd.sample(range(bt.WARMUP + 5, len(rows) - 2), 25))
  mism = []
  for i in probes:
    tctx = bt.build_context(rows[: i + 1], vix, vix3m)
    for s in lib:
      try:
        a = bool(s["fn"](ctx, i))
      except (IndexError, TypeError, ZeroDivisionError):
        a = None
      try:
        b = bool(s["fn"](tctx, i))
      except (IndexError, TypeError, ZeroDivisionError):
        b = None
      if a != b:
        mism.append((s["key"], i))
  check(not mism, f"no lookahead across {len(probes)} bars × {len(lib)} rules" + (f" (mismatches {mism[:5]})" if mism else ""))

  # 2. de-clustering
  for h in (5, 10, 20):
    tr = bt._trades(ctx, lambda _c, _i: True, h, bt.WARMUP, ctx["n"])
    gaps = [tr[k + 1]["i"] - tr[k]["i"] for k in range(len(tr) - 1)]
    check(gaps and min(gaps) >= h, f"always-on signal h={h}: min gap {min(gaps) if gaps else None} >= {h}, N={len(tr)}")
    expect = (ctx["n"] - bt.WARMUP + h - 1) // h
    check(abs(len(tr) - expect) <= 1, f"always-on signal h={h}: N {len(tr)} ≈ {expect}")

  # 3. known outcomes
  up = trend_rows(600, 0.01)
  ctx_up = bt.build_context(up)
  res_up = {r["key"]: r for r in bt.run(up)["signals"]}
  longs_fired = [k for k, r in res_up.items() if r["side"] == "long" and r["n"] > 0]
  exits_fired = [k for k, r in res_up.items() if r["side"] == "exit" and r["n"] > 0]
  check(all(res_up[k]["win_pct"] == 100.0 for k in longs_fired), f"up-trend: every long trade wins ({longs_fired})")
  check(all(res_up[k]["win_pct"] == 0.0 for k in exits_fired), f"up-trend: every exit trade loses ({exits_fired})")
  base_up = next(iter(res_up.values()))["base"]["win_pct"]
  check(base_up == 100.0, f"up-trend long base rate 100 (got {base_up})")
  down = trend_rows(600, -0.01)
  res_dn = {r["key"]: r for r in bt.run(down)["signals"]}
  longs_dn = [k for k, r in res_dn.items() if r["side"] == "long" and r["n"] > 0]
  check(all(res_dn[k]["win_pct"] == 0.0 for k in longs_dn), f"down-trend: every long trade loses ({longs_dn})")
  check(ctx_up["c"][-1] > ctx_up["c"][0], "sanity: trend rows rise")

  # 4. statistics
  lo, hi = bt.wilson_ci(40, 62)
  check(abs(lo - 52.1) < 0.1 and abs(hi - 75.3) < 0.1, f"Wilson 40/62 = [{lo},{hi}] (expect [52.1,75.3])")
  lo0, hi0 = bt.wilson_ci(0, 10)
  check(lo0 == 0.0 and abs(hi0 - 27.8) < 0.1, f"Wilson 0/10 = [{lo0},{hi0}] (expect [0,27.8])")
  p = bt.binom_p_greater(40, 62, 0.554)
  check(p is not None and abs(p - 0.0932) < 0.002, f"binomial P(X>=40 | 62, .554) = {p} (expect 0.093)")
  p2 = bt.binom_p_greater(20, 24, 0.573)
  check(p2 is not None and abs(p2 - 0.0067) < 0.002, f"binomial P(X>=20 | 24, .573) = {p2} (expect 0.007)")
  q = bt.bh_qvalues([0.01, 0.04, 0.03, None, 0.20])
  # sorted p = .01 .03 .04 .20 (m=4): q4=.20, q3=min(.20,.04*4/3)=.0533, q2=min(.0533,.03*4/2)=.0533, q1=min(.0533,.01*4)=.04
  check(q[3] is None and q[0] == 0.04 and q[1] == 0.0533 and q[2] == 0.0533 and q[4] == 0.2, f"BH q-values {q} (expect [0.04,0.0533,0.0533,None,0.2])")
  check(bt._grade(62, 27, 62.9, 66.7, 55.4, 1.83, True, 0.093)[0] == "B", "grade: 64.5% vs 55.4% with p=0.093 is B, not A")
  check(bt._grade(62, 27, 62.9, 66.7, 55.4, 1.83, True, 0.01)[0] == "A", "grade: same signal with p=0.01 is A")
  check(bt._grade(24, 7, 76.5, 100.0, 57.3, 6.7, True, 0.0067)[0] == "B*", "grade: significant but OOS N=7 is B*")
  check(bt._grade(24, 7, 76.5, 100.0, 57.3, 6.7, True, 0.3)[0] == "—", "grade: not significant and OOS N=7 is 樣本不足")

  # 5. trigger prices
  c_trig = bt._sma20_tomorrow_cross(ctx)
  s20_next = ind.sma(ctx["c"] + [c_trig], 20)[-1]
  check(abs(s20_next - c_trig) < 1e-6, f"SMA20 crossing close {c_trig:.4f} equals tomorrow's SMA20 {s20_next:.4f}")
  r_trig = bt._rsi_threshold_close(ctx, 2, 10.0)
  rsi_at = ind.rsi(ctx["c"] + [r_trig], 2)[-1]
  rsi_above = ind.rsi(ctx["c"] + [r_trig + 0.01], 2)[-1]
  check(rsi_at <= 10.0 + 1e-6 and rsi_above > 10.0 - 1e-6, f"RSI(2) threshold close {r_trig:.4f}: RSI at close {rsi_at:.3f} <= 10 < {rsi_above:.3f} one cent higher")

  # 6. dynamic base + dd15 base
  db = bt._dyn_base(ctx, bt.WARMUP, ctx["n"])
  check(db["n"] > 50 and 0 < db["win_pct"] < 100, f"dynamic-exit base computed: N={db['n']} win={db['win_pct']}%")
  check(bt._dyn_base(ctx, bt.WARMUP, ctx["n"]) is db, "dynamic-exit base cached on the context")
  d15 = bt._dd15_base(ctx, bt.WARMUP, ctx["n"])
  check(d15 is not None and 0 <= d15 <= 100, f"dd15 base = {d15}%")

  # 7. regime on an external series: build a series that is always above its SMA200 while SOXL is in a down-trend
  dn = trend_rows(600, -0.005)
  ctx_dn = bt.build_context(dn)
  ext = {r["date"]: 100.0 * (1.002 ** k) for k, r in enumerate(dn)}
  own = bt.regime_test(ctx_dn, 0.0)
  ex = bt.regime_test(ctx_dn, 0.0, 1, ext, "EXT")
  check(own["time_in_market_pct"] == 0 and ex["time_in_market_pct"] == 100, f"regime: own-series out 100% ({own['time_in_market_pct']}% in), external series in 100% ({ex['time_in_market_pct']}% in)")
  check(ex["today"]["in_market"] and not own["today"]["in_market"], "regime today: external IN, own OUT")
  check(ex["strategy"]["final_multiple"] == ex["buy_hold"]["final_multiple"], "regime: always-in equals buy and hold")

  # 8. full run shape
  out = bt.run(rows, vix, vix3m, underlying_rows=[{"date": r["date"], "close": r["close"] * 1.01} for r in rows])
  check(len(out["regime"]["grid"]) == 7, f"regime grid has 7 rows ({len(out['regime']['grid'])})")
  check(all("q_value" in r and "p_value" in r and "short_name" in r for r in out["signals"]), "every signal carries p_value, q_value, short_name")
  check(all(len(r["short_name"]) <= 12 for r in out["signals"]), "short_name <= 12 chars")
  check("dyn_base_win_pct" in out["summary"], "summary has dyn_base_win_pct")

  print("FAILURES:" if FAILS else "ALL PASS", len(FAILS))
  return 1 if FAILS else 0


if __name__ == "__main__":
  sys.exit(main())
