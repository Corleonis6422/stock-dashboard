#!/usr/bin/env python3
"""Shared pieces of the viewer page: escaping, SVG helpers, small charts, the glossary and the base CSS.

``report_page.py`` assembles the page.  ``report_chart.py`` draws the combined chart of the first
screen and ``report_sections.py`` builds the ten sections; both import their helpers from here.

Security: every interpolated value passes through html.escape(); the page ships a strict
Content-Security-Policy with a script nonce and loads no external resource.
"""

from __future__ import annotations

import html
import math

NONCE = "soxlQuant2026"


def esc(v: object) -> str:
  return html.escape("" if v is None else str(v), quote=True)


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


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
CSS = """
:root{--bg:#070b14;--card:#0f172a;--card2:#131d33;--bd:#1e293b;--tx:#f1f5f9;--mu:#94a3b8;--bull:#10b981;--bear:#f43f5e;--warn:#f59e0b;--acc:#38bdf8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang TC","Microsoft JhengHei",sans-serif;line-height:1.55;padding:18px 22px 60px;max-width:1420px;margin:0 auto}
a{color:var(--acc)}
.up{color:#34d399}
.dn{color:#fb7185}
.score-line{font-size:1.05rem;font-weight:700}
.regime{margin-top:6px;font-size:.88rem;color:#fbbf24;font-weight:700}
.headline{font-size:1.05rem;font-weight:800;color:var(--acc);margin-bottom:8px}
.bul{padding-left:18px;font-size:.88rem;color:#e2e8f0}
.bul li{margin:4px 0}
.ladder{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px}
.rung{background:var(--card2);border:1px solid var(--bd);border-radius:9px;padding:8px;text-align:center}
.rung.res{border-top:3px solid var(--bear)}
.rung.sup{border-top:3px solid var(--bull)}
.rung.cur{border:2px solid var(--acc);background:rgba(56,189,248,.12)}
.rung-val{font-family:ui-monospace,Menlo,monospace;font-weight:800;font-size:1rem}
.rung-lbl{font-size:.74rem;color:#e2e8f0;font-weight:600}
.rung-note{font-size:.68rem;color:var(--mu)}
.scen-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.scen{background:var(--card2);border:1px solid var(--bd);border-radius:10px;padding:14px;font-size:.84rem;color:#cbd5e1}
.scen.bull{border-left:4px solid var(--bull)}
.scen.neutral{border-left:4px solid var(--warn)}
.scen.bear{border-left:4px solid var(--bear)}
.scen-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.scen-title{font-weight:800;color:#f8fafc}
.scen-prob{font-size:.78rem;font-weight:800;background:rgba(255,255,255,.1);padding:2px 8px;border-radius:99px;white-space:nowrap}
.scen-row{margin:4px 0}
.scen-act{margin-top:8px;padding:7px 9px;border-radius:7px;background:rgba(15,23,42,.75);color:#f8fafc;font-weight:600}
.checks{list-style:none;display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
.checks li{background:var(--card2);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;font-size:.84rem}
.checks li.ok{border-left:3px solid var(--bull)}
.checks li.no{border-left:3px solid var(--bear)}
.chk-now{float:right;color:var(--mu);font-family:ui-monospace,Menlo,monospace;font-size:.78rem}
.filters{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.fbtn{background:#1e293b;color:#cbd5e1;border:1px solid #334155;border-radius:7px;padding:4px 11px;font-size:.78rem;font-weight:600;cursor:pointer}
.fbtn.active{background:var(--acc);color:#070b14;border-color:var(--acc)}
.tbl-wrap{overflow-x:auto}
.tbl-wrap.tall{max-height:420px;overflow-y:auto}
.tbl{width:100%;border-collapse:collapse;font-size:.84rem}
.tbl.small{font-size:.78rem}
.tbl th{background:#162032;color:var(--mu);text-align:left;padding:7px 8px;font-size:.74rem;border-bottom:1px solid var(--bd);position:sticky;top:0;white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid rgba(30,41,59,.7);vertical-align:top}
.tbl tr:hover{background:rgba(56,189,248,.04)}
.tbl tr.hl td{background:rgba(244,63,94,.08)}
.tbl tr.on td{background:rgba(245,158,11,.08)}
.tbl tr.act td{background:rgba(56,189,248,.08)}
.tbl tr.tot td{border-top:2px solid var(--bd)}
.fw{font-weight:600}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem}
.small{font-size:.74rem;color:var(--mu)}
.center{text-align:center}
.rat{color:#cbd5e1;font-size:.8rem}
.cat{font-size:.72rem;padding:2px 6px;border-radius:5px;background:#1e293b;color:#cbd5e1;white-space:nowrap}
.kind{font-size:.68rem;padding:1px 6px;border-radius:4px}
.k-trend{background:rgba(56,189,248,.15);color:#7dd3fc}
.k-contrarian{background:rgba(192,132,252,.15);color:#d8b4fe}
.k-flow{background:rgba(245,158,11,.15);color:#fcd34d}
.pill{display:inline-block;min-width:34px;padding:2px 7px;border-radius:6px;font-weight:800;font-family:ui-monospace,Menlo,monospace;font-size:.8rem}
.s-pos2{background:rgba(16,185,129,.25);color:#34d399}
.s-pos1{background:rgba(16,185,129,.14);color:#6ee7b7}
.s-zero{background:rgba(148,163,184,.18);color:#cbd5e1}
.s-neg1{background:rgba(244,63,94,.15);color:#fda4af}
.s-neg2{background:rgba(244,63,94,.28);color:#fb7185}
.crit{font-size:.68rem;color:var(--mu);margin-top:3px}
.chart{width:100%;height:auto;display:block;border-radius:10px;margin:6px 0}
.chart-scroll{overflow-x:auto;overflow-y:hidden;border-radius:10px;margin:6px 0;-webkit-overflow-scrolling:touch}
.chart-scroll svg.chart{margin:0}
.chart-scroll.sm>svg.chart{min-width:440px;max-width:780px;margin:0 auto}
.swipe{display:none;font-size:.72rem;color:var(--mu);text-align:right;margin:-2px 2px 6px}
.swipe.sm,.swipe.t{display:none}
.card-h .small{font-weight:500}
.card{--sbg:var(--card2)}
.tbl-wrap{background:linear-gradient(to right,var(--sbg) 30%,rgba(0,0,0,0)) left center/30px 100% no-repeat local,linear-gradient(to left,var(--sbg) 30%,rgba(0,0,0,0)) right center/30px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(56,189,248,.38),rgba(0,0,0,0)) left center/12px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(56,189,248,.38),rgba(0,0,0,0)) right center/12px 100% no-repeat scroll}
.legend{font-size:.74rem;color:var(--mu);margin:4px 0 2px;display:flex;flex-wrap:wrap;align-items:center;row-gap:2px}
.lg{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 5px 0 0}
.lg.c{background:#10b981}
.lg.p{background:#f43f5e;margin-left:12px}
.lg-note{margin-left:12px}
.nw,.nw1 td:first-child,.nwm td.mono{white-space:nowrap}
.rung-lbl,.rung-note,.crit,.card-h,.qa-q,.scen-title,.kpi-l,.lesson-t,.news-h{text-wrap-style:balance}
.tbl td{text-wrap-style:pretty}
.tbl td.fw,.tbl td:first-child{text-wrap-style:balance}
.c-grp{width:96px}
.c-grp2{width:120px}
.c-name{width:220px}
.c-read{width:250px}
.c-score{width:150px}
.w-480{min-width:480px}
.w-640{min-width:640px}
.w-760{min-width:760px}
.w-900{min-width:900px}
.two>*,.qa-grid>*,.scen-grid>*,.lessons>*,.kpis>*,.tiles>*,.checks>*{min-width:0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.card{background:var(--card2);border:1px solid var(--bd);border-radius:11px;padding:12px}
.card-h{font-size:.9rem;font-weight:700;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px}
.kpi{background:#0b1120;border:1px solid var(--bd);border-radius:7px;padding:6px;text-align:center}
.kpi-l{font-size:.68rem;color:var(--mu)}
.kpi-v{font-weight:800;font-family:ui-monospace,Menlo,monospace;font-size:.9rem}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
.tile{border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:7px}
.tile-r{font-size:.98rem;font-weight:800;font-family:ui-monospace,Menlo,monospace}
.note{margin-top:8px;padding:8px 11px;border-radius:8px;background:rgba(56,189,248,.08);border-left:3px solid var(--acc);font-size:.8rem;color:#e2e8f0}
.note.big{font-size:.9rem;margin-bottom:10px}
.lessons{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.lesson{background:var(--card2);border:1px solid var(--bd);border-left:4px solid var(--warn);border-radius:10px;padding:12px}
.lesson-t{font-weight:800;margin-bottom:6px;color:#fbbf24}
.lesson-d{font-size:.84rem;color:#e2e8f0}
.lesson-r{margin-top:8px;font-size:.82rem;background:rgba(15,23,42,.75);padding:7px 9px;border-radius:7px;color:#f8fafc;font-weight:600}
.news{background:var(--card2);border:1px solid var(--bd);border-radius:9px;padding:10px 12px;margin-bottom:8px;font-size:.8rem}
.news.bull{border-left:4px solid var(--bull)}
.news.bear{border-left:4px solid var(--bear)}
.news.neutral{border-left:4px solid var(--warn)}
.news-h{margin-bottom:5px;color:#e2e8f0}
.badge{float:right;font-size:.72rem;background:rgba(255,255,255,.08);padding:1px 8px;border-radius:99px}
.news ul{list-style:none}
.news li{margin:3px 0;color:#cbd5e1}
.tagz{font-size:.68rem;background:#1e293b;padding:1px 5px;border-radius:4px;color:#cbd5e1}
.btns{display:inline-flex;gap:4px}
.meter{width:100%;height:auto;display:block}
.meter-names{display:grid;grid-template-columns:repeat(5,1fr);text-align:center;font-size:.78rem;font-weight:600;color:#94a3b8;margin-top:2px}
.meter-names span{white-space:nowrap}
.meter-names span.on{color:#f8fafc;font-weight:800}
.ratio{display:flex;height:30px;border-radius:8px;overflow:hidden;font-size:.8rem;font-weight:800;margin:6px 0}
.ratio div{display:flex;align-items:center;justify-content:center;white-space:nowrap;flex:1 1 0;min-width:max-content;padding:0 8px}
.r-sell{background:#ef4444;color:#fff}
.r-hold{background:#64748b;color:#fff}
.r-buy{background:#22c55e;color:#06281a}
.tldr{margin-top:14px;background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.3);border-radius:12px;padding:12px 16px}
.tldr ol{padding-left:20px;font-size:.95rem}
.tldr li{margin:4px 0}
.qa-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}
.qa{background:var(--card2);border:1px solid var(--bd);border-radius:12px;padding:14px}
.qa-q{font-weight:800;margin-bottom:6px;color:#fbbf24}
.qa-a{font-size:.9rem;color:#f1f5f9}
.size-bar{position:relative;height:26px;background:#1e293b;border-radius:8px;overflow:hidden;margin:8px 0}
.size-fill{height:100%;border-radius:8px}
.size-fill.bear{background:#ef4444}
.size-fill.neutral{background:#eab308}
.size-fill.bull{background:#22c55e}
.size-lbl{position:absolute;right:10px;top:0;line-height:26px;font-weight:800;font-family:ui-monospace,Menlo,monospace}
.case ul{list-style:none}
.case-list li{padding:8px 0;border-bottom:1px solid rgba(30,41,59,.7);font-size:.86rem}
.case-list li:last-child{border-bottom:none}
.case.bull{border-left:4px solid var(--bull)}
.case.bear{border-left:4px solid var(--bear)}
.pts{font-family:ui-monospace,Menlo,monospace;font-weight:800;white-space:nowrap}
.case-h{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.gloss{display:grid;grid-template-columns:240px 1fr;gap:6px 14px;font-size:.84rem;margin-top:8px}
.gloss dt{font-weight:700;color:#fbbf24;word-break:keep-all}
.gloss dd{color:#e2e8f0}
@media(max-width:1100px){.c-name{width:170px}
.c-read{width:190px}
.c-score{width:130px}}
@media(max-width:520px){.swipe.sm{display:block}}
@media(max-width:960px){.swipe.t{display:block;margin-top:4px}}
@media(max-width:685px){.swipe{display:block}}
@media(max-width:640px){body{padding:12px 10px 48px}
.kpis{grid-template-columns:repeat(2,1fr)!important}
.tiles{grid-template-columns:repeat(2,1fr)!important}}
@media(max-width:1100px){.two,.scen-grid,.lessons,.checks,.qa-grid{grid-template-columns:1fr}
.tiles{grid-template-columns:repeat(2,1fr)}
.gloss{grid-template-columns:1fr}}
"""

