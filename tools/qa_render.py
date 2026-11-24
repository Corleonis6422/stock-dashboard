#!/usr/bin/env python3
"""Rendering QA harness for the SOXL page (headless Chrome).

The page is one file under three names; the checks load ``index.html``.  For each chart view x
viewport width it builds a QA copy of the HTML (CSP relaxed ONLY in the copy, all <details>
opened), injects a measurement script, runs Chrome --dump-dom and collects:

  svg-text-clipped   <text> whose bbox leaves the SVG viewBox (gets cut by overflow:hidden)
  svg-text-overlap   two <text> labels in the same SVG overlapping each other
  svg-text-tiny      SVG text rendered smaller than 8 CSS px
  html-clipped       element with overflow hidden / nowrap whose content is wider/taller than its box
  html-escape        element sticking out of its parent's box (overlaps neighbours)
  page-hscroll       the whole page scrolls horizontally
  html-text-overlap  sibling text blocks overlapping (e.g. tile labels)

A chart view that is not shown has no box, so each view (daily, weekly) gets its own runs.

Usage (from the project folder; needs Google Chrome, override with CHROME_PATH):
  python3 tools/qa_render.py                          # full matrix: the chart views x 9 widths
  python3 tools/qa_render.py 1440 900 390             # chosen widths
  python3 tools/qa_render.py --snapshots              # the page of every history/snapshots/*.json.gz at 1440, 768, 390
  python3 tools/qa_render.py --snapshots DIR 1440 390 # payloads (.json, .json.gz) of another folder, chosen widths
  python3 tools/qa_render.py --first-screen           # boxes of the seven first-screen items + budgets, per view
  python3 tools/qa_render.py --first-screen 1440 390  # the same at chosen widths
  python3 tools/qa_render.py --crosshair 1440 390     # scripted pointer and touch on the crosshair, per view
  python3 tools/qa_render.py --shot first 1440 index.html 800 weekly   # first screen, page as loaded → .qa/
  python3 tools/qa_render.py --shot sec-plan 1400     # screenshot one section, folds open → .qa/
  python3 tools/qa_render.py --shot all 390 index.html 3000

Exit code 1 when any issue is found (handy after editing report_page.py, report_chart.py or report_sections.py).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import os

CHROME = os.environ.get("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / ".qa"   # QA copies (CSP relaxed ONLY here, never served) + screenshots
OUT.mkdir(parents=True, exist_ok=True)
PROFILE = Path(tempfile.gettempdir()) / "chrome-soxl-qa"

QA_JS = r"""
(function(){
  document.querySelectorAll('details').forEach(function(d){ d.open = true; });
  var res = {vw: window.innerWidth, docW: document.documentElement.scrollWidth, issues: []};
  function secOf(el){ var s = el.closest('section'); return s ? (s.id || s.className.split(' ')[0]) : (el.closest('header') ? 'header' : (el.closest('main') ? 'main' : 'body')); }
  function short(s){ return (s || '').replace(/\s+/g, ' ').trim().slice(0, 70); }
  if (document.documentElement.scrollWidth > window.innerWidth + 1) {
    res.issues.push({type: 'page-hscroll', sec: 'page', detail: 'docW ' + document.documentElement.scrollWidth + ' > vw ' + window.innerWidth});
  }
  // ---------------- SVG checks
  document.querySelectorAll('svg').forEach(function(svg, si){
    var vis = svg.getBoundingClientRect();
    if (vis.width === 0 || vis.height === 0) return;
    var vb = svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal : {x: 0, y: 0, width: vis.width, height: vis.height};
    var scale = vis.width / vb.width;
    var sec = secOf(svg);
    var label = svg.getAttribute('aria-label') || svg.getAttribute('class') || ('svg#' + si);
    var texts = Array.prototype.slice.call(svg.querySelectorAll('text')).filter(function(t){ return t.textContent.trim().length; }).map(function(t){ return {t: t, b: t.getBBox()}; });
    texts.forEach(function(o){
      var b = o.b, tol = 0.5;
      if (b.x < vb.x - tol || b.y < vb.y - tol || b.x + b.width > vb.x + vb.width + tol || b.y + b.height > vb.y + vb.height + tol) {
        res.issues.push({type: 'svg-text-clipped', sec: sec, svg: label, text: short(o.t.textContent), detail: 'bbox x' + b.x.toFixed(0) + '..' + (b.x + b.width).toFixed(0) + ' y' + b.y.toFixed(0) + '..' + (b.y + b.height).toFixed(0) + ' vs viewBox ' + vb.width + 'x' + vb.height});
      }
      var fs = parseFloat(o.t.getAttribute('font-size') || getComputedStyle(o.t).fontSize || '16');
      if (fs * scale < 8) res.issues.push({type: 'svg-text-tiny', sec: sec, svg: label, text: short(o.t.textContent), detail: (fs * scale).toFixed(1) + 'px'});
    });
    // text vs data marks (polylines, lines, rects, stroked polygons, circles)
    function segRect(x1, y1, x2, y2, r){
      var p = [-(x2 - x1), x2 - x1, -(y2 - y1), y2 - y1], q = [x1 - r.x, r.x + r.w - x1, y1 - r.y, r.y + r.h - y1], u1 = 0, u2 = 1;
      for (var k = 0; k < 4; k++){ if (p[k] === 0){ if (q[k] < 0) return false; } else { var tt = q[k] / p[k]; if (p[k] < 0){ if (tt > u2) return false; if (tt > u1) u1 = tt; } else { if (tt < u1) return false; if (tt < u2) u2 = tt; } } }
      return true;
    }
    function pts(el){ return (el.getAttribute('points') || '').trim().split(/\s+/).map(function(pp){ var a = pp.split(','); return [parseFloat(a[0]), parseFloat(a[1])]; }).filter(function(a){ return !isNaN(a[0]) && !isNaN(a[1]); }); }
    var marks = [];
    svg.querySelectorAll('polyline, line, rect, polygon, circle').forEach(function(m){
      if (m.hasAttribute('data-bg') || m.hasAttribute('data-qa-ok')) return;
      var tag = m.tagName.toLowerCase();
      if (tag === 'rect' && (m.getAttribute('width') === '100%')) return;
      if (tag === 'polygon' && (!m.getAttribute('stroke') || m.getAttribute('stroke') === 'none')) return;
      var desc = tag + (m.getAttribute('stroke') ? '[' + m.getAttribute('stroke') + ']' : (m.getAttribute('fill') ? '[' + m.getAttribute('fill') + ']' : ''));
      if (tag === 'polyline' || tag === 'polygon'){ var P = pts(m); if (tag === 'polygon' && P.length) P.push(P[0]); for (var k = 1; k < P.length; k++) marks.push({seg: [P[k-1][0], P[k-1][1], P[k][0], P[k][1]], d: desc}); }
      else if (tag === 'line'){ marks.push({seg: [+m.getAttribute('x1'), +m.getAttribute('y1'), +m.getAttribute('x2'), +m.getAttribute('y2')], d: desc}); }
      else { var bb = m.getBBox(); marks.push({box: {x: bb.x, y: bb.y, w: bb.width, h: bb.height}, d: desc}); }
    });
    texts.forEach(function(o){
      if (o.t.hasAttribute('data-qa-ok')) return;
      var r = {x: o.b.x + 1.5, y: o.b.y + 2, w: Math.max(0, o.b.width - 3), h: Math.max(0, o.b.height - 4)};
      var hits = {};
      marks.forEach(function(m){
        var hit = m.seg ? segRect(m.seg[0], m.seg[1], m.seg[2], m.seg[3], r) : (m.box.x < r.x + r.w && m.box.x + m.box.w > r.x && m.box.y < r.y + r.h && m.box.y + m.box.h > r.y);
        if (hit) hits[m.d] = (hits[m.d] || 0) + 1;
      });
      var keys = Object.keys(hits);
      if (keys.length) res.issues.push({type: 'svg-text-on-data', sec: sec, svg: label, text: short(o.t.textContent), detail: keys.map(function(k){ return k + '×' + hits[k]; }).join(' ')});
    });
    for (var i = 0; i < texts.length; i++) for (var j = i + 1; j < texts.length; j++) {
      var a = texts[i].b, c = texts[j].b;
      var ox = Math.min(a.x + a.width, c.x + c.width) - Math.max(a.x, c.x);
      var oy = Math.min(a.y + a.height, c.y + c.height) - Math.max(a.y, c.y);
      if (ox > 1 && oy > 1.5) res.issues.push({type: 'svg-text-overlap', sec: sec, svg: label, text: short(texts[i].t.textContent) + '  ⟷  ' + short(texts[j].t.textContent), detail: 'overlap ' + ox.toFixed(0) + 'x' + oy.toFixed(0)});
    }
  });
  // ---------------- HTML checks
  var all = document.querySelectorAll('body *');
  all.forEach(function(el){
    if (el.closest('svg') || el.id === 'qa-result') return;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    var sec = secOf(el);
    var scrollable = /(auto|scroll)/.test(cs.overflowX + cs.overflowY);
    var clipsX = (cs.overflowX === 'hidden' || cs.overflowX === 'clip');
    var clipsY = (cs.overflowY === 'hidden' || cs.overflowY === 'clip');
    if (clipsX && el.scrollWidth > el.clientWidth + 1 && el.textContent.trim()) {
      res.issues.push({type: 'html-clipped', sec: sec, el: el.tagName.toLowerCase() + '.' + el.className, text: short(el.textContent), detail: 'scrollW ' + el.scrollWidth + ' > clientW ' + el.clientWidth});
    }
    if (clipsY && el.scrollHeight > el.clientHeight + 1 && el.textContent.trim()) {
      res.issues.push({type: 'html-clipped', sec: sec, el: el.tagName.toLowerCase() + '.' + el.className, text: short(el.textContent), detail: 'scrollH ' + el.scrollHeight + ' > clientH ' + el.clientHeight});
    }
    var p = el.parentElement;
    if (!p || p === document.body || p.tagName === 'HTML') return;
    var pcs = getComputedStyle(p);
    if (/(auto|scroll)/.test(pcs.overflowX)) return;  // inside an intentional scroll container
    if (el.closest('.tbl-wrap')) return;
    var pr = p.getBoundingClientRect();
    if (cs.position === 'absolute' || cs.position === 'fixed' || cs.position === 'sticky') return;
    if (r.right > pr.right + 2 || r.left < pr.left - 2) {
      res.issues.push({type: 'html-escape', sec: sec, el: el.tagName.toLowerCase() + '.' + el.className + ' in ' + p.tagName.toLowerCase() + '.' + p.className, text: short(el.textContent), detail: 'el ' + r.left.toFixed(0) + '..' + r.right.toFixed(0) + ' parent ' + pr.left.toFixed(0) + '..' + pr.right.toFixed(0)});
    }
  });
  // intrinsic text overflow: inline content wider than the block (white-space:nowrap, long tokens)
  all.forEach(function(el){
    if (el.closest('svg') || el.closest('.tbl-wrap') || el.closest('.chart-scroll') || el.id === 'qa-result') return;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || !el.childNodes.length) return;
    if (/(auto|scroll)/.test(cs.overflowX)) return;
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 && !(cs.overflowX === 'hidden' || cs.overflowX === 'clip') && cs.display !== 'inline') {
      res.issues.push({type: 'html-overflow', sec: secOf(el), el: el.tagName.toLowerCase() + '.' + el.className, text: short(el.textContent), detail: 'scrollW ' + el.scrollWidth + ' > clientW ' + el.clientWidth});
    }
  });
  // short labels that wrapped onto 2+ lines (e.g. 「下月/線」, 「均線系/統」)
  all.forEach(function(el){
    if (el.closest('svg') || el.id === 'qa-result') return;
    if (el.children.length) return;
    var txt = (el.textContent || '').trim();
    if (!txt || txt.length > 9) return;
    var cs = getComputedStyle(el);
    if (cs.display === 'none') return;
    var fs = parseFloat(cs.fontSize) || 14;
    var range = document.createRange(); range.selectNodeContents(el);
    var rects = range.getClientRects();
    var tops = [];
    for (var k = 0; k < rects.length; k++){ if (rects[k].width < 0.5) continue; var t0 = rects[k].top + rects[k].height / 2; if (!tops.some(function(v){ return Math.abs(v - t0) < fs * 0.6; })) tops.push(t0); }
    if (tops.length > 1) res.issues.push({type: 'html-short-wrap', sec: secOf(el), el: el.tagName.toLowerCase() + '.' + el.className, text: txt, detail: tops.length + ' lines'});
  });
  // informational: intentional scroll containers that actually need scrolling at this width
  res.scrollers = [];
  document.querySelectorAll('.tbl-wrap, .chart-scroll').forEach(function(el){
    var cs = getComputedStyle(el); if (cs.display === 'none' || !el.getBoundingClientRect().width) return;
    if (el.scrollWidth > el.clientWidth + 2) res.scrollers.push(secOf(el) + ':' + el.className + ' ' + el.scrollWidth + '>' + el.clientWidth + ' ' + short(el.textContent).slice(0, 24));
  });
  // short label text nodes with ugly breaks: orphans (last line ≤2 chars), mid-word Latin breaks,
  // or very short labels (≤8 chars) that wrap at all — only for label-like parents (flex/grid items,
  // headings, table cells, buttons, dt) and descriptive card notes; plain paragraphs may wrap freely.
  var LABEL_TAGS = {H1:1, H2:1, H3:1, H4:1, TH:1, TD:1, BUTTON:1, DT:1};
  var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  var node;
  while ((node = walker.nextNode())) {
    var par = node.parentElement;
    if (!par || par.closest('svg') || par.closest('#qa-result') || par.closest('script') || par.closest('style')) continue;
    var tx = node.textContent.replace(/\s+/g, ' ').trim();
    if (tx.length < 2 || tx.length > 16) continue;
    var pcs = getComputedStyle(par); if (pcs.display === 'none') continue;
    var labelLike = LABEL_TAGS[par.tagName] || /flex|grid/.test(pcs.display) || /flex|grid/.test(getComputedStyle(par.parentElement || par).display) || /rung|gauge|pillar|kpi|tile|lv-|chip|crit|card-h|qa-q|scen-/.test(par.className);
    if (!labelLike) continue;
    var raw = node.textContent, fsz = parseFloat(pcs.fontSize) || 14, lines = [], cur = '', lastMid = null;
    for (var ci = 0; ci < raw.length; ci++) {
      var rr = document.createRange(); rr.setStart(node, ci); rr.setEnd(node, ci + 1);
      var rc = rr.getClientRects()[0];
      if (!rc || rc.width < 0.1) { cur += raw[ci]; continue; }
      var mid = rc.top + rc.height / 2;
      if (lastMid !== null && Math.abs(mid - lastMid) > fsz * 0.6) { lines.push(cur); cur = ''; }
      cur += raw[ci]; lastMid = mid;
    }
    lines.push(cur);
    lines = lines.map(function(l){ return l.trim(); }).filter(function(l){ return l.length; });
    if (lines.length < 2) continue;
    var last = lines[lines.length - 1].replace(/[\s，。；：、！？,.;:!?）)」』%]/g, '');
    var bad = null;
    if (tx.length <= 8) bad = 'short label wrapped';
    else if (last.length <= 2) bad = 'orphan「' + lines[lines.length - 1] + '」';
    else {
      for (var li = 0; li < lines.length - 1; li++) {
        var e1 = lines[li].slice(-1), s1 = lines[li + 1].slice(0, 1);
        if (/[A-Za-z0-9$]/.test(e1) && /[A-Za-z0-9%]/.test(s1)) { bad = 'mid-word break'; break; }
      }
    }
    if (bad) res.issues.push({type: 'html-short-wrap', sec: secOf(par), el: par.tagName.toLowerCase() + '.' + par.className + ' #text', text: tx, detail: bad + ' (' + lines.join(' ⏎ ') + ')'});
  }
  var pre = document.createElement('pre'); pre.id = 'qa-result'; pre.textContent = JSON.stringify(res);
  document.body.appendChild(pre);
  if (window.parent !== window) { try { window.parent.postMessage(JSON.stringify(res), '*'); } catch (e) {} }
})();
"""


def page_views(page: str = "index.html") -> list[str]:
  """The chart views the page offers (``data-views`` of ``[data-chart]``); [] when it has no chart."""
  src_path = Path(page) if Path(page).is_absolute() else BASE / page
  m = re.search(r'<div[^>]*\bdata-chart\b[^>]*\bdata-views="([a-z ]+)"', src_path.read_text(encoding="utf-8"))
  return m.group(1).split() if m else []


def make_variant(page: str, only: str | None = None, extra_css: str = "", view: str | None = None,
                 script: str | None = QA_JS, tag: str = "") -> Path:
  src_path = Path(page) if Path(page).is_absolute() else BASE / page
  src = src_path.read_text(encoding="utf-8")
  page = src_path.name
  html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", src, count=1)
  html = re.sub(r'<meta http-equiv="refresh"[^>]*>', "", html, count=1)
  if view:  # the page script starts from data-active-view when neither the URL nor the browser store names a view
    html = re.sub(r'(<div[^>]*\bdata-chart\b[^>]*\bdata-active-view=")[a-z]+(")', rf"\g<1>{view}\g<2>", html, count=1)
  css = extra_css
  if only:
    css += f"body > *:not(#{only}):not(:has(#{only})):not(script):not(style) {{display:none !important}}"
  if css:
    html = html.replace("</head>", f"<style>{css}</style></head>", 1)
  if script:
    html = html.replace("</body>", f"<script>{script}</script></body>", 1)
  out = OUT / (f"qa_{page.replace('.html', '')}" + (f"_{view}" if view else "") + (f"_{only}" if only else "") + (f"_{tag}" if tag else "") + ".html")
  out.write_text(html, encoding="utf-8")
  return out


def chrome(args: list[str], timeout: int = 60) -> str:
  for attempt in range(3):
    prof = tempfile.mkdtemp(prefix="chrome-soxl-qa-")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={prof}", "--virtual-time-budget=4000", *args]
    try:
      res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
      return res.stdout
    except subprocess.TimeoutExpired:
      print(f"   (chrome timeout, retry {attempt + 1})", flush=True)
    finally:
      import shutil
      shutil.rmtree(prof, ignore_errors=True)
  return ""


def measure(path: Path, width: int, height: int = 1200) -> dict:
  target = path
  if width < 500:
    wrap = path.with_name(path.stem + f"_wrap{width}.html")
    wrap.write_text(f'<!doctype html><html><body style="margin:0"><iframe src="{path.name}" style="width:{width}px;height:{height}px;border:0"></iframe>'
                    '<pre id="qa-result"></pre><script>window.addEventListener("message",function(e){document.getElementById("qa-result").textContent=e.data;});</script></body></html>', encoding="utf-8")
    target = wrap
    width = 520
  dom = chrome([f"--window-size={width},{height}", "--allow-file-access-from-files", "--dump-dom", target.as_uri()])
  m = None
  for m in re.finditer(r'<pre id="qa-result">(.*?)</pre>', dom, re.S):
    if m.group(1).strip():
      break
  if not m or not m.group(1).strip():
    return {"error": "no qa-result", "dom_len": len(dom)}
  import html as _h
  return json.loads(_h.unescape(m.group(1)))


def shot(path: Path, width: int, height: int, out: Path) -> Path:
  chrome([f"--window-size={width},{height}", f"--screenshot={out}", path.as_uri()])
  return out


def summarize(tag: str, r: dict, verbose: int = 6) -> int:
  if "error" in r:
    print(f"[{tag}] ERROR {r}")
    return 1
  issues = r["issues"]
  print(f"[{tag}] vw={r['vw']} docW={r['docW']} issues={len(issues)}  " + ", ".join(f"{k}:{v}" for k, v in Counter(i['type'] for i in issues).items())
        + (f"  | scroll-needed {len(r.get('scrollers', []))}" if r.get('scrollers') else ""))
  for sc in r.get("scrollers", [])[:12]:
    print(f"     ⇆ {sc}")
  groups = defaultdict(list)
  for i in issues:
    groups[(i["type"], i["sec"])].append(i)
  for (typ, sec), items in sorted(groups.items()):
    print(f"   - {typ} @ {sec}: {len(items)}")
    for it in items[:verbose]:
      print(f"       · {it.get('svg') or it.get('el', '')} | {it.get('text', '')} | {it.get('detail', '')}")
  return len(issues)


PAGE = "index.html"                  # the one page; soxl_analysis_report.html and soxl_simple.html hold the same bytes
SNAPSHOT_WIDTHS = [1440, 768, 390]   # the widths for the pages built from stored daily payloads
WIDTHS = [1440, 1280, 1100, 1024, 900, 768, 600, 430, 390]
FIRST_SCREEN_SECS = ("header", "main", "readouts", "chart", "chart-rules", "evidence")   # section names of the first screen and the strip
WIDE_PX, WIDE_FOLD = 1440, 800       # first screen: the top 800 px at 1440 px width
NARROW_PX, NARROW_FOLD = 390, 700    # and the top 700 px at 390 px width
NARROW_CHART_TOP, NARROW_CHART_H = 1400, 700   # at 390 px the chart starts above this line and is at most this tall

# Where the first-screen items sit, in page coordinates, with the page as loaded (no fold opened).
FS_JS = r"""
(function(){
  var W = document.querySelector('[data-chart]');
  var res = {vw: window.innerWidth, vh: window.innerHeight, docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight,
             view: W ? W.getAttribute('data-active-view') : null, items: [], extra: {}, problems: [], labels: 0, bars: 0};
  function rnd(x){ return Math.round(x * 10) / 10; }
  function box(el){ var r = el.getBoundingClientRect(); return {l: rnd(r.left + window.scrollX), t: rnd(r.top + window.scrollY), r: rnd(r.right + window.scrollX), b: rnd(r.bottom + window.scrollY), w: rnd(r.width), h: rnd(r.height)}; }
  function shown(el){ var r = el.getBoundingClientRect(); return (r.width > 0 || r.height > 0) && getComputedStyle(el).visibility !== 'hidden'; }
  document.querySelectorAll('[data-r2]').forEach(function(el){ var o = box(el); o.n = el.getAttribute('data-r2'); o.name = el.getAttribute('data-r2-name'); o.shown = shown(el); res.items.push(o); });
  [['volume', '[data-readout="volume"]'], ['chart-rules', '[data-chart-rulebox]'], ['evidence', '[data-evidence-strip]'], ['drawing', '[data-cross-target="' + res.view + '"]']].forEach(function(p){
    var el = document.querySelector(p[1]); if (el && shown(el)) res.extra[p[0]] = box(el);
  });
  if (res.docW > res.vw + 1) res.problems.push('page-hscroll: docW ' + res.docW + ' > vw ' + res.vw);
  var cb = document.querySelector('[data-chart-box]');
  if (cb) {
    [cb].concat(Array.prototype.slice.call(cb.querySelectorAll('*'))).forEach(function(el){
      if (el.closest('svg')) return;
      var cs = getComputedStyle(el); if (cs.display === 'none' || cs.display === 'inline') return;
      if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1) res.problems.push('chart-hscroll: ' + el.tagName.toLowerCase() + '.' + el.className + ' scrollW ' + el.scrollWidth + ' > clientW ' + el.clientWidth);
    });
    var cr = cb.getBoundingClientRect();
    if (cr.left < -0.5 || cr.right > window.innerWidth + 0.5) res.problems.push('chart-outside: box x ' + cr.left.toFixed(1) + '..' + cr.right.toFixed(1) + ' in a viewport of ' + window.innerWidth);
  }
  // labels, leaders and arrow heads against the candles of the latest 20 bars
  var tgt = W && W.querySelector('[data-cross-target="' + res.view + '"]');
  if (tgt) {
    var bars = Array.prototype.slice.call(tgt.querySelectorAll('[data-series="candles"] [data-bar]'));
    var last = bars.slice(-20).map(function(g){ return {i: g.getAttribute('data-bar'), r: g.getBoundingClientRect()}; });
    var labs = Array.prototype.slice.call(tgt.parentElement.querySelectorAll('.sx-l, .sx-ld, .sx-ah')).filter(function(el){ return getComputedStyle(el).display !== 'none'; });
    res.labels = labs.length; res.bars = bars.length;
    labs.forEach(function(el){
      var a = el.getBoundingClientRect();
      last.forEach(function(c){
        var ox = Math.min(a.right, c.r.right) - Math.max(a.left, c.r.left), oy = Math.min(a.bottom, c.r.bottom) - Math.max(a.top, c.r.top);
        if (ox > 0.25 && oy > 0.25) res.problems.push('label-on-candle: "' + ((el.textContent || '').trim() || el.className) + '" covers bar ' + c.i + ' by ' + ox.toFixed(1) + ' x ' + oy.toFixed(1) + ' px');
      });
    });
  }
  // placeholder tokens in the text the first screen shows
  var txt = '';
  ['header', 'main'].forEach(function(sel){ var el = document.querySelector(sel); if (el) txt += ' ' + el.innerText; });
  [[/\bNone\b/, 'None'], [/\bn\/a\b/i, 'n/a'], [/\bnan\b/i, 'nan'], [/\bnull\b/, 'null'], [/\bundefined\b/, 'undefined'], [/\$(?!\s?[\d,.]*\d)/, '$ with no number'],
   [/\(\s*\)|（\s*）|\[\s*\]|【\s*】|「\s*」/, 'empty brackets']].forEach(function(t){ if (t[0].test(txt)) res.problems.push('placeholder: ' + t[1]); });
  res.chars = txt.replace(/\s+/g, '').length;
  var pre = document.createElement('pre'); pre.id = 'qa-result'; pre.textContent = JSON.stringify(res);
  document.body.appendChild(pre);
  if (window.parent !== window) { try { window.parent.postMessage(JSON.stringify(res), '*'); } catch (e) {} }
})();
"""

# A scripted pointer and a scripted finger at the x position of three bars; the read-out must show that bar.
CROSS_JS = r"""
(function(){
  var W = document.querySelector('[data-chart]');
  var res = {vw: window.innerWidth, view: W ? W.getAttribute('data-active-view') : null, checks: [], problems: [], bars: 0};
  function done(){
    var pre = document.createElement('pre'); pre.id = 'qa-result'; pre.textContent = JSON.stringify(res); document.body.appendChild(pre);
    if (window.parent !== window) { try { window.parent.postMessage(JSON.stringify(res), '*'); } catch (e) {} }
  }
  var tgt = W && W.querySelector('[data-cross-target="' + res.view + '"]');
  var ro = W && W.querySelector('[data-crosshair-readout][data-pane="' + res.view + '"]');
  if (!tgt || !ro) { res.problems.push('no crosshair target or no read-out'); done(); return; }
  var svg = tgt.querySelector('svg'), step = parseFloat(svg.getAttribute('data-step')), line = tgt.querySelector('[data-crosshair-line]');
  var bars = Array.prototype.slice.call(tgt.querySelectorAll('[data-series="candles"] [data-bar]')), n = bars.length;
  res.bars = n;
  var picks = [0, Math.floor(n / 3), Math.floor(2 * n / 3)].filter(function(v, k, a){ return a.indexOf(v) === k; });
  function val(name){ var el = ro.querySelector('[data-f="' + name + '"]'); return el ? {v: el.getAttribute('data-v'), t: el.textContent} : null; }
  function want(b){ return {date: b.getAttribute('data-d'), close: b.getAttribute('data-c'), vix: b.getAttribute('data-vix'), volume: b.getAttribute('data-v'), crash: b.getAttribute('data-cr')}; }
  function xy(i){ var r = svg.getBoundingClientRect(); return [r.left + r.width * (i + 0.5) * step / 1000, r.top + r.height * 0.3]; }
  function touch(name, x, y){
    var ev;
    try { var t = new Touch({identifier: 7, target: tgt, clientX: x, clientY: y}); ev = new TouchEvent(name, {bubbles: true, touches: [t], targetTouches: [t], changedTouches: [t]}); }
    catch (e) { ev = new Event(name, {bubbles: true}); Object.defineProperty(ev, 'touches', {value: [{clientX: x, clientY: y}]}); }
    tgt.dispatchEvent(ev);
  }
  var KINDS = [
    ['pointermove (mouse)', function(x, y){ tgt.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: x, clientY: y, pointerType: 'mouse'})); }],
    ['mousemove', function(x, y){ tgt.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: x, clientY: y})); }],
    ['pointerdown (touch)', function(x, y){ tgt.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, clientX: x, clientY: y, pointerType: 'touch'})); }],
    ['touchstart', function(x, y){ touch('touchstart', x, y); }],
    ['touchmove', function(x, y){ touch('touchmove', x, y); }]
  ];
  KINDS.forEach(function(k){
    picks.forEach(function(i){
      tgt.dispatchEvent(new PointerEvent('pointerleave', {pointerType: 'mouse'}));   // back to the latest bar
      var p = xy(i); k[1](p[0], p[1]);
      var w = want(bars[i]), bad = [];
      ['date', 'close', 'vix', 'volume', 'crash'].forEach(function(f){
        var g = val(f);
        if (!g) { if (f === 'date' || f === 'close' || f === 'volume' || w[f] !== null) bad.push(f + ': no field in the read-out'); return; }
        if (g.v !== w[f]) bad.push(f + ': read-out ' + g.v + ' != bar ' + w[f]);
      });
      if (ro.getAttribute('data-bar') !== String(i)) bad.push('read-out data-bar ' + ro.getAttribute('data-bar') + ' != ' + i);
      if (line) { var lr = line.getBoundingClientRect(); if (Math.abs(lr.left + lr.width / 2 - p[0]) > 0.75) bad.push('line at ' + (lr.left + lr.width / 2).toFixed(1) + ' px, bar at ' + p[0].toFixed(1) + ' px'); }
      res.checks.push({kind: k[0], bar: i, x: Math.round(p[0] * 10) / 10, ok: !bad.length, bad: bad, text: ro.innerText.replace(/\s+/g, ' ').trim()});
    });
  });
  tgt.dispatchEvent(new PointerEvent('pointerleave', {pointerType: 'mouse'}));
  if (ro.getAttribute('data-bar') !== String(n - 1)) res.problems.push('after the pointer leaves, the read-out does not return to the latest bar');
  done();
})();
"""


def crop_png(path: Path, width: int, height: int) -> None:
  """Keep the top-left ``width`` x ``height`` pixels of an 8-bit RGB or RGBA PNG (standard library only)."""
  import struct
  import zlib
  data = path.read_bytes()
  if data[:8] != b"\x89PNG\r\n\x1a\n":
    return
  pos, chunks = 8, []
  while pos + 8 <= len(data):
    ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
    chunks.append((typ, data[pos + 8:pos + 8 + ln]))
    pos += 12 + ln
  w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", next(c for t, c in chunks if t == b"IHDR"))
  if depth != 8 or ctype not in (2, 6) or interlace or (w <= width and h <= height):
    return
  bpp = 4 if ctype == 6 else 3
  raw = zlib.decompress(b"".join(c for t, c in chunks if t == b"IDAT"))
  stride, nw = w * bpp, min(w, width)
  rows, prev = [], bytearray(stride)
  for y in range(min(h, height)):
    f = raw[y * (stride + 1)]
    line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
    if f == 1:
      for i in range(bpp, stride):
        line[i] = (line[i] + line[i - bpp]) & 255
    elif f == 2:
      for i in range(stride):
        line[i] = (line[i] + prev[i]) & 255
    elif f == 3:
      for i in range(stride):
        line[i] = (line[i] + (((line[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
    elif f == 4:
      for i in range(stride):
        a, b, c = (line[i - bpp] if i >= bpp else 0), prev[i], (prev[i - bpp] if i >= bpp else 0)
        pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
        line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
    prev = line
    rows.append(b"\x00" + bytes(line[:nw * bpp]))

  def chunk(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)

  path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", nw, len(rows), 8, ctype, 0, 0, 0))
                   + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def shot_first(width: int, view: str | None = None, page: str = PAGE) -> Path:
  """Screenshot of the first screen of the unmodified page as loaded (no fold opened), with ``view`` shown.

  1440 x 800 and wider screens use the window itself.  Below 500 px Chrome refuses the window width,
  so the page loads in an iframe of that width and the picture is cropped to it (390 x 700).
  """
  src_path = Path(page) if Path(page).is_absolute() else BASE / page
  height = NARROW_FOLD if width < 500 else WIDE_FOLD
  url = src_path.as_uri() + (f"#view={view}" if view else "")
  out = OUT / f"first_{src_path.stem}_{width}_{view or 'default'}.png"
  if width < 500:
    wrap = OUT / f"qa_first_wrap_{width}_{view or 'default'}.html"
    wrap.write_text(f'<!doctype html><html><body style="margin:0;background:#070b14"><iframe src="{url}" style="display:block;width:{width}px;height:{height}px;border:0"></iframe></body></html>', encoding="utf-8")
    chrome([f"--window-size=520,{height}", "--allow-file-access-from-files", f"--screenshot={out}", wrap.as_uri()])
    crop_png(out, width, height)
  else:
    chrome([f"--window-size={width},{height}", f"--screenshot={out}", url])
  return out


def first_screen_report(widths: list[int], page: str = PAGE) -> int:
  """Print where the seven first-screen items sit for each chart view, and check the budgets.

  The page is measured as loaded: no fold opened.  At 1440 px all seven items and
  the rule lines end inside the top 800 px.  At 390 px items 1 to 6 end inside the top 700 px, the
  chart starts above 1,400 px and is at most 700 px tall.  At every width the page and the chart
  need no horizontal scroll, no label covers a candle of the latest 20 bars, and the first screen
  shows no placeholder token.  Returns the number of failed runs.
  """
  fails = 0
  for view in page_views(page) or [None]:
    v = make_variant(page, view=view, script=FS_JS, tag="fs")
    for w in widths:
      r = measure(v, w, NARROW_FOLD if w < 500 else WIDE_FOLD)
      tag = f"first-screen|{view or 'no-chart'}|{w}"
      if "error" in r:
        print(f"[{tag}] ERROR {r}")
        fails += 1
        continue
      print(f"[{tag}] vw={r['vw']} docW={r['docW']} docH={r['docH']} view={r['view']} bars={r['bars']} labels={r['labels']} first-screen chars={r.get('chars')}")
      items = {int(i["n"]): i for i in r["items"]}
      for n in sorted(items):
        i = items[n]
        print(f"   R2 {n} {i['name']:<8} x {i['l']:>7.1f} .. {i['r']:<7.1f} y {i['t']:>7.1f} .. {i['b']:<7.1f} ({i['w']:.1f} x {i['h']:.1f})" + ("" if i["shown"] else "  NOT SHOWN"))
      for k, e in r["extra"].items():
        print(f"   {k:<13} x {e['l']:>7.1f} .. {e['r']:<7.1f} y {e['t']:>7.1f} .. {e['b']:<7.1f} ({e['w']:.1f} x {e['h']:.1f})")
      bad = list(r["problems"])
      if sorted(items) != [1, 2, 3, 4, 5, 6, 7] or not all(i["shown"] for i in items.values()):
        bad.append(f"r2-items: found {sorted(items)}, expected 1 to 7, all shown")
      else:
        if w >= WIDE_PX:
          low = max(i["b"] for i in items.values())
          rules_b = (r["extra"].get("chart-rules") or {}).get("b", 0)
          print(f"   budget {WIDE_FOLD} px: lowest item ends at {low:.1f}, rule lines end at {rules_b:.1f}")
          if low > WIDE_FOLD:
            bad.append(f"budget: an item ends at {low:.1f} px, below the first {WIDE_FOLD} px")
          if rules_b > WIDE_FOLD:
            bad.append(f"budget: the rule lines end at {rules_b:.1f} px, below the first {WIDE_FOLD} px")
        if w <= NARROW_PX:
          low = max(items[n]["b"] for n in range(1, 7))
          print(f"   budget {NARROW_FOLD} px: items 1 to 6 end at {low:.1f}; chart starts at {items[7]['t']:.1f} and is {items[7]['h']:.1f} tall")
          if low > NARROW_FOLD:
            bad.append(f"budget: items 1 to 6 end at {low:.1f} px, below the first {NARROW_FOLD} px")
          if items[7]["t"] >= NARROW_CHART_TOP:
            bad.append(f"budget: the chart starts at {items[7]['t']:.1f} px, not above {NARROW_CHART_TOP} px")
          if items[7]["h"] > NARROW_CHART_H:
            bad.append(f"budget: the chart is {items[7]['h']:.1f} px tall, more than {NARROW_CHART_H} px")
      for b in bad:
        print(f"   FAIL {b}")
      fails += 1 if bad else 0
  print("FIRST SCREEN FAILED RUNS:", fails)
  return fails


def crosshair_report(widths: list[int], page: str = PAGE) -> int:
  """Move a scripted pointer and a scripted finger to three bars of each view; the read-out must show each bar's stored values."""
  fails = 0
  for view in page_views(page) or [None]:
    v = make_variant(page, view=view, script=CROSS_JS, tag="cross")
    for w in widths:
      r = measure(v, w, NARROW_FOLD if w < 500 else WIDE_FOLD)
      tag = f"crosshair|{view or 'no-chart'}|{w}"
      if "error" in r:
        print(f"[{tag}] ERROR {r}")
        fails += 1
        continue
      checks = r["checks"]
      bad = [c for c in checks if not c["ok"]]
      print(f"[{tag}] vw={r['vw']} bars={r['bars']} checks={len(checks)} failed={len(bad)}" + ("".join(f" | {p}" for p in r["problems"])))
      seen = set()
      for c in checks:
        if c["ok"] and c["bar"] in seen:
          continue
        seen.add(c["bar"])
        print(f"   {'ok  ' if c['ok'] else 'FAIL'} {c['kind']:<20} bar {c['bar']:>3} at x {c['x']:>7.1f} → {c['text'][:110]}" + ("".join(f" | {b}" for b in c["bad"])))
      kinds = Counter(c["kind"] for c in checks if c["ok"])
      print("   passed by event: " + ", ".join(f"{k} {n}" for k, n in kinds.items()))
      fails += 1 if (bad or r["problems"] or not checks) else 0
  print("CROSSHAIR FAILED RUNS:", fails)
  return fails


