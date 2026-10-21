#!/usr/bin/env python3
"""Upcoming event calendar for the semiconductor complex (what can move SOXL next).

Sources (all free, no key):
* FOMC meeting dates          federalreserve.gov calendar page (static fallback)
* Constituent earnings        api.nasdaq.com daily earnings calendar, filtered to the
                              SOXX heavyweights tracked by heatmap.py
* Options expirations         derived: weekly (Friday) and monthly (3rd Friday) opex
* US market holidays          marketclock (static NYSE calendar)

Everything is best-effort: a failed source simply yields no events of that kind
and is listed in ``sources`` so the brief can say what it could not see.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import datafeed, marketclock

CONSTITUENTS = ["NVDA", "AVGO", "AMD", "TSM", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "INTC", "MRVL", "ADI", "ASML", "ARM", "NXPI"]
_WD_ZH = ["一", "二", "三", "四", "五", "六", "日"]
_TYPE_ORDER = {"fomc": 0, "earnings": 1, "opex": 2, "holiday": 3}


def _third_friday(y: int, m: int) -> date:
  d = date(y, m, 15)
  while d.weekday() != 4:
    d += timedelta(days=1)
  return d


def _fmt(d: date) -> str:
  return f"{d.month}/{d.day}（{_WD_ZH[d.weekday()]}）"


def _fomc_events(today: date, end: date, sources: dict) -> list[dict]:
  out: list[dict] = []
  try:
    srcs = []
    for y in sorted({today.year, (end + timedelta(days=45)).year}):
      cal = datafeed.fetch_fomc_calendar(y)
      srcs.append(str(cal.get("source", "static")))
      for m in cal.get("meetings", []):
        s, e = date.fromisoformat(m["start"]), date.fromisoformat(m["end"])
        if e < today or s > end + timedelta(days=45):
          continue
        out.append({
            "date": e.isoformat(), "start": s.isoformat(), "type": "fomc", "days_ahead": (e - today).days,
            "label": f"FOMC 利率決議 {s.month}/{s.day}–{e.day}" + ("（含點陣圖 SEP）" if m.get("sep") else ""),
            "detail": "決議 14:00 ET 公布、14:30 記者會；半導體與高 Beta 資產波動最大的時段" + ("，另附經濟預測與利率點陣圖" if m.get("sep") else ""),
        })
    sources["fomc"] = "/".join(sorted(set(srcs))) or "n/a"
  except Exception as e:  # noqa: BLE001
    sources["fomc"] = f"失敗: {type(e).__name__}"
  return out


def _earnings_events(today: date, days: int, sources: dict) -> list[dict]:
  out: list[dict] = []
  try:
    hits = checked = 0
    d = today
    while d <= today + timedelta(days=days):
      if marketclock.is_trading_day(d):
        for r in datafeed.fetch_nasdaq_earnings_calendar(d.isoformat()):
          if r["symbol"] not in CONSTITUENTS:
            continue
          hits += 1
          detail = "｜".join(x for x in (f"EPS 預估 {r['eps_forecast']}" if r.get("eps_forecast") else "", r.get("fiscal_quarter") or "") if x)
          out.append({"date": d.isoformat(), "type": "earnings", "symbol": r["symbol"], "days_ahead": (d - today).days,
                      "label": f"{r['symbol']} 財報（{r['when']}）", "detail": detail, "name": r.get("name", "")})
        checked += 1
      d += timedelta(days=1)
    sources["earnings"] = f"nasdaq.com（掃描 {checked} 個交易日，成分股命中 {hits}）"
  except Exception as e:  # noqa: BLE001
    sources["earnings"] = f"失敗: {type(e).__name__}"
  return out


def _opex_events(today: date, end: date) -> list[dict]:
  out: list[dict] = []
  d = today
  while d <= end:
    if d.weekday() == 4:
      monthly = d == _third_friday(d.year, d.month)
      quarterly = monthly and d.month in (3, 6, 9, 12)
      exp_day = d if marketclock.is_trading_day(d) else d - timedelta(days=1)
      label = ("季度四巫日 (Quad Witching)" if quarterly else "月選擇權到期 (Monthly OPEX)") if monthly else "週選擇權到期"
      out.append({"date": exp_day.isoformat(), "type": "opex", "days_ahead": (exp_day - today).days, "label": label,
                  "detail": "Max Pain 磁吸與 Gamma 對沖解除最明顯的一天" if monthly else "到期後造市商 Gamma 部位重置，隔週波動常改變"})
    d += timedelta(days=1)
  return out


def _holiday_events(today: date, end: date) -> list[dict]:
  out: list[dict] = []
  for hd in sorted(marketclock.US_MARKET_HOLIDAYS):
    if today <= hd <= end:
      out.append({"date": hd.isoformat(), "type": "holiday", "days_ahead": (hd - today).days, "label": "美股休市（NYSE 假日）", "detail": ""})
  return out


def analyze(today: date | None = None, horizon_days: int = 14, earnings_days: int = 10) -> dict:
  today = today or datetime.now().date()
  end = today + timedelta(days=horizon_days)
  sources: dict[str, str] = {}
  events = _fomc_events(today, end, sources) + _earnings_events(today, earnings_days, sources) + _opex_events(today, end) + _holiday_events(today, end)
  events.sort(key=lambda e: (e["date"], _TYPE_ORDER.get(e["type"], 9), e.get("symbol", "")))
  for e in events:
    e["when_zh"] = _fmt(date.fromisoformat(e["date"]))
  next_fomc = next((e for e in events if e["type"] == "fomc"), None)
  next_earnings = [e for e in events if e["type"] == "earnings"][:8]
  within = [e for e in events if e["days_ahead"] <= horizon_days]
  summary = "；".join(f"{e['when_zh']} {e['label']}" for e in within[:6]) or "未來兩週沒有已知的重大排程事件"
  return {"as_of": today.isoformat(), "horizon_days": horizon_days, "events": events, "sources": sources,
          "next_fomc": next_fomc, "next_earnings": next_earnings, "summary_zh": summary}


if __name__ == "__main__":
  import json
  print(json.dumps(analyze(), ensure_ascii=False, indent=1))
