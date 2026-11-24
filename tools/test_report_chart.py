#!/usr/bin/env python3
"""Offline tests of the combined chart and the first screen of the page (no network, no browser).

Usage (from the project folder):
  python3 tools/test_report_chart.py                        # current data, history/snapshots, the payloads of git tag `baseline`
  python3 tools/test_report_chart.py some/payload.json ...  # also build the page from these payloads (.json or .json.gz)

What it checks
   1. geometry        the bar count equals the bars in view; candle, volume, VIX and crash index of one bar share one x
   2. stored values   each bar carries the values of the chart data; the read-out starts on the latest bar
   3. markers         the seven first-screen items, the view switch, spike labels with leaders, crash-drop markers,
                      the channel end points, the busiest band, the latest value of each panel
   4. legend          one line per drawn series and none for a missing one; each rule line; the "no spike" and the
                      "no channel" line when they apply
   5. evidence strip  each figure shows its base rate, sample count and sample period; a count under 20 is labelled
   6. fallbacks       no chart block (daily view, one line for the weekly view, one line for the strip), no spike,
                      every session a spike, fewer than 30 bars, no VIX, no crash index, a VIX reading one session old,
                      no bars at all
   7. first screen    rating label, buy answer and watch price equal the feed; outside text is escaped
   8. page            content policy, nothing loaded from another origin, no innerHTML in the page script
   9. every payload   the page builds from each stored payload and passes checks 1 to 5 and the placeholder check

``docs/page_markers.md`` describes the markers these checks read.  Exit code 1 on any failure.
"""
from __future__ import annotations

import copy
import gzip
import json
import math
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from soxl_quant import brief, report_chart as rc, report_page as rp, stress_chart as sx  # noqa: E402

FAILS: list[str] = []
COUNT = [0]
VOID = {"meta", "br", "hr", "img", "input", "link", "col", "wbr", "area", "base", "embed", "source", "track"}
PLACEHOLDERS = [(re.compile(r"\bNone\b"), "None"), (re.compile(r"\bn/a\b", re.I), "n/a"), (re.compile(r"\bnan\b", re.I), "nan"), (re.compile(r"\bnull\b"), "null"),
                (re.compile(r"\bundefined\b"), "undefined"), (re.compile(r"\$(?!\s?[\d,.]*\d)"), "$ with no number"), (re.compile(r"\(\s*\)|（\s*）|\[\s*\]|【\s*】|「\s*」"), "empty brackets")]
WICK = re.compile(r"^M(-?[\d.]+) (-?[\d.]+)V(-?[\d.]+)$")
BODY = re.compile(r"^M(-?[\d.]+) (-?[\d.]+)h([\d.]+)v([\d.]+)h-([\d.]+)z$")
BANNED_JS = ("innerHTML", "outerHTML", "document.write", "insertAdjacentHTML")
R2_NAMES = ["verdict", "data", "price", "watch", "crash", "vix", "chart"]


def check(cond: bool, msg: str, quiet: bool = False) -> bool:
  """Count one check; print it unless it passed quietly."""
  COUNT[0] += 1
  if not cond:
    FAILS.append(msg)
  if not cond or not quiet:
    print(("  ok   " if cond else "  FAIL ") + msg)
  return bool(cond)


# --------------------------------------------------------------------------- #
# a small DOM, enough to read markers
# --------------------------------------------------------------------------- #
class Node:
  __slots__ = ("tag", "attrs", "kids", "parent")

  def __init__(self, tag: str, attrs: dict, parent: "Node | None") -> None:
    self.tag, self.attrs, self.kids, self.parent = tag, attrs, [], parent

  def walk(self):
    yield self
    for k in self.kids:
      if isinstance(k, Node):
        yield from k.walk()

  def find(self, tag: str | None = None, **want) -> list["Node"]:
    """Descendants (and self) with this tag and these attributes; ``data_bar=True`` means "has data-bar"."""
    out = []
    for n in self.walk():
      if tag and n.tag != tag:
        continue
      for k, v in want.items():
        k = k.replace("_", "-")
        if (k not in n.attrs) if v is True else (n.attrs.get(k) != v):
          break
      else:
        out.append(n)
    return out

  def one(self, tag: str | None = None, **want) -> "Node | None":
    got = self.find(tag, **want)
    return got[0] if len(got) == 1 else None

  def children(self, tag: str | None = None) -> list["Node"]:
    return [k for k in self.kids if isinstance(k, Node) and (tag is None or k.tag == tag)]

  def text(self) -> str:
    return "".join(k if isinstance(k, str) else ("" if k.tag in ("script", "style") else k.text()) for k in self.kids)

  def has_class(self, name: str) -> bool:
    return name in (self.attrs.get("class") or "").split()


class Dom(HTMLParser):
  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self.root = Node("#root", {}, None)
    self.cur = self.root

  def handle_starttag(self, tag, attrs):
    n = Node(tag, dict(attrs), self.cur)
    self.cur.kids.append(n)
    if tag not in VOID:
      self.cur = n

  def handle_startendtag(self, tag, attrs):
    self.cur.kids.append(Node(tag, dict(attrs), self.cur))

  def handle_endtag(self, tag):
    n = self.cur
    while n is not None and n.tag != tag:
      n = n.parent
    if n is not None and n.parent is not None:
      self.cur = n.parent

  def handle_data(self, data):
    self.cur.kids.append(data)