def layout_report(widths: list[int], page: str = PAGE, quiet: bool = False) -> int:
  """The layout checks on one page: every chart view, every width, every fold open.  Returns the issue count."""
  total, runs = 0, 0
  by_type: Counter = Counter()
  by_sec: Counter = Counter()
  for view in page_views(page) or [None]:
    v = make_variant(page, view=view)
    for w in widths:
      r = measure(v, w)
      total += summarize(f"{Path(page).stem}|{view or 'no-chart'}|{w}", r)
      runs += 1
      for i in r.get("issues", []):
        by_type[i["type"]] += 1
        by_sec[i["sec"]] += 1
  if not quiet:
    first = sum(c for sec, c in by_sec.items() if sec in FIRST_SCREEN_SECS)
    print("RUNS:", runs)
    print("BY TYPE:", ", ".join(f"{k}:{v}" for k, v in sorted(by_type.items())) or "none")
    print("BY SECTION:", ", ".join(f"{k}:{v}" for k, v in sorted(by_sec.items())) or "none")
    print(f"FIRST SCREEN, CHART AND EVIDENCE STRIP ({', '.join(FIRST_SCREEN_SECS)}):", first)
    print("TOTAL ISSUES:", total)
  return total


def snapshots_report(folder: Path, widths: list[int]) -> int:
  """Build the page from every stored daily payload of ``folder`` and run the layout checks on it.  Returns the issue count."""
  import gzip
  sys.path.insert(0, str(BASE))
  from soxl_quant import report_page
  files = sorted(f for f in folder.iterdir() if f.name.endswith((".json", ".json.gz")))
  total = 0
  for f in files:
    payload = json.load(gzip.open(f, "rt", encoding="utf-8") if f.name.endswith(".gz") else open(f, encoding="utf-8"))
    name = f.name.replace(".json.gz", "").replace(".json", "")
    page = OUT / f"snap_{name}.html"
    page.write_text(report_page.render(payload), encoding="utf-8")
    n = layout_report(widths, str(page), quiet=True)
    print(f"== {name}: {n} issues at {widths} ({page.stat().st_size:,} bytes)", flush=True)
    total += n
  print("PAYLOADS:", len(files))
  print("TOTAL ISSUES:", total)
  return total


