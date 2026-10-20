#!/usr/bin/env python3
"""Data-driven price / volume / technical regime analysis for SOXL.

Every signal label, score (-2..+2) and explanatory sentence is derived from the
numbers at run time (no hard-coded dates or price levels), so the report stays
accurate whenever the pipeline is re-run.
"""

from __future__ import annotations

import math
import statistics

from . import indicators as ind


def _fmt_money(v: float) -> str:
  return f"${v:,.2f}"


def _ma_structure(close: float, s20: float, s50: float, s200: float) -> tuple[str, int, str]:
  """Classify moving-average structure. Returns (label, score, detail)."""
  if close > s20 > s50 > s200:
    return ("完全多頭排列 (Bullish Alignment)", 2,
            f"現價站穩 20MA({_fmt_money(s20)}) > 50MA({_fmt_money(s50)}) > 200MA({_fmt_money(s200)})，中長線多頭結構完整。")
  if close < s20 and close > s50 and close > s200 and s50 > s200:
    return ("多頭回檔 (Pullback in Uptrend)", 1,
            f"現價跌破 20MA({_fmt_money(s20)}) 但守住 50MA({_fmt_money(s50)}) 與 200MA({_fmt_money(s200)})，屬多頭趨勢中的健康回檔。")
  if close < s50 and close > s200:
    return ("中期修正 (Correction, 守 200MA)", -1,
            f"現價已跌破 50MA 季線({_fmt_money(s50)})，下方僅剩 200MA 年線({_fmt_money(s200)}) 為最後中期防線。")
  if close < s200 and s50 > s200:
    return ("跌破年線 (Below 200MA)", -2,
            f"現價跌破 200MA 年線({_fmt_money(s200)})，雖 50MA 仍高於 200MA，但趨勢結構已嚴重受損，需等待站回年線。")
  if close < s200 and s50 <= s200:
    return ("空頭排列 (Bearish Alignment)", -2,
            f"50MA({_fmt_money(s50)}) 已下穿 200MA({_fmt_money(s200)}) 形成死亡交叉，現價位於所有均線之下，為標準空頭排列。")
  return ("均線糾結 (Mixed)", 0, "短中長期均線交錯糾結，方向不明，等待表態。")


def _macd_signal(dif: list[float], dea: list[float], hist: list[float]) -> tuple[str, int, str]:
  d, s, h, hp = dif[-1], dea[-1], hist[-1], hist[-2]
  cross_up = hist[-2] <= 0 < hist[-1]
  cross_dn = hist[-2] >= 0 > hist[-1]
  if d > 0 and h > 0 and h >= hp:
    return ("零軸上多頭擴張", 2, f"DIF({d:+.2f}) 與 DEA({s:+.2f}) 皆在零軸上方且紅柱擴大({h:+.2f})，多頭動能增強。")
  if d > 0 and h > 0:
    return ("零軸上多頭 (柱體收斂)", 1, f"DIF({d:+.2f}) 在零軸上方，紅柱由 {hp:+.2f} 收斂至 {h:+.2f}，短線動能降溫。")
  if cross_dn:
    return ("剛形成死亡交叉", -1, f"DIF({d:+.2f}) 下穿 DEA({s:+.2f})，柱體翻負({h:+.2f})，動能轉空。")
  if cross_up:
    return ("剛形成黃金交叉", 1, f"DIF({d:+.2f}) 上穿 DEA({s:+.2f})，柱體翻正({h:+.2f})，動能轉多。")
  if d < 0 and h < 0 and h < hp:
    return ("零軸下空頭擴張", -2, f"DIF({d:+.2f}) 與 DEA({s:+.2f}) 皆在零軸下方且綠柱擴大({h:+.2f})，空方動能仍在加速。")
  if d < 0 and h < 0 and h >= hp:
    return ("零軸下空頭 (綠柱收斂)", -1, f"DIF({d:+.2f}) 在零軸下方，綠柱由 {hp:+.2f} 收斂至 {h:+.2f}，跌勢動能放緩、醞釀背離。")
  if d < 0 and h > 0:
    return ("零軸下金叉反彈", 0, f"DIF({d:+.2f}) 雖仍在零軸下方，但柱體已翻正({h:+.2f})，屬弱勢反彈需站回零軸確認。")
  return ("多空轉換", 0, f"DIF({d:+.2f}) / DEA({s:+.2f}) 接近零軸糾結。")