def parse(text: str) -> Node:
  d = Dom()
  d.feed(text)
  d.close()
  return d.root


def same(attr: str | None, value, nd: int) -> bool:
  """An attribute against a stored number rounded to ``nd`` decimals; a missing value needs a missing attribute."""
  if value is None:
    return attr is None
  return attr is not None and abs(float(attr) - round(float(value), nd)) < 1e-9


def points(n: Node) -> list[tuple[float, float]]:
  return [(float(a), float(b)) for a, b in (pt.split(",") for pt in (n.attrs.get("points") or "").split())]


def left_units(n: Node) -> float:
  """``left:NN%`` of a label, in viewBox units."""
  m = re.search(r"left:(-?[\d.]+)%", n.attrs.get("style") or "")
  return float(m.group(1)) * 10.0 if m else float("nan")


# --------------------------------------------------------------------------- #
# one view: geometry, stored values, markers, legend
# --------------------------------------------------------------------------- #
def check_view(root: Node, block: dict, kind: str, tag: str, quiet: bool, episodes: list | None) -> None:
  v = block["views"][kind]
  rows = sx.view_bars(block, kind)
  n = len(rows)
  weekly = kind == "weekly"
  dkey = "end" if weekly else "date"
  ser = v.get("series") or {}
  svg = root.one("svg", data_view_svg=kind)
  inner = root.one("div", data_cross_target=kind)
  if not check(svg is not None and inner is not None and inner.parent is not None, f"{tag}: one drawing with its crosshair target", quiet):
    return
  pane = inner.parent
  step = float(svg.attrs["data-step"])
  cg = svg.one("g", data_series="candles")
  bars = cg.children("g") if cg else []
  if not check(len(bars) == n == int(svg.attrs["data-n"]) and [b.attrs.get("data-bar") for b in bars] == [str(i) for i in range(n)],
               f"{tag}: {len(bars)} candles = {n} bars in view, numbered in order", quiet):
    return

  # ---- 1. geometry: every series of bar i at x = (i + 0.5) * step
  wick_x: list[float] = []
  dev = 0.0
  for i, g in enumerate(bars):
    paths = g.children("path")
    mw = WICK.match(paths[0].attrs.get("d", "")) if len(paths) == 2 else None
    mb = BODY.match(paths[1].attrs.get("d", "")) if len(paths) == 2 else None
    if not (mw and mb):
      check(False, f"{tag}: bar {i} is not a wick path and a body path", quiet)
      return
    x = float(mw.group(1))
    wick_x.append(x)
    dev = max(dev, abs(x - (i + 0.5) * step), abs(float(mb.group(1)) + float(mb.group(3)) / 2 - x))
  vg = svg.one("g", data_series="volume")
  vr = vg.children("rect") if vg else []
  if check(len(vr) == n, f"{tag}: {len(vr)} volume bars = {n} bars in view", quiet):
    dev = max([dev] + [abs(float(r.attrs["x"]) + float(r.attrs["width"]) / 2 - wick_x[i]) for i, r in enumerate(vr)])
  for series, key, flag in (("vix", "vix", "vix"), ("crash", "crash", "crash"), ("volume-avg", "vol_avg20w" if weekly else "vol_avg20", "volume_avg")):
    expect = [i for i, r in enumerate(rows) if r.get(key) is not None] if ser.get(flag) else []
    drawn: list[int] | None = []
    for pl in svg.find("polyline", data_series=series):
      first, cnt = int(pl.attrs["data-first"]), int(pl.attrs["data-n"])
      pts = points(pl)[:1] if cnt == 1 else points(pl)
      if len(pts) != cnt or drawn is None:
        drawn = None
        break
      drawn += list(range(first, first + cnt))
      dev = max([dev] + [abs(pt[0] - wick_x[i]) for pt, i in zip(pts, range(first, first + cnt))])
    check(drawn == expect, f"{tag}: the {series} line has one vertex for each of the {len(expect)} bars that have a value", quiet)
  check(dev <= 0.5, f"{tag}: candle, volume, average, VIX and crash index of one bar share one x (largest gap {dev:.3f} of 1000 units; the drawing is under 1000 px wide)", quiet)

  # ---- 2. stored values
  bad = []
  for i, (g, r) in enumerate(zip(bars, rows)):
    a = g.attrs
    cls = a.get("class") or ""
    ok = (a.get("data-d") == r[dkey] and same(a.get("data-c"), r["close"], 2) and a.get("data-v") == str(int(r.get("volume") or 0))
          and same(a.get("data-vix"), r.get("vix"), 2) and same(a.get("data-cr"), r.get("crash"), 1)
          and (not weekly or (a.get("data-s") == r["start"] and ("data-partial" in a) == bool(r.get("partial"))))
          and cls in ("u", "d", "su", "sd") and cls.startswith("s") == (r.get("spike") is True) and cls.endswith("u") == (r["close"] >= r["open"]))
    if not ok:
      bad.append(i)
  check(not bad, f"{tag}: each bar stores the date, close, volume, VIX and crash index of the chart data; spike bars have their own class" + (f" (bad bars {bad[:6]})" if bad else ""), quiet)
  last = rows[-1]
  ro = root.one("div", data_crosshair_readout=True, data_pane=kind)
  f = {x.attrs["data-f"]: x for x in ro.find(data_f=True)} if ro is not None else {}
  ok = (ro is not None and ro.attrs.get("data-bar") == str(n - 1) and {"date", "close", "volume"} <= set(f) and f["date"].attrs.get("data-v") == last[dkey]
        and same(f["close"].attrs.get("data-v"), last["close"], 2) and f["volume"].attrs.get("data-v") == str(int(last.get("volume") or 0))
        and ("vix" in f) == bool(ser.get("vix")) and ("crash" in f) == bool(ser.get("crash"))
        and ("vix" not in f or same(f["vix"].attrs.get("data-v"), last.get("vix"), 2)) and ("crash" not in f or same(f["crash"].attrs.get("data-v"), last.get("crash"), 1)))
  check(ok, f"{tag}: the read-out starts on the latest bar with its date, close, volume" + (", VIX" if ser.get("vix") else "") + (", crash index" if ser.get("crash") else ""), quiet)

  # ---- 3. markers
  eps = (v.get("spikes") or {}).get("episodes") or []
  want = list(range(len(eps)))[-rc.MAX_SPIKE_LABELS:]
  ok = True
  for lay in ("sx-w", "sx-n"):
    labs = [x for x in inner.find("span", data_spike_label=True) if x.has_class(lay)]
    leads = [x for x in inner.find("i", data_spike_leader=True) if x.has_class(lay)]
    ok = ok and sorted(int(x.attrs["data-spike-label"]) for x in labs) == want and sorted(int(x.attrs["data-spike-leader"]) for x in leads) == want
    for x in labs:
      e = eps[int(x.attrs["data-spike-label"])]
      ok = ok and x.attrs.get("data-bar") == str(e["anchor_bar"]) and x.attrs.get("data-start") == e["start"] and x.attrs.get("data-end") == e["end"] and x.text().strip() == block["legend"]["spike_label_zh"]
    for x in leads:
      a = eps[int(x.attrs["data-spike-leader"])]["anchor_bar"]
      ok = ok and x.attrs.get("data-bar") == str(a) and abs(left_units(x) - wick_x[a]) <= 0.11
  check(ok, f"{tag}: {len(want)} spike label(s) for the latest {len(want)} of {len(eps)} episode(s), each with a leader at its candle, in both label layouts", quiet)
  drops = v.get("crash_drops") or []
  marks = svg.find("line", data_marker="crash-drop")
  ok = ([(m.attrs.get("data-date"), m.attrs.get("data-bar")) for m in marks] == [(d["date"], str(d["bar"])) for d in drops]
        and all(abs(float(m.attrs["x1"]) - wick_x[int(m.attrs["data-bar"])]) <= 0.06 for m in marks))
  if episodes is not None:
    inside = sorted(str(e.get("date")) for e in episodes if isinstance(e, dict) and str(v.get("start")) <= str(e.get("date")) <= str(v.get("end")))
    ok = ok and sorted(m.attrs.get("data-date") for m in marks) == inside
  check(ok, f"{tag}: {len(marks)} crash-drop marker(s), each at its bar" + ("" if episodes is None else ", equal to the event-study dates inside the view"), quiet)
  ch = v.get("channel") or {}
  g = svg.one("g", data_series="channel")
  if ch.get("available"):
    y0, y1, top, bot = (float(svg.attrs[k]) for k in ("data-price-y0", "data-price-y1", "data-price-top", "data-price-bottom"))
    ok, worst = g is not None and svg.attrs.get("data-price-scale") == "log", 0.0
    for key in ("upper", "mid", "lower"):
      ln = g.one("line", data_line=key) if g is not None else None
      if ln is None:
        ok = False
        break
      ok = ok and same(ln.attrs.get("data-p0"), ch[key][0], 4) and same(ln.attrs.get("data-p1"), ch[key][1], 4) and abs(float(ln.attrs["x1"]) - wick_x[0]) <= 0.06 and abs(float(ln.attrs["x2"]) - wick_x[-1]) <= 0.06
      for y, price in ((ln.attrs["y1"], ch[key][0]), (ln.attrs["y2"], ch[key][1])):
        drawn_price = math.exp(math.log(top) - (float(y) - y0) / (y1 - y0) * (math.log(top) - math.log(bot)))
        worst = max(worst, abs(drawn_price / price - 1.0) * 100.0)
    check(ok and worst <= 0.5, f"{tag}: the channel runs from the first to the last bar; its drawn end points are within {worst:.3f}% of the stored prices", quiet)
  else:
    check(g is None, f"{tag}: no channel is drawn", quiet)
  pf = v.get("profile") or {}
  pg = svg.one("g", data_series="profile")
  lab = pane.find("span", data_busiest_label=True)
  if pf.get("available"):
    stored = sx.table_dicts(pf["bands"])
    bands = pg.find("rect", data_band=True) if pg is not None else []
    busy = [r for r in bands if r.attrs.get("data-busiest") == "1"]
    bz = pf["busiest"]
    ok = (len(bands) == len(stored) and len(busy) == 1 and len(lab) == 1 and busy[0].attrs.get("data-band") == str(bz["index"])
          and all(same(x.attrs.get("data-lo"), bz["price_low"], 4) and same(x.attrs.get("data-hi"), bz["price_high"], 4) for x in (busy[0], lab[0]))
          and all(int(r.attrs["data-vol"]) == int(b["total_volume"]) and same(r.attrs.get("data-lo"), b["price_low"], 4) for r, b in zip(bands, stored))
          and float(busy[0].attrs["width"]) >= max(float(r.attrs["width"]) for r in bands) - 1e-9
          and all(float(r.attrs["x"]) >= rc.BARS_X1 for r in bands))
    check(ok, f"{tag}: {len(bands)} profile bands right of the bars; the busiest one is marked and labelled ${bz['price_low']:.2f} to ${bz['price_high']:.2f}", quiet)
  else:
    check(pg is None and not lab, f"{tag}: no volume profile is drawn", quiet)
  lat = {x.attrs["data-latest"]: x for x in pane.find("span", data_latest=True)}
  ok = set(lat) == {"price", "volume"} | ({"vix"} if ser.get("vix") else set()) | ({"crash"} if ser.get("crash") else set())
  ok = ok and same(lat["price"].attrs.get("data-v"), last["close"], 2) and lat["volume"].attrs.get("data-v") == str(int(last.get("volume") or 0))
  for key, nd in (("vix", 2), ("crash", 1)):
    if ok and key in lat:
      j = max(i for i, r in enumerate(rows) if r.get(key) is not None)
      ok = lat[key].attrs.get("data-bar") == str(j) and same(lat[key].attrs.get("data-v"), rows[j][key], nd)
  check(ok, f"{tag}: each panel carries its latest value ({', '.join(sorted(lat))})", quiet)
  if ser.get("crash"):
    levels = sorted(float(x.attrs["data-level"]) for x in svg.find("line", data_level=True))
    check(levels == sorted(float(x["value"]) for x in block["legend"]["crash_lines"]) == [60.0, 80.0], f"{tag}: the crash index panel has its lines at 60 and 80", quiet)

  # ---- 4. legend and rule lines
  leg = root.one("ul", data_chart_legend=True, data_pane=kind)
  got = [li.attrs["data-legend-series"] for li in leg.find("li", data_legend_series=True)] if leg is not None else None
  drawn_c = {("s" if r.get("spike") is True else "") + ("u" if r["close"] >= r["open"] else "d") for r in rows}
  has_plain = any(c in drawn_c for c in ("u", "d"))
  has_marked = any(c in drawn_c for c in ("su", "sd"))
  n_clines = len(block.get("legend", {}).get("crash_lines") or []) if ser.get("crash") else 0
  want_series = ((["candles"] if has_plain else []) + (["spike-candles"] if has_marked else []) + (["channel"] if ch.get("available") else [])
                 + ["last-close"] + (["profile"] if pf.get("available") else []) + ["volume"]
                 + (["volume-avg"] if ser.get("volume_avg") else []) + (["vix"] if ser.get("vix") else [])
                 + (["crash"] + ["crash-line"] * n_clines if ser.get("crash") else []) + (["crash-drops"] if drops else []))
  check(got == want_series and leg is not None and len(leg.children("li")) == len(want_series), f"{tag}: the legend has one line for each drawn series and no other line ({', '.join(want_series)})", quiet)
  rl = root.one("ul", data_chart_rules=True, data_pane=kind)
  if check(rl is not None, f"{tag}: the rule lines exist", quiet):
    rules = {s.attrs["data-rule"]: s.text() for s in rl.find("span", data_rule=True)}
    check(all(rules.get(k) == block["rules"][k]["text_zh"] for k in v["rules"]), f"{tag}: each rule line prints the rule text of the data ({', '.join(v['rules'])})", quiet)
    notes = {x.attrs["data-legend-note"]: x.text().strip() for x in rl.find(data_legend_note=True)}
    check(("no-spike" in notes) == (not eps) and ("no-channel" in notes) == (not ch.get("available")) and ("no-profile" in notes) == (not pf.get("available")) and all(notes.values()),
          f"{tag}: the legend says so when there is " + ("no spike" if not eps else "a spike") + " and " + ("no channel" if not ch.get("available") else "a channel")
          + (f" → {notes.get('no-spike', '')} / {notes.get('no-channel', '')}" if (not eps or not ch.get("available")) and not quiet else ""), quiet)
    if weekly:
      check(notes.get("last-bar") == v.get("last_bar_text_zh") and bool(notes.get("last-bar")), f"{tag}: the weekly view states whether its last bar is a partial week" + ("" if quiet else f" → {notes.get('last-bar')}"), quiet)
    miss = [x.text().strip() for x in rl.find(data_legend_note="missing")]
    check(all(m in rl.text() for m in v.get("missing_zh") or []) and len(miss) == len(set(miss)), f"{tag}: each missing source is named once ({len(v.get('missing_zh') or [])})", quiet)


