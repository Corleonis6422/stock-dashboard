#!/usr/bin/env python3
"""Agent brief — the machine- and LLM-friendly digest of one pipeline run.

Everything a downstream agent (Muse, Gemini, Claude, a Slack bot …) needs in one
small, stable document, produced in three shapes from the same dict:

* ``feed/latest.json``   compact JSON (schema ``soxl-quant-brief/2``) — ~50 KB, flat
                         sections, no SVG / chart series, nothing secret.  v2 adds
                         ``trade_plan`` (explicit entry / stop / targets / R:R / size /
                         time stop / invalidation), ``signals`` (validated signal library
                         with win rate, base rate, p-value, grade, today's state) and
                         ``validation`` (method, regime grid, multiple-testing summary);
                         every v1 field is still present
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
SCHEMA_ID = "soxl-quant-brief/2"
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


FLAG_ZH = {"geo_escalation_24h": "地緣風險升溫", "tariff_shock_24h": "關稅 / 出口管制收緊", "capex_warning_24h": "龍頭資本支出轉弱",
           "fed_statement_24h": "聯準會剛公布決議", "fed_hawkish_24h": "聯準會偏鷹"}


def _beginner_block(sc: dict, b: dict, tp: dict, plan: dict, flash: dict | None, ev_list: list[dict], today_ews: dict, tech: dict) -> dict:
  """One answer (buy / wait / no), one price to watch, one holder rule, one risk line.  Plan first, rating second."""
  r5 = sc.get("rating_5")
  label = sc.get("rating_label") or b.get("verdict") or "n/a"
  tp = tp or {}
  side = tp.get("side")
  ent, st, sz, t1, hold = (tp.get(k) or {} for k in ("entry", "stop", "size", "t1", "holder"))
  ep, rule = ent.get("price"), (ent.get("rule") or "")
  stop_p = st.get("price") if tp else plan.get("stop_price")
  basis = f"trade_plan.side={side or 'n/a'}, rating_5={r5}, rr_blend={tp.get('rr_blend')}"
  if side == "long" and tp.get("tradeable"):
    ans, emo = "可以買", "✅"
    text = f"驗證過的買訊今天成立（{rule}）。進場 {_usd(ep)}，倉位上限 {sz.get('pct')}%，停損 {_usd(stop_p)}（{_pct(st.get('dist_pct'), 1)}），第一目標 {_usd(t1.get('price'))}。"
    watch = {"label": "停損，唯一出場價", "price": stop_p}
  elif side == "long":
    ans, emo = "先別買，等更好的價位", "⏸"
    text = f"買訊成立但風報比只有 {_num(tp.get('rr_blend'), 1)}R（門檻 {_num(tp.get('min_rr'), 1)}R）。" + (f"同樣的停損與目標，進場價 ≤ {_usd(tp.get('trade_if_entry'))} 才值得。" if tp.get("trade_if_entry") else "等回檔。")
    watch = {"label": "值得進場的價位", "price": tp.get("trade_if_entry") or ep}
  elif side == "long_pending":
    ans, emo = "先別買，等觸發", "⏳"
    text = f"買點還沒成立：{rule}。成立後次日開盤才進，倉位 {sz.get('if_triggered_pct')}%，停損 {_usd(stop_p)}。今天不追。"
    watch = {"label": "買點觸發價，收盤站上才算", "price": ep}
  elif r5 is not None and r5 <= 2:
    ans, emo = "不該買", "❌"
    text = f"評級「{label}」，沒有驗證過的買點，今天不開新倉。" + (f"要等的條件：{rule}（到了也只用 {sz.get('if_triggered_pct')}% 試單）。" if ep and tp else "")
    watch = {"label": "條件買點，收盤站上才算", "price": ep}
  elif r5 == 3:
    ans, emo = "先別買，等確認", "⏸"
    text = f"評級「{label}」：多空因子打平，沒有買訊。" + (f"等 {rule} 再說。" if rule else "")
    watch = {"label": "條件買點，收盤站上才算", "price": ep}
  elif r5 is not None:
    ans, emo = ("可以分批小量" if r5 == 4 else "可以買"), ("🟢" if r5 == 4 else "✅")
    text = f"評級「{label}」偏多，但今天沒有驗證過的買訊成立：{b.get('q_no_position') or '只能小量分批，照計畫停損。'}"
    watch = {"label": "停損，唯一出場價", "price": stop_p}
  else:
    ans, emo, text = "資料不足", "⚪", "今天缺少評級或計畫，等下一次更新。"
    watch = {"label": "n/a", "price": None}
  holder_txt = (f"硬停損 {_usd(hold.get('hard_stop'))}（{hold.get('hard_stop_label')}）；{hold.get('trail_note')}" if hold else (b.get("q_holder") or "守停損，不加碼。"))
  if hold and hold.get("reduce_into"):
    holder_txt += "；反彈到 " + " / ".join(_usd(r.get("price")) for r in hold["reduce_into"][:2]) + " 先減碼"
  risks = [f"{e.get('when_zh')} {e.get('label')}" for e in ev_list if (e.get("days_ahead") or 99) <= 2]
  for c in (flash or {}).get("cautions") or []:
    evd = c.get("evidence") or {}
    t = str(evd.get("title") or "")
    risks.append(f"{FLAG_ZH.get(c.get('flag'), c.get('flag'))}（{evd.get('publisher')}：{t if len(t) <= 72 else t[:70].rstrip() + '…'}）")
  cr = today_ews.get("score")
  if cr is not None and cr >= 60:
    risks.append(f"崩跌前兆分數 {cr:.0f}/100（≥ 60 注意）")
  biggest = (flash or {}).get("beginner_line") or "今日時事模組沒有資料（見 warnings）。"
  return {
      "buy": {"answer": ans, "emoji": emo, "text": text, "basis": basis},
      "biggest_thing": biggest, "flash_label": (flash or {}).get("label"),
      "holder": holder_txt, "watch": watch, "risk_48h": risks or ["無排定事件，也沒有新聞旗標。"],
      "lines": [
          f"現在該不該買？{emo} {ans}。{text}",
          biggest,
          f"已持有的人：{holder_txt}。",
          (f"明天只盯一個價：{_usd(watch['price'])}（{watch['label']}）。" if watch.get("price") else "明天沒有單一關鍵價位。"),
          "48 小時內風險：" + "；".join(risks or ["無"]) + "。",
      ],
  }

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

  # ---- v2: validated signals + explicit trade plan (absent when the pipeline could not run the backtest)
  bt = p.get("backtest") or {}
  tp = p.get("trade_plan") or {}
  sig_rows = []
  for s in bt.get("signals") or []:
    td = s.get("today") or {}
    pend = td.get("pending") or {}
    sig_rows.append({
        "key": s.get("key"), "short_name": s.get("short_name"), "name": s.get("name"), "family": s.get("family"), "side": s.get("side"), "horizon": s.get("horizon"), "rule": s.get("rule"),
        "n": s.get("n"), "win_pct": s.get("win_pct"), "ci": s.get("ci"), "base_win_pct": (s.get("base") or {}).get("win_pct"), "edge_pts": s.get("edge_pts"),
        "mean": s.get("mean"), "pf": s.get("pf"), "p_value": s.get("p_value"), "q_value": s.get("q_value"), "significant": s.get("significant"),
        "is_win_pct": (s.get("is") or {}).get("win_pct"), "oos_win_pct": (s.get("oos") or {}).get("win_pct"), "oos_n": (s.get("oos") or {}).get("n"),
        "grade": s.get("grade"), "grade_zh": s.get("grade_zh"), "stop_k_atr": (s.get("stop") or {}).get("k_atr"),
        "sim_oos": {k: (s.get("sim") or {}).get(k) for k in ("n", "win_pct", "expectancy_r")} if s.get("sim") else None,
        "dyn": ({k: (s.get("dyn") or {}).get(k) for k in ("n", "win_pct", "base_win_pct", "mean", "avg_bars", "p_value", "exit_rule")} if s.get("dyn") else None),
        "dd15": s.get("dd15"), "state": td.get("state"), "fired": td.get("fired"), "recent_dates": td.get("recent_dates"),
        "pending": ({k: pend.get(k) for k in ("price", "op", "dist_pct", "needs")} if pend else None), "last_signal": s.get("last_signal"),
    })
  validation = ({
      "method": bt.get("method"), "summary": bt.get("summary"), "skipped": bt.get("skipped"),
      "regime_grid": [{"series": g.get("series"), "band_pct": g.get("band_pct"), "confirm_days": g.get("confirm_days"), "cagr_pct": (g.get("strategy") or {}).get("cagr_pct"),
                       "max_dd_pct": (g.get("strategy") or {}).get("max_dd_pct"), "switches": g.get("switches"), "time_in_market_pct": g.get("time_in_market_pct"),
                       "in_market": (g.get("today") or {}).get("in_market"), "dist_pct": (g.get("today") or {}).get("dist_pct")} for g in ((bt.get("regime") or {}).get("grid") or [])],
      "buy_hold": ((bt.get("regime") or {}).get("sma200") or {}).get("buy_hold"), "regime_note": (bt.get("regime") or {}).get("note"),
      "atr14": bt.get("atr14"), "atr_pct": bt.get("atr_pct"),
  } if bt else None)

  # ---- v2.1: breaking-news flash (last 36 h) + the beginner block (one answer, one price, one risk line)
  fl = p.get("newsflash") or {}
  flash = ({
      "as_of_tpe": fl.get("fetched_at_tpe"), "window_h": fl.get("window_h"), "label": fl.get("label"), "net": fl.get("net"), "n_relevant": fl.get("n_relevant"),
      "beginner_line": fl.get("beginner_line"), "top": (fl.get("top") or [])[:8], "more": (fl.get("more") or [])[:12],
      "flags": fl.get("flags") or {}, "flag_evidence": fl.get("flag_evidence") or {}, "cautions": fl.get("cautions") or [],
      "by_category": fl.get("by_category") or [], "seeking_alpha": (fl.get("seeking_alpha") or [])[:8], "method": fl.get("method"), "errors": fl.get("errors") or [],
  } if fl else None)
  beginner = _beginner_block(sc, b, tp, plan, flash, ev_list, today_ews, tech)
  dash = p.get("dashboard") or None

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
      "trade_plan": (tp or None), "signals": sig_rows, "validation": validation,
      "beginner": beginner, "flash": flash, "dashboard": dash,
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


def _state_zh(state: str | None) -> str:
  return {"fired": "🔴 今日觸發", "recent": "🟠 10 日內觸發", "pending": "⏳ 待觸發", "off": "⚪ 未觸發"}.get(state or "", "⚪ 未觸發")


def _ladder_rows(br: dict, n_each: int = 3) -> list[dict]:
  """3 resistances above, the close, 3 supports below (top-down), each with distance to spot."""
  lv = br.get("levels") or {}
  spot = (br.get("price") or {}).get("close") or 0
  ladder = lv.get("ladder") or []
  res = [r for r in ladder if r.get("kind") == "res" and r.get("price") and r["price"] > spot][-n_each:]
  sup = [r for r in ladder if r.get("kind") == "sup" and r.get("price") and r["price"] < spot][:n_each]
  rows = [dict(r, dist=(r["price"] / spot - 1.0) * 100.0 if spot else None) for r in res]
  rows.append({"price": spot, "label": "現價", "kind": "cur", "dist": 0.0})
  rows += [dict(r, dist=(r["price"] / spot - 1.0) * 100.0 if spot else None) for r in sup]
  return rows


def _history_check(hist: list[dict]) -> tuple[int, int, str]:
  """Direction hits of past verdicts vs their realised 5-day return (rating 3 = no call, skipped)."""
  hits = n = 0
  for h in hist or []:
    r5, rating = h.get("fwd_ret_5d"), h.get("rating_5")
    if r5 is None or rating is None or rating == 3:
      continue
    n += 1
    hits += 1 if ((rating >= 4 and r5 > 0) or (rating <= 2 and r5 <= 0)) else 0
  if not n:
    first = next((h.get("date") for h in hist or [] if h.get("date")), None)
    return 0, 0, f"尚無 5 日後結果可對照（評級紀錄自 {first or 'n/a'} 起，第一個結果要等 5 個交易日）"
  return hits, n, f"最近 {n} 次有結果的評級，方向正確 {hits}/{n}（{hits / n * 100:.0f}%）"


def to_markdown(br: dict, with_links: bool = True) -> str:
  v, pr, lv, o, s, cr, n, pl, ch, ev = (br.get(k) or {} for k in ("verdict", "price", "levels", "options", "sentiment", "crash_risk", "news", "plan", "changes", "events"))
  fg, vx, bd = s.get("fear_greed") or {}, s.get("vix") or {}, br.get("breadth") or {}
  cons = v.get("consensus") or {}
  tp = br.get("trade_plan") or {}
  sigs = br.get("signals") or []
  val = br.get("validation") or {}
  summ = val.get("summary") or {}
  tech = br.get("technicals") or {}
  spot = pr.get("close") or 0
  L: list[str] = []
  wd = br.get("data_as_of_zh", "").split("（")[-1].rstrip("）")
  L.append(f"# SOXL {br.get('data_as_of')}（{wd}）收盤 · {v.get('emoji') or ''} {v.get('label') or 'n/a'} · {_usd(pr.get('close'))}（{_pct(pr.get('ret_1d'))}）")
  L.append(f"> {(br.get('data_status') or {}).get('label') or 'n/a'} · 產生 {br.get('generated_at')} 台北 · 自動計算的研究參考，不是投資建議 · 三倍槓桿單日可 ±15%"
           + ("｜⚠️ 資料降級：" + "；".join(br.get("warnings") or []) if br.get("warnings") else ""))
  L.append("")
  L.append(f"**TL;DR** {v.get('one_liner') or ''} 綜合 **{_num(v.get('composite'), 2, True)}**（−2 ~ +2）· 多/中/空 {_num(cons.get('buy_pct'), 0)}%/{_num(cons.get('hold_pct'), 0)}%/{_num(cons.get('sell_pct'), 0)}% · 信心 {v.get('confidence') or 'n/a'} · 倉位上限 **{v.get('size_pct')}%** · 底部檢核 {v.get('checklist')}")
  if ch.get("notes"):
    L.append(f"與前一交易日：{'；'.join(ch['notes'])}")
  L.append("")

  # ---------------------------------------------------------------- beginner block (one screen)
  bg = br.get("beginner") or {}
  if bg:
    L.append("## 新手一眼看懂")
    buy = bg.get("buy") or {}
    L.append(f"- **現在該不該買？** {buy.get('emoji') or ''} **{buy.get('answer') or 'n/a'}**。{buy.get('text') or ''}")
    L.append(f"- **今天最大的事：** {str(bg.get('biggest_thing') or '').replace('今天最大的事：', '', 1)}")
    L.append(f"- **已持有的人：** {bg.get('holder')}")
    w = bg.get("watch") or {}
    if w.get("price"):
      L.append(f"- **明天只盯一個價：** {_usd(w['price'])}（{w.get('label')}）")
    L.append(f"- **48 小時內風險：** {'；'.join(bg.get('risk_48h') or ['無'])}")
    L.append("")

  # ---------------------------------------------------------------- six gauges (add-on? macro, SOXX, whales, put/call, crash)
  dash = br.get("dashboard") or {}
  if dash.get("gauges"):
    L.append("## 六個儀表（能不能加碼、宏觀、費半、大戶、Put/Call、崩跌）")
    L.append("| 儀表 | 燈 | 讀數 | 一句話 |")
    L.append("|---|---|---|---|")
    for g in dash["gauges"]:
      meaning = str(g.get("meaning") or "").replace("|", "／")
      first = meaning.split("。")[0]
      L.append(f"| {g.get('title')} | {g.get('emoji')} | {str(g.get('value') or '').replace('|', '／')} | {first}{'。' if first and not first.endswith('。') else ''} |")
    for g in dash["gauges"]:
      if g.get("key") in ("soxx", "whales") and g.get("detail"):
        L.append(f"- {g.get('title')}：{g['detail']}")
    grades = dash.get("factor_grades") or []
    if grades:
      L.append("- 因子等級（借 Seeking Alpha 的 A+ … F 寫法，分數來自 24 因子評分表）：" + " · ".join(f"{x.get('short')} **{x.get('grade')}**" for x in grades) + f" → 總評 **{dash.get('overall_grade')}**")
    vc = dash.get("voices") or {}
    if vc.get("rows"):
      L.append(f"- {vc.get('summary')}：" + "；".join(f"{str(r.get('voice') or '').split('（')[0]} {r.get('reading')}" for r in vc["rows"]))
    L.append("")

  # ---------------------------------------------------------------- breaking news (last 36 h)
  fl = br.get("flash") or {}
  if fl:
    L.append(f"## 今日時事（過去 {fl.get('window_h') or 36} 小時，對 SOXL 的影響）")
    cats = "、".join(f"{c.get('emoji') or ''}{c.get('category')} {c.get('neg')}空/{c.get('pos')}多" for c in (fl.get("by_category") or [])[:4])
    L.append(f"- 新聞氣壓 **{fl.get('label') or 'n/a'}**（淨影響 {_num(fl.get('net'), 2, True)}，{fl.get('n_relevant')} 則，抓取 {fl.get('as_of_tpe')} 台北）：{cats}")
    for r in (fl.get("top") or [])[:6]:
      imp = r.get("impact") or 0
      dot = "🔴" if imp < 0 else ("🟢" if imp > 0 else "⚪")
      why_short = str(r.get("why_zh") or "").split("：")[0]
      L.append(f"- {dot} {r.get('emoji') or ''} {r.get('category')}（{r.get('time_tpe')}，{r.get('publisher')}）{r.get('title')} → {why_short}")
    sa = fl.get("seeking_alpha") or []
    if sa:
      L.append("- Seeking Alpha（SOXL / SOXX / NVDA 近 72 小時；連結在 JSON `flash.seeking_alpha[].link`）：" + "；".join(f"{t.get('tone')}「{t.get('title')}」（{t.get('kind')}）" for t in sa[:3]))
    for c in (fl.get("cautions") or [])[:3]:
      L.append(f"- ⚠️ {c.get('text')}")
    if fl.get("errors"):
      L.append(f"- 來源部分失敗：{'；'.join(str(e) for e in fl['errors'][:2])}")
    L.append("")

  # ---------------------------------------------------------------- trade plan
  L.append("## 交易計畫")
  if tp:
    st, t1, t2, sz, ts = tp.get("stop") or {}, tp.get("t1") or {}, tp.get("t2") or {}, tp.get("size") or {}, tp.get("time_stop") or {}
    en = tp.get("entry") or {}
    L.append(f"**{tp.get('headline')}**")
    L.append("")
    L.append("| 欄位 | 值 |")
    L.append("|---|---|")
    L.append(f"| 進場 | {en.get('rule')} |")
    L.append(f"| 停損 | **{_usd(st.get('price'))}**（{_pct(st.get('dist_pct'), 1)}；{'結構支撐' if st.get('kind') == 'structural' else str(st.get('k_atr')) + '×ATR'}；新倉與舊倉唯一的出場價） |")
    L.append(f"| 目標 T1 | {_usd(t1.get('price'))}（{t1.get('label')}，{_num(t1.get('rr'), 2)}R） |")
    L.append(f"| 目標 T2 | {_usd(t2.get('price'))}（{t2.get('label')}，{_num(t2.get('rr'), 2)}R） |")
    gate = "✅ 達標" if (tp.get("rr_blend") or 0) >= (tp.get("min_rr") or 1.5) else f"❌ 不足，進場價需 ≤ {_usd(tp.get('trade_if_entry'))}"
    L.append(f"| 風報比 | 加權 {_num(tp.get('rr_blend'), 2)}R（門檻 {tp.get('min_rr')}R）{gate} |")
    L.append(f"| 倉位 | {'觸發後 ' if tp.get('side') == 'no_trade' else ''}{sz.get('if_triggered_pct')}% 帳戶（每筆風險 {sz.get('risk_per_trade_pct')}% ÷ 停損距離；評級上限 {_num(sz.get('verdict_cap_pct'), 0)}%）；連續 3 次停損 = {sz.get('three_stops_pct')}% |")
    L.append(f"| 時間停損 | {ts.get('rule')} |")
    L.append(f"| 失效條件 | {'；'.join(tp.get('invalidation') or [])} |")
    for e in (tp.get("explain") or [])[:3]:
      L.append(f"- {e}")
    hd = tp.get("holder") or {}
    L.append("")
    L.append("**已持有者**")
    if hd.get("verdict_action"):
      L.append(f"- {hd['verdict_action']}")
    L.append(f"- 硬停損 {_usd(hd.get('hard_stop'))}（{hd.get('hard_stop_label')}）；{hd.get('trail_note')}")
    if hd.get("reduce_into"):
      L.append("- 減碼點：" + "、".join(f"{_usd(r.get('price'))}（{r.get('label')}）" for r in hd["reduce_into"]))
    L.append(f"- {hd.get('edge_note')}" + (f" 近 10 日觸發的賣出訊號：{'、'.join(hd.get('exit_signals_recent') or [])}" if hd.get("exit_signals_recent") else ""))
  else:
    L.append(f"- 進場：{pl.get('entry') or 'n/a'}")
    L.append(f"- 停損：{pl.get('stop') or 'n/a'}")
    L.append(f"- 目標：{pl.get('target') or 'n/a'}（風報比 {_num(pl.get('risk_reward'), 1)}）")
  L.append("")

  # ---------------------------------------------------------------- levels
  L.append("## 關鍵價位（由上而下）")
  L.append("| 價位 | 類型 | 來源 | 距現價 |")
  L.append("|---|---|---|---|")
  spot_gap = ((o.get("cboe_spot") or 0) / spot - 1.0) * 100.0 if (spot and o.get("cboe_spot")) else 0.0
  iv_stale = abs(spot_gap) >= 2.0
  iv_words = ("1σ", "Gamma", "Max Pain")
  for r in _ladder_rows(br):
    kind = {"res": "壓力", "sup": "支撐", "cur": "現價"}.get(r.get("kind"), "")
    parts = (r.get("label") or "").split(" / ")
    lbl = " / ".join(parts[:2]) if r.get("kind") != "cur" else f"{br.get('data_as_of')} 收盤"
    if iv_stale and r.get("kind") != "cur" and any(w in lbl for w in iv_words):
      lbl += " ※"
    bold = "**" if r.get("kind") == "cur" else ""
    L.append(f"| {bold}{_usd(r.get('price'))}{bold} | {kind} | {lbl} | {_pct(r.get('dist'), 1) if r.get('kind') != 'cur' else '—'} |")
  if iv_stale:
    L.append(f"※ 以 CBOE 即時價 {_usd(o.get('cboe_spot'))} 為中心推算（與收盤差 {spot_gap:+.1f}%）；1σ 區間與 Gamma 翻正位會在下次更新隨開盤價重算，履約價型的牆不受影響。")
  em = (o.get("expected_move") or {}).get("weekly") or {}
  emm = (o.get("expected_move") or {}).get("monthly") or {}
  spot_note = f"；期權區以 CBOE 即時價 {_usd(o.get('cboe_spot'))} 為中心，與收盤差 {spot_gap:+.1f}%" if iv_stale else ""
  L.append(f"- 期權牆：Put 牆 {_usd(o.get('put_wall'), 0)} / Call 牆 {_usd(o.get('call_wall'), 0)} / Gamma 翻正 {_usd(o.get('gamma_flip'), 1)}；淨 GEX {_num(o.get('net_gex_m'), 1)}M、P/C 成交 {_num(o.get('pc_vol_ratio'), 2)}、IV30 {_num(o.get('iv30_pct'), 0)}%（CBOE 延遲鏈 {o.get('chain_timestamp') or 'n/a'}；牆是以未平倉推算的模型值，不是觀察到的造市商部位{spot_note}）")
  if em:
    L.append(f"- 期權定價波動：週選 ±{_num(em.get('expected_move_pct'), 1)}% → {_usd(em.get('low'), 0)} 到 {_usd(em.get('high'), 0)}（{em.get('expiration')}）；月選 ±{_num(emm.get('expected_move_pct'), 1)}% → {_usd(emm.get('low'), 0)} 到 {_usd(emm.get('high'), 0)}")
  L.append(f"- 均線：20MA {_usd(lv.get('sma20'), 1)}（{_pct(lv.get('dist_sma20_pct'), 1)}）/ 50MA {_usd(lv.get('sma50'), 1)} / 200MA {_usd(lv.get('sma200'), 1)}（{_pct(lv.get('dist_sma200_pct'), 1)}）→ {lv.get('ma_structure') or 'n/a'}")
  L.append(f"- 波動：ATR14 {_pct(pr.get('atr_pct'), 1, False)}（一天正常波動的尺度，停損距離由它決定）、量能 RVOL {_num(pr.get('rvol20'), 2)}x、20 日實現波動率 {_num(pr.get('realized_vol_20d_pct'), 0)}%")
  L.append("")

  # ---------------------------------------------------------------- signals
  if sigs:
    meth = val.get("method") or {}
    L.append(f"## 訊號驗證（{meth.get('sample') or ''}，非重疊交易，勝率旁為同期基準）")
    L.append("| 訊號 | 勝率 vs 基準（N） | 平均報酬 | 狀態 |")
    L.append("|---|---|---|---|")
    grade_rank = {"A": 0, "B*": 1, "B": 2, "C": 3, "—": 4}
    graded = [x for x in sigs if (x.get("n") or 0) >= 20 or x.get("state") in ("fired", "recent", "pending")]
    graded.sort(key=lambda x: (0 if x.get("state") == "fired" else 1, grade_rank.get(x.get("grade"), 4), x.get("p_value") or 1.0))
    for x in graded[:8]:
      side = "買" if x.get("side") == "long" else "賣"
      tag = f"{x.get('grade')}" + ("★" if x.get("significant") else "")
      st_txt = _state_zh(x.get("state"))
      if x.get("state") == "pending" and x.get("pending"):
        st_txt += f" {x['pending'].get('op') or ''}{_usd(x['pending'].get('price'))}"
      dyn = x.get("dyn") or {}
      dyn_txt = f"；動態出場 {_num(dyn.get('win_pct'), 0)}% vs {_num(dyn.get('base_win_pct'), 0)}%" if dyn and dyn.get("win_pct") is not None else ""
      L.append(f"| {side} {x.get('short_name')} [{tag}] | {_num(x.get('win_pct'), 0)}% vs {_num(x.get('base_win_pct'), 0)}%（{x.get('n')}）{dyn_txt} | {_pct(x.get('mean'), 1)} / {x.get('horizon')} 日 | {st_txt} |")
    L.append(f"- 買進訊號的勝率 = 訊號後 h 日收高的比例，賣出訊號的勝率 = 收低的比例；等級 A 可靠、B 尚可、B* 顯著但樣本外薄、C 無優勢；★ = 顯著高於基準（p < 0.05）。{summ.get('n_graded')} 個有樣本的訊號中 {summ.get('n_significant')} 個顯著，經多重檢定校正（BH q < 0.10）剩 {summ.get('n_q_lt_10')} 個。")
    L.append(f"- 賣出訊號：{'歷史上沒有一個的命中率高於基準，也沒有一個能預測 20 日內 ≥15% 的回撤 → 停損是保險，不是預測。' if not summ.get('exits_predictive') else '有預測力的：' + '、'.join(summ['exits_predictive'])} 反轉買點用「收盤站上 5 日線」出場時，勝率基準本身就是 {_num(summ.get('dyn_base_win_pct'), 0)}%，請以該基準比較。")
    grid = val.get("regime_grid") or []
    own = next((g for g in grid if g.get("series") == "SOXL" and g.get("band_pct") == 0.0), None)
    idx = next((g for g in grid if g.get("series") != "SOXL" and g.get("band_pct") == 3.0 and g.get("confirm_days") == 2), None)
    bh = val.get("buy_hold") or {}
    if own and idx:
      L.append(f"- 200 日線濾網（{meth.get('sample', '')[:7]} 起，無成本）：SOXL 自身 → {'持有' if own.get('in_market') else '空手'}（距年線 {_pct(own.get('dist_pct'), 1)}；年化 {_num(own.get('cagr_pct'), 1)}%、切換 {own.get('switches')} 次）；{idx.get('series')} 指數 ±3% 帶 2 日確認 → {'持有' if idx.get('in_market') else '空手'}（距年線 {_pct(idx.get('dist_pct'), 1)}；年化 {_num(idx.get('cagr_pct'), 1)}%、最大回撤 {_num(idx.get('max_dd_pct'), 1)}%、切換 {idx.get('switches')} 次）；買進抱牢 年化 {_num(bh.get('cagr_pct'), 1)}%、最大回撤 {_num(bh.get('max_dd_pct'), 1)}%。{'兩種讀法今天不一致。' if own.get('in_market') != idx.get('in_market') else ''}")
    L.append("")

  # ---------------------------------------------------------------- crash + events + what changes my mind
  L.append("## 崩跌前兆")
  zone = (cr.get("zone") or "n/a").split("；")[0]
  L.append(f"- 分數 **{_num(cr.get('score'), 0)}/100**（{zone}；≥60 注意、≥80 警戒）；完全成立 {cr.get('n_active')} 項" + (("；主要壓力來源：" + "、".join((a.get("label") or "") for a in (cr.get("active_signals") or [])[:3])) if cr.get("active_signals") else ""))
  es = ((cr.get("event_study") or {}).get("stats_top_80") or {})
  if es.get("precision_pct") is not None:
    L.append(f"- 分數 ≥80 的歷史命中率 {_num(es.get('precision_pct'), 0)}%（基準 {_num(es.get('base_rate_pct'), 0)}%，提升 {_num(es.get('lift'), 1)}x）" + (f"；歷史同類情境：{cr.get('analog_reference')}" if cr.get("analog_reference") else ""))
  L.append("")
  L.append("## 48 小時內事件")
  up = ev.get("upcoming") or []
  near = [e for e in up if (e.get("days_ahead") or 99) <= 2]
  if near:
    for e in near:
      L.append(f"- {e.get('when_zh')} {e.get('label')}" + (f"：{e['detail']}" if e.get("detail") else ""))
  else:
    L.append("- 無。")
  later = [e for e in up if (e.get("days_ahead") or 99) > 2][:5]
  if later:
    L.append("- 14 天內：" + "；".join(f"{e.get('when_zh')} {e.get('label')}" for e in later))
  L.append("")
  L.append("## 什麼會改變結論")
  checks = br.get("checklist") or []
  missing = [c for c in checks if not c.get("ok") and "20 日均線" not in str(c.get("item"))][:2]
  L.append(f"- 轉多：收盤站回 20MA {_usd(lv.get('sma20'))}" + ("；再加上 " + "；".join(f"{str(c.get('item', '')).split(' (')[0]}（目前 {c.get('now')}）" for c in missing) if missing else ""))
  st_price = (tp.get("stop") or {}).get("price") if tp else pl.get("stop_price")
  L.append(f"- 轉更空：收盤 < {_usd(st_price)}；VIX/VIX3M ≥ 1.0（目前 {_num(vx.get('ratio_vix_3m'), 3)}）；崩跌前兆分數 ≥ 80（目前 {_num(cr.get('score'), 0)}）")
  L.append(f"- 資料風險：{'；'.join(br.get('warnings') or []) or '無'}；期權牆與 GEX 為模型推算、每日 OI 結算後重算")
  L.append("")

  # ---------------------------------------------------------------- sentiment + breadth (compact; put/call + whales live in the gauges when present)
  L.append("## 情緒、廣度與籌碼")
  L.append(f"- CNN Fear & Greed {_num(fg.get('score'), 1)}（{fg.get('rating_zh') or fg.get('rating') or 'n/a'}；前值 {_num(fg.get('previous_close'), 1)}）｜VIX {_num(vx.get('vix'), 2)} / VIX3M {_num(vx.get('vix3m'), 2)} → {_num(vx.get('ratio_vix_3m'), 3)}（{vx.get('term_state') or 'n/a'}）｜SKEW {_num(vx.get('skew'), 1)}｜VVIX {_num(vx.get('vvix'), 1)}")
  if not dash.get("gauges"):
    mpc = s.get("market_put_call") or {}
    wh = o.get("whale") or {}
    L.append(f"- 全市場 P/C {_num(mpc.get('total_pc'), 2)}、個股 P/C {_num(mpc.get('equity_pc'), 2)}；大戶期權 {wh.get('whale_count')} 筆 淨方向 {_num(wh.get('whale_net_score'), 2, True)}（多 ${_num(wh.get('whale_bull_prem_m'), 1)}M / 空 ${_num(wh.get('whale_bear_prem_m'), 1)}M）；SOXL/SOXS 資金流 {_num((s.get('flows') or {}).get('ratio'), 1)}x")
  L.append(f"- 16 檔成分股站上 20MA {_num(bd.get('above_sma20_pct'), 0)}% / 50MA {_num(bd.get('above_sma50_pct'), 0)}% / 200MA {_num(bd.get('above_sma200_pct'), 0)}%；權值加權日漲跌 {_pct(bd.get('weighted_ret_1d'))}；RSI14 {_num(tech.get('rsi14'), 0)}、MACD 柱 {_num(tech.get('macd_hist'), 2, True)}、KD {_num(tech.get('k9'), 0)}/{_num(tech.get('d9'), 0)}")
  L.append("")

  # ---------------------------------------------------------------- news (no URLs here; links live in JSON news.top_bull[].link)
  L.append(f"## 消息面（近 7 日 利多 {n.get('bull_7d')} / 利空 {n.get('bear_7d')}，比值 {_num(n.get('bull_bear_ratio'), 2)}）")
  if n.get("themes_7d"):
    L.append("- 主題：" + "、".join(f"{x.get('tag')} ×{x.get('count')}" for x in n["themes_7d"][:4]))
  k_news = 2 if dash.get("gauges") else 3
  for h in (n.get("top_bull") or [])[:k_news]:
    L.append(f"- 多 - {h.get('title')}（{h.get('publisher')}）")
  for h in (n.get("top_bear") or [])[:k_news]:
    L.append(f"- 空 - {h.get('title')}（{h.get('publisher')}）")
  L.append("")

  # ---------------------------------------------------------------- self check
  hits, nn, hist_txt = _history_check(br.get("history") or [])
  L.append("## 自我驗證")
  L.append(f"- {hist_txt}；連續同評級 {ch.get('same_verdict_streak_days')} 個交易日" + (f"；上次評級改變 {ch.get('previous_date')}" if ch.get("verdict_changed") else ""))
  if with_links:
    lk = br.get("links") or {}
    L.append(f"- 完整報告 {lk.get('report_html')} ・ 新手版 {lk.get('simple_html')} ・ JSON {lk.get('brief_json')}（新聞連結在 news.top_bull[].link）")
  L.append("")
  L.append(f"_{br.get('disclaimer')}_")
  return "\n".join(L) + "\n"


def to_text(br: dict, max_chars: int = 900) -> str:
  v, pr, pl, o, s, cr, ch, ev = (br.get(k) or {} for k in ("verdict", "price", "plan", "options", "sentiment", "crash_risk", "changes", "events"))
  cons = v.get("consensus") or {}
  fg, vx = s.get("fear_greed") or {}, s.get("vix") or {}
  bg = br.get("beginner") or {}
  buy = bg.get("buy") or {}
  parts = [
      f"SOXL {br.get('data_as_of')} 收盤 {_usd(pr.get('close'))}（{_pct(pr.get('ret_1d'))}）",
      f"{v.get('emoji') or ''} {v.get('label') or ''}｜綜合 {_num(v.get('composite'), 2, True)}｜空 {_num(cons.get('sell_pct'), 0)}% / 中 {_num(cons.get('hold_pct'), 0)}% / 多 {_num(cons.get('buy_pct'), 0)}%｜倉位上限 {v.get('size_pct')}%",
  ]
  if buy:
    first = str(buy.get("text") or "").split("。")[0]
    w = bg.get("watch") or {}
    parts.append(f"該不該買：{buy.get('emoji') or ''} {buy.get('answer')}。{first}。" + (f" 明天盯 {_usd(w['price'])}（{w.get('label')}）。" if w.get("price") else ""))
  dash = br.get("dashboard") or {}
  if dash.get("gauges"):
    g = {x.get("key"): x for x in dash["gauges"]}
    parts.append("儀表：" + "｜".join(f"{g[k]['emoji']} {lab} {g[k].get('short') or str(g[k].get('value') or '').split('｜')[0][:14]}" for k, lab in (("add_on", "加碼"), ("macro", "宏觀"), ("soxx", "費半"), ("whales", "大戶"), ("put_call", "P/C"), ("crash", "崩跌")) if k in g))
  parts += [
      (f"{str((br.get('trade_plan') or {}).get('headline', '')).split('：')[0]}｜守 {_usd(((br.get('trade_plan') or {}).get('stop') or {}).get('price'))} → 看 {_usd(((br.get('trade_plan') or {}).get('t1') or {}).get('price'))} → {_usd(((br.get('trade_plan') or {}).get('t2') or {}).get('price'))}（加權 {_num((br.get('trade_plan') or {}).get('rr_blend'), 1)}R）" if br.get("trade_plan") else
       f"守 {_usd(pl.get('stop_price'))} → 看 {_usd(pl.get('target1_price'))} → {_usd(pl.get('target2_price'))}"),
      f"Put 牆 {_usd(o.get('put_wall'), 0)} / Call 牆 {_usd(o.get('call_wall'), 0)} / Gamma 翻正 {_usd(o.get('gamma_flip'), 1)}",
      f"F&G {_num(fg.get('score'), 0)}（{fg.get('rating_zh') or ''}）｜VIX {_num(vx.get('vix'), 1)}（VIX/VIX3M {_num(vx.get('ratio_vix_3m'), 2)}）｜崩跌前兆 {_num(cr.get('score'), 0)}/100",
  ]
  fl = br.get("flash") or {}
  if fl.get("top"):
    t0 = fl["top"][0]
    parts.append(f"時事（{fl.get('label')}）：{'利空' if (t0.get('impact') or 0) < 0 else ('利多' if (t0.get('impact') or 0) > 0 else '中性')}「{str(t0.get('title'))[:70]}」（{t0.get('publisher')}）")
  if ch.get("notes"):
    parts.append("變化：" + "；".join(ch["notes"][:2]))
  if ev.get("upcoming"):
    parts.append("事件：" + "；".join(f"{e.get('when_zh')} {e.get('label')}" for e in ev["upcoming"][:3]))
  n = br.get("news") or {}
  if not fl.get("top") and (n.get("top_bear") or n.get("top_bull")):
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
      "required": ["schema", "generated_at", "data_as_of", "verdict", "price", "levels", "plan", "links", "trade_plan", "signals", "validation"],
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
          "trade_plan": {"type": ["object", "null"], "description": "v2: explicit plan; null only when the backtest could not run", "properties": {
              "side": {"type": "string", "enum": ["long", "long_pending", "no_trade"]}, "tradeable": {"type": "boolean"}, "headline": {"type": "string"},
              "entry": {"type": "object", "properties": {"type": {"type": "string"}, "price": num, "rule": {"type": "string"}, "signal": {"type": ["string", "null"]}}},
              "stop": {"type": "object", "properties": {"price": num, "dist_pct": num, "k_atr": num, "atr14": num, "basis": {"type": "string"}}},
              "t1": {"type": "object", "properties": {"price": num, "label": {"type": "string"}, "rr": num, "synthetic": {"type": "boolean"}}},
              "t2": {"type": "object", "properties": {"price": num, "label": {"type": "string"}, "rr": num, "synthetic": {"type": "boolean"}}},
              "rr_blend": num, "min_rr": num, "trade_if_entry": {**num, "description": "entry that would satisfy min_rr with the same stop and targets (null when already satisfied)"},
              "size": {"type": "object", "properties": {"pct": num, "if_triggered_pct": num, "risk_based_pct": num, "verdict_cap_pct": num, "risk_per_trade_pct": num}},
              "time_stop": {"type": "object", "properties": {"days": {"type": "integer"}, "rule": {"type": "string"}, "kind": {"type": "string"}}},
              "invalidation": {"type": "array", "items": {"type": "string"}}, "signals_fired": {"type": "array"}, "signals_pending": {"type": "array"},
              "holder": {"type": "object"}, "regime": {"type": "object"}, "explain": {"type": "array", "items": {"type": "string"}}}},
          "signals": {"type": "array", "description": "v2: validated signal library (fixed rules, 10y SOXL, de-clustered trades)", "items": {"type": "object", "properties": {
              "key": {"type": "string"}, "short_name": {"type": "string"}, "side": {"type": "string", "enum": ["long", "exit"]}, "horizon": {"type": "integer"},
              "n": {"type": "integer"}, "win_pct": num, "base_win_pct": num, "ci": {"type": ["array", "null"]}, "mean": num, "pf": num,
              "p_value": {**num, "description": "one-sided exact binomial vs base_win_pct"}, "q_value": {**num, "description": "Benjamini-Hochberg across graded signals"}, "significant": {"type": ["boolean", "null"]},
              "grade": {"type": "string", "description": "A / B / B* / C / —"}, "state": {"type": "string", "enum": ["fired", "recent", "pending", "off"]},
              "pending": {"type": ["object", "null"], "description": "trigger price that would fire the rule tomorrow"}, "dyn": {"type": ["object", "null"]}, "dd15": {"type": ["object", "null"]}}}},
          "validation": {"type": ["object", "null"], "description": "v2: method, multiple-testing summary, 200-day regime grid (SOXL vs underlying index)", "properties": {
              "method": {"type": "object"}, "summary": {"type": "object"}, "regime_grid": {"type": "array"}, "buy_hold": {"type": [
                  "object", "null"]}}},
          "beginner": {"type": ["object", "null"], "description": "v2.1: the one-screen answer; derived from trade_plan.side first, verdict.rating_5 second", "properties": {
              "buy": {"type": "object", "properties": {"answer": {"type": "string", "description": "可以買 / 可以分批小量 / 先別買，等觸發 / 先別買，等確認 / 先別買，等更好的價位 / 不該買 / 資料不足"},
                                                       "emoji": {"type": "string"}, "text": {"type": "string"}, "basis": {"type": "string"}}},
              "biggest_thing": {"type": "string", "description": "flash.beginner_line: the one headline of the last 36 h and why it matters for SOXL"},
              "holder": {"type": "string"}, "watch": {"type": "object", "properties": {"label": {"type": "string"}, "price": num}},
              "risk_48h": {"type": "array", "items": {"type": "string"}}, "lines": {"type": "array", "items": {"type": "string"}, "description": "the 5 rendered bullets"}}},
          "flash": {"type": ["object", "null"], "description": "v2.1: breaking news of the last 36 h ranked by |impact| × recency × publisher weight (keyword rules, not an LLM)", "properties": {
              "as_of_tpe": {"type": ["string", "null"]}, "window_h": {"type": ["integer", "null"]}, "label": {"type": ["string", "null"], "description": "偏空 / 中性 / 偏多"}, "net": num,
              "beginner_line": {"type": ["string", "null"]},
              "top": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "publisher": {"type": ["string", "null"]}, "link": {"type": ["string", "null"]}, "time_tpe": {"type": "string"},
                                                                                "category": {"type": "string", "description": "聯準會與利率 / 政策與關稅 / 地緣政治 / 半導體與 AI / 經濟數據 / 市場波動"},
                                                                                "impact": {"type": "integer", "minimum": -2, "maximum": 2}, "why_zh": {"type": "string"}}}},
              "flags": {"type": "object", "properties": {k: {"type": "boolean"} for k in ("fed_statement_24h", "geo_escalation_24h", "tariff_shock_24h", "capex_warning_24h", "fed_hawkish_24h")}},
              "flag_evidence": {"type": "object"}, "cautions": {"type": "array", "items": {"type": "object", "properties": {"flag": {"type": "string"}, "text": {"type": "string"}, "evidence": {"type": "object"}}}},
              "by_category": {"type": "array"}, "seeking_alpha": {"type": "array", "description": "latest Seeking Alpha items on SOXL / SOXX / NVDA (news desk + contributor analysis), 72 h"}, "method": {"type": ["string", "null"]}, "errors": {"type": "array"}}},
          "dashboard": {"type": ["object", "null"], "description": "v2.2: six gauges (add_on / macro / soxx / whales / put_call / crash), Seeking-Alpha-style factor grades, four-voice summary", "properties": {
              "gauges": {"type": "array", "items": {"type": "object", "properties": {"key": {"type": "string", "enum": ["add_on", "macro", "soxx", "whales", "put_call", "crash"]}, "title": {"type": "string"}, "value": {"type": "string"},
                                                                                   "light": {"type": "string", "enum": ["green", "yellow", "red", "grey"]}, "emoji": {"type": "string"}, "meaning": {"type": "string"}, "detail": {"type": "string"},
                                                                                   "fields": {"type": "array", "items": {"type": "string"}, "description": "JSON paths the gauge was derived from"}, "caveat": {"type": "string"}}}},
              "lights": {"type": "object"}, "factor_grades": {"type": "array", "items": {"type": "object", "properties": {"short": {"type": "string"}, "grade": {"type": "string", "description": "A+ … F from the category score"}, "score": num, "weight": num}}},
              "overall_grade": {"type": "string"}, "voices": {"type": "object", "properties": {"rows": {"type": "array"}, "n_bear": {"type": "integer"}, "n_neutral": {"type": "integer"}, "n_bull": {"type": "integer"}, "summary": {"type": "string"}}},
              "soxx_stats": {"type": "object", "properties": {"close": num, "ret_1d": num, "ret_5d": num, "ret_20d": num, "sma20": num, "sma50": num, "sma200": num, "dist_sma200_pct": num, "trend": {"type": "string"}, "light": {"type": "string"}}},
              "one_liner": {"type": "string"}, "method": {"type": "string"}}},
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