def _kd_signal(k: list[float], d: list[float], j: list[float]) -> tuple[str, int, str]:
  kv, dv, jv = k[-1], d[-1], j[-1]
  cross_up = k[-2] <= d[-2] and kv > dv
  cross_dn = k[-2] >= d[-2] and kv < dv
  if kv < 20 and (dv < 25 or jv < 0):
    if cross_up or kv > k[-2]:
      return ("低檔金叉 / 超賣反彈", 1, f"K({kv:.1f}) 處於 20 以下超賣區且勾頭向上 (D={dv:.1f})，短線反彈訊號浮現 (J={jv:.1f})。")
    return ("低檔鈍化 (超賣)", 0, f"K({kv:.1f}) / D({dv:.1f}) 位於超賣區、J={jv:.1f} 已跌到 0 以下，急跌後進入低檔鈍化；反彈需待 K 上穿 D 確認，鈍化期間仍可能續跌。")
  if kv > 80 and dv > 80:
    if cross_dn:
      return ("高檔死叉", -1, f"K({kv:.1f}) 在 80 以上超買區下穿 D({dv:.1f})，為高檔回檔警訊。")
    return ("高檔鈍化 (超買)", 1, f"K({kv:.1f}) / D({dv:.1f}) 皆位於 80 以上強勢鈍化區，趨勢強勁但隨時可能回檔。")
  if cross_up:
    return ("金叉向上", 1, f"K({kv:.1f}) 上穿 D({dv:.1f})，J 值 {jv:.1f} 向上。")
  if cross_dn:
    return ("死叉向下", -1, f"K({kv:.1f}) 下穿 D({dv:.1f})，J 值 {jv:.1f} 急挫。")
  if kv > dv:
    return ("K > D 偏多", 1, f"K({kv:.1f}) 高於 D({dv:.1f})，J={jv:.1f}。")
  return ("K < D 偏空", -1, f"K({kv:.1f}) 低於 D({dv:.1f})，J={jv:.1f}。")


def _rsi_signal(r6: float, r14: float, r24: float) -> tuple[str, int, str]:
  if r14 < 30:
    return ("超賣區 (Oversold)", 1 if r6 < 20 else 0,
            f"RSI(14)={r14:.1f} 跌入 30 以下超賣區，RSI(6)={r6:.1f}，歷史上此區間常出現技術性反彈，但超賣可持續。")
  if r14 > 70:
    return ("超買區 (Overbought)", -1 if r6 > 85 else 0,
            f"RSI(14)={r14:.1f} 進入 70 以上超買區 (RSI6={r6:.1f})，追價風險升高。")
  if r14 >= 50 and r24 >= 50:
    return ("中多守穩 (>50)", 1, f"RSI(14)={r14:.1f}、RSI(24)={r24:.1f} 守穩 50 多空分水嶺之上。")
  if r14 < 50 and r24 < 50:
    return ("中空偏弱 (<50)", -1, f"RSI(14)={r14:.1f}、RSI(24)={r24:.1f} 皆跌破 50 分水嶺，趨勢轉弱。")
  return ("中性整理", 0, f"RSI(6/14/24)={r6:.1f}/{r14:.1f}/{r24:.1f}，多空分歧。")