def check_evidence(strip: Node | None, ev: dict, tag: str, quiet: bool) -> int:
  """Each figure shows its base rate, its sample count and its sample period; a count under 20 is labelled.  Returns the number of labels."""
  if not check(strip is not None and strip.attrs.get("data-available") == "1", f"{tag}: the evidence strip is shown", quiet):
    return 0
  below = ev.get("small_sample_below") or sx.EVIDENCE_SMALL_N
  shown, small_n, ok = 0, 0, below == 20
  for c in ev.get("conditions") or []:
    if not c.get("available"):
      ok = ok and len(strip.find("div", data_evidence=c["key"], data_available="0")) == 1
      continue
    for fig in c.get("figures") or []:
      hz, n = str(fig["horizon"]), int(fig.get("n") or 0)
      per = fig.get("period") or {}
      boxes = strip.find("tr", data_evidence_row=c["key"], data_horizon=hz) + strip.find("div", data_evidence=c["key"], data_horizon=hz)
      ok = ok and len(boxes) == (2 if fig["horizon"] == ev.get("default_horizon") else 1) and bool(fig.get("small_sample")) == (n < below)
      for box in boxes:
        fld = {x.attrs["data-f"]: x.text().strip() for x in box.find(data_f=True)}
        shown += 1
        small = len(box.find("span", data_small_sample="1"))
        small_n += small
        ok = ok and fld.get("n") == str(n) and small == (1 if n < below else 0) and str(per.get("start")) in fld.get("period", "") and str(per.get("end")) in fld.get("period", "")
        if n:
          ok = (ok and fld.get("gain_share") == f"{fig['gain_share_pct']:.0f}%" and fld.get("gain_base") == f"{fig['base']['gain_share_pct']:.0f}%"
                and fld.get("median") == f"{fig['median_ret_pct']:+.1f}%" and fld.get("median_base") == f"{fig['base']['median_ret_pct']:+.1f}%")
  check(ok and shown > 0, f"{tag}: {shown} evidence figure(s), each with its base rate, sample count and sample period; {small_n} carry the small-sample label (count under {below})", quiet)
  return small_n


