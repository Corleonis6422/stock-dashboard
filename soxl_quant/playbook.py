#!/usr/bin/env python3
"""Investor playbook: plain-language verdict, key price ladder, three data-driven
scenarios with base-rate probabilities, and a re-entry checklist.

Everything here is derived from the other modules' outputs — nothing is typed in
by hand — so the "next step" stays consistent with the data every time the
pipeline runs.
"""

from __future__ import annotations


PLAIN = {
    "EMA5": "極短線均線（5 日）", "EMA10": "短線均線（10 日）", "20MA 月線": "多空停損線：站回才算止跌", "50MA 季線": "中期趨勢線",
    "200MA 年線": "長線牛熊分界", "20D VWAP": "近 20 日平均成本（套牢盤）", "VPVR POC 籌碼峰": "半年來成交最多的價位（解套賣壓區）",
    "價值區下緣 VAL": "半年成交密集區的下緣", "Gamma 翻正位": "站上後造市商改為壓抑波動", "月選 Max Pain": "月選到期前常被吸引的價位",
    "布林下軌": "統計上的超跌邊界（2σ）", "週選 1σ 上緣": "期權定價的一週常態波動上限", "週選 1σ 下緣": "期權定價的一週常態波動下限",
    "月選 1σ 上緣": "期權定價的一個月常態波動上限", "月選 1σ 下緣": "期權定價的一個月常態波動下限",
    "近 10 日最高": "短線反彈第一道關卡", "近 10 日最低": "跌破 = 續跌確認", "52 週最低": "一年來最低價",
    "Fib 23.6% 反彈位": "反彈第一道技術關卡", "Fib 38.2% 反彈位": "反彈第二道關卡（收復才算像樣反彈）", "Fib 50% 反彈位": "反彈中線關卡",
    "Fib 61.8% 反彈位": "收復此位跌勢多半結束", "Fib 38.2%": "回檔第一道支撐", "Fib 50%": "回檔中線支撐", "Fib 61.8%": "黃金分割最後支撐", "Fib 78.6%": "深度回撤支撐",
}


def _plain(label: str) -> str:
  for k, v in PLAIN.items():
    if label.startswith(k):
      return v
  if label.startswith("Call 牆"):
    return "大量買權未平倉 → 反壓"
  if label.startswith("Put 牆"):
    return "大量賣權未平倉 → 支撐"
  if label.startswith("前波恐慌低點"):
    return "上一次崩跌的最低點"
  return ""


def _dedupe(levels: list[dict], tol: float = 0.012) -> list[dict]:
  out: list[dict] = []
  for lv in levels:
    if any(abs(lv["price"] / o["price"] - 1.0) < tol for o in out):
      for o in out:
        if abs(lv["price"] / o["price"] - 1.0) < tol and lv["label"] not in o["label"]:
          o["label"] = f"{o['label']} / {lv['label']}"
      continue
    out.append(dict(lv))
  return out


