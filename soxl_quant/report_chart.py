#!/usr/bin/env python3
"""The combined chart of the first screen: SOXL candles, VIX, volume and the crash index on one date axis.

Input is the block that ``stress_chart.for_payload`` returns.  This module draws.  It computes no
rule and no figure: spike flags, episodes, channel, profile and the evidence figures all come from
the block.  ``docs/page_markers.md`` lists the markers a script can rely on.

How one drawing serves every screen width
  * Each view (daily, weekly) is one ``<svg>`` that holds every shape and no text.  Its viewBox is
    1000 x 1000 with ``preserveAspectRatio="none"``, so the drawing stretches to the box that CSS
    gives it and never needs a horizontal scroll.  Strokes keep their width (``vector-effect``).
  * Every label is an HTML element laid over the drawing and placed in percent of the same box, so
    type keeps its size at every width.  Axis labels sit in two gutters of fixed width.
  * A label of fixed size covers more bars on a narrow screen.  The labels that must stay clear of
    candles (the spike labels) and the date ticks are therefore placed twice, for a wide and for a
    narrow box (``LAYOUTS``); CSS shows one of the two.

Security: every value goes through ``html.escape``; the script uses textContent and attributes only.
"""

from __future__ import annotations

import html
import math

from . import stress_chart as sx
from .report_html import _tw

VB = 1000.0                       # viewBox width and height
BARS_X1 = 868.0                   # bars occupy x 0 .. BARS_X1
PROF_X0, PROF_X1 = 880.0, 1000.0  # the volume profile sits right of the bars, inside the price panel
TOP, STRIP, GAP, DATE_H = 2.0, 44.0, 6.0, 38.0   # top margin, title strip above each panel, gap under a panel, date axis
PANEL_H = {"volume": 108.0, "vix": 104.0, "crash": 118.0}   # the price panel takes the rest
BODY_MAX = 14.0                   # widest candle body, for views with few bars
# viewBox units per CSS px (x, y) in the narrowest box of each label layout: "w" from 700 px page width, "n" below it
LAYOUTS = {"w": (VB / 510.0, VB / 480.0), "n": (VB / 222.0, VB / 440.0)}
UY_MIN = LAYOUTS["n"][1]          # the gutter labels are placed once, for the shortest box
DATE_TICKS = {"w": {"daily": 7, "weekly": 6}, "n": {"daily": 4, "weekly": 3}}
SPIKE_FS, SPIKE_H = 10.5, 17.0    # spike label: font size and box height in CSS px
MAX_SPIKE_LABELS = 3
VIEW_NAME = {"daily": "日線", "weekly": "週線"}
VIEW_SPAN = {"daily": "約 6 個月", "weekly": "約 2 年"}
NA_VIX, NA_CRASH = "未公布", "無資料"


def esc(v: object) -> str:
  return html.escape("" if v is None else str(v), quote=True)


def _n(v: float, nd: int = 1) -> str:
  """A number for an attribute: ``nd`` decimals at most, no trailing zeros."""
  s = f"{v:.{nd}f}"
  if "." in s:
    s = s.rstrip("0").rstrip(".")
  return "0" if s in ("-0", "") else s


def _pc(u: float) -> str:
  """viewBox units as a CSS percentage of the drawing box."""
  return _n(u / 10.0, 2) + "%"


def _tick_usd(p: float) -> str:
  if p >= 1000:
    return "$" + _n(p / 1000.0, 1) + "k"
  return "$" + _n(p, 2)


def _band_usd(p: float) -> str:
  return f"{p:.0f}" if p >= 100 else (f"{p:.1f}" if p >= 10 else f"{p:.2f}")


def _last_usd(p: float) -> str:
  """The latest close for the right gutter: whole dollars from $1,000 so it fits."""
  return f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}"


def shares_zh(v: float) -> str:
  """Volume for the reader, rounded half up in whole steps so the page script prints the same text."""
  v = max(0, int(v))
  if v >= 1_000_000:
    return f"{(v + 500_000) // 1_000_000 / 100:.2f} 億股"
  if v >= 10_000:
    return f"{(v + 5_000) // 10_000} 萬股"
  return f"{v} 股"


def _shares_short(v: float) -> str:
  return shares_zh(v).replace(" ", "").replace("股", "")


def _mmdd(d: str) -> str:
  return d[5:].replace("-", "/")


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def _panels(names: list[str]) -> dict[str, tuple[float, float]]:
  """Plot area (y0, y1) of each panel, top to bottom; a title strip of STRIP units sits above each."""
  fixed = sum(PANEL_H[n] for n in names if n != "price")
  price_h = VB - DATE_H - TOP - len(names) * STRIP - (len(names) - 1) * GAP - fixed
  out: dict[str, tuple[float, float]] = {}
  y = TOP
  for n in names:
    h = price_h if n == "price" else PANEL_H[n]
    out[n] = (y + STRIP, y + STRIP + h)
    y += STRIP + h + GAP
  return out


def _runs(vals: list) -> list[list[int]]:
  """Positions that have a value, split where a value is missing."""
  runs: list[list[int]] = []
  cur: list[int] = []
  for i, v in enumerate(vals):
    if v is None:
      if cur:
        runs.append(cur)
        cur = []
    else:
      cur.append(i)
  if cur:
    runs.append(cur)
  return runs


def _polylines(series: str, vals: list, xs: list[float], yf) -> str:
  """One ``<polyline>`` per run of bars that have a value.

  Vertex k belongs to bar ``data-first + k``; ``data-n`` is the number of bars in the run.  A run of
  one bar repeats its point, so it shows as a dot.
  """
  out = []
  for run in _runs(vals):
    idx = run if len(run) > 1 else run * 2
    pts = " ".join(f"{_n(xs[i])},{_n(yf(vals[i]))}" for i in idx)
    out.append(f'<polyline data-series="{series}" data-first="{run[0]}" data-n="{len(run)}" points="{pts}"/>')
  return "".join(out)


def _price_ticks(a_lo: float, a_hi: float, yp, y0: float, y1: float, min_gap: float) -> list[tuple[float, float]]:
  """Ticks of a logarithmic price axis, from the top: 1-2-3-5-7 steps that keep ``min_gap`` units apart."""
  cands = sorted({m * 10.0 ** e for e in range(-3, 7) for m in (1, 2, 3, 5, 7)})
  out: list[tuple[float, float]] = []
  for p in reversed([c for c in cands if a_lo <= math.log(c) <= a_hi]):
    y = yp(p)
    if y0 + min_gap / 2 <= y <= y1 - min_gap / 2 and (not out or y - out[-1][1] >= min_gap):
      out.append((p, y))
  if len(out) < 2:  # a very narrow range: three even steps in log price
    out = []
    for k in (0.15, 0.5, 0.85):
      p = math.exp(a_hi - k * (a_hi - a_lo))
      p = float(f"{p:.3g}")
      out.append((p, yp(p)))
  return out


def _nice_ticks(lo: float, hi: float, yf, y0: float, y1: float, min_gap: float, most: int = 3) -> list[tuple[float, float]]:
  """Up to ``most`` round ticks of a linear axis that keep ``min_gap`` units apart."""
  for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000):
    ticks = []
    t = math.ceil(lo / step) * step
    while t <= hi and len(ticks) <= most:
      y = yf(t)
      if y0 + min_gap / 2 <= y <= y1 - min_gap / 2:
        ticks.append((float(t), y))
      t += step
    if ticks and len(ticks) <= most and all(abs(a[1] - b[1]) >= min_gap for a, b in zip(ticks, ticks[1:])):
      return ticks
  mid = (lo + hi) / 2.0   # no round number fits: label the middle of the range
  return [(mid, yf(mid))]


def _date_ticks(n: int, want: int) -> list[int]:
  if n <= 1:
    return [0] if n else []
  want = max(2, min(want, n))
  return sorted({round(j * (n - 1) / (want - 1)) for j in range(want)})