def check_page(text: str, payload: dict, tag: str, quiet: bool) -> Node:
  """Checks 1 to 5 and the placeholder check on one built page."""
  root = parse(text)
  block = sx.for_payload(payload)
  items = root.find(data_r2=True)
  check([(x.attrs.get("data-r2"), x.attrs.get("data-r2-name")) for x in sorted(items, key=lambda x: x.attrs.get("data-r2") or "")] == [(str(i + 1), nm) for i, nm in enumerate(R2_NAMES)],
        f"{tag}: the seven first-screen items are marked once each ({', '.join(R2_NAMES)})", quiet)
  header, first = root.one("header"), root.one("main", data_first_screen=True)
  shown = (header.text() if header is not None else "") + " " + (first.text() if first is not None else "")
  found = [name for rx, name in PLACEHOLDERS if rx.search(shown)]
  check(header is not None and first is not None and not found, f"{tag}: no placeholder token in the first screen" + (f" (found {found})" if found else ""), quiet)
  check(root.text().count(brief.DISCLAIMER) == 1, f"{tag}: the disclaimer of the feed is on the page, once", quiet)
  wrap = root.one("div", data_chart=True)
  box = root.one("section", data_chart_box=True)
  if not block.get("available"):
    check(box is not None and box.attrs.get("data-available") == "0" and len(box.find("p", data_chart_missing=True)) == 1, f"{tag}: no bars → one plain line in the chart box", quiet)
    return root
  kinds = [k for k in ("daily", "weekly") if (block["views"].get(k) or {}).get("available")]
  ok = wrap is not None and (wrap.attrs.get("data-views") or "").split() == kinds and wrap.attrs.get("data-active-view") == kinds[0] and box is not None and box.attrs.get("data-r2") == "7"
  buttons = root.find("button", data_view_switch=True)
  if len(kinds) == 2:
    ok = ok and [(b.attrs["data-view-switch"], b.attrs.get("aria-pressed")) for b in buttons] == [("daily", "true"), ("weekly", "false")]
  else:
    lines = root.find("p", data_view_missing=True)
    absent = [k for k in ("daily", "weekly") if k not in kinds]
    ok = (ok and not buttons and root.one("span", data_view_only=kinds[0]) is not None and [x.attrs["data-view-missing"] for x in lines] == absent
          and all(x.text().strip() == block["views"][x.attrs["data-view-missing"]]["text_zh"] for x in lines))
  check(ok, f"{tag}: the chart offers {' and '.join(kinds)}" + ("" if len(kinds) == 2 else "; one plain line replaces the other view"), quiet)
  episodes = ((payload.get("early_warning") or {}).get("event_study") or {}).get("episodes")
  for k in kinds:
    check_view(root, block, k, f"{tag} {k}", quiet, episodes if isinstance(episodes, list) else None)
  ev = block.get("evidence") or {}
  strip = root.one("section", data_evidence_strip=True)
  if ev.get("available"):
    check_evidence(strip, ev, tag, quiet)
  else:
    lines = strip.find("p", data_evidence_missing=True) if strip is not None else []
    check(strip is not None and strip.attrs.get("data-available") == "0" and len(lines) == 1 and lines[0].text().strip() == (ev.get("text_zh") or sx.TEXT_NO_EVIDENCE) and not strip.find("div", data_evidence=True),
          f"{tag}: no long history → one plain line replaces the evidence strip", quiet)
  return root


