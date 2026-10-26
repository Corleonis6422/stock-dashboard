#!/usr/bin/env python3
"""Market dashboard — six gauges a viewer asks about first, plus Seeking-Alpha-style factor grades.

The six questions (one gauge each, every gauge = value + light + one sentence + the JSON fields it came from):

  add_on     SOXL 能不能加碼？      decided by trade_plan.side first, then the 5-level rating, the chandelier stop,
                                    the crash score and the VIX term structure
  macro      現在的宏觀消息          36-hour news flash label + the top non-semiconductor headline + 10Y / Brent / VIX / DXY moves
  soxx       費半（SOXX）整體走向    SOXX close vs 20 / 50 / 200-day averages, 1 / 5 / 20-day returns, breadth of the 16 names
  whales     大戶怎麼走              CBOE large-premium option prints (net score −1…+1, call vs put premium, biggest print),
                                    retail vs whale call/put mix, SOXL vs SOXS dollar flow
  put_call   Put/Call                SOXL volume and OI put/call, market-wide equity P/C with its 1-year percentile
  crash      崩跌指數                crash-precursor score 0–100 (≥ 60 watch, ≥ 80 alert) and the active symptoms

Also:
  factor_grades   the 7 scorecard categories mapped to letter grades A+ … F (the Seeking Alpha "factor grades" idiom)
  voices          four independent readings side by side (quant rating, validated signals, news flash, SOXX trend),
                  the Seeking Alpha "ratings summary" idiom, with an agreement count
  soxx_stats      the raw SOXX numbers used by the soxx gauge

Everything is derived from numbers already in the payload; nothing here changes the verdict or the plan.
"""
from __future__ import annotations

from . import indicators as ind

LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴", "grey": "⚪"}
GRADE_STEPS = [(1.5, "A+"), (1.0, "A"), (0.6, "B+"), (0.3, "B"), (0.1, "C+"), (-0.1, "C"), (-0.3, "C-"), (-0.6, "D"), (-1.0, "D-")]
CATEGORY_SHORT = {"1": "期權籌碼", "2": "量能", "3": "技術趨勢", "4": "廣度", "5": "宏觀", "6": "情緒", "7": "消息"}
MACRO_CATEGORIES = ("聯準會與利率", "政策與關稅", "地緣政治", "經濟數據", "市場波動")


def _r(v, nd=2):
  try:
    return round(float(v), nd)
  except (TypeError, ValueError):
    return None


def _usd(v, nd=2):
  try:
    return f"${float(v):,.{nd}f}"
  except (TypeError, ValueError):
    return "n/a"


def _pct(v, nd=1, sign=True):
  try:
    return (f"{float(v):+.{nd}f}%" if sign else f"{float(v):.{nd}f}%")
  except (TypeError, ValueError):
    return "n/a"


def grade(score) -> str:
  """−2…+2 category score → letter grade (A+ ≥ 1.5 … F < −1.0)."""
  try:
    s = float(score)
  except (TypeError, ValueError):
    return "—"
  for thr, g in GRADE_STEPS:
    if s >= thr:
      return g
  return "F"


def _gauge(key, title, value, light, meaning, detail="", fields=None, caveat="", short=None):
  return {"key": key, "title": title, "value": value, "short": (short or str(value).split("｜")[0]), "light": light, "emoji": LIGHT.get(light, "⚪"), "meaning": meaning,
          "detail": detail, "fields": fields or [], "caveat": caveat}