def _place_spike_labels(eps: list[tuple[int, int]], xs: list[float], y_hi: list[float], y_lo: list[float],
                        p0: float, p1: float, w: float, h: float, ux: float, uy: float) -> list[dict]:
  """Place one label box of ``w`` x ``h`` units for each episode ``(k, anchor bar)``, latest first.

  A label sits above or below the candles of every bar it spans, so it covers none of them.  Its
  leader is the vertical line at the anchor bar from the label towards that candle; it stops short
  of the tallest candle under its arrow head, which is 8 px wide.  The label is centred
  on the anchor, or pushed left or right of it near an edge.  Labels and leaders placed earlier are
  obstacles: a label moves further out past them, and a leader may not cross them.  The candidate
  with the shortest leader wins.  ``ok`` is False when no candidate fits inside the panel.
  """
  gap, lead = 3.0 * uy, 8.0 * uy
  obstacles: list[tuple[float, float, float, float]] = []
  out: list[dict] = []
  for k, a in eps:
    xa = xs[a]
    near = [i for i, x in enumerate(xs) if abs(x - xa) <= 5.0 * ux] or [a]   # the candles under the arrow head
    hi_a, lo_a = min(y_hi[i] for i in near), max(y_lo[i] for i in near)
    best = None
    for align, x0 in (("c", xa - w / 2), ("r", min(xa + 2 * ux, BARS_X1) - w), ("l", max(xa - 2 * ux, 0.0))):
      if x0 < 0 or x0 + w > BARS_X1 + 1e-6:
        continue
      idx = [i for i, x in enumerate(xs) if x0 - ux <= x <= x0 + w + ux] or [a]
      top, bot = min(y_hi[i] for i in idx), max(y_lo[i] for i in idx)
      for side in ("a", "b"):
        if side == "a":
          ya = min(top - gap, hi_a - gap - lead) - h      # top edge of the box
          tip = hi_a - gap
        else:
          ya = max(bot + gap, lo_a + gap + lead)
          tip = lo_a + gap
        clear = False
        for _ in range(8):
          hit = next((o for o in obstacles if x0 < o[2] + 2 * ux and x0 + w > o[0] - 2 * ux and ya < o[3] + uy and ya + h > o[1] - uy), None)
          if hit is None:
            clear = True
            break
          ya = hit[1] - 2 * uy - h if side == "a" else hit[3] + 2 * uy
        s0, s1 = (ya + h, tip) if side == "a" else (tip, ya)   # the leader, top to bottom
        crosses = any(o[0] - ux <= xa <= o[2] + ux and s0 < o[3] and s1 > o[1] for o in obstacles)
        inside = ya >= p0 + 1 and ya + h <= p1 - 1
        over = max(0.0, p0 + 1 - ya) + max(0.0, ya + h - (p1 - 1))
        cost = (s1 - s0) + (0.0 if align == "c" else 4 * uy) + (0.0 if side == "a" else uy)
        cand = {"k": k, "bar": a, "side": side, "align": align, "x0": x0, "y0": ya, "tip": tip, "s0": s0, "s1": s1,
                "ok": bool(clear and inside and not crosses), "rank": (0 if clear and inside and not crosses else 1, over, cost)}
        if best is None or cand["rank"] < best["rank"]:
          best = cand
    if best is None:  # the box is wider than the bar area: centre it and let the caller see ok=False
      best = {"k": k, "bar": a, "side": "a", "align": "c", "x0": max(0.0, xa - w / 2), "y0": p0 + 1, "tip": hi_a - gap, "s0": p0 + 1 + h, "s1": hi_a - gap, "ok": False, "rank": (2, 0, 0)}
    if not best["ok"]:  # keep the box inside the panel
      best["y0"] = min(max(best["y0"], p0 + 1), p1 - 1 - h)
      if best["side"] == "a":
        best["s0"], best["s1"] = best["y0"] + h, max(best["tip"], best["y0"] + h)
      else:
        best["s0"], best["s1"] = min(best["tip"], best["y0"]), best["y0"]
    obstacles.append((best["x0"], best["y0"], best["x0"] + w, best["y0"] + h))
    obstacles.append((xa - ux, best["s0"], xa + ux, best["s1"]))
    out.append(best)
  return out