# --------------------------------------------------------------------------- #
# payloads
# --------------------------------------------------------------------------- #
def load(path: Path) -> dict:
  raw = path.read_bytes()
  return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def baseline_payloads() -> list[tuple[str, dict]]:
  """The data file and the snapshots of git tag ``baseline``; [] when git or the tag is missing."""
  try:
    ls = subprocess.run(["git", "ls-tree", "-r", "--name-only", "baseline", "--", "soxl_analysis_data.json", "history/snapshots"], cwd=BASE, capture_output=True, text=True, timeout=30)
    if ls.returncode != 0:
      return []
    out = []
    for name in sorted(x for x in ls.stdout.split("\n") if x.endswith((".json", ".json.gz"))):
      raw = subprocess.run(["git", "show", f"baseline:{name}"], cwd=BASE, capture_output=True, timeout=30).stdout
      out.append((f"baseline:{name}", json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)))
    return out
  except (OSError, subprocess.SubprocessError, ValueError):
    return []


def without_block(p: dict) -> dict:
  q = copy.deepcopy(p)
  q.pop("stress_chart", None)
  return q


def view_of(p: dict, kind: str = "daily") -> dict:
  return sx.for_payload(p)["views"][kind]


# --------------------------------------------------------------------------- #
# the tests
# --------------------------------------------------------------------------- #
def test_current(p: dict) -> Node:
  print("1-5. the page of the current data")
  text = rp.render(p)
  root = check_page(text, p, "current", quiet=False)
  blk = sx.for_payload(p)
  check(blk.get("source") == "pipeline" and all(blk["views"][k]["available"] for k in ("daily", "weekly")), "current: the data carries the chart block with both views")
  check(110 <= len(sx.view_bars(blk, "daily")) <= 130 and 96 <= len(sx.view_bars(blk, "weekly")) <= 110, f"current: the daily view has {len(sx.view_bars(blk, 'daily'))} sessions and the weekly view {len(sx.view_bars(blk, 'weekly'))} weeks")
  return root


