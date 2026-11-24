#!/usr/bin/env python3
"""The one viewer page.

``index.html``, ``soxl_analysis_report.html`` and ``soxl_simple.html`` hold the same file, so every
old link still opens the page.

Layout
  first screen   the seven readouts of the spec (rating label and plain answer, data date and status,
                 close and 1-day change, the level to watch, the crash index, VIX and its spike state,
                 the combined chart) plus the volume line; ``docs/page_markers.md`` lists the markers
  evidence strip under the chart
  sections       ten sections, each with one takeaway, one visual and folds (``report_sections``);
                 ``docs/section_log.md`` says where each block of the two former pages went
  footer         sources, the disclaimer of the feed, the update status, three folds

The first screen takes the rating label and the buy answer from the same fields and the same function
as the agent feed (``brief.build``), so the page and ``feed/latest.json`` cannot disagree.

Security: every interpolated value passes through html.escape(); the Content-Security-Policy is the
one of the former full report (default-src 'none', a script nonce, no connection, no base, no form).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import fsio, report_chart, report_html, report_sections, stress_chart
from .report_html import NONCE, esc

PAGE_FILES = ("soxl_analysis_report.html", "soxl_simple.html", "index.html")   # the same page under its three URLs
REFRESH_SEC = 1800   # an open tab re-reads the file every 30 min, as the former beginner page did; the chart view and the open folds survive it
BUY_NOTE = "答案先看交易計畫，再看評級"
NO_WATCH = "沒有單一關鍵價位"
VS_ZH = {"above": "高於", "below": "低於", "equal": "等於"}

# warnings[] entries start with the pipeline step that failed; the page names the source, never the raw text
SOURCE_ZH = (
    ("options", "期權"), ("sentiment", "市場情緒"), ("heatmap", "成分股"), ("macro", "宏觀"), ("vix complex", "VIX 家族"), ("treasury", "美債殖利率"),
    ("early_warning", "崩跌前兆"), ("newsflash", "時事"), ("news", "新聞"), ("postmortem", "崩跌復盤"), ("backtest/tradeplan", "回測與交易計畫"),
    ("events", "事件日曆"), ("soxx", "SOXX 日線"), ("soxs", "SOXS 日線"), ("spy", "SPY 日線"), ("hyg", "HYG 日線"), ("dashboard", "六個儀表"),
    ("stress_chart", "組合圖"), ("history", "歷史紀錄"), ("snapshot", "每日快照"),
)


def failed_sources(warnings: list | None) -> list[str]:
  """The sources named by ``warnings``, in Traditional Chinese, each once, in order."""
  out: list[str] = []
  for w in warnings or []:
    key = str(w).split(":", 1)[0].strip().lower()
    name = next((zh for k, zh in SOURCE_ZH if key.startswith(k)), "其他來源")
    if name not in out:
      out.append(name)
  return out


def _num(v) -> float | None:
  try:
    f = float(v)
  except (TypeError, ValueError):
    return None
  return f if f == f and f not in (float("inf"), float("-inf")) else None


def _mmdd(d: object) -> str:
  d = str(d or "")
  return d[5:].replace("-", "/") if len(d) >= 10 else d


def _phrases(text: object) -> str:
  """Escaped text in which a line breaks after a comma or a semicolon before it breaks inside a phrase."""
  return "".join(f'<span class="fs-ph">{esc(x)}</span>' for x in re.split(r"(?<=[，；、,;])", str(text or "")) if x)


def first_screen(p: dict, block: dict | None = None) -> dict:
  """The readouts of the first screen as plain values.  Every text is ready for the reader: no None, no n/a."""
  from . import brief as briefmod  # the feed's own function, so the page and the feed cannot differ
  block = stress_chart.for_payload(p) if block is None else block
  tech, sc, pb, tp = (p.get(k) or {} for k in ("technicals", "scoring", "playbook", "trade_plan"))
  b = pb.get("beginner") or {}
  ews = (p.get("early_warning") or {}).get("today") or {}
  try:
    bg = briefmod._beginner_block(sc, b, tp, b.get("plan") or {}, p.get("newsflash") or None, [], ews, tech)
  except Exception:  # noqa: BLE001 - the first screen must still build; the answer then reads as missing
    bg = {}
  buy, watch = bg.get("buy") or {}, bg.get("watch") or {}
  ds = p.get("data_status") or {}
  lt = block.get("latest") or {}

  # ---- item 1: the feed's verdict.label and beginner.buy.answer
  rating = b.get("verdict") or sc.get("rating_label")
  out: dict = {
      "rating": str(rating) if rating else "評級暫缺", "rating_emoji": str(b.get("emoji") or sc.get("rating_emoji") or ""),
      "color": b.get("color") if b.get("color") in ("bear", "bull", "neutral") else "neutral",
      "answer": str(buy.get("answer") or "資料不足"), "answer_emoji": str(buy.get("emoji") or ""),
      # ---- item 2
      "data_date": str(p.get("data_as_of") or tech.get("latest_date") or ""), "data_status": str(ds.get("label") or "收盤"),
      "missing_sources": failed_sources(p.get("warnings")), "generated_at": str(p.get("generated_at") or "")[:16],
  }
  # ---- item 3
  out["close"], out["ret_1d"] = _num(tech.get("close")), _num(tech.get("ret_1d"))
  # ---- item 4: the feed's beginner.watch
  wp = _num(watch.get("price"))
  kind = str(watch.get("label") or "")
  out["watch_price"] = wp if wp and kind not in ("", "n/a") else None
  out["watch_kind"] = kind if out["watch_price"] is not None else NO_WATCH
  # ---- item 5
  score = _num(ews.get("score"))
  zone = str(ews.get("zone") or "").split(" (")[0].split("；")[0].strip()
  out["crash"], out["crash_zone"] = (score, zone) if score is not None and zone not in ("", "n/a") else (None, "")
  # ---- item 6: the latest VIX reading at or before the latest session, and whether that session is a spike
  lv = lt.get("vix") or {}
  sv = (p.get("sentiment") or {}).get("vix") or {}
  out["vix_note"] = ""
  if _num(lv.get("close")) is not None:
    out["vix"], out["vix_date"], out["vix_same_session"] = _num(lv.get("close")), str(lv.get("date") or ""), bool(lv.get("same_session"))
    if not out["vix_same_session"]:
      out["spike"], out["spike_text"] = None, "最新交易日的 VIX 還沒公布，無法判定急升"
    elif lv.get("spike") is None:
      out["spike"], out["spike_text"] = None, "VIX 歷史不足，無法判定急升"
    else:
      out["spike"] = bool(lv.get("spike"))
      out["spike_text"] = "最新交易日是 VIX 急升" if out["spike"] else "最新交易日不是 VIX 急升"
      mult = _num(lv.get("multiple"))
      rule = ((block.get("rules") or {}).get("vix_spike") or {}).get("params") or {}
      if mult is not None and rule.get("multiple") and lv.get("lookback_sessions"):
        out["vix_note"] = f"是前 {lv['lookback_sessions']} 個交易日中位數的 {mult:.2f} 倍，門檻 {rule['multiple']:g} 倍"
  elif _num(sv.get("vix")) is not None:
    out["vix"], out["vix_date"], out["vix_same_session"] = _num(sv.get("vix")), str(sv.get("date") or ""), str(sv.get("date") or "") == out["data_date"]
    out["spike"], out["spike_text"] = None, "缺少 VIX 歷史資料，無法判定急升"
  else:
    out["vix"], out["vix_date"], out["vix_same_session"], out["spike"], out["spike_text"] = None, "", False, None, "缺少 VIX 資料（來源 CBOE）"
  # ---- volume against its 20-session average
  vol = _num(lt.get("volume")) if lt else _num(tech.get("volume"))
  avg = _num(lt.get("vol_avg20")) if lt else _num(tech.get("vol_sma20"))
  vs = lt.get("volume_vs_avg") if lt else None
  if vs is None and vol is not None and avg:
    vs = "above" if vol > avg else ("below" if vol < avg else "equal")
  ratio = _num(lt.get("volume_ratio")) if lt else None
  if ratio is None and vol is not None and avg:
    ratio = round(vol / avg, 2)
  out["volume"], out["volume_avg"], out["volume_vs"], out["volume_ratio"] = vol, avg, vs if vs in VS_ZH else None, ratio
  return out


def first_screen_cards(fs: dict) -> str:
  """R2 items 1 and 3 to 6 and the volume line.  Each readout has its label in words and a stable marker."""
  ret = fs["ret_1d"]
  price = (f'<div class="fs-v" data-f="close" data-v="{fs["close"]:.2f}">${fs["close"]:,.2f}</div>' if fs["close"] is not None else '<div class="fs-v2" data-f="close">收盤價暫缺</div>')
  change = (f'<div class="fs-s">單日漲跌 <b class="{"up" if ret >= 0 else "dn"}" data-f="ret-1d" data-v="{ret:.2f}">{ret:+.2f}%</b></div>' if ret is not None else "")
  if fs["watch_price"] is not None:
    watch = (f'<div class="fs-v" data-f="watch-price" data-v="{fs["watch_price"]:.2f}">${fs["watch_price"]:,.2f}</div><div class="fs-s">這個價位是：<b data-f="watch-kind">{_phrases(fs["watch_kind"])}</b></div>')
  else:
    watch = f'<div class="fs-v2" data-f="watch-kind">{esc(fs["watch_kind"])}</div>'
  if fs["crash"] is not None:
    crash = (f'<div class="fs-v"><span data-f="crash-score" data-v="{fs["crash"]:.1f}">{fs["crash"]:.1f}</span><small> / 100</small></div><div class="fs-s">區間：<b data-f="crash-zone">{esc(fs["crash_zone"])}</b></div>')
  else:
    crash = '<div class="fs-v2" data-f="crash-zone">崩跌指數暫缺：前兆系統這次沒有產生分數</div>'
  if fs["vix"] is not None:
    stale = "" if fs["vix_same_session"] or not fs["vix_date"] else f'<small data-f="vix-date" data-v="{esc(fs["vix_date"])}">（{esc(_mmdd(fs["vix_date"]))} 收盤）</small>'
    tone = " fs-spike" if fs["spike"] else ""
    state = {True: "spike", False: "no-spike"}.get(fs["spike"], "unknown")
    vix = (f'<div class="fs-v"><span data-f="vix" data-v="{fs["vix"]:.2f}">{fs["vix"]:.2f}</span>{stale}</div>'
           f'<div class="fs-s{tone}" data-f="spike-state" data-v="{state}">{esc(fs["spike_text"])}</div>'
           + (f'<div class="fs-note">{esc(fs["vix_note"])}</div>' if fs["vix_note"] else ""))
  else:
    vix = f'<div class="fs-v2" data-f="spike-state" data-v="unknown">{esc(fs["spike_text"])}</div>'
  if fs["volume"] is not None:
    shares = esc(report_chart.shares_zh(fs["volume"]))
    if fs["volume_vs"]:
      ratio = f'（<span data-f="volume-ratio">{fs["volume_ratio"]:.2f}</span> 倍）' if fs["volume_ratio"] is not None else ""
      volume = f'<div class="fs-v2"><span data-f="volume" data-v="{int(fs["volume"])}">{shares}</span>，<b data-f="volume-vs-avg" data-v="{fs["volume_vs"]}">{VS_ZH[fs["volume_vs"]]}</b> 20 日均量{ratio}</div>'
    else:
      volume = f'<div class="fs-v2"><span data-f="volume" data-v="{int(fs["volume"])}">{shares}</span>，20 日均量資料不足</div>'
  else:
    volume = '<div class="fs-v2">成交量資料暫缺</div>'
  emo = f'<span class="fs-emo">{esc(fs["rating_emoji"])}</span>' if fs["rating_emoji"] else ""
  aemo = f'<span class="fs-emo">{esc(fs["answer_emoji"])}</span>' if fs["answer_emoji"] else ""
  return (
      f'<section class="fs-cards" id="readouts" aria-label="重點讀數">'
      f'<div class="fs-card fs-verdict {fs["color"]}" data-r2="1" data-r2-name="verdict"><div class="fs-k">模型評級</div><div class="fs-v">{emo}<span data-f="rating-label">{esc(fs["rating"])}</span></div>'
      f'<div class="fs-k fs-k2">現在該不該買？</div><div class="fs-v">{aemo}<span data-f="buy-answer">{esc(fs["answer"])}</span></div><div class="fs-note">{BUY_NOTE}</div></div>'
      f'<div class="fs-card" data-r2="3" data-r2-name="price"><div class="fs-k">收盤價</div>{price}{change}</div>'
      f'<div class="fs-card" data-r2="4" data-r2-name="watch"><div class="fs-k">明天只盯一個價</div>{watch}</div>'
      f'<div class="fs-card" data-r2="5" data-r2-name="crash"><div class="fs-k">崩跌指數</div>{crash}</div>'
      f'<div class="fs-card" data-r2="6" data-r2-name="vix"><div class="fs-k">VIX 恐慌指數</div>{vix}</div>'
      f'<div class="fs-card fs-vol" data-readout="volume"><div class="fs-k">成交量</div>{volume}</div>'
      f'</section>')


def first_screen_data_line(fs: dict) -> str:
  """R2 item 2: the data date and the data status, and one plain line when a source failed."""
  miss = fs["missing_sources"]
  failed = f'<span class="fs-miss" data-f="data-missing" data-n="{len(miss)}">；缺 {len(miss)} 個來源：{esc("、".join(miss))}</span>' if miss else ""
  made = f'<span class="fs-made">｜產生 {esc(fs["generated_at"])}</span>' if fs["generated_at"] else ""
  return (f'<div class="fs-data" data-r2="2" data-r2-name="data">資料日期 <b data-f="data-date">{esc(fs["data_date"])}</b>｜資料狀態 <b data-f="data-status">{esc(fs["data_status"])}</b>{failed}{made}</div>')


PAGE_CSS = """
body{padding-top:12px}
.fs-top{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:2px 18px;margin-bottom:8px}
.fs-title{font-size:1.2rem;font-weight:900;white-space:nowrap}
.fs-data{font-size:.86rem;color:#cbd5e1}.fs-data b{color:#f8fafc}.fs-miss{color:#fbbf24}.fs-made{color:var(--mu)}
.fs{display:grid;grid-template-columns:330px minmax(0,1fr);gap:12px;align-items:start;margin-bottom:12px}
.fs-cards{display:grid;grid-template-columns:minmax(0,1fr);gap:8px}
.fs-card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:8px 12px 9px;min-width:0}
.fs-k{font-size:.8rem;color:var(--mu);font-weight:700}.fs-k2{margin-top:6px}
.fs-v{font-size:1.6rem;font-weight:900;line-height:1.25;font-variant-numeric:tabular-nums;text-wrap:balance}
.fs-v small{font-size:.86rem;color:var(--mu);font-weight:600}
.fs-v2{font-size:1rem;font-weight:700;line-height:1.4;color:#f1f5f9;text-wrap:balance}
.fs-s{font-size:.92rem;color:#e2e8f0;text-wrap:balance}.fs-s b{color:#f8fafc}.fs-s .up,.fs-v2 .up{color:#34d399}.fs-s .dn,.fs-v2 .dn{color:#fb7185}
.fs-spike{color:#fbbf24;font-weight:800}
.fs-note{font-size:.74rem;color:var(--mu);margin-top:1px}
.fs-emo{margin-right:6px}.fs-ph{display:inline-block}
.fs-verdict{border-width:2px}
.fs-verdict.bear{border-color:rgba(244,63,94,.6);background:linear-gradient(160deg,rgba(244,63,94,.24),rgba(244,63,94,.05))}
.fs-verdict.bull{border-color:rgba(16,185,129,.6);background:linear-gradient(160deg,rgba(16,185,129,.24),rgba(16,185,129,.05))}
.fs-verdict.neutral{border-color:rgba(245,158,11,.6);background:linear-gradient(160deg,rgba(245,158,11,.22),rgba(245,158,11,.05))}
.fs-status{margin:0 0 12px;border-left-color:#f59e0b}
@media(max-width:1199px){.fs{grid-template-columns:minmax(0,1fr)}.fs-cards{grid-template-columns:repeat(3,minmax(0,1fr))}.fs-verdict{grid-row:span 2}.fs-vol{grid-column:2/-1}}
@media(max-width:699px){.fs-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.fs-verdict{grid-row:auto;grid-column:1/-1}.fs-vol{grid-column:1/-1}.fs-v{font-size:1.4rem}.fs-title{font-size:1.05rem}.fs-data{font-size:.8rem}.fs-made{display:none}}
"""


def render(p: dict) -> str:
  """The whole page for one payload: the first screen, the evidence strip, the ten sections, the footer."""
  block = stress_chart.for_payload(p)
  fs = first_screen(p, block)
  ds = p.get("data_status") or {}
  # the short status is in the header line; the longer note of a provisional bar sits under the first screen, so the first screen keeps its size
  note = f'<div class="note fs-status" data-status-note>{report_sections.tx(ds.get("note"))}</div>' if ds.get("provisional") and ds.get("note") else ""
  css = report_html.CSS + report_chart.CSS + PAGE_CSS + report_sections.CSS
  return f'''<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{NONCE}'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none';">
<meta http-equiv="refresh" content="{REFRESH_SEC}">
<title>SOXL 投資決策儀表板 — {esc(fs["data_date"])}</title><style>{css}</style></head>
<body>
<header class="fs-top"><h1 class="fs-title">SOXL 投資決策儀表板</h1>{first_screen_data_line(fs)}</header>
<main class="fs" data-first-screen>{first_screen_cards(fs)}{report_chart.chart_html(block)}</main>
{note}
{report_chart.evidence_html(block)}
{report_sections.nav_html()}
{report_sections.sections_html(p)}
{report_sections.footer_html(p)}
<script nonce="{NONCE}">{report_sections.JS}{report_chart.JS}</script>
</body></html>'''


def write_pages(p: dict, base_dir: Path) -> list[Path]:
  """Render the page once and write it under its three names.  Returns the paths."""
  text = render(p)
  out = []
  for name in PAGE_FILES:
    path = Path(base_dir) / name
    fsio.atomic_write_text(path, text)
    out.append(path)
  return out