def _adx_signal(pdi: float, ndi: float, adx: float) -> tuple[str, int, str]:
  strong = adx >= 25
  if pdi > ndi:
    return (("強勢多頭趨勢" if strong else "多方略佔優 (趨勢弱)"), 1 if strong else 0,
            f"+DI({pdi:.1f}) > -DI({ndi:.1f})，ADX={adx:.1f}{'（≥25 趨勢明確）' if strong else '（<25 趨勢不明顯，屬震盪）'}。")
  return (("強勢空頭趨勢" if strong else "空方略佔優 (趨勢弱)"), -2 if (strong and adx >= 35) else (-1 if strong else 0),
          f"-DI({ndi:.1f}) > +DI({pdi:.1f})，ADX={adx:.1f}{'（≥25 空頭趨勢明確，勿輕易接刀）' if strong else '（<25 尚未形成單邊趨勢）'}。")


def _bb_signal(close: float, mid: float, upper: float, lower: float, pct_b: float, width: float) -> tuple[str, int, str]:
  if pct_b < 0:
    return ("跌破下軌 (極端超賣)", 0, f"%B={pct_b:.2f} 收在布林下軌({_fmt_money(lower)})之外，屬統計極端 (2σ)，短線反彈機率高但需量能配合。")
  if pct_b < 0.2:
    return ("貼近下軌", 0, f"%B={pct_b:.2f}，股價貼近下軌({_fmt_money(lower)})，通道寬度 {width:.1f}%。")
  if pct_b > 1:
    return ("突破上軌 (強勢/超買)", 1, f"%B={pct_b:.2f} 突破上軌({_fmt_money(upper)})，強勢但乖離過大。")
  if pct_b >= 0.5:
    return ("中軌上方偏多", 1, f"%B={pct_b:.2f}，股價位於中軌({_fmt_money(mid)})上方。")
  return ("中軌下方偏空", -1, f"%B={pct_b:.2f}，股價位於中軌({_fmt_money(mid)})下方，通道寬度 {width:.1f}%。")


def _ichimoku_signal(close: float, tenkan: float, kijun: float, top: float, bot: float) -> tuple[str, int, str]:
  if close > top and close > kijun:
    return ("雲上多頭", 2, f"現價位於雲帶({_fmt_money(bot)}~{_fmt_money(top)})與基準線({_fmt_money(kijun)})之上。")
  if close > top:
    return ("雲上但跌破基準線", 1, f"現價仍在雲帶上方，但已跌破基準線({_fmt_money(kijun)})，需觀察雲頂({_fmt_money(top)})支撐。")
  if bot <= close <= top:
    return ("雲中整理 (方向不明)", 0, f"現價進入雲帶({_fmt_money(bot)}~{_fmt_money(top)})之內，多空拉鋸。")
  return ("雲下空頭", -2, f"現價跌破雲帶下緣({_fmt_money(bot)})，一目均衡表轉為空頭格局，雲底成為反壓。")


