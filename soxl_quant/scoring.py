#!/usr/bin/env python3
"""-2 ~ +2 multi-factor scorecard (7 dimensions, ~22 factors), fully data-driven.

Each factor carries a `kind`:
  trend       – follows the prevailing direction (buy strength / sell weakness)
  contrarian  – mean-reversion / sentiment extremes (fear = future opportunity)
  flow        – positioning & money-flow evidence
The report shows the composite plus separate Trend and Contrarian sub-scores so
an investor can tell "trend says wait" apart from "sentiment says a bounce is
likely" instead of a single blended number hiding the conflict.
"""

from __future__ import annotations


def esc_label(v: object) -> str:
  return str(v)


def _f(category: str, metric: str, value: str, weight: int, score: int, criteria: str, rationale: str, kind: str) -> dict:
  return {"category": category, "metric": metric, "value": value, "weight": weight,
          "score": max(-2, min(2, int(score))), "criteria": criteria, "rationale": rationale, "kind": kind}


def build(tech: dict, opt: dict, hm: dict, mac: dict, sen: dict, nws: dict, ews: dict) -> dict:
  F: list[dict] = []
  spot = tech["close"]

  # ------------------------------------------------------------------ 1. Options
  C1 = "1. 期權籌碼 (Options Flow)"
  cp = opt.get("cp_vol_ratio") or 0.0
  s = 2 if cp >= 1.6 else (1 if cp >= 1.15 else (0 if cp >= 0.85 else (-1 if cp >= 0.6 else -2)))
  F.append(_f(C1, "Call/Put 成交量比 (今日)", f"{cp:.2f}x (Call {opt['total_call_vol']:,} / Put {opt['total_put_vol']:,})", 4, s,
              "+2: ≥1.6x | +1: 1.15-1.6 | 0: 0.85-1.15 | -1: 0.6-0.85 | -2: <0.6 (Put 主導)",
              f"今日 Put 成交 {opt['total_put_vol']:,} 口 vs Call {opt['total_call_vol']:,} 口；Put/Call = {opt.get('pc_vol_ratio') or 0:.2f}。", "flow"))
  gex = opt.get("total_net_gex_m") or 0.0
  flip = opt.get("gamma_flip")
  s = 2 if gex > 5 else (1 if gex > 0.5 else (0 if gex > -2 else (-1 if gex > -10 else -2)))
  flip_txt = f"Gamma 翻正位 ${flip:.2f}（現價{'上方' if (flip or 0) > spot else '下方'}）" if flip else "無明確 Gamma 翻正位"
  F.append(_f(C1, "淨 Gamma 曝險 & Gamma 翻正位", f"GEX {gex:+.1f}M | {flip_txt}", 5, s,
              "+2: GEX>+5M (造市商壓抑波動) | 0: -2~+0.5M | -2: <-10M (負 Gamma 助漲助跌)",
              ("負 Gamma：造市商順勢對沖，漲跌皆被放大，日內波動劇烈。" if gex < -2 else "正 Gamma：造市商逆勢對沖，波動受壓抑。")
              + (f" 站回 ${flip:.0f} 以上波動才會收斂。" if flip and flip > spot else ""), "flow"))
  skew = opt.get("iv_skew_25d") or 0.0
  s = -2 if skew >= 15 else (-1 if skew >= 6 else (0 if skew >= -3 else 1))
  F.append(_f(C1, "25Δ IV 偏度 (Put IV − Call IV)", f"{skew:+.1f}% (Put {opt.get('avg_put_25d_iv', 0):.0f}% / Call {opt.get('avg_call_25d_iv', 0):.0f}%)", 3, s,
              "+1: Call IV > Put IV (搶多) | 0: 平衡 | -1: Put 溢價 6-15% | -2: Put 溢價 ≥15% (恐慌避險)",
              "Put 溢價越高代表避險需求越強；但極端 Put 溢價歷史上常出現在底部附近 (反指標)。", "flow"))
  w = opt.get("whale", {})
  ws = w.get("whale_net_score")
  s = 0 if ws is None else (2 if ws >= 0.4 else (1 if ws >= 0.12 else (0 if ws > -0.12 else (-1 if ws > -0.4 else -2))))
  F.append(_f(C1, "大戶 (Whale) 期權淨方向", f"淨分數 {ws if ws is not None else 'n/a'} | 大單 Call ${w.get('whale_call_prem_m', 0):.1f}M vs Put ${w.get('whale_put_prem_m', 0):.1f}M (C/P {w.get('whale_cp_ratio') or 'n/a'})",
              4, s, "+2: 淨分數 ≥+0.4 (大戶積極買 Call/賣 Put) | 0: ±0.12 | -2: ≤-0.4 (大戶買 Put/賣 Call)",
              f"偵測到 {w.get('whale_count', 0)} 筆大額新倉 (權利金 ≥$25 萬或 ≥1,500 口且 Vol/OI ≥0.4)；看多金額 ${w.get('whale_bull_prem_m', 0):.1f}M vs 看空 ${w.get('whale_bear_prem_m', 0):.1f}M。散戶小單 C/P = {w.get('retail_cp_ratio') or 'n/a'}。", "flow"))
  mp = opt.get("near_max_pain") or opt.get("monthly_max_pain")
  cw, pw = opt.get("call_wall"), opt.get("put_wall")
  if mp:
    dist = (mp / spot - 1.0) * 100.0
    # Max Pain only acts as a magnet when it is reasonably close; stale OI far away is ignored
    s = 0 if abs(dist) > 15 else (1 if dist >= 5 else (0 if dist > -5 else -1))
    far_note = "（距現價 >15%，多為舊倉、磁吸效果弱，不計分）" if abs(dist) > 15 else ""
    F.append(_f(C1, "Max Pain 與 Call/Put 牆位置", f"近月 Max Pain ${mp:.0f} ({dist:+.1f}%) | Call 牆 ${cw} | Put 牆 ${pw}", 4, s,
                "+1: Max Pain 高於現價 5~15% (到期前有上拉磁吸) | 0: ±5% 或距離 >15% | -1: 低於現價 5~15%",
                f"近月最大痛點 ${mp:.0f}{far_note}；上方最大 Call 未平倉牆 ${cw}（反壓），下方最大 Put 牆 ${pw}（支撐）。", "flow"))

  # ------------------------------------------------------------------ 2. Volume
  C2 = "2. 量能結構 (Volume)"
  ud = tech["up_down_vol_ratio"]
  s = 2 if ud >= 1.35 else (1 if ud >= 1.1 else (0 if ud >= 0.9 else (-1 if ud >= 0.7 else -2)))
  F.append(_f(C2, "20 日上漲/下跌量能比", f"{ud:.2f}x (漲 {tech['up_days_20']} 天 / 跌 {tech['down_days_20']} 天；RVOL {tech['rvol20']:.2f}x)", 5, s,
              "+2: ≥1.35 | +1: 1.1-1.35 | 0: 0.9-1.1 | -1: 0.7-0.9 | -2: <0.7 (派發主導)",
              f"放量吸籌日 {tech['accum_days_20']} 天 vs 放量派發日 {tech['dist_days_20']} 天。", "trend"))
  cmf = tech["cmf20"]
  s = 2 if (cmf >= 0.12 and tech["obv_bullish"]) else (1 if cmf >= 0.03 else (0 if cmf > -0.05 else (-1 if cmf > -0.15 else -2)))
  F.append(_f(C2, "資金流 CMF(20) / OBV / MFI(14)", f"CMF {cmf:+.3f} | OBV {'多' if tech['obv_bullish'] else '空'} | MFI {tech['mfi14']:.0f}", 4, s,
              "+2: CMF≥+0.12 且 OBV 多 | +1: ≥+0.03 | 0: -0.05~+0.03 | -1: -0.15~-0.05 | -2: <-0.15",
              ("資金持續淨流出。" if cmf < -0.05 else "資金淨流入。") + (f" MFI {tech['mfi14']:.0f} 進入超賣 (<20)，賣壓接近極限。" if tech['mfi14'] < 20 else ""), "trend"))
  vw, poc, val, vah = tech["vwap20"], tech["poc_price"], tech["val_price"], tech["vah_price"]
  s = 2 if (spot > vah and spot > vw) else (1 if (spot >= poc and spot >= vw) else (0 if spot >= val else (-1 if spot >= val * 0.9 else -2)))
  F.append(_f(C2, "籌碼位階：20D VWAP / VPVR POC / 價值區", f"現價 ${spot:.2f} | VWAP ${vw:.2f} | POC ${poc:.2f} | 價值區 ${val:.2f}~${vah:.2f}", 5, s,
              "+2: 現價>VAH 且 >VWAP | +1: ≥POC 且 ≥VWAP | 0: 價值區內 | -1: 跌破 VAL | -2: 遠低於 VAL (套牢區在上方)",
              ("現價已跌破半年價值區下緣，上方全是套牢籌碼，反彈到 VAL/POC 附近易遇解套賣壓。" if spot < val else "現價位於價值區內/上方，籌碼結構尚可。"), "trend"))

  # ------------------------------------------------------------------ 3. Technicals
  C3 = "3. 技術趨勢 (Technicals)"
  ms = tech["ma_structure"]
  F.append(_f(C3, "均線結構 (20 / 50 / 200MA)", f"{ms['label']} | 距 20MA {tech['dist_sma20_pct']:+.1f}% / 50MA {tech['dist_sma50_pct']:+.1f}% / 200MA {tech['dist_sma200_pct']:+.1f}%",
              8, ms["score"], "+2: 價>20>50>200 | +1: 多頭回檔 | 0: 糾結 | -1: 跌破 50MA | -2: 跌破 200MA / 空頭排列",
              next((t["detail"] for t in tech["tech_table"] if t["name"].startswith("均線")), ""), "trend"))
  for name_prefix, w_ in (("MACD", 5), ("KD / KDJ", 4), ("多週期 RSI", 4)):
    t = next((x for x in tech["tech_table"] if x["name"].startswith(name_prefix)), None)
    if t:
      F.append(_f(C3, t["name"], t["reading"], w_, t["score"], f"訊號：{t['signal']}", t["detail"], "trend" if name_prefix == "MACD" else "contrarian"))
  fib_t = next((x for x in tech["tech_table"] if x["group"] == "黃金分割"), None)
  ich_t = next((x for x in tech["tech_table"] if x["group"] == "雲圖指標"), None)
  st_t = next((x for x in tech["tech_table"] if x["group"] == "趨勢追蹤"), None)
  conf = [x for x in (fib_t, ich_t, st_t) if x]
  if conf:
    avg = sum(x["score"] for x in conf) / len(conf)
    s = 2 if avg >= 1.5 else (1 if avg >= 0.5 else (0 if avg > -0.5 else (-1 if avg > -1.5 else -2)))
    F.append(_f(C3, "斐波那契 / 一目均衡表 / Supertrend 共振", " | ".join(f"{x['signal']}" for x in conf), 5, s,
                "三指標平均：+2 ≥1.5 | +1 ≥0.5 | 0 | -1 ≤-0.5 | -2 ≤-1.5", " ".join(x["detail"] for x in conf), "trend"))

  # ------------------------------------------------------------------ 4. Breadth
  C4 = "4. 板塊廣度 (Heat Map Breadth)"
  b20, b50, b200, bos = hm["breadth_above_sma20_pct"], hm["breadth_above_sma50_pct"], hm["breadth_above_sma200_pct"], hm["breadth_oversold_pct"]
  s = 2 if (b20 >= 75 and b50 >= 70) else (1 if b20 >= 60 else (0 if b20 >= 40 else (-1 if b20 >= 25 else -2)))
  F.append(_f(C4, "成分股站上 20 / 50 / 200MA 比例", f"{b20:.0f}% / {b50:.0f}% / {b200:.0f}% | RSI<30 佔 {bos:.0f}%", 6, s,
              "+2: ≥75% 上 20MA 且 ≥70% 上 50MA | +1: ≥60% | 0: 40-60% | -1: 25-40% | -2: <25% (全面潰敗)",
              (f"16 檔核心半導體僅 {b20:.0f}% 站在月線上，{bos:.0f}% 已進入 RSI 超賣；" + ("廣度洗到極端通常離短線底部不遠，但需等待首批個股站回月線確認。" if b20 < 25 else "廣度仍弱。")) if b20 < 40 else f"{b20:.0f}% 成分股站上月線，板塊結構{'健康' if b20 >= 60 else '中性'}。", "trend"))
  w5, w20 = hm["weighted_ret_5d"], hm["weighted_ret_20d"]
  s = 2 if (w5 >= 3 and w20 >= 6) else (1 if w20 >= 3 else (0 if w20 > -5 else (-1 if w20 > -15 else -2)))
  F.append(_f(C4, "權值股加權動能 (1D / 5D / 20D)", f"{hm['weighted_ret_1d']:+.2f}% / {w5:+.2f}% / {w20:+.2f}%", 4, s,
              "+2: 5D≥+3% 且 20D≥+6% | +1: 20D≥+3% | 0: 20D -5~+3% | -1: 20D -15~-5% | -2: 20D <-15%",
              "領跌：" + "、".join(f"{c['ticker']} {c['ret_20d']:+.0f}%" for c in sorted(hm["constituents"], key=lambda c: c["ret_20d"])[:4]) + "；相對抗跌：" + "、".join(f"{c['ticker']} {c['ret_20d']:+.0f}%" for c in sorted(hm["constituents"], key=lambda c: -c["ret_20d"])[:3]), "trend"))

  # ------------------------------------------------------------------ 5. Macro
  C5 = "5. 宏觀跨資產 (Macro)"
  lat = mac.get("latest", {})
  y10, y30 = lat.get("TNX_10Y"), lat.get("TYX_30Y")
  if y10 is not None and y30 is not None:
    kpi10 = next((k for k in mac["macro_kpis"] if k["key"] == "TNX_10Y"), {})
    chg20 = kpi10.get("chg_20d", "")
    falling = chg20.startswith("-")
    s = (1 if falling else -1) if y30 >= 5.3 else (2 if (falling and y10 < 4.5) else (1 if y10 < 4.8 else 0))
    F.append(_f(C5, "10Y / 30Y 美債殖利率", f"10Y {y10:.2f}% | 30Y {y30:.2f}% | 10Y 20 日 {chg20}", 4, s,
                "+2: 殖利率回落且 10Y<4.5% | +1: 回落中 / 平穩 | 0: 區間 | -1: 30Y≥5.3% 高檔且上行 | -2: 失控飆升",
                f"{kpi10.get('beta_note', '')}；" + ("殖利率自高檔回落 (資金避險湧入債市) 對估值是緩解，但也反映風險偏好惡化。" if falling else "殖利率仍高，壓抑高估值成長股。"), "trend"))
  br = lat.get("BRENT")
  if br is not None:
    kpi_b = next((k for k in mac["macro_kpis"] if k["key"] == "BRENT"), {})
    if "BRENT" in (mac.get("proxies") or {}):
      chg20 = kpi_b.get("chg_20d", "+0%")
      try:
        c20 = float(chg20.replace("%", "").replace("+", ""))
      except ValueError:
        c20 = 0.0
      s = -2 if c20 >= 15 else (-1 if c20 >= 6 else (0 if c20 > -6 else (1 if c20 > -15 else 2)))
      F.append(_f(C5, "原油走勢 (通膨/利率傳導，ETF 代理)", f"{esc_label(kpi_b.get('name', 'Brent 代理'))} 20 日 {chg20} | 20D 相關 {mac['horizons']['20D']['BRENT']['ret_corr']:+.2f}", 3, s,
                  "+2: 20 日跌 >15% | +1: 跌 6-15% | 0: ±6% | -1: 漲 6-15% | -2: 漲 >15%", kpi_b.get("beta_note", ""), "trend"))
    else:
      s = -2 if br >= 110 else (-1 if br >= 100 else (0 if br >= 90 else (1 if br >= 75 else 2)))
      F.append(_f(C5, "Brent 原油 (通膨/利率傳導)", f"${br:.2f} | 20D 相關 {mac['horizons']['20D']['BRENT']['ret_corr']:+.2f}", 3, s,
                  "+2: <$75 | +1: $75-90 | 0: $90-100 | -1: $100-110 | -2: >$110", kpi_b.get("beta_note", ""), "trend"))
  vx = sen.get("vix", {})
  if vx.get("available"):
    v = vx["vix"]
    s = 1 if v < 16 else (0 if v < 20 else (-1 if v < 25 else (-2 if v < 35 else -1)))
    F.append(_f(C5, "VIX 水位 (趨勢面)", f"VIX {v:.2f} | {vx['vix_regime']} | 1 年百分位 {vx['vix_percentile_1y']:.0f}% | 5 日 {vx['vix_5d_chg_pct']:+.0f}%", 3, s,
                "+1: <16 | 0: 16-20 | -1: 20-25 | -2: 25-35 (高度恐慌，趨勢面極差) | -1: >35 (極端恐慌，反而接近投降)",
                f"與 SOXL 20D 報酬相關 {mac['horizons']['20D']['VIX']['ret_corr']:+.2f}，Beta {mac['beta_vix_20d']:+.2f}x。", "trend"))

  # ------------------------------------------------------------------ 6. Sentiment (contrarian)
  C6 = "6. 市場情緒 (Sentiment, 逆勢指標)"
  fg = sen.get("fear_greed")
  if fg:
    sc_ = fg["score"]
    s = 2 if sc_ < 15 else (1 if sc_ < 30 else (0 if sc_ <= 60 else (-1 if sc_ <= 75 else -2)))
    F.append(_f(C6, "CNN Fear & Greed (逆勢)", f"{sc_:.0f} {fg['rating_zh']} | 一週前 {fg['week_ago']:.0f} | 一月前 {fg['month_ago']:.0f}", 4, s,
                "+2: <15 極度恐懼 (歷史買點區) | +1: 15-30 | 0: 30-60 | -1: 60-75 貪婪 | -2: >75 極度貪婪",
                "七項子指標：" + "；".join(f"{c['label'].split(' (')[0]} {c['score']:.0f}" for c in fg["components"][:7]), "contrarian"))
  if vx.get("available") and vx.get("ratio_vix_3m"):
    r = vx["ratio_vix_3m"]
    s = 1 if r >= 1.05 else (0 if r >= 0.95 else (1 if r <= 0.85 else 0))
    F.append(_f(C6, "VIX 期限結構 (VIX / VIX3M)", f"{r:.2f} → {vx['term_state']} | VIX9D {vx['vix9d']} / VIX {vx['vix']} / VIX3M {vx['vix3m']}", 3, s,
                "+1: ≥1.05 倒掛 (恐慌高峰常見短線底) 或 ≤0.85 健康正價差 | 0: 0.95-1.05 走平 (警訊區)", vx["term_zh"], "contrarian"))
  pc = sen.get("put_call", {})
  if pc.get("available") and pc.get("equity_pc"):
    e5 = pc.get("equity_pc_5d") or pc["equity_pc"]
    s = 2 if e5 >= 0.9 else (1 if e5 >= 0.75 else (0 if e5 >= 0.55 else -1))
    F.append(_f(C6, "CBOE 個股 Put/Call (5 日均, 逆勢)", f"{e5:.2f} (單日 {pc['equity_pc']:.2f}) | 全市場 {pc['total_pc']:.2f} | SPX {pc['spx_pc']}", 3, s,
                "+2: ≥0.90 投降式避險 | +1: 0.75-0.90 | 0: 0.55-0.75 | -1: <0.55 自滿", pc["equity_read"], "contrarian"))
  fl = sen.get("flows", {})
  if fl.get("available"):
    lr, a20 = fl["latest"]["ratio"] or 0, fl["ratio_avg20"] or 1
    s = -1 if lr > a20 * 1.3 else (1 if lr < a20 * 0.7 else 0)
    F.append(_f(C6, "SOXL / SOXS 資金流 (散戶行為)", f"成交金額比 {lr:.2f} (20 日均 {a20:.2f})", 2, s,
                "+1: 散戶轉空/放棄 (比值 <0.7×均值，反指標) | 0: 均衡 | -1: 散戶狂熱接刀 (>1.3×均值)", fl["read"], "contrarian"))
  ews_today = ews.get("today", {})
  if ews_today:
    cr = ews_today["score"]
    s = 1 if cr < 60 else (0 if cr < 80 else -1)
    F.append(_f(C6, "崩跌前兆分數 (Crash Risk Score, 歷史百分位)", f"{cr:.0f} / 100 → {ews_today['zone']} | 觸發訊號 {ews_today['n_active']} 項", 3, s,
                "+1: <60 | 0: 60-80 注意 | -1: ≥80 警戒 (症狀負荷在歷史前 20%)", "由 21 項過熱/動能/波動/宏觀/情緒訊號加權後換算成歷史百分位；此分數偵測『頂部型』崩跌前兆，已在空頭中則以均線結構為準。", "trend"))

  # ------------------------------------------------------------------ 7. News
  C7 = "7. 消息面 (News Sentiment)"
  bb = nws.get("bull_bear_ratio")
  nb, ns = nws.get("recent_bull_count", 0), nws.get("recent_bear_count", 0)
  s = 0 if bb is None else (2 if bb >= 1.6 else (1 if bb >= 1.15 else (0 if bb >= 0.85 else (-1 if bb >= 0.6 else -2))))
  F.append(_f(C7, "近 7 日利多 / 利空新聞比", f"利多 {nb} 則 vs 利空 {ns} 則 ({bb if bb is not None else 'n/a'}x)", 6, s,
              "+2: ≥1.6x | +1: 1.15-1.6 | 0: 0.85-1.15 | -1: 0.6-0.85 | -2: <0.6 (利空洗版)",
              "主題：" + "、".join(f"{t['tag']}×{t['count']}" for t in nws.get("themes_7d", [])[:5]), "trend"))

  tw = sum(f["weight"] for f in F) or 1
  composite = sum(f["score"] * f["weight"] for f in F) / tw

  def sub(kind: str) -> float | None:
    fs = [f for f in F if f["kind"] == kind]
    w_ = sum(f["weight"] for f in fs)
    return round(sum(f["score"] * f["weight"] for f in fs) / w_, 2) if w_ else None

  cats: dict[str, dict] = {}
  for f in F:
    c = cats.setdefault(f["category"], {"category": f["category"], "weight": 0, "ws": 0.0})
    c["weight"] += f["weight"]
    c["ws"] += f["score"] * f["weight"]
  category_scores = [{"category": c["category"], "weight": c["weight"], "avg_score": round(c["ws"] / c["weight"], 2)} for c in cats.values()]

  if composite >= 1.25:
    verdict = "強勢看多 (Strong Bullish)"
  elif composite >= 0.35:
    verdict = "偏多 (Moderately Bullish)"
  elif composite > -0.35:
    verdict = "中性 / 區間 (Neutral)"
  elif composite > -1.25:
    verdict = "偏空 (Moderately Bearish)"
  else:
    verdict = "強勢看空 (Strong Bearish)"
  trend_s, contra_s = sub("trend"), sub("contrarian")
  if trend_s is not None and contra_s is not None:
    if trend_s <= -0.6 and contra_s >= 0.6:
      regime = "空頭趨勢 + 情緒極端 → 『超賣反彈』格局：只做短線反彈、不做趨勢多單"
    elif trend_s >= 0.6 and contra_s <= -0.6:
      regime = "多頭趨勢 + 情緒過熱 → 『漲多拉回』風險區：減碼、勿追高"
    elif trend_s >= 0.6:
      regime = "多頭趨勢且情緒健康 → 順勢持有"
    elif trend_s <= -0.6:
      regime = "空頭趨勢且情緒未到極端 → 保持觀望"
    else:
      regime = "中性震盪 → 區間操作"
  else:
    regime = verdict

  # ---- Beginner-friendly aggregates --------------------------------------
  # (a) TradingView-style 5-zone rating from the composite (-2..+2)
  if composite >= 1.25:
    rating_5, rating_label, rating_emoji = 5, "強力買進", "🟢🟢"
  elif composite >= 0.35:
    rating_5, rating_label, rating_emoji = 4, "買進", "🟢"
  elif composite > -0.35:
    rating_5, rating_label, rating_emoji = 3, "中立 / 觀望", "🟡"
  elif composite > -1.25:
    rating_5, rating_label, rating_emoji = 2, "賣出 / 減碼", "🔴"
  else:
    rating_5, rating_label, rating_emoji = 1, "強力賣出 / 避開", "🔴🔴"
  rating_pos = round((composite + 2.0) / 4.0 * 100.0, 1)  # 0 = strong sell ... 100 = strong buy

  # (b) Analyst-consensus-style Buy / Hold / Sell ratio (weighted by factor weight)
  buy_w = sum(f["weight"] for f in F if f["score"] > 0)
  sell_w = sum(f["weight"] for f in F if f["score"] < 0)
  hold_w = tw - buy_w - sell_w
  n_buy = sum(1 for f in F if f["score"] > 0)
  n_sell = sum(1 for f in F if f["score"] < 0)
  n_hold = len(F) - n_buy - n_sell
  consensus = {
      "buy_pct": round(buy_w / tw * 100.0, 1), "hold_pct": round(hold_w / tw * 100.0, 1), "sell_pct": round(sell_w / tw * 100.0, 1),
      "n_buy": n_buy, "n_hold": n_hold, "n_sell": n_sell,
      "n_strong_buy": sum(1 for f in F if f["score"] == 2), "n_strong_sell": sum(1 for f in F if f["score"] == -2),
      "buy_sell_ratio": round(buy_w / sell_w, 2) if sell_w else None,
  }

  # (c) Agreement across the 7 dimensions -> confidence
  sign = 1 if composite > 0.35 else (-1 if composite < -0.35 else 0)
  agree = sum(1 for c in category_scores if (c["avg_score"] >= 0.35 and sign > 0) or (c["avg_score"] <= -0.35 and sign < 0) or (abs(c["avg_score"]) < 0.35 and sign == 0))
  agree_pct = agree / len(category_scores) * 100.0 if category_scores else 0.0
  confidence = "高" if agree_pct >= 70 else ("中" if agree_pct >= 45 else "低")

  return {"composite_score": round(composite, 2), "verdict": verdict, "trend_score": trend_s, "contrarian_score": contra_s,
          "regime": regime, "factors": F, "category_scores": category_scores, "total_weight": tw,
          "rating_5": rating_5, "rating_label": rating_label, "rating_emoji": rating_emoji, "rating_pos": rating_pos,
          "consensus": consensus, "agreement_pct": round(agree_pct, 0), "confidence": confidence}
