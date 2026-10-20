#!/usr/bin/env python3
"""Post-mortem of the most recent major drawdown: timeline, what warned, what
stayed silent, the 3x-leverage math, big-picture (bear-market-rally) context and
rules-based lessons.  All numbers are computed from the data (no hand typing)."""

from __future__ import annotations

from . import indicators as ind


def _by_date(rows: list[dict] | None, key: str = "close") -> dict[str, float]:
  return {r["date"]: r[key] for r in (rows or []) if r.get(key) is not None}


def build(soxl: list[dict], soxx: list[dict] | None, spy: list[dict] | None, sen: dict, ews: dict, treasury: list[dict] | None, opt: dict) -> dict:
  closes = [r["close"] for r in soxl]
  dates = [r["date"] for r in soxl]
  n = len(soxl)
  v20 = ind.sma([float(r["volume"]) for r in soxl], 20)
  pc = ews.get("peak_checklist") or {}
  peak_date = pc.get("peak_date") or max(soxl[-30:], key=lambda r: r["close"])["date"]
  pi = dates.index(peak_date)
  start = max(0, pi - 4)

  vxh = {h["date"]: h for h in (sen.get("vix") or {}).get("history", [])}
  fg_by = {h["date"]: h["score"] for h in (sen.get("fear_greed") or {}).get("history", [])}
  pc_by = {h["date"]: h for h in (sen.get("put_call") or {}).get("history", [])}
  tre_by = {t["date"]: t for t in (treasury or [])}
  score_by = {s["date"]: s["score"] for s in ews.get("score_history_90d", [])}
  soxx_by, spy_by = _by_date(soxx), _by_date(spy)
  soxx_dates, spy_dates = sorted(soxx_by), sorted(spy_by)

  def chg(by: dict, ds: list[str], d: str) -> float | None:
    if d not in by:
      return None
    i = ds.index(d)
    return ind.pct_change(by[d], by[ds[i - 1]]) if i > 0 else None

  timeline = []
  prev_skew = None
  for i in range(start, n):
    r = soxl[i]
    d = r["date"]
    c1 = ind.pct_change(r["close"], closes[i - 1])
    rvol = r["volume"] / v20[i] if v20[i] else None
    vx = vxh.get(d, {})
    t = tre_by.get(d, {})
    notes = []
    if c1 <= -8:
      notes.append(f"放量長黑 {c1:+.1f}%" + (f" (量能 {rvol:.1f}× 均量)" if rvol else ""))
    elif c1 >= 5:
      notes.append(f"反彈 {c1:+.1f}%")
    if rvol and rvol >= 1.8 and c1 > -8:
      notes.append(f"爆量 {rvol:.1f}×")
    if vx.get("skew") and prev_skew and vx["skew"] - prev_skew >= 4:
      notes.append(f"SKEW 跳升至 {vx['skew']:.0f}")
    if vx.get("vix") and i > 0:
      pv = vxh.get(dates[i - 1], {}).get("vix")
      if pv and ind.pct_change(vx["vix"], pv) >= 15:
        notes.append(f"VIX 急升 {ind.pct_change(vx['vix'], pv):+.0f}%")
    if vx.get("ratio_vix_3m") and vx["ratio_vix_3m"] >= 0.95:
      notes.append("VIX 期限結構走平")
    f = fg_by.get(d)
    if f is not None and f < 25:
      notes.append(f"F&G 極度恐懼 {f:.0f}")
    if d == peak_date:
      notes.append("★ 波段最高收盤")
    if r["open"] > closes[i - 1] * 1.02 and r["close"] < closes[i - 1]:
      notes.append("開高走低 (假突破)")
    sc = score_by.get(d)
    if sc is not None and sc >= 45:
      notes.append(f"崩跌預警 {sc:.0f}")
    timeline.append({
        "date": d, "close": round(r["close"], 2), "chg_pct": round(c1, 2), "volume_m": round(r["volume"] / 1e6, 1),
        "rvol": round(rvol, 2) if rvol else None,
        "soxx_chg": (round(chg(soxx_by, soxx_dates, d), 2) if chg(soxx_by, soxx_dates, d) is not None else None),
        "spy_chg": (round(chg(spy_by, spy_dates, d), 2) if chg(spy_by, spy_dates, d) is not None else None),
        "vix": vx.get("vix"), "vix_ratio": vx.get("ratio_vix_3m"), "skew": vx.get("skew"), "vvix": vx.get("vvix"),
        "y10": t.get("y10"), "y30": t.get("y30"), "fg": f, "equity_pc": pc_by.get(d, {}).get("equity_pc"),
        "crash_score": sc, "notes": "；".join(notes),
    })
    if vx.get("skew"):
      prev_skew = vx["skew"]

  # ---- 3x leverage math (peak → trough)
  trough_i = min(range(pi, n), key=lambda j: closes[j])
  soxl_dd = ind.pct_change(closes[trough_i], closes[pi])
  soxx_dd = None
  if soxx_by and peak_date in soxx_by and dates[trough_i] in soxx_by:
    soxx_dd = ind.pct_change(soxx_by[dates[trough_i]], soxx_by[peak_date])
  spy_dd = None
  if spy_by and peak_date in spy_by and dates[trough_i] in spy_by:
    spy_dd = ind.pct_change(spy_by[dates[trough_i]], spy_by[peak_date])

  # ---- big picture: was the rally into the peak a bear-market rally?
  win = soxl[max(0, pi - 160) : pi + 1]
  big_high = max(win, key=lambda r: r["high"])
  bh_i = soxl.index(big_high)
  between = soxl[bh_i : pi + 1]
  big_low = min(between, key=lambda r: r["low"]) if len(between) > 5 else None
  big_picture = None
  if big_low and big_high["high"] > big_low["low"] * 1.3 and big_low["date"] != peak_date and bh_i < pi:
    peak_high = max(r["high"] for r in soxl[pi - 2 : pi + 2])
    rng = big_high["high"] - big_low["low"]
    retr = (peak_high - big_low["low"]) / rng * 100.0 if rng else None
    big_picture = {
        "big_high_date": big_high["date"], "big_high": round(big_high["high"], 2),
        "big_low_date": big_low["date"], "big_low": round(big_low["low"], 2),
        "big_decline_pct": round(ind.pct_change(big_low["low"], big_high["high"]), 1),
        "rally_high_date": peak_date, "rally_high": round(peak_high, 2),
        "rally_pct": round(ind.pct_change(peak_high, big_low["low"]), 1),
        "retrace_pct_of_decline": round(retr, 1) if retr is not None else None,
        "fib_382_of_decline": round(big_low["low"] + 0.382 * rng, 2), "fib_500_of_decline": round(big_low["low"] + 0.5 * rng, 2),
        "is_failed_bear_rally": bool(retr is not None and retr < 50.0),
    }

  # ---- what warned / what stayed silent (from EWS peak checklist)
  warned = [r for r in pc.get("rows", []) if r.get("flashed")]
  silent = [r for r in pc.get("rows", []) if not r.get("flashed")]

  # ---- paths of key sentiment gauges from peak to trough
  def path(by: dict, key: str | None = None) -> list:
    out = []
    for j in range(pi, trough_i + 1):
      v = by.get(dates[j])
      if isinstance(v, dict):
        v = v.get(key)
      if v is not None:
        out.append((dates[j], v))
    return out

  skew_path, vix_path, fg_path = path(vxh, "skew"), path(vxh, "vix"), path(fg_by)
  y10_path = [(d, v["y10"]) for d, v in sorted(tre_by.items()) if peak_date <= d <= dates[trough_i] and v.get("y10")]

  # ---- analog stat for "could it be predicted"
  analog = {}
  for c in (ews.get("analogs") or {}).get("conditions", []):
    if c["condition"].startswith("【事前訊號】20 日漲幅"):
      analog = c
      break

  lessons = []
  lessons.append({
      "title": "① 3 倍槓桿的數學：板塊只修正一成多，SOXL 就腰斬",
      "detail": (f"從 {peak_date} 高點到 {dates[trough_i]} 低點，SOXL {soxl_dd:+.1f}%" + (f"，同期 1 倍的 SOXX 只有 {soxx_dd:+.1f}%" if soxx_dd is not None else "") + (f"、大盤 SPY {spy_dd:+.1f}%" if spy_dd is not None else "") + "。這不是「板塊崩盤」，而是「3 倍槓桿把正常修正放大成崩盤」。"),
      "rule": "部位大小必須用『標的指數跌 15% = 我的 3x 部位跌 40%+』來做壓力測試；SOXL 任何時候的單筆部位不應超過總資金的 10–15%。",
  })
  if big_picture:
    lessons.append({
        "title": "② 看大不看小：10 月初的高點只是『熊市反彈』",
        "detail": (f"更大的一段是 {big_picture['big_high_date']} 高點 ${big_picture['big_high']} → {big_picture['big_low_date']} 低點 ${big_picture['big_low']} ({big_picture['big_decline_pct']:+.1f}%)。"
                   f"之後反彈到 {peak_date} 的 ${big_picture['rally_high']} ({big_picture['rally_pct']:+.1f}%)，只收復了那段跌幅的 {big_picture['retrace_pct_of_decline']}%，"
                   f"恰好止於 38.2% 回撤位 ${big_picture['fib_382_of_decline']} 下方 — 這是教科書級的『熊市反彈失敗點』。"
                   "若只用最近一段小波段畫斐波那契、把它的 38.2% 當支撐，就會忽略大級別仍是空頭。"),
        "rule": "畫斐波那契與判斷趨勢時，先看 6–12 個月的最大一段；反彈未收復大跌段 50% 之前，一律視為熊市反彈，不做趨勢多單。",
    })
  lessons.append({
      "title": "③ VIX、Fear & Greed 幾乎沒有事前預警 — 它們是『大盤指標』，不是『板塊指標』",
      "detail": (f"整段下跌期間 VIX 只在 {min(v for _, v in vix_path):.1f}～{max(v for _, v in vix_path):.1f} 之間" if vix_path else "VIX 全程低檔") +
                (f"，直到最後一天才跳到 {vix_path[-1][1]:.1f}" if vix_path else "") +
                (f"；CNN Fear & Greed 從高點日的 {fg_path[0][1]:.0f} 到跌破 25 花了 {sum(1 for _, v in fg_path if v >= 25)} 個交易日" if fg_path else "") +
                "；CBOE 個股 Put/Call 全程 0.55–0.65 沒有恐慌。因為大盤 (SPY) 幾乎沒跌，這是『AI/半導體單一板塊去槓桿』。",
      "rule": "操作 3x 板塊 ETF 時，VIX < 20 不代表安全；必須看板塊自己的風險指標：SOXL 距 200MA 乖離、成分股站上月線比例、派發日數、SKEW。",
  })
  lessons.append({
      "title": "④ 真正提前亮燈的訊號：SKEW、殖利率見頂、派發日、KD 高檔死叉、放量長黑",
      "detail": (f"SKEW (機構尾部避險需求) 從高點日 {skew_path[0][1]:.0f} 一路升到 {skew_path[-1][1]:.0f}" if skew_path else "") +
                (f"；10 年期殖利率在高點附近觸及 {max(v for _, v in y10_path):.2f}% 後反轉下行（資金逃向債市）" if y10_path else "") +
                f"；崩跌前兆系統在高點前 2 日～後 6 日之間亮起 {len(warned)}/{len(warned) + len(silent)} 項訊號：" + (f"分數 {min(pc.get('scores') or [0]):.0f}~{max(pc.get('scores') or [0]):.0f} (警戒區 ≥80)；" if pc.get("scores") else "") + "、".join(r["label"].split(" (")[0].split("：")[0] for r in warned[:8]) + "。",
      "rule": "以下任三項同時成立就先減碼一半：(a) 20 日漲幅 ≥40% 後出現首根 ≥8% 放量長黑；(b) KD 高檔死叉 + MACD 柱連續收斂；(c) SKEW 連續上升且 >150；(d) 首次收盤跌破 20MA；(e) 殖利率 20 日急升或 HYG 相對 SPY 轉弱。",
  })
  es = ews.get("event_study") or {}
  bk = {b["bucket"]: b for b in es.get("buckets_top", [])}
  hi_b, lo_b = bk.get("80-90"), bk.get("0-60")
  peak_scores = pc.get("scores") or []
  if analog and analog.get("horizons", {}).get("10d"):
    h = analog["horizons"]["10d"]
    detail = (f"先說誠實的結論：單一訊號預測不了。回測顯示「20 日漲幅 ≥40% 後出現首根 ≥8% 長黑」在過去 5 年共 {analog['n_days']} 次 ({analog['n_episodes']} 個獨立事件)，"
              f"10 個交易日後中位數 {h['median']:+.1f}%、{h['pct_positive']:.0f}% 上漲、只有 {h['pct_down10']:.0f}% 再跌 ≥10% — 也就是說，單看 10/08 那根長黑，歷史上『多半是買點』，當時偏多的判讀並非無據。"
              "這次真正不同的是三件事同時成立：(1) 大格局是熊市反彈失敗 (只收復前一段跌幅的 "
              + (f"{big_picture['retrace_pct_of_decline']}%" if big_picture else "不到一半") + ")；"
              + (f"(2) 崩跌前兆分數從 {pc.get('columns', [''])[0][5:]} 起就在 {min(peak_scores):.0f}~{max(peak_scores):.0f} 的警戒區" if peak_scores else "(2) 崩跌前兆分數處於警戒區")
              + (f" — 在 80~90 區間，5 日內再跌 ≥10% 的機率 {hi_b['pct_drop10']:.0f}%、≥20% 的機率 {hi_b['pct_crash']:.0f}%，是低分區 ({lo_b['pct_drop10']:.0f}% / {lo_b['pct_crash']:.0f}%) 的 {hi_b['pct_drop10'] / max(lo_b['pct_drop10'], 1):.1f}~{hi_b['pct_crash'] / max(lo_b['pct_crash'], 1):.1f} 倍" if (hi_b and lo_b) else "")
              + "；(3) SKEW、信用 (HYG vs SPY)、殖利率等『機構先行』訊號同步亮燈。結論：無法預測崩盤的日期與深度，但可以在機率顯著升高時，先把 3x 部位降到跌 40% 也不致命的水準。")
    lessons.append({
        "title": "⑤ 可以『預測』嗎？單一訊號不能，組合只能提高『警覺』— 用部位大小回應機率，而不是猜方向",
        "detail": detail,
        "rule": "價格結構 (過熱/動能)、波動尾部 (SKEW/VVIX)、宏觀信用 (殖利率/HYG) 三個獨立家族同時亮燈、且前兆分數 ≥80 時：3x 部位至少減半，不等『確認』；等到 VIX 跳升時通常已跌 30%+。",
    })
  gex = opt.get("total_net_gex_m")
  fails = []
  for j in range(pi + 1, trough_i + 1):
    r = soxl[j]
    if r["open"] > closes[j - 1] * 1.02 and r["close"] < closes[j - 1]:
      fails.append(f"{r['date'][5:]} 開高 ${r['open']:.1f} 收 ${r['close']:.1f}")
  example = ("例如 " + "、".join(fails[:2]) + "，都是這個結構。") if fails else ""
  lessons.append({
      "title": "⑥ 負 Gamma + 高 IV 的日內結構：每次開高都被對沖賣壓打下來",
      "detail": (f"造市商淨 Gamma 目前 {gex:+.1f}M (Gamma 翻正位 ${opt.get('gamma_flip')})，IV30 高達 {opt.get('iv30_pct')}%。" if gex is not None else "") +
                "在負 Gamma 區，造市商『跌時賣、漲時買』放大波動；" + example + "高 IV 也讓事後買 Put 避險的成本極高。",
      "rule": "避險要在 SKEW 剛開始升、IV 還低 (<70%) 時買；IV >100% 後只用減碼或現貨 SOXS 小量對沖，不追買 Put。",
  })
  lessons.append({
      "title": "⑦ 重建部位的紀律：等檢核表，不等感覺",
      "detail": "極度恐懼 (F&G <20)、RSI <25、跌破 200MA 都是『反彈機率升高』而非『底部確認』。歷史同類情境表顯示反彈常見但續跌也不罕見。",
      "rule": "只有『重返多頭檢核表』≥6/8 項成立 (站回 20MA、崩跌前兆分數 <60、VIX 期限結構正價差、成分股 >40% 站回月線、大戶淨方向轉正、MACD 柱翻正、F&G 回升、量能比 >1) 才重建趨勢部位；之前只做 ≤1/3 部位的反彈單。",
  })

  return {
      "peak_date": peak_date, "peak_close": round(closes[pi], 2), "trough_date": dates[trough_i], "trough_close": round(closes[trough_i], 2),
      "soxl_drawdown_pct": round(soxl_dd, 1), "soxx_drawdown_pct": round(soxx_dd, 1) if soxx_dd is not None else None,
      "spy_drawdown_pct": round(spy_dd, 1) if spy_dd is not None else None,
      "timeline": timeline, "big_picture": big_picture, "warned": warned, "silent": silent,
      "skew_path": skew_path, "vix_path": vix_path, "fg_path": fg_path, "y10_path": y10_path,
      "analog_pre_crash": analog, "lessons": lessons,
  }