# --------------------------------------------------------------------------- #
# one view
# --------------------------------------------------------------------------- #
def _view(block: dict, kind: str) -> dict:
  """The parts of one view: the drawing with its labels, the read-out, the legend, the rule lines."""
  v = block["views"][kind]
  rows = sx.view_bars(block, kind)
  n = len(rows)
  weekly = kind == "weekly"
  dkey = "end" if weekly else "date"
  avg_key = "vol_avg20w" if weekly else "vol_avg20"
  ser = v.get("series") or {}
  has_vix, has_crash, has_avg = bool(ser.get("vix")), bool(ser.get("crash")), bool(ser.get("volume_avg"))
  names = ["price", "volume"] + (["vix"] if has_vix else []) + (["crash"] if has_crash else [])
  pan = _panels(names)
  p0, p1 = pan["price"]
  step = BARS_X1 / n
  xs = [(i + 0.5) * step for i in range(n)]
  bw = min(max(step * 0.62, 1.6), BODY_MAX)
  lg = block.get("legend") or {}
  rules = block.get("rules") or {}

  # ---- price scale: logarithmic, wide enough for the candles and the channel end points
  ch = v.get("channel") or {}
  lo, hi = min(r["low"] for r in rows), max(r["high"] for r in rows)
  if ch.get("available"):
    lo, hi = min([lo] + list(ch["lower"])), max([hi] + list(ch["upper"]))
  llo, lhi = math.log(lo), math.log(hi)
  if lhi - llo < 0.02:
    mid = (llo + lhi) / 2
    llo, lhi = mid - 0.01, mid + 0.01

  spikes = v.get("spikes") or {}
  episodes = spikes.get("episodes") or []
  labelled = [(k, e["anchor_bar"]) for k, e in list(enumerate(episodes))[-MAX_SPIKE_LABELS:]][::-1]   # latest first
  spike_text = str(lg.get("spike_label_zh") or "VIX 急升")
  spike_w = _tw(spike_text, SPIKE_FS, bold=True) + 8.0
  placed: dict[str, list[dict]] = {}
  yp = None
  a_lo = a_hi = 0.0
  for pad_top, pad_bot in ((0.04, 0.04), (0.16, 0.04), (0.04, 0.16), (0.16, 0.16), (0.3, 0.3)):
    span = lhi - llo
    a_hi, a_lo = lhi + span * pad_top, llo - span * pad_bot

    def yp(p: float, _hi: float = a_hi, _lo: float = a_lo) -> float:
      return p0 + (_hi - math.log(p)) / (_hi - _lo) * (p1 - p0)

    y_hi, y_lo = [yp(r["high"]) for r in rows], [yp(r["low"]) for r in rows]
    placed = {lay: _place_spike_labels(labelled, xs, y_hi, y_lo, p0, p1, spike_w * ux, SPIKE_H * uy, ux, uy) for lay, (ux, uy) in LAYOUTS.items()}
    if all(pl["ok"] for pls in placed.values() for pl in pls):
      break

  svg: list[str] = []
  lab: list[str] = []     # labels inside the drawing box, in percent of it
  gut: list[str] = []     # labels in the two gutters, vertical position in percent of the drawing box

  # ---- panel backgrounds, titles
  for name in names:
    y0, y1 = pan[name]
    svg.append(f'<rect class="sx-pbg" data-panel="{name}" x="0" y="{_n(y0)}" width="1000" height="{_n(y1 - y0)}"/>')

  def title(name: str, inner: str) -> None:
    lab.append(f'<span class="sx-l sx-t" data-panel-title="{name}" style="left:0;top:{_pc(pan[name][0] - STRIP + 8)}">{inner}</span>')

  # ---- price ticks and grid
  for p, y in _price_ticks(a_lo, a_hi, yp, p0, p1, 14.0 * UY_MIN):
    svg.append(f'<line class="sx-grid" x1="0" y1="{_n(y)}" x2="1000" y2="{_n(y)}"/>')
    gut.append(f'<span class="sx-l sx-yl sx-mid" data-tick="price" style="top:{_pc(y)}">{esc(_tick_usd(p))}</span>')
  svg.append(f'<line class="sx-sep" x1="{_n((BARS_X1 + PROF_X0) / 2)}" y1="{_n(p0)}" x2="{_n((BARS_X1 + PROF_X0) / 2)}" y2="{_n(p1)}"/>')

  # ---- date ticks (two sets) and vertical guides for the wide set
  last_y = pan[names[-1]][1]
  for lay in LAYOUTS:
    ticks = _date_ticks(n, DATE_TICKS[lay][kind])
    for j, i in enumerate(ticks):
      d = rows[i][dkey]
      txt = d[:7].replace("-", "/") if weekly else _mmdd(d)
      align = " sx-tr" if (j == len(ticks) - 1 and len(ticks) > 1) else ("" if j == 0 else " sx-tc")
      lab.append(f'<span class="sx-l sx-dt sx-{lay}{align}" data-tick="date" data-bar="{i}" style="left:{_pc(xs[i])};top:{_pc(last_y + 6)}">{esc(txt)}</span>')
      if lay == "w":
        for name in names:
          svg.append(f'<line class="sx-grid" x1="{_n(xs[i])}" y1="{_n(pan[name][0])}" x2="{_n(xs[i])}" y2="{_n(pan[name][1])}"/>')

  # ---- trend channel (reference lines: straight on a logarithmic axis)
  if ch.get("available"):
    x0c, x1c = _n(xs[0]), _n(xs[-1])
    up, md, dn = ch["upper"], ch["mid"], ch["lower"]
    svg.append(f'<g data-series="channel" data-direction="{esc(ch.get("direction"))}" data-rsq="{_n(ch.get("r2") or 0, 4)}">'
               f'<polygon class="sx-chf" points="{x0c},{_n(yp(up[0]))} {x1c},{_n(yp(up[1]))} {x1c},{_n(yp(dn[1]))} {x0c},{_n(yp(dn[0]))}"/>')
    for key, ends in (("upper", up), ("mid", md), ("lower", dn)):
      svg.append(f'<line class="sx-chl sx-ch-{key}" data-line="{key}" data-p0="{_n(ends[0], 4)}" data-p1="{_n(ends[1], 4)}" '
                 f'x1="{x0c}" y1="{_n(yp(ends[0]))}" x2="{x1c}" y2="{_n(yp(ends[1]))}"/>')
    svg.append("</g>")

  # ---- latest close: a dotted reference line, the value in the right gutter
  last = rows[-1]
  y_close = yp(last["close"])
  svg.append(f'<line class="sx-lc" x1="0" y1="{_n(y_close)}" x2="1000" y2="{_n(y_close)}"/>')

  # ---- candles
  svg.append('<g data-series="candles">')
  for i, r in enumerate(rows):
    cls = ("s" if r.get("spike") is True else "") + ("u" if r["close"] >= r["open"] else "d")
    yo, yc = yp(r["open"]), yp(r["close"])
    top, hgt = min(yo, yc), abs(yc - yo)
    if hgt < 2.4:
      top, hgt = (yo + yc) / 2 - 1.2, 2.4
    a = f'data-bar="{i}" data-d="{esc(r[dkey])}"'
    if weekly:
      a += f' data-s="{esc(r["start"])}"' + (' data-partial="1"' if r.get("partial") else "")
    a += f' data-c="{_n(r["close"], 2)}" data-v="{int(r.get("volume") or 0)}"'
    if r.get("vix") is not None:
      a += f' data-vix="{_n(r["vix"], 2)}"'
    if r.get("crash") is not None:
      a += f' data-cr="{_n(r["crash"], 1)}"'
    svg.append(f'<g class="{cls}" {a}><path d="M{_n(xs[i])} {_n(yp(r["high"]))}V{_n(yp(r["low"]))}"/>'
               f'<path d="M{_n(xs[i] - bw / 2)} {_n(top)}h{_n(bw)}v{_n(hgt)}h-{_n(bw)}z"/></g>')
  svg.append("</g>")
  title("price", f'SOXL {VIEW_NAME[kind]}<span class="sx-dim">｜價格軸：對數刻度</span>')

  # ---- volume profile at the right of the price panel
  pf = v.get("profile") or {}
  busiest_y = None
  if pf.get("available"):
    bands = sx.table_dicts(pf["bands"])
    vmaxp = max(b["total_volume"] for b in bands) or 1
    bz = (pf.get("busiest") or {}).get("index")
    svg.append(f'<g data-series="profile" data-rule="{esc(pf.get("rule"))}" data-spacing="{esc(pf.get("spacing"))}">')
    for k, b in enumerate(bands):
      yt, yb = yp(b["price_high"]), yp(b["price_low"])
      hgt = max(yb - yt - 1.0, 0.6)
      length = b["total_volume"] / vmaxp * (PROF_X1 - PROF_X0)
      up_len = b["up_volume"] / vmaxp * (PROF_X1 - PROF_X0)
      busy = k == bz
      mark = ' data-busiest="1"' if busy else ""
      svg.append(f'<rect class="{"sx-pb sx-bz" if busy else "sx-pb"}" data-band="{k}" data-lo="{_n(b["price_low"], 4)}" data-hi="{_n(b["price_high"], 4)}" data-vol="{int(b["total_volume"])}"{mark} '
                 f'x="{_n(PROF_X1 - length)}" y="{_n(yt + 0.5)}" width="{_n(length)}" height="{_n(hgt)}"/>')
      if up_len > 0:
        svg.append(f'<rect class="sx-pu" x="{_n(PROF_X1 - up_len)}" y="{_n(yt + 0.5)}" width="{_n(up_len)}" height="{_n(hgt)}"/>')
      if busy:
        busiest_y = (yt + yb) / 2
    svg.append("</g>")

  # ---- right gutter of the price panel: latest close, and the busiest band kept clear of it
  half_close, half_band = 8.0 * UY_MIN, 12.0 * UY_MIN
  yc_lab = min(max(y_close, p0 + half_close), p1 - half_close)
  gut.append(f'<span class="sx-l sx-yr sx-mid sx-last" data-latest="price" data-v="{_n(last["close"], 2)}" style="top:{_pc(yc_lab)}">{_last_usd(last["close"])}</span>')
  if busiest_y is not None:
    bzb = pf["busiest"]
    need = half_close + half_band + 2.0 * UY_MIN
    yb_lab = min(max(busiest_y, p0 + half_band), p1 - half_band)
    if abs(yb_lab - yc_lab) < need:
      below, above = yc_lab + need, yc_lab - need
      first, second = (below, above) if busiest_y >= yc_lab else (above, below)
      yb_lab = first if p0 + half_band <= first <= p1 - half_band else second
    gut.append(f'<span class="sx-l sx-yr sx-mid sx-bzl" data-busiest-label="1" data-band="{esc(bzb.get("index"))}" data-lo="{_n(bzb["price_low"], 4)}" data-hi="{_n(bzb["price_high"], 4)}" '
               f'style="top:{_pc(yb_lab)}">最大量價帶<br>${_band_usd(bzb["price_low"])}–{_band_usd(bzb["price_high"])}</span>')

  # ---- spike labels with their leaders, one set per label layout
  for lay, pls in placed.items():
    for pl in pls:
      e = episodes[pl["k"]]
      xa = xs[pl["bar"]]
      above = pl["side"] == "a"
      if pl["align"] == "c":
        ax, acls = xa, " sx-tc"
      elif pl["align"] == "r":
        ax, acls = pl["x0"] + spike_w * LAYOUTS[lay][0], " sx-tr"
      else:
        ax, acls = pl["x0"], ""
      ay = pl["y0"] + SPIKE_H * LAYOUTS[lay][1] if above else pl["y0"]
      lab.append(f'<span class="sx-l sx-sp sx-{lay}{acls}{" sx-up" if above else ""}" data-spike-label="{pl["k"]}" data-bar="{pl["bar"]}" data-start="{esc(e.get("start"))}" data-end="{esc(e.get("end"))}" '
                 f'style="left:{_pc(ax)};top:{_pc(ay)}">{esc(spike_text)}</span>'
                 f'<i class="sx-ld sx-{lay}" data-spike-leader="{pl["k"]}" data-bar="{pl["bar"]}" style="left:{_pc(xa)};top:{_pc(pl["s0"])};height:{_pc(max(pl["s1"] - pl["s0"], 0.0))}"></i>'
                 f'<i class="sx-ah sx-ah{pl["side"]} sx-{lay}" style="left:{_pc(xa)};top:{_pc(pl["tip"])}"></i>')

  # ---- volume with its average
  v0, v1 = pan["volume"]
  vols = [float(r.get("volume") or 0) for r in rows]
  avgs = [r.get(avg_key) for r in rows]
  vmax = max(vols + [float(a) for a in avgs if a is not None] + [1.0]) * 1.08

  def yv(x: float) -> float:
    return v1 - x / vmax * (v1 - v0)

  svg.append('<g data-series="volume">')
  for i, r in enumerate(rows):
    cls = ("s" if r.get("spike") is True else "") + ("u" if r["close"] >= r["open"] else "d")
    svg.append(f'<rect class="{cls}" x="{_n(xs[i] - bw / 2)}" y="{_n(yv(vols[i]))}" width="{_n(bw)}" height="{_n(v1 - yv(vols[i]))}"/>')
  svg.append("</g>")
  avg_name = "20 週均量" if weekly else "20 日均量"
  if has_avg:
    svg.append(_polylines("volume-avg", avgs, xs, yv))
  title("volume", "成交量" + (f'<i class="sx-k sx-k-va"></i>{avg_name}' if has_avg else ""))
  half = 6.5 * UY_MIN
  gut.append(f'<span class="sx-l sx-yr sx-mid sx-last" data-latest="volume" data-v="{int(vols[-1])}" style="top:{_pc(min(max(yv(vols[-1]), v0 + half), v1 - half))}">{esc(_shares_short(vols[-1]))}</span>')

  # ---- VIX on its own axis
  vix_latest = None
  if has_vix:
    x0v, x1v = pan["vix"]
    vv = [r.get("vix") for r in rows]
    have = [x for x in vv if x is not None]
    lo_v, hi_v = min(have), max(have)
    padv = max((hi_v - lo_v) * 0.12, 0.5)
    lo_v, hi_v = lo_v - padv, hi_v + padv

    def yx(x: float) -> float:
      return x1v - (x - lo_v) / (hi_v - lo_v) * (x1v - x0v)

    for t, y in _nice_ticks(lo_v, hi_v, yx, x0v, x1v, 13.0 * UY_MIN):
      svg.append(f'<line class="sx-grid" x1="0" y1="{_n(y)}" x2="{_n(BARS_X1)}" y2="{_n(y)}"/>')
      gut.append(f'<span class="sx-l sx-yl sx-mid" data-tick="vix" style="top:{_pc(y)}">{_n(t, 1)}</span>')
    svg.append(_polylines("vix", vv, xs, yx))
    j = max(i for i, x in enumerate(vv) if x is not None)
    vix_latest = (j, vv[j])
    gut.append(f'<span class="sx-l sx-yr sx-mid sx-last" data-latest="vix" data-v="{_n(vv[j], 2)}" data-bar="{j}" style="top:{_pc(min(max(yx(vv[j]), x0v + half), x1v - half))}">{vv[j]:.2f}</span>')
    title("vix", 'VIX<span class="sx-dim">（點，獨立刻度）</span>' + (f'<span class="sx-dim">最新 {esc(_mmdd(rows[j][dkey]))}</span>' if j != n - 1 else ""))

  # ---- crash index with its two lines
  if has_crash:
    c0, c1 = pan["crash"]
    cc = [r.get("crash") for r in rows]

    def yc_(s: float) -> float:
      return c1 - max(0.0, min(100.0, s)) / 100.0 * (c1 - c0)

    keys = ""
    for q, ln in enumerate(lg.get("crash_lines") or []):
      val = float(ln.get("value"))
      y = yc_(val)
      svg.append(f'<line class="sx-lv sx-lv{q}" data-level="{_n(val, 1)}" x1="0" y1="{_n(y)}" x2="{_n(BARS_X1)}" y2="{_n(y)}"/>')
      gut.append(f'<span class="sx-l sx-yl sx-mid sx-lvt{q}" data-tick="crash" data-level="{_n(val, 1)}" style="top:{_pc(y)}">{_n(val, 0)}</span>')
      keys += f'<i class="sx-k sx-k-lv{q}"></i>{_n(val, 0)} {esc(ln.get("label_zh"))}'
    for run in _runs(cc):
      pts = " ".join(f"{_n(xs[i])},{_n(yc_(cc[i]))}" for i in run)
      svg.append(f'<polygon class="sx-ca" points="{_n(xs[run[0]])},{_n(c1)} {pts} {_n(xs[run[-1]])},{_n(c1)}"/>')
    svg.append(_polylines("crash", cc, xs, yc_))
    j = max(i for i, x in enumerate(cc) if x is not None)
    gut.append(f'<span class="sx-l sx-yr sx-mid sx-last" data-latest="crash" data-v="{_n(cc[j], 1)}" data-bar="{j}" style="top:{_pc(min(max(yc_(cc[j]), c0 + half), c1 - half))}">{cc[j]:.1f}</span>')
    title("crash", "崩跌指數" + keys)

  # ---- crash-drop markers, in the lowest panel
  drops = v.get("crash_drops") or []
  if drops:
    m0, m1 = pan[names[-1]]
    svg.append(f'<g data-series="crash-drops" data-panel="{names[-1]}">')
    for m in drops:
      x = xs[m["bar"]]
      svg.append(f'<line class="sx-mkl" data-marker="crash-drop" data-bar="{m["bar"]}" data-date="{esc(m.get("date"))}" x1="{_n(x)}" y1="{_n(m0)}" x2="{_n(x)}" y2="{_n(m1)}"/>'
                 f'<polygon class="sx-mk" points="{_n(x - 4.5)},{_n(m0)} {_n(x + 4.5)},{_n(m0)} {_n(x)},{_n(m0 + 20)}"/>')
    svg.append("</g>")

  first_y, bottom_y = pan[names[0]][0], pan[names[-1]][1]
  cross = f'<div class="sx-cl" data-crosshair-line style="top:{_pc(first_y)};height:{_pc(bottom_y - first_y)}"></div>'
  aria = f"SOXL {VIEW_NAME[kind]}組合圖，{v.get('start')} 至 {v.get('end')}，{n} 根 K 棒"
  head = (f'<svg class="sx-svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label="{esc(aria)}" data-view-svg="{kind}" data-n="{n}" data-step="{_n(step, 4)}" '
          f'data-bars-x1="{_n(BARS_X1)}" data-price-scale="log" data-price-y0="{_n(p0)}" data-price-y1="{_n(p1)}" data-price-top="{_n(math.exp(a_hi), 4)}" data-price-bottom="{_n(math.exp(a_lo), 4)}">')
  plot = (f'<div class="sx-plot" data-pane="{kind}"><div class="sx-in" data-cross-target="{kind}">{head}{"".join(svg)}</svg>{"".join(lab)}{cross}</div>{"".join(gut)}</div>')

  # ---- read-out: the latest bar until the crosshair moves
  r = last
  ro = [f'<span class="sx-tag sx-t0">最新一根</span><span class="sx-tag sx-t1">十字線</span>',
        f'<span><b data-f="date" data-v="{esc(r[dkey])}">{esc(r["start"] + "～" + r["end"] if weekly else r["date"])}</b></span>',
        f'<span>收盤 <b data-f="close" data-v="{_n(r["close"], 2)}">${r["close"]:.2f}</b></span>']
  if has_vix:
    ro.append(f'<span>VIX <b data-f="vix"' + (f' data-v="{_n(r["vix"], 2)}">{r["vix"]:.2f}' if r.get("vix") is not None else f">{NA_VIX}") + "</b></span>")
  ro.append(f'<span>成交量 <b data-f="volume" data-v="{int(vols[-1])}">{esc(shares_zh(vols[-1]))}</b></span>')
  if has_crash:
    ro.append(f'<span>崩跌指數 <b data-f="crash"' + (f' data-v="{_n(r["crash"], 1)}">{r["crash"]:.1f}' if r.get("crash") is not None else f">{NA_CRASH}") + "</b></span>")
  readout = (f'<div class="sx-read" data-crosshair-readout data-pane="{kind}" data-bar="{n - 1}" data-na-vix="{NA_VIX}" data-na-crash="{NA_CRASH}">{"".join(ro)}</div>')

  # ---- legend inside the box: one line for each drawn series, with one key for each color that the
  #      view draws.  A series that is not drawn has no line.  A color that is not drawn has no key.
  drawn = {("s" if r.get("spike") is True else "") + ("u" if r["close"] >= r["open"] else "d") for r in rows}
  plain = tuple(c for c in ("u", "d") if c in drawn)
  marked = tuple(c for c in ("su", "sd") if c in drawn)

  def line(series: str, key: str, text: str, colors: tuple[str, ...] = (), more: str = "") -> str:
    if colors:
      key = "".join(f'<i class="sx-sw sx-c-{c}"></i>' for c in colors)
      more += f' data-colors="{" ".join(colors)}"'
    return f'<li data-legend-series="{series}"{more}>{key}{text}</li>'

  leg = []
  if plain:
    leg.append(line("candles", "", "K 棒（" + {("u", "d"): "綠漲紅跌", ("u",): "綠＝上漲", ("d",): "紅＝下跌"}[plain] + "）", plain))
  if marked:
    leg.append(line("spike-candles", "", "VIX 急升 K 棒（" + {("su", "sd"): "藍漲橘跌", ("su",): "藍＝上漲", ("sd",): "橘＝下跌"}[marked] + "）", marked))
  if ch.get("available"):
    leg.append(line("channel", '<i class="sx-sw sx-c-ch"></i>', "趨勢通道（±2σ）"))
  leg.append(line("last-close", '<i class="sx-ln sx-c-lc"></i>', "最新收盤價"))
  if pf.get("available"):
    parts = tuple(c for c, ok_c in (
        ("pu", any((b.get("up_volume") or 0) > 0 for b in bands)),
        ("pd", any((b.get("down_volume") or 0) > 0 for b in bands)),
        ("bz", (pf.get("busiest") or {}).get("index") is not None),
    ) if ok_c)
    names_pf = {"pu": "綠漲", "pd": "灰跌", "bz": "白最大量"}
    words = "、".join(names_pf[c] for c in parts)
    leg.append(line("profile", '<i class="sx-sw sx-c-pd"></i>', "成交量分布" + (f"（{words}）" if words else ""), parts))
  leg.append(line("volume", "", "成交量（顏色同 K 棒）", plain + marked))
  if has_avg:
    leg.append(line("volume-avg", '<i class="sx-ln sx-c-va"></i>', avg_name))
  if has_vix:
    leg.append(line("vix", '<i class="sx-ln sx-c-vx"></i>', "VIX（獨立刻度）"))
  if has_crash:
    leg.append(line("crash", '<i class="sx-ln sx-c-cr"></i>', "崩跌指數 0–100"))
    for q, ln in enumerate(lg.get("crash_lines") or []):
      leg.append(line("crash-line", f'<i class="sx-ln sx-c-lv{q}"></i>', f'{_n(float(ln.get("value")), 0)} {esc(ln.get("label_zh"))}線', more=f' data-level="{_n(float(ln.get("value")), 1)}"'))
  if drops:
    leg.append(line("crash-drops", '<i class="sx-sw sx-c-mk"></i>', "崩跌起點"))
  legend = f'<ul class="sx-leg" data-chart-legend data-pane="{kind}">{"".join(leg)}</ul>'

  # ---- rule lines under the box: each rule from the data, with what it found in this view.  A line
  #      that says an element is not drawn carries data-legend-note; then one line per missing source.
  def state_of(key: str) -> tuple[str, str]:
    if key == "vix_spike":
      if episodes:
        return "", f"這個視窗有 {len(episodes)} 段，標出最近 {min(len(episodes), MAX_SPIKE_LABELS)} 段"
      return "no-spike", str(spikes.get("text_zh") or lg.get("no_spike_in_view_zh") or "")
    if key == "trend_channel":
      if ch.get("available"):
        return "", str(ch.get("text_zh") or "")
      return "no-channel", str(ch.get("text_zh") or lg.get("no_channel_zh") or "")
    if key.startswith("volume_profile"):
      if not pf.get("available"):
        return "no-profile", str(pf.get("text_zh") or "")
      b = pf["busiest"]
      return "", f"最大量價帶 ${b['price_low']:,.2f}–${b['price_high']:,.2f}，占視窗成交量 {b['share_pct']:.1f}%"
    if key == "weekly_bars":
      return "last-bar", str(v.get("last_bar_text_zh") or "")
    return "", ""

  items: list[str] = []
  said: set[str] = set()
  noted: set[str] = set()
  for key in v.get("rules") or []:
    text = (rules.get(key) or {}).get("text_zh")
    if not text:
      continue
    note, st = state_of(key)
    state = ""
    if st:
      said.add(st)
      noted.add(note)
      warn = ' class="sx-note"' if note in ("no-spike", "no-channel", "no-profile") else ""
      state = f'<b data-rule-state="{esc(key)}"' + (f' data-legend-note="{note}"' if note else "") + f'{warn}>{esc(st)}</b>'
    items.append(f'<li><span data-rule="{esc(key)}">{esc(text)}</span>{state}</li>')
  if drops and lg.get("crash_drop_zh"):
    items.append(f'<li><span data-rule="crash_drop">{esc(lg["crash_drop_zh"])}</span><b data-rule-state="crash_drop">這個視窗有 {len(drops)} 個</b></li>')
  extra = []   # what is not drawn and no rule line has said yet
  if not episodes and "no-spike" not in noted:
    extra.append(("no-spike", str(spikes.get("text_zh") or lg.get("no_spike_in_view_zh") or "")))
  if not ch.get("available") and "no-channel" not in noted:
    extra.append(("no-channel", str(ch.get("text_zh") or lg.get("no_channel_zh") or "")))
  if not pf.get("available") and "no-profile" not in noted:
    extra.append(("no-profile", str(pf.get("text_zh") or "")))
  extra += [("missing", str(m)) for m in v.get("missing_zh") or []]
  for note, text in extra:
    if text and text not in said:
      said.add(text)
      items.append(f'<li class="sx-note" data-legend-note="{note}">{esc(text)}</li>')
  rule_block = f'<ul class="sx-rules" data-chart-rules data-pane="{kind}">{"".join(items)}</ul>'
  return {"plot": plot, "readout": readout, "legend": legend, "rules": rule_block, "bars": n}