# --------------------------------------------------------------------------- #
# SOXX trend
# --------------------------------------------------------------------------- #
def soxx_stats(rows: list[dict] | None, recent: list[dict] | None = None, regime_underlying: dict | None = None) -> dict:
  """SOXX close vs 20 / 50 / 200-day SMA and 1 / 5 / 20-day returns.  ``rows`` = 10y daily rows (preferred);
  falls back to the 40-close ``benchmarks_recent`` series plus the regime grid's 200-day distance."""
  closes = [float(r["close"]) for r in (rows or []) if r.get("close") is not None]
  dates = [r.get("date") for r in (rows or [])]
  src = "nasdaq_10y"
  if len(closes) < 60 and recent:
    closes = [float(r["close"]) for r in recent if r.get("close") is not None]
    dates = [r.get("date") for r in recent]
    src = "benchmarks_recent"
  if len(closes) < 21:
    return {"available": False, "source": src}
  c = closes[-1]
  s20 = ind.sma(closes, 20)[-1]
  s50 = ind.sma(closes, 50)[-1] if len(closes) >= 50 else None
  s200 = ind.sma(closes, 200)[-1] if len(closes) >= 200 else None
  if s200 is None and regime_underlying and regime_underlying.get("sma200"):
    s200 = float(regime_underlying["sma200"])
  hi20, lo20 = max(closes[-20:]), min(closes[-20:])
  hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)

  def ret(n):
    return _r((c / closes[-1 - n] - 1.0) * 100.0, 2) if len(closes) > n else None

  def dist(ma):
    return _r((c / ma - 1.0) * 100.0, 1) if ma else None

  above20, above50, above200 = (c > s20) if s20 else None, (c > s50) if s50 else None, (c > s200) if s200 else None
  if above200 and above50 and above20:
    trend, light = "多頭（站穩 20 / 50 / 200 日線）", "green"
  elif above200 and (above50 or above20):
    trend, light = "年線上方整理（20 或 50 日線其中一條失守）", "yellow"
  elif above200:
    trend, light = "修正中（年線上方，但 20 與 50 日線都在頭上）", "yellow"
  elif above20:
    trend, light = "年線下方反彈（站回 20 日線，年線仍在頭上）", "yellow"
  elif above200 is None:
    trend, light = "資料不足", "grey"
  else:
    trend, light = "空頭（年線與短均線都在頭上）", "red"
  return {
      "available": True, "source": src, "date": dates[-1] if dates else None, "close": _r(c), "ret_1d": ret(1), "ret_5d": ret(5), "ret_20d": ret(20),
      "sma20": _r(s20), "sma50": _r(s50), "sma200": _r(s200), "dist_sma20_pct": dist(s20), "dist_sma50_pct": dist(s50), "dist_sma200_pct": dist(s200),
      "above_sma20": above20, "above_sma50": above50, "above_sma200": above200, "high_20d": _r(hi20), "low_20d": _r(lo20), "drawdown_52w_pct": _r((c / hi52 - 1.0) * 100.0, 1),
      "trend": trend, "light": light,
  }


# --------------------------------------------------------------------------- #
# gauges
# --------------------------------------------------------------------------- #
def gauge_add_on(sc: dict, tp: dict, tech: dict, ews_today: dict, vx: dict, regime_underlying: dict | None, size_cap=None) -> dict:
  r5 = sc.get("rating_5")
  side, tradeable = tp.get("side"), bool(tp.get("tradeable"))
  hold, st, sz, ent = (tp.get(k) or {} for k in ("holder", "stop", "size", "entry"))
  stop = st.get("price")
  cap = (tp.get("size") or {}).get("verdict_cap_pct") or size_cap
  cap = f"{float(cap):.0f}" if isinstance(cap, (int, float)) else "n/a"
  close, sma20 = tech.get("close"), tech.get("sma20")
  crash = ews_today.get("score")
  ratio = vx.get("ratio_vix_3m")
  reduce_into = " / ".join(_usd(r.get("price")) for r in (hold.get("reduce_into") or [])[:2])
  fields = ["trade_plan.side", "trade_plan.tradeable", "verdict.rating_5", "trade_plan.holder.trail_breached", "crash_risk.score", "sentiment.vix.ratio_vix_3m", "levels.sma20"]
  hard_no = []
  if crash is not None and crash >= 80:
    hard_no.append(f"崩跌前兆 {crash:.0f} ≥ 80")
  if ratio is not None and ratio >= 1.0:
    hard_no.append(f"VIX/VIX3M {ratio:.2f} 倒掛")
  if hard_no:
    return _gauge("add_on", "SOXL 能不能加碼？", "不能加碼", "red",
                  f"{'；'.join(hard_no)}：歷史上這種狀態加碼的賠率最差，只能減碼或空手。", f"跌破 {_usd(stop)} 全出" + (f"；反彈到 {reduce_into} 先減" if reduce_into else ""), fields)
  if side == "long" and tradeable:
    return _gauge("add_on", "SOXL 能不能加碼？", "可以加碼", "green",
                  f"驗證過的買訊今天成立，可用計畫倉位 {sz.get('pct')}% 加碼，總倉位不超過評級上限 {cap}%，新舊部位同一停損 {_usd(stop)}。",
                  f"進場 {_usd(ent.get('price'))}；這是依訊號加碼，不是攤平", fields)
  if side == "long_pending":
    return _gauge("add_on", "SOXL 能不能加碼？", "先不加碼", "yellow",
                  f"買訊還沒成立：收盤站上 {_usd(ent.get('price'))} 才算，成立後次日開盤再加 {sz.get('if_triggered_pct')}%。今天不追。",
                  f"失守 {_usd(stop)} 則既有部位全出", fields)
  if r5 is not None and r5 <= 2:
    why = "評級偏空" + ("、吊燈移動停損已觸發" if hold.get("trail_breached") else "")
    return _gauge("add_on", "SOXL 能不能加碼？", "不能加碼", "red",
                  f"{why}：加碼就是攤平三倍槓桿，SOXL 單日可 ±15%。只能減碼或等買訊。",
                  f"反彈到 {reduce_into} 先減碼；跌破 {_usd(stop)} 全出" if reduce_into else f"跌破 {_usd(stop)} 全出", fields)
  if r5 == 3:
    return _gauge("add_on", "SOXL 能不能加碼？", "先不加碼", "yellow",
                  f"評級「觀望」：多空打平，沒有買訊。等收盤站回 20 日線 {_usd(sma20)} 或計畫的觸發條件成立再說。",
                  f"既有部位守 {_usd(stop)}", fields)
  ok_struct = (close is not None and sma20 is not None and close > sma20) and bool((regime_underlying or {}).get("in_market"))
  if r5 is not None and r5 >= 4 and ok_struct:
    return _gauge("add_on", "SOXL 能不能加碼？", "可小量加碼", "green",
                  f"評級偏多、價在 20 日線上、費半在年線濾網內：可以分批加碼，總倉位不超過 {cap}%，停損 {_usd(stop)}。",
                  "沒有驗證過的買訊成立，所以是「小量分批」不是「一次補滿」", fields)
  if r5 is not None and r5 >= 4:
    return _gauge("add_on", "SOXL 能不能加碼？", "先不加碼", "yellow",
                  f"評級偏多，但{'價還在 20 日線下' if not (close and sma20 and close > sma20) else '費半仍在年線濾網外'}：等結構確認再加。",
                  f"既有部位守 {_usd(stop)}", fields)
  return _gauge("add_on", "SOXL 能不能加碼？", "資料不足", "grey", "缺少評級或計畫。", "", fields)


