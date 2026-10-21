#!/usr/bin/env python3
"""Live quote snapshot — the "報價" half of 「最新消息報價」.

A handful of fast calls (Nasdaq quote/info for ETFs & stocks, CBOE delayed
quotes for the volatility complex) that an agent can request at any time without
re-running the 1–5 minute analysis pipeline.  Written to ``feed/quotes.json`` on
every pipeline run and exposed live through ``auto_update.py quotes`` and the
MCP tool ``get_quotes``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import datafeed

ET = ZoneInfo("America/New_York")
TPE = ZoneInfo("Asia/Taipei")

CORE = [("SOXL", "etf", "SOXL 三倍做多半導體"), ("SOXS", "etf", "SOXS 三倍做空半導體"), ("SOXX", "etf", "SOXX 費半 ETF"),
        ("SPY", "etf", "S&P 500"), ("QQQ", "etf", "Nasdaq 100")]
LEADERS = [("NVDA", "stocks", "Nvidia"), ("AVGO", "stocks", "Broadcom"), ("AMD", "stocks", "AMD"), ("MU", "stocks", "Micron"),
           ("TSM", "stocks", "TSMC ADR"), ("AMAT", "stocks", "Applied Materials"), ("LRCX", "stocks", "Lam Research")]
VOL = [("_VIX", "VIX 恐慌指數"), ("_VIX3M", "VIX 3 個月"), ("_VIX9D", "VIX 9 天"), ("_SKEW", "SKEW 尾部風險")]


def _row(sym: str, cls: str, label: str) -> dict:
  try:
    q = datafeed.fetch_nasdaq_quote(sym, cls)
  except Exception:  # noqa: BLE001
    q = None
  if not q:
    return {"symbol": sym, "label": label, "available": False}
  return {"symbol": sym, "label": label, "available": True, "last": q["last"], "change": q.get("change"), "change_pct": q.get("change_pct"),
          "market_status": q.get("market_status"), "last_trade": q.get("last_trade"), "ext_last": q.get("ext_last"),
          "ext_change_pct": q.get("ext_change_pct"), "ext_trade": q.get("ext_trade"), "volume": q.get("volume")}


def _vol_row(sym: str, label: str) -> dict:
  try:
    q = datafeed.fetch_cboe_quote(sym)
  except Exception:  # noqa: BLE001
    q = None
  if not q:
    return {"symbol": sym.lstrip("_"), "label": label, "available": False}
  return {"symbol": q["symbol"], "label": label, "available": True, "last": q["last"], "change": q.get("change"), "change_pct": q.get("change_pct"),
          "last_trade": q.get("last_trade")}


def snapshot(include_leaders: bool = True) -> dict:
  now = datetime.now(timezone.utc)
  core = [_row(*c) for c in CORE]
  leaders = [_row(*c) for c in LEADERS] if include_leaders else []
  vol = [_vol_row(*v) for v in VOL]
  vix = next((v for v in vol if v["symbol"] == "VIX" and v.get("available")), None)
  vix3m = next((v for v in vol if v["symbol"] == "VIX3M" and v.get("available")), None)
  term = round(vix["last"] / vix3m["last"], 3) if vix and vix3m and vix3m["last"] else None
  status = next((r.get("market_status") for r in core if r.get("available") and r.get("market_status")), "")
  soxl = core[0] if core and core[0].get("available") else None
  return {
      "fetched_at_utc": now.strftime("%Y-%m-%d %H:%M:%S"), "fetched_at_et": now.astimezone(ET).strftime("%Y-%m-%d %H:%M ET"),
      "fetched_at_tpe": now.astimezone(TPE).strftime("%Y-%m-%d %H:%M 台北"), "market_status": status,
      "soxl": soxl, "core": core, "leaders": leaders, "volatility": vol, "vix_term_ratio": term,
      "one_liner": _one_liner(soxl, vix, term, status),
  }


def _one_liner(soxl: dict | None, vix: dict | None, term: float | None, status: str) -> str:
  if not soxl:
    return "報價暫時無法取得"
  s = f"SOXL ${soxl['last']:.2f}（{(soxl.get('change_pct') or 0):+.2f}%）"
  if soxl.get("ext_last") and soxl.get("ext_change_pct") is not None:
    s += f"，盤後 ${soxl['ext_last']:.2f}（{soxl['ext_change_pct']:+.2f}%）"
  if vix:
    s += f"；VIX {vix['last']:.2f}（{(vix.get('change_pct') or 0):+.1f}%）"
  if term is not None:
    s += f"，VIX/VIX3M {term:.3f}" + ("（倒掛，恐慌）" if term > 1 else "（正常）" if term < 0.92 else "（偏緊）")
  if status:
    s += f"｜市場狀態 {status}"
  return s


if __name__ == "__main__":
  import json
  print(json.dumps(snapshot(), ensure_ascii=False, indent=1))