# --------------------------------------------------------------------------- #
# evidence strip
# --------------------------------------------------------------------------- #
def _pct0(x: float) -> str:
  return f"{x:.0f}%"


def _pct1(x: float) -> str:
  return f"{x:+.1f}%"


def evidence_html(block: dict) -> str:
  """What SOXL did after past VIX spike episodes and after the crash index rose to 80 or more.

  Each figure sits next to its base rate, its sample count and its sample period.  A count under
  ``small_sample_below`` carries a small-sample label.  One plain line replaces the strip when the
  payload has no long history.
  """
  ev = block.get("evidence") or {}
  if not ev.get("available"):
    return (f'<section class="sx-ev" id="evidence" data-evidence-strip data-available="0"><p class="sx-evx" data-evidence-missing>{esc(ev.get("text_zh") or sx.TEXT_NO_EVIDENCE)}</p></section>')
  default_h = ev.get("default_horizon")
  small_below = ev.get("small_sample_below") or sx.EVIDENCE_SMALL_N
  small_tag = f'<span class="sx-small" data-small-sample="1">小樣本（少於 {esc(small_below)} 次）</span>'

  def figure_bits(f: dict) -> dict:
    base = f.get("base") or {}
    per = f.get("period") or {}
    return {
        "gain": _pct0(f["gain_share_pct"]) if f.get("gain_share_pct") is not None else "", "gain_base": _pct0(base["gain_share_pct"]) if base.get("gain_share_pct") is not None else "",
        "median": _pct1(f["median_ret_pct"]) if f.get("median_ret_pct") is not None else "", "median_base": _pct1(base["median_ret_pct"]) if base.get("median_ret_pct") is not None else "",
        "n": int(f.get("n") or 0), "base_n": int(base.get("n") or 0), "period": f"{per.get('start')} 至 {per.get('end')}" if per.get("start") and per.get("end") else "",
    }

  cards, rows, defs = [], [], []
  for c in ev.get("conditions") or []:
    key = esc(c.get("key"))
    if not c.get("available"):
      cards.append(f'<div class="sx-evc" data-evidence="{key}" data-available="0"><div class="sx-evt">{esc(c.get("label_zh"))}</div><p class="sx-evx" data-evidence-missing>{esc(c.get("text_zh"))}</p></div>')
      continue
    defs.append(f'<li><b>{esc(c.get("label_zh"))}</b>：{esc(c.get("definition_zh"))}' + (f'。{esc(c.get("note_zh"))}' if c.get("note_zh") else "") + "</li>")
    for f in c.get("figures") or []:
      b = figure_bits(f)
      hz = f.get("horizon")
      small = small_tag if f.get("small_sample") else ""
      if b["n"]:
        rows.append(f'<tr data-evidence-row="{key}" data-horizon="{esc(hz)}"><td>{esc(c.get("label_zh"))}</td><td class="mono">{esc(hz)} 日</td>'
                    f'<td class="mono"><span data-f="gain_share">{b["gain"]}</span>（基準 <span data-f="gain_base">{b["gain_base"]}</span>）</td>'
                    f'<td class="mono"><span data-f="median">{b["median"]}</span>（基準 <span data-f="median_base">{b["median_base"]}</span>）</td>'
                    f'<td class="mono"><span data-f="n">{b["n"]}</span> 次{small}</td><td class="mono" data-f="period">{esc(b["period"])}</td></tr>')
      else:
        rows.append(f'<tr data-evidence-row="{key}" data-horizon="{esc(hz)}"><td>{esc(c.get("label_zh"))}</td><td class="mono">{esc(hz)} 日</td><td colspan="2">這個天期還沒有可計算的事件</td>'
                    f'<td class="mono"><span data-f="n">0</span> 次{small}</td><td class="mono" data-f="period">{esc(b["period"])}</td></tr>')
      if hz != default_h:
        continue
      if not b["n"]:
        cards.append(f'<div class="sx-evc" data-evidence="{key}" data-horizon="{esc(hz)}" data-n="0"><div class="sx-evt">{esc(c.get("label_zh"))}之後 {esc(hz)} 個交易日</div>'
                     f'<p class="sx-evx">樣本期間 <span data-f="period">{esc(b["period"])}</span> 內還沒有可計算的事件 {small}</p></div>')
        continue
      cards.append(
          f'<div class="sx-evc" data-evidence="{key}" data-horizon="{esc(hz)}" data-n="{b["n"]}"><div class="sx-evt">{esc(c.get("label_zh"))}之後 {esc(hz)} 個交易日</div>'
          f'<div class="sx-evr"><span class="sx-evk">上漲的比例</span><b data-f="gain_share" data-v="{_n(f["gain_share_pct"], 6)}">{b["gain"]}</b>'
          f'<span class="sx-evb">基準 <span data-f="gain_base" data-v="{_n(f["base"]["gain_share_pct"], 6)}">{b["gain_base"]}</span></span></div>'
          f'<div class="sx-evr"><span class="sx-evk">報酬中位數</span><b data-f="median" data-v="{_n(f["median_ret_pct"], 6)}">{b["median"]}</b>'
          f'<span class="sx-evb">基準 <span data-f="median_base" data-v="{_n(f["base"]["median_ret_pct"], 6)}">{b["median_base"]}</span></span></div>'
          f'<div class="sx-evm"><span>樣本 <span data-f="n">{b["n"]}</span> 次{small}</span><span>基準 <span data-f="base_n">{b["base_n"]:,}</span> 個交易日</span>'
          f'<span>樣本期間 <span data-f="period">{esc(b["period"])}</span></span></div></div>')
  conv = (ev.get("convention") or {}).get("text_zh")
  fold = (f'<details class="sx-fold" data-evidence-fold><summary>{"、".join(str(h) for h in ev.get("horizons") or [])} 個交易日的數字與算法</summary>'
          f'<div class="tbl-wrap"><table class="tbl small nwm sx-evtbl"><thead><tr><th>條件</th><th>天期</th><th>上漲的比例</th><th>報酬中位數</th><th>樣本</th><th>樣本期間</th></tr></thead>'
          f'<tbody>{"".join(rows)}</tbody></table></div><ul class="sx-evd">{"".join(defs)}' + (f"<li><b>算法</b>：{esc(conv)}</li>" if conv else "") + "</ul></details>")
  return (f'<section class="sx-ev" id="evidence" data-evidence-strip data-available="1" aria-label="歷史佐證"><h3 class="sx-evh">過去出現這些情況之後，SOXL 怎麼走'
          f'<small>「基準」是同一段期間每個交易日都照樣買賣的結果</small></h3><div class="sx-evg">{"".join(cards)}</div>{fold}</section>')


