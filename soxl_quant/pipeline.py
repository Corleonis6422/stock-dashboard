#!/usr/bin/env python3
"""Pipeline orchestration: fetch → analyze → score → playbook → JSON (+ HTML)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import traceback

from . import datafeed, early_warning, fsio, heatmap, history, macro, news, options_flow, playbook, postmortem, scheduler, scoring, sentiment, technicals

BASE_DIR = Path(__file__).resolve().parent.parent


def _step(label: str):
  print(label, flush=True)


def run(write_html: bool = True, refresh: bool = False) -> dict:
  t0 = time.time()
  if refresh:
    n = datafeed.clear_cache()
    _step(f"Cache cleared ({n} files)")
  warnings: list[str] = []

  _step("1/9 SOXL daily history (5y) & technicals ...")
  soxl = datafeed.fetch_history("SOXL", "5y")
  tech = technicals.analyze(soxl)
  last_bar = soxl[-1]
  data_status = {
      "provisional": bool(last_bar.get("provisional")), "final": bool(last_bar.get("final", True)),
      "asof_et": last_bar.get("asof_et"), "last_tick_et": last_bar.get("last_tick_et"),
  }
  if not data_status["provisional"]:
    data_status["label"], data_status["note"] = "官方日線", ""
  elif data_status["final"]:
    data_status["label"] = "收盤即時報價補齊"
    data_status["note"] = f"{tech['latest_date']} 的 K 線由 Nasdaq 即時報價補齊（官方日線通常收盤後數小時才公布），與官方收盤價可能有幾分錢差異，下次更新會自動換成官方數據。"
  else:
    data_status["label"] = f"盤中快照 {last_bar.get('last_tick_et') or ''} ET"
    data_status["note"] = f"{tech['latest_date']} 為盤中快照（美東 {last_bar.get('last_tick_et') or ''}），今日尚未收盤；收盤後的自動更新會以收盤價重算。"
  _step(f"    {tech['latest_date']} close ${tech['close']} ({tech['ret_1d']:+.2f}%), 52w-high drawdown {tech['drawdown_from_52w_high_pct']}%, MA: {tech['ma_structure']['label']} [{data_status['label']}]")

  _step("2/9 Sentiment: CNN Fear & Greed, VIX complex (CBOE), market P/C, flows, cross-asset ...")
  try:
    sen = sentiment.analyze(soxl)
    fg = sen.get("fear_greed") or {}
    vx = sen.get("vix") or {}
    _step(f"    F&G {fg.get('score')} ({fg.get('rating')}), VIX {vx.get('vix')} / VIX3M {vx.get('vix3m')} ratio {vx.get('ratio_vix_3m')}, SKEW {vx.get('skew')}, Pulse {sen['pulse']['score']}")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"sentiment: {e}")
    traceback.print_exc()
    sen = {"fear_greed": None, "vix": {"available": False}, "put_call": {"available": False}, "flows": {"available": False}, "cross_asset": {"available": False}, "pulse": {"score": 50, "rating_zh": "n/a", "parts": []}}

  _step("3/9 Options: CBOE SOXL chain (P/C, walls, GEX, gamma flip, whale flow, forecast) + SOXX/SOXS ...")
  try:
    opt = options_flow.analyze("SOXL", tech["close"], with_secondary=True)
    _step(f"    spot ${opt['cboe_spot']} contracts {opt['total_contracts']} P/C vol {opt['pc_vol_ratio']} GEX {opt['total_net_gex_m']}M flip {opt['gamma_flip']} whale {opt['whale']['whale_net_score']} IV30 {opt['iv30_pct']}%")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"options: {e}")
    traceback.print_exc()
    opt = {"cboe_spot": tech["close"], "total_contracts": 0, "total_call_vol": 0, "total_put_vol": 0, "pc_vol_ratio": None, "cp_vol_ratio": None,
           "total_net_gex_m": 0.0, "gamma_flip": None, "whale": {}, "forecast": {}, "expirations": [], "focus_strikes": [], "secondary": {}}

  _step("4/9 Heat map: 16 constituents ...")
  try:
    hm = heatmap.analyze(soxl)
    _step(f"    breadth >20MA {hm['breadth_above_sma20_pct']}% >50MA {hm['breadth_above_sma50_pct']}% >200MA {hm['breadth_above_sma200_pct']}% oversold {hm['breadth_oversold_pct']}% (failed {len(hm['failed'])})")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"heatmap: {e}")
    traceback.print_exc()
    hm = {"constituents": [], "subsectors": [], "failed": [], "breadth_above_sma20_pct": 0, "breadth_above_sma50_pct": 0, "breadth_above_sma200_pct": 0,
          "breadth_oversold_pct": 0, "breadth_pos_1d_pct": 0, "breadth_pos_5d_pct": 0, "weighted_ret_1d": 0, "weighted_ret_5d": 0, "weighted_ret_20d": 0, "avg_rsi14": 50}

  _step("5/9 Macro correlations (10Y/30Y Treasury, Brent, VIX, DXY/HYG/Gold/Copper/BTC) ...")
  vix_rows = datafeed.fetch_history("^VIX", "5y")
  try:
    mac = macro.analyze(soxl, vix_rows)
    _step(f"    latest {mac['latest_date']}, missing {mac['missing']}, 20D corr VIX {mac['horizons']['20D']['VIX']['ret_corr']}")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"macro: {e}")
    traceback.print_exc()
    mac = {"latest_date": tech["latest_date"], "missing": [], "labels": {}, "macro_kpis": [], "horizons": {k: {"VIX": {"ret_corr": 0, "level_corr": 0}, "BRENT": {"ret_corr": 0, "level_corr": 0}} for k in ("20D", "60D", "120D", "250D")},
           "matrix_20d": [], "matrix_60d": [], "matrix_keys": [], "beta_vix_20d": 0, "beta_brent_20d": 0, "beta_tnx_10bps": 0, "beta_tyx_10bps": 0, "rolling_series": [], "latest": {}}

  _step("6/9 Crash early-warning system, event study & analogs ...")
  try:
    vixc = {n: datafeed.fetch_cboe_index_history(n) for n in ("VIX", "VIX3M", "VIX9D", "VVIX", "SKEW")}
  except Exception as e:  # noqa: BLE001
    warnings.append(f"vix complex: {e}")
    vixc = {}
  try:
    treasury = datafeed.fetch_treasury_yields(4)
  except Exception as e:  # noqa: BLE001
    warnings.append(f"treasury: {e}")
    treasury = []
  aux = {}
  for sym in ("HYG", "SPY", "SOXS", "SOXX"):
    try:
      aux[sym] = datafeed.fetch_history(sym, "5y" if sym == "SPY" else "2y")
    except Exception as e:  # noqa: BLE001
      warnings.append(f"{sym}: {e}")
      aux[sym] = None
  fg_hist = (sen.get("fear_greed") or {}).get("history")
  pc_hist = (sen.get("put_call") or {}).get("history")
  try:
    ews = early_warning.analyze(soxl, vixc, treasury, fg_hist, pc_hist, aux.get("HYG"), aux.get("SPY"), aux.get("SOXS"))
    es = ews["event_study"]
    _step(f"    crash risk today {ews['today']['score']} pct (raw {ews['today']['raw']}) ({ews['today']['zone']}); episodes {es['n_episodes']} (top-type {es['n_top_episodes']}, flagged@80 {es['top_episodes_flagged']}); precision@80 {es['stats_top_80']['precision_pct']}% base {es['stats_top_80']['base_rate_pct']}% lift {es['stats_top_80']['lift']}x")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"early_warning: {e}")
    traceback.print_exc()
    ews = {"today": {"date": tech["latest_date"], "score": 0, "zone": "n/a", "n_active": 0}, "contributions": [], "chart": [], "event_study": {}, "analogs": {"conditions": []}, "peak_checklist": {}, "score_history_90d": []}

  _step("7/9 News: bullish vs bearish classification ...")
  try:
    tnx_rows = datafeed.fetch_history("^TNX", "2y")
  except Exception:  # noqa: BLE001
    tnx_rows = None
  try:
    brent_rows = datafeed.fetch_history("BZ=F", "2y")
  except Exception:  # noqa: BLE001
    brent_rows = None
  try:
    nws = news.analyze(soxl, vix_rows, tnx_rows, brent_rows)
    _step(f"    articles {nws['total_unique_articles']} 7d bull {nws['recent_bull_count']} bear {nws['recent_bear_count']} ratio {nws['bull_bear_ratio']}")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"news: {e}")
    traceback.print_exc()
    nws = {"total_unique_articles": 0, "recent_bull_count": 0, "recent_bear_count": 0, "bull_bear_ratio": None, "themes_7d": [], "daily_feed": []}

  _step("7b/9 News flash: what happened in the last 36 h (Fed / Iran / tariffs / chip leaders) ...")
  flash: dict = {}
  try:
    from . import newsflash
    flash = newsflash.analyze()
    on = [k for k, v in flash["flags"].items() if v]
    _step(f"    {flash['n_relevant']} relevant headlines, net {flash['net']} ({flash['label']}); flags {on or 'none'}; top: {flash['top'][0]['title'][:70] if flash['top'] else '—'}")
    if flash.get("errors"):
      warnings.append("newsflash sources: " + "; ".join(flash["errors"][:3]))
  except Exception as e:  # noqa: BLE001
    warnings.append(f"newsflash: {e}")
    traceback.print_exc()

  _step("8/9 Scorecard, playbook & post-mortem ...")
  score = scoring.build(tech, opt, hm, mac, sen, nws, ews)
  pb = playbook.build(tech, opt, sen, hm, ews, score, soxl)
  _step(f"    composite {score['composite_score']} ({score['verdict']}) trend {score['trend_score']} contrarian {score['contrarian_score']}")
  _step(f"    regime: {score['regime']}")
  try:
    pm = postmortem.build(soxl, aux.get("SOXX"), aux.get("SPY"), sen, ews, treasury, opt)
    _step(f"    post-mortem: peak {pm['peak_date']} ${pm['peak_close']} → trough {pm['trough_date']} ${pm['trough_close']} ({pm['soxl_drawdown_pct']}%), SOXX {pm['soxx_drawdown_pct']}%")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"postmortem: {e}")
    traceback.print_exc()
    pm = {}

  _step("8b/9 Signal validation (10y walk-forward backtest) & explicit trade plan ...")
  bt: dict = {}
  tp: dict = {}
  soxx10: list[dict] | None = None
  try:
    from . import backtest, tradeplan
    soxl10 = datafeed._augment_latest("SOXL", "etf", datafeed.fetch_nasdaq_history("SOXL", "etf", years=10))
    if soxl10 and soxl10[-1]["date"] < soxl[-1]["date"]:  # 10y series must end on the same session as the 5y series
      soxl10 = soxl10 + [soxl[-1]]
    try:
      soxx10 = datafeed.fetch_nasdaq_history("SOXX", "etf", years=10)
    except Exception as e:  # noqa: BLE001
      warnings.append(f"soxx 10y: {e}")
      soxx10 = None
    vix_d = {r["date"]: r["close"] for r in (vixc.get("VIX") or [])}
    vix3m_d = {r["date"]: r["close"] for r in (vixc.get("VIX3M") or [])}
    bt = backtest.run(soxl10, vix_d, vix3m_d, underlying_rows=soxx10)
    bt["ews_today"] = ews.get("today") or {}
    sm = bt["summary"]
    _step(f"    {sm['n_signals']} signals on {bt['method']['bars']} bars ({bt['method']['sample']}); significant {sm['n_significant']}/{sm['n_graded']}, BH q<0.10 {sm['n_q_lt_10']}; fired today {sm['fired_today'] or 'none'}; pending {sm['pending'] or 'none'}")
    tp = tradeplan.build(tech, opt, pb, score, bt, soxl, sen)
    _step(f"    plan: {tp['side']} entry {tp['entry']['price']} stop {tp['stop']['price']} ({tp['stop']['dist_pct']}%) T1 {tp['t1']['price']} T2 {tp['t2']['price']} R:R {tp['rr_blend']} size {tp['size']['if_triggered_pct']}% tradeable={tp['tradeable']}")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"backtest/tradeplan: {e}")
    traceback.print_exc()

  _step("8c/9 Market dashboard: add-on? / macro / SOXX trend / whales / put-call / crash ...")
  dash: dict = {}
  try:
    from . import dashboard, events as events_mod
    try:
      ev_list = (events_mod.analyze() or {}).get("events") or []
    except Exception as e:  # noqa: BLE001
      warnings.append(f"events (dashboard): {e}")
      ev_list = []
    soxx_rows = soxx10
    try:  # make sure the SOXX series ends on today's session (the regime test above tolerates a lag, the gauge should not)
      if soxx10 and soxx10[-1]["date"] < tech["latest_date"]:
        soxx_rows = datafeed._augment_latest("SOXX", "etf", list(soxx10))
    except Exception as e:  # noqa: BLE001
      warnings.append(f"soxx augment: {e}")
    dash = dashboard.build({**{k: v for k, v in (("technicals", tech), ("options", opt), ("sentiment", sen), ("heatmap", hm), ("macro", mac), ("early_warning", ews),
                                                   ("scoring", score), ("trade_plan", tp), ("newsflash", flash), ("playbook", pb), ("data_as_of", tech["latest_date"]))},
                            "benchmarks_recent": {"SOXX": [{"date": r["date"], "close": r["close"]} for r in (aux.get("SOXX") or [])[-40:]]}},
                           soxx_rows=soxx_rows, events=ev_list)
    _step(f"    {dash['one_liner']}")
    _step(f"    grades {' '.join(f'{g['short']} {g['grade']}' for g in dash['factor_grades'])} → overall {dash['overall_grade']}; {dash['voices']['summary']}")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"dashboard: {e}")
    traceback.print_exc()

  payload = {
      "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "data_as_of": tech["latest_date"],
      "data_status": data_status,
      "warnings": warnings,
      "technicals": tech, "options": opt, "sentiment": sen, "heatmap": hm, "macro": mac,
      "early_warning": ews, "news": nws, "newsflash": flash, "scoring": score, "playbook": pb, "postmortem": pm,
      "backtest": bt, "trade_plan": tp, "dashboard": dash,
      "benchmarks_recent": {sym: [{"date": r["date"], "close": r["close"]} for r in (aux.get(sym) or [])[-40:]] for sym in ("SOXX", "SPY")},
      "soxl_recent": [{k: r[k] for k in ("date", "open", "high", "low", "close", "volume")} for r in soxl[-30:]],
  }

  # ---- daily history (what the auto-update accumulates) + schedule status for the pages
  try:
    payload["light_history"] = history.technical_lights(tech.get("chart_series") or [])
    history.append(payload)
    payload["verdict_history"] = history.load(60)
    _step(f"    history: {len(payload['verdict_history'])} daily verdict record(s) → {history.LOG_PATH.relative_to(BASE_DIR)}")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"history: {e}")
    traceback.print_exc()
    payload.setdefault("light_history", [])
    payload.setdefault("verdict_history", [])
  try:
    payload["schedule"] = scheduler.schedule_summary()
  except Exception as e:  # noqa: BLE001
    payload["schedule"] = {"installed": False, "error": str(e)}

  json_path = BASE_DIR / "soxl_analysis_data.json"
  fsio.atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=1))
  _step(f"9/9 Saved JSON → {json_path} ({json_path.stat().st_size/1024:.0f} KB)")
  try:
    snap = history.snapshot(payload)
    _step(f"    Snapshot → {snap.relative_to(BASE_DIR)} ({snap.stat().st_size/1024:.0f} KB)")
  except Exception as e:  # noqa: BLE001
    warnings.append(f"snapshot: {e}")

  if write_html:
    from . import report_html, report_simple
    out = BASE_DIR / "soxl_analysis_report.html"
    html_text = report_html.render(payload)
    fsio.atomic_write_text(out, html_text)
    _step(f"    Saved HTML → {out} ({out.stat().st_size/1024:.0f} KB)")
    out2 = BASE_DIR / "soxl_simple.html"
    fsio.atomic_write_text(out2, report_simple.render(payload))
    _step(f"    Saved 新手版 → {out2} ({out2.stat().st_size/1024:.0f} KB)")
    fsio.atomic_write_text(BASE_DIR / "index.html", html_text)  # GitHub Pages landing page = full report

  # ---- agent feed: upcoming events + live quotes + one-page brief (JSON / Markdown / text / RSS)
  payload["_feed"] = build_feed(payload, label="    ")
  _step(f"Done in {time.time()-t0:.0f}s; warnings: {warnings or 'none'}")
  return payload


def build_feed(payload: dict, label: str = "", with_quotes: bool = True) -> dict:
  """Build events + quotes + brief and write the feed/ directory. Never raises; returns paths + notes."""
  from . import brief, events, quotes
  notes: list[str] = []
  try:
    ev = events.analyze()
    _step(f"{label}events: {ev.get('summary_zh')}")
  except Exception as e:  # noqa: BLE001
    notes.append(f"events: {e}")
    ev = {}
  q: dict = {}
  if with_quotes:
    try:
      q = quotes.snapshot()
      _step(f"{label}quotes: {q.get('one_liner')}")
    except Exception as e:  # noqa: BLE001
      notes.append(f"quotes: {e}")
    try:  # breaking news is a freshness item like quotes: refresh when the stored flash is > 30 min old
      from . import newsflash
      stale = True
      fl = payload.get("newsflash") or {}
      if fl.get("as_of_utc"):
        age_min = (datetime.now(timezone.utc) - datetime.strptime(fl["as_of_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)).total_seconds() / 60
        stale = age_min > 30
      if stale:
        payload["newsflash"] = newsflash.analyze()
        _step(f"{label}newsflash: {payload['newsflash']['n_relevant']} headlines, {payload['newsflash']['label']}; {payload['newsflash']['beginner_line'][:80]}")
        if payload.get("dashboard"):
          from . import dashboard
          payload["dashboard"] = dashboard.refresh_macro(payload["dashboard"], payload, (ev or {}).get("events") or [])
    except Exception as e:  # noqa: BLE001
      notes.append(f"newsflash: {e}")
  try:
    cfg = scheduler.load_config(create=False)
    base_url = (cfg.get("feed") or {}).get("base_url")
  except Exception:  # noqa: BLE001
    base_url = None
  try:
    br = brief.build(payload, ev, q, base_url)
    paths = brief.write_all(br)
    _step(f"{label}feed → {brief.FEED_DIR.relative_to(BASE_DIR)}/latest.{{json,md,txt}} + rss.xml ({len(brief.to_markdown(br).encode('utf-8'))//1024} KB md)")
    try:
      from . import meta_pack
      mp = meta_pack.build(br, payload, base_url)
      paths["meta"] = mp["dir"]
      _step(f"{label}meta → {Path(mp['dir']).relative_to(BASE_DIR)}/ ({len(mp['files'])} files, {mp['total_bytes']//1024} KB) for Muse / AI agents")
    except Exception as e:  # noqa: BLE001
      traceback.print_exc()
      notes.append(f"meta: {e}")
    return {"ok": True, "paths": paths, "brief": br, "notes": notes}
  except Exception as e:  # noqa: BLE001
    traceback.print_exc()
    notes.append(f"brief: {e}")
    return {"ok": False, "paths": {}, "brief": None, "notes": notes}


if __name__ == "__main__":
  run(write_html="--no-html" not in sys.argv, refresh="--refresh" in sys.argv)