def _fib_signal(close: float, swing: dict) -> tuple[str, int, str, str]:
  lv = swing["levels"]
  if swing["kind"] == "up":
    name = f"斐波那契回撤 ({_fmt_money(swing['low_price'])} {swing['low_date']} → {_fmt_money(swing['high_price'])} {swing['high_date']})"
    if close >= lv["fib_236"]:
      return (name, "守穩 23.6% (強勢)", 2, f"現價仍在 23.6% 回撤位({_fmt_money(lv['fib_236'])})之上，僅屬強勢整理。")
    if close >= lv["fib_382"]:
      return (name, "守穩 38.2% (健康回檔)", 1, f"現價位於 38.2%({_fmt_money(lv['fib_382'])}) 之上，屬多頭健康回檔區。")
    if close >= lv["fib_500"]:
      return (name, "測試 50% (關鍵中線)", 0, f"現價跌破 38.2%，正測試 50% 回撤位({_fmt_money(lv['fib_500'])})，為多空分水嶺。")
    if close >= lv["fib_618"]:
      return (name, "測試 61.8% (黃金分割最後防線)", -1, f"現價跌破 50%，正測試 61.8% 黃金分割({_fmt_money(lv['fib_618'])})，若失守則整段漲勢恐全數回吐。")
    if close >= lv["fib_786"]:
      return (name, "跌破 61.8% (深度回撤)", -2, f"現價已跌破 61.8%({_fmt_money(lv['fib_618'])})，僅剩 78.6%({_fmt_money(lv['fib_786'])}) 與波段起漲點({_fmt_money(swing['low_price'])})支撐。")
    return (name, "逼近波段起點 (漲勢全數回吐)", -2, f"現價跌破 78.6% 回撤，整段波段漲幅幾乎全數回吐，趨勢反轉。")
  # down-swing: rebound levels are resistance
  name = f"斐波那契反彈 ({_fmt_money(swing['high_price'])} {swing['high_date']} → {_fmt_money(swing['low_price'])} {swing['low_date']})"
  if close <= lv["fib_236"]:
    return (name, "弱勢反彈 (<23.6%)", -2, f"反彈尚未收復 23.6%({_fmt_money(lv['fib_236'])})，空方完全主導。")
  if close <= lv["fib_382"]:
    return (name, "反彈至 23.6%~38.2%", -1, f"反彈收復 23.6% 但受制於 38.2%({_fmt_money(lv['fib_382'])}) 反壓。")
  if close <= lv["fib_500"]:
    return (name, "反彈至 38.2%~50%", 0, f"反彈收復 38.2%，正挑戰 50%({_fmt_money(lv['fib_500'])}) 中線反壓。")
  if close <= lv["fib_618"]:
    return (name, "反彈收復 50% (轉強)", 1, f"反彈收復 50%，若再站上 61.8%({_fmt_money(lv['fib_618'])}) 則有望重返多頭。")
  return (name, "收復 61.8% (V 型反轉)", 2, f"反彈已收復 61.8%({_fmt_money(lv['fib_618'])})，跌勢大概率結束。")


