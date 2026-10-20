#!/usr/bin/env python3
"""Rendering QA harness for the SOXL dashboards (headless Chrome).

For each page × mode × viewport width it builds a QA copy of the HTML (CSP relaxed
ONLY in the copy, all <details> opened), injects a measurement script, runs Chrome
--dump-dom and collects:

  svg-text-clipped   <text> whose bbox leaves the SVG viewBox (gets cut by overflow:hidden)
  svg-text-overlap   two <text> labels in the same SVG overlapping each other
  svg-text-tiny      SVG text rendered smaller than 8 CSS px
  html-clipped       element with overflow hidden / nowrap whose content is wider/taller than its box
  html-escape        element sticking out of its parent's box (overlaps neighbours)
  page-hscroll       the whole page scrolls horizontally
  html-text-overlap  sibling text blocks overlapping (e.g. tile labels)

Usage (from the project folder; needs Google Chrome, override with CHROME_PATH):
  .venv/bin/python tools/qa_render.py                          # full matrix: 2 pages × modes × 9 widths
  .venv/bin/python tools/qa_render.py 1440 900 390             # chosen widths
  .venv/bin/python tools/qa_render.py --shot s3 1400           # screenshot one section → .qa/
  .venv/bin/python tools/qa_render.py --shot all 390 soxl_analysis_report.html 3000

Exit code 1 when any issue is found (handy after editing report_html.py / report_simple.py).
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
  function secOf(el){ var s = el.closest('section'); return s ? (s.id || s.className.split(' ')[0]) : (el.closest('header') ? 'header' : 'body'); }
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


def make_variant(page: str, mode: str, only: str | None = None, extra_css: str = "") -> Path:
  src_path = Path(page) if Path(page).is_absolute() else BASE / page
  src = src_path.read_text(encoding="utf-8")
  page = src_path.name
  html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", src, count=1)
  html = re.sub(r'<meta http-equiv="refresh"[^>]*>', "", html, count=1)
  if mode == "pro":
    html = html.replace('<body class="beginner">', '<body class="">', 1)
  css = extra_css
  if only:
    css += f"body > section:not(#{only}), body > .note, body > .auto, header.top, .foot {{display:none !important}}"
  if css:
    html = html.replace("</head>", f"<style>{css}</style></head>", 1)
  html = html.replace("</body>", f"<script>{QA_JS}</script></body>", 1)
  out = OUT / f"qa_{page.replace('.html', '')}_{mode}{'_' + only if only else ''}.html"
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


if __name__ == "__main__":
  if len(sys.argv) >= 2 and sys.argv[1] == "--shot":
    sec, width = sys.argv[2], int(sys.argv[3])
    page = sys.argv[4] if len(sys.argv) > 4 else "soxl_analysis_report.html"
    height = int(sys.argv[5]) if len(sys.argv) > 5 else 2600
    mode = sys.argv[6] if len(sys.argv) > 6 else "pro"
    v = make_variant(page, mode, only=None if sec == "all" else sec)
    out = OUT / f"shot_{Path(page).stem}_{sec}_{width}_{mode}.png"
    if width < 500:  # Chrome headless enforces >=500px windows: render inside a narrow iframe
      wrap = v.with_name(v.stem + f"_shot{width}.html")
      wrap.write_text(f'<!doctype html><html><body style="margin:0;background:#070b14"><iframe src="{v.name}" style="width:{width}px;height:{height}px;border:0"></iframe></body></html>', encoding="utf-8")
      chrome([f"--window-size={max(520, width)},{height}", "--allow-file-access-from-files", f"--screenshot={out}", wrap.as_uri()])
    else:
      shot(v, width, height, out)
    print(out)
    sys.exit(0)
  widths = [int(w) for w in sys.argv[1:]] or [1440, 1280, 1100, 1024, 900, 768, 600, 430, 390]
  total = 0
  for page, modes in (("soxl_analysis_report.html", ("pro", "beginner")), ("soxl_analysis_report.html", ("pro",))):
    for mode in modes:
      v = make_variant(page, mode)
      for w in widths:
        total += summarize(f"{page.split('.')[0]}|{mode}|{w}", measure(v, w))
  print("TOTAL ISSUES:", total)
  sys.exit(1 if total else 0)
