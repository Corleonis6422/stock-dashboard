#!/usr/bin/env python3
"""Agent brief — the machine- and LLM-friendly digest of one pipeline run.

Everything a downstream agent (Muse, Gemini, Claude, a Slack bot …) needs in one
small, stable document, produced in three shapes from the same dict:

* ``feed/latest.json``   compact JSON (schema ``soxl-quant-brief/1``) — ~20 KB, flat
                         sections, no SVG / chart series, nothing secret
* ``feed/latest.md``     one-page Markdown brief in Traditional Chinese (paste into
                         any chat / LLM; also the body of e-mail and webhook pushes)
* ``feed/latest.txt``    ≤ ~900-character plain text for phone notifications

Plus the archive (``feed/YYYY-MM-DD.{json,md}``, ``feed/index.json``), an RSS 2.0
feed (``feed/rss.xml``) and the JSON Schema (``feed/schema.json``) so a consumer can
validate what it ingests.  All writes are atomic.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from . import fsio

BASE_DIR = Path(__file__).resolve().parent.parent
FEED_DIR = BASE_DIR / "feed"
SCHEMA_ID = "soxl-quant-brief/1"
DEFAULT_BASE_URL = "https://corleonis6422.github.io/stock-dashboard/"
ARCHIVE_KEEP = 120
TPE = ZoneInfo("Asia/Taipei")
_WD_ZH = ["一", "二", "三", "四", "五", "六", "日"]
DISCLAIMER = "本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _f(v, nd: int = 2):
  try:
    if v is None:
      return None
    x = float(v)
    if x != x or x in (float("inf"), float("-inf")):
      return None
    return round(x, nd)
  except (TypeError, ValueError):
    return None


def _pct(v, nd: int = 2, sign: bool = True) -> str:
  x = _f(v, nd)
  if x is None:
    return "n/a"
  return f"{x:+.{nd}f}%" if sign else f"{x:.{nd}f}%"


def _usd(v, nd: int = 2) -> str:
  x = _f(v, nd)
  return "n/a" if x is None else f"${x:,.{nd}f}"


def _num(v, nd: int = 2, sign: bool = False) -> str:
  x = _f(v, nd)
  if x is None:
    return "n/a"
  return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def _date_zh(d: str) -> str:
  try:
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{dt.month}/{dt.day}（{_WD_ZH[dt.weekday()]}）"
  except (TypeError, ValueError):
    return str(d)


def _headline(h: dict) -> dict:
  return {"title": h.get("title"), "publisher": h.get("publisher"), "tag": h.get("zh_tag"), "time_utc": h.get("time"), "link": h.get("link")}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build(p: dict, events: dict | None = None, quotes: dict | None = None, base_url: str | None = None) -> dict:
  tech = p.get("technicals") or {}
  opt = p.get("options") or {}
  sen = p.get("sentiment") or {}
  hm = p.get("heatmap") or {}
  mac = p.get("macro") or {}
  ews = p.get("early_warning") or {}
  nws = p.get("news") or {}
  sc = p.get("scoring") or {}
  pb = p.get("playbook") or {}
  b = pb.get("beginner") or {}
  cons = (sc.get("consensus") or b.get("consensus") or {})
  plan = b.get("plan") or {}
  fg = sen.get("fear_greed") or {}
  vx = sen.get("vix") or {}
  pc = sen.get("put_call") or {}
  flows = (sen.get("flows") or {}).get("latest") or {}
  wh = opt.get("whale") or {}
  fc = opt.get("forecast") or {}
  today_ews = ews.get("today") or {}
  base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
  data_as_of = p.get("data_as_of")
  hist = [h for h in (p.get("verdict_history") or []) if h.get("date")]
  prev = next((h for h in reversed(hist) if h.get("date") and data_as_of and h["date"] < data_as_of), None)

  # ---- changes vs previous session record
  changes: dict = {"has_previous": bool(prev)}
  streak = 0
  if hist:
    cur_color = b.get("color") or (hist[-1].get("color") if hist else None)
    for h in reversed(hist):
      if h.get("color") == cur_color:
        streak += 1
      else:
        break
  if prev:
    changes.update({
        "previous_date": prev.get("date"), "previous_verdict": prev.get("verdict"), "verdict_changed": (prev.get("verdict") != b.get("verdict")),
        "composite_prev": _f(prev.get("composite")), "composite_delta": _f((sc.get("composite_score") or 0) - (prev.get("composite") or 0)),
        "crash_risk_delta": _f((today_ews.get("score") or 0) - (prev.get("crash_risk") or 0), 0),
        "fear_greed_delta": _f((fg.get("score") or 0) - (prev.get("fear_greed") or 0), 1) if fg.get("score") is not None and prev.get("fear_greed") is not None else None,
        "vix_delta": _f((vx.get("vix") or 0) - (prev.get("vix") or 0), 2) if vx.get("vix") is not None and prev.get("vix") is not None else None,
        "size_pct_prev": prev.get("size_pct"),
    })
  changes["same_verdict_streak_days"] = streak
  notes = []
  if prev:
    notes.append(f"評級{'改變：' + str(prev.get('verdict')) + ' → ' + str(b.get('verdict')) if changes.get('verdict_changed') else '不變（連續 ' + str(streak) + ' 個交易日 ' + str(b.get('emoji') or '') + str(b.get('verdict') or '') + '）'}")
    if changes.get("composite_delta") is not None:
      notes.append(f"綜合分數 {_num(prev.get('composite'), 2, True)} → {_num(sc.get('composite_score'), 2, True)}（{_num(changes['composite_delta'], 2, True)}）")
    if changes.get("crash_risk_delta") is not None:
      notes.append(f"崩跌前兆 {_num(prev.get('crash_risk'), 0)} → {_num(today_ews.get('score'), 0)}")
  changes["notes"] = notes

  # ---- news
  feed = nws.get("daily_feed") or []
  latest_days = feed[:3]
  top_bull = [_headline(h) for d in latest_days for h in (d.get("top_bull_headlines") or [])][:6]
  top_bear = [_headline(h) for d in latest_days for h in (d.get("top_bear_headlines") or [])][:6]

  # ---- events
  ev = events or {}
  ev_list = [{k: e.get(k) for k in ("date", "when_zh", "type", "label", "detail", "days_ahead", "symbol")} for e in (ev.get("events") or []) if (e.get("days_ahead") or 0) <= 14][:10]

  # ---- quotes
  q = quotes or {}
  q_rows = [{k: r.get(k) for k in ("symbol", "label", "last", "change_pct", "ext_last", "ext_change_pct")} for r in ((q.get("core") or []) + (q.get("leaders") or []) + (q.get("volatility") or [])) if r.get("available")]

  macro_kpis = [{"key": k.get("key"), "name": k.get("name"), "latest": k.get("latest"), "chg_1d": k.get("chg_1d"), "chg_20d": k.get("chg_20d"),
                 "corr_20d": k.get("corr_20d"), "corr_60d": k.get("corr_60d"), "regime": k.get("regime")} for k in (mac.get("macro_kpis") or [])]

  brief = {
      "schema": SCHEMA_ID,
      "generated_at": p.get("generated_at"), "generated_at_tz": "Asia/Taipei",
      "data_as_of": data_as_of, "data_as_of_zh": _date_zh(data_as_of or ""),
      "data_status": {k: (p.get("data_status") or {}).get(k) for k in ("label", "provisional", "final", "note")},
      "warnings": p.get("warnings") or [],
      "verdict": {
          "label": b.get("verdict") or sc.get("rating_label"), "emoji": b.get("emoji") or sc.get("rating_emoji"), "color": b.get("color"),
          "rating_5": sc.get("rating_5"), "rating_label": sc.get("rating_label"), "composite": _f(sc.get("composite_score")),
          "trend_score": _f(sc.get("trend_score")), "contrarian_score": _f(sc.get("contrarian_score")), "confidence": sc.get("confidence") or b.get("confidence"),
          "agreement_pct": _f(sc.get("agreement_pct"), 0), "regime": sc.get("regime"), "one_liner": b.get("one_liner"), "headline": pb.get("headline"),
          "consensus": {k: _f(cons.get(k), 1) for k in ("buy_pct", "hold_pct", "sell_pct")} | {k: cons.get(k) for k in ("n_buy", "n_hold", "n_sell")},
          "size_pct": b.get("size_pct"), "size_note": b.get("size_note"),
          "checklist": f"{pb.get('checklist_passed', 0)}/{pb.get('checklist_total', 0)}", "checklist_verdict": pb.get("checklist_verdict"),
          "tldr": b.get("tldr") or [], "q_no_position": b.get("q_no_position"), "q_holder": b.get("q_holder"), "q_when": b.get("q_when"),
      },
      "price": {
          "close": _f(tech.get("close")), "open": _f(tech.get("open")), "high": _f(tech.get("high")), "low": _f(tech.get("low")), "volume": tech.get("volume"),
          "ret_1d": _f(tech.get("ret_1d")), "ret_5d": _f(tech.get("ret_5d")), "ret_20d": _f(tech.get("ret_20d")), "ret_60d": _f(tech.get("ret_60d")),
          "high_52w": _f(tech.get("high_52w")), "low_52w": _f(tech.get("low_52w")), "drawdown_52w_pct": _f(tech.get("drawdown_from_52w_high_pct"), 1),
          "rvol20": _f(tech.get("rvol20")), "atr_pct": _f(tech.get("atr_pct")), "realized_vol_20d_pct": _f(tech.get("realized_vol_20d_ann_pct"), 0),
          "consec_down_days": tech.get("consec_down_days"),
      },
      "levels": {
          "sma20": _f(tech.get("sma20")), "sma50": _f(tech.get("sma50")), "sma200": _f(tech.get("sma200")), "ema5": _f(tech.get("ema5")), "ema10": _f(tech.get("ema10")),
          "dist_sma20_pct": _f(tech.get("dist_sma20_pct"), 1), "dist_sma50_pct": _f(tech.get("dist_sma50_pct"), 1), "dist_sma200_pct": _f(tech.get("dist_sma200_pct"), 1),
          "ma_structure": (tech.get("ma_structure") or {}).get("label"),
          "pivot": tech.get("pivot"), "fib": tech.get("fib_levels"), "swing": {k: (tech.get("swing") or {}).get(k) for k in ("kind", "low_price", "low_date", "high_price", "high_date")},
          "bollinger": {"upper": _f(tech.get("bb_upper")), "mid": _f(tech.get("bb_mid")), "lower": _f(tech.get("bb_lower")), "pct_b": _f(tech.get("bb_pct_b"))},
          "volume_profile": {"poc": _f(tech.get("poc_price")), "vah": _f(tech.get("vah_price")), "val": _f(tech.get("val_price"))},
          "ladder": [{k: r.get(k) for k in ("price", "label", "kind", "note")} for r in (pb.get("ladder") or [])][:12],
      },
      "technicals": {
          "rsi14": _f(tech.get("rsi14"), 1), "rsi6": _f(tech.get("rsi6"), 1), "macd": _f(tech.get("macd")), "macd_signal": _f(tech.get("macd_signal")), "macd_hist": _f(tech.get("macd_hist")),
          "k9": _f(tech.get("k9"), 1), "d9": _f(tech.get("d9"), 1), "j9": _f(tech.get("j9"), 1), "adx14": _f(tech.get("adx14"), 1), "pdi14": _f(tech.get("pdi14"), 1), "ndi14": _f(tech.get("ndi14"), 1),
          "cci20": _f(tech.get("cci20"), 1), "will_r14": _f(tech.get("will_r14"), 1), "mfi14": _f(tech.get("mfi14"), 1), "cmf20": _f(tech.get("cmf20"), 3), "obv_bullish": tech.get("obv_bullish"),
          "supertrend": _f(tech.get("supertrend")), "supertrend_bull": tech.get("supertrend_bull"), "sar": _f(tech.get("sar")),
          "ichimoku": {"tenkan": _f(tech.get("tenkan9")), "kijun": _f(tech.get("kijun26")), "cloud_top": _f(tech.get("cloud_top")), "cloud_bot": _f(tech.get("cloud_bot"))},
          "up_down_vol_ratio_20d": _f(tech.get("up_down_vol_ratio")), "tech_avg_score": _f(tech.get("tech_avg_score")),
          "table": [{k: t.get(k) for k in ("group", "name", "reading", "score", "signal")} for t in (tech.get("tech_table") or [])],
      },
      "options": {
          "chain_timestamp": opt.get("chain_timestamp"), "cboe_spot": _f(opt.get("cboe_spot")), "total_contracts": opt.get("total_contracts"),
          "pc_vol_ratio": _f(opt.get("pc_vol_ratio"), 3), "pc_oi_ratio": _f(opt.get("pc_oi_ratio"), 3), "cp_prem_ratio": _f(opt.get("cp_prem_ratio")),
          "net_gex_m": _f(opt.get("total_net_gex_m"), 1), "gamma_flip": _f(opt.get("gamma_flip"), 1), "call_wall": _f(opt.get("call_wall"), 1), "call_wall_oi": opt.get("call_wall_oi"),
          "put_wall": _f(opt.get("put_wall"), 1), "put_wall_oi": opt.get("put_wall_oi"), "near_max_pain": _f(opt.get("near_max_pain"), 1), "monthly_max_pain": _f(opt.get("monthly_max_pain"), 1),
          "monthly_expiration": opt.get("monthly_expiration"), "iv30_pct": _f(opt.get("iv30_pct"), 1), "iv30_change": _f(opt.get("iv30_change"), 1), "iv_skew_25d": _f(opt.get("iv_skew_25d"), 1),
          "expected_move": {k: ({kk: fc[k].get(kk) for kk in ("expiration", "dte", "expected_move_pct", "low", "high", "atm_iv_pct")} if isinstance(fc.get(k), dict) else None) for k in ("weekly", "monthly", "quarterly")},
          "whale": {k: _f(wh.get(k), 3) if k in ("whale_net_score",) else wh.get(k) for k in ("whale_count", "whale_call_prem_m", "whale_put_prem_m", "whale_net_score", "whale_bull_prem_m", "whale_bear_prem_m", "retail_cp_ratio")},
          "nearest_expirations": [{k: e.get(k) for k in ("expiration", "dte", "pc_vol", "pc_oi", "max_pain", "net_gex_m", "atm_iv_pct")} for e in (opt.get("expirations") or [])[:3]],
      },
      "sentiment": {
          "fear_greed": {k: fg.get(k) for k in ("score", "rating", "rating_zh", "previous_close", "week_ago", "month_ago")},
          "vix": {k: vx.get(k) for k in ("date", "vix", "vix9d", "vix3m", "vix6m", "vvix", "skew", "ratio_vix_3m", "term_state", "term_zh", "vix_regime", "vvix_regime", "skew_regime", "vix_percentile_1y", "vix_5d_chg_pct")},
          "market_put_call": {k: pc.get(k) for k in ("date", "total_pc", "equity_pc", "index_pc", "equity_pc_percentile", "equity_read", "total_read")},
          "flows": {k: flows.get(k) for k in ("date", "soxl_dollar_vol_m", "soxs_dollar_vol_m", "ratio")},
          "pulse": {"score": _f((sen.get("pulse") or {}).get("score"), 0), "rating_zh": (sen.get("pulse") or {}).get("rating_zh")},
          "cross_asset": [{k: a.get(k) for k in ("symbol", "label", "last", "chg_5d_pct", "chg_20d_pct", "percentile_1y")} for a in ((sen.get("cross_asset") or {}).get("assets") or []) if a.get("available")],
      },
      "breadth": {
          "above_sma20_pct": _f(hm.get("breadth_above_sma20_pct"), 1), "above_sma50_pct": _f(hm.get("breadth_above_sma50_pct"), 1), "above_sma200_pct": _f(hm.get("breadth_above_sma200_pct"), 1),
          "oversold_pct": _f(hm.get("breadth_oversold_pct"), 1), "weighted_ret_1d": _f(hm.get("weighted_ret_1d")), "weighted_ret_5d": _f(hm.get("weighted_ret_5d")), "weighted_ret_20d": _f(hm.get("weighted_ret_20d")),
          "avg_rsi14": _f(hm.get("avg_rsi14"), 1),
          "constituents": [{k: c.get(k) for k in ("ticker", "weight", "close", "ret_1d", "ret_5d", "ret_20d", "rsi14", "above_sma20", "above_sma50", "above_sma200")} for c in (hm.get("constituents") or [])],
      },
      "macro": {"latest_date": mac.get("latest_date"), "kpis": macro_kpis, "beta_tnx_10bps": _f(mac.get("beta_tnx_10bps")), "beta_vix_20d": _f(mac.get("beta_vix_20d")), "beta_brent_20d": _f(mac.get("beta_brent_20d")), "missing": mac.get("missing") or []},
      "crash_risk": {
          "score": _f(today_ews.get("score"), 0), "raw": _f(today_ews.get("raw"), 1), "zone": today_ews.get("zone"), "n_active": today_ews.get("n_active"), "above_200ma": today_ews.get("above_200"),
          "active_signals": [{"label": c.get("label"), "family": c.get("family"), "points": c.get("points")} for c in (ews.get("contributions") or []) if (c.get("value") or 0) > 0][:8],
          "event_study": {k: (ews.get("event_study") or {}).get(k) for k in ("n_episodes", "stats_top_80")},
          "analog_h10": pb.get("analog_h10"), "analog_reference": pb.get("analog_reference"),
      },
      "scorecard": {
          "categories": [{"category": c.get("category"), "weight": c.get("weight"), "avg_score": _f(c.get("avg_score"))} for c in (sc.get("category_scores") or [])],
          "factors": [{k: f.get(k) for k in ("category", "metric", "value", "score", "weight", "kind")} for f in (sc.get("factors") or [])],
          "bull_case": [{k: x.get(k) for k in ("metric", "value", "pts", "why")} for x in (b.get("bull_case") or [])][:5],
          "bear_case": [{k: x.get(k) for k in ("metric", "value", "pts", "why")} for x in (b.get("bear_case") or [])][:5],
      },
      "plan": {k: plan.get(k) for k in ("entry", "stop", "target", "risk_reward", "max_size_pct", "stop_price", "stop_label", "stop_dist_pct", "target1_price", "target1_label", "target1_dist_pct", "target2_price", "target2_label", "target2_dist_pct")},
      "scenarios": [{k: s.get(k) for k in ("key", "tone", "title", "prob", "trigger", "target", "action")} for s in (pb.get("scenarios") or [])],
      "checklist": [{k: c.get(k) for k in ("item", "ok", "now")} for c in (pb.get("checklist") or [])],
      "watch": b.get("watch") or [],
      "news": {
          "articles_total": nws.get("total_unique_articles"), "sources": nws.get("sources"), "bull_7d": nws.get("recent_bull_count"), "bear_7d": nws.get("recent_bear_count"),
          "bull_bear_ratio": _f(nws.get("bull_bear_ratio")), "themes_7d": (nws.get("themes_7d") or [])[:6],
          "by_day": [{k: d.get(k) for k in ("date", "bull_count", "bear_count", "neutral_count", "net_sentiment_ratio", "soxl_perf")} for d in feed[:7]],
          "top_bull": top_bull, "top_bear": top_bear,
      },
      "events": {"as_of": ev.get("as_of"), "summary_zh": ev.get("summary_zh"), "next_fomc": ev.get("next_fomc"), "upcoming": ev_list, "sources": ev.get("sources")},
      "quotes": {"fetched_at_tpe": q.get("fetched_at_tpe"), "fetched_at_et": q.get("fetched_at_et"), "market_status": q.get("market_status"), "one_liner": q.get("one_liner"), "vix_term_ratio": q.get("vix_term_ratio"), "rows": q_rows},
      "changes": changes,
      "history": [{k: h.get(k) for k in ("date", "close", "ret_1d", "composite", "rating_5", "verdict", "emoji", "size_pct", "crash_risk", "fear_greed", "vix", "fwd_ret_5d", "fwd_ret_10d")} for h in hist[-15:]],
      "schedule": {k: (p.get("schedule") or {}).get(k) for k in ("installed", "times", "weekday_text", "next_run")},
      "links": {
          "report_html": base + "soxl_analysis_report.html", "simple_html": base + "soxl_simple.html", "index_html": base,
          "brief_json": base + "feed/latest.json", "brief_md": base + "feed/latest.md", "brief_txt": base + "feed/latest.txt",
          "quotes_json": base + "feed/quotes.json", "rss": base + "feed/rss.xml", "schema": base + "feed/schema.json", "full_json": base + "soxl_analysis_data.json",
          "archive_index": base + "feed/index.json",
      },
      "disclaimer": DISCLAIMER,
  }
  return brief


# --------------------------------------------------------------------------- #
# renderers
# --------------------------------------------------------------------------- #
def _rss_items_for_news(n: dict, kind: str) -> list[str]:
  out = []
  for h in n.get(kind) or []:
    t = f"{h.get('title')}（{h.get('publisher')}）" if h.get("publisher") else str(h.get("title"))
    out.append(f"  - {t}" + (f" <{h['link']}>" if h.get("link") else ""))
  return out


def to_markdown(br: dict, with_links: bool = True) -> str:
  v, pr, lv, o, s, cr, n, pl, ch, ev, q = (br.get(k) or {} for k in ("verdict", "price", "levels", "options", "sentiment", "crash_risk", "news", "plan", "changes", "events", "quotes"))
  fg, vx, bd, mc = s.get("fear_greed") or {}, s.get("vix") or {}, br.get("breadth") or {}, br.get("macro") or {}
  cons = v.get("consensus") or {}
  lines: list[str] = []
  lines.append(f"# SOXL 每日簡報 {br.get('data_as_of')}（{br.get('data_as_of_zh', '').split('（')[-1].rstrip('）')}）收盤")
  lines.append(f"產生時間 {br.get('generated_at')} 台北｜資料狀態：{(br.get('data_status') or {}).get('label') or 'n/a'}" + ("｜⚠️ " + "；".join(br.get("warnings") or []) if br.get("warnings") else ""))
  lines.append("")
  lines.append(f"## 結論：{v.get('emoji') or ''} {v.get('label') or 'n/a'}")
  lines.append(f"- 綜合評分 **{_num(v.get('composite'), 2, True)}**（範圍 −2 ~ +2；趨勢面 {_num(v.get('trend_score'), 2, True)}、逆勢面 {_num(v.get('contrarian_score'), 2, True)}），信心 {v.get('confidence') or 'n/a'}")
  lines.append(f"- 多空比重：偏空 {_num(cons.get('sell_pct'), 0)}% / 中性 {_num(cons.get('hold_pct'), 0)}% / 偏多 {_num(cons.get('buy_pct'), 0)}%；建議倉位上限 **{v.get('size_pct')}%**；底部檢核 {v.get('checklist')}")
  if v.get("one_liner"):
    lines.append(f"- 一句話：{v['one_liner']}")
  if v.get("regime"):
    lines.append(f"- 市場狀態：{v['regime']}")
  if ch.get("notes"):
    lines.append("- 與前一交易日相比：" + "；".join(ch["notes"]))
  lines.append("")
  lines.append("## 價格與關鍵價位")
  lines.append(f"- 收盤 {_usd(pr.get('close'))}（{_pct(pr.get('ret_1d'))}）；5 日 {_pct(pr.get('ret_5d'), 1)}、20 日 {_pct(pr.get('ret_20d'), 1)}；距 52 週高點 {_pct(pr.get('drawdown_52w_pct'), 1)}；量能 RVOL {_num(pr.get('rvol20'), 2)}x")
  lines.append(f"- 均線：20MA {_usd(lv.get('sma20'), 1)}（{_pct(lv.get('dist_sma20_pct'), 1)}）/ 50MA {_usd(lv.get('sma50'), 1)} / 200MA {_usd(lv.get('sma200'), 1)} → {lv.get('ma_structure') or 'n/a'}")
  lines.append(f"- 計畫價位：停損 {_usd(pl.get('stop_price'))}（{pl.get('stop_label') or ''}）→ 目標一 {_usd(pl.get('target1_price'))}（{pl.get('target1_label') or ''}）→ 目標二 {_usd(pl.get('target2_price'))}（{pl.get('target2_label') or ''}）；風報比 {_num(pl.get('risk_reward'), 1)}")
  nx = (o.get("nearest_expirations") or [{}])[0]
  mp_txt = f"Max Pain {_usd(nx.get('max_pain'), 0)}（{nx.get('expiration')} 到期）" if nx.get("max_pain") is not None else f"月選 Max Pain {_usd(o.get('monthly_max_pain'), 0)}"
  lines.append(f"- 期權牆：Put 牆 {_usd(o.get('put_wall'), 0)} / Call 牆 {_usd(o.get('call_wall'), 0)} / Gamma 翻正 {_usd(o.get('gamma_flip'), 1)} / {mp_txt}；淨 GEX {_num(o.get('net_gex_m'), 1)}M；P/C 成交 {_num(o.get('pc_vol_ratio'), 2)}；IV30 {_num(o.get('iv30_pct'), 0)}%")
  em = (o.get("expected_move") or {}).get("weekly") or {}
  emm = (o.get("expected_move") or {}).get("monthly") or {}
  if em or emm:
    lines.append(f"- 市場定價波動：週選 ±{_num(em.get('expected_move_pct'), 1)}%（{_usd(em.get('low'), 0)}–{_usd(em.get('high'), 0)}，{em.get('expiration')}）；月選 ±{_num(emm.get('expected_move_pct'), 1)}%（{_usd(emm.get('low'), 0)}–{_usd(emm.get('high'), 0)}）")
  wh = o.get("whale") or {}
  if wh.get("whale_net_score") is not None:
    lines.append(f"- 大戶期權（權利金 ≥ $25 萬）：{wh.get('whale_count')} 筆，淨方向 {_num(wh.get('whale_net_score'), 2, True)}（看多 ${_num(wh.get('whale_bull_prem_m'), 1)}M vs 看空 ${_num(wh.get('whale_bear_prem_m'), 1)}M）")
  lines.append("")
  lines.append("## 技術指標快照")
  t = br.get("technicals") or {}
  lines.append(f"- RSI14 {_num(t.get('rsi14'), 0)}｜MACD 柱 {_num(t.get('macd_hist'), 2, True)}｜KD {_num(t.get('k9'), 0)}/{_num(t.get('d9'), 0)}｜ADX {_num(t.get('adx14'), 0)}（+DI {_num(t.get('pdi14'), 0)} / −DI {_num(t.get('ndi14'), 0)}）｜布林 %B {_num((lv.get('bollinger') or {}).get('pct_b'), 2)}｜SuperTrend {'多' if t.get('supertrend_bull') else '空'} {_usd(t.get('supertrend'), 1)}")
  lines.append(f"- 20 日上漲/下跌量能比 {_num(t.get('up_down_vol_ratio_20d'), 2)}x｜CMF {_num(t.get('cmf20'), 2)}｜MFI {_num(t.get('mfi14'), 0)}｜技術面平均分 {_num(t.get('tech_avg_score'), 2, True)}")
  lines.append("")
  lines.append("## 情緒、廣度與宏觀")
  lines.append(f"- CNN Fear & Greed {_num(fg.get('score'), 1)}（{fg.get('rating_zh') or fg.get('rating') or 'n/a'}；前值 {_num(fg.get('previous_close'), 1)}、一週前 {_num(fg.get('week_ago'), 1)}）")
  lines.append(f"- VIX {_num(vx.get('vix'), 2)}｜VIX9D {_num(vx.get('vix9d'), 2)}｜VIX3M {_num(vx.get('vix3m'), 2)}｜VIX/VIX3M {_num(vx.get('ratio_vix_3m'), 3)}（{vx.get('term_state') or 'n/a'}）｜VVIX {_num(vx.get('vvix'), 1)}｜SKEW {_num(vx.get('skew'), 1)}（{vx.get('skew_regime') or ''}）")
  mpc = s.get("market_put_call") or {}
  lines.append(f"- 全市場 P/C {_num(mpc.get('total_pc'), 2)}、個股 P/C {_num(mpc.get('equity_pc'), 2)}（{mpc.get('equity_read') or 'n/a'}）；SOXL/SOXS 資金流 {_num((s.get('flows') or {}).get('ratio'), 1)}x")
  lines.append(f"- 16 檔成分股：站上 20MA {_num(bd.get('above_sma20_pct'), 0)}% / 50MA {_num(bd.get('above_sma50_pct'), 0)}% / 200MA {_num(bd.get('above_sma200_pct'), 0)}%；權值加權日漲跌 {_pct(bd.get('weighted_ret_1d'))}；平均 RSI {_num(bd.get('avg_rsi14'), 0)}")
  for k in (mc.get("kpis") or [])[:6]:
    lines.append(f"- {k.get('name')}: {k.get('latest')}（1 日 {k.get('chg_1d')}，20 日 {k.get('chg_20d')}；20D 相關 {_num(k.get('corr_20d'), 2, True)}）")
  lines.append("")
  lines.append("## 崩跌前兆")
  lines.append(f"- 分數 **{_num(cr.get('score'), 0)}/100**（{cr.get('zone') or 'n/a'}）；完全成立的訊號 {cr.get('n_active')} 個" + ("；主要壓力來源：" + "、".join(a.get("label") or "" for a in (cr.get("active_signals") or [])[:4]) if cr.get("active_signals") else ""))
  if cr.get("analog_reference"):
    lines.append(f"- 歷史同類情境：{cr['analog_reference']}")
  lines.append("")
  lines.append(f"## 消息面（近 7 日 利多 {n.get('bull_7d')} / 利空 {n.get('bear_7d')}，比值 {_num(n.get('bull_bear_ratio'), 2)}；共 {n.get('articles_total')} 則）")
  if n.get("themes_7d"):
    lines.append("- 主題：" + "、".join(f"{x.get('tag')} ×{x.get('count')}" for x in n["themes_7d"][:5]))
  if n.get("top_bull"):
    lines.append("- 利多：")
    lines += _rss_items_for_news(n, "top_bull")[:4]
  if n.get("top_bear"):
    lines.append("- 利空：")
    lines += _rss_items_for_news(n, "top_bear")[:4]
  lines.append("")
  lines.append("## 近期事件（14 天內）")
  if ev.get("upcoming"):
    for e in ev["upcoming"][:8]:
      lines.append(f"- {e.get('when_zh')} {e.get('label')}" + (f"：{e['detail']}" if e.get("detail") else ""))
  else:
    lines.append("- 無已知重大排程事件")
  lines.append("")
  lines.append("## 行動計畫")
  lines.append(f"- 進場：{pl.get('entry') or 'n/a'}")
  lines.append(f"- 停損：{pl.get('stop') or 'n/a'}")
  lines.append(f"- 目標：{pl.get('target') or 'n/a'}")
  for sc_ in br.get("scenarios") or []:
    lines.append(f"- {sc_.get('title')}（機率 {sc_.get('prob')}%）：{sc_.get('action')}")
  if br.get("watch"):
    lines.append("- 觀察清單：")
    lines += [f"  - {w}" for w in br["watch"][:6]]
  if q.get("one_liner"):
    lines.append("")
    lines.append(f"## 最新報價（{q.get('fetched_at_tpe')}）")
    lines.append(f"- {q['one_liner']}")
    rows = [r for r in (q.get("rows") or []) if r.get("symbol") not in ("SOXL",)][:12]
    if rows:
      lines.append("- " + "｜".join(f"{r['symbol']} {_num(r.get('last'), 2)}（{_pct(r.get('change_pct'), 2)}）" for r in rows))
  if with_links:
    lk = br.get("links") or {}
    lines.append("")
    lines.append("## 連結")
    lines.append(f"- 完整報告 {lk.get('report_html')}")
    lines.append(f"- 新手版 {lk.get('simple_html')}")
    lines.append(f"- 本簡報 JSON {lk.get('brief_json')} ・ RSS {lk.get('rss')}")
  lines.append("")
  lines.append(f"_{br.get('disclaimer')}_")
  return "\n".join(lines) + "\n"


def to_text(br: dict, max_chars: int = 900) -> str:
  v, pr, pl, o, s, cr, ch, ev = (br.get(k) or {} for k in ("verdict", "price", "plan", "options", "sentiment", "crash_risk", "changes", "events"))
  cons = v.get("consensus") or {}
  fg, vx = s.get("fear_greed") or {}, s.get("vix") or {}
  parts = [
      f"SOXL {br.get('data_as_of')} 收盤 {_usd(pr.get('close'))}（{_pct(pr.get('ret_1d'))}）",
      f"{v.get('emoji') or ''} {v.get('label') or ''}｜綜合 {_num(v.get('composite'), 2, True)}｜空 {_num(cons.get('sell_pct'), 0)}% / 中 {_num(cons.get('hold_pct'), 0)}% / 多 {_num(cons.get('buy_pct'), 0)}%｜倉位上限 {v.get('size_pct')}%",
      f"守 {_usd(pl.get('stop_price'))} → 看 {_usd(pl.get('target1_price'))} → {_usd(pl.get('target2_price'))}；Put 牆 {_usd(o.get('put_wall'), 0)} / Call 牆 {_usd(o.get('call_wall'), 0)} / Gamma 翻正 {_usd(o.get('gamma_flip'), 1)}",
      f"F&G {_num(fg.get('score'), 0)}（{fg.get('rating_zh') or ''}）｜VIX {_num(vx.get('vix'), 1)}（VIX/VIX3M {_num(vx.get('ratio_vix_3m'), 2)}）｜崩跌前兆 {_num(cr.get('score'), 0)}/100",
  ]
  if ch.get("notes"):
    parts.append("變化：" + "；".join(ch["notes"][:2]))
  if ev.get("upcoming"):
    parts.append("事件：" + "；".join(f"{e.get('when_zh')} {e.get('label')}" for e in ev["upcoming"][:3]))
  n = br.get("news") or {}
  if n.get("top_bear") or n.get("top_bull"):
    hb = (n.get("top_bull") or [{}])[0].get("title")
    hs = (n.get("top_bear") or [{}])[0].get("title")
    parts.append("頭條：" + "／".join(x for x in (f"利多「{hb}」" if hb else "", f"利空「{hs}」" if hs else "") if x))
  text = "\n".join(parts)
  return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def to_rss(entries: list[dict], links: dict) -> str:
  """RSS 2.0 with one item per archived brief (newest first)."""
  now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
  items = []
  for e in entries[:30]:
    try:
      pub = datetime.strptime(e["generated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TPE).astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    except (KeyError, TypeError, ValueError):
      pub = now
    title = f"SOXL {e.get('date')} {e.get('emoji') or ''} {e.get('verdict') or ''} 收盤 ${e.get('close')} ({e.get('ret_1d'):+.2f}%) 綜合 {e.get('composite'):+.2f}" if isinstance(e.get("ret_1d"), (int, float)) and isinstance(e.get("composite"), (int, float)) else f"SOXL {e.get('date')} {e.get('verdict') or ''}"
    link = links.get("archive_base", "") + f"{e.get('date')}.md"
    desc = html.escape(e.get("text") or "")
    items.append(f"<item><title>{html.escape(title)}</title><link>{html.escape(link)}</link><guid isPermaLink=\"false\">soxl-brief-{e.get('date')}</guid><pubDate>{pub}</pubDate><description>{desc}</description></item>")
  return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
          f"<title>SOXL Quant 每日簡報</title><link>{html.escape(links.get('index_html', ''))}</link>"
          "<description>SOXL 三倍做多半導體 ETF 每日量化評級、關鍵價位、情緒與消息面摘要（自動產生，非投資建議）</description>"
          f"<language>zh-tw</language><lastBuildDate>{now}</lastBuildDate>{''.join(items)}</channel></rss>\n")


def schema() -> dict:
  """A light JSON Schema (draft-07) for latest.json: section names + the fields an agent should rely on."""
  num = {"type": ["number", "null"]}
  return {
      "$schema": "http://json-schema.org/draft-07/schema#", "$id": SCHEMA_ID, "title": "SOXL Quant daily brief",
      "type": "object",
      "required": ["schema", "generated_at", "data_as_of", "verdict", "price", "levels", "plan", "links"],
      "properties": {
          "schema": {"const": SCHEMA_ID}, "generated_at": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS, Asia/Taipei"},
          "data_as_of": {"type": "string", "format": "date", "description": "US trading day the numbers describe"},
          "data_status": {"type": "object", "properties": {"label": {"type": ["string", "null"]}, "provisional": {"type": ["boolean", "null"]}, "final": {"type": ["boolean", "null"]}}},
          "warnings": {"type": "array", "items": {"type": "string"}, "description": "data sources that failed this run (empty = all good)"},
          "verdict": {"type": "object", "required": ["label", "composite", "size_pct"], "properties": {
              "label": {"type": ["string", "null"], "description": "強力買進 / 買進 / 觀望 / 賣出 / 減碼 / 強力賣出 (zh-TW)"}, "emoji": {"type": ["string", "null"]},
              "rating_5": {"type": ["integer", "null"], "minimum": 1, "maximum": 5, "description": "1 = strong sell … 5 = strong buy"},
              "composite": {**num, "description": "weighted score in [-2, +2]"}, "confidence": {"type": ["string", "null"]},
              "consensus": {"type": "object", "properties": {"buy_pct": num, "hold_pct": num, "sell_pct": num}},
              "size_pct": {"type": ["number", "null"], "description": "suggested max position size, % of risk capital"}, "tldr": {"type": "array", "items": {"type": "string"}}}},
          "price": {"type": "object", "properties": {"close": num, "ret_1d": num, "ret_5d": num, "ret_20d": num, "drawdown_52w_pct": num, "rvol20": num}},
          "levels": {"type": "object", "properties": {"sma20": num, "sma50": num, "sma200": num, "ma_structure": {"type": ["string", "null"]}, "ladder": {"type": "array"}}},
          "options": {"type": "object", "properties": {"put_wall": num, "call_wall": num, "gamma_flip": num, "net_gex_m": num, "pc_vol_ratio": num, "iv30_pct": num}},
          "sentiment": {"type": "object"}, "breadth": {"type": "object"}, "macro": {"type": "object"},
          "crash_risk": {"type": "object", "properties": {"score": {**num, "description": "0–100 percentile of crash-precursor load"}, "zone": {"type": ["string", "null"]}}},
          "plan": {"type": "object", "properties": {"entry": {"type": ["string", "null"]}, "stop": {"type": ["string", "null"]}, "target": {"type": ["string", "null"]}, "stop_price": num, "target1_price": num, "target2_price": num}},
          "scenarios": {"type": "array"}, "checklist": {"type": "array"}, "watch": {"type": "array", "items": {"type": "string"}},
          "news": {"type": "object", "properties": {"bull_7d": {"type": ["integer", "null"]}, "bear_7d": {"type": ["integer", "null"]}, "top_bull": {"type": "array"}, "top_bear": {"type": "array"}}},
          "events": {"type": "object", "properties": {"upcoming": {"type": "array"}, "next_fomc": {"type": ["object", "null"]}}},
          "quotes": {"type": "object", "description": "live snapshot at generation time (not the official close)"},
          "changes": {"type": "object", "properties": {"verdict_changed": {"type": ["boolean", "null"]}, "composite_delta": num, "same_verdict_streak_days": {"type": "integer"}, "notes": {"type": "array"}}},
          "history": {"type": "array"}, "links": {"type": "object"}, "disclaimer": {"type": "string"},
      },
  }


# --------------------------------------------------------------------------- #
# write everything
# --------------------------------------------------------------------------- #
def write_all(br: dict) -> dict:
  FEED_DIR.mkdir(parents=True, exist_ok=True)
  md = to_markdown(br)
  txt = to_text(br)
  day = br.get("data_as_of") or datetime.now().strftime("%Y-%m-%d")
  paths = {
      "json": FEED_DIR / "latest.json", "md": FEED_DIR / "latest.md", "txt": FEED_DIR / "latest.txt",
      "day_json": FEED_DIR / f"{day}.json", "day_md": FEED_DIR / f"{day}.md",
      "index": FEED_DIR / "index.json", "rss": FEED_DIR / "rss.xml", "schema": FEED_DIR / "schema.json", "quotes": FEED_DIR / "quotes.json",
  }
  blob = json.dumps(br, ensure_ascii=False, indent=1) + "\n"
  fsio.atomic_write_text(paths["json"], blob)
  fsio.atomic_write_text(paths["day_json"], blob)
  fsio.atomic_write_text(paths["md"], md)
  fsio.atomic_write_text(paths["day_md"], md)
  fsio.atomic_write_text(paths["txt"], txt + "\n")
  fsio.atomic_write_text(paths["schema"], json.dumps(schema(), ensure_ascii=False, indent=1) + "\n")
  if br.get("quotes"):
    fsio.atomic_write_text(paths["quotes"], json.dumps(br["quotes"], ensure_ascii=False, indent=1) + "\n")
  # archive index (newest first) + prune
  entries: dict[str, dict] = {}
  if paths["index"].exists():
    try:
      for e in json.loads(paths["index"].read_text(encoding="utf-8")).get("entries", []):
        if e.get("date"):
          entries[e["date"]] = e
    except (json.JSONDecodeError, OSError, AttributeError):
      entries = {}
  v, pr = br.get("verdict") or {}, br.get("price") or {}
  entries[day] = {"date": day, "generated_at": br.get("generated_at"), "verdict": v.get("label"), "emoji": v.get("emoji"), "rating_5": v.get("rating_5"),
                  "composite": v.get("composite"), "size_pct": v.get("size_pct"), "close": pr.get("close"), "ret_1d": pr.get("ret_1d"),
                  "crash_risk": (br.get("crash_risk") or {}).get("score"), "text": txt, "json": f"{day}.json", "md": f"{day}.md"}
  ordered = [entries[k] for k in sorted(entries, reverse=True)]
  for stale in ordered[ARCHIVE_KEEP:]:
    for f in (FEED_DIR / f"{stale['date']}.json", FEED_DIR / f"{stale['date']}.md"):
      try:
        f.unlink(missing_ok=True)
      except OSError:
        pass
  ordered = ordered[:ARCHIVE_KEEP]
  links = br.get("links") or {}
  fsio.atomic_write_text(paths["index"], json.dumps({"schema": SCHEMA_ID, "latest": day, "count": len(ordered), "entries": ordered}, ensure_ascii=False, indent=1) + "\n")
  fsio.atomic_write_text(paths["rss"], to_rss(ordered, {"index_html": links.get("index_html", ""), "archive_base": (links.get("brief_md", "").rsplit("/", 1)[0] + "/") if links.get("brief_md") else ""}))
  return {k: str(v) for k, v in paths.items()}


def load_latest() -> dict | None:
  p = FEED_DIR / "latest.json"
  if not p.exists():
    return None
  try:
    return json.loads(p.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError):
    return None