if __name__ == "__main__":
  if len(sys.argv) >= 2 and sys.argv[1] == "--shot":
    sec, width = sys.argv[2], int(sys.argv[3])
    page = sys.argv[4] if len(sys.argv) > 4 else PAGE
    height = int(sys.argv[5]) if len(sys.argv) > 5 else 2600
    view = sys.argv[6] if len(sys.argv) > 6 else None
    if sec == "first":  # the first screen of the unmodified page: its own size, no fold opened
      print(shot_first(width, view, page))
      sys.exit(0)
    v = make_variant(page, only=None if sec == "all" else sec, view=view)
    out = OUT / f"shot_{Path(page).stem}_{sec}_{width}{'_' + view if view else ''}.png"
    if width < 500:  # Chrome headless enforces >=500px windows: render inside a narrow iframe
      wrap = v.with_name(v.stem + f"_shot{width}.html")
      wrap.write_text(f'<!doctype html><html><body style="margin:0;background:#070b14"><iframe src="{v.name}" style="width:{width}px;height:{height}px;border:0"></iframe></body></html>', encoding="utf-8")
      chrome([f"--window-size={max(520, width)},{height}", "--allow-file-access-from-files", f"--screenshot={out}", wrap.as_uri()])
    else:
      shot(v, width, height, out)
    print(out)
    sys.exit(0)
  if len(sys.argv) >= 2 and sys.argv[1] == "--snapshots":
    rest = sys.argv[2:]
    folder = Path(rest.pop(0)) if rest and not rest[0].isdigit() else BASE / "history" / "snapshots"
    sys.exit(1 if snapshots_report(folder, [int(w) for w in rest] or SNAPSHOT_WIDTHS) else 0)
  if len(sys.argv) >= 2 and sys.argv[1] in ("--first-screen", "--crosshair"):
    widths = [int(w) for w in sys.argv[2:]] or WIDTHS
    sys.exit(1 if (first_screen_report if sys.argv[1] == "--first-screen" else crosshair_report)(widths) else 0)
  sys.exit(1 if layout_report([int(w) for w in sys.argv[1:]] or WIDTHS) else 0)
