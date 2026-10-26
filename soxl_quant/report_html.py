#!/usr/bin/env python3
"""Investor-friendly HTML dashboard renderer (single self-contained file).

Security: every interpolated value passes through html.escape(); the page ships
a strict Content-Security-Policy with a script nonce; the small amount of JS only
toggles classes / textContent (no innerHTML, no eval, no external resources).
"""

from __future__ import annotations

import html
import math
import re

NONCE = "soxlQuant2026"


def esc(v: object) -> str:
  return html.escape("" if v is None else str(v), quote=True)


def _nwp(v: object) -> str:
  return esc(v)


def num(v, nd: int = 2, prefix: str = "", suffix: str = "", na: str = "n/a", sign: bool = False) -> str:
  if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
    return na
  try:
    s = f"{v:+,.{nd}f}" if sign else f"{v:,.{nd}f}"
  except (TypeError, ValueError):
    return esc(v)
  return f"{prefix}{s}{suffix}"


def pill(score: int) -> str:
  cls = {2: "s-pos2", 1: "s-pos1", 0: "s-zero", -1: "s-neg1", -2: "s-neg2"}.get(int(score), "s-zero")
  return f'<span class="pill {cls}">{int(score):+d}</span>'


def tone_of(v: float, lo: float, hi: float, invert: bool = False) -> str:
  """Return bull/neutral/bear css tone for a value in [lo, hi]."""
  t = (v - lo) / (hi - lo) if hi != lo else 0.5
  t = 1 - t if invert else t
  return "bull" if t >= 0.66 else ("bear" if t <= 0.33 else "neutral")


# --------------------------------------------------------------------------- #
# SVG builders
#
# Layout rules (verified by the headless-Chrome rendering QA):
#   * every text label lives in a reserved strip / gutter — never on top of data
#   * gutter labels are de-collided vertically (leader lines when displaced)
#   * edge labels are clamped inside the viewBox, so nothing gets clipped
#   * wide charts sit in a .chart-scroll wrapper with a min-width, so text never
#     shrinks below ~9 px on narrow screens (the chart scrolls instead)
# --------------------------------------------------------------------------- #
def _tw(s: str, fs: float, bold: bool = False) -> float:
  """Conservative width estimate of a label in SVG user units (bold glyphs run ~10% wider)."""
  w = 0.0
  for ch in str(s):
    o = ord(ch)
    if o >= 0x2E80 or ch in "━┅┆▆▮▼●■":
      w += 1.0
    elif ch in "il.,:;|!'` ":
      w += 0.34
    elif ch.isupper() or ch in "MW%$@#&":
      w += 0.70
    else:
      w += 0.60
  return w * fs * (1.12 if bold else 1.04)