# --------------------------------------------------------------------------- #
# the chart: box (R2 item 7) and rule lines
# --------------------------------------------------------------------------- #
def chart_html(block: dict) -> str:
  """The chart box (R2 item 7) with both views, and the rule lines of the legend under it.

  The box holds the view switch, the crosshair read-out, the drawing and one legend line for each
  drawn series.  The rule lines sit outside the box, so the box stays short on a phone.
  """
  if not (block or {}).get("available"):
    text = (block or {}).get("text_zh") or sx.TEXT_NO_BARS
    return (f'<div class="sx-wrap" data-chart data-active-view="daily"><section class="sx" id="chart" data-r2="7" data-r2-name="chart" data-chart-box data-available="0">'
            f'<p class="sx-evx" data-chart-missing>{esc(text)}</p></section></div>')
  views = {k: _view(block, k) for k in ("daily", "weekly") if (block["views"].get(k) or {}).get("available")}
  kinds = list(views)
  first = kinds[0]
  if len(kinds) > 1:
    switch = ('<div class="sx-switch" role="group" aria-label="圖表檢視" data-view-switch-group>'
              + "".join(f'<button type="button" data-view-switch="{k}" aria-pressed="{"true" if k == first else "false"}">{VIEW_NAME[k]}・{VIEW_SPAN[k]}</button>' for k in kinds) + "</div>")
  else:
    switch = f'<span class="sx-only" data-view-only="{first}">{VIEW_NAME[first]}・{VIEW_SPAN[first]}</span>'
  missing = "".join(f'<p class="sx-noview" data-view-missing="{k}">{esc((block["views"].get(k) or {}).get("text_zh"))}</p>'
                    for k in ("daily", "weekly") if k not in views and (block["views"].get(k) or {}).get("text_zh"))
  box = (f'<section class="sx" id="chart" data-r2="7" data-r2-name="chart" data-chart-box data-available="1" aria-label="組合圖">'
         f'<div class="sx-bar"><h2 class="sx-h">組合圖<small>價格、VIX、成交量、崩跌指數對齊同一條日期軸</small></h2>{switch}{"".join(views[k]["readout"] for k in kinds)}</div>{missing}'
         f'{"".join(views[k]["plot"] for k in kinds)}{"".join(views[k]["legend"] for k in kinds)}</section>')
  return (f'<div class="sx-wrap" data-chart data-active-view="{first}" data-views="{" ".join(kinds)}">{box}'
          f'<section class="sx-rulebox" id="chart-rules" data-chart-rulebox aria-label="圖例的規則">{"".join(views[k]["rules"] for k in kinds)}</section></div>')