def test_small_sample(p: dict) -> None:
  print("5. evidence strip with a small sample")
  ev = copy.deepcopy(sx.for_payload(p).get("evidence") or {})
  if not ev.get("available"):
    print("  skip the current data has no evidence strip")
    return
  c = next(c for c in ev["conditions"] if c.get("available"))
  fig = next(f for f in c["figures"] if f["horizon"] == ev["default_horizon"])
  other = next(f for f in c["figures"] if f["horizon"] != ev["default_horizon"])
  fig["n"], fig["small_sample"] = 7, True
  other["n"], other["small_sample"] = 0, True
  strip = parse(rc.evidence_html({"evidence": ev})).one("section", data_evidence_strip=True)
  labels = check_evidence(strip, ev, "small sample", quiet=False)
  check(labels == 3, f"a count of 7 carries the small-sample label on its card and on its table row, a count of 0 on its row ({labels} labels)")


def test_fallbacks(p: dict) -> None:
  print("6. fallbacks")
  bare = without_block(p)
  check_page(rp.render(bare), bare, "no chart block", quiet=False)
  hist = lambda q: (q["sentiment"].get("vix") or {}).get("history") or []  # noqa: E731

  flat = without_block(p)
  for r in hist(flat):
    r["vix"] = 18.0
  check(not view_of(flat)["spikes"]["episodes"], "no spike: a flat VIX history marks no session")
  root = check_page(rp.render(flat), flat, "no spike", quiet=True)
  note = root.find(data_legend_note="no-spike")
  check(len(note) == 1 and not root.find("span", data_spike_label=True) and not root.find("li", data_legend_series="spike-candles") and not [g for g in root.find("g", data_bar=True) if (g.attrs.get("class") or "").startswith("s")],
        f"no spike: the legend says so and nothing is marked → {note[0].text().strip() if note else ''}")
  fs = rp.first_screen(flat)
  check(fs["spike"] is False and "不是" in fs["spike_text"], f"no spike: the first screen says → {fs['spike_text']}")

  rise = without_block(p)
  for i, r in enumerate(hist(rise)):
    r["vix"] = round(9.0 * 1.012 ** i, 2)
  rv = view_of(rise)
  rows = sx.view_bars(sx.for_payload(rise), "daily")
  check(all(r.get("spike") is True for r in rows) and len(rv["spikes"]["episodes"]) == 1, f"every session a spike: all {len(rows)} bars are marked, one episode")
  root = check_page(rp.render(rise), rise, "every session a spike", quiet=True)
  check(len([x for x in root.find("span", data_spike_label=True) if x.has_class("sx-w")]) == 1, "every session a spike: one label with one leader")

  tiny = without_block(p)
  tiny["technicals"]["chart_series"] = tiny["technicals"]["chart_series"][-12:]
  check(view_of(tiny)["channel"].get("available") is False, "fewer than 30 bars: the rule yields no channel")
  root = check_page(rp.render(tiny), tiny, "fewer than 30 bars", quiet=True)
  note = root.find(data_legend_note="no-channel")
  check(len(note) == 1 and not root.find("g", data_series="channel") and not root.find("li", data_legend_series="channel"), f"fewer than 30 bars: the legend says so → {note[0].text().strip() if note else ''}")

  novix = without_block(p)
  novix["sentiment"]["vix"] = {"available": False}
  root = check_page(rp.render(novix), novix, "no VIX", quiet=True)
  check(not root.find("polyline", data_series="vix") and not root.find("li", data_legend_series="vix") and not root.find("span", data_panel_title="vix") and not root.one("div", data_crosshair_readout=True).find(data_f="vix")
        and len(root.find(data_legend_note=True)) >= 1, "no VIX: no VIX panel, no VIX legend line, no VIX field in the read-out; the legend names the missing source")
  fs = rp.first_screen(novix)
  state = root.one(None, data_f="spike-state")
  check(fs["spike"] is None and state is not None and state.attrs.get("data-v") == "unknown", f"no VIX: the first screen says → {state.text().strip() if state is not None else ''}")

  nocrash = without_block(p)
  nocrash["early_warning"]["chart"] = []
  root = check_page(rp.render(nocrash), nocrash, "no crash index", quiet=True)
  drops = root.one("g", data_series="crash-drops")
  check(not root.find("polyline", data_series="crash") and not root.find("li", data_legend_series="crash") and not root.find("line", data_level=True) and (drops is None or drops.attrs.get("data-panel") != "crash"),
        "no crash index: no crash panel and no crash legend line; the crash-drop markers move to the lowest panel")

  stale = without_block(p)
  h = hist(stale)
  last_date = stale["technicals"]["chart_series"][-1]["date"]
  stale["sentiment"]["vix"]["history"] = [r for r in h if r.get("date") != last_date]
  fs = rp.first_screen(stale)
  root = check_page(rp.render(stale), stale, "VIX one session old", quiet=True)
  ro = root.one("div", data_crosshair_readout=True)
  vx = ro.one(None, data_f="vix") if ro is not None else None
  check(fs["vix"] is not None and fs["vix_same_session"] is False and fs["spike"] is None and fs["vix_date"] < last_date and len(root.find("small", data_f="vix-date")) == 1,
        f"VIX one session old: the first screen shows the reading of {fs['vix_date']} with its date and no spike verdict → {fs['spike_text']}")
  check(vx is not None and "data-v" not in vx.attrs and vx.text().strip() == rc.NA_VIX, f"VIX one session old: the read-out of the latest bar says → {vx.text().strip() if vx is not None else ''}")

  none = sx.for_payload({})
  html_ = rc.chart_html(none) + rc.evidence_html(none)
  root = parse(html_)
  check(none["available"] is False and len(root.find("p", data_chart_missing=True)) == 1 and root.one("section", data_r2="7") is not None and len(root.find("p", data_evidence_missing=True)) == 1 and not root.find("svg"),
        f"no bars: one plain line in the chart box and one for the strip → {root.find('p', data_chart_missing=True)[0].text() if root.find('p', data_chart_missing=True) else ''}")
  fs = rp.first_screen({})
  cards = parse(rp.first_screen_cards(fs) + rp.first_screen_data_line(fs))
  found = [name for rx, name in PLACEHOLDERS if rx.search(cards.text())]
  check(not found and len(cards.find(data_r2=True)) == 6, "no bars: the six readouts still build from an empty payload, with words in place of every missing value")


