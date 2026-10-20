#!/usr/bin/env python3
"""Generate a streamlined, investor-focused interactive HTML report for SOXL.

Aggregates all core analyses into 4 clean, high-impact sections:
1. Next Step & Trend Playbook (3 Scenarios, Key Price Ladder, Executive Verdict)
2. Aggregated -2 to +2 Scorecard (6 Pillar Cards + Compact 16-Factor Table)
3. Unified Visual Hub (All-in-One Price/Volume/MACD/KD Chart + Options Wall +
16-Stock Heat Map)
4. Macro Correlations (10Y/30Y/Brent Oil/VIX) & Latest Bull/Bear News Digest
"""

import html
import json
from pathlib import Path


def esc(val: object) -> str:
  return html.escape(str(val), quote=True)


def build_unified_technical_svg(vp_data: dict) -> str:
  """Build a single unified SVG combining Candlesticks, MAs, Fib Levels, Volume/VPVR, MACD, and KDJ."""
  series = vp_data["chart_series"]
  vp_bins = vp_data["volume_profile"]
  fib = vp_data["fib_levels"]
  n = len(series)
  if n == 0:
    return ""

  w, h = 1120, 680
  pad_l, pad_r = 62, 165
  plot_w = w - pad_l - pad_r

  # 4 stacked panels inside one unified chart:
  # 1. Price + MA + Fib + VPVR: y = 24..310 (h=286)
  # 2. Volume + 20MA:          y = 326..406 (h=80)
  # 3. MACD (12,26,9):         y = 426..530 (h=104)
  # 4. KD / KDJ (9,3,3):       y = 550..650 (h=100)
  p_top, p_h = 24, 286
  v_top, v_h = 326, 80
  m_top, m_h = 426, 104
  k_top, k_h = 550, 100

  p_min = min(r["low"] for r in series) * 0.96
  p_max = max(r["high"] for r in series) * 1.03
  v_max = max(r["volume"] for r in series) * 1.10

  def x_pos(i: int) -> float:
    return pad_l + (i + 0.5) * (plot_w / n)

  def y_price(p: float) -> float:
    return p_top + p_h - ((p - p_min) / (p_max - p_min)) * p_h

  def y_vol(v: float) -> float:
    return v_top + v_h - (v / v_max) * v_h

  parts = [
      f'<svg viewBox="0 0 {w} {h}" class="chart-svg" role="img"'
      ' aria-label="SOXL 價量與技術指標整合圖">',
      (
          '<rect x="0" y="0" width="100%" height="100%" fill="#0b1120"'
          ' rx="10"/>'
      ),
  ]

  # Price Grid
  for step in range(6):
    pv = p_min + (p_max - p_min) * (step / 5.0)
    yp = y_price(pv)
    parts.append(
        f'<line x1="{pad_l}" y1="{yp:.1f}" x2="{w - pad_r}" y2="{yp:.1f}"'
        ' stroke="#1e293b" stroke-dasharray="3,3"/>'
    )
    parts.append(
        f'<text x="{pad_l - 8}" y="{yp + 4:.1f}" fill="#94a3b8"'
        f' font-size="11" text-anchor="end">${pv:.0f}</text>'
    )

  # Key Fibonacci & Support/Resistance Horizontal Lines
  key_levels = [
      (fib["fib_236"], "#94a3b8", "Fib 23.6% $153.0", "2,4"),
      (fib["fib_382"], "#38bdf8", "Fib 38.2% $142.6 (收盤守穩)", "4,3"),
      (fib["fib_500"], "#10b981", "Fib 50.0% $134.2 (鐵底防守)", "4,3"),
  ]
  for lvl_p, col, lbl, dash in key_levels:
    if p_min <= lvl_p <= p_max:
      yl = y_price(lvl_p)
      parts.append(
          f'<line x1="{pad_l}" y1="{yl:.1f}" x2="{w - pad_r}" y2="{yl:.1f}"'
          f' stroke="{col}" stroke-width="1.2" stroke-dasharray="{dash}"'
          ' opacity="0.8"/>'
      )
      parts.append(
          f'<text x="{pad_l + 6}" y="{yl - 4:.1f}" fill="{col}" font-size="10"'
          f' font-weight="600">{esc(lbl)}</text>'
      )

  # Candlesticks & Volume Bars
  cw = max(2.5, (plot_w / n) * 0.64)
  for i, r in enumerate(series):
    cx = x_pos(i)
    is_up = r["close"] >= r["open"]
    col = "#10b981" if is_up else "#f43f5e"
    yh, yl = y_price(r["high"]), y_price(r["low"])
    yo, yc = y_price(r["open"]), y_price(r["close"])
    bt, bh = min(yo, yc), max(1.5, abs(yc - yo))
    parts.append(
        f'<line x1="{cx:.1f}" y1="{yh:.1f}" x2="{cx:.1f}" y2="{yl:.1f}"'
        f' stroke="{col}" stroke-width="1.1"/>'
    )
    parts.append(
        f'<rect x="{cx - cw/2:.1f}" y="{bt:.1f}" width="{cw:.1f}"'
        f' height="{bh:.1f}" fill="{col}" rx="1"/>'
    )

    yv = y_vol(r["volume"])
    vh = (v_top + v_h) - yv
    parts.append(
        f'<rect x="{cx - cw/2:.1f}" y="{yv:.1f}" width="{cw:.1f}"'
        f' height="{max(1.0, vh):.1f}" fill="{col}" fill-opacity="0.55"/>'
    )

  # Moving Averages (20MA, 50MA, 200MA) & Supertrend
  def poly(key: str, color: str, width: float = 1.8, dash: str = "") -> str:
    pts = [
        f"{x_pos(i):.1f},{y_price(r[key]):.1f}"
        for i, r in enumerate(series)
        if r.get(key) is not None
    ]
    if len(pts) < 2:
      return ""
    d_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline fill="none" stroke="{color}" stroke-width="{width}"'
        f'{d_attr} points="{" ".join(pts)}"/>'
    )

  parts.append(poly("sma20", "#38bdf8", 1.9))
  parts.append(poly("sma50", "#f59e0b", 1.9))
  parts.append(poly("sma200", "#a855f7", 1.9, "5,3"))

  # Volume 20MA
  v_pts = [
      f"{x_pos(i):.1f},{y_vol(r['vol_sma20']):.1f}"
      for i, r in enumerate(series)
      if r.get("vol_sma20")
  ]
  if len(v_pts) >= 2:
    parts.append(
        '<polyline fill="none" stroke="#facc15" stroke-width="1.4"'
        f' points="{" ".join(v_pts)}"/>'
    )

  # Right-side VPVR Volume Profile
  max_b_vol = max(b["total_volume"] for b in vp_bins) if vp_bins else 1
  vp_x0 = w - pad_r + 10
  vp_max_w = pad_r - 22
  poc_p = vp_data["poc_price"]
  for b in vp_bins:
    ym = y_price(b["price_mid"])
    if p_top <= ym <= p_top + p_h:
      bw = (b["total_volume"] / max_b_vol) * vp_max_w
      is_poc = abs(b["price_mid"] - poc_p) < 0.05
      bcol = "#f59e0b" if is_poc else "#3b82f6"
      bop = "0.88" if is_poc else "0.35"
      parts.append(
          f'<rect x="{vp_x0:.1f}" y="{ym - 4:.1f}" width="{max(2.0, bw):.1f}"'
          f' height="7.5" fill="{bcol}" fill-opacity="{bop}" rx="1.5"/>'
      )
  parts.append(
      f'<text x="{vp_x0}" y="{p_top + 12}" fill="#94a3b8" font-size="10"'
      ' font-weight="600">VPVR 籌碼峰 (POC $117)</text>'
  )

  # Panel 3: MACD (12, 26, 9)
  m_vals = (
      [r["macd"] for r in series]
      + [r["macd_signal"] for r in series]
      + [r["macd_hist"] for r in series]
  )
  m_abs = max(abs(min(m_vals)), abs(max(m_vals)), 1.0) * 1.12
  y_m0 = m_top + m_h / 2.0

  def y_macd(val: float) -> float:
    return y_m0 - (val / m_abs) * (m_h / 2.0)

  parts.append(
      f'<line x1="{pad_l}" y1="{m_top}" x2="{w - pad_r}" y2="{m_top}"'
      ' stroke="#334155"/>'
  )
  parts.append(
      f'<line x1="{pad_l}" y1="{y_m0:.1f}" x2="{w - pad_r}" y2="{y_m0:.1f}"'
      ' stroke="#475569" stroke-dasharray="3,3"/>'
  )
  for i, r in enumerate(series):
    cx = x_pos(i)
    hv = r["macd_hist"]
    yh = y_macd(hv)
    bt, bh = min(y_m0, yh), max(1.0, abs(yh - y_m0))
    hcol = "#10b981" if hv >= 0 else "#f43f5e"
    parts.append(
        f'<rect x="{cx - cw/2:.1f}" y="{bt:.1f}" width="{cw:.1f}"'
        f' height="{bh:.1f}" fill="{hcol}" fill-opacity="0.65"/>'
    )
  dif_pts = " ".join(
      f"{x_pos(i):.1f},{y_macd(r['macd']):.1f}" for i, r in enumerate(series)
  )
  dea_pts = " ".join(
      f"{x_pos(i):.1f},{y_macd(r['macd_signal']):.1f}"
      for i, r in enumerate(series)
  )
  parts.append(
      '<polyline fill="none" stroke="#38bdf8" stroke-width="1.7"'
      f' points="{dif_pts}"/>'
  )
  parts.append(
      '<polyline fill="none" stroke="#f59e0b" stroke-width="1.6"'
      f' points="{dea_pts}"/>'
  )

  # Panel 4: KD / KDJ (9, 3, 3)
  def y_kd(val: float) -> float:
    clamped = max(-10.0, min(110.0, val))
    return k_top + k_h - ((clamped + 10.0) / 120.0) * k_h

  parts.append(
      f'<line x1="{pad_l}" y1="{k_top}" x2="{w - pad_r}" y2="{k_top}"'
      ' stroke="#334155"/>'
  )
  for klvl, kcol in [(80, "#f43f5e"), (50, "#475569"), (20, "#10b981")]:
    yk = y_kd(klvl)
    parts.append(
        f'<line x1="{pad_l}" y1="{yk:.1f}" x2="{w - pad_r}" y2="{yk:.1f}"'
        f' stroke="{kcol}" stroke-dasharray="3,3" stroke-opacity="0.6"/>'
    )
    parts.append(
        f'<text x="{pad_l - 6}" y="{yk + 3:.1f}" fill="#64748b" font-size="10"'
        f' text-anchor="end">{klvl}</text>'
    )
  k_pts = " ".join(
      f"{x_pos(i):.1f},{y_kd(r['k9']):.1f}" for i, r in enumerate(series)
  )
  d_pts = " ".join(
      f"{x_pos(i):.1f},{y_kd(r['d9']):.1f}" for i, r in enumerate(series)
  )
  j_pts = " ".join(
      f"{x_pos(i):.1f},{y_kd(r['j9']):.1f}" for i, r in enumerate(series)
  )
  parts.append(
      '<polyline fill="none" stroke="#38bdf8" stroke-width="1.7"'
      f' points="{k_pts}"/>'
  )
  parts.append(
      '<polyline fill="none" stroke="#f59e0b" stroke-width="1.7"'
      f' points="{d_pts}"/>'
  )
  parts.append(
      '<polyline fill="none" stroke="#c084fc" stroke-width="1.2"'
      f' stroke-dasharray="2,2" points="{j_pts}"/>'
  )

  # X-axis dates
  for i in range(0, n, 12):
    cx = x_pos(i)
    parts.append(
        f'<text x="{cx:.1f}" y="{h - 8}" fill="#94a3b8" font-size="10"'
        f' text-anchor="middle">{esc(series[i]["date"][5:])}</text>'
    )
  parts.append(
      f'<text x="{x_pos(n-1):.1f}" y="{h - 8}" fill="#e2e8f0" font-size="10"'
      f' font-weight="600" text-anchor="end">{esc(series[-1]["date"][5:])}</text>'
  )

  # Panel Titles
  parts.append(
      f'<text x="{pad_l + 8}" y="{p_top + 14}" fill="#e2e8f0" font-size="11"'
      ' font-weight="700">SOXL 日K線・20MA($139.5 藍)・50MA($130.2 橘)・200MA($119.9'
      ' 紫)・黃金分割支撐</text>'
  )
  parts.append(
      f'<text x="{pad_l + 8}" y="{v_top + 14}" fill="#cbd5e1" font-size="11"'
      ' font-weight="600">成交量 Volume &amp; 20日均量線 (RVOL 1.62x)</text>'
  )
  parts.append(
      f'<text x="{pad_l + 8}" y="{m_top + 14}" fill="#cbd5e1" font-size="11"'
      f' font-weight="600">MACD (12,26,9)：DIF {vp_data["macd"]:+.2f} (藍) / DEA'
      f' {vp_data["macd_signal"]:+.2f} (橘) / 柱體'
      f' {vp_data["macd_hist"]:+.2f} (零軸上多頭)</text>'
  )
  parts.append(
      f'<text x="{pad_l + 8}" y="{k_top + 14}" fill="#cbd5e1" font-size="11"'
      f' font-weight="600">KD / KDJ (9,3,3)：K={vp_data["k9"]:.1f} (藍) /'
      f' D={vp_data["d9"]:.1f} (橘) / J={vp_data["j9"]:.1f} (紫虛線，逼近20超賣反彈區)</text>'
  )

  parts.append("</svg>")
  return "\n".join(parts)