CSS = """
.sx-wrap{min-width:0}
.sx{background:#0b1120;border:1px solid var(--bd);border-radius:12px;padding:8px 8px 6px}
.sx-bar{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;margin:0 2px 4px}
.sx-h{font-size:.92rem;font-weight:800;white-space:nowrap}.sx-h small{font-size:.72rem;font-weight:500;color:var(--mu);margin-left:8px}
.sx-switch{display:inline-flex}
.sx-switch button{background:#1e293b;color:#cbd5e1;border:1px solid #334155;padding:3px 10px;font:inherit;font-size:.78rem;font-weight:700;cursor:pointer;white-space:nowrap}
.sx-switch button:first-child{border-radius:8px 0 0 8px}.sx-switch button:last-child{border-radius:0 8px 8px 0;border-left:0}
.sx-switch button[aria-pressed="true"]{background:var(--acc);color:#070b14;border-color:var(--acc)}
.sx-only{font-size:.78rem;font-weight:700;color:#cbd5e1;border:1px solid #334155;border-radius:8px;padding:3px 10px;white-space:nowrap}
.sx-noview{font-size:.76rem;color:#fbbf24;margin:0 2px 4px}
.sx-read{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 10px;font-size:.76rem;color:#cbd5e1;font-variant-numeric:tabular-nums;min-width:0}
.sx-read span{white-space:nowrap}.sx-read b{color:#f8fafc;font-weight:700}.sx-tag{color:var(--mu)}
.sx-read.on .sx-t0,.sx-read:not(.on) .sx-t1{display:none}
.sx-wrap[data-active-view="daily"] [data-pane="weekly"],.sx-wrap[data-active-view="weekly"] [data-pane="daily"]{display:none}
.sx-plot{position:relative;padding:0 66px 0 38px}
.sx-in{position:relative;height:480px;touch-action:pan-y;cursor:crosshair}
.sx-svg{position:absolute;left:0;top:0;width:100%;height:100%;display:block}
.sx-svg *{vector-effect:non-scaling-stroke}
.sx-pbg{fill:#0f172a;stroke:none}.sx-grid{stroke:#1e293b;stroke-width:1}.sx-sep{stroke:#1e293b;stroke-width:1}
.sx-lc{stroke:#f8fafc;stroke-width:1;stroke-dasharray:1 3;opacity:.6}
.sx-svg .u{stroke:#10b981;fill:#10b981}.sx-svg .d{stroke:#f43f5e;fill:#f43f5e}.sx-svg .su{stroke:#38bdf8;fill:#38bdf8}.sx-svg .sd{stroke:#f59e0b;fill:#f59e0b}
.sx-svg [data-series="candles"] path:first-child{stroke-width:1;fill:none}.sx-svg [data-series="candles"] path:last-child,.sx-svg [data-series="volume"] rect{stroke:none}
.sx-svg [data-series="volume"] rect{fill-opacity:.62}
.sx-svg polyline{fill:none;stroke-linejoin:round;stroke-linecap:round}
.sx-svg [data-series="volume-avg"]{stroke:#e2e8f0;stroke-width:1.3}.sx-svg [data-series="vix"]{stroke:#c084fc;stroke-width:1.6}.sx-svg [data-series="crash"]{stroke:#fb923c;stroke-width:1.6}
.sx-ca{fill:#fb923c;fill-opacity:.16;stroke:none}
.sx-lv{stroke-width:1;stroke-dasharray:4 3}.sx-lv0{stroke:#eab308}.sx-lv1{stroke:#ef4444}
.sx-chf{fill:#94a3b8;fill-opacity:.09;stroke:none}.sx-chl{stroke:#94a3b8;stroke-width:1}.sx-ch-mid{stroke-dasharray:4 4;opacity:.7}
.sx-pb{fill:#475569;stroke:none}.sx-pu{fill:#10b981;fill-opacity:.5;stroke:none}.sx-pb.sx-bz{fill:#e2e8f0}
.sx-mkl{stroke:#f43f5e;stroke-width:1;stroke-dasharray:2 2;opacity:.85}.sx-mk{fill:#f43f5e;stroke:none}
.sx-l{position:absolute;white-space:nowrap;font-size:11px;line-height:1.2;color:var(--mu);pointer-events:none;transform:translate(var(--tx,0),var(--ty,0))}
.sx-tc{--tx:-50%}.sx-tr{--tx:-100%}.sx-up{--ty:-100%}.sx-mid{--ty:-50%}
.sx-t{color:#e2e8f0;font-weight:700}.sx-dim{color:var(--mu);font-weight:500}
.sx-k{display:inline-block;width:12px;height:0;border-top:2px solid;margin:0 3px 0 8px;vertical-align:middle}
.sx-k-va{border-color:#e2e8f0}.sx-k-lv0{border-color:#eab308;border-top-style:dashed}.sx-k-lv1{border-color:#ef4444;border-top-style:dashed}
.sx-yl{right:calc(100% - 34px);text-align:right;font-size:10px}.sx-yr{left:calc(100% - 62px);font-size:10px}
.sx-lvt0{color:#eab308;font-weight:700}.sx-lvt1{color:#ef4444;font-weight:700}
.sx-last{background:#f8fafc;color:#0b1120;font-weight:800;border-radius:3px;padding:1px 4px;font-variant-numeric:tabular-nums}
.sx-bzl{color:#e2e8f0;line-height:1.15}
.sx-dt{font-size:10.5px}
.sx-sp{color:#f8fafc;font-weight:700;font-size:10.5px;background:rgba(11,17,32,.88);border:1px solid #64748b;border-radius:3px;padding:1px 3px}
.sx-ld{position:absolute;width:0;border-left:1px solid #e2e8f0;margin-left:-.5px;pointer-events:none}
.sx-ah{position:absolute;width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;pointer-events:none}
.sx-aha{border-top:6px solid #e2e8f0;transform:translate(-50%,-100%)}.sx-ahb{border-bottom:6px solid #e2e8f0;transform:translate(-50%,0)}
.sx-n{display:none}
.sx-cl{position:absolute;width:0;border-left:1px solid #f8fafc;margin-left:-.5px;opacity:.75;pointer-events:none;display:none}.sx-cl.on{display:block}
.sx-leg{list-style:none;display:flex;flex-wrap:wrap;gap:2px 12px;margin:5px 2px 0;font-size:.71rem;color:#cbd5e1}
.sx-leg li{display:flex;align-items:center;gap:3px;white-space:nowrap}
.sx-sw{display:inline-block;width:9px;height:9px;border-radius:2px;flex:none}.sx-ln{display:inline-block;width:14px;height:0;border-top:2px solid;flex:none}
.sx-c-u{background:#10b981}.sx-c-d{background:#f43f5e}.sx-c-su{background:#38bdf8}.sx-c-sd{background:#f59e0b}.sx-c-ch{background:rgba(148,163,184,.35);border:1px solid #94a3b8}
.sx-c-lc{border-color:#f8fafc;border-top-style:dotted}.sx-c-pu{background:rgba(16,185,129,.55)}.sx-c-pd{background:#475569}.sx-c-bz{background:#e2e8f0}
.sx-c-mk{background:#f43f5e}.sx-c-va{border-color:#e2e8f0}.sx-c-vx{border-color:#c084fc}.sx-c-cr{border-color:#fb923c}
.sx-c-lv0{border-color:#eab308;border-top-style:dashed}.sx-c-lv1{border-color:#ef4444;border-top-style:dashed}
.sx-rulebox{margin:5px 4px 0;font-size:.72rem;line-height:1.45;color:var(--mu)}
.sx-rules{list-style:none}.sx-rules li{padding-left:.8em;text-indent:-.8em}.sx-rules li::before{content:"・"}
.sx-rules b{display:inline-block;text-indent:0;color:#cbd5e1;font-weight:600;margin-left:.6em}.sx-rules .sx-note{color:#fbbf24}
.sx-ev{margin-top:10px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:10px 12px}
.sx-evh{font-size:.92rem;font-weight:800;margin-bottom:6px}.sx-evh small{font-size:.74rem;color:var(--mu);font-weight:500;margin-left:8px}
.sx-evg{display:grid;grid-template-columns:1fr 1fr;gap:10px}.sx-evg>*{min-width:0}
.sx-evc{background:var(--card2);border:1px solid var(--bd);border-radius:10px;padding:8px 10px}
.sx-evt{font-size:.84rem;font-weight:700;color:#fbbf24;margin-bottom:4px}
.sx-evr{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 8px;font-size:.82rem}.sx-evr>*{white-space:nowrap}
.sx-evr b{font-size:1.15rem;font-family:ui-monospace,Menlo,monospace}.sx-evk{color:#cbd5e1}.sx-evb{color:var(--mu)}
.sx-evm{display:flex;flex-wrap:wrap;gap:0 12px;font-size:.74rem;color:var(--mu);margin-top:4px}.sx-evm>span{white-space:nowrap}
.sx-evx{font-size:.84rem;color:#e2e8f0}
.sx-small{display:inline-block;border:1px solid #f59e0b;color:#fbbf24;border-radius:999px;padding:0 7px;font-size:.7rem;margin-left:6px;white-space:nowrap}
.sx-fold{margin-top:8px}.sx-fold>summary{cursor:pointer;color:var(--acc);font-weight:600;font-size:.8rem;padding:2px 0}
.sx-fold:not([open])>*:not(summary){display:none}
.sx-evtbl th,.sx-evtbl td{white-space:nowrap}
.sx-evd{list-style:none;font-size:.76rem;color:var(--mu);margin-top:6px;line-height:1.5}.sx-evd b{color:#cbd5e1}
@media(min-width:1200px){.sx-in{height:500px}}
@media(max-width:699px){.sx-in{height:440px}.sx-w{display:none}.sx-n{display:block}.sx-h small{display:none}.sx-leg{gap:2px 10px}.sx-evg{grid-template-columns:1fr}}
"""