def gauge_macro(flash: dict, mac: dict, events: list[dict] | None) -> dict:
  fl = flash or {}
  kp = {k.get("key"): k for k in (mac.get("macro_kpis") or [])}

  def kv(key, label):
    k = kp.get(key) or {}
    return f"{label} {k.get('latest')}（{k.get('chg_1d')}）" if k.get("latest") else None

  bits = [x for x in (kv("TNX_10Y", "10Y"), kv("BRENT", "油"), kv("VIX", "VIX"), kv("DXY", "美元")) if x]
  top_macro = next((t for t in (fl.get("top") or []) if t.get("category") in MACRO_CATEGORIES), (fl.get("top") or [None])[0])
  label = fl.get("label") or "n/a"
  flags_on = [k for k, v in (fl.get("flags") or {}).items() if v]
  light = "red" if (label == "偏空" or flags_on) else ("green" if label == "偏多" else ("yellow" if label == "中性" else "grey"))
  fomc = next((e for e in (events or []) if e.get("type") == "fomc" and (e.get("days_ahead") or 99) <= 7), None)
  head = f"{top_macro.get('emoji') or ''} {top_macro.get('title')}（{top_macro.get('publisher')}）" if top_macro else "過去 36 小時沒有抓到宏觀大事"
  meaning = (str(top_macro.get("why_zh") or "") if top_macro else "") or "看殖利率、油價與 VIX 的方向就夠。"
  detail = "；".join(bits) + (f"；{fomc.get('when_zh')} {fomc.get('label')}" if fomc else "")
  value = f"{label}｜{head}"
  return _gauge("macro", "現在的宏觀消息", value, light, meaning, detail,
                ["flash.label", "flash.top[0]", "flash.flags", "macro.kpis[TNX_10Y|BRENT|VIX|DXY]", "events.upcoming"],
                "時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤", short=label + ("，有旗標" if flags_on else ""))


