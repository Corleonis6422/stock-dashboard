#!/usr/bin/env python3
"""新手版 one-screen page (soxl_simple.html).

One question, one answer: 「SOXL 今天該買還是該賣？」  Everything on this page
is derived from the same JSON payload as the full dashboard, but reduced to the
handful of things a beginner needs: the verdict block, the buy/hold/sell ratio,
"what should *I* do" by situation, position cap, the two prices that matter,
the 10-day scenario odds, the top reasons, and a 120-day traffic-light history.

Security: no JavaScript at all (CSP script-src 'none'); every value is escaped
with html.escape(); no external resources are loaded.
"""

from __future__ import annotations

from .report_html import GLOSSARY, _meter_svg, _ratio_bar, _tw, esc, num

REFRESH_SEC = 1800  # an open tab re-reads the file every 30 min (auto-update rewrites it)
TONE_COL = {"bull": "#22c55e", "neutral": "#eab308", "bear": "#ef4444"}
TONE_ZH = {"bull": "偏多", "neutral": "中性", "bear": "偏空"}
TONE_EMOJI = {"bull": "🟢", "neutral": "🟡", "bear": "🔴"}
RATING_EMOJI = {1: "🔴🔴", 2: "🔴", 3: "🟡", 4: "🟢", 5: "🟢🟢"}


def _mmdd(d: str) -> str:
  return d[5:].replace("-", "/") if isinstance(d, str) and len(d) >= 10 else esc(d)