def test_first_screen(p: dict, root: Node) -> None:
  print("7. first screen")
  feed_path = BASE / "feed" / "latest.json"
  feed = json.loads(feed_path.read_text(encoding="utf-8")) if feed_path.exists() else {}
  zones = [z for z in (root.one("section", id="readouts"), root.one("header")) if z is not None]

  def field(name: str) -> Node | None:
    """A first-screen field.  The crosshair read-out reuses some names (close, vix, volume), so look inside the readouts only."""
    got = [x for z in zones for x in z.find(data_f=name)]
    return got[0] if len(got) == 1 else None

  def val(name: str) -> str | None:
    return field(name).text().strip() if field(name) is not None else None

  if feed.get("data_as_of") == p.get("data_as_of"):
    buy, watch = (feed.get("beginner") or {}).get("buy") or {}, (feed.get("beginner") or {}).get("watch") or {}
    check(val("rating-label") == (feed.get("verdict") or {}).get("label") and val("buy-answer") == buy.get("answer"), f"the rating label and the buy answer equal feed/latest.json → {val('rating-label')} ｜ {val('buy-answer')}")
    wp = field("watch-price")
    check((wp is not None and same(wp.attrs.get("data-v"), watch.get("price"), 2) and val("watch-kind") == watch.get("label")) or (wp is None and not watch.get("price")), f"the level to watch and its kind equal the feed → {val('watch-price')} ｜ {val('watch-kind')}")
  else:
    print(f"  skip the feed is for {feed.get('data_as_of')}, the data file for {p.get('data_as_of')}")
  tech, ews = p.get("technicals") or {}, (p.get("early_warning") or {}).get("today") or {}
  lt = sx.for_payload(p).get("latest") or {}
  close, ret, score = field("close"), field("ret-1d"), field("crash-score")
  check(close is not None and same(close.attrs.get("data-v"), tech.get("close"), 2) and ret is not None and same(ret.attrs.get("data-v"), tech.get("ret_1d"), 2)
        and score is not None and same(score.attrs.get("data-v"), ews.get("score"), 1) and val("crash-zone") == str(ews.get("zone") or "").split(" (")[0].split("；")[0].strip()
        and val("data-date") == p.get("data_as_of"), f"close, 1-day change, crash index, zone and data date equal the data → {val('close')} {val('ret-1d')} ｜ {val('crash-score')} {val('crash-zone')} ｜ {val('data-date')}")
  vix, state, vol = field("vix"), field("spike-state"), field("volume-vs-avg")
  lv = lt.get("vix") or {}
  want_state = "unknown" if not lv.get("same_session") or lv.get("spike") is None else ("spike" if lv.get("spike") else "no-spike")
  check(vix is not None and same(vix.attrs.get("data-v"), lv.get("close"), 2) and state is not None and state.attrs.get("data-v") == want_state and vol is not None and vol.attrs.get("data-v") == lt.get("volume_vs_avg"),
        f"VIX, its spike state and volume against its average equal the chart data → {val('vix')} {val('spike-state')} ｜ {root.one('div', data_readout='volume').text().strip() if root.one('div', data_readout='volume') is not None else ''}")

  evil = '<script>alert(1)</script><img src=x onerror=alert(2)>"\'&'
  q = copy.deepcopy(p)
  q["playbook"]["beginner"]["verdict"] = evil
  q["data_status"] = dict(q.get("data_status") or {}, label=evil)
  q["data_as_of"] = evil
  q["warnings"] = [evil + ": boom", "options: " + evil]
  blk = q["stress_chart"]
  for k in blk["rules"]:
    blk["rules"][k]["text_zh"] = evil
  blk["legend"]["spike_label_zh"] = evil
  blk["legend"]["crash_drop_zh"] = evil
  for k in ("daily", "weekly"):
    blk["views"][k]["channel"]["text_zh"] = evil
    blk["views"][k]["last_bar_text_zh"] = evil
  for c in blk["evidence"]["conditions"]:
    c["label_zh"] = c["definition_zh"] = evil
  page = parse(rp.render(q))
  zone = [page.one("header"), page.one("main", data_first_screen=True), page.one("section", data_evidence_strip=True)]
  made = [n.tag for z in zone if z is not None for n in z.walk() if n.tag in ("script", "img", "iframe", "object") or any(a.startswith("on") for a in n.attrs)]
  check(all(z is not None for z in zone) and not made and evil in zone[0].text() and evil in zone[1].text() and evil in zone[2].text() and "其他來源" in zone[0].text(),
        "markup inside the rating label, the data status, the data date, a warning, the rule lines and the strip labels shows as text and creates no element and no handler")