def _spread(items: list[dict], lo: float, hi: float, gap: float) -> list[dict]:
  """Vertical label de-collision. Items carry 'y' (+ optional 'prio', lower = keep first).
  Returns the kept items (sorted by y) with 'ly' set ≥ gap apart inside [lo, hi]."""
  if not items:
    return []
  max_n = max(1, int((hi - lo) // gap) + 1)
  keep = sorted(items, key=lambda d: d.get("prio", 9))[:max_n]
  keep.sort(key=lambda d: d["y"])
  for i, it in enumerate(keep):
    it["ly"] = min(max(it["y"], lo), hi)
    if i and it["ly"] < keep[i - 1]["ly"] + gap:
      it["ly"] = keep[i - 1]["ly"] + gap
  if keep[-1]["ly"] > hi:
    keep[-1]["ly"] = hi
    for i in range(len(keep) - 2, -1, -1):
      keep[i]["ly"] = min(keep[i]["ly"], keep[i + 1]["ly"] - gap)
  return keep


def _place_x(cx: float, tw: float, lo: float, hi: float) -> float:
  """Clamp the centre of a label of width tw so the label stays inside [lo, hi]."""
  return min(max(cx, lo + tw / 2), hi - tw / 2)


def _take_row(rows: list[list[tuple[float, float]]], x0: float, x1: float, pad: float = 6.0) -> int | None:
  """First row whose occupied intervals don't collide with [x0, x1] (then reserve it); None if all full."""
  for ri, occ in enumerate(rows):
    if all(x1 + pad <= a or x0 - pad >= b for a, b in occ):
      occ.append((x0, x1))
      return ri
  return None


def _legend_text(x: float, y: float, parts: list[tuple[str, str, bool]], fs: float = 13) -> str:
  spans = "".join(f'<tspan fill="{c}"{" font-weight=\"800\"" if b else ""}>{esc(t)}</tspan>' for t, c, b in parts)
  return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" font-weight="600">{spans}</text>'


def _date_ticks(n: int, xfun, min_gap: float, want: int = 9) -> list[int]:
  step = max(1, math.ceil(n / want))
  out: list[int] = []
  for i in range(0, n, step):
    if not out or xfun(i) - xfun(out[-1]) >= min_gap:
      out.append(i)
  last = n - 1
  if out and out[-1] != last:  # always label the latest bar
    if xfun(last) - xfun(out[-1]) >= min_gap:
      out.append(last)
    elif len(out) > 1 and xfun(last) - xfun(out[-2]) >= min_gap:
      out[-1] = last
  return out


def gauge_svg(value: float | None, label: str, sub: str, invert: bool = False, vmin: float = 0, vmax: float = 100, display: str | None = None) -> str:
  """Semicircular gauge; the reading sits below the pivot so the needle never crosses it.
  invert=True paints high values red (risk gauges)."""
  if value is None:
    return f'<div class="gauge"><div class="gauge-na">n/a</div><div class="gauge-label">{esc(label)}</div><div class="gauge-sub">{esc(sub)}</div></div>'
  v = max(vmin, min(vmax, float(value)))
  frac = (v - vmin) / (vmax - vmin) if vmax != vmin else 0.5
  cx, cy, r = 100, 96, 76
  colors = ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"]
  if invert:
    colors = colors[::-1]
  segs = []
  for i in range(5):
    a0 = math.pi * (1 - i / 5)
    a1 = math.pi * (1 - (i + 1) / 5)
    x0, y0 = cx + r * math.cos(a0), cy - r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
    segs.append(f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}" stroke="{colors[i]}" stroke-width="16" fill="none" stroke-linecap="butt" opacity="0.85"/>')
  ang = math.pi * (1 - frac)
  nx, ny = cx + (r - 8) * math.cos(ang), cy - (r - 8) * math.sin(ang)
  disp = display if display is not None else f"{value:.0f}"
  return f'''<div class="gauge"><svg viewBox="0 0 200 140" role="img" aria-label="{esc(label)} {esc(disp)}">
    {"".join(segs)}
    <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#f8fafc" stroke-width="3" stroke-linecap="round"/>
    <circle cx="{cx}" cy="{cy}" r="5" fill="#f8fafc"/>
    <text x="{cx}" y="132" text-anchor="middle" fill="#f8fafc" font-size="26" font-weight="800">{esc(disp)}</text>
  </svg><div class="gauge-label">{esc(label)}</div><div class="gauge-sub">{esc(sub)}</div></div>'''


def unified_chart_svg(tech: dict, opt: dict, compact: bool = False) -> str:
  """compact=True renders a 760-wide layout for narrow viewports (switched by CSS media query)."""
  series = tech["chart_series"]
  n = len(series)
  if n == 0:
    return ""
  w, h = (760, 774) if compact else (1160, 774)
  pad_l, pad_r = (54, 136) if compact else (66, 180)
  pw = w - pad_l - pad_r
  x_r = w - pad_r
  p_top, p_h = 42, 294          # title strip baseline 26
  v_top, v_h = 380, 76          # title strip baseline 368
  m_top, m_h = 498, 106         # title strip baseline 486
  k_top, k_h = 646, 94          # title strip baseline 634
  date_y = 762
  lows = [r["low"] for r in series] + [r["bb_lower"] for r in series if r.get("bb_lower")]
  highs = [r["high"] for r in series] + [r["bb_upper"] for r in series if r.get("bb_upper")]
  for key in ("sma20", "sma50", "sma200"):  # keep the MA lines inside the price panel
    vals = [r[key] for r in series if r.get(key) is not None]
    lows += vals
    highs += vals
  p_min, p_max = min(lows) * 0.97, max(highs) * 1.02
  v_max = max(r["volume"] for r in series) * 1.06 or 1

  def x(i): return pad_l + (i + 0.5) * pw / n
  def yp(p): return p_top + p_h - (p - p_min) / (p_max - p_min) * p_h
  def yv(v): return v_top + v_h - v / v_max * v_h

  t = tech
  out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="SOXL 價量與技術指標整合圖"><rect width="100%" height="100%" fill="#0b1120" rx="10"/>']
  # ---- panel title strips (legends) — reserved space above every panel
  out.append(_legend_text(pad_l, 26, [("SOXL 日 K", "#f8fafc", True), (f"　━ 20MA ${t['sma20']:.1f}", "#38bdf8", False), (f"　━ 50MA ${t['sma50']:.1f}", "#f59e0b", False),
                                       (f"　┅ 200MA ${t['sma200']:.1f}", "#c084fc", False), ("　┆ 布林帶", "#7dd3fc", False)] + ([] if compact else [("　右側＝關鍵價位", "#94a3b8", False)]), 12.5 if compact else 13))
  out.append(_legend_text(pad_l, 368, [("成交量", "#f8fafc", True), ("　▮ 綠漲 ▮ 紅跌" if compact else "　▮ 綠＝上漲日　▮ 紅＝下跌日", "#94a3b8", False), ("　━ 20 日均量", "#facc15", False), (f"　RVOL {t['rvol20']:.2f}x" if compact else f"　今日 RVOL {t['rvol20']:.2f}x", "#e2e8f0", False)], 12.5))
  out.append(_legend_text(pad_l, 486, [("MACD (12,26,9)", "#f8fafc", True), (f"　━ DIF {t['macd']:+.2f}", "#38bdf8", False), (f"　━ DEA {t['macd_signal']:+.2f}", "#f59e0b", False), (f"　▮ 柱 {t['macd_hist']:+.2f}", "#94a3b8", False)], 12.5))
  out.append(_legend_text(pad_l, 634, [("KD / KDJ (9,3,3)", "#f8fafc", True), (f"　━ K {t['k9']:.1f}", "#38bdf8", False), (f"　━ D {t['d9']:.1f}", "#f59e0b", False), (f"　┅ J {t['j9']:.1f}", "#c084fc", False)] + ([] if compact else [("　80 超買 / 20 超賣", "#94a3b8", False)]), 12.5))
  # ---- price grid + axis
  for k in range(6):
    pv = p_min + (p_max - p_min) * k / 5
    out.append(f'<line x1="{pad_l}" y1="{yp(pv):.1f}" x2="{x_r}" y2="{yp(pv):.1f}" stroke="#1e293b" stroke-dasharray="3,3" data-bg="1"/>'
               f'<text x="{pad_l - 8}" y="{yp(pv) + 4:.1f}" fill="#94a3b8" font-size="12" text-anchor="end">${pv:.0f}</text>')
  ticks = _date_ticks(n, x, 84)
  for i in ticks:  # faint vertical guides inside each panel
    for top, hh in ((p_top, p_h), (v_top, v_h), (m_top, m_h), (k_top, k_h)):
      out.append(f'<line x1="{x(i):.1f}" y1="{top}" x2="{x(i):.1f}" y2="{top + hh}" stroke="#1e293b" stroke-width="1" data-bg="1"/>')
  # ---- key horizontal levels (lines in the plot, labels in the right gutter)
  levels = []
  sw = tech.get("swing") or {}
  keys = (("fib_236", "Fib 23.6%"), ("fib_382", "Fib 38.2%"), ("fib_500", "Fib 50%")) if sw.get("kind") == "down" else (("fib_382", "Fib 38.2%"), ("fib_500", "Fib 50%"), ("fib_618", "Fib 61.8%"))
  for key, lbl in keys:
    if (sw.get("levels") or {}).get(key) is not None:
      levels.append((sw["levels"][key], "#38bdf8", f"{lbl} ${sw['levels'][key]:.1f}", "4,3", 2))
  if opt.get("put_wall"):
    levels.append((opt["put_wall"], "#f43f5e", f"Put 牆 ${opt['put_wall']:.0f}", "2,3", 1))
  if opt.get("call_wall"):
    levels.append((opt["call_wall"], "#10b981", f"Call 牆 ${opt['call_wall']:.0f}", "2,3", 1))
  if opt.get("gamma_flip"):
    levels.append((opt["gamma_flip"], "#f59e0b", f"Gamma 翻正 ${opt['gamma_flip']:.0f}", "6,3", 1))
  close = series[-1]["close"]
  gutter = [{"y": yp(close), "label": f"現價 ${close:,.2f}", "col": "#f8fafc", "prio": 0, "bold": True, "dash": "1,3"}]
  for price, col, lbl, dash, prio in levels:
    if p_min <= price <= p_max:
      gutter.append({"y": yp(price), "label": lbl, "col": col, "prio": prio, "bold": False, "dash": dash})
  gutter = _spread(gutter, p_top + 7, p_top + p_h - 5, 15.5)
  for g in gutter:
    out.append(f'<line x1="{pad_l}" y1="{g["y"]:.1f}" x2="{x_r}" y2="{g["y"]:.1f}" stroke="{g["col"]}" stroke-width="1.1" stroke-dasharray="{g["dash"]}" opacity="{0.55 if g["bold"] else 0.85}" data-bg="1"/>')
  # ---- Bollinger band fill
  bb_pts_u = [(x(i), yp(r["bb_upper"])) for i, r in enumerate(series) if r.get("bb_upper")]
  bb_pts_l = [(x(i), yp(r["bb_lower"])) for i, r in enumerate(series) if r.get("bb_lower")]
  if len(bb_pts_u) > 2:
    path = " ".join(f"{px:.1f},{py:.1f}" for px, py in bb_pts_u) + " " + " ".join(f"{px:.1f},{py:.1f}" for px, py in reversed(bb_pts_l))
    out.append(f'<polygon points="{path}" fill="#38bdf8" fill-opacity="0.05" stroke="none"/>')
  cw = max(2.5, pw / n * 0.64)
  for i, r in enumerate(series):
    cx = x(i)
    up = r["close"] >= r["open"]
    col = "#10b981" if up else "#f43f5e"
    yo, yc = yp(r["open"]), yp(r["close"])
    out.append(f'<line x1="{cx:.1f}" y1="{yp(r["high"]):.1f}" x2="{cx:.1f}" y2="{yp(r["low"]):.1f}" stroke="{col}" stroke-width="1"/>'
               f'<rect x="{cx - cw / 2:.1f}" y="{min(yo, yc):.1f}" width="{cw:.1f}" height="{max(1.2, abs(yc - yo)):.1f}" fill="{col}" rx="1"/>'
               f'<rect x="{cx - cw / 2:.1f}" y="{yv(r["volume"]):.1f}" width="{cw:.1f}" height="{max(1.0, v_top + v_h - yv(r["volume"])):.1f}" fill="{col}" fill-opacity="0.55"/>')

  def poly(key, color, width=1.8, dash=""):
    pts = [f"{x(i):.1f},{yp(r[key]):.1f}" for i, r in enumerate(series) if r.get(key) is not None]
    return f'<polyline fill="none" stroke="{color}" stroke-width="{width}"{f" stroke-dasharray=\"{dash}\"" if dash else ""} points="{" ".join(pts)}"/>' if len(pts) > 1 else ""

  out += [poly("sma20", "#38bdf8"), poly("sma50", "#f59e0b"), poly("sma200", "#c084fc", 1.8, "5,3"), poly("bb_upper", "#38bdf8", 0.8, "2,3"), poly("bb_lower", "#38bdf8", 0.8, "2,3")]
  vpts = [f"{x(i):.1f},{yv(r['vol_sma20']):.1f}" for i, r in enumerate(series) if r.get("vol_sma20")]
  if len(vpts) > 1:
    out.append(f'<polyline fill="none" stroke="#facc15" stroke-width="1.3" points="{" ".join(vpts)}"/>')
  # ---- MACD panel
  mv = [abs(r["macd"]) for r in series] + [abs(r["macd_signal"]) for r in series] + [abs(r["macd_hist"]) for r in series]
  m_abs = max(mv) * 1.1 or 1
  y0 = m_top + m_h / 2

  def ym(v): return y0 - v / m_abs * (m_h / 2)

  out.append(f'<line x1="{pad_l}" y1="{m_top}" x2="{x_r}" y2="{m_top}" stroke="#334155" data-bg="1"/><line x1="{pad_l}" y1="{y0:.1f}" x2="{x_r}" y2="{y0:.1f}" stroke="#475569" stroke-dasharray="3,3" data-bg="1"/>'
             f'<text x="{pad_l - 8}" y="{y0 + 4:.1f}" fill="#64748b" font-size="11.5" text-anchor="end">0</text>')
  for i, r in enumerate(series):
    hv = r["macd_hist"]
    out.append(f'<rect x="{x(i) - cw / 2:.1f}" y="{min(y0, ym(hv)):.1f}" width="{cw:.1f}" height="{max(1.0, abs(ym(hv) - y0)):.1f}" fill="{"#10b981" if hv >= 0 else "#f43f5e"}" fill-opacity="0.65"/>')
  out.append(f'<polyline fill="none" stroke="#38bdf8" stroke-width="1.6" points="{" ".join(f"{x(i):.1f},{ym(r["macd"]):.1f}" for i, r in enumerate(series))}"/>')
  out.append(f'<polyline fill="none" stroke="#f59e0b" stroke-width="1.5" points="{" ".join(f"{x(i):.1f},{ym(r["macd_signal"]):.1f}" for i, r in enumerate(series))}"/>')
  # ---- KD panel
  def yk(v): return k_top + k_h - (max(-15, min(115, v)) + 15) / 130 * k_h

  out.append(f'<line x1="{pad_l}" y1="{k_top}" x2="{x_r}" y2="{k_top}" stroke="#334155" data-bg="1"/>')
  for lvl, col in ((80, "#f43f5e"), (50, "#475569"), (20, "#10b981")):
    out.append(f'<line x1="{pad_l}" y1="{yk(lvl):.1f}" x2="{x_r}" y2="{yk(lvl):.1f}" stroke="{col}" stroke-dasharray="3,3" stroke-opacity="0.6" data-bg="1"/>'
               f'<text x="{pad_l - 8}" y="{yk(lvl) + 4:.1f}" fill="#64748b" font-size="11.5" text-anchor="end">{lvl}</text>')
  for key, col, wd, dash in (("k9", "#38bdf8", 1.6, ""), ("d9", "#f59e0b", 1.6, ""), ("j9", "#c084fc", 1.1, "2,2")):
    out.append(f'<polyline fill="none" stroke="{col}" stroke-width="{wd}"{f" stroke-dasharray=\"{dash}\"" if dash else ""} points="{" ".join(f"{x(i):.1f},{yk(r[key]):.1f}" for i, r in enumerate(series))}"/>')
  # ---- right-gutter labels (drawn last so they sit above everything)
  for g in gutter:
    fs = min(12.0, (pad_r - 20) / max(1.0, _tw(g["label"], 1.0, bold=True)))
    out.append(f'<line x1="{x_r}" y1="{g["y"]:.1f}" x2="{x_r + 9}" y2="{g["ly"]:.1f}" stroke="{g["col"]}" stroke-width="1" opacity="0.8" data-qa-ok="1"/>'
               f'<text x="{x_r + 13}" y="{g["ly"] + fs * 0.36:.1f}" fill="{g["col"]}" font-size="{fs:.1f}" font-weight="{800 if g["bold"] else 600}">{esc(g["label"])}</text>')
  # ---- date axis
  for i in ticks:
    lbl = series[i]["date"][5:].replace("-", "/")
    out.append(f'<text x="{_place_x(x(i), _tw(lbl, 12), 4, w - 4):.1f}" y="{date_y}" fill="#94a3b8" font-size="12" text-anchor="middle">{esc(lbl)}</text>')
  out.append("</svg>")
  return "".join(out)


def risk_chart_svg(chart: list[dict], episodes_dates: list[str], compact: bool = False) -> str:
  if not chart:
    return ""
  w, h = (760, 346) if compact else (1160, 346)
  pl, pr = (54, 88) if compact else (66, 100)
  pt, ph = 60, 248              # legend baseline 18, marker rows 37 / 52
  pw = w - pl - pr
  n = len(chart)
  closes = [c["close"] for c in chart]
  pmin, pmax = min(closes) * 0.95, max(closes) * 1.03

  def x(i): return pl + (i + 0.5) * pw / n
  def yp(p): return pt + ph - (p - pmin) / (pmax - pmin) * ph
  def ys(s): return pt + ph - max(0.0, min(100.0, s)) / 100 * ph

  out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="崩跌前兆分數 vs SOXL"><rect width="100%" height="100%" fill="#0b1120" rx="10"/>']
  out.append(_legend_text(pl, 20, [("━ SOXL 收盤（左軸）", "#e2e8f0", True), ("　▆ 前兆分數（右軸）" if compact else "　▆ 崩跌前兆分數（右軸，歷史百分位）", "#f97316", False), ("　┆ 之後 5 日內跌 ≥20%" if compact else "　┆ 紅虛線＝之後 5 日內跌 ≥20% 的起點", "#fb7185", False)], 12.5))
  for lvl in (20, 40, 60, 80):
    col = {60: "#eab308", 80: "#ef4444"}.get(lvl, "#1e293b")
    out.append(f'<line x1="{pl}" y1="{ys(lvl):.1f}" x2="{w - pr}" y2="{ys(lvl):.1f}" stroke="{col}" stroke-dasharray="4,3" opacity="{0.75 if lvl in (60, 80) else 1}" data-bg="1"/>')
  for lvl in (0, 20, 40, 60, 80, 100):
    lbl, col, wt = {60: ("60 注意", "#eab308", 700), 80: ("80 警戒", "#ef4444", 700)}.get(lvl, (str(lvl), "#64748b", 500))
    out.append(f'<text x="{w - pr + 8}" y="{ys(lvl) + 4:.1f}" fill="{col}" font-size="11.5" font-weight="{wt}">{lbl}</text>')
  area = " ".join(f"{x(i):.1f},{ys(c['score']):.1f}" for i, c in enumerate(chart))
  out.append(f'<polygon points="{x(0):.1f},{ys(0):.1f} {area} {x(n - 1):.1f},{ys(0):.1f}" fill="#f97316" fill-opacity="0.18"/>')
  out.append(f'<polyline fill="none" stroke="#f97316" stroke-width="1.8" points="{area}"/>')
  out.append(f'<polyline fill="none" stroke="#e2e8f0" stroke-width="1.8" points="{" ".join(f"{x(i):.1f},{yp(c["close"]):.1f}" for i, c in enumerate(chart))}"/>')
  dates = [c["date"] for c in chart]
  rows: list[list[tuple[float, float]]] = [[], []]
  for d in sorted(set(episodes_dates)):
    if d not in dates:
      continue
    xi = x(dates.index(d))
    out.append(f'<line x1="{xi:.1f}" y1="{pt}" x2="{xi:.1f}" y2="{pt + ph}" stroke="#f43f5e" stroke-width="1.2" stroke-dasharray="2,2" opacity="0.85" data-bg="1"/>')
    lbl = f"▼ {d[5:].replace('-', '/')}"
    tw = _tw(lbl, 11.5, bold=True)
    cx = _place_x(xi, tw, pl, w - pr)
    row = _take_row(rows, cx - tw / 2, cx + tw / 2)
    if row is not None:
      out.append(f'<text x="{cx:.1f}" y="{37 + row * 15}" fill="#fb7185" font-size="11.5" font-weight="700" text-anchor="middle">{esc(lbl)}</text>')
  for k in range(5):
    pv = pmin + (pmax - pmin) * k / 4
    out.append(f'<text x="{pl - 8}" y="{yp(pv) + 4:.1f}" fill="#94a3b8" font-size="11.5" text-anchor="end">${pv:.0f}</text>')
  for i in _date_ticks(n, x, 84, 8):
    lbl = dates[i][5:].replace("-", "/")
    out.append(f'<text x="{_place_x(x(i), _tw(lbl, 12), 4, w - 4):.1f}" y="{h - 12}" fill="#94a3b8" font-size="12" text-anchor="middle">{esc(lbl)}</text>')
  out.append("</svg>")
  return "".join(out)


def fg_history_svg(hist: list[dict]) -> str:
  if not hist:
    return ""
  w, h = 560, 178
  pl, pr, pt, pb = 38, 14, 12, 28
  pw, ph = w - pl - pr, h - pt - pb
  n = len(hist)

  def x(i): return pl + i * pw / max(1, n - 1)
  def y(s): return pt + ph - max(0.0, min(100.0, s)) / 100 * ph

  bands = [(0, 25, "#ef4444"), (25, 45, "#f97316"), (45, 55, "#64748b"), (55, 75, "#84cc16"), (75, 100, "#22c55e")]
  out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="CNN Fear and Greed 一年走勢"><rect width="100%" height="100%" fill="#0b1120" rx="8"/>']
  for lo, hi, col in bands:
    out.append(f'<rect x="{pl}" y="{y(hi):.1f}" width="{pw}" height="{y(lo) - y(hi):.1f}" fill="{col}" fill-opacity="0.10" data-bg="1"/>')
  out.append(f'<polyline fill="none" stroke="#38bdf8" stroke-width="1.6" points="{" ".join(f"{x(i):.1f},{y(p["score"]):.1f}" for i, p in enumerate(hist))}"/>')
  last = hist[-1]
  out.append(f'<circle cx="{x(n - 1):.1f}" cy="{y(last["score"]):.1f}" r="4" fill="#f8fafc"/>')
  for lvl in (25, 50, 75):
    out.append(f'<text x="{pl - 7}" y="{y(lvl) + 4:.1f}" fill="#94a3b8" font-size="11" text-anchor="end">{lvl}</text>')
  for i in _date_ticks(n, x, 66, 6):
    lbl = hist[i]["date"][2:7].replace("-", "/")
    out.append(f'<text x="{_place_x(x(i), _tw(lbl, 11), 3, w - 3):.1f}" y="{h - 9}" fill="#94a3b8" font-size="11" text-anchor="middle">{esc(lbl)}</text>')
  out.append("</svg>")
  return "".join(out)


def options_wall_svg(focus: list[dict], spot: float, flip: float | None, mp: float | None) -> str:
  if not focus:
    return ""
  w, h = 560, 280
  pl, pr, pt, pb = 48, 14, 52, 36   # marker-label rows at baselines 20 / 38
  pw, ph = w - pl - pr, h - pt - pb
  n = len(focus)
  gw = pw / n
  bw = max(3.0, gw * 0.36)
  mx = max(max(s["call_oi"], s["put_oi"]) for s in focus) * 1.08 or 1
  out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="期權 Call/Put 未平倉牆"><rect width="100%" height="100%" fill="#0b1120" rx="8"/>']
  for k in range(4):
    yv = pt + ph - k / 3 * ph
    out.append(f'<line x1="{pl}" y1="{yv:.1f}" x2="{w - pr}" y2="{yv:.1f}" stroke="#1e293b" stroke-dasharray="3,3" data-bg="1"/><text x="{pl - 7}" y="{yv + 4:.1f}" fill="#64748b" font-size="11" text-anchor="end">{mx * k / 3 / 1000:.0f}k</text>')
  for i, s in enumerate(focus):
    cx = pl + (i + 0.5) * gw
    ch, phh = s["call_oi"] / mx * ph, s["put_oi"] / mx * ph
    out.append(f'<rect x="{cx - bw - 1:.1f}" y="{pt + ph - ch:.1f}" width="{bw:.1f}" height="{max(1, ch):.1f}" fill="#10b981" rx="1.5"/>'
               f'<rect x="{cx + 1:.1f}" y="{pt + ph - phh:.1f}" width="{bw:.1f}" height="{max(1, phh):.1f}" fill="#f43f5e" rx="1.5"/>')
  stride = max(1, math.ceil(40 / gw))
  for i in range(0, n, stride):
    lbl = f"${focus[i]['strike']:g}"
    out.append(f'<text x="{_place_x(pl + (i + 0.5) * gw, _tw(lbl, 11), 3, w - 3):.1f}" y="{h - 12}" fill="#94a3b8" font-size="11" text-anchor="middle">{esc(lbl)}</text>')

  strikes = [s["strike"] for s in focus]

  def px(price: float) -> float | None:
    """x for a price, interpolated between strike centres; None if outside the plotted strikes."""
    if price is None or price < strikes[0] or price > strikes[-1]:
      return None
    for i in range(n - 1):
      if strikes[i] <= price <= strikes[i + 1]:
        f = 0.0 if strikes[i + 1] == strikes[i] else (price - strikes[i]) / (strikes[i + 1] - strikes[i])
        return pl + (i + 0.5 + f) * gw
    return pl + (n - 0.5) * gw

  rows: list[list[tuple[float, float]]] = [[], []]
  marks = [(spot, "#38bdf8", f"現價 ${spot:.1f}")]
  if flip:
    marks.append((flip, "#f59e0b", f"Gamma 翻正 ${flip:.0f}"))
  if mp is not None:
    marks.append((mp, "#c084fc", f"Max Pain ${mp:g}"))
  seen: list[float] = []
  for price, col, lbl in marks:
    sx = px(price)
    if sx is None or any(abs(sx - o) < 3 for o in seen):
      continue
    seen.append(sx)
    out.append(f'<line x1="{sx:.1f}" y1="{pt}" x2="{sx:.1f}" y2="{pt + ph}" stroke="{col}" stroke-width="1.6" stroke-dasharray="4,3" data-bg="1"/>')
    tw = _tw(lbl, 11.5, bold=True)
    cx = _place_x(sx, tw, 4, w - 4)
    row = _take_row(rows, cx - tw / 2, cx + tw / 2)
    if row is not None:
      out.append(f'<text x="{cx:.1f}" y="{20 + row * 18}" fill="{col}" font-size="11.5" font-weight="700" text-anchor="middle">{esc(lbl)}</text>')
  out.append("</svg>")
  return "".join(out)


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #
GLOSSARY = [
    ("綜合評分 (−2~+2)", "22 項指標各給 −2（很空）到 +2（很多）的分數，依重要性加權平均。≥+0.35 偏多、≤−0.35 偏空。"),
    ("趨勢面 / 逆勢面", "趨勢面＝順著價格方向的指標（均線、MACD、量能、廣度）；逆勢面＝情緒極端的反向指標（恐懼貪婪、超賣）。趨勢空但逆勢多＝『可能反彈但趨勢沒變』。"),
    ("重返多頭檢核表", "8 個『底部確認』條件。成立越多，越適合建立趨勢部位；<3 項只適合小量短線。"),
    ("崩跌前兆分數", "21 個頂部前兆（過熱、動能轉弱、波動結構、宏觀、情緒）加權後換成歷史百分位。≥80 代表症狀比歷史 80% 的日子都重，建議減碼。"),
    ("CNN Fear & Greed", "CNN 的市場情緒指數，0 極度恐懼～100 極度貪婪。極度恐懼常是反彈區，但不等於底部。"),
    ("VIX / VIX3M 期限結構", "VIX 是 S&P 500 未來 30 天的隱含波動；VIX3M 是 3 個月。VIX 比 VIX3M 高（倒掛）＝恐慌高峰；低很多＝市場放鬆。"),
    ("SKEW", "CBOE 尾部風險指數，衡量機構買『極端下跌保險』的需求。>150 表示大戶在避險。"),
    ("Put/Call 比", "賣權(Put)成交量 ÷ 買權(Call)成交量。>1 代表避險/看空多；個股 P/C >0.85 常是散戶恐慌、<0.55 是自滿。"),
    ("淨 Gamma (GEX) / Gamma 翻正位", "造市商因為選擇權部位需要的對沖量。負 Gamma 時造市商『跌時賣、漲時買』，會放大波動；價格站回『翻正位』以上波動才會收斂。"),
    ("Call 牆 / Put 牆 / Max Pain", "未平倉量最大的買權/賣權履約價，常成為反壓/支撐；Max Pain 是到期時讓最多選擇權歸零的價位，到期前價格常被吸過去。"),
    ("IV / 預期波動", "隱含波動率＝市場對未來波動的定價。『月選 ±30%』表示市場認為到月選到期有約 68% 機率落在 ±30% 內。"),
    ("大戶 (Whale) 期權淨方向", "權利金 ≥$25 萬的大單，依買 Call/賣 Put（看多）與買 Put/賣 Call（看空）加總後的方向，−1～+1。"),
    ("RVOL", "今日成交量 ÷ 20 日平均成交量。>1.5 代表放量。"),
    ("斐波那契回撤 / 反彈位", "把一段漲跌幅切成 23.6%、38.2%、50%、61.8%，常見的支撐/反壓參考位。"),
    ("20MA / 50MA / 200MA", "20、50、200 日移動平均線，分別代表月線（短線多空）、季線、年線（長線牛熊分界）。"),
]


def _meter_svg(pos: float, label: str) -> str:
  """TradingView-style 5-zone rating meter. Zone names are HTML so they stay legible at any width."""
  w, h = 640, 44
  pl, pr = 10, 10
  bw = (w - pl - pr) / 5
  cols = ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"]
  names = ["強力賣出", "賣出", "中立", "買進", "強力買進"]
  segs = "".join(f'<rect x="{pl + i * bw:.1f}" y="22" width="{bw - 3:.1f}" height="18" rx="4" fill="{cols[i]}" opacity="0.85"/>' for i in range(5))
  x = pl + (w - pl - pr) * max(0.0, min(100.0, pos)) / 100.0
  active = min(4, int(max(0.0, min(99.999, pos)) // 20))
  name_html = "".join(f'<span class="{"on" if i == active else ""}">{n}</span>' for i, n in enumerate(names))
  return (f'<div class="meter-wrap"><svg viewBox="0 0 {w} {h}" class="meter" role="img" aria-label="評級 {esc(label)}">{segs}'
          f'<polygon points="{x:.1f},20 {x - 9:.1f},6 {x + 9:.1f},6" fill="#f8fafc"/>'
          f'<line x1="{x:.1f}" y1="20" x2="{x:.1f}" y2="42" stroke="#f8fafc" stroke-width="3"/></svg>'
          f'<div class="meter-names">{name_html}</div></div>')


def _ratio_bar(cons: dict) -> str:
  """Buy / hold / sell bar: segment widths follow the weights, but never shrink below their label."""
  segs = []
  for key, cls, name in (("sell_pct", "r-sell", "賣出"), ("hold_pct", "r-hold", "觀望"), ("buy_pct", "r-buy", "買進")):
    v = float(cons.get(key) or 0)
    if v >= 0.5:
      segs.append(f'<div class="{cls}" style="flex-grow:{v:.1f}">{name} {v:.0f}%</div>')
  return f'<div class="ratio">{"".join(segs)}</div>'


def sec_beginner(p: dict) -> str:
  pb, sc, tech = p["playbook"], p["scoring"], p["technicals"]
  b = pb.get("beginner") or {}
  if not b:
    return ""
  cons = b.get("consensus") or {}
  tldr = "".join(f"<li>{esc(t)}</li>" for t in b.get("tldr", []))
  bull = "".join(f'<li><div class="case-h"><b>{esc(x["metric"])}</b><span class="pts up">+{x["pts"]}</span></div><div class="small">{esc(x["value"])}</div><div class="why">{esc(x["why"])}</div></li>' for x in b.get("bull_case", [])) or "<li class='small'>目前沒有明顯的多方因子</li>"
  bear = "".join(f'<li><div class="case-h"><b>{esc(x["metric"])}</b><span class="pts dn">{x["pts"]}</span></div><div class="small">{esc(x["value"])}</div><div class="why">{esc(x["why"])}</div></li>' for x in b.get("bear_case", [])) or "<li class='small'>目前沒有明顯的空方因子</li>"
  plan = b.get("plan") or {}
  watch = "".join(f"<li>{esc(w)}</li>" for w in b.get("watch", []))
  gloss = "".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in GLOSSARY)
  size = int(b.get("size_pct") or 0)
  size_tone = "bull" if size >= 50 else ("neutral" if size >= 25 else "bear")
  return f'''
  <section id="s0" class="box verdict-box {esc(b.get("color", "neutral"))}">
    <div class="sec-head"><h2>0. 新手一頁看懂：現在該買還是該賣？</h2><span class="sub">資料截至 {esc(p["data_as_of"])} 收盤｜一句話 + 評級 + 三問三答，看完這區就夠做決定</span></div>
    <div class="verdict-grid">
      <div class="verdict-card {esc(b.get("color", "neutral"))}">
        <div class="v-emoji">{esc(b.get("emoji", ""))}</div>
        <div class="v-title">{esc(b.get("verdict", ""))}</div>
        <div class="v-sub">{esc(b.get("one_liner", ""))}</div>
        <div class="v-meta">綜合評分 <b>{sc["composite_score"]:+.2f}</b> / ±2　·　信心 <b>{esc(b.get("confidence", ""))}</b>（7 個維度中 {num(b.get("agreement_pct"), 0)}% 同方向）　·　現價 ${tech["close"]:,.2f}（{tech["ret_1d"]:+.2f}%）</div>
      </div>
      <div class="verdict-side">
        <div class="card-h">📊 技術評級（TradingView 風格）</div>
        {_meter_svg(float(b.get("rating_pos") or 50), str(b.get("rating_label")))}
        <div class="small center">{len(sc["factors"])} 項指標：🔴 偏空 {cons.get("n_sell", 0)} 項（其中 −2 有 {cons.get("n_strong_sell", 0)}）· 🟡 中性 {cons.get("n_hold", 0)} 項 · 🟢 偏多 {cons.get("n_buy", 0)} 項（其中 +2 有 {cons.get("n_strong_buy", 0)}）</div>
        <div class="card-h" style="margin-top:12px">⚖️ 買進 / 觀望 / 賣出 權重比（像分析師共識一樣看）</div>
        {_ratio_bar(cons)}
        <div class="small">買進/賣出權重比 {esc(cons.get("buy_sell_ratio") if cons.get("buy_sell_ratio") is not None else "∞")}（>1.5 偏多、<0.67 偏空）</div>
      </div>
    </div>
    <div class="tldr"><div class="card-h">TL;DR（三行看完）</div><ol>{tldr}</ol></div>
    <div class="qa-grid">
      <div class="qa"><div class="qa-q">❓ 我沒有部位，現在能買嗎？</div><div class="qa-a">{esc(b.get("q_no_position", ""))}</div></div>
      <div class="qa"><div class="qa-q">❓ 我已經持有，該怎麼辦？</div><div class="qa-a">{esc(b.get("q_holder", ""))}</div></div>
      <div class="qa"><div class="qa-q">❓ 什麼時候才可以買？</div><div class="qa-a">{esc(b.get("q_when", ""))}</div></div>
    </div>
    <div class="size-row">
      <div class="card-h">🎚️ 建議 SOXL 曝險上限（佔你「原本打算投入 SOXL 的最大金額」的比例）</div>
      <div class="size-bar"><div class="size-fill {size_tone}" style="width:{max(size, 2)}%"></div><span class="size-lbl">{size}%</span></div>
      <div class="small">{esc(b.get("size_note", ""))}。3x 槓桿 ETF 建議永遠不要超過總資產的 10–15%。</div>
    </div>
    <div class="two">
      <div class="card case bull"><div class="card-h">🐂 多方論點（為什麼可能漲）</div><ul class="case-list">{bull}</ul></div>
      <div class="card case bear"><div class="card-h">🐻 空方論點（為什麼可能跌）</div><ul class="case-list">{bear}</ul></div>
    </div>
    <div class="two">
      <div class="card"><div class="card-h">🧭 交易計畫卡（像 DD 文的 Positions / Plan）</div>
        <table class="tbl small nw1"><tbody>
          <tr><td>進場條件</td><td>{esc(plan.get("entry", ""))}</td></tr>
          <tr><td>停損</td><td>{esc(plan.get("stop", ""))}</td></tr>
          <tr><td>目標</td><td>{esc(plan.get("target", ""))}</td></tr>
          <tr><td>報酬 / 風險比</td><td>{esc(plan.get("risk_reward") if plan.get("risk_reward") is not None else "n/a")}（第一目標 vs 停損）</td></tr>
          <tr><td>部位上限</td><td>{esc(plan.get("max_size_pct"))}% 的規劃金額</td></tr></tbody></table></div>
      <div class="card"><div class="card-h">👀 本週觀察清單（哪些數字變了就要重看）</div><ul class="bul">{watch}</ul></div>
    </div>
    <details class="det"><summary>📖 名詞小抄：看不懂的名詞點這裡</summary><dl class="gloss">{gloss}</dl></details>
    <div class="note">新手模式只顯示第 0、1、3 區；點右上角「進階模式」可看完整評分表、情緒 / 期權預測與崩跌復盤。本工具為量化研究，不是投資建議。</div>
  </section>'''


def sec_playbook(p: dict) -> str:
  tech, pb, sc, sen, ews, opt = p["technicals"], p["playbook"], p["scoring"], p["sentiment"], p["early_warning"], p["options"]
  fg = sen.get("fear_greed") or {}
  vx = sen.get("vix") or {}
  pulse = sen.get("pulse") or {}
  w = opt.get("whale") or {}
  chg_cls = "up" if tech["ret_1d"] >= 0 else "dn"
  gauges = [
      gauge_svg(pulse.get("score"), "市場脈搏 Market Pulse", pulse.get("rating_zh", ""), False),
      gauge_svg(fg.get("score"), "CNN Fear & Greed", f"{fg.get('rating_zh', '')}｜一週前 {num(fg.get('week_ago'), 0)}", False),
      gauge_svg(ews.get("today", {}).get("score"), "崩跌前兆分數 (歷史百分位)", str(ews.get("today", {}).get("zone", "")).split("；")[0], True),
      gauge_svg(vx.get("vix"), "VIX 恐慌指數", f"{vx.get('vix_regime', '')}｜VIX/VIX3M {num(vx.get('ratio_vix_3m'), 2)}", True, 10, 45, display=num(vx.get("vix"), 1)),
      gauge_svg(((w.get("whale_net_score") or 0) + 1) * 50 if w.get("whale_net_score") is not None else None, "大戶期權淨方向", f"看多 ${num(w.get('whale_bull_prem_m'), 1)}M vs 看空 ${num(w.get('whale_bear_prem_m'), 1)}M", False, display=num(w.get("whale_net_score"), 2, sign=True)),
  ]
  ladder = "".join(
      f'<div class="rung {esc(l["kind"])}"><div class="rung-val">${l["price"]:,.2f}</div><div class="rung-lbl">{esc(l["label"])}</div><div class="rung-note">{esc(l.get("note", ""))}</div></div>'
      for l in pb["ladder"])
  scen = "".join(f'''<div class="scen {esc(s["tone"])}"><div class="scen-head"><span class="scen-title">{esc(s["title"])}</span><span class="scen-prob">機率 {esc(s["prob"])}%</span></div>
      <div class="scen-row"><b>觸發：</b>{esc(s["trigger"])}</div><div class="scen-row"><b>目標：</b>{esc(s["target"])}</div><div class="scen-act">💡 {esc(s["action"])}</div></div>''' for s in pb["scenarios"])
  checks = "".join(f'<li class="{"ok" if c["ok"] else "no"}"><span class="chk">{"✅" if c["ok"] else "❌"}</span> {esc(c["item"])} <span class="chk-now">{esc(c["now"])}</span></li>' for c in pb["checklist"])
  bullets = "".join(f"<li>{esc(b)}</li>" for b in pb["bullets"])
  return f'''
  <section id="s1" class="box">
    <div class="sec-head"><h2>1. 進一步看：儀表、價位階梯、三劇本與檢核表</h2><span class="sub">資料截至 {esc(p["data_as_of"])} 收盤｜報告產生 {esc(p["generated_at"])}｜看不懂的名詞請用第 0 區的「名詞小抄」</span></div>
    <div class="hero">
      <div class="hero-left">
        <div class="spot">${tech["close"]:,.2f} <span class="chg {chg_cls}">{tech["ret_1d"]:+.2f}%</span></div>
        <div class="spot-sub">5 日 {tech["ret_5d"]:+.1f}%｜20 日 {tech["ret_20d"]:+.1f}%｜距 52 週高點 {tech["drawdown_from_52w_high_pct"]:+.1f}%｜連跌 {tech["consec_down_days"]} 日</div>
        <div class="score-line">綜合評分 <b>{sc["composite_score"]:+.2f}</b> / ±2 → {esc(sc["verdict"])}</div>
        <div class="score-split"><span class="tag bear">趨勢面 {num(sc.get("trend_score"), 2, sign=True)}</span><span class="tag bull">逆勢/情緒面 {num(sc.get("contrarian_score"), 2, sign=True)}</span></div>
        <div class="regime">{esc(sc["regime"])}</div>
      </div>
      <div class="hero-right">
        <div class="headline">📌 {esc(pb["headline"])}</div>
        <ul class="bul">{bullets}</ul>
      </div>
    </div>
    <div class="gauges">{"".join(gauges)}</div>
    <h3 class="h3">關鍵價位階梯 (由上而下：反壓 → 現價 → 支撐)</h3>
    <div class="ladder">{ladder}</div>
    <h3 class="h3">三種劇本與機率 (機率來自歷史同類情境的 10 日分佈：{esc(pb.get("analog_reference") or "全部交易日")})</h3>
    <div class="scen-grid">{scen}</div>
    <h3 class="h3">重返多頭檢核表 — {esc(pb["checklist_passed"])}/{esc(pb["checklist_total"])} 項成立 → {esc(pb["checklist_verdict"])}</h3>
    <ul class="checks">{checks}</ul>
  </section>'''


def sec_scorecard(p: dict) -> str:
  sc = p["scoring"]
  cards = "".join(
      f'<div class="pillar {tone_of(c["avg_score"], -1.2, 1.2)}"><div class="pillar-t">{esc(c["category"])}</div><div class="pillar-v">{c["avg_score"]:+.2f}<span> / 2</span></div><div class="pillar-w">權重 {esc(c["weight"])}</div></div>'
      for c in sc["category_scores"])
  kind_zh = {"trend": "趨勢", "contrarian": "逆勢", "flow": "籌碼"}
  rows = "".join(f'''<tr class="row" data-score="{int(f["score"])}"><td><span class="cat">{esc(f["category"].split("(")[0].strip())}</span><br><span class="kind k-{esc(f["kind"])}">{esc(kind_zh.get(f["kind"], f["kind"]))}</span></td>
      <td class="fw">{_nwp(f["metric"])}</td><td class="mono small">{esc(f["value"])}</td><td class="center">{pill(f["score"])}<div class="crit">{esc(f["criteria"])}</div></td><td class="rat">{esc(f["rationale"])}</td></tr>''' for f in sc["factors"])
  return f'''
  <section id="s2" class="box">
    <div class="sec-head"><h2>2. 七大維度 −2 ~ +2 評分表 (Scorecard)</h2><span class="sub">趨勢面 {num(sc.get("trend_score"), 2, sign=True)}｜逆勢/情緒面 {num(sc.get("contrarian_score"), 2, sign=True)}｜綜合 {sc["composite_score"]:+.2f}</span></div>
    <div class="pillars">{cards}</div>
    <div class="filters"><button class="fbtn active" data-filter="all">全部 ({len(sc["factors"])})</button><button class="fbtn" data-filter="bull">🟢 加分</button><button class="fbtn" data-filter="neutral">⚪ 中性</button><button class="fbtn" data-filter="bear">🔴 扣分</button></div>
    <div class="tbl-wrap"><table class="tbl w-760" id="score-table"><thead><tr><th class="c-grp2">維度/類型</th><th class="c-name">指標</th><th class="c-read">實測</th><th class="center c-score">評分 / 標準</th><th>意義</th></tr></thead><tbody>{rows}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>
  </section>'''


def sec_charts(p: dict) -> str:
  tech, opt, hm, ews = p["technicals"], p["options"], p["heatmap"], p["early_warning"]
  ep_dates = [e["date"] for e in ews.get("event_study", {}).get("episodes", [])]
  tiles = "".join(
      f'''<div class="tile" data-r1="{c["ret_1d"]}" data-r5="{c["ret_5d"]}" data-r20="{c["ret_20d"]}" style="background:{"rgba(16,185,129,.25)" if c["ret_1d"] >= 0 else ("rgba(244,63,94,.22)" if c["ret_1d"] > -2.5 else "rgba(244,63,94,.42)")}">
        <div class="tile-top"><b>{esc(c["ticker"])}</b><span>{c["weight"]:.1f}%</span></div><div class="tile-p">${c["close"]:,.1f}</div><div class="tile-r">{c["ret_1d"]:+.2f}%</div>
        <div class="tile-s"><span>20D {c["ret_20d"]:+.0f}%</span><span>RSI {c["rsi14"]:.0f}</span><span>{"月線上" if c["above_sma20"] else "月線下"}</span></div></div>''' for c in hm["constituents"])
  tech_rows = "".join(f'<tr><td class="nw">{esc(t["group"])}</td><td class="fw">{_nwp(t["name"])}</td><td class="mono small">{esc(t["reading"])}</td><td class="center">{pill(t["score"])}<div class="crit">{esc(t["signal"])}</div></td><td class="rat">{esc(t["detail"])}</td></tr>' for t in tech["tech_table"])
  wh = opt.get("whale", {})
  whale_rows = "".join(f'<tr><td class="mono">{esc(t["expiration"])} ({t["dte"]}d)</td><td class="center"><b class="{"up" if t["type"] == "C" else "dn"}">{esc(t["type"])}</b> ${t["strike"]:g} <span class="small">({t["moneyness_pct"]:+.0f}%)</span></td><td class="mono">{t["volume"]:,}</td><td class="mono">{t["open_interest"]:,} <span class="small">({t["vol_oi"]:.1f}x)</span></td><td class="mono">${t["premium_m"]:.2f}M</td><td class="mono">{f"{t['iv_pct']:.0f}%" if t.get("iv_pct") else "—"}</td><td>{esc(t["bias"])}</td></tr>' for t in wh.get("top_whale_trades", [])[:12])
  return f'''
  <section id="s3" class="box">
    <div class="sec-head"><h2>3. 核心圖表：價量技術・崩跌前兆・期權牆・成分股熱力圖</h2><span class="sub">所有關鍵價位都標在主圖上</span></div>
    <div class="chart-scroll"><div class="only-wide">{unified_chart_svg(tech, opt)}</div><div class="only-narrow">{unified_chart_svg(tech, opt, compact=True)}</div></div>
    <div class="swipe">⇆ 圖表可左右滑動</div>
    <details class="det"><summary>展開 11 項技術指標明細表 (均線 / MACD / KD / RSI / ADX / 一目 / 布林 / 斐波那契 …)</summary>
      <div class="tbl-wrap"><table class="tbl w-760"><thead><tr><th class="c-grp">類別</th><th class="c-name">指標</th><th class="c-read">讀數</th><th class="center c-score">評分 / 訊號</th><th>說明</th></tr></thead><tbody>{tech_rows}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div></details>
    <h3 class="h3">崩跌前兆分數 vs 價格 (近 130 個交易日)</h3>
    <div class="chart-scroll"><div class="only-wide">{risk_chart_svg(ews.get("chart", []), ep_dates)}</div><div class="only-narrow">{risk_chart_svg(ews.get("chart", []), ep_dates, compact=True)}</div></div>
    <div class="swipe">⇆ 圖表可左右滑動</div>
    <div class="two">
      <div class="card">
        <div class="card-h">🛡️ SOXL 期權 Call/Put 未平倉牆 (CBOE, {esc(opt.get("total_contracts"))} 檔)</div>
        <div class="kpis">
          <div class="kpi"><div class="kpi-l">Put/Call 成交</div><div class="kpi-v">{num(opt.get("pc_vol_ratio"), 2)}</div></div>
          <div class="kpi"><div class="kpi-l">淨 Gamma</div><div class="kpi-v {"dn" if (opt.get("total_net_gex_m") or 0) < 0 else "up"}">{num(opt.get("total_net_gex_m"), 1, sign=True)}M</div></div>
          <div class="kpi"><div class="kpi-l">Gamma 翻正位</div><div class="kpi-v">{num(opt.get("gamma_flip"), 0, "$")}</div></div>
          <div class="kpi"><div class="kpi-l">IV30</div><div class="kpi-v">{num(opt.get("iv30_pct"), 0)}%</div></div>
        </div>
        <div class="legend"><i class="lg c"></i>Call 未平倉<i class="lg p"></i>Put 未平倉<span class="lg-note">虛線：現價 / Gamma 翻正 / 近月 Max Pain</span></div>
        <div class="chart-scroll sm">{options_wall_svg(opt.get("focus_strikes", []), opt.get("cboe_spot") or tech["close"], opt.get("gamma_flip"), opt.get("near_max_pain"))}</div>
        <div class="swipe sm">⇆ 圖表可左右滑動</div>
        <div class="note">Put 牆 ${esc(opt.get("put_wall"))} (OI {opt.get("put_wall_oi", 0):,})｜Call 牆 ${esc(opt.get("call_wall"))} (OI {opt.get("call_wall_oi", 0):,})｜近月 Max Pain ${esc(opt.get("near_max_pain"))}｜月選 Max Pain ${esc(opt.get("monthly_max_pain"))} ({esc(opt.get("monthly_expiration"))})</div>
      </div>
      <div class="card">
        <div class="card-h">🔥 16 檔成分股熱力圖 — 站上 20MA {hm["breadth_above_sma20_pct"]:.0f}%｜50MA {hm["breadth_above_sma50_pct"]:.0f}%｜200MA {hm["breadth_above_sma200_pct"]:.0f}%
          <span class="btns"><button class="fbtn active hm" data-h="1">1D</button><button class="fbtn hm" data-h="5">5D</button><button class="fbtn hm" data-h="20">20D</button></span></div>
        <div class="tiles" id="tiles">{tiles}</div>
      </div>
    </div>
    <h3 class="h3">🐋 大戶期權大單 (權利金 ≥$25 萬或 ≥1,500 口、Vol/OI ≥0.4)：{esc(wh.get("whale_count"))} 筆｜大單 Call ${num(wh.get("whale_call_prem_m"), 1)}M vs Put ${num(wh.get("whale_put_prem_m"), 1)}M｜散戶小單 C/P {num(wh.get("retail_cp_ratio"), 2)}</h3>
    <div class="tbl-wrap"><table class="tbl small nwm w-760"><thead><tr><th>到期</th><th class="center">合約</th><th>成交量</th><th>未平倉 (Vol/OI)</th><th>權利金</th><th>IV</th><th>解讀</th></tr></thead><tbody>{whale_rows}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>
  </section>'''


def sec_sentiment(p: dict) -> str:
  sen, opt, mac = p["sentiment"], p["options"], p["macro"]
  fg = sen.get("fear_greed") or {}
  vx = sen.get("vix") or {}
  pc = sen.get("put_call") or {}
  fl = sen.get("flows") or {}
  xa = sen.get("cross_asset") or {}
  fc = opt.get("forecast") or {}
  fg_zh = {"extreme fear": "極度恐懼", "fear": "恐懼", "neutral": "中性", "greed": "貪婪", "extreme greed": "極度貪婪"}
  comp_rows = "".join(f'<tr><td>{_nwp(c["label"])}</td><td class="center"><b>{c["score"]:.0f}</b></td><td class="nw">{esc(fg_zh.get(str(c.get("rating", "")).lower(), c.get("rating")))}</td></tr>' for c in fg.get("components", []))
  pulse_rows = "".join(f'<tr><td>{_nwp(x["label"])}</td><td class="center"><b>{x["score"]:.0f}</b></td><td class="center">{x["weight"] * 100:.0f}%</td><td class="rat">{esc(x["note"])}</td></tr>' for x in (sen.get("pulse") or {}).get("parts", []))
  vix_tbl = f'''<div class="tbl-wrap"><table class="tbl small nw1"><tbody>
    <tr><td>VIX / VIX9D / VIX3M / VIX6M</td><td class="mono">{num(vx.get("vix"), 2)} / {num(vx.get("vix9d"), 2)} / {num(vx.get("vix3m"), 2)} / {num(vx.get("vix6m"), 2)}</td></tr>
    <tr><td>期限結構 VIX/VIX3M</td><td class="mono">{num(vx.get("ratio_vix_3m"), 3)} → {esc(vx.get("term_zh"))}</td></tr>
    <tr><td>VIX 1 年百分位 / 5 日變化 / 近 5 日盤中高</td><td class="mono">{num(vx.get("vix_percentile_1y"), 0)}% / {num(vx.get("vix_5d_chg_pct"), 0, sign=True)}% / {num(vx.get("vix_intraday_high_5d"), 2)}</td></tr>
    <tr><td>VVIX (波動率的波動)</td><td class="mono">{num(vx.get("vvix"), 1)} — {esc(vx.get("vvix_regime"))}</td></tr>
    <tr><td>SKEW (尾部風險定價)</td><td class="mono">{num(vx.get("skew"), 1)} — {esc(vx.get("skew_regime"))}</td></tr>
    <tr><td>VIX1D (當日事件恐慌)</td><td class="mono">{num(vx.get("vix1d"), 2)}</td></tr></tbody></table></div>'''
  pc_tbl = f'''<div class="tbl-wrap"><table class="tbl small"><tbody>
    <tr><td>全市場 Total P/C (單日 / 5 日 / 20 日)</td><td class="mono">{num(pc.get("total_pc"), 2)} / {num(pc.get("total_pc_5d"), 2)} / {num(pc.get("total_pc_20d"), 2)} — {esc(pc.get("total_read"))}</td></tr>
    <tr><td>個股 Equity P/C (單日 / 5 日 / 20 日)</td><td class="mono">{num(pc.get("equity_pc"), 2)} / {num(pc.get("equity_pc_5d"), 2)} / {num(pc.get("equity_pc_20d"), 2)} — {esc(pc.get("equity_read"))}</td></tr>
    <tr><td>指數 / SPX / VIX 選擇權 P/C</td><td class="mono">{num(pc.get("index_pc"), 2)} / {num(pc.get("spx_pc"), 2)} / {num(pc.get("vix_pc"), 2)}</td></tr>
    <tr><td>SOXL / SOXS 成交金額比 (散戶行為)</td><td class="mono">{num((fl.get("latest") or {}).get("ratio"), 2)} (20 日均 {num(fl.get("ratio_avg20"), 2)}) — {esc(fl.get("read"))}</td></tr>
    <tr><td>SOXX 期權 P/C 成交 / 淨 GEX｜SOXS P/C</td><td class="mono">{num((opt.get("secondary", {}).get("SOXX") or {}).get("pc_vol_ratio"), 2)} / {num((opt.get("secondary", {}).get("SOXX") or {}).get("net_gex_m"), 0)}M｜{num((opt.get("secondary", {}).get("SOXS") or {}).get("pc_vol_ratio"), 2)}</td></tr></tbody></table></div>'''
  xa_rows = "".join(f'<tr><td>{_nwp(a["label"])}</td><td class="mono">{num(a.get("last"), 2)}</td><td class="mono">{num(a.get("chg_5d_pct"), 2, sign=True)}%</td><td class="mono">{num(a.get("chg_20d_pct"), 2, sign=True)}%</td><td class="mono">{num(a.get("percentile_1y"), 0)}%</td></tr>' for a in xa.get("assets", []) if a.get("available"))
  em_rows = "".join(f'<tr><td>{esc(lbl)}</td><td class="mono">{esc(e["expiration"])} ({e["dte"]}d)</td><td class="mono">±{e["expected_move_pct"]}%</td><td class="mono">${e["low"]:,.2f} ~ ${e["high"]:,.2f}</td><td class="mono">{num(e.get("atm_iv_pct"), 0)}%</td></tr>'
                    for lbl, e in (("週選 (Weekly)", fc.get("weekly")), ("月選 (Monthly)", fc.get("monthly")), ("季選 (Quarterly)", fc.get("quarterly"))) if e)
  cone_rows = "".join(f'<tr><td>{esc(c["horizon"])}</td><td class="mono">±{c["one_sigma_pct"]}%</td><td class="mono">${c["p16"]:,.2f} ~ ${c["p84"]:,.2f}</td><td class="mono">${c["p2_5"]:,.2f} ~ ${c["p97_5"]:,.2f}</td></tr>' for c in fc.get("iv_cone", []))
  prob_rows = "".join(f'<tr><td class="mono">${r["level"]:g} ({r["vs_spot_pct"]:+.0f}%)</td><td class="mono">{r["prob_above_at_expiry_pct"]:.0f}%</td><td class="mono">{r["prob_below_at_expiry_pct"]:.0f}%</td><td class="mono">{r["prob_touch_pct"]:.0f}%</td></tr>' for r in fc.get("prob_table", []))
  mac_rows = "".join(f'<tr><td class="fw">{_nwp(k["name"])}</td><td class="mono">{esc(k["latest"])}</td><td class="mono">{esc(k["chg_1d"])}</td><td class="mono">{esc(k["chg_20d"])}</td><td class="mono center">{num(k["corr_20d"], 2, sign=True)}</td><td class="mono center">{num(k["corr_60d"], 2, sign=True)}</td><td class="rat">{esc(k["regime"])} {esc(k["beta_note"])}</td></tr>' for k in mac.get("macro_kpis", []))
  return f'''
  <section id="s4" class="box">
    <div class="sec-head"><h2>4. 市場情緒 &amp; 期權預測 (Fear &amp; Greed・VIX 全家族・Put/Call・大戶・預期波動)</h2><span class="sub">逆勢指標：極端恐懼 = 反彈機率升高，不等於底部確認</span></div>
    <div class="two">
      <div class="card"><div class="card-h">CNN Fear &amp; Greed：{num(fg.get("score"), 0)} ({esc(fg.get("rating_zh"))})｜前日 {num(fg.get("previous_close"), 0)}｜一週前 {num(fg.get("week_ago"), 0)}｜一月前 {num(fg.get("month_ago"), 0)}｜一年前 {num(fg.get("year_ago"), 0)}</div>
        <div class="chart-scroll sm">{fg_history_svg(fg.get("history", []))}</div>
        <div class="swipe sm">⇆ 圖表可左右滑動</div>
        <div class="tbl-wrap"><table class="tbl small nw1"><thead><tr><th>七大子指標</th><th class="center">分數</th><th>評級</th></tr></thead><tbody>{comp_rows}</tbody></table></div></div>
      <div class="card"><div class="card-h">市場脈搏 Market Pulse 組成 (0 恐懼 → 100 貪婪)：{num((sen.get("pulse") or {}).get("score"), 0)} {esc((sen.get("pulse") or {}).get("rating_zh"))}</div>
        <div class="tbl-wrap"><table class="tbl small nw1 w-480"><thead><tr><th>指標</th><th class="center">分數</th><th class="center">權重</th><th>讀數</th></tr></thead><tbody>{pulse_rows}</tbody></table></div></div>
    </div>
    <div class="two">
      <div class="card"><div class="card-h">VIX 全家族 (CBOE 官方資料 {esc(vx.get("date"))})</div>{vix_tbl}</div>
      <div class="card"><div class="card-h">Put/Call 與資金流 (CBOE 市場統計 {esc(pc.get("date"))})</div>{pc_tbl}</div>
    </div>
    <div class="two">
      <div class="card"><div class="card-h">📐 期權隱含預期波動 (ATM 跨式) — 市場「定價」的波動範圍</div>
        <div class="tbl-wrap"><table class="tbl small nw1 nwm"><thead><tr><th>到期</th><th>日期</th><th>預期波動</th><th>1σ 區間</th><th>ATM IV</th></tr></thead><tbody>{em_rows or '<tr><td colspan="5">無足夠報價</td></tr>'}</tbody></table></div>
        <div class="note">IV 期限結構：近月 {num(fc.get("iv_near_pct"), 0)}% / 中期 {num(fc.get("iv_mid_pct"), 0)}% / 遠月 {num(fc.get("iv_far_pct"), 0)}% → {esc(fc.get("iv_term_structure"))}；25Δ 偏度 (Put−Call IV) {num(opt.get("iv_skew_25d"), 1, sign=True)}%</div>
        <div class="tbl-wrap"><table class="tbl small nw1 nwm"><thead><tr><th>IV 機率錐</th><th>1σ</th><th>68% 區間</th><th>95% 區間</th></tr></thead><tbody>{cone_rows or '<tr><td colspan="4">n/a</td></tr>'}</tbody></table></div></div>
      <div class="card"><div class="card-h">🎯 月選到期 ({esc((fc.get("monthly") or {}).get("expiration"))}) 價位機率 (由 ATM IV 推算，風險中性)</div>
        <div class="tbl-wrap"><table class="tbl small nw1 nwm"><thead><tr><th>價位</th><th>到期在上方</th><th>到期在下方</th><th>期間觸及</th></tr></thead><tbody>{prob_rows or '<tr><td colspan="4">n/a</td></tr>'}</tbody></table></div>
        <div class="note">機率由選擇權隱含波動率推算 (對數常態)，反映市場定價而非預言；3x ETF 的 IV 本身極高，區間會很寬。</div></div>
    </div>
    <div class="card"><div class="card-h">🌍 宏觀跨資產 (10Y/30Y 美債・原油・VIX・美元・信用) 與 SOXL 相關性</div>
      <div class="tbl-wrap"><table class="tbl small nw1 nwm w-760"><thead><tr><th>指標</th><th>最新</th><th>1 日</th><th>20 日</th><th class="center">20D 相關</th><th class="center">60D 相關</th><th>解讀</th></tr></thead><tbody>{mac_rows or '<tr><td colspan="7">資料暫缺</td></tr>'}</tbody></table></div>
      <div class="tbl-wrap"><table class="tbl small nw1 nwm w-480"><thead><tr><th>跨資產風險溫度計</th><th>最新</th><th>5 日</th><th>20 日</th><th>1 年百分位</th></tr></thead><tbody>{xa_rows or '<tr><td colspan="5">(Yahoo 來源暫時限流，稍後重跑即可補齊)</td></tr>'}</tbody></table></div>
    </div>
  </section>'''


def sec_postmortem(p: dict) -> str:
  pm, ews, nws = p.get("postmortem") or {}, p["early_warning"], p["news"]
  es = ews.get("event_study", {})
  pc = ews.get("peak_checklist", {})
  an = ews.get("analogs", {})
  if not pm:
    return '<section id="s5" class="box"><div class="sec-head"><h2>5. 崩跌復盤與教訓</h2></div><p>近 30 日無重大回檔可供復盤。</p></section>'
  tl_rows = "".join(f'''<tr class="{"hl" if r["chg_pct"] <= -8 else ""}"><td class="mono">{esc(r["date"])}</td><td class="mono">${r["close"]:,.2f}</td><td class="mono {"dn" if r["chg_pct"] < 0 else "up"}">{r["chg_pct"]:+.1f}%</td><td class="mono">{r["volume_m"]:.0f}M ({num(r["rvol"], 1)}x)</td>
      <td class="mono">{num(r["soxx_chg"], 1, sign=True)}%</td><td class="mono">{num(r["spy_chg"], 1, sign=True)}%</td><td class="mono">{num(r["vix"], 1)}</td><td class="mono">{num(r["vix_ratio"], 2)}</td><td class="mono">{num(r["skew"], 0)}</td><td class="mono">{num(r["y10"], 2)}</td><td class="mono">{num(r["fg"], 0)}</td><td class="mono">{num(r["equity_pc"], 2)}</td><td class="mono">{num(r["crash_score"], 0)}</td><td class="small">{esc(r["notes"])}</td></tr>''' for r in pm["timeline"])
  cols = pc.get("columns", [])
  chk_rows = "".join(f'<tr class="{"on" if r["flashed"] else ""}"><td>{esc(r["family"])}</td><td>{esc(r["label"])}</td>' + "".join(f'<td class="center mono">{"—" if v is None else ("🔴" if v >= 0.5 else ("🟡" if v >= 0.25 else "·"))}</td>' for v in r["values"]) + f'<td class="center nw">{"✅ " + esc(r["first_on"]) if r["flashed"] else "✗"}</td></tr>' for r in pc.get("rows", []))
  chk_head = "".join(f'<th class="center">{esc(c[5:])}</th>' for c in cols)
  score_row = "".join(f'<td class="center mono"><b>{s:.0f}</b></td>' for s in pc.get("scores", []))
  lessons = "".join(f'<div class="lesson"><div class="lesson-t">{esc(l["title"])}</div><div class="lesson-d">{esc(l["detail"])}</div><div class="lesson-r">📏 規則：{esc(l["rule"])}</div></div>' for l in pm.get("lessons", []))
  bp = pm.get("big_picture") or {}
  bp_html = (f'<div class="note big">🔭 大格局：{esc(bp["big_high_date"])} 高點 ${bp["big_high"]:,.2f} → {esc(bp["big_low_date"])} 低點 ${bp["big_low"]:,.2f} ({bp["big_decline_pct"]:+.1f}%)；之後反彈到 {esc(bp["rally_high_date"])} ${bp["rally_high"]:,.2f} 只收復 {bp["retrace_pct_of_decline"]}% (38.2% 位於 ${bp["fib_382_of_decline"]:,.2f})'
             + ("，屬『失敗的熊市反彈』。" if bp.get("is_failed_bear_rally") else "。") + "</div>") if bp else ""
  an_rows = "".join(f'''<tr class="{"act" if c.get("active_today") else ""}"><td>{_nwp(c["condition"])}{" <b class=\"nw\">(今日成立)</b>" if c.get("active_today") else ""}{" <span class=\"small nw\">(樣本不足)</span>" if c.get("sufficient") is False else ""}</td><td class="mono center">{esc(c["n_days"])}{f" / {c['n_episodes']}" if c.get("n_episodes") is not None else ""}</td>'''
                    + "".join(f'<td class="mono center">{h["median"]:+.1f}% <span class="small">({h["pct_positive"]:.0f}%↑ / {h.get("pct_down10", 0):.0f}%≤-10)</span></td>' if (h := c["horizons"].get(k)) else '<td class="center">—</td>' for k in ("5d", "10d", "20d", "60d")) + "</tr>" for c in an.get("conditions", []))
  sig_name = {r["key"]: (r["label"].split("：")[0] if "：" in r["label"] else r["label"].split(" (")[0]) for r in pc.get("rows", []) if r.get("key")}
  ep_rows = "".join(f'<tr><td class="mono">{esc(e["date"])}</td><td class="mono">${e["close"]:,.2f}</td><td class="mono dn">{e["fwd_min_pct"]:+.1f}%</td><td class="nw">{esc(str(e["regime"]).split(" (")[0])}</td><td class="mono center">{num(e["score_max_prev5"], 0)}</td><td class="center">{"✅" if e["flagged"] else "✗"}</td><td class="small">{esc("、".join(f"{sig_name.get(k, k)} {float(v):.2f}" for k, v in e["top_signals"]))}</td></tr>' for e in es.get("episodes", [])[::-1])
  st80, st90 = es.get("stats_top_80", {}), es.get("stats_top_90", {})
  bucket_rows = "".join(f'<tr><td class="mono">{esc(b["bucket"])}</td><td class="mono center">{b["days"]}</td><td class="mono center">{b["pct_drop10"]:.1f}%</td><td class="mono center">{b["pct_crash"]:.1f}%</td><td class="mono center">{b["median_fwd_min"]:+.1f}%</td></tr>' for b in es.get("buckets_top", []))
  feed = nws.get("daily_feed", [])

  def day_card(d: dict) -> str:
    bulls = "".join(f'<li>🟢 <span class="tagz">{esc(h["zh_tag"])}</span> {esc(h["title"])} <span class="small nw">({esc(h["publisher"])})</span></li>' for h in d["top_bull_headlines"][:4])
    bears = "".join(f'<li>🔴 <span class="tagz">{esc(h["zh_tag"])}</span> {esc(h["title"])} <span class="small nw">({esc(h["publisher"])})</span></li>' for h in d["top_bear_headlines"][:4])
    tone = "bull" if d["net_sentiment_ratio"] >= 0.15 else ("bear" if d["net_sentiment_ratio"] <= -0.15 else "neutral")
    return f'<div class="news {tone}"><div class="news-h"><b>{esc(d["date"])}</b> SOXL {esc(d["soxl_perf"])}｜VIX {esc(d["vix_perf"])}｜10Y {esc(d["tnx_perf"])} <span class="badge">利多 {d["bull_count"]} vs 利空 {d["bear_count"]}</span></div><ul>{bulls}{bears}</ul></div>'

  news_html = "".join(day_card(d) for d in feed[:4]) + (f'<details class="det"><summary>展開更早的 {len(feed) - 4} 個交易日</summary>{"".join(day_card(d) for d in feed[4:])}</details>' if len(feed) > 4 else "")
  return f'''
  <section id="s5" class="box">
    <div class="sec-head"><h2>5. 崩跌復盤與教訓 (Lessons Learned)：{esc(pm["peak_date"])} ${pm["peak_close"]:,.2f} → {esc(pm["trough_date"])} ${pm["trough_close"]:,.2f} ({pm["soxl_drawdown_pct"]:+.1f}%)</h2>
      <span class="sub">同期 SOXX {num(pm.get("soxx_drawdown_pct"), 1, sign=True)}%｜SPY {num(pm.get("spy_drawdown_pct"), 1, sign=True)}%</span></div>
    {bp_html}
    <h3 class="h3">① 發生了什麼：逐日時間軸 (自高點前 4 日起)</h3>
    <div class="tbl-wrap"><table class="tbl small nwm w-900"><thead><tr><th>日期</th><th>SOXL</th><th>漲跌</th><th>量 (RVOL)</th><th>SOXX</th><th>SPY</th><th>VIX</th><th>VIX/3M</th><th>SKEW</th><th>10Y</th><th>F&amp;G</th><th>Eq P/C</th><th>前兆分</th><th>備註</th></tr></thead><tbody>{tl_rows}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>
    <h3 class="h3">② 哪些跡象事前亮燈？— 高點 {esc(pc.get("peak_date"))} 前後 21 項前兆訊號 ({esc(pc.get("n_flashed"))}/{esc(pc.get("n_total"))} 項曾觸發)</h3>
    <div class="tbl-wrap"><table class="tbl small nw1 w-900"><thead><tr><th>家族</th><th>訊號</th>{chk_head}<th class="center">首次觸發</th></tr></thead><tbody>{chk_rows}<tr class="tot"><td colspan="2"><b>崩跌前兆分數 (歷史百分位)</b></td>{score_row}<td></td></tr></tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>
    <div class="note">圖例：🔴 ≥0.5 觸發　🟡 0.25–0.5 醞釀　· 未觸發　— 無資料。分數以 2021 年以來 (排除最近 60 日) 的歷史分佈換算百分位。</div>
    <h3 class="h3">③ 可以預測嗎？歷史同類情境的後續報酬 (SOXL {esc(an.get("sample_range"))}，中位數 / 上漲機率 / 再跌 ≥10% 機率)</h3>
    <div class="tbl-wrap"><table class="tbl small nwm w-900"><thead><tr><th>情境</th><th class="center">樣本日 / 事件</th><th class="center">5 日後</th><th class="center">10 日後</th><th class="center">20 日後</th><th class="center">60 日後</th></tr></thead><tbody>{an_rows}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>
    <h3 class="h3">④ 前兆分數的實證：過去 {es.get("n_days", 0)} 個交易日中，5 日內跌 ≥20% 的事件共 {esc(es.get("n_episodes"))} 次 (每年約 {esc(es.get("episodes_per_year"))} 次)；其中「頂部型」{esc(es.get("n_top_episodes"))} 次、事前分數 ≥80 者 {esc(es.get("top_episodes_flagged"))} 次</h3>
    <div class="two one">
      <div class="card"><div class="card-h">價在 200MA 之上時，依前兆分數分組的後 5 日表現</div>
        <div class="tbl-wrap"><table class="tbl small w-480"><thead><tr><th>分數區間</th><th class="center">交易日</th><th class="center">5 日內跌 ≥10%</th><th class="center">5 日內跌 ≥20%</th><th class="center">5 日內最大跌幅中位數</th></tr></thead><tbody>{bucket_rows or '<tr><td colspan="5">n/a</td></tr>'}</tbody></table></div>
        <div class="note">逐日統計 (門檻 80)：命中率 {num(st80.get("precision_pct"), 1)}%（基準 {num(st80.get("base_rate_pct"), 1)}%，提升 {num(st80.get("lift"), 2)}x）、召回 {num(st80.get("recall_pct"), 1)}%。
          事件統計：分數 ≥80 的「警報段」共 {esc(es.get("alert_episodes"))} 次，其中 {esc(es.get("alert_episodes_followed_by_crash"))} 次在 15 個交易日內出現 5 日跌 ≥20% (命中 {num(es.get("alert_hit_rate_pct"), 0)}%)；反過來，{esc(es.get("n_top_episodes"))} 次頂部型崩跌中有 {esc(es.get("top_episodes_flagged"))} 次事前 5 日內分數 ≥80。
          權重為人工設定 (非擬合)、樣本有限，請當作風險溫度計：分數高 = 減碼，而不是放空的理由。</div></div>
      <div class="card"><div class="card-h">{esc(es.get("n_episodes"))} 次事件逐筆 (最新在上)<span class="small">類型：頂部型＝起點時價在 200MA 之上；下跌延續型＝已在 200MA 之下</span></div><div class="tbl-wrap tall"><table class="tbl small nwm w-640"><thead><tr><th>起點</th><th>價格</th><th>5 日最大跌幅</th><th>類型</th><th class="center">事前最高分</th><th class="center">≥80</th><th>當時主要訊號</th></tr></thead><tbody>{ep_rows}</tbody></table></div></div>
    </div>
    <h3 class="h3">⑤ 教訓與操作規則</h3>
    <div class="lessons">{lessons}</div>
    <h3 class="h3">⑥ 每日利多 vs 利空新聞 (近 7 日 利多 {esc(nws.get("recent_bull_count"))} / 利空 {esc(nws.get("recent_bear_count"))}，共 {esc(nws.get("total_unique_articles"))} 則)</h3>
    {news_html or '<div class="note">新聞來源暫時無法取得。</div>'}
  </section>'''


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
CSS = """
:root{--bg:#070b14;--card:#0f172a;--card2:#131d33;--bd:#1e293b;--tx:#f1f5f9;--mu:#94a3b8;--bull:#10b981;--bear:#f43f5e;--warn:#f59e0b;--acc:#38bdf8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang TC","Microsoft JhengHei",sans-serif;line-height:1.55;padding:18px 22px 60px;max-width:1420px;margin:0 auto}
a{color:var(--acc)}
.top{position:sticky;top:8px;z-index:50;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;background:rgba(15,23,42,.94);border:1px solid var(--bd);border-radius:12px;padding:10px 16px;margin-bottom:18px;backdrop-filter:blur(8px)}
.brand{font-size:1.15rem;font-weight:800}.brand small{display:block;font-size:.78rem;color:var(--mu);font-weight:500}
.nav a{display:inline-block;background:#1e293b;color:#e2e8f0;padding:5px 11px;border-radius:999px;font-size:.8rem;font-weight:600;text-decoration:none;margin-left:6px}
.nav a:hover{background:var(--acc);color:#070b14}
.box{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:20px;margin-bottom:20px;scroll-margin-top:100px}
.sec-head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;border-bottom:1px solid var(--bd);padding-bottom:10px;margin-bottom:16px}
.sec-head h2{font-size:1.18rem;font-weight:800}.sub{font-size:.82rem;color:var(--mu)}
.h3{font-size:.98rem;font-weight:700;margin:18px 0 10px;color:#e2e8f0}
.hero{display:grid;grid-template-columns:1.05fr 2fr;gap:16px;background:linear-gradient(135deg,rgba(244,63,94,.10),rgba(56,189,248,.08));border:1px solid rgba(148,163,184,.25);border-radius:12px;padding:16px}
.hero-left{border-right:1px solid rgba(148,163,184,.2);padding-right:14px}
.spot{font-size:2.1rem;font-weight:900}.chg{font-size:1rem;font-weight:700;margin-left:6px}.up{color:#34d399}.dn{color:#fb7185}
.spot-sub{font-size:.82rem;color:#cbd5e1;margin:4px 0 8px}
.score-line{font-size:1.05rem;font-weight:700}.score-split{margin:6px 0}.tag{display:inline-block;padding:3px 9px;border-radius:6px;font-size:.8rem;font-weight:700;margin-right:6px}
.tag.bear{background:rgba(244,63,94,.18);color:#fb7185}.tag.bull{background:rgba(16,185,129,.18);color:#34d399}
.regime{margin-top:6px;font-size:.88rem;color:#fbbf24;font-weight:700}
.headline{font-size:1.05rem;font-weight:800;color:var(--acc);margin-bottom:8px}.bul{padding-left:18px;font-size:.88rem;color:#e2e8f0}.bul li{margin:4px 0}
.gauges{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:16px 0}
.gauge{background:var(--card2);border:1px solid var(--bd);border-radius:10px;padding:8px;text-align:center}.gauge svg{width:100%;height:auto}
.gauge-label{font-weight:700;font-size:.86rem}.gauge-sub{font-size:.74rem;color:var(--mu);min-height:1.2em}.gauge-na{font-size:1.6rem;color:var(--mu);padding:30px 0}
.ladder{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px}
.rung{background:var(--card2);border:1px solid var(--bd);border-radius:9px;padding:8px;text-align:center}
.rung.res{border-top:3px solid var(--bear)}.rung.sup{border-top:3px solid var(--bull)}.rung.cur{border:2px solid var(--acc);background:rgba(56,189,248,.12)}
.rung-val{font-family:ui-monospace,Menlo,monospace;font-weight:800;font-size:1rem}.rung-lbl{font-size:.74rem;color:#e2e8f0;font-weight:600}.rung-note{font-size:.68rem;color:var(--mu)}
.scen-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.scen{background:var(--card2);border:1px solid var(--bd);border-radius:10px;padding:14px;font-size:.84rem;color:#cbd5e1}
.scen.bull{border-left:4px solid var(--bull)}.scen.neutral{border-left:4px solid var(--warn)}.scen.bear{border-left:4px solid var(--bear)}
.scen-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px}.scen-title{font-weight:800;color:#f8fafc}.scen-prob{font-size:.78rem;font-weight:800;background:rgba(255,255,255,.1);padding:2px 8px;border-radius:99px;white-space:nowrap}
.scen-row{margin:4px 0}.scen-act{margin-top:8px;padding:7px 9px;border-radius:7px;background:rgba(15,23,42,.75);color:#f8fafc;font-weight:600}
.checks{list-style:none;display:grid;grid-template-columns:repeat(2,1fr);gap:6px}.checks li{background:var(--card2);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;font-size:.84rem}
.checks li.ok{border-left:3px solid var(--bull)}.checks li.no{border-left:3px solid var(--bear)}.chk-now{float:right;color:var(--mu);font-family:ui-monospace,Menlo,monospace;font-size:.78rem}
.pillars{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:12px}
.pillar{background:var(--card2);border:1px solid var(--bd);border-radius:10px;padding:10px;text-align:center}.pillar.bull{border-bottom:3px solid var(--bull)}.pillar.neutral{border-bottom:3px solid var(--warn)}.pillar.bear{border-bottom:3px solid var(--bear)}
.pillar-t{font-size:.74rem;color:var(--mu);font-weight:600;min-height:2.4em}.pillar-v{font-size:1.2rem;font-weight:800;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}.pillar-v span{font-size:.72rem;color:var(--mu)}.pillar-w{font-size:.7rem;color:#64748b}
.filters{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}.fbtn{background:#1e293b;color:#cbd5e1;border:1px solid #334155;border-radius:7px;padding:4px 11px;font-size:.78rem;font-weight:600;cursor:pointer}.fbtn.active{background:var(--acc);color:#070b14;border-color:var(--acc)}
.tbl-wrap{overflow-x:auto}.tbl-wrap.tall{max-height:420px;overflow-y:auto}
.tbl{width:100%;border-collapse:collapse;font-size:.84rem}.tbl.small{font-size:.78rem}
.tbl th{background:#162032;color:var(--mu);text-align:left;padding:7px 8px;font-size:.74rem;border-bottom:1px solid var(--bd);position:sticky;top:0;white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid rgba(30,41,59,.7);vertical-align:top}.tbl tr:hover{background:rgba(56,189,248,.04)}
.tbl tr.hl td{background:rgba(244,63,94,.08)}.tbl tr.on td{background:rgba(245,158,11,.08)}.tbl tr.act td{background:rgba(56,189,248,.08)}.tbl tr.tot td{border-top:2px solid var(--bd)}
.fw{font-weight:600}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem}.small{font-size:.74rem;color:var(--mu)}.center{text-align:center}.rat{color:#cbd5e1;font-size:.8rem}
.cat{font-size:.72rem;padding:2px 6px;border-radius:5px;background:#1e293b;color:#cbd5e1;white-space:nowrap}.kind{font-size:.68rem;padding:1px 6px;border-radius:4px}.k-trend{background:rgba(56,189,248,.15);color:#7dd3fc}.k-contrarian{background:rgba(192,132,252,.15);color:#d8b4fe}.k-flow{background:rgba(245,158,11,.15);color:#fcd34d}
.pill{display:inline-block;min-width:34px;padding:2px 7px;border-radius:6px;font-weight:800;font-family:ui-monospace,Menlo,monospace;font-size:.8rem}
.s-pos2{background:rgba(16,185,129,.25);color:#34d399}.s-pos1{background:rgba(16,185,129,.14);color:#6ee7b7}.s-zero{background:rgba(148,163,184,.18);color:#cbd5e1}.s-neg1{background:rgba(244,63,94,.15);color:#fda4af}.s-neg2{background:rgba(244,63,94,.28);color:#fb7185}
.crit{font-size:.68rem;color:var(--mu);margin-top:3px}
.chart{width:100%;height:auto;display:block;border-radius:10px;margin:6px 0}
.chart-scroll{overflow-x:auto;overflow-y:hidden;border-radius:10px;margin:6px 0;-webkit-overflow-scrolling:touch}
.chart-scroll svg.chart{margin:0}.only-narrow{display:none}.chart-scroll .only-narrow>svg.chart{min-width:600px}
.chart-scroll.sm>svg.chart{min-width:440px;max-width:780px;margin:0 auto}
.swipe{display:none;font-size:.72rem;color:var(--mu);text-align:right;margin:-2px 2px 6px}.swipe.sm,.swipe.t{display:none}.two.one{grid-template-columns:1fr}
.card-h .small{font-weight:500}
.box{--sbg:var(--card)}.card{--sbg:var(--card2)}
.tbl-wrap{background:linear-gradient(to right,var(--sbg) 30%,rgba(0,0,0,0)) left center/30px 100% no-repeat local,linear-gradient(to left,var(--sbg) 30%,rgba(0,0,0,0)) right center/30px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(56,189,248,.38),rgba(0,0,0,0)) left center/12px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(56,189,248,.38),rgba(0,0,0,0)) right center/12px 100% no-repeat scroll}
.legend{font-size:.74rem;color:var(--mu);margin:4px 0 2px;display:flex;flex-wrap:wrap;align-items:center;row-gap:2px}.lg{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 5px 0 0}.lg.c{background:#10b981}.lg.p{background:#f43f5e;margin-left:12px}.lg-note{margin-left:12px}
.nw,.nw1 td:first-child,.nwm td.mono{white-space:nowrap}
.rung-lbl,.rung-note,.gauge-label,.gauge-sub,.pillar-t,.crit,.card-h,.sec-head h2,.h3,.qa-q,.scen-title,.kpi-l,.v-sub,.lesson-t,.news-h{text-wrap-style:balance}
.tbl td{text-wrap-style:pretty}.tbl td.fw,.tbl td:first-child{text-wrap-style:balance}
.c-grp{width:96px}.c-grp2{width:120px}.c-name{width:220px}.c-read{width:250px}.c-score{width:150px}
.w-480{min-width:480px}.w-640{min-width:640px}.w-760{min-width:760px}.w-900{min-width:900px}.w-1100{min-width:1100px}
.two>*,.hero>*,.verdict-grid>*,.qa-grid>*,.scen-grid>*,.lessons>*,.gauges>*,.pillars>*,.kpis>*,.tiles>*,.checks>*{min-width:0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.box>.card{margin-top:14px}.card{background:var(--card2);border:1px solid var(--bd);border-radius:11px;padding:12px}
.card-h{font-size:.9rem;font-weight:700;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px}.kpi{background:#0b1120;border:1px solid var(--bd);border-radius:7px;padding:6px;text-align:center}.kpi-l{font-size:.68rem;color:var(--mu)}.kpi-v{font-weight:800;font-family:ui-monospace,Menlo,monospace;font-size:.9rem}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.tile{border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:7px}.tile-top{display:flex;justify-content:space-between;font-size:.76rem}.tile-top span{color:var(--mu)}.tile-p{font-size:.78rem;color:#cbd5e1;font-family:ui-monospace,Menlo,monospace}.tile-r{font-size:.98rem;font-weight:800;font-family:ui-monospace,Menlo,monospace}.tile-s{font-size:.66rem;color:#cbd5e1;display:flex;flex-wrap:wrap;column-gap:6px}.tile-s span{white-space:nowrap}
.note{margin-top:8px;padding:8px 11px;border-radius:8px;background:rgba(56,189,248,.08);border-left:3px solid var(--acc);font-size:.8rem;color:#e2e8f0}.note.big{font-size:.9rem;margin-bottom:10px}
.det{margin:10px 0}.det summary{cursor:pointer;color:var(--acc);font-weight:600;font-size:.84rem;padding:6px 0}
.lessons{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.lesson{background:var(--card2);border:1px solid var(--bd);border-left:4px solid var(--warn);border-radius:10px;padding:12px}
.lesson-t{font-weight:800;margin-bottom:6px;color:#fbbf24}.lesson-d{font-size:.84rem;color:#e2e8f0}.lesson-r{margin-top:8px;font-size:.82rem;background:rgba(15,23,42,.75);padding:7px 9px;border-radius:7px;color:#f8fafc;font-weight:600}
.news{background:var(--card2);border:1px solid var(--bd);border-radius:9px;padding:10px 12px;margin-bottom:8px;font-size:.8rem}.news.bull{border-left:4px solid var(--bull)}.news.bear{border-left:4px solid var(--bear)}.news.neutral{border-left:4px solid var(--warn)}
.news-h{margin-bottom:5px;color:#e2e8f0}.badge{float:right;font-size:.72rem;background:rgba(255,255,255,.08);padding:1px 8px;border-radius:99px}.news ul{list-style:none}.news li{margin:3px 0;color:#cbd5e1}.tagz{font-size:.68rem;background:#1e293b;padding:1px 5px;border-radius:4px;color:#cbd5e1}
.btns{display:inline-flex;gap:4px}
.foot{font-size:.74rem;color:var(--mu);text-align:center;margin-top:10px}
/* ---- beginner section ---- */
.verdict-box{border-width:2px}.verdict-box.bear{border-color:rgba(244,63,94,.55)}.verdict-box.bull{border-color:rgba(16,185,129,.55)}.verdict-box.neutral{border-color:rgba(245,158,11,.55)}
.verdict-grid{display:grid;grid-template-columns:1.1fr 1.4fr;gap:16px}
.verdict-card{border-radius:14px;padding:22px;text-align:center;display:flex;flex-direction:column;justify-content:center;gap:8px}
.verdict-card.bear{background:linear-gradient(160deg,rgba(244,63,94,.28),rgba(244,63,94,.08));border:1px solid rgba(244,63,94,.5)}
.verdict-card.bull{background:linear-gradient(160deg,rgba(16,185,129,.28),rgba(16,185,129,.08));border:1px solid rgba(16,185,129,.5)}
.verdict-card.neutral{background:linear-gradient(160deg,rgba(245,158,11,.26),rgba(245,158,11,.08));border:1px solid rgba(245,158,11,.5)}
.v-emoji{font-size:2rem}.v-title{font-size:2rem;font-weight:900;letter-spacing:1px}.v-sub{font-size:.98rem;color:#f8fafc}.v-meta{font-size:.8rem;color:#cbd5e1;margin-top:6px}
.verdict-side{background:var(--card2);border:1px solid var(--bd);border-radius:12px;padding:14px}
.meter{width:100%;height:auto;display:block}
.meter-names{display:grid;grid-template-columns:repeat(5,1fr);text-align:center;font-size:.78rem;font-weight:600;color:#94a3b8;margin-top:2px}.meter-names span{white-space:nowrap}.meter-names span.on{color:#f8fafc;font-weight:800}
.ratio{display:flex;height:30px;border-radius:8px;overflow:hidden;font-size:.8rem;font-weight:800;margin:6px 0}
.ratio div{display:flex;align-items:center;justify-content:center;white-space:nowrap;flex:1 1 0;min-width:max-content;padding:0 8px}
.r-sell{background:#ef4444;color:#fff}.r-hold{background:#64748b;color:#fff}.r-buy{background:#22c55e;color:#06281a}
.tldr{margin-top:14px;background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.3);border-radius:12px;padding:12px 16px}.tldr ol{padding-left:20px;font-size:.95rem}.tldr li{margin:4px 0}
.qa-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}
.qa{background:var(--card2);border:1px solid var(--bd);border-radius:12px;padding:14px}.qa-q{font-weight:800;margin-bottom:6px;color:#fbbf24}.qa-a{font-size:.9rem;color:#f1f5f9}
.size-row{margin-top:14px;background:var(--card2);border:1px solid var(--bd);border-radius:12px;padding:12px 14px}
.size-bar{position:relative;height:26px;background:#1e293b;border-radius:8px;overflow:hidden;margin:8px 0}
.size-fill{height:100%;border-radius:8px}.size-fill.bear{background:#ef4444}.size-fill.neutral{background:#eab308}.size-fill.bull{background:#22c55e}
.size-lbl{position:absolute;right:10px;top:0;line-height:26px;font-weight:800;font-family:ui-monospace,Menlo,monospace}
.case ul{list-style:none}.case-list li{padding:8px 0;border-bottom:1px solid rgba(30,41,59,.7);font-size:.86rem}.case-list li:last-child{border-bottom:none}
.case.bull{border-left:4px solid var(--bull)}.case.bear{border-left:4px solid var(--bear)}
.pts{font-family:ui-monospace,Menlo,monospace;font-weight:800;white-space:nowrap}.case-h{display:flex;justify-content:space-between;align-items:baseline;gap:10px}.why{font-size:.78rem;color:#cbd5e1;margin-top:2px}
.gloss{display:grid;grid-template-columns:240px 1fr;gap:6px 14px;font-size:.84rem;margin-top:8px}.gloss dt{font-weight:700;color:#fbbf24;word-break:keep-all}.gloss dd{color:#e2e8f0}
.mode{background:var(--acc);color:#070b14;border:none;border-radius:999px;padding:6px 14px;font-weight:800;cursor:pointer;font-size:.82rem}
body.beginner .pro{display:none}
body.beginner .nav a.pro-link{opacity:.45}
@media(max-width:1100px){.c-name{width:170px}.c-read{width:190px}.c-score{width:130px}}
@media(max-width:1000px){.only-wide{display:none}.only-narrow{display:block}}
@media(max-width:520px){.swipe.sm{display:block}}
@media(max-width:960px){.swipe.t{display:block;margin-top:4px}}
@media(max-width:685px){.swipe{display:block}}
@media(max-width:640px){body{padding:12px 10px 48px}.box{padding:14px}.top{position:static}.gauges,.pillars,.kpis{grid-template-columns:repeat(2,1fr)!important}.tiles{grid-template-columns:repeat(2,1fr)!important}.nav a{margin:3px 4px 0 0}}
@media(max-width:1100px){.hero,.two,.scen-grid,.lessons,.checks,.verdict-grid,.qa-grid{grid-template-columns:1fr}.gauges{grid-template-columns:repeat(3,1fr)}.pillars{grid-template-columns:repeat(4,1fr)}.tiles{grid-template-columns:repeat(2,1fr)}.gloss{grid-template-columns:1fr}}
"""

JS = """
(function(){
  var fb=document.querySelectorAll('#s2 .fbtn'),rows=document.querySelectorAll('#score-table tbody .row');
  fb.forEach(function(b){b.addEventListener('click',function(){fb.forEach(function(x){x.classList.remove('active')});b.classList.add('active');var m=b.getAttribute('data-filter');
    rows.forEach(function(r){var s=parseInt(r.getAttribute('data-score'),10);var show=true;if(m==='bull')show=s>0;else if(m==='neutral')show=s===0;else if(m==='bear')show=s<0;r.style.display=show?'':'none';});});});
  var hb=document.querySelectorAll('.fbtn.hm'),tiles=document.querySelectorAll('#tiles .tile');
  hb.forEach(function(b){b.addEventListener('click',function(){hb.forEach(function(x){x.classList.remove('active')});b.classList.add('active');var h=b.getAttribute('data-h');
    tiles.forEach(function(t){var v=parseFloat(t.getAttribute('data-r'+h));var el=t.querySelector('.tile-r');el.textContent=(v>=0?'+':'')+v.toFixed(2)+'%';
      t.style.background=v>=5?'rgba(16,185,129,.42)':(v>=0?'rgba(16,185,129,.22)':(v>-3?'rgba(244,63,94,.22)':'rgba(244,63,94,.42)'));});});});
  var mb=document.getElementById('modeBtn');
  if(mb){mb.addEventListener('click',function(){var b=document.body;b.classList.toggle('beginner');var beg=b.classList.contains('beginner');mb.textContent=beg?'切換到進階模式 ▸':'◂ 回到新手模式';});}
  document.querySelectorAll('.nav a.pro-link').forEach(function(a){a.addEventListener('click',function(){document.body.classList.remove('beginner');var m=document.getElementById('modeBtn');if(m){m.textContent='◂ 回到新手模式';}});});
})();
"""


def render(p: dict) -> str:
  from .report_plan import beginner_card_html, dashboard_card_html, flash_card_html, plan_card_html, signals_table_html  # local import avoids a cycle
  warn = ""
  if p.get("warnings"):
    warn = f'<div class="note">⚠️ 部分來源暫時無法取得 ({esc("; ".join(p["warnings"]))})，其餘分析不受影響；稍後重跑即可補齊。</div>'
  ds = p.get("data_status") or {}
  if ds.get("provisional"):
    warn += f'<div class="note">{"⏱️" if ds.get("final") else "⚠️"} {esc(ds.get("note", ""))}</div>'
  sch = p.get("schedule") or {}
  if sch.get("installed"):
    auto = f"🔄 每日自動更新：{esc(sch.get('weekday_text'))} {esc('、'.join(sch.get('times') or []))}，下次 {esc(sch.get('next_run_short') or 'n/a')}"
  else:
    auto = "⏸ 自動更新未啟用（.venv/bin/python auto_update.py install）"
  last = sch.get("last_run") or {}
  if last.get("status") == "error":
    auto += f"｜❌ 上次自動更新失敗 {esc(last.get('finished'))}"
  return f'''<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{NONCE}'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none';">
<title>SOXL 投資決策儀表板 — {esc(p["data_as_of"])}</title><style>{CSS}</style></head>
<body class="beginner">
<header class="top"><div class="brand">SOXL 投資決策儀表板 (Quant Playbook)<small>資料 {esc(p["data_as_of"])} {esc((p.get("data_status") or {}).get("label") or "收盤")} · 產生 {esc(p["generated_at"])} · {auto}</small></div>
<nav class="nav"><a href="soxl_simple.html">👶 新手版</a><a href="#s0a">0a 該不該買 / 六個儀表 / 時事</a><a href="#s0">0 新手一頁看懂</a><a href="#s0b">0b 交易計畫 / 驗證</a><a href="#s1">1 怎麼做</a><a href="#s2" class="pro-link">2 評分表</a><a href="#s3">3 圖表</a><a href="#s4" class="pro-link">4 情緒 &amp; 期權</a><a href="#s5" class="pro-link">5 崩跌復盤</a> <button id="modeBtn" class="mode" type="button">切換到進階模式 ▸</button></nav></header>
{warn}
<section id="s0a" class="box">{beginner_card_html(p, "0a. 新手一眼看懂：現在該不該買？")}{dashboard_card_html(p, "📟 六個儀表：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌")}{flash_card_html(p, "📰 今天發生了什麼（過去 36 小時，對 SOXL 的影響）")}</section>
{sec_beginner(p)}
<section id="s0b" class="box">{plan_card_html(p, "0b. 可執行的交易計畫")}{signals_table_html(p, "0c. 訊號驗證：買賣點歷史命中率（附基準與 p 值）")}</section>
{sec_playbook(p)}
{sec_scorecard(p).replace('<section id="s2" class="box">', '<section id="s2" class="box pro">', 1)}
{sec_charts(p)}
{sec_sentiment(p).replace('<section id="s4" class="box">', '<section id="s4" class="box pro">', 1)}
{sec_postmortem(p).replace('<section id="s5" class="box">', '<section id="s5" class="box pro">', 1)}
<div class="foot">資料來源：Nasdaq / CBOE (選擇權鏈、VIX 家族、Put/Call 統計) / CNN Fear &amp; Greed / 美國財政部殖利率 / Yahoo Finance / Google News。本報告為量化研究工具，非投資建議；3x 槓桿 ETF 風險極高。</div>
<script nonce="{NONCE}">{JS}</script>
</body></html>'''