def build_options_wall_svg(opt_data: dict, spot: float) -> str:
  """Build compact Call vs Put Open Interest Wall SVG around Spot."""
  strikes = opt_data["focus_strikes"]
  if not strikes:
    return ""
  w, h = 540, 260
  pad_l, pad_r, pad_t, pad_b = 46, 16, 26, 36
  pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

  max_oi = max(max(s["call_oi"], s["put_oi"]) for s in strikes) * 1.12 or 1
  n = len(strikes)
  grp_w = pw / n
  bw = max(3.5, grp_w * 0.36)

  parts = [
      f'<svg viewBox="0 0 {w} {h}" class="chart-svg" role="img"'
      ' aria-label="SOXL 期權多空牆">',
      (
          '<rect x="0" y="0" width="100%" height="100%" fill="#0b1120"'
          ' rx="10"/>'
      ),
  ]

  for step in range(4):
    yv = pad_t + ph - (step / 3.0) * ph
    val = (max_oi * step) / 3.0
    parts.append(
        f'<line x1="{pad_l}" y1="{yv:.1f}" x2="{w - pad_r}" y2="{yv:.1f}"'
        ' stroke="#1e293b" stroke-dasharray="3,3"/>'
    )
    parts.append(
        f'<text x="{pad_l - 6}" y="{yv + 4:.1f}" fill="#64748b" font-size="10"'
        f' text-anchor="end">{val/1000:.0f}k</text>'
    )

  for i, s in enumerate(strikes):
    cx = pad_l + (i + 0.5) * grp_w
    ch = (s["call_oi"] / max_oi) * ph
    ph_bar = (s["put_oi"] / max_oi) * ph
    parts.append(
        f'<rect x="{cx - bw - 1:.1f}" y="{pad_t + ph - ch:.1f}"'
        f' width="{bw:.1f}" height="{max(1.0, ch):.1f}" fill="#10b981"'
        ' rx="1.5"/>'
    )
    parts.append(
        f'<rect x="{cx + 1:.1f}" y="{pad_t + ph - ph_bar:.1f}"'
        f' width="{bw:.1f}" height="{max(1.0, ph_bar):.1f}" fill="#f43f5e"'
        ' rx="1.5"/>'
    )
    if i % 2 == 0 or s["strike"] in (100, 140, 145, 150, 170):
      parts.append(
          f'<text x="{cx:.1f}" y="{h - 10}" fill="#94a3b8" font-size="9.5"'
          f' text-anchor="middle">${int(s["strike"])}</text>'
      )

  # Spot Marker
  best_idx = min(
      range(n), key=lambda idx: abs(strikes[idx]["strike"] - spot)
  )
  sx = pad_l + (best_idx + 0.5) * grp_w
  parts.append(
      f'<line x1="{sx:.1f}" y1="{pad_t}" x2="{sx:.1f}" y2="{pad_t + ph}"'
      ' stroke="#38bdf8" stroke-width="1.8" stroke-dasharray="4,3"/>'
  )
  parts.append(
      f'<text x="{sx:.1f}" y="{pad_t - 6}" fill="#38bdf8" font-size="10.5"'
      f' font-weight="700" text-anchor="middle">現價 ${spot:.1f} / MaxPain'
      ' $143</text>'
  )

  parts.append("</svg>")
  return "\n".join(parts)