def lights_svg(lights: list[dict], hist: list[dict]) -> str:
  pts = [r for r in (lights or []) if r.get("close") is not None]
  if len(pts) < 5:
    return ""
  w, h = 760, 214
  pl, pr, pt, pb = 52, 70, 16, 44   # right gutter holds the latest-price tag
  cw, ch = w - pl - pr, h - pt - pb
  closes = [float(r["close"]) for r in pts]
  lo, hi = min(closes), max(closes)
  rng = (hi - lo) or 1.0
  n = len(pts)
  bw = cw / n

  def ypos(c: float) -> float:
    return pt + ch - (c - lo) / rng * ch

  bands = "".join(f'<rect x="{pl + i * bw:.1f}" y="{pt}" width="{bw + 0.6:.1f}" height="{ch}" fill="{TONE_COL[r["light"]]}" opacity="0.22" data-bg="1"/>' for i, r in enumerate(pts))
  path = " ".join(f"{pl + (i + 0.5) * bw:.1f},{ypos(float(r['close'])):.1f}" for i, r in enumerate(pts))
  by_date = {r["date"]: i for i, r in enumerate(pts)}
  dots = ""
  for rec in hist or []:
    i = by_date.get(rec.get("date"))
    if i is None or rec.get("close") is None:
      continue
    x, y = pl + (i + 0.5) * bw, ypos(float(rec["close"]))
    dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{TONE_COL.get(rec.get("color"), "#94a3b8")}" stroke="#0b1120" stroke-width="2"><title>{esc(rec.get("date"))} {esc(rec.get("verdict"))} ${num(rec.get("close"))}</title></circle>'
  # x labels: first / 1/3 / 2/3 / last
  xl = ""
  for i in sorted({0, n // 3, 2 * n // 3, n - 1}):
    xl += f'<text x="{pl + (i + 0.5) * bw:.1f}" y="{h - 14}" text-anchor="middle" fill="#94a3b8" font-size="11">{_mmdd(pts[i]["date"])}</text>'
  yl = (f'<text x="{pl - 6}" y="{pt + 10}" text-anchor="end" fill="#94a3b8" font-size="11">${hi:,.0f}</text>'
        f'<text x="{pl - 6}" y="{pt + ch}" text-anchor="end" fill="#94a3b8" font-size="11">${lo:,.0f}</text>')
  last = pts[-1]
  ly = min(max(ypos(float(last["close"])), pt + 8), pt + ch - 2)
  lc = float(last["close"])
  tag_txt = f"${lc:,.0f}" if lc >= 1000 else f"${lc:,.2f}"
  tag_fs = min(12.0, (pr - 14) / max(1.0, _tw(tag_txt, 1.0, bold=True)))
  tag = (f'<line x1="{pl + cw:.1f}" y1="{ypos(lc):.1f}" x2="{pl + cw + 6:.1f}" y2="{ly:.1f}" stroke="#f8fafc" stroke-width="1" data-qa-ok="1"/>'
         f'<text x="{pl + cw + 9:.1f}" y="{ly + 4:.1f}" fill="#f8fafc" font-size="{tag_fs:.1f}" font-weight="700">{esc(tag_txt)}</text>')
  legend = (f'<rect x="{pl}" y="{h - 8}" width="10" height="6" fill="{TONE_COL["bull"]}" opacity=".6"/><text x="{pl + 14}" y="{h - 2}" fill="#94a3b8" font-size="10">偏多</text>'
            f'<rect x="{pl + 50}" y="{h - 8}" width="10" height="6" fill="{TONE_COL["neutral"]}" opacity=".6"/><text x="{pl + 64}" y="{h - 2}" fill="#94a3b8" font-size="10">中性</text>'
            f'<rect x="{pl + 100}" y="{h - 8}" width="10" height="6" fill="{TONE_COL["bear"]}" opacity=".6"/><text x="{pl + 114}" y="{h - 2}" fill="#94a3b8" font-size="10">偏空</text>'
            f'<circle cx="{pl + 160}" cy="{h - 5}" r="4" fill="#94a3b8" stroke="#0b1120" stroke-width="1.5"/><text x="{pl + 168}" y="{h - 2}" fill="#94a3b8" font-size="10">完整模型每日評級（自動更新累積）</text>')
  return (f'<svg viewBox="0 0 {w} {h}" class="lights" role="img" aria-label="過去 {n} 天價格與技術燈號">{bands}'
          f'<polyline points="{path}" fill="none" stroke="#f8fafc" stroke-width="2"/>{dots}{xl}{yl}{tag}{legend}</svg>')


def _strip(hist: list[dict]) -> str:
  if not hist:
    return '<div class="small">尚無紀錄 — 第一次自動更新後開始累積。</div>'
  chips = ""
  for r in hist[-21:]:
    tone = r.get("color") or "neutral"
    chips += (f'<div class="chip {esc(tone)}" title="{esc(r.get("date"))} {esc(r.get("verdict"))} 收盤 ${num(r.get("close"))} 綜合 {num(r.get("composite"), 2, sign=True)}">'
              f'<div class="chip-d">{_mmdd(r.get("date", ""))}</div><div class="chip-e">{esc(RATING_EMOJI.get(r.get("rating_5"), "⚪"))}</div><div class="chip-p">${num(r.get("close"), 0)}</div></div>')
  return f'<div class="strip">{chips}</div>'


def _selfcheck(hist: list[dict]) -> str:
  rows = [r for r in (hist or []) if r.get("fwd_ret_5d") is not None]
  if len(rows) < 3:
    first = hist[0]["date"] if hist else "今天"
    return f'<div class="small">系統從 <b>{esc(first)}</b> 開始每天記錄評級；累積約兩週後，這裡會自動顯示「當天評級 vs 之後 5 / 10 天實際漲跌」的驗證表，讓你自己判斷這套評分準不準。</div>'
  body = ""
  for r in rows[-15:]:
    f5, f10 = r.get("fwd_ret_5d"), r.get("fwd_ret_10d")
    body += (f'<tr><td>{esc(r.get("date"))}</td><td>{esc(RATING_EMOJI.get(r.get("rating_5"), ""))} {esc(r.get("verdict"))}</td><td class="mono">{num(r.get("composite"), 2, sign=True)}</td>'
             f'<td class="mono {"up" if (f5 or 0) >= 0 else "dn"}">{num(f5, 1, suffix="%", sign=True)}</td><td class="mono {"up" if (f10 or 0) >= 0 else "dn"}">{num(f10, 1, suffix="%", sign=True, na="—")}</td></tr>')
  bear = [r for r in rows if (r.get("rating_5") or 3) <= 2]
  bull = [r for r in rows if (r.get("rating_5") or 3) >= 4]
  def _avg(xs):
    xs = [x["fwd_ret_5d"] for x in xs if x.get("fwd_ret_5d") is not None]
    return (sum(xs) / len(xs)) if xs else None
  summ = f'<div class="small">偏空評級後 5 日平均 {num(_avg(bear), 1, suffix="%", sign=True, na="n/a")}（{len(bear)} 次）· 偏多評級後 5 日平均 {num(_avg(bull), 1, suffix="%", sign=True, na="n/a")}（{len(bull)} 次）。樣本少時不要過度解讀。</div>'
  return f'<table class="tbl"><thead><tr><th>日期</th><th>當日評級</th><th>綜合</th><th>之後 5 天</th><th>之後 10 天</th></tr></thead><tbody>{body}</tbody></table>{summ}'


def _scenarios(pb: dict) -> str:
  out = ""
  for s in pb.get("scenarios") or []:
    tone = s.get("tone") or "neutral"
    prob = float(s.get("prob") or 0)
    title = str(s.get("title") or "")
    short = title.split("：", 1)[-1]
    out += (f'<div class="sc-row"><div class="sc-name">{esc(TONE_EMOJI.get(tone, ""))} {esc(short)}</div>'
            f'<div class="sc-bar"><div class="sc-fill" style="width:{max(prob, 2):.0f}%;background:{TONE_COL.get(tone, "#64748b")}"></div></div><div class="sc-pct">{prob:.0f}%</div></div>')
  return out


def _reasons(items: list[dict], up: bool) -> str:
  if not items:
    return '<li class="small">目前沒有明顯的理由</li>'
  out = ""
  for x in items[:3]:
    pts = x.get("pts")
    out += (f'<li><div class="rs-t"><b>{esc(x.get("metric"))}</b><span class="pts {"up" if up else "dn"}">{num(pts, 2, sign=True)}</span></div>'
            f'<div class="rs-v">{esc(x.get("value"))}</div><div class="rs-w">{esc(x.get("why"))}</div></li>')
  return out


CSS = """
:root{--bg:#070b14;--card:#0f172a;--card2:#131d33;--bd:#1e293b;--tx:#f1f5f9;--mu:#94a3b8;--acc:#38bdf8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Microsoft JhengHei","Segoe UI",Roboto,sans-serif;line-height:1.6;padding:16px 16px 60px;max-width:860px;margin:0 auto;font-size:16px}
a{color:var(--acc)}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;margin-bottom:14px}
h1{font-size:1.45rem;font-weight:900}.meta{font-size:.82rem;color:var(--mu);margin-top:4px}.meta b{color:#e2e8f0}
.btn{display:inline-block;background:#1e293b;color:#e2e8f0;padding:8px 14px;border-radius:999px;font-size:.85rem;font-weight:700;text-decoration:none;border:1px solid #334155}
.btn:hover{background:var(--acc);color:#070b14}
.auto{font-size:.82rem;padding:8px 12px;border-radius:10px;margin-bottom:14px;border:1px solid var(--bd);background:var(--card)}
.auto.on{border-color:rgba(16,185,129,.45)}.auto.off{border-color:rgba(245,158,11,.5)}.auto.err{border-color:rgba(244,63,94,.6)}
.auto code{background:#1e293b;padding:1px 6px;border-radius:5px;font-size:.78rem}
.hero{border-radius:18px;padding:26px 22px;text-align:center;border:2px solid;margin-bottom:14px}
.hero.bear{background:linear-gradient(160deg,rgba(244,63,94,.32),rgba(244,63,94,.08));border-color:rgba(244,63,94,.6)}
.hero.bull{background:linear-gradient(160deg,rgba(16,185,129,.32),rgba(16,185,129,.08));border-color:rgba(16,185,129,.6)}
.hero.neutral{background:linear-gradient(160deg,rgba(245,158,11,.30),rgba(245,158,11,.08));border-color:rgba(245,158,11,.6)}
.h-e{font-size:2.4rem;line-height:1}.h-t{font-size:2.5rem;font-weight:900;letter-spacing:2px;margin:6px 0}.h-s{font-size:1.02rem;color:#f8fafc;max-width:620px;margin:0 auto}
.h-m{display:flex;justify-content:center;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:.9rem;color:#e2e8f0}.h-m b{font-size:1.1rem}
.up{color:#34d399}.dn{color:#fb7185}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px 18px;margin-bottom:14px}
.card h2{font-size:1.05rem;font-weight:800;margin-bottom:10px;display:flex;flex-wrap:wrap;align-items:baseline;column-gap:8px;row-gap:2px}.nw{white-space:nowrap}
h1,.card h2,.h-s,.q-q,.lv-k,.lv-l,.sc-name,.rs-t b,.chip-d{text-wrap-style:balance}
.card h2 small{font-size:.78rem;color:var(--mu);font-weight:500}
.meter{width:100%;height:auto;display:block}
.meter-names{display:grid;grid-template-columns:repeat(5,1fr);text-align:center;font-size:.8rem;font-weight:600;color:#94a3b8;margin-top:2px}.meter-names span{white-space:nowrap}.meter-names span.on{color:#f8fafc;font-weight:800}
.chart-scroll{overflow-x:auto;overflow-y:hidden;border-radius:10px;-webkit-overflow-scrolling:touch}.chart-scroll>svg{min-width:620px}
.swipe{display:none;font-size:.72rem;color:var(--mu);text-align:right;margin:2px 2px 4px}@media(max-width:700px){.swipe{display:block}}
.lv>div,.two>*,.qa>*{min-width:0}
.ratio{display:flex;height:34px;border-radius:9px;overflow:hidden;font-size:.86rem;font-weight:800;margin:8px 0 4px}
.ratio div{display:flex;align-items:center;justify-content:center;white-space:nowrap;flex:1 1 0;min-width:max-content;padding:0 8px}
.r-sell{background:#ef4444;color:#fff}.r-hold{background:#64748b;color:#fff}.r-buy{background:#22c55e;color:#06281a}
.small{font-size:.8rem;color:var(--mu)}.mono{font-family:ui-monospace,Menlo,monospace}
.qa{display:grid;grid-template-columns:1fr;gap:10px}
.q{background:var(--card2);border:1px solid var(--bd);border-radius:12px;padding:12px 14px}.q-q{font-weight:800;color:#fbbf24;margin-bottom:4px}.q-a{font-size:.95rem}
.size-bar{position:relative;height:30px;background:#1e293b;border-radius:9px;overflow:hidden;margin:8px 0}
.size-fill{height:100%}.size-fill.bear{background:#ef4444}.size-fill.neutral{background:#eab308}.size-fill.bull{background:#22c55e}
.size-lbl{position:absolute;right:12px;top:0;line-height:30px;font-weight:900;font-family:ui-monospace,Menlo,monospace;font-size:1rem}
.lv{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.lv>div{background:var(--card2);border:1px solid var(--bd);border-radius:12px;padding:12px;text-align:center}
.lv .lv-k{font-size:.78rem;color:var(--mu)}.lv .lv-p{font-size:1.35rem;font-weight:900;font-family:ui-monospace,Menlo,monospace;margin:2px 0}.lv .lv-l{font-size:.76rem;color:#e2e8f0}
.lv .stop{border-top:3px solid #ef4444}.lv .t1{border-top:3px solid #eab308}.lv .t2{border-top:3px solid #22c55e}
.sc-row{display:grid;grid-template-columns:1fr 2fr 48px;gap:10px;align-items:center;margin:8px 0;font-size:.9rem}
.sc-bar{height:16px;background:#1e293b;border-radius:8px;overflow:hidden}.sc-fill{height:100%;border-radius:8px}.sc-pct{font-weight:800;font-family:ui-monospace,Menlo,monospace;text-align:right}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.rs{list-style:none}.rs li{padding:8px 0;border-bottom:1px solid rgba(30,41,59,.8);font-size:.9rem}.rs li:last-child{border-bottom:none}
.rs-t{display:flex;justify-content:space-between;gap:8px}.pts{font-family:ui-monospace,Menlo,monospace;font-weight:800}.rs-v{font-size:.8rem;color:#cbd5e1}.rs-w{font-size:.78rem;color:var(--mu)}
.case.bull{border-left:4px solid #22c55e}.case.bear{border-left:4px solid #ef4444}
.lights{width:100%;height:auto;display:block;border-radius:10px;background:#0b1120;margin:6px 0}
.strip{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.chip{width:58px;border-radius:8px;padding:5px 0;text-align:center;border:1px solid var(--bd);background:var(--card2)}
.chip.bear{border-color:rgba(244,63,94,.6);background:rgba(244,63,94,.14)}.chip.bull{border-color:rgba(16,185,129,.6);background:rgba(16,185,129,.14)}.chip.neutral{border-color:rgba(245,158,11,.6);background:rgba(245,158,11,.14)}
.chip-d{font-size:.7rem;color:var(--mu)}.chip-e{font-size:.95rem}.chip-p{font-size:.7rem;font-family:ui-monospace,Menlo,monospace}
.tbl{width:100%;border-collapse:collapse;font-size:.82rem;margin-top:6px}.tbl th{text-align:left;color:var(--mu);font-size:.74rem;padding:6px 8px;border-bottom:1px solid var(--bd)}.tbl td{padding:6px 8px;border-bottom:1px solid rgba(30,41,59,.7)}
.bul{padding-left:20px;font-size:.92rem}.bul li{margin:6px 0}
.rules li{margin:8px 0;font-size:.92rem}.rules b{color:#fbbf24}
details{margin-top:4px}summary{cursor:pointer;color:var(--acc);font-weight:700;font-size:.9rem;padding:6px 0}
.gloss{display:grid;grid-template-columns:230px 1fr;gap:6px 14px;font-size:.84rem;margin-top:8px}.gloss dt{font-weight:700;color:#fbbf24;word-break:keep-all}.gloss dd{color:#e2e8f0}
.foot{font-size:.76rem;color:var(--mu);text-align:center;margin-top:16px;line-height:1.7}
@media(max-width:640px){.two,.lv{grid-template-columns:1fr}.gloss{grid-template-columns:1fr}.h-t{font-size:2rem}.sc-row{grid-template-columns:1fr 44px;row-gap:4px}.sc-name{grid-column:1/-1}}
"""


def render(p: dict) -> str:
  from .report_plan import plan_card_html, signals_table_html  # local import: keeps this module importable alone
  tech, sc, pb = p["technicals"], p["scoring"], p["playbook"]
  b = pb.get("beginner") or {}
  cons = b.get("consensus") or sc.get("consensus") or {}
  plan = b.get("plan") or {}
  color = b.get("color") or "neutral"
  size = int(b.get("size_pct") or 0)
  size_tone = "bull" if size >= 50 else ("neutral" if size >= 25 else "bear")
  lights = p.get("light_history") or []
  hist = p.get("verdict_history") or []
  from .history import light_stats  # local import to avoid cycles at module import
  ls = light_stats(lights)
  sch = p.get("schedule") or {}
  warn = ""
  if p.get("warnings"):
    warn = f'<div class="auto err">⚠️ 這次有部分資料來源暫時抓不到（{esc("; ".join(p["warnings"]))}），其餘分析不受影響。</div>'
  ds = p.get("data_status") or {}
  if ds.get("provisional"):
    warn += f'<div class="auto {"on" if ds.get("final") else "off"}">{"⏱️" if ds.get("final") else "⚠️"} {esc(ds.get("note", ""))}</div>'
  data_label = ds.get("label") or "美股收盤"
  if sch.get("installed"):
    auto_cls, auto_txt = "on", f"🔄 已啟用每日自動更新：{esc(sch.get('weekday_text'))} {esc('、'.join(sch.get('times') or []))}（本機時間）· 下次 <b>{esc(sch.get('next_run_short') or 'n/a')}</b> · 這個分頁每 30 分鐘自動重新載入"
  else:
    auto_cls, auto_txt = "off", f"⏸ 尚未啟用每日自動更新 — 在終端機執行 <code>{esc(sch.get('install_cmd') or '.venv/bin/python auto_update.py install')}</code> 一次即可（之後每天美股收盤後自動重跑並通知你）"
  last = sch.get("last_run") or {}
  if last.get("status") == "error":
    auto_cls = "err"
    auto_txt += f'<br>❌ 上次自動更新（{esc(last.get("finished"))}）失敗：{esc(last.get("error"))}。目前顯示的是最近一次成功的結果。'
  ret = tech.get("ret_1d") or 0.0
  cl_days = f"{ls['days']} 個交易日（自 {_mmdd(ls['since'] or '')}）" if ls.get("current") else "n/a"
  watch = "".join(f"<li>{esc(w)}</li>" for w in (b.get("watch") or [])[:3])
  gloss = "".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in GLOSSARY)
  rr = plan.get("risk_reward")
  return f'''<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none';">
<meta http-equiv="refresh" content="{REFRESH_SEC}">
<title>SOXL 今天該買還是該賣？（新手版）— {esc(p["data_as_of"])}</title><style>{CSS}</style></head>
<body>
<header class="top"><div><h1>👶 SOXL 今天該買還是該賣？<span class="nw">（新手版）</span></h1>
<div class="meta">資料：<b>{esc(p["data_as_of"])}</b> {esc(data_label)} · 報告產生：<b>{esc(p["generated_at"])}</b> · 全部指標自動抓取（Nasdaq / CBOE / CNN / 美國財政部 / Google News）</div></div>
<a class="btn" href="soxl_analysis_report.html">看完整報告 ▸</a></header>
<div class="auto {auto_cls}">{auto_txt}</div>
{warn}
<section class="hero {esc(color)}">
  <div class="h-e">{esc(b.get("emoji", ""))}</div>
  <div class="h-t">{esc(b.get("verdict", ""))}</div>
  <div class="h-s">{esc(b.get("one_liner", ""))}</div>
  <div class="h-m"><span>現價 <b>${tech["close"]:,.2f}</b> <span class="{"up" if ret >= 0 else "dn"}">{ret:+.2f}%</span></span><span>綜合評分 <b>{sc["composite_score"]:+.2f}</b> / ±2</span><span>信心 <b>{esc(b.get("confidence", ""))}</b></span><span>底部檢核 <b>{esc(pb.get("checklist_passed", 0))}/{esc(pb.get("checklist_total", 8))}</b></span></div>
</section>

<section class="card"><h2>📊 評級儀表 <small>{len(sc.get("factors") or [])} 項指標加權投票，像分析師共識一樣看</small></h2>
  {_meter_svg(float(b.get("rating_pos") or sc.get("rating_pos") or 50), str(b.get("rating_label") or sc.get("rating_label")))}
  {_ratio_bar(cons)}
  <div class="small">🔴 偏空 {esc(cons.get("n_sell", 0))} 項 · 🟡 中性 {esc(cons.get("n_hold", 0))} 項 · 🟢 偏多 {esc(cons.get("n_buy", 0))} 項（共 {len(sc.get("factors") or [])} 項）。紅色超過一半＝不要買；綠色超過一半＋底部檢核 ≥6 才是買點。</div>
</section>

<section class="card"><h2>🙋 我該怎麼做？ <small>依你的狀況選一格看</small></h2>
  <div class="qa">
    <div class="q"><div class="q-q">我還沒買，現在能進場嗎？</div><div class="q-a">{esc(b.get("q_no_position", ""))}</div></div>
    <div class="q"><div class="q-q">我已經套牢 / 持有中，怎麼辦？</div><div class="q-a">{esc(b.get("q_holder", ""))}</div></div>
    <div class="q"><div class="q-q">那什麼時候才可以買？</div><div class="q-a">{esc(b.get("q_when", ""))}</div></div>
  </div>
</section>

<section class="card"><h2>🎚️ 現在最多放多少？ <small>佔你「原本打算投入 SOXL 的最大金額」的比例</small></h2>
  <div class="size-bar"><div class="size-fill {size_tone}" style="width:{max(size, 2)}%"></div><span class="size-lbl">{size}%</span></div>
  <div class="small">{esc(b.get("size_note", ""))}。不管燈號多綠，3 倍槓桿 ETF 都不要超過總資產的 10–15%。</div>
</section>

<section class="card"><h2>📍 只要記住三個價位</h2>
  <div class="lv">
    <div class="stop"><div class="lv-k">跌破就要跑（停損）</div><div class="lv-p">{num(plan.get("stop_price"), prefix="$")}</div><div class="lv-l">{esc(plan.get("stop_label", ""))}（{num(plan.get("stop_dist_pct"), 1, suffix="%", sign=True)}）</div></div>
    <div class="t1"><div class="lv-k">第一道關卡（反彈減碼點）</div><div class="lv-p">{num(plan.get("target1_price"), prefix="$")}</div><div class="lv-l">{esc(plan.get("target1_label", ""))}（{num(plan.get("target1_dist_pct"), 1, suffix="%", sign=True)}）</div></div>
    <div class="t2"><div class="lv-k">站上才算轉強</div><div class="lv-p">{num(plan.get("target2_price"), prefix="$")}</div><div class="lv-l">{esc(plan.get("target2_label", ""))}（{num(plan.get("target2_dist_pct"), 1, suffix="%", sign=True)}）</div></div>
  </div>
  <div class="small" style="margin-top:8px">進場條件：{esc(plan.get("entry", ""))}。第一目標 vs 停損的報酬/風險比 {esc(rr if rr is not None else "n/a")}。</div>
</section>

{plan_card_html(p)}
{signals_table_html(p)}

<section class="card"><h2>🎲 未來 10 天最可能怎麼走？ <small>歷史同類情境統計（{esc(pb.get("analog_reference") or "n/a")}）</small></h2>
  {_scenarios(pb)}
  <div class="small">機率來自過去 4 年 SOXL 出現「同樣情境」後 10 天的實際結果，不是預言；用它決定倉位大小，不是用來梭哈。</div>
</section>

<section class="card"><h2>🤔 為什麼是這個結論？ <small>影響分數最大的前三個理由</small></h2>
  <div class="two">
    <div class="card case bear" style="margin:0"><b>🐻 看空的理由</b><ul class="rs">{_reasons(b.get("bear_case") or [], False)}</ul></div>
    <div class="card case bull" style="margin:0"><b>🐂 看多的理由</b><ul class="rs">{_reasons(b.get("bull_case") or [], True)}</ul></div>
  </div>
</section>

<section class="card"><h2>🚦 過去 120 天的燈號 <small>價格技術燈號（背景色）＋ 完整模型每日評級（圓點）</small></h2>
  <div class="chart-scroll">{lights_svg(lights, hist)}</div>
  <div class="swipe">⇆ 圖表可左右滑動</div>
  <div class="small">目前價格燈號：{esc(TONE_EMOJI.get(ls.get("current"), ""))} {esc(TONE_ZH.get(ls.get("current"), "n/a"))}，已持續 {esc(cl_days)}。背景燈號只看價格（20/50/200 日均線、MACD、RSI、SuperTrend），可回溯；圓點是加入期權、情緒、資金流後的完整評級，從啟用自動更新那天起每天累積一顆。</div>
  <div style="margin-top:10px"><b style="font-size:.9rem">📅 每日評級紀錄</b>{_strip(hist)}</div>
  <details><summary>🧪 這套評級準不準？（事後驗證）</summary>{_selfcheck(hist)}</details>
</section>

<section class="card"><h2>👀 這週只要盯三件事</h2><ul class="bul">{watch}</ul></section>

<section class="card"><h2>🧯 新手三條鐵律</h2>
  <ol class="rules">
    <li><b>SOXL 是 3 倍槓桿：</b>費城半導體指數跌 10%，它大約跌 30%；而且長期震盪會「磨損」淨值，不適合無腦長抱。</li>
    <li><b>不要攤平：</b>紅燈時每往下買一次，就是把風險放大三倍。等燈號轉綠、檢核表 ≥6 項再分批進。</li>
    <li><b>先想停損再想獲利：</b>進場前就決定「跌破哪個價位出場」（上面第一個價位），並照做。</li>
  </ol>
</section>

<details class="card"><summary>📖 名詞小抄：看不懂的名詞點這裡</summary><dl class="gloss">{gloss}</dl></details>

<div class="foot">想看評分表、期權/情緒細節、崩跌復盤 → <a href="soxl_analysis_report.html">完整報告</a>。本頁為量化研究工具產生，不是投資建議；3 倍槓桿 ETF 風險極高，請自行判斷並控制部位。<br>重新產生：<span class="mono">.venv/bin/python analyze_soxl.py</span>；排程狀態：<span class="mono">.venv/bin/python auto_update.py status</span></div>
</body></html>'''