def analyze(rows: list[dict]) -> dict:
  """Full technical analysis on daily OHLCV rows (≥ 260 rows recommended)."""
  closes = [r["close"] for r in rows]
  vols = [float(r["volume"]) for r in rows]
  latest, prev = rows[-1], rows[-2]
  close = latest["close"]

  ema5, ema10, ema20 = ind.ema(closes, 5), ind.ema(closes, 10), ind.ema(closes, 20)
  s20, s50, s100, s200 = ind.sma(closes, 20), ind.sma(closes, 50), ind.sma(closes, 100), ind.sma(closes, 200)
  v20, v50 = ind.sma(vols, 20), ind.sma(vols, 50)
  rsi6, rsi14, rsi24 = ind.rsi(closes, 6), ind.rsi(closes, 14), ind.rsi(closes, 24)
  r14w = rsi14[-14:]
  stoch_rsi = (rsi14[-1] - min(r14w)) / (max(r14w) - min(r14w)) * 100.0 if max(r14w) - min(r14w) > 1e-9 else 50.0
  dif, dea, hist = ind.macd(closes)
  rsv9, k9, d9, j9 = ind.kdj(rows, 9, 3, 3)
  _, k14, d14, _ = ind.kdj(rows, 14, 3, 3)
  pdi, ndi, adx = ind.adx_dmi(rows, 14)
  willr = ind.williams_r(rows, 14)
  cci20 = ind.cci(rows, 20)
  roc12 = ind.pct_change(close, rows[-13]["close"]) if len(rows) >= 13 else 0.0
  st_line, st_dir = ind.supertrend(rows, 10, 3.0)
  sar_line, sar_bull = ind.parabolic_sar(rows)
  atr14 = ind.atr(rows, 14)
  bb = ind.bollinger(closes, 20, 2.0)
  cmf20 = ind.cmf(rows, 20)
  obv = ind.obv(rows)
  obv_s20 = ind.sma(obv, 20)
  mfi14 = ind.mfi(rows, 14)

  # Ichimoku (9, 26, 52)
  def mid(sl: list[dict]) -> float:
    return (max(r["high"] for r in sl) + min(r["low"] for r in sl)) / 2.0

  tenkan, kijun = mid(rows[-9:]), mid(rows[-26:])
  he = len(rows) - 26
  span_a = (mid(rows[he - 9 : he]) + mid(rows[he - 26 : he])) / 2.0
  span_b = mid(rows[he - 52 : he])
  cloud_top, cloud_bot = max(span_a, span_b), min(span_a, span_b)

  # Swing / Fibonacci: tactical (last ~2 months) + major (last ~8 months) swings
  swing = ind.detect_swing(rows, 40)
  major_swing = ind.detect_swing(rows, 160)

  # Pivot points
  pp = (latest["high"] + latest["low"] + latest["close"]) / 3.0
  piv = {
      "p": pp, "r1": 2 * pp - latest["low"], "s1": 2 * pp - latest["high"],
      "r2": pp + (latest["high"] - latest["low"]), "s2": pp - (latest["high"] - latest["low"]),
  }

  # Volume statistics (20D)
  up_v = dn_v = up_d = dn_d = acc_d = dist_d = 0
  for i in range(len(rows) - 20, len(rows)):
    chg = rows[i]["close"] - rows[i - 1]["close"]
    va = v20[i] or statistics.mean(vols[-20:])
    if chg > 0:
      up_v += rows[i]["volume"]; up_d += 1
      acc_d += 1 if rows[i]["volume"] > va else 0
    elif chg < 0:
      dn_v += rows[i]["volume"]; dn_d += 1
      dist_d += 1 if rows[i]["volume"] > va else 0
  ud_ratio = up_v / dn_v if dn_v > 0 else 9.99
  tpv = sum(((r["high"] + r["low"] + r["close"]) / 3.0) * r["volume"] for r in rows[-20:])
  vsum = sum(r["volume"] for r in rows[-20:])
  vwap20 = tpv / vsum if vsum else close

  # Volume profile (126 bars, 24 bins)
  vp_rows = rows[-126:]
  p_min, p_max = min(r["low"] for r in vp_rows), max(r["high"] for r in vp_rows)
  nb = 24
  bs = (p_max - p_min) / nb or 1.0
  bins = [{"price_low": p_min + b * bs, "price_high": p_min + (b + 1) * bs, "price_mid": p_min + (b + 0.5) * bs, "total_volume": 0, "up_volume": 0, "down_volume": 0} for b in range(nb)]
  for i, r in enumerate(vp_rows):
    tp = (r["high"] + r["low"] + r["close"]) / 3.0
    bi = min(int((tp - p_min) / bs), nb - 1)
    up = r["close"] >= (vp_rows[i - 1]["close"] if i else r["open"])
    bins[bi]["total_volume"] += r["volume"]
    bins[bi]["up_volume" if up else "down_volume"] += r["volume"]
  poc_i = max(range(nb), key=lambda b: bins[b]["total_volume"])
  tot = sum(b["total_volume"] for b in bins)
  va_v, lo_i, hi_i = bins[poc_i]["total_volume"], poc_i, poc_i
  while va_v < tot * 0.7 and (lo_i > 0 or hi_i < nb - 1):
    lv = bins[lo_i - 1]["total_volume"] if lo_i > 0 else -1
    hv = bins[hi_i + 1]["total_volume"] if hi_i < nb - 1 else -1
    if hv >= lv:
      hi_i += 1; va_v += bins[hi_i]["total_volume"]
    else:
      lo_i -= 1; va_v += bins[lo_i]["total_volume"]
  for b in bins:
    for k in ("price_low", "price_high", "price_mid"):
      b[k] = round(b[k], 2)

  # Returns & realized vol
  def ret_n(n: int) -> float:
    return ind.pct_change(close, rows[-1 - n]["close"]) if len(rows) > n else 0.0

  rets = [ind.pct_change(closes[i], closes[i - 1]) for i in range(1, len(closes))]
  rv20 = statistics.pstdev(rets[-20:]) * math.sqrt(252) if len(rets) >= 20 else 0.0
  hi52 = max(r["high"] for r in rows[-252:])
  lo52 = min(r["low"] for r in rows[-252:])
  consec_down = 0
  for i in range(len(rows) - 1, 0, -1):
    if rows[i]["close"] < rows[i - 1]["close"]:
      consec_down += 1
    else:
      break

  # ---- Signals ----
  ma_lbl, ma_sc, ma_txt = _ma_structure(close, s20[-1], s50[-1], s200[-1])
  macd_lbl, macd_sc, macd_txt = _macd_signal(dif, dea, hist)
  kd_lbl, kd_sc, kd_txt = _kd_signal(k9, d9, j9)
  rsi_lbl, rsi_sc, rsi_txt = _rsi_signal(rsi6[-1], rsi14[-1], rsi24[-1])
  adx_lbl, adx_sc, adx_txt = _adx_signal(pdi[-1], ndi[-1], adx[-1])
  bb_lbl, bb_sc, bb_txt = _bb_signal(close, bb["mid"][-1], bb["upper"][-1], bb["lower"][-1], bb["pct_b"][-1], bb["width_pct"][-1])
  ich_lbl, ich_sc, ich_txt = _ichimoku_signal(close, tenkan, kijun, cloud_top, cloud_bot)
  fib_name, fib_lbl, fib_sc, fib_txt = _fib_signal(close, swing)
  st_bull = st_dir[-1] == 1
  st_lbl = "多頭防守 (價在線上)" if st_bull else "空頭壓制 (價在線下)"
  st_txt = (f"Supertrend(10,3) 支撐線 {_fmt_money(st_line[-1])}，拋物線 SAR {_fmt_money(sar_line[-1])}。"
            if st_bull else
            f"Supertrend(10,3) 已翻空，壓力線位於 {_fmt_money(st_line[-1])}；SAR {_fmt_money(sar_line[-1])} 位於價格上方，需站回才轉多。")

  tech_table = [
      {"group": "均線系統", "name": "均線結構 (SMA 20/50/200, EMA 5/10)",
       "reading": f"20MA {_fmt_money(s20[-1])} | 50MA {_fmt_money(s50[-1])} | 200MA {_fmt_money(s200[-1])}",
       "signal": ma_lbl, "score": ma_sc, "detail": ma_txt},
      {"group": "趨勢指標", "name": "MACD (12, 26, 9)",
       "reading": f"DIF {dif[-1]:+.2f} | DEA {dea[-1]:+.2f} | Hist {hist[-1]:+.2f}",
       "signal": macd_lbl, "score": macd_sc, "detail": macd_txt},
      {"group": "擺盪指標", "name": "KD / KDJ (9, 3, 3)",
       "reading": f"K={k9[-1]:.1f} | D={d9[-1]:.1f} | J={j9[-1]:.1f} (RSV {rsv9[-1]:.1f})",
       "signal": kd_lbl, "score": kd_sc, "detail": kd_txt},
      {"group": "擺盪指標", "name": "慢速 KD (14, 3, 3)",
       "reading": f"Slow K={k14[-1]:.1f} | Slow D={d14[-1]:.1f}",
       "signal": ("低檔區" if k14[-1] < 20 else ("高檔區" if k14[-1] > 80 else "中軸區")), "score": 0,
       "detail": f"14 日慢速 KD 為 {k14[-1]:.1f}/{d14[-1]:.1f}。"},
      {"group": "動能指標", "name": "多週期 RSI (6/14/24) & StochRSI",
       "reading": f"RSI6={rsi6[-1]:.1f} | RSI14={rsi14[-1]:.1f} | RSI24={rsi24[-1]:.1f} | StochRSI={stoch_rsi:.0f}",
       "signal": rsi_lbl, "score": rsi_sc, "detail": rsi_txt},
      {"group": "趨向指標", "name": "ADX / DMI (14)",
       "reading": f"ADX={adx[-1]:.1f} | +DI={pdi[-1]:.1f} | -DI={ndi[-1]:.1f}",
       "signal": adx_lbl, "score": adx_sc, "detail": adx_txt},
      {"group": "趨勢追蹤", "name": "Supertrend (10, 3) & Parabolic SAR",
       "reading": f"ST {_fmt_money(st_line[-1])} ({'多' if st_bull else '空'}) | SAR {_fmt_money(sar_line[-1])}",
       "signal": st_lbl, "score": 1 if st_bull else -1, "detail": st_txt},
      {"group": "雲圖指標", "name": "一目均衡表 (9, 26, 52)",
       "reading": f"轉換線 {_fmt_money(tenkan)} | 基準線 {_fmt_money(kijun)} | 雲帶 {_fmt_money(cloud_bot)}~{_fmt_money(cloud_top)}",
       "signal": ich_lbl, "score": ich_sc, "detail": ich_txt},
      {"group": "通道指標", "name": "布林通道 (20, 2)",
       "reading": f"上軌 {_fmt_money(bb['upper'][-1])} | 中軌 {_fmt_money(bb['mid'][-1])} | 下軌 {_fmt_money(bb['lower'][-1])} | %B={bb['pct_b'][-1]:.2f}",
       "signal": bb_lbl, "score": bb_sc, "detail": bb_txt},
      {"group": "黃金分割", "name": fib_name,
       "reading": " | ".join(f"{k[4:5]}{k[5:]}%={_fmt_money(v)}" for k, v in swing["levels"].items() if k in ("fib_382", "fib_500", "fib_618")),
       "signal": fib_lbl, "score": fib_sc, "detail": fib_txt},
      {"group": "擺盪指標", "name": "Williams %R (14) / CCI (20) / ROC (12)",
       "reading": f"%R={willr:.1f} | CCI={cci20:+.1f} | ROC12={roc12:+.1f}%",
       "signal": ("極度超賣" if willr < -90 or cci20 < -150 else ("超賣" if willr < -80 or cci20 < -100 else ("超買" if willr > -20 or cci20 > 100 else "中性"))),
       "score": (0 if (willr < -80 or cci20 < -100) else (-1 if roc12 < -10 else (1 if roc12 > 10 else 0))),
       "detail": f"Williams %R={willr:.1f}（<-80 超賣）、CCI(20)={cci20:+.1f}（<-100 超賣）、12 日變動率 {roc12:+.1f}%。"},
  ]

  chart_series = []
  for i in range(max(0, len(rows) - 120), len(rows)):
    r = rows[i]
    chart_series.append({
        "date": r["date"], "open": round(r["open"], 2), "high": round(r["high"], 2), "low": round(r["low"], 2),
        "close": round(r["close"], 2), "volume": r["volume"],
        "sma20": None if s20[i] is None else round(s20[i], 2),
        "sma50": None if s50[i] is None else round(s50[i], 2),
        "sma200": None if s200[i] is None else round(s200[i], 2),
        "vol_sma20": None if v20[i] is None else round(v20[i]),
        "macd": round(dif[i], 3), "macd_signal": round(dea[i], 3), "macd_hist": round(hist[i], 3),
        "k9": round(k9[i], 2), "d9": round(d9[i], 2), "j9": round(j9[i], 2),
        "rsi14": round(rsi14[i], 2),
        "bb_upper": None if bb["upper"][i] is None else round(bb["upper"][i], 2),
        "bb_lower": None if bb["lower"][i] is None else round(bb["lower"][i], 2),
        "supertrend": round(st_line[i], 2), "supertrend_dir": st_dir[i],
    })

  tech_avg = statistics.mean(t["score"] for t in tech_table)
  return {
      "latest_date": latest["date"], "close": round(close, 2), "open": round(latest["open"], 2),
      "high": round(latest["high"], 2), "low": round(latest["low"], 2), "volume": latest["volume"],
      "prev_close": round(prev["close"], 2),
      "ret_1d": round(ind.pct_change(close, prev["close"]), 2), "ret_5d": round(ret_n(5), 2),
      "ret_10d": round(ret_n(10), 2), "ret_20d": round(ret_n(20), 2), "ret_60d": round(ret_n(60), 2),
      "consec_down_days": consec_down,
      "high_52w": round(hi52, 2), "low_52w": round(lo52, 2),
      "drawdown_from_52w_high_pct": round(ind.pct_change(close, hi52), 2),
      "dist_sma20_pct": round(ind.pct_change(close, s20[-1]), 2),
      "dist_sma50_pct": round(ind.pct_change(close, s50[-1]), 2),
      "dist_sma200_pct": round(ind.pct_change(close, s200[-1]), 2),
      "realized_vol_20d_ann_pct": round(rv20, 1),
      "vol_sma20": round(v20[-1]), "rvol20": round(latest["volume"] / v20[-1], 2) if v20[-1] else 1.0,
      "ema5": round(ema5[-1], 2), "ema10": round(ema10[-1], 2), "ema20": round(ema20[-1], 2),
      "sma20": round(s20[-1], 2), "sma50": round(s50[-1], 2), "sma100": round(s100[-1], 2), "sma200": round(s200[-1], 2),
      "vwap20": round(vwap20, 2),
      "rsi6": round(rsi6[-1], 2), "rsi14": round(rsi14[-1], 2), "rsi24": round(rsi24[-1], 2), "stoch_rsi": round(stoch_rsi, 1),
      "k9": round(k9[-1], 2), "d9": round(d9[-1], 2), "j9": round(j9[-1], 2),
      "k14": round(k14[-1], 2), "d14": round(d14[-1], 2),
      "pdi14": round(pdi[-1], 2), "ndi14": round(ndi[-1], 2), "adx14": round(adx[-1], 2),
      "will_r14": round(willr, 2), "cci20": round(cci20, 2), "roc12": round(roc12, 2),
      "macd": round(dif[-1], 3), "macd_signal": round(dea[-1], 3), "macd_hist": round(hist[-1], 3),
      "supertrend": round(st_line[-1], 2), "supertrend_bull": st_bull, "sar": round(sar_line[-1], 2),
      "tenkan9": round(tenkan, 2), "kijun26": round(kijun, 2), "cloud_top": round(cloud_top, 2), "cloud_bot": round(cloud_bot, 2),
      "bb_upper": round(bb["upper"][-1], 2), "bb_mid": round(bb["mid"][-1], 2), "bb_lower": round(bb["lower"][-1], 2),
      "bb_pct_b": round(bb["pct_b"][-1], 3), "bb_width_pct": round(bb["width_pct"][-1], 1),
      "atr14": round(atr14[-1], 2), "atr_pct": round(atr14[-1] / close * 100.0, 2),
      "obv_bullish": obv[-1] > (obv_s20[-1] or obv[-1]), "cmf20": round(cmf20[-1], 3), "mfi14": round(mfi14, 1),
      "up_vol_20": up_v, "down_vol_20": dn_v, "up_down_vol_ratio": round(ud_ratio, 2),
      "up_days_20": up_d, "down_days_20": dn_d, "accum_days_20": acc_d, "dist_days_20": dist_d,
      "poc_price": bins[poc_i]["price_mid"], "vah_price": bins[hi_i]["price_high"], "val_price": bins[lo_i]["price_low"],
      "volume_profile": bins,
      "swing": swing, "major_swing": major_swing, "fib_levels": swing["levels"], "pivot": {k: round(v, 2) for k, v in piv.items()},
      "ma_structure": {"label": ma_lbl, "score": ma_sc},
      "tech_table": tech_table, "tech_avg_score": round(tech_avg, 2),
      "chart_series": chart_series,
  }