def generate_html(data: dict) -> str:
  vp = data["volume_price"]
  opt = data["options"]
  hm = data["heatmap"]
  mc = data["macro"]
  news = data["news"]
  sc = data["scoring"]

  spot = vp["close"]

  unified_svg = build_unified_technical_svg(vp)
  opt_svg = build_options_wall_svg(opt, spot)

  # Category Pillar Cards (6 dimensions)
  pillar_cards_html = []
  for c in sc["category_scores"]:
    avg = c["avg_score"]
    cls = "bull" if avg >= 0.3 else ("bear" if avg <= -0.3 else "neutral")
    sign_str = f"{avg:+.2f}"
    pillar_cards_html.append(f"""
      <div class="pillar-card {cls}">
        <div class="pillar-title">{esc(c["category"])}</div>
        <div class="pillar-score">{esc(sign_str)} <span class="pillar-max">/ 2.0</span></div>
        <div class="pillar-weight">權重 {int(c["weight"])}%</div>
      </div>
    """)

  # Compact 16-Factor Table Rows
  factor_rows_html = []
  for f in sc["factors"]:
    s = int(f["score"])
    s_cls = (
        "s-pos2"
        if s == 2
        else (
            "s-pos1"
            if s == 1
            else ("s-zero" if s == 0 else ("s-neg1" if s == -1 else "s-neg2"))
        )
    )
    pct_pos = ((s + 2) / 4.0) * 100.0
    cat_short = f["category"].split("(")[0].strip()
    factor_rows_html.append(f"""
      <tr class="score-row" data-score="{s}">
        <td><span class="cat-tag">{esc(cat_short)}</span></td>
        <td class="fw-600">{esc(f["metric"])}</td>
        <td class="mono">{esc(f["value"])}</td>
        <td class="text-center">
          <span class="score-pill {s_cls}">{s:+d}</span>
          <div class="mini-track"><div class="mini-fill {s_cls}" style="width:{pct_pos:.0f}%"></div></div>
        </td>
        <td class="rationale-cell">{esc(f["rationale"])}</td>
      </tr>
    """)

  # 16 Semiconductor Constituents Heat Map Tiles
  hm_tiles_html = []
  for item in hm["constituents"]:
    r1 = item["ret_1d"]
    r5 = item["ret_5d"]
    r20 = item["ret_20d"]
    bg = (
        "rgba(16,185,129,0.28)"
        if r1 >= 0
        else (
            "rgba(244,63,94,0.22)"
            if r1 > -2.5
            else "rgba(244,63,94,0.42)"
        )
    )
    hm_tiles_html.append(f"""
      <div class="hm-tile" data-r1="{r1}" data-r5="{r5}" data-r20="{r20}" style="background:{bg}">
        <div class="hm-top">
          <span class="hm-ticker">{esc(item["ticker"])}</span>
          <span class="hm-weight">{item["weight"]:.1f}%</span>
        </div>
        <div class="hm-price">${item["close"]:.1f}</div>
        <div class="hm-ret" data-horizon="1d">{r1:+.2f}%</div>
        <div class="hm-sub">20D: {r20:+.1f}%</div>
      </div>
    """)

  # Macro Correlation Summary Rows
  h20 = mc["horizons"]["20D"]
  h60 = mc["horizons"]["60D"]
  h120 = mc["horizons"]["120D"]
  macro_rows_html = []
  macro_meta = [
      (
          "VIX",
          "CBOE VIX 恐慌指數 (^VIX)",
          f"{mc['rolling_series'][-1]['VIX']:.2f} (10/09 15.21)",
          f"Beta {mc['beta_vix_20d']:+.2f}x",
          "🟢 偏多穩定：VIX 維持 15.2~15.4 低檔，確認 10/08 回檔非系統性崩盤",
      ),
      (
          "BRENT",
          "Brent 布蘭特原油 (BZ=F)",
          f"${mc['rolling_series'][-1]['BRENT']:.2f} (+4.07%)",
          f"Beta {mc['beta_brent_20d']:+.2f}x",
          "🔴 短線逆風：與 SOXL 呈 -0.60 強負相關，油價回落 <$100 為轉強訊號",
      ),
      (
          "TNX_10Y",
          "美國 10Y 公債殖利率 (^TNX)",
          f"{mc['rolling_series'][-1]['TNX_10Y']:.3f}%",
          f"{mc['beta_tnx_10bps']:+.2f}% / +10bps",
          "🟡 高檔震盪：與 Brent 原油 60D 正相關 +0.80，壓抑短線估值擴張",
      ),
      (
          "TYX_30Y",
          "美國 30Y 公債殖利率 (^TYX)",
          f"{mc['rolling_series'][-1]['TYX_30Y']:.3f}%",
          f"{mc['beta_tyx_10bps']:+.2f}% / +10bps",
          "🔴 長端警戒：處 24 年高點區 (5.61%)，與 10Y 同步率高達 +0.93",
      ),
      (
          "SPREAD_30_10",
          "30Y - 10Y 美債利差 (Spread)",
          f"+{(mc['rolling_series'][-1]['TYX_30Y'] - mc['rolling_series'][-1]['TNX_10Y'])*100:.1f} bps",
          "正斜率陡峭化",
          "🟢 經濟具韌性：維持 +37.5 bps 正利差，反映非衰退環境",
      ),
  ]
  for key, name, latest_str, beta_str, impact_str in macro_meta:
    c20 = h20[key]["ret_corr"]
    c60 = h60[key]["ret_corr"]
    c120 = h120[key]["ret_corr"]
    c20_cls = "neg-strong" if c20 <= -0.4 else ("neg-mid" if c20 < 0 else "pos-mid")
    macro_rows_html.append(f"""
      <tr>
        <td class="fw-600">{esc(name)}</td>
        <td class="mono">{esc(latest_str)}</td>
        <td class="mono text-center {c20_cls}">{c20:+.2f}</td>
        <td class="mono text-center">{c60:+.2f}</td>
        <td class="mono text-center">{c120:+.2f}</td>
        <td class="mono">{esc(beta_str)}</td>
        <td class="rationale-cell">{esc(impact_str)}</td>
      </tr>
    """)

  # Top 4 Recent Daily News Digest Cards (with collapsible older days)
  timeline = news["daily_feed"]
  recent_days = timeline[:4]
  older_days = timeline[4:]

  def render_day_card(d: dict) -> str:
    net_r = d["net_sentiment_ratio"]
    b_cls = "bull" if net_r >= 0.08 else ("bear" if net_r <= -0.08 else "neutral")
    bias_lbl = f"利多 {d['bull_count']} vs 利空 {d['bear_count']}"
    hl_items = []
    for h_item in d.get("top_bull_headlines", [])[:1]:
      hl_items.append(
          f'<div class="hl-link">🟢 [{esc(h_item["query"])}] {esc(h_item["title"])} ({esc(h_item["publisher"])})</div>'
      )
    for h_item in d.get("top_bear_headlines", [])[:1]:
      hl_items.append(
          f'<div class="hl-link">🔴 [{esc(h_item["query"])}] {esc(h_item["title"])} ({esc(h_item["publisher"])})</div>'
      )
    hl_html = "".join(hl_items)
    return f"""
      <div class="news-day-card {b_cls}">
        <div class="news-day-header">
          <div>
            <span class="news-date">{esc(d["date"])}</span>
            <span class="news-price">{esc(d["soxl_perf"])}</span>
          </div>
          <span class="bias-badge {b_cls}">{esc(bias_lbl)}</span>
        </div>
        <ul class="news-list">
          <li><span class="tag-bull">利多</span> {esc(d["bull_summary_zh"])}</li>
          <li><span class="tag-bear">利空</span> {esc(d["bear_summary_zh"])}</li>
        </ul>
        <div class="hl-wrap">{hl_html}</div>
      </div>
    """

  recent_news_html = "".join(render_day_card(d) for d in recent_days)
  older_news_html = "".join(render_day_card(d) for d in older_days)

  html_doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-soxlQuant2026'; img-src data:; connect-src 'none';">
  <title>SOXL 投資決策精簡儀表板 — 下一步走勢與量化評分</title>
  <style>
    :root {{
      --bg: #070b14;
      --card: #0f172a;
      --card-alt: #131d33;
      --border: #1e293b;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --bull: #10b981;
      --bull-bg: rgba(16, 185, 129, 0.12);
      --bear: #f43f5e;
      --bear-bg: rgba(244, 63, 94, 0.12);
      --warn: #f59e0b;
      --warn-bg: rgba(245, 158, 11, 0.12);
      --accent: #38bdf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Microsoft JhengHei", sans-serif;
      line-height: 1.55;
      padding: 20px 24px 48px;
      max-width: 1400px;
      margin: 0 auto;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* Top Sticky Nav */
    .top-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      background: rgba(15, 23, 42, 0.92);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 18px;
      margin-bottom: 20px;
      position: sticky;
      top: 10px;
      z-index: 50;
      backdrop-filter: blur(10px);
    }}
    .brand-title {{ font-size: 1.2rem; font-weight: 800; letter-spacing: 0.3px; }}
    .brand-sub {{ font-size: 0.8rem; color: var(--muted); }}
    .nav-pills {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .nav-pill {{
      background: #1e293b;
      color: #e2e8f0;
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 600;
      transition: 0.15s;
    }}
    .nav-pill:hover {{ background: var(--accent); color: #070b14; text-decoration: none; }}

    /* Section Containers */
    .section-box {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px;
      margin-bottom: 22px;
    }}
    .sec-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 10px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      margin-bottom: 18px;
    }}
    .sec-title {{ font-size: 1.22rem; font-weight: 800; color: #f8fafc; }}
    .sec-sub {{ font-size: 0.84rem; color: var(--muted); }}

    /* Section 1: Hero Verdict & Next Step Scenarios */
    .verdict-banner {{
      display: grid;
      grid-template-columns: 1.2fr 2fr;
      gap: 18px;
      background: linear-gradient(135deg, rgba(16,185,129,0.14), rgba(56,189,248,0.08));
      border: 1px solid rgba(16,185,129,0.35);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 18px;
    }}
    .verdict-left {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      border-right: 1px solid rgba(148,163,184,0.2);
      padding-right: 16px;
    }}
    .spot-row {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
    .spot-price {{ font-size: 2.1rem; font-weight: 900; }}
    .spot-chg {{ font-size: 0.95rem; font-weight: 700; color: var(--bear); }}
    .pre-tag {{
      display: inline-block;
      margin-top: 4px;
      padding: 3px 9px;
      border-radius: 6px;
      background: rgba(16,185,129,0.2);
      color: #34d399;
      font-size: 0.82rem;
      font-weight: 700;
      width: fit-content;
    }}
    .score-big {{
      margin-top: 12px;
      font-size: 1.35rem;
      font-weight: 800;
      color: #34d399;
    }}
    .verdict-right {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 8px;
      font-size: 0.92rem;
    }}
    .verdict-headline {{ font-size: 1.08rem; font-weight: 800; color: #38bdf8; }}

    /* Key Price Action Ladder */
    .price-ladder {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 8px;
      margin-bottom: 18px;
    }}
    .rung {{
      background: var(--card-alt);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 10px;
      text-align: center;
    }}
    .rung.res {{ border-top: 3px solid var(--bear); }}
    .rung.piv {{ border-top: 3px solid var(--warn); background: rgba(245,158,11,0.09); }}
    .rung.cur {{ border: 2px solid var(--accent); background: rgba(56,189,248,0.12); }}
    .rung.sup {{ border-top: 3px solid var(--bull); }}
    .rung-lbl {{ font-size: 0.74rem; color: var(--muted); font-weight: 600; }}
    .rung-val {{ font-size: 1.05rem; font-weight: 800; margin: 3px 0; font-family: monospace; }}
    .rung-note {{ font-size: 0.72rem; color: #cbd5e1; }}

    /* 3 Scenarios Grid */
    .scenario-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }}
    .scen-card {{
      background: var(--card-alt);
      border-radius: 11px;
      padding: 16px;
      border: 1px solid var(--border);
    }}
    .scen-card.bull {{ border-left: 4px solid var(--bull); }}
    .scen-card.neutral {{ border-left: 4px solid var(--warn); }}
    .scen-card.bear {{ border-left: 4px solid var(--bear); }}
    .scen-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }}
    .scen-title {{ font-weight: 800; font-size: 0.98rem; }}
    .scen-prob {{
      font-size: 0.76rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 99px;
      background: rgba(255,255,255,0.08);
    }}
    .scen-body {{ font-size: 0.85rem; color: #cbd5e1; display: flex; flex-direction: column; gap: 6px; }}
    .scen-action {{
      margin-top: 6px;
      padding: 7px 10px;
      border-radius: 7px;
      background: rgba(15,23,42,0.7);
      font-weight: 600;
      font-size: 0.83rem;
      color: #f8fafc;
    }}

    /* Section 2: 6 Pillar Cards & Compact Table */
    .pillar-grid {{
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }}
    .pillar-card {{
      background: var(--card-alt);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      text-align: center;
    }}
    .pillar-card.bull {{ border-bottom: 3px solid var(--bull); }}
    .pillar-card.neutral {{ border-bottom: 3px solid var(--warn); }}
    .pillar-card.bear {{ border-bottom: 3px solid var(--bear); }}
    .pillar-title {{ font-size: 0.78rem; color: var(--muted); font-weight: 600; margin-bottom: 4px; }}
    .pillar-score {{ font-size: 1.25rem; font-weight: 800; font-family: monospace; }}
    .pillar-max {{ font-size: 0.75rem; color: var(--muted); }}
    .pillar-weight {{ font-size: 0.72rem; color: #64748b; margin-top: 2px; }}

    .filter-bar {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
    .filter-btn {{
      background: #1e293b;
      color: #cbd5e1;
      border: 1px solid #334155;
      border-radius: 7px;
      padding: 5px 12px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
    }}
    .filter-btn.active {{ background: var(--accent); color: #070b14; border-color: var(--accent); }}

    .compact-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }}
    .compact-table th {{
      background: #162032;
      color: #94a3b8;
      text-align: left;
      padding: 9px 10px;
      font-size: 0.78rem;
      border-bottom: 1px solid var(--border);
    }}
    .compact-table td {{
      padding: 9px 10px;
      border-bottom: 1px solid rgba(30,41,59,0.7);
      vertical-align: middle;
    }}
    .compact-table tr:hover {{ background: rgba(56,189,248,0.04); }}
    .cat-tag {{
      font-size: 0.74rem;
      padding: 2px 7px;
      border-radius: 5px;
      background: #1e293b;
      color: #cbd5e1;
      white-space: nowrap;
    }}
    .fw-600 {{ font-weight: 600; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.82rem; }}
    .text-center {{ text-align: center; }}
    .rationale-cell {{ color: #cbd5e1; font-size: 0.82rem; }}

    .score-pill {{
      display: inline-block;
      min-width: 34px;
      padding: 2px 7px;
      border-radius: 6px;
      font-weight: 800;
      font-family: monospace;
      font-size: 0.82rem;
    }}
    .s-pos2 {{ background: rgba(16,185,129,0.25); color: #34d399; }}
    .s-pos1 {{ background: rgba(16,185,129,0.14); color: #6ee7b7; }}
    .s-zero {{ background: rgba(148,163,184,0.18); color: #cbd5e1; }}
    .s-neg1 {{ background: rgba(244,63,94,0.15); color: #fda4af; }}
    .s-neg2 {{ background: rgba(244,63,94,0.28); color: #fb7185; }}
    .mini-track {{
      width: 58px;
      height: 4px;
      background: #1e293b;
      border-radius: 3px;
      margin: 4px auto 0;
      overflow: hidden;
    }}
    .mini-fill {{ height: 100%; }}

    /* Section 3: Unified Visual Hub */
    .chart-svg {{ width: 100%; height: auto; display: block; border-radius: 10px; }}
    .sub-visual-grid {{
      display: grid;
      grid-template-columns: 1fr 1.15fr;
      gap: 16px;
      margin-top: 16px;
    }}
    .sub-box {{
      background: var(--card-alt);
      border: 1px solid var(--border);
      border-radius: 11px;
      padding: 14px;
    }}
    .sub-box-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .sub-box-title {{ font-size: 0.95rem; font-weight: 700; }}
    .kpi-strip {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 10px;
    }}
    .kpi-mini {{
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 7px;
      padding: 7px;
      text-align: center;
    }}
    .kpi-mini-lbl {{ font-size: 0.7rem; color: var(--muted); }}
    .kpi-mini-val {{ font-size: 0.92rem; font-weight: 800; font-family: monospace; margin-top: 2px; }}

    .hm-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 7px;
    }}
    .hm-tile {{
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      padding: 8px;
      transition: transform 0.12s;
    }}
    .hm-tile:hover {{ transform: translateY(-2px); }}
    .hm-top {{ display: flex; justify-content: space-between; font-size: 0.76rem; }}
    .hm-ticker {{ font-weight: 800; }}
    .hm-weight {{ color: var(--muted); font-size: 0.7rem; }}
    .hm-price {{ font-size: 0.8rem; color: #cbd5e1; margin-top: 2px; font-family: monospace; }}
    .hm-ret {{ font-size: 0.98rem; font-weight: 800; font-family: monospace; margin-top: 2px; }}
    .hm-sub {{ font-size: 0.7rem; color: #cbd5e1; opacity: 0.85; }}

    /* Section 4: Macro + News Side-by-Side */
    .macro-news-grid {{
      display: grid;
      grid-template-columns: 1.15fr 1fr;
      gap: 18px;
    }}
    .neg-strong {{ color: #fb7185; font-weight: 800; }}
    .neg-mid {{ color: #fda4af; }}
    .pos-mid {{ color: #34d399; font-weight: 700; }}
    .macro-callout {{
      margin-top: 12px;
      padding: 11px 14px;
      border-radius: 9px;
      background: rgba(56,189,248,0.09);
      border-left: 3px solid var(--accent);
      font-size: 0.83rem;
      color: #e2e8f0;
    }}

    .news-day-card {{
      background: var(--card-alt);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 10px;
    }}
    .news-day-card.bull {{ border-left: 4px solid var(--bull); }}
    .news-day-card.bear {{ border-left: 4px solid var(--bear); }}
    .news-day-card.neutral {{ border-left: 4px solid var(--warn); }}
    .news-day-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }}
    .news-date {{ font-weight: 800; font-family: monospace; font-size: 0.9rem; margin-right: 8px; }}
    .news-price {{ font-size: 0.82rem; color: #cbd5e1; font-family: monospace; }}
    .bias-badge {{
      font-size: 0.72rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 99px;
    }}
    .bias-badge.bull {{ background: var(--bull-bg); color: #34d399; }}
    .bias-badge.bear {{ background: var(--bear-bg); color: #fb7185; }}
    .bias-badge.neutral {{ background: var(--warn-bg); color: #fbbf24; }}
    .news-takeaway {{ font-size: 0.83rem; font-weight: 600; color: #f8fafc; margin-bottom: 6px; }}
    .news-list {{ list-style: none; font-size: 0.8rem; color: #cbd5e1; display: flex; flex-direction: column; gap: 4px; }}
    .tag-bull {{
      display: inline-block;
      padding: 1px 5px;
      border-radius: 4px;
      background: rgba(16,185,129,0.2);
      color: #34d399;
      font-size: 0.7rem;
      font-weight: 700;
      margin-right: 4px;
    }}
    .tag-bear {{
      display: inline-block;
      padding: 1px 5px;
      border-radius: 4px;
      background: rgba(244,63,94,0.2);
      color: #fb7185;
      font-size: 0.7rem;
      font-weight: 700;
      margin-right: 4px;
    }}
    .hl-wrap {{ margin-top: 6px; display: flex; flex-direction: column; gap: 3px; }}
    .hl-link {{ font-size: 0.75rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }}
    .hl-link:hover {{ color: var(--accent); }}
    details.older-news summary {{
      cursor: pointer;
      color: var(--accent);
      font-size: 0.83rem;
      font-weight: 600;
      padding: 6px 0;
    }}

    @media (max-width: 1024px) {{
      .verdict-banner, .scenario-grid, .sub-visual-grid, .macro-news-grid {{ grid-template-columns: 1fr; }}
      .pillar-grid {{ grid-template-columns: repeat(3, 1fr); }}
      .price-ladder {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>

  <!-- Sticky Navigation -->
  <header class="top-bar">
    <div>
      <div class="brand-title">SOXL 投資決策精簡儀表板 (Executive Playbook)</div>
      <div class="brand-sub">整合期權・量能・技術指標 (MACD/KD/Fib)・板塊熱力圖・美債/原油/VIX 連動與每日多空消息</div>
    </div>
    <nav class="nav-pills">
      <a href="#sec-next-step" class="nav-pill">1. 下一步走勢與策略</a>
      <a href="#sec-scorecard" class="nav-pill">2. -2 ~ +2 綜合評分表</a>
      <a href="#sec-visuals" class="nav-pill">3. 核心技術・期權・熱力圖</a>
      <a href="#sec-macro-news" class="nav-pill">4. 宏觀連動 &amp; 每日多空消息</a>
    </nav>
  </header>

  <!-- SECTION 1: NEXT STEP & TREND PLAYBOOK -->
  <section id="sec-next-step" class="section-box">
    <div class="sec-head">
      <h2 class="sec-title">1. 下一步走勢預判與實戰行動指南 (What's the Next Step &amp; Trend?)</h2>
      <span class="sec-sub">即時更新：2026-10-09 盤中現報 $139.36 (-2.22%) ｜ 開盤衝高 $148.18 遇 $150 Call Wall 壓回測試 20MA ($139.51)</span>
    </div>

    <div class="verdict-banner">
      <div class="verdict-left">
        <div class="spot-row">
          <span class="spot-price">$139.36</span>
          <span class="spot-chg">-2.22% (10/09 盤中)</span>
        </div>
        <span class="pre-tag" style="background:rgba(245,158,11,0.2); color:#fbbf24;">⚡ 今開 $148.18 (+3.97%) 撞 $150 期權牆拉回｜低點 $138.40</span>
        <div class="score-big">綜合量化評分：{sc["composite_score"]:+.2f} / +2.00 ({esc(sc["verdict"])})</div>
      </div>
      <div class="verdict-right">
        <div class="verdict-headline">📌 為什麼今天開高 +4% 卻翻黑跌 2.2%？正演繹「劇本 B：$150 Call Wall 壓回洗盤」：</div>
        <p>• <strong>原因 1（$150 Call Wall + 負 Gamma 造市商對沖）：</strong> 盤前受利多帶動開高於 <strong>$148.18</strong>，恰逢 <strong>$150.00 最大 Call Wall (3.25萬口)</strong> 阻力；由於目前處於 <strong>-$18.12M 負 Gamma 區間</strong>，衝關 $150 未果引發造市商順勢拋售對沖，放大日內回檔。</p>
        <p>• <strong>原因 2（NVDA/AVGO 翻紅，但前波飆股與設備股獲利回吐）：</strong> 盤中 <strong>NVDA (+0.15%)、AVGO (+0.66%)</strong> 仍維持紅盤，但前波大漲的 <strong>MRVL (-2.01%)、INTC (-1.40%)、AMD (-1.26%，ARK 減持 $37M)、LRCX (-1.14%)、TXN (-0.97%)</strong> 開高走低，使 SOXX 微跌 -0.67%（3倍槓桿放大為 -2.22%）。</p>
        <p>• <strong>原因 3（開盤後 10Y/30Y 殖利率與油價微幅反彈）：</strong> 開盤後 10Y 殖利率升至 <strong>5.265%</strong>、30Y 升至 <strong>5.629%</strong>，Brent 原油自盤前 $102.4 彈回 <strong>$104.09</strong>；但好消息是 <strong>VIX 恐慌指數逆勢續跌 -2.21% 至 15.07</strong>，且現價 ($139.36) 正精準回測 <strong>20MA 月線 ($139.51) 與 20D VWAP ($137.16)</strong> 支撐帶！</p>
      </div>
    </div>

    <!-- Key Price Ladder -->
    <div class="price-ladder">
      <div class="rung res">
        <div class="rung-lbl">前高 / 次大 Call Wall</div>
        <div class="rung-val">$169.83</div>
        <div class="rung-note">波段停利目標區</div>
      </div>
      <div class="rung res">
        <div class="rung-lbl">短均反壓 / Fib 23.6%</div>
        <div class="rung-val">$153.02</div>
        <div class="rung-note">EMA5 ($153.7) 壓力</div>
      </div>
      <div class="rung piv">
        <div class="rung-lbl">⚡ 最大 Call Wall 樞紐</div>
        <div class="rung-val">$150.00</div>
        <div class="rung-note">今開 $148.18 遇壓拉回</div>
      </div>
      <div class="rung cur">
        <div class="rung-lbl">📍 收盤 / Fib 38.2% / 痛點</div>
        <div class="rung-val">$142.52</div>
        <div class="rung-note">Fib $142.63｜MaxPain $143</div>
      </div>
      <div class="rung sup">
        <div class="rung-lbl">第一支撐 (月線 20MA)</div>
        <div class="rung-val">$139.51</div>
        <div class="rung-note">布林中軌支撐</div>
      </div>
      <div class="rung sup">
        <div class="rung-lbl">機構成本 (20D VWAP)</div>
        <div class="rung-val">$137.16</div>
        <div class="rung-note">10/08 低點 $136.32 止跌</div>
      </div>
      <div class="rung sup">
        <div class="rung-lbl">鐵底防守 (Fib 50% / ST)</div>
        <div class="rung-val">$134.23</div>
        <div class="rung-note">Supertrend $135.4 多空線</div>
      </div>
    </div>

    <!-- 3 Actionable Next-Step Scenarios -->
    <div class="scenario-grid">
      <div class="scen-card bull">
        <div class="scen-head">
          <span class="scen-title" style="color:#34d399;">🟢 劇本 A：突破 $150 轉強上攻</span>
          <span class="scen-prob">機率 45%</span>
        </div>
        <div class="scen-body">
          <div><strong>觸發條件：</strong> 收盤帶量站穩 <strong>$150.00 (Call Wall)</strong> 與 <strong>$153.02 (Fib 23.6%)</strong>，9 日 J 線由 29.5 向上金叉，且布蘭特原油回落至 $102 以下。</div>
          <div><strong>目標價位：</strong> 造市商負 Gamma 轉正助漲，上攻 <strong>$165.00 ~ $169.83 (前高 &amp; $170 Call Wall)</strong>。</div>
          <div class="scen-action">💡 投資人下一步：突破 $150~$153 順勢右側加碼，於 $165~$170 分批獲利了結。</div>
        </div>
      </div>

      <div class="scen-card neutral">
        <div class="scen-head">
          <span class="scen-title" style="color:#fbbf24;">🟡 劇本 B：$136 ~ $150 區間洗盤築底</span>
          <span class="scen-prob">機率 40%</span>
        </div>
        <div class="scen-body">
          <div><strong>觸發條件：</strong> 30Y 殖利率續處 5.6% 高檔，股價受制於 $150 Call Wall，圍繞 <strong>Max Pain $143</strong> 與 <strong>20MA ($139.5)</strong> 震盪消化 KD 死叉。</div>
          <div><strong>核心支撐：</strong> <strong>$136.30 ~ $139.50 (20D VWAP 與月線區)</strong> 具備強勁機構買盤。</div>
          <div class="scen-action">💡 投資人下一步：不追高！趁回測 $137~$142 分批低接，反彈近 $150 減碼做波段價差。</div>
        </div>
      </div>

      <div class="scen-card bear">
        <div class="scen-head">
          <span class="scen-title" style="color:#fb7185;">🔴 劇本 C：跌破 $134 轉弱回測季線</span>
          <span class="scen-prob">機率 15%</span>
        </div>
        <div class="scen-body">
          <div><strong>觸發條件：</strong> 油價飆破 $108 或 VIX 跳升突破 20，導致收盤跌破 <strong>$134.23 (Fib 50% &amp; 一目基準線)</strong> 與 <strong>$135.40 (Supertrend)</strong>。</div>
          <div><strong>下檔風險：</strong> 回測 <strong>$130.25 (50MA 季線)</strong> 與 <strong>$125.82 (Fib 61.8%)</strong>。</div>
          <div class="scen-action">💡 投資人下一步：若收盤實質跌破 $134.00 嚴格停損減倉，退守 $126~$130 季線區再接回。</div>
        </div>
      </div>
    </div>
  </section>

  <!-- SECTION 2: AGGREGATED -2 TO +2 SCORECARD -->
  <section id="sec-scorecard" class="section-box">
    <div class="sec-head">
      <h2 class="sec-title">2. 六大維度匯總與 `-2 ~ +2` 量化評分表 (Aggregated Scorecard)</h2>
      <span class="sec-sub">將 16 項量化指標濃縮為 6 大核心支柱：量能(+1.40)、板塊(+1.00)、消息(+1.00)、技術(+0.87) 領銜多方；期權(-0.48)與高債息/油價(-0.38)為短線阻力</span>
    </div>

    <div class="pillar-grid">
      {"".join(pillar_cards_html)}
    </div>

    <div class="filter-bar">
      <button class="filter-btn active" data-filter="all">全部指標 (16)</button>
      <button class="filter-btn" data-filter="bull">🟢 多方加分 (+1 / +2)</button>
      <button class="filter-btn" data-filter="neutral">⚪ 中性 (0)</button>
      <button class="filter-btn" data-filter="bear">🔴 短線逆風 (-1 / -2)</button>
    </div>

    <div style="overflow-x:auto;">
      <table class="compact-table" id="score-table">
        <thead>
          <tr>
            <th style="width:130px;">維度</th>
            <th style="width:230px;">核心評估指標</th>
            <th style="width:230px;">最新實測讀數</th>
            <th style="width:100px; text-align:center;">評分 (-2~+2)</th>
            <th>對投資人的實戰意義 (Key Takeaway)</th>
          </tr>
        </thead>
        <tbody>
          {"".join(factor_rows_html)}
        </tbody>
      </table>
    </div>
  </section>

  <!-- SECTION 3: UNIFIED VISUAL HUB (TECHNICALS + OPTIONS WALL + HEAT MAP) -->
  <section id="sec-visuals" class="section-box">
    <div class="sec-head">
      <h2 class="sec-title">3. 核心圖表三合一：技術量價 (MACD/KD/Fib)・期權牆・成分股熱力圖</h2>
      <span class="sec-sub">一張主圖整合日K線、均線簇、黃金分割、VPVR 籌碼峰、MACD 與 KDJ；下方並列期權多空牆與 16 檔成分股熱力圖</span>
    </div>

    <!-- Main Unified Price + Volume + MACD + KD SVG -->
    {unified_svg}

    <div class="sub-visual-grid">
      <!-- Left: Options Wall -->
      <div class="sub-box">
        <div class="sub-box-head">
          <span class="sub-box-title">🛡️ CBOE 期權多空牆 (Call Wall $150 vs Put Wall $100)</span>
          <span class="sec-sub">3,488 檔合約</span>
        </div>
        <div class="kpi-strip">
          <div class="kpi-mini">
            <div class="kpi-mini-lbl">C/P 成交量比</div>
            <div class="kpi-mini-val">{opt["cp_vol_ratio"]:.2f}x</div>
          </div>
          <div class="kpi-mini">
            <div class="kpi-mini-lbl">C/P 未平倉比</div>
            <div class="kpi-mini-val">{opt["cp_oi_ratio"]:.2f}x</div>
          </div>
          <div class="kpi-mini">
            <div class="kpi-mini-lbl">最大 Call 壓力牆</div>
            <div class="kpi-mini-val" style="color:#34d399;">${opt["call_wall"]:.0f}</div>
          </div>
          <div class="kpi-mini">
            <div class="kpi-mini-lbl">近期 Max Pain</div>
            <div class="kpi-mini-val" style="color:#38bdf8;">${opt["near_max_pain"]:.0f}</div>
          </div>
        </div>
        {opt_svg}
      </div>

      <!-- Right: 16-Stock Semiconductor Heat Map -->
      <div class="sub-box">
        <div class="sub-box-head">
          <span class="sub-box-title">🔥 SOXL 16 大半導體成分股熱力圖 (81.2% 站上月線)</span>
          <div>
            <button class="filter-btn active hm-btn" data-hm="1d">1D 漲跌</button>
            <button class="filter-btn hm-btn" data-hm="5d">5D 漲跌</button>
            <button class="filter-btn hm-btn" data-hm="20d">20D 波段</button>
          </div>
        </div>
        <div class="hm-grid" id="hm-grid">
          {"".join(hm_tiles_html)}
        </div>
      </div>
    </div>
  </section>

  <!-- SECTION 4: MACRO CORRELATIONS & DAILY BULL/BEAR NEWS -->
  <section id="sec-macro-news" class="section-box">
    <div class="sec-head">
      <h2 class="sec-title">4. 宏觀跨資產連動 (10Y/30Y 美債・原油・VIX) &amp; 每日最新利多利空消息</h2>
      <span class="sec-sub">左表掌握利率、油價、VIX 對 SOXL 的連動影響；右欄追蹤每日最新利多與利空催化劑</span>
    </div>

    <div class="macro-news-grid">
      <!-- Left: Macro Correlation Table & Insight -->
      <div>
        <h3 style="font-size:0.96rem; margin-bottom:10px; color:#e2e8f0;">📊 SOXL vs 10Y/30Y 殖利率・Brent 原油・VIX 相關性與敏感度</h3>
        <div style="overflow-x:auto;">
          <table class="compact-table">
            <thead>
              <tr>
                <th>宏觀指標</th>
                <th>最新報價</th>
                <th class="text-center">20D 相關</th>
                <th class="text-center">60D 相關</th>
                <th class="text-center">120D 相關</th>
                <th>Beta 敏感度</th>
                <th>對 SOXL 走勢意義</th>
              </tr>
            </thead>
            <tbody>
              {"".join(macro_rows_html)}
            </tbody>
          </table>
        </div>
        <div class="macro-callout">
          <strong>💡 跨資產核心傳導鏈 (Investor Insight)：</strong><br>
          1. <strong>10Y (^TNX) 與 30Y (^TYX) 高度同步 (+0.93)</strong>，而推動美債殖利率居高不下的元兇是 <strong>Brent 原油（與 10Y 殖利率 60D 水位相關高達 +0.80）</strong>。<br>
          2. <strong>Brent 原油與 SOXL 近 20 日負相關達 -0.60</strong>：只要油價自 $104 回落至 $100 以下，美債殖利率將同步降溫，為 SOXL 突破 $150 掃清最大宏觀障礙。<br>
          3. <strong>VIX (-0.68 強負相關) 是最佳安全氣囊指標</strong>：目前 VIX 僅 15.2~15.4（遠低於 20 警戒線），代表市場風險偏好穩健，拉回皆屬良性換手。
        </div>
      </div>

      <!-- Right: Latest 5-Day Bull vs Bear News Digest -->
      <div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <h3 style="font-size:0.96rem; color:#e2e8f0;">📰 每日最新利多 vs 利空消息精選 (近7日利多/利空比 1.17x)</h3>
        </div>
        {recent_news_html}
        <details class="older-news">
          <summary>👉 點擊展開更多近期交易日 (09/28 ~ 10/02) 利多利空紀錄</summary>
          <div style="margin-top:8px;">
            {older_news_html}
          </div>
        </details>
      </div>
    </div>
  </section>

  <script nonce="soxlQuant2026">
    // 1. Scorecard Filter
    const filterBtns = document.querySelectorAll('#sec-scorecard .filter-btn');
    const scoreRows = document.querySelectorAll('#score-table tbody .score-row');
    filterBtns.forEach(btn => {{
      btn.addEventListener('click', () => {{
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const mode = btn.getAttribute('data-filter');
        scoreRows.forEach(row => {{
          const s = parseInt(row.getAttribute('data-score'), 10);
          let show = true;
          if (mode === 'bull') show = s > 0;
          else if (mode === 'neutral') show = s === 0;
          else if (mode === 'bear') show = s < 0;
          row.style.display = show ? '' : 'none';
        }});
      }});
    }});

    // 2. Heat Map Horizon Switcher (1D / 5D / 20D)
    const hmBtns = document.querySelectorAll('.hm-btn');
    const hmTiles = document.querySelectorAll('#hm-grid .hm-tile');
    hmBtns.forEach(btn => {{
      btn.addEventListener('click', () => {{
        hmBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const h = btn.getAttribute('data-hm');
        hmTiles.forEach(tile => {{
          const val = parseFloat(tile.getAttribute('data-r' + h.replace('d', '')));
          const retEl = tile.querySelector('.hm-ret');
          const sign = val >= 0 ? '+' : '';
          retEl.textContent = sign + val.toFixed(2) + '%';
          if (val >= 5) tile.style.background = 'rgba(16,185,129,0.42)';
          else if (val >= 0) tile.style.background = 'rgba(16,185,129,0.22)';
          else if (val > -3) tile.style.background = 'rgba(244,63,94,0.22)';
          else tile.style.background = 'rgba(244,63,94,0.42)';
        }});
      }});
    }});
  </script>
</body>
</html>
"""
  return html_doc