def gauge_soxx(sx: dict, hm: dict, regime_underlying: dict | None) -> dict:
  if not sx.get("available"):
    return _gauge("soxx", "費半（SOXX）整體走向", "資料不足", "grey", "SOXX 歷史抓取失敗。", "", ["soxx_stats"])
  ru = regime_underlying or {}
  value = f"{sx['trend'].split('（')[0]}｜{_usd(sx.get('close'))}（{_pct(sx.get('ret_1d'), 2)}）"
  detail = (f"5 日 {_pct(sx.get('ret_5d'))}、20 日 {_pct(sx.get('ret_20d'))}；距 20MA {_pct(sx.get('dist_sma20_pct'))}、50MA {_pct(sx.get('dist_sma50_pct'))}、200MA {_pct(sx.get('dist_sma200_pct'))}"
            f"；16 檔成分股站上 50MA {hm.get('breadth_above_sma50_pct')}%、200MA {hm.get('breadth_above_sma200_pct')}%"
            + (f"；年線濾網：{'持有' if ru.get('in_market') else '空手'}（出場線 {_usd(ru.get('exit_below'))}）" if ru else ""))
  meaning = {"green": "費半多頭時 SOXL 的反彈才有延續性；這是加碼的前提之一。",
             "yellow": "費半在修正或反彈的半路：SOXL 的 3 倍槓桿會把這段震盪放大，只做有停損的單。",
             "red": "費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。"}.get(sx["light"], "")
  return _gauge("soxx", "費半（SOXX）整體走向", value, sx["light"], meaning, detail,
                ["soxx_stats", "breadth.above_sma50_pct", "breadth.above_sma200_pct", "trade_plan.regime.underlying"],
                short=f"{sx['trend'].split('（')[0]} {_pct(sx.get('ret_20d'), 0)}/20日")


def gauge_whales(opt: dict, flows: dict, flows_avg20) -> dict:
  wh = opt.get("whale") or {}
  net = wh.get("whale_net_score")
  if net is None:
    return _gauge("whales", "大戶怎麼走", "資料不足", "grey", "CBOE 選擇權鏈沒有大單資料。", "", ["options.whale"])
  light = "green" if net >= 0.2 else ("red" if net <= -0.2 else "yellow")
  word = "偏多" if net >= 0.2 else ("偏空" if net <= -0.2 else "中性")
  top = (wh.get("top_whale_trades") or [{}])[0]
  top_txt = (f"最大單 {top.get('expiration')} {_usd(top.get('strike'), 0)} {'Call' if top.get('type') == 'C' else 'Put'} ${top.get('premium_m')}M（{top.get('bias')}）" if top else "")
  retail = wh.get("retail_cp_ratio")
  whale_cp = wh.get("whale_cp_ratio")
  mix = (f"大戶 C/P {whale_cp} vs 散戶 C/P {retail}" if whale_cp is not None and retail is not None else "")
  fl = flows or {}
  flow_txt = (f"SOXL/SOXS 資金流 {fl.get('ratio')}x（20 日均 {flows_avg20}x）" if fl.get("ratio") is not None else "")
  value = f"{word} {net:+.2f}｜大單 Call ${wh.get('whale_call_prem_m')}M vs Put ${wh.get('whale_put_prem_m')}M（{wh.get('whale_count')} 筆）"
  detail = "；".join(x for x in (top_txt, mix, flow_txt) if x)
  meaning = {"green": "大單權利金偏向 Call：大戶在買反彈或賣 Put 收權利金，和評級偏空時是分歧，值得盯但不是買點。",
             "red": "大單權利金偏向 Put：大戶在避險或押跌，和空頭評級同向。",
             "yellow": "大單方向不明顯：沒有誰在明顯站隊。"}[light]
  return _gauge("whales", "大戶怎麼走", value, light, meaning, detail,
                ["options.whale.whale_net_score", "options.whale.whale_call_prem_m", "options.whale.whale_put_prem_m", "options.whale.top_whale_trades", "sentiment.flows.ratio"],
                "大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報", short=f"{word} {net:+.2f}")