# The page script: the view switch (kept in the URL hash and in localStorage) and the crosshair.
# It reads attributes and writes textContent, attributes and style only.
JS = """
(function(){
  var W=document.querySelector('[data-chart]'); if(!W) return;
  var KEY='soxl.chartView', views=(W.getAttribute('data-views')||'daily').split(' ');
  function setView(v, keep){
    if(views.indexOf(v)<0) v=views[0];
    W.setAttribute('data-active-view', v);
    W.querySelectorAll('[data-view-switch]').forEach(function(b){ b.setAttribute('aria-pressed', b.getAttribute('data-view-switch')===v?'true':'false'); });
    if(keep){ try{ localStorage.setItem(KEY, v); }catch(e){} try{ history.replaceState(null, '', '#view='+v); }catch(e){} }
  }
  function fromHash(){ var m=/[#&]view=(daily|weekly)\\b/.exec(location.hash||''); return m?m[1]:null; }
  var saved=null; try{ saved=localStorage.getItem(KEY); }catch(e){}
  setView(fromHash()||saved||W.getAttribute('data-active-view'), false);
  W.querySelectorAll('[data-view-switch]').forEach(function(b){ b.addEventListener('click', function(){ setView(b.getAttribute('data-view-switch'), true); }); });
  window.addEventListener('hashchange', function(){ var v=fromHash(); if(v) setView(v, false); });
  function vol(v){ v=Math.max(0, Math.round(+v)); if(v>=1e6) return (Math.floor((v+5e5)/1e6)/100).toFixed(2)+' 億股'; if(v>=1e4) return Math.floor((v+5e3)/1e4)+' 萬股'; return v+' 股'; }
  W.querySelectorAll('[data-cross-target]').forEach(function(tgt){
    var kind=tgt.getAttribute('data-cross-target'), svg=tgt.querySelector('svg'), line=tgt.querySelector('[data-crosshair-line]');
    var ro=W.querySelector('[data-crosshair-readout][data-pane="'+kind+'"]');
    var bars=Array.prototype.slice.call(tgt.querySelectorAll('[data-series="candles"] [data-bar]'));
    if(!svg||!ro||!bars.length) return;
    var last=bars.length-1, step=parseFloat(svg.getAttribute('data-step'));
    function put(name, raw, txt){ var el=ro.querySelector('[data-f="'+name+'"]'); if(!el) return; el.textContent=txt; if(raw===null) el.removeAttribute('data-v'); else el.setAttribute('data-v', raw); }
    function show(i, on){
      var b=bars[i], d=b.getAttribute('data-d'), s=b.getAttribute('data-s'), vx=b.getAttribute('data-vix'), cr=b.getAttribute('data-cr');
      ro.setAttribute('data-bar', i);
      put('date', d, s?s+'～'+d:d);
      put('close', b.getAttribute('data-c'), '$'+(+b.getAttribute('data-c')).toFixed(2));
      put('vix', vx, vx===null?ro.getAttribute('data-na-vix'):(+vx).toFixed(2));
      put('volume', b.getAttribute('data-v'), vol(b.getAttribute('data-v')));
      put('crash', cr, cr===null?ro.getAttribute('data-na-crash'):(+cr).toFixed(1));
      if(on) ro.classList.add('on'); else ro.classList.remove('on');
      if(line){ line.style.left=((i+0.5)*step/10)+'%'; if(on) line.classList.add('on'); else line.classList.remove('on'); }
    }
    function at(cx){ var r=svg.getBoundingClientRect(); if(!r.width) return last; var i=Math.round((cx-r.left)/r.width*1000/step-0.5); return i<0?0:(i>last?last:i); }
    function move(e){ var t=(e.touches&&e.touches.length)?e.touches[0]:e; if(typeof t.clientX!=='number') return; show(at(t.clientX), true); }
    ['pointerdown','pointermove','mousemove','touchstart','touchmove'].forEach(function(n){ tgt.addEventListener(n, move, {passive:true}); });
    function leave(e){ if(e.pointerType&&e.pointerType!=='mouse') return; show(last, false); }
    tgt.addEventListener('pointerleave', leave); tgt.addEventListener('mouseleave', leave);
  });
})();
"""
