#!/usr/bin/env python3
"""Verdict history — what the daily auto-update accumulates over time.

* ``history/verdicts.jsonl``   one compact record per trading day (verdict,
  composite score, rating, position cap, key sentiment / flow readings).  A
  re-run on the same ``data_as_of`` date replaces that day's record, so an
  intraday run followed by the post-close run never duplicates a day.
* ``history/snapshots/``       gzip'd copies of the full JSON payload (kept for
  ``SNAP_KEEP`` days) so any past dashboard can be re-rendered or back-tested.
* forward-return self-check    every append back-fills ``fwd_ret_5d`` /
  ``fwd_ret_10d`` for older records from the price series, so the beginner page
  can honestly show "what happened after each verdict" once enough days exist.
* ``technical_lights``         a *price-only* traffic light for the last 120
  days (close vs 20/50/200 MA, MACD histogram, RSI 50-line, SuperTrend) that can
  be back-filled from history — the full model needs options / sentiment data
  that only exists from the day the daily log starts.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from .fsio import atomic_write_bytes, atomic_write_text

BASE_DIR = Path(__file__).resolve().parent.parent
HIST_DIR = BASE_DIR / "history"
LOG_PATH = HIST_DIR / "verdicts.jsonl"
SNAP_DIR = HIST_DIR / "snapshots"
SNAP_KEEP = 180


def _num(v, nd: int = 2):
  try:
    return None if v is None else round(float(v), nd)
  except (TypeError, ValueError):
    return None


def record_from_payload(p: dict) -> dict:
  tech = p.get("technicals") or {}
  sc = p.get("scoring") or {}
  pb = p.get("playbook") or {}
  b = pb.get("beginner") or {}
  cons = sc.get("consensus") or {}
  sen = p.get("sentiment") or {}
  fg = sen.get("fear_greed") or {}
  vx = sen.get("vix") or {}
  opt = p.get("options") or {}
  ews = (p.get("early_warning") or {}).get("today") or {}
  tp = p.get("trade_plan") or {}
  return {
      "date": p.get("data_as_of"), "generated_at": p.get("generated_at"),
      "close": _num(tech.get("close")), "ret_1d": _num(tech.get("ret_1d")),
      "composite": _num(sc.get("composite_score")), "trend": _num(sc.get("trend_score")), "contrarian": _num(sc.get("contrarian_score")),
      "rating_5": sc.get("rating_5"), "rating_label": sc.get("rating_label"),
      "verdict": b.get("verdict"), "color": b.get("color"), "emoji": b.get("emoji"),
      "size_pct": b.get("size_pct"),
      "checklist_passed": pb.get("checklist_passed"), "checklist_total": pb.get("checklist_total"),
      "crash_risk": _num(ews.get("score"), 0),
      "fear_greed": _num(fg.get("score"), 1), "vix": _num(vx.get("vix"), 2),
      "pc_vol": _num(opt.get("pc_vol_ratio")), "whale_net": _num((opt.get("whale") or {}).get("whale_net_score")),
      "sell_pct": _num(cons.get("sell_pct"), 1), "hold_pct": _num(cons.get("hold_pct"), 1), "buy_pct": _num(cons.get("buy_pct"), 1),
      "confidence": sc.get("confidence"),
      "final": bool((p.get("data_status") or {}).get("final", True)), "provisional": bool((p.get("data_status") or {}).get("provisional", False)),
      # v3: the explicit plan, so later runs can score it (did price reach T1 before the stop?)
      "plan_side": tp.get("side"), "plan_entry": _num((tp.get("entry") or {}).get("price")), "plan_stop": _num((tp.get("stop") or {}).get("price")),
      "plan_t1": _num((tp.get("t1") or {}).get("price")), "plan_t2": _num((tp.get("t2") or {}).get("price")), "plan_rr": _num(tp.get("rr_blend")),
      "signals_fired": [s.get("key") for s in (tp.get("signals_fired") or [])],
      "fwd_ret_5d": None, "fwd_ret_10d": None,
  }


def load(n: int | None = None) -> list[dict]:
  if not LOG_PATH.exists():
    return []
  out: list[dict] = []
  for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
      continue
    try:
      rec = json.loads(line)
    except json.JSONDecodeError:
      continue
    if isinstance(rec, dict) and rec.get("date"):
      out.append(rec)
  out.sort(key=lambda r: r.get("date") or "")
  return out[-n:] if n else out


def _backfill_forward_returns(records: list[dict], closes_by_date: dict[str, float]) -> None:
  dates = sorted(closes_by_date)
  idx = {d: i for i, d in enumerate(dates)}
  for r in records:
    i = idx.get(r.get("date"))
    if i is None:
      continue
    for h in (5, 10):
      key = f"fwd_ret_{h}d"
      if r.get(key) is None and i + h < len(dates):
        c0, c1 = closes_by_date[dates[i]], closes_by_date[dates[i + h]]
        if c0:
          r[key] = round((c1 / c0 - 1.0) * 100.0, 2)


def append(p: dict) -> dict:
  """Insert / replace today's record, back-fill forward returns, rewrite the log."""
  rec = record_from_payload(p)
  records = [r for r in load() if r.get("date") != rec["date"]]
  records.append(rec)
  closes: dict[str, float] = {}
  for r in ((p.get("technicals") or {}).get("chart_series") or []):
    if r.get("date") and r.get("close"):
      closes[r["date"]] = float(r["close"])
  for r in (p.get("soxl_recent") or []):
    if r.get("date") and r.get("close"):
      closes.setdefault(r["date"], float(r["close"]))
  _backfill_forward_returns(records, closes)
  records.sort(key=lambda r: r.get("date") or "")
  atomic_write_text(LOG_PATH, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
  return rec


def snapshot(p: dict) -> Path:
  """Keep a gzip'd copy of the full payload per trading day (pruned to SNAP_KEEP)."""
  SNAP_DIR.mkdir(parents=True, exist_ok=True)
  day = str(p.get("data_as_of") or "unknown").replace("/", "-")
  out = SNAP_DIR / f"soxl_{day}.json.gz"
  atomic_write_bytes(out, gzip.compress(json.dumps(p, ensure_ascii=False).encode("utf-8")))
  snaps = sorted(SNAP_DIR.glob("soxl_*.json.gz"))
  for old in snaps[:-SNAP_KEEP]:
    old.unlink(missing_ok=True)
  return out


def technical_lights(chart_series: list[dict], n: int = 120) -> list[dict]:
  """Price-only traffic light per day: +1/−1 votes from 6 trend facts."""
  out: list[dict] = []
  for r in (chart_series or [])[-n:]:
    c = r.get("close")
    if c is None:
      continue
    votes: list[int] = []
    for ref in ("sma20", "sma50", "sma200"):
      v = r.get(ref)
      if v is not None:
        votes.append(1 if c > v else -1)
    if r.get("macd_hist") is not None:
      votes.append(1 if r["macd_hist"] > 0 else -1)
    if r.get("rsi14") is not None:
      votes.append(1 if r["rsi14"] >= 50 else -1)
    sd = r.get("supertrend_dir")
    if sd is not None:
      votes.append(1 if (sd is True or (isinstance(sd, (int, float)) and sd > 0)) else -1)
    pts = sum(votes)
    nv = len(votes) or 1
    frac = pts / nv
    light = "bull" if frac >= 0.5 else ("bear" if frac <= -0.5 else "neutral")
    out.append({"date": r["date"], "close": c, "pts": pts, "n": nv, "light": light})
  return out


def light_stats(lights: list[dict]) -> dict:
  """How long the current light has been on, and the previous switch date."""
  if not lights:
    return {"current": None, "days": 0, "since": None, "previous": None}
  cur = lights[-1]["light"]
  days = 0
  since = lights[-1]["date"]
  prev = None
  for r in reversed(lights):
    if r["light"] == cur:
      days += 1
      since = r["date"]
    else:
      prev = r["light"]
      break
  return {"current": cur, "days": days, "since": since, "previous": prev}