def test_page(p: dict) -> None:
  print("8. page")
  text = rp.render(p)
  root = parse(text)
  csp = [m.attrs.get("content") or "" for m in root.find("meta") if (m.attrs.get("http-equiv") or "").lower() == "content-security-policy"]
  need = ("default-src 'none'", "connect-src 'none'", "base-uri 'none'", "form-action 'none'", "script-src 'nonce-")
  check(len(csp) == 1 and all(x in csp[0] for x in need), "one Content-Security-Policy with default-src, connect-src, base-uri and form-action 'none' and a script nonce")
  scripts = root.find("script")
  m = re.search(r"script-src 'nonce-([^']+)'", csp[0] if csp else "")
  check(bool(scripts) and m is not None and all(s.attrs.get("nonce") == m.group(1) and "src" not in s.attrs for s in scripts), f"{len(scripts)} inline script(s), each with the nonce and no src")
  code = "".join(k for s in scripts for k in s.kids if isinstance(k, str)) + rc.JS
  check(not [b for b in BANNED_JS if b in code], "the page script uses no " + ", ".join(BANNED_JS))
  loads = [(n.tag, n.attrs.get("src") or n.attrs.get("href")) for n in root.walk() if (n.tag != "a" and (n.attrs.get("src") or (n.tag == "link" and n.attrs.get("href")))) and not str(n.attrs.get("src") or "").startswith("data:")]
  css = "".join(k for s in root.find("style") for k in s.kids if isinstance(k, str))
  check(not loads and "@import" not in css and not re.search(r"url\(\s*['\"]?(?:https?:)?//", css), "nothing is loaded from another origin: no script, style, font or image address")
  chart = rc.chart_html(sx.for_payload(p))
  size = len(chart.encode()) + len(rc.evidence_html(sx.for_payload(p)).encode()) + len(rc.CSS.encode()) + len(rc.JS.encode())
  check(size <= 130_000, f"chart markup, strip, style and script take {size:,} bytes (the page file is {len(text.encode()):,} bytes)")
  check(len({rp.render(p) for _ in range(2)}) == 1 and rp.PAGE_FILES == ("soxl_analysis_report.html", "soxl_simple.html", "index.html"), "the page is the same text on each build and goes to three file names")


def test_every_payload(extra: list[str]) -> None:
  print("9. every payload")
  groups: list[tuple[str, list[tuple[str, dict]]]] = []
  snaps = sorted((BASE / "history" / "snapshots").glob("*.json.gz"))
  groups.append(("history/snapshots", [(s.name, load(s)) for s in snaps]))
  base = baseline_payloads()
  if base:
    groups.append(("git tag baseline", base))
  else:
    print("  skip git tag `baseline` not found: its payloads are not built here")
  if extra:
    groups.append(("command line", [(x, load(Path(x))) for x in extra]))
  for label, items in groups:
    before, fails, kinds = COUNT[0], len(FAILS), {"pipeline": 0, "reduced": 0}
    for name, payload in items:
      try:
        text = rp.render(payload)
      except Exception as e:  # noqa: BLE001 - the test reports which payload broke the page
        check(False, f"{label}: {name} raises {type(e).__name__}: {e}")
        continue
      kinds[sx.for_payload(payload).get("source") or "reduced"] += 1
      check_page(text, payload, f"{label} {name}", quiet=True)
    check(len(FAILS) == fails and bool(items), f"{label}: the page builds from {len(items)} payload(s) ({kinds['pipeline']} with the chart block, {kinds['reduced']} without) and passes {COUNT[0] - before} checks")


def main() -> int:
  p = load(BASE / "soxl_analysis_data.json")
  root = test_current(p)
  test_small_sample(p)
  test_fallbacks(p)
  test_first_screen(p, root)
  test_page(p)
  test_every_payload(sys.argv[1:])
  print("FAILURES:" if FAILS else "ALL PASS", len(FAILS), f"({COUNT[0]} checks)")
  for f in FAILS[:40]:
    print("  -", f)
  return 1 if FAILS else 0


if __name__ == "__main__":
  sys.exit(main())