def gauge_put_call(opt: dict, pc: dict) -> dict:
  v, oi = opt.get("pc_vol_ratio"), opt.get("pc_oi_ratio")
  eq, eqp, tot = pc.get("equity_pc"), pc.get("equity_pc_percentile"), pc.get("total_pc")
  if v is None and eq is None:
    return _gauge("put_call", "Put/Call", "資料不足", "grey", "CBOE Put/Call 未取得。", "", ["options.pc_vol_ratio"])

  def state(x):
    if x is None:
      return "n/a"
    return "避險 / 恐慌" if x >= 1.0 else ("中性" if x >= 0.7 else "偏樂觀")

  fear = (eqp is not None and eqp >= 90) or (v is not None and v >= 1.2)
  complacent = (eqp is not None and eqp <= 10) or (v is not None and v <= 0.5)
  light = "yellow" if (fear or complacent) else "green"
  value = f"SOXL 成交 {v}（{state(v)}）｜全市場個股 {eq}（1 年第 {eqp:.0f} 百分位）" if eqp is not None else f"SOXL 成交 {v}（{state(v)}）"
  detail = f"SOXL 未平倉 P/C {oi}；全市場總 P/C {tot}（{pc.get('total_read')}）；個股 P/C 讀法 {pc.get('equity_read')}"
  where = (f"個股 P/C 第 {eqp:.0f} 百分位" if eqp is not None and eqp >= 90 else "") + ("、SOXL 成交 P/C ≥ 1.2" if v is not None and v >= 1.2 else "")
  meaning = (f"恐慌區（{where.strip('、')}）：底部常出現在這裡，但這是恐慌的證據不是買點，配合站回 20 日線才算。P/C 越高代表買 Put 避險越多。" if fear
             else "自滿區：期權市場偏樂觀，對 3 倍槓桿不是好事。P/C 越低代表買 Put 避險越少。" if complacent else "中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。")
  return _gauge("put_call", "Put/Call", value, light, meaning, detail,
                ["options.pc_vol_ratio", "options.pc_oi_ratio", "sentiment.market_put_call.equity_pc", "sentiment.market_put_call.equity_pc_percentile", "sentiment.market_put_call.total_pc"],
                short=f"SOXL {v}" + (f"，個股第 {eqp:.0f} 百分位" if eqp is not None else "") + ("（恐慌）" if fear else ("（自滿）" if complacent else "")))


def gauge_crash(ews: dict) -> dict:
  t = ews.get("today") or {}
  s = t.get("score")
  if s is None:
    return _gauge("crash", "崩跌指數", "資料不足", "grey", "前兆系統未產生分數。", "", ["crash_risk.score"])
  light = "red" if s >= 80 else ("yellow" if s >= 60 else "green")
  active = [c.get("label") for c in (ews.get("contributions") or []) if (c.get("value") or 0) >= 0.5][:3]
  es = (ews.get("event_study") or {}).get("stats_top_80") or {}
  value = f"{s:.0f} / 100（{'警戒' if s >= 80 else ('注意' if s >= 60 else '低')}）"
  detail = ("成立中的症狀：" + "、".join(active) if active else "沒有症狀成立") + (f"；分數 ≥ 80 的歷史命中率 {es.get('precision_pct')}%（基準 {es.get('base_rate_pct')}%）" if es.get("precision_pct") is not None else "")
  zone = str(t.get("zone") or "")
  meaning = ("分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。" if not t.get("above_200") and s < 60
             else "分數 ≥ 80 時過去 20 日內出現 ≥15% 回撤的機率明顯高於平時，減碼優先。" if s >= 80
             else "分數進入注意區：盯 VIX 期限結構與派發日，不加碼。")
  return _gauge("crash", "崩跌指數", value, light, meaning, detail + (f"；{zone}" if zone else ""), ["crash_risk.score", "crash_risk.zone", "crash_risk.active_signals", "crash_risk.event_study"],
                short=f"{s:.0f}/100 {'警戒' if s >= 80 else ('注意' if s >= 60 else '低')}")


# --------------------------------------------------------------------------- #
# factor grades + voices
# --------------------------------------------------------------------------- #
def factor_grades(sc: dict) -> list[dict]:
  out = []
  for c in sc.get("category_scores") or []:
    name = str(c.get("category") or "")
    short = CATEGORY_SHORT.get(name.split(".")[0].strip(), name.split("(")[0].strip())
    out.append({"category": name, "short": short, "weight": c.get("weight"), "score": _r(c.get("avg_score")), "grade": grade(c.get("avg_score"))})
  return out