def build(tech: dict, opt: dict, sen: dict, hm: dict, ews: dict, score: dict, soxl_rows: list[dict]) -> dict:
  spot = tech["close"]
  fc = opt.get("forecast", {})
  swing = tech["swing"]
  fib = swing["levels"]
  recent_low = min(r["low"] for r in soxl_rows[-10:])
  recent_high = max(r["high"] for r in soxl_rows[-10:])

  # -------------------------------------------------------------- levels
  cands = []

  def add(price, label, kind, note=""):
    if price and price > 0:
      cands.append({"price": float(price), "label": label, "kind": kind, "note": note})

  add(tech["ema5"], "EMA5", "res" if tech["ema5"] > spot else "sup", "5 日均線")
  add(tech["ema10"], "EMA10", "res" if tech["ema10"] > spot else "sup", "10 日均線")
  add(tech["sma20"], "20MA 月線", "res" if tech["sma20"] > spot else "sup", "多空停損線")
  add(tech["sma50"], "50MA 季線", "res" if tech["sma50"] > spot else "sup", "")
  add(tech["sma200"], "200MA 年線", "res" if tech["sma200"] > spot else "sup", "牛熊分界")
  add(tech["vwap20"], "20D VWAP", "res" if tech["vwap20"] > spot else "sup", "近 20 日平均成本")
  add(tech["poc_price"], "VPVR POC 籌碼峰", "res" if tech["poc_price"] > spot else "sup", "半年最大成交量價位")
  add(tech["val_price"], "價值區下緣 VAL", "res" if tech["val_price"] > spot else "sup", "")
  if swing["kind"] == "down":
    for k, lbl in (("fib_236", "Fib 23.6% 反彈位"), ("fib_382", "Fib 38.2% 反彈位"), ("fib_500", "Fib 50% 反彈位"), ("fib_618", "Fib 61.8% 反彈位")):
      add(fib[k], lbl, "res" if fib[k] > spot else "sup", f"{swing['high_date']} 高 → {swing['low_date']} 低")
  else:
    for k, lbl in (("fib_382", "Fib 38.2%"), ("fib_500", "Fib 50%"), ("fib_618", "Fib 61.8%"), ("fib_786", "Fib 78.6%")):
      add(fib[k], lbl, "res" if fib[k] > spot else "sup", "")
  if opt.get("gamma_flip"):
    add(opt["gamma_flip"], "Gamma 翻正位", "res" if opt["gamma_flip"] > spot else "sup", "站上後造市商轉為壓抑波動")
  if opt.get("call_wall"):
    add(opt["call_wall"], f"Call 牆 (OI {opt.get('call_wall_oi', 0):,})", "res" if opt["call_wall"] > spot else "sup", "最大 Call 未平倉")
  if opt.get("put_wall"):
    add(opt["put_wall"], f"Put 牆 (OI {opt.get('put_wall_oi', 0):,})", "res" if opt["put_wall"] > spot else "sup", "最大 Put 未平倉")
  mp = opt.get("monthly_max_pain") or opt.get("near_max_pain")
  if mp:
    add(mp, "月選 Max Pain", "res" if mp > spot else "sup", opt.get("monthly_expiration", ""))
  if fc.get("weekly"):
    add(fc["weekly"]["low"], "週選 1σ 下緣", "sup", f"預期波動 ±{fc['weekly']['expected_move_pct']}%")
    add(fc["weekly"]["high"], "週選 1σ 上緣", "res", f"預期波動 ±{fc['weekly']['expected_move_pct']}%")
  if fc.get("monthly"):
    add(fc["monthly"]["low"], "月選 1σ 下緣", "sup", f"±{fc['monthly']['expected_move_pct']}%")
    add(fc["monthly"]["high"], "月選 1σ 上緣", "res", f"±{fc['monthly']['expected_move_pct']}%")
  add(recent_low, "近 10 日最低", "sup", "跌破 = 續跌確認")
  add(recent_high, "近 10 日最高", "res", "")
  add(tech["bb_lower"], "布林下軌", "sup" if tech["bb_lower"] < spot else "res", "2σ 統計極端")
  if tech["low_52w"] >= spot * 0.5:
    add(tech["low_52w"], "52 週最低", "sup", "")
  # Major-swing low (e.g. previous panic low) is a key support if below spot
  ms = tech.get("major_swing") or {}
  if ms.get("low_price") and spot * 0.65 <= ms["low_price"] < spot and ms["low_date"] != swing["low_date"]:
    add(ms["low_price"], f"前波恐慌低點 ({ms['low_date']})", "sup", "跌破則下方無近期支撐")
  res = sorted([c for c in cands if c["price"] > spot * 1.003], key=lambda c: c["price"])
  sup = sorted([c for c in cands if c["price"] < spot * 0.997], key=lambda c: -c["price"])
  res, sup = _dedupe(res)[:6], _dedupe(sup)[:6]
  for lv in res + sup:
    hint = _plain(lv["label"].split(" / ")[0])
    lv["note"] = hint if hint else lv.get("note", "")
  ladder = [dict(r, kind="res") for r in reversed(res)] + [{"price": spot, "label": "現價", "kind": "cur", "note": tech["latest_date"] + " 收盤"}] + [dict(s, kind="sup") for s in sup]

  # -------------------------------------------------------------- probabilities from analogs
  conds = {c["condition"]: c for c in ews.get("analogs", {}).get("conditions", [])}
  prefer = ["10 日跌幅 ≤ -30% (崩跌後)", "5 日跌幅 ≤ -20% (急跌後)", "RSI(14) < 25 (極度超賣)", "距 52 週高點回撤 ≥ 40% 且 VIX ≥ 20",
            "跌破 200 日均線 >10% (趨勢受損)", "CNN Fear & Greed < 20 (極度恐懼)", "全部交易日 (基準)"]
  ref = None
  for name in prefer:
    c = conds.get(name)
    if c and c.get("active_today") and c.get("horizons", {}).get("10d") and (c.get("n_days") or 0) >= 8:
      ref = c
      break
  if ref is None:
    ref = conds.get("全部交易日 (基準)")
  h10 = (ref or {}).get("horizons", {}).get("10d", {})
  p_up10 = h10.get("pct_up10", 30.0)
  p_dn10 = h10.get("pct_down10", 25.0)
  p_mid = max(0.0, 100.0 - p_up10 - p_dn10)

  r1 = res[0] if res else None
  r2 = res[1] if len(res) > 1 else r1
  s1 = sup[0] if sup else None
  s2 = sup[1] if len(sup) > 1 else s1
  trend_s = score.get("trend_score")
  contra_s = score.get("contrarian_score")
  crash = ews.get("today", {}).get("score", 0)

  scenarios = [
      {
          "key": "A", "tone": "bull", "title": f"劇本 A：超跌反彈 (10 日內 ≥ +10%)", "prob": round(p_up10),
          "trigger": (f"收盤站回 {r1['label']} ${r1['price']:.2f}" + (f"，並帶量突破 {r2['label']} ${r2['price']:.2f}" if r2 and r2 is not r1 else "")) if r1 else "出現帶量長紅",
          "target": (f"反彈目標 {r2['label']} ${r2['price']:.2f}" if r2 else "") + (f" → 月選 1σ 上緣 ${fc['monthly']['high']:.2f}" if fc.get("monthly") else ""),
          "action": "只做反彈、不做趨勢多單：分批小量 (≤1/3 部位)，反彈至第一道反壓減碼；守住進場日低點為停損。",
      },
      {
          "key": "B", "tone": "neutral", "title": f"劇本 B：區間築底 / 弱勢盤整 (±10% 以內)", "prob": round(p_mid),
          "trigger": (f"在 {s1['label']} ${s1['price']:.2f} ~ {r1['label']} ${r1['price']:.2f} 之間來回" if (s1 and r1) else "量縮盤整"),
          "target": f"等待 20MA ${tech['sma20']:.2f} 走平、崩跌前兆分數回落 <60、成分股站回月線比例 >40%",
          "action": "觀望為主；可用賣出價外 Put (Put 牆附近) 收高 IV 權利金，或等底部型態 (W 底 / 突破下降趨勢線) 再進場。",
      },
      {
          "key": "C", "tone": "bear", "title": f"劇本 C：續跌 (10 日內 ≤ -10%)", "prob": round(p_dn10),
          "trigger": (f"收盤跌破 {s1['label']} ${s1['price']:.2f}" + (f" → 下探 {s2['label']} ${s2['price']:.2f}" if s2 and s2 is not s1 else "")) if s1 else "再出現放量長黑",
          "target": (f"月選 1σ 下緣 ${fc['monthly']['low']:.2f}" if fc.get("monthly") else "") + (f"；2σ 極端 ${fc['iv_cone'][2]['p2_5']:.2f}" if len(fc.get("iv_cone", [])) > 2 else ""),
          "action": "嚴守停損、不攤平 3x 槓桿；留意 SOXS/避險 Put 成本已高 (IV 極高)，避免在恐慌高點追買避險。",
      },
  ]

  # -------------------------------------------------------------- headline & bullets
  dd = tech["drawdown_from_52w_high_pct"]
  ma_lbl = tech["ma_structure"]["label"]
  fg = sen.get("fear_greed") or {}
  vx = sen.get("vix") or {}
  w = opt.get("whale", {})
  if (trend_s or 0) <= -0.6 and (contra_s or 0) >= 0.6:
    headline = f"空頭趨勢 + 情緒極端 ({fg.get('rating_zh', '')})：現在是『超賣反彈區』而不是『趨勢買點』— 只做反彈、不重壓"
  elif (trend_s or 0) <= -0.6:
    headline = "趨勢已轉空、情緒尚未投降：保持觀望，等待底部確認"
  elif (trend_s or 0) >= 0.6 and (contra_s or 0) <= -0.6:
    headline = "多頭趨勢但情緒過熱：減碼、不追高"
  elif (trend_s or 0) >= 0.6:
    headline = "多頭趨勢且情緒健康：順勢持有，逢回加碼"
  else:
    headline = "多空拉鋸：區間操作，等待方向表態"
  bullets = [
      f"位置：收盤 ${spot:.2f}，距 52 週高點 {dd:+.1f}%，均線結構為「{ma_lbl}」，RSI(14) {tech['rsi14']:.0f}，20 日實現波動率 {tech['realized_vol_20d_ann_pct']:.0f}%（年化）。",
      f"情緒：CNN Fear & Greed {fg.get('score', 'n/a')} ({fg.get('rating_zh', '')})、VIX {vx.get('vix', 'n/a')} ({vx.get('term_state', '')})、SKEW {vx.get('skew', 'n/a')}、個股 P/C {sen.get('put_call', {}).get('equity_pc', 'n/a')}。",
      f"籌碼：SOXL 期權 Put/Call 成交 {opt.get('pc_vol_ratio')}、淨 GEX {opt.get('total_net_gex_m'):+.1f}M、大戶淨方向 {w.get('whale_net_score')}、Put 牆 ${opt.get('put_wall')} / Call 牆 ${opt.get('call_wall')}、IV30 {opt.get('iv30_pct')}%。",
      f"風險：崩跌預警分數 {crash:.0f}/100 ({ews.get('today', {}).get('zone', '')})；歷史同類情境 10 日後上漲機率 {h10.get('pct_positive', 'n/a')}%、中位數 {h10.get('median', 'n/a')}%（樣本 {ref.get('n_days') if ref else 'n/a'} 日，情境：{(ref or {}).get('condition', '')}）。",
  ]

  # -------------------------------------------------------------- re-entry checklist
  b20 = hm.get("breadth_above_sma20_pct", 0)
  checks = [
      {"item": "收盤站回 20 日均線 (多頭停損線)", "ok": spot > tech["sma20"], "now": f"現價 ${spot:.2f} vs 20MA ${tech['sma20']:.2f}"},
      {"item": "崩跌前兆分數 < 60 (症狀負荷回到歷史中位數以下)", "ok": crash < 60, "now": f"{crash:.0f}/100"},
      {"item": "VIX 期限結構回到正價差 (VIX/VIX3M < 0.92)", "ok": (vx.get("ratio_vix_3m") or 1) < 0.92, "now": f"{vx.get('ratio_vix_3m', 'n/a')}"},
      {"item": "成分股站上 20MA 比例 > 40%", "ok": b20 > 40, "now": f"{b20:.0f}%"},
      {"item": "大戶期權淨方向轉正 (≥ 0)", "ok": (w.get("whale_net_score") or 0) >= 0, "now": f"{w.get('whale_net_score')}"},
      {"item": "MACD 柱體連續 2 日收斂 / 翻正 (動能止跌)", "ok": tech["macd_hist"] > 0, "now": f"Hist {tech['macd_hist']:+.2f}"},
      {"item": "Fear & Greed 從極度恐懼區回升 (> 25 且上升)", "ok": (fg.get("score") or 0) > 25 and (fg.get("score") or 0) > (fg.get("previous_close") or 0), "now": f"{fg.get('score', 'n/a')} (前值 {fg.get('previous_close', 'n/a')})"},
      {"item": "5 日上漲/下跌量能比 > 1 (買盤回流)", "ok": tech["up_down_vol_ratio"] > 1.0, "now": f"20D U/D {tech['up_down_vol_ratio']:.2f}x"},
  ]
  passed = sum(1 for c in checks if c["ok"])
  checklist_verdict = ("✅ 條件充分：可開始分批建立趨勢部位" if passed >= 6 else ("🟡 部分條件成立：僅限小量反彈單" if passed >= 3 else "⛔ 條件不足：持續觀望 / 只做極短線反彈"))

  # -------------------------------------------------------------- beginner block
  comp = score.get("composite_score", 0.0)
  rating = score.get("rating_5", 3)
  missing = [c for c in checks if not c["ok"]]
  stop_lvl = s1["price"] if s1 else spot * 0.9
  first_res = r1["price"] if r1 else spot * 1.1
  second_res = r2["price"] if r2 else first_res
  below_20 = spot < tech["sma20"]
  below_200 = spot < tech["sma200"]

  if rating <= 1:
    verdict, color, emoji = "強力賣出 / 避開", "bear", "🔴🔴"
    one_liner = "多數訊號一面倒偏空：沒部位的人不要買，有部位的人優先減碼。"
  elif rating == 2:
    verdict, color, emoji = ("賣出 / 減碼" if passed < 3 else "減碼 / 觀望"), "bear", "🔴"
    one_liner = ("趨勢偏空、底部條件還沒成立：現在不是買點。" if passed < 3 else "趨勢偏空但部分止跌條件出現：持有者減碼觀望，不加碼。")
  elif rating == 3:
    verdict, color, emoji = "觀望 / 持有不加碼", "neutral", "🟡"
    one_liner = "多空訊號打平：不開新倉；已持有者續抱但設好停損。"
  elif rating == 4:
    verdict, color, emoji = ("分批買進" if passed >= 5 else "觀望偏多 (等確認)"), ("bull" if passed >= 5 else "neutral"), ("🟢" if passed >= 5 else "🟡")
    one_liner = ("訊號偏多且確認條件多數成立：可以分批建立部位。" if passed >= 5 else "訊號偏多但確認條件不足：等檢核表再多幾項成立再進場。")
  else:
    verdict, color, emoji = ("買進 / 持有" if passed >= 6 else "分批買進"), "bull", "🟢🟢"
    one_liner = "多數訊號一致偏多：順勢持有，回檔分批加碼。"
  if (trend_s or 0) <= -0.6 and (contra_s or 0) >= 0.6:
    one_liner += " 情緒已到極端 → 反彈機率升高，但只適合小量短線，不是趨勢買點。"

  # position sizing (share of the investor's own maximum SOXL allocation)
  if passed >= 8 and rating >= 4:
    size_pct, size_note = 100, "檢核表全數成立且評分偏多：可達到你的滿額 SOXL 配置"
  elif passed >= 6 and rating >= 3:
    size_pct, size_note = 50, "多數確認條件成立：先建到 50%，站穩後再加"
  elif passed >= 3:
    size_pct, size_note = 25, "部分條件成立：最多 25%，且只做反彈單"
  else:
    size_pct, size_note = 10, "條件不足：趨勢部位 0%；若要搶反彈，總額 ≤10% 且嚴守停損"
  if rating <= 2 and passed < 3:
    size_pct = 0 if rating == 1 else 10

  q_no_position = (
      f"❌ 現在不要買。" + (f" 真的想搶反彈：最多用 ≤{size_pct}% 的規劃部位，進場後跌破 ${stop_lvl:,.2f}（{s1['label'] if s1 else '近期低點'}）就出場，反彈到 ${first_res:,.2f}（{r1['label'] if r1 else '第一道反壓'}）先減一半。" if size_pct > 0 else " 連反彈單都不建議，等檢核表至少 3 項成立。")
      if rating <= 2 else (
          f"⏸ 先別急。等價格站回 20 日均線 ${tech['sma20']:,.2f} 或檢核表 ≥6 項成立再分批進場；想先佈局也只用 ≤{size_pct}%。" if rating == 3 else
          f"✅ 可以分批買：先買 1/3，守 ${stop_lvl:,.2f} 停損；站穩 ${first_res:,.2f} 再加 1/3；總曝險不超過規劃的 {size_pct}%。"))
  if rating <= 2 or (below_20 and (crash >= 80 or (trend_s or 0) <= -1.0)):
    q_holder = (f"📉 減碼至少一半，剩下的部位跌破 ${stop_lvl:,.2f} 全出；不要攤平 3 倍槓桿。反彈到 ${first_res:,.2f}～${second_res:,.2f} 是減碼點，不是加碼點。")
  elif rating == 3:
    q_holder = f"✋ 續抱但不加碼；停損設在 ${stop_lvl:,.2f}，站回 ${first_res:,.2f} 之前不要有「回本就好」的期待。"
  else:
    q_holder = f"👍 續抱。停損上移到 ${max(stop_lvl, tech['supertrend'] if tech.get('supertrend_bull') else stop_lvl):,.2f}，回檔到 ${tech['sma20']:,.2f} 附近可加碼。"
  q_when = ("現在就是可以分批買的時候（見上）。" if rating >= 4 and passed >= 5 else
            "最先要看到這幾件事：" + "；".join(f"{c['item'].split(' (')[0]}（目前 {c['now']}）" for c in missing[:3]) + f"。目前 {passed}/{len(checks)} 項成立。")

  # bull / bear case from the scorecard factors (weight × score)
  fs = score.get("factors", [])
  bull_case = [{"metric": f["metric"], "value": f["value"], "why": f["rationale"], "pts": f["score"] * f["weight"]} for f in sorted(fs, key=lambda f: -(f["score"] * f["weight"])) if f["score"] > 0][:4]
  bear_case = [{"metric": f["metric"], "value": f["value"], "why": f["rationale"], "pts": f["score"] * f["weight"]} for f in sorted(fs, key=lambda f: (f["score"] * f["weight"])) if f["score"] < 0][:4]

  cons = score.get("consensus", {})
  tldr = [
      f"{emoji} 結論：{verdict}（綜合 {comp:+.2f}，{cons.get('sell_pct', 0):.0f}% 權重偏空 / {cons.get('hold_pct', 0):.0f}% 中性 / {cons.get('buy_pct', 0):.0f}% 偏多，信心{score.get('confidence', '中')}）。",
      (f"最大空方理由：{bear_case[0]['metric']}（{bear_case[0]['value']}）" if bear_case else "空方理由不明顯") + "；" + (f"最大多方理由：{bull_case[0]['metric']}（{bull_case[0]['value']}）" if bull_case else "多方理由不明顯") + "。",
      f"計畫：守 ${stop_lvl:,.2f}、看 ${first_res:,.2f} → ${second_res:,.2f}；10 日內反彈 ≥10% 機率 {round(p_up10)}%、續跌 ≥10% 機率 {round(p_dn10)}%（歷史同類情境）。",
  ]
  plan = {
      "entry": (f"站回 ${first_res:,.2f} 且量能比 >1 時第一批；或在 ${stop_lvl:,.2f} 上方分批試單（僅限反彈單）" if rating <= 3 else f"現價～${stop_lvl:,.2f} 之間分批"),
      "stop": f"收盤跌破 ${stop_lvl:,.2f}（{s1['label'] if s1 else '近期低點'}）",
      "target": f"${first_res:,.2f}（{r1['label'] if r1 else ''}） → ${second_res:,.2f}（{r2['label'] if r2 else ''}）",
      "risk_reward": round((first_res - spot) / max(spot - stop_lvl, 0.01), 1) if first_res > spot > stop_lvl else None,
      "max_size_pct": size_pct,
      "stop_price": round(stop_lvl, 2), "stop_label": (s1["label"] if s1 else "近期低點"),
      "stop_dist_pct": round((stop_lvl / spot - 1.0) * 100.0, 1) if spot else None,
      "target1_price": round(first_res, 2), "target1_label": (r1["label"] if r1 else "第一道反壓"),
      "target1_dist_pct": round((first_res / spot - 1.0) * 100.0, 1) if spot else None,
      "target2_price": round(second_res, 2), "target2_label": (r2["label"] if r2 else "第二道反壓"),
      "target2_dist_pct": round((second_res / spot - 1.0) * 100.0, 1) if spot else None,
  }
  exps = opt.get("expirations") or []
  next_exp = exps[0] if exps else {}
  nw_themes = []
  mp_next = next_exp.get("max_pain")
  mp_note = "（離現價遠、磁吸效果弱）" if (mp_next and abs(mp_next / spot - 1.0) > 0.15) else ""
  watch = [
      f"價格：守 ${stop_lvl:,.2f}（{s1['label'] if s1 else ''}）、攻 ${first_res:,.2f}（{r1['label'] if r1 else ''}）",
      f"期權：{next_exp.get('expiration', 'n/a')} 到期（Max Pain ${mp_next if mp_next is not None else 'n/a'}{mp_note}，P/C {next_exp.get('pc_vol', 'n/a')}）；Gamma 翻正位 ${opt.get('gamma_flip', 'n/a')}",
      f"情緒：Fear & Greed {fg.get('score', 'n/a')} 是否回升 >25；VIX {vx.get('vix', 'n/a')} 與期限結構 {vx.get('ratio_vix_3m', 'n/a')}（<0.92 才算回穩）",
      f"板塊：16 檔成分股站上 20MA 比例 {b20:.0f}% → 目標 >40%；大戶期權淨方向 {w.get('whale_net_score', 'n/a')} → 轉正",
      f"崩跌前兆分數 {crash:.0f} → 回落 <60",
  ]
  beginner = {
      "verdict": verdict, "color": color, "emoji": emoji, "one_liner": one_liner,
      "rating_5": rating, "rating_label": score.get("rating_label"), "rating_pos": score.get("rating_pos"),
      "consensus": cons, "confidence": score.get("confidence"), "agreement_pct": score.get("agreement_pct"),
      "q_no_position": q_no_position, "q_holder": q_holder, "q_when": q_when,
      "size_pct": size_pct, "size_note": size_note,
      "tldr": tldr, "bull_case": bull_case, "bear_case": bear_case, "plan": plan, "watch": watch,
  }

  return {
      "headline": headline, "bullets": bullets, "ladder": ladder, "scenarios": scenarios,
      "analog_reference": (ref or {}).get("condition"), "analog_h10": h10,
      "checklist": checks, "checklist_passed": passed, "checklist_total": len(checks),
      "checklist_verdict": checklist_verdict, "beginner": beginner,
  }