def voices(sc: dict, tp: dict, flash: dict, sx: dict) -> dict:
  r5 = sc.get("rating_5")
  q_tone = "bear" if (r5 or 3) <= 2 else ("bull" if (r5 or 3) >= 4 else "neutral")
  side = tp.get("side")
  s_tone = "bull" if side == "long" and tp.get("tradeable") else "neutral"  # no validated entry = no edge, not a short call
  fl_label = (flash or {}).get("label")
  f_tone = {"偏空": "bear", "偏多": "bull", "中性": "neutral"}.get(fl_label, "neutral")
  x_tone = {"green": "bull", "red": "bear"}.get(sx.get("light"), "neutral")
  rows = [
      {"voice": "量化評級（24 因子）", "reading": f"{sc.get('rating_label') or 'n/a'}（綜合 {_r(sc.get('composite_score')):+.2f}）" if sc.get("composite_score") is not None else "n/a", "tone": q_tone, "field": "verdict"},
      {"voice": "訊號驗證（10 年回測）", "reading": {"long": "買進訊號成立", "long_pending": f"等觸發 {_usd((tp.get('entry') or {}).get('price'))}", "no_trade": "沒有驗證過的買點（不開新倉）"}.get(side, "n/a"), "tone": s_tone, "field": "trade_plan.side"},
      {"voice": "時事 / 宏觀（36 小時）", "reading": f"{fl_label or 'n/a'}（淨影響 {(flash or {}).get('net')}）", "tone": f_tone, "field": "flash.label"},
      {"voice": "費半趨勢（SOXX）", "reading": sx.get("trend", "n/a").split("（")[0] if sx.get("available") else "n/a", "tone": x_tone, "field": "dashboard.soxx_stats.trend"},
  ]
  n_bear = sum(1 for r in rows if r["tone"] == "bear")
  n_bull = sum(1 for r in rows if r["tone"] == "bull")
  n_neu = len(rows) - n_bear - n_bull
  summary = f"四個聲音：{n_bear} 空 / {n_neu} 中性 / {n_bull} 多"
  if n_bull >= 3:
    summary += " → 一致偏多"
  elif n_bear >= 3:
    summary += " → 一致偏空，不加碼"
  elif n_bull == 0:
    summary += " → 沒有任何多方聲音：不加碼、不開新倉"
  else:
    summary += " → 分歧，等對齊再動"
  return {"rows": rows, "n_bear": n_bear, "n_neutral": n_neu, "n_bull": n_bull, "summary": summary}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build(p: dict, soxx_rows: list[dict] | None = None, events: list[dict] | None = None) -> dict:
  tech, opt, sen, hm, mac, ews, sc, tp = (p.get(k) or {} for k in ("technicals", "options", "sentiment", "heatmap", "macro", "early_warning", "scoring", "trade_plan"))
  flash = p.get("newsflash") or {}
  ru = (tp.get("regime") or {}).get("underlying") or {}
  sx = soxx_stats(soxx_rows, (p.get("benchmarks_recent") or {}).get("SOXX"), ru)
  flows = (sen.get("flows") or {})
  gauges = [
      gauge_add_on(sc, tp, tech, ews.get("today") or {}, sen.get("vix") or {}, ru, ((p.get("playbook") or {}).get("beginner") or {}).get("size_pct")),
      gauge_macro(flash, mac, events),
      gauge_soxx(sx, hm, ru),
      gauge_whales(opt, flows.get("latest") or {}, flows.get("ratio_avg20")),
      gauge_put_call(opt, sen.get("put_call") or {}),
      gauge_crash(ews),
  ]
  fg = factor_grades(sc)
  vc = voices(sc, tp, flash, sx)
  lights = {g["key"]: g["light"] for g in gauges}
  return {
      "as_of": p.get("data_as_of"), "gauges": gauges, "lights": lights,
      "factor_grades": fg, "overall_grade": grade(sc.get("composite_score")), "voices": vc, "soxx_stats": sx,
      "one_liner": "｜".join(f"{lab}：{g['emoji']} {g['short']}" for lab, g in zip(("加碼", "宏觀", "費半", "大戶", "P/C", "崩跌"), gauges)),
      "method": "六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（<−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。",
  }


def refresh_macro(d: dict, p: dict, events: list[dict] | None = None) -> dict:
  """Recompute only the macro gauge and the voices after a news-flash refresh (feed rebuilds have no SOXX history)."""
  if not d or not d.get("gauges"):
    return d
  flash = p.get("newsflash") or {}
  sc, tp, mac = (p.get(k) or {} for k in ("scoring", "trade_plan", "macro"))
  gauges = [gauge_macro(flash, mac, events) if g.get("key") == "macro" else g for g in d["gauges"]]
  d = dict(d, gauges=gauges, lights={g["key"]: g["light"] for g in gauges}, voices=voices(sc, tp, flash, d.get("soxx_stats") or {}))
  d["one_liner"] = "｜".join(f"{lab}：{g['emoji']} {g['short']}" for lab, g in zip(("加碼", "宏觀", "費半", "大戶", "P/C", "崩跌"), gauges))
  return d
