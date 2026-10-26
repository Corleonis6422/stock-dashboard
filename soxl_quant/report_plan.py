#!/usr/bin/env python3
"""HTML fragments for the explicit trade plan and the validated-signal table.

Shared by the full report (report_html.py) and the beginner page (report_simple.py).
Pure functions: payload dict in, HTML string out.  Degrades to an explanatory note when
the backtest step did not run (payload lacks ``trade_plan`` / ``backtest``).
"""
from __future__ import annotations

import html


def _esc(v: object) -> str:
  return html.escape("" if v is None else str(v), quote=True)


def _usd(v, nd: int = 2) -> str:
  try:
    return f"${float(v):,.{nd}f}"
  except (TypeError, ValueError):
    return "n/a"


def _num(v, nd: int = 1, sign: bool = False, suffix: str = "") -> str:
  try:
    x = float(v)
  except (TypeError, ValueError):
    return "n/a"
  return (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}") + suffix


STATE_ZH = {"fired": "🔴 今日觸發", "recent": "🟠 10 日內觸發", "pending": "⏳ 待觸發", "off": "⚪ 未觸發"}
CSS = """
.tp-tbl{width:100%;border-collapse:collapse;font-size:.86rem;margin-top:8px}.tp-tbl th{text-align:left;font-size:.74rem;opacity:.75;padding:6px 8px;border-bottom:1px solid rgba(148,163,184,.35)}
.tp-tbl td{padding:7px 8px;border-bottom:1px solid rgba(148,163,184,.18);vertical-align:top}.tp-tbl td:first-child{white-space:nowrap;opacity:.8}
.tp-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}.tp-sig{min-width:560px}.tp-sig th,.tp-sig td:last-child,.tp-sig td:nth-child(3){white-space:nowrap}
.tp-head{font-weight:700;font-size:1.02rem;margin:4px 0 6px}.tp-note{font-size:.8rem;opacity:.8;line-height:1.6;margin-top:8px}.tp-ok{color:#22c55e}.tp-bad{color:#ef4444}
.tp-grade{display:inline-block;font-size:.7rem;padding:1px 6px;border-radius:999px;border:1px solid rgba(148,163,184,.5);margin-left:4px}
@media(max-width:640px){.tp-tbl{font-size:.8rem}.tp-tbl td,.tp-tbl th{padding:6px 5px}}
"""


def plan_card_html(p: dict, heading: str = "🧭 可執行的交易計畫") -> str:
  tp = p.get("trade_plan") or {}
  if not tp:
    return (f'<section class="card box"><h2>{heading}</h2><div class="tp-note">這次更新沒有產生交易計畫（回測步驟失敗或資料不足），請看上方三個價位與下一次更新。</div></section>')
  st, t1, t2, sz, ts, en = tp.get("stop") or {}, tp.get("t1") or {}, tp.get("t2") or {}, tp.get("size") or {}, tp.get("time_stop") or {}, tp.get("entry") or {}
  gate_ok = (tp.get("rr_blend") or 0) >= (tp.get("min_rr") or 1.5)
  gate = '<span class="tp-ok">✅ 達標</span>' if gate_ok else f'<span class="tp-bad">❌ 不足：進場價需 ≤ {_usd(tp.get("trade_if_entry"))}</span>'
  rows = [
      ("進場", _esc(en.get("rule"))),
      ("停損", f"<b>{_usd(st.get('price'))}</b>（{_num(st.get('dist_pct'), 1, True, '%')}；{'結構支撐' if st.get('kind') == 'structural' else _esc(st.get('k_atr')) + '×ATR14'}；新倉與舊倉唯一的出場價）"),
      ("目標 T1", f"{_usd(t1.get('price'))}（{_esc(t1.get('label'))}，{_num(t1.get('rr'), 2)}R）"),
      ("目標 T2", f"{_usd(t2.get('price'))}（{_esc(t2.get('label'))}，{_num(t2.get('rr'), 2)}R）"),
      ("風報比", f"加權 {_num(tp.get('rr_blend'), 2)}R（門檻 {_esc(tp.get('min_rr'))}R）{gate}"),
      ("倉位", f"{'觸發後 ' if tp.get('side') == 'no_trade' else ''}{_esc(sz.get('if_triggered_pct'))}% 帳戶 ＝ 每筆風險 {_esc(sz.get('risk_per_trade_pct'))}% ÷ 停損距離（評級上限 {_num(sz.get('verdict_cap_pct'), 0)}%）；連續 3 次停損 = {_esc(sz.get('three_stops_pct'))}%"),
      ("時間停損", _esc(ts.get("rule"))),
      ("失效條件", "；".join(_esc(x) for x in (tp.get("invalidation") or []))),
  ]
  trs = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
  why = "".join(f"<li>{_esc(e)}</li>" for e in (tp.get("explain") or [])[:4])
  hd = tp.get("holder") or {}
  holder = (f"<div class='tp-note'><b>已持有者</b>：{_esc(hd.get('verdict_action') or '')} 硬停損 {_usd(hd.get('hard_stop'))}（{_esc(hd.get('hard_stop_label'))}）；{_esc(hd.get('trail_note'))}。"
            + (f" 減碼點：{'、'.join(_usd(r.get('price')) + '（' + _esc(r.get('label')) + '）' for r in hd.get('reduce_into') or [])}。" if hd.get("reduce_into") else "")
            + f" {_esc(hd.get('edge_note'))}</div>")
  rg = tp.get("regime") or {}
  own, idx = rg.get("soxl_own") or {}, rg.get("underlying") or {}
  regime = ""
  if own and idx:
    regime = (f"<div class='tp-note'><b>200 日線濾網（兩種讀法）</b>：SOXL 自身 → {'持有' if own.get('in_market') else '空手'}（距年線 {_num(own.get('dist_pct'), 1, True, '%')}；9 年年化 {_num(own.get('cagr_pct'), 1)}%、切換 {own.get('switches')} 次）；"
              f"{_esc(idx.get('series'))} 指數 ±3% 帶 2 日確認 → {'持有' if idx.get('in_market') else '空手'}（距年線 {_num(idx.get('dist_pct'), 1, True, '%')}，出場線 {_usd(idx.get('exit_below'))}；年化 {_num(idx.get('cagr_pct'), 1)}%、最大回撤 {_num(idx.get('max_dd_pct'), 1)}%、切換 {idx.get('switches')} 次）。"
              f"{'兩種讀法今天不一致：長期持有者看指數那條，短線反彈單看 SOXL 自身。' if rg.get('agree') is False else ''}</div>")
  return (f'<style>{CSS}</style><section class="card box"><h2>{heading} <small>每個價位都說明來源；風報比不到門檻就寫明「不開新倉」</small></h2>'
          f'<div class="tp-head">{_esc(tp.get("headline"))}</div><table class="tp-tbl"><tbody>{trs}</tbody></table>'
          f'<ul class="tp-note">{why}</ul>{holder}{regime}</section>')


def signals_table_html(p: dict, heading: str = "🧪 訊號驗證：這些買賣點過去到底準不準？", limit: int = 10) -> str:
  bt = p.get("backtest") or {}
  sigs = bt.get("signals") or []
  if not sigs:
    return f'<section class="card box"><h2>{heading}</h2><div class="tp-note">這次更新沒有回測結果。</div></section>'
  sm = bt.get("summary") or {}
  meth = bt.get("method") or {}
  rank = {"A": 0, "B*": 1, "B": 2, "C": 3, "—": 4}
  shown = [s for s in sigs if (s.get("n") or 0) >= 20 or (s.get("today") or {}).get("state") in ("fired", "recent", "pending")]
  shown.sort(key=lambda s: (0 if (s.get("today") or {}).get("state") == "fired" else 1, rank.get(s.get("grade"), 4), s.get("p_value") or 1.0))
  trs = []
  for s in shown[:limit]:
    td = s.get("today") or {}
    st = STATE_ZH.get(td.get("state"), "⚪ 未觸發")
    pend = td.get("pending") or {}
    if td.get("state") == "pending" and pend.get("price") is not None:
      st += f" {_esc(pend.get('op') or '')}{_usd(pend.get('price'))}"
    dyn = s.get("dyn") or {}
    dyn_txt = f"<br><small>動態出場 {_num(dyn.get('win_pct'), 0)}% vs {_num(dyn.get('base_win_pct'), 0)}%</small>" if dyn and dyn.get("win_pct") is not None else ""
    side = "買" if s.get("side") == "long" else "賣"
    star = "★" if s.get("significant") else ""
    trs.append(f"<tr><td>{side} {_esc(s.get('short_name'))}<span class='tp-grade'>{_esc(s.get('grade'))}{star}</span></td>"
               f"<td>{_num(s.get('win_pct'), 0)}% vs {_num((s.get('base') or {}).get('win_pct'), 0)}%（N {s.get('n')}）{dyn_txt}</td>"
               f"<td>{_num(s.get('mean'), 1, True, '%')} / {s.get('horizon')} 日</td><td>{st}</td></tr>")
  note = (f"買進訊號的勝率 = 訊號後 h 日收高的比例，賣出訊號 = 收低的比例；旁邊永遠附同期基準。等級 A 可靠、B 尚可、B* 顯著但樣本外薄、C 無優勢；★ = 顯著高於基準（p &lt; 0.05）。"
          f"{sm.get('n_graded')} 個有樣本的訊號中 {sm.get('n_significant')} 個顯著，多重檢定校正後（BH q &lt; 0.10）剩 {sm.get('n_q_lt_10')} 個。"
          f"{'賣出訊號歷史上沒有一個優於基準，也沒有一個能預測 20 日內 ≥15% 回撤：停損是保險，不是預測。' if not sm.get('exits_predictive') else ''}"
          f" 樣本 {_esc(meth.get('sample'))}，非重疊交易，進場為訊號次日開盤。")
  return (f'<style>{CSS}</style><section class="card box"><h2>{heading} <small>固定規則、10 年 SOXL 日線、樣本外 40% 檢查</small></h2>'
          f'<div class="tp-wrap"><table class="tp-tbl tp-sig"><thead><tr><th>訊號</th><th>勝率 vs 基準（N）</th><th>平均報酬 / 期間</th><th>今日狀態</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
          f'<div class="tp-note">{note}</div></section>')


BEGIN_CSS = """
.bg-ans{font-size:1.25rem;font-weight:800;margin:4px 0 8px}.bg-ans small{font-size:.8rem;font-weight:500;opacity:.75;margin-left:6px}
.bg-list{list-style:none;padding:0;margin:0}.bg-list li{padding:7px 0;border-top:1px solid rgba(148,163,184,.18);font-size:.9rem;line-height:1.6}.bg-list li b{opacity:.85}
.nf-item{display:grid;grid-template-columns:1.4rem 1fr;gap:6px;padding:7px 0;border-top:1px solid rgba(148,163,184,.18);font-size:.88rem;line-height:1.55}
.nf-meta{font-size:.74rem;opacity:.7}.nf-why{font-size:.8rem;opacity:.85}.nf-item a{color:inherit;text-decoration:underline dotted}
.nf-bar{font-size:.84rem;margin:2px 0 6px}.nf-tag{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:999px;border:1px solid rgba(148,163,184,.45);margin-right:4px}
.nf-caution{font-size:.84rem;padding:6px 10px;border-left:3px solid #f59e0b;background:rgba(245,158,11,.08);margin-top:8px;border-radius:4px}
"""


def beginner_card_html(p: dict, heading: str = "🟢🔴 新手一眼看懂：現在該不該買？") -> str:
  """Same text as the Markdown block (brief._beginner_block), so the page and the brief never disagree."""
  from . import brief as briefmod
  sc, pb, tp = p.get("scoring") or {}, p.get("playbook") or {}, p.get("trade_plan") or {}
  b = pb.get("beginner") or {}
  flash = p.get("newsflash") or None
  today_ews = (p.get("early_warning") or {}).get("today") or {}
  try:
    bg = briefmod._beginner_block(sc, b, tp, b.get("plan") or {}, flash, [], today_ews, p.get("technicals") or {})
  except Exception as e:  # noqa: BLE001
    return f'<section class="card box"><h2>{heading}</h2><div class="tp-note">無法產生（{_esc(e)}）。</div></section>'
  buy = bg.get("buy") or {}
  w = bg.get("watch") or {}
  items = [
      ("今天最大的事", _esc(str(bg.get("biggest_thing") or "").replace("今天最大的事：", "", 1))),
      ("已持有的人", _esc(bg.get("holder"))),
      ("明天只盯一個價", f"<b>{_usd(w.get('price'))}</b>（{_esc(w.get('label'))}）" if w.get("price") else "沒有單一關鍵價位"),
      ("48 小時內風險", _esc("；".join(bg.get("risk_48h") or ["無"])) + "（排定事件見下方日曆）"),
  ]
  lis = "".join(f"<li><b>{k}：</b>{v}</li>" for k, v in items)
  return (f'<style>{BEGIN_CSS}</style><section class="card box"><h2>{heading} <small>先看這五行，其餘都是依據</small></h2>'
          f'<div class="bg-ans">{_esc(buy.get("emoji"))} {_esc(buy.get("answer"))}<small>依據 {_esc(buy.get("basis"))}</small></div>'
          f'<div class="tp-note" style="margin-top:0">{_esc(buy.get("text"))}</div><ul class="bg-list">{lis}</ul></section>')


def flash_card_html(p: dict, heading: str = "📰 今天發生了什麼（過去 36 小時，對 SOXL 的影響）", limit: int = 8) -> str:
  fl = p.get("newsflash") or {}
  if not fl:
    return f'<section class="card box"><h2>{heading}</h2><div class="tp-note">這次更新沒有抓到時事（新聞來源失敗或模組未執行）。</div></section>'
  cats = " ".join(f'<span class="nf-tag">{_esc(c.get("emoji"))}{_esc(c.get("category"))} {c.get("neg")}空/{c.get("pos")}多</span>' for c in (fl.get("by_category") or [])[:6])
  bar = (f'<div class="nf-bar">新聞氣壓 <b>{_esc(fl.get("label"))}</b>（淨影響 {_num(fl.get("net"), 2, True)}，{fl.get("n_relevant")} 則，抓取 {_esc(fl.get("fetched_at_tpe"))} 台北）<br>{cats}</div>')
  rows = []
  for r in (fl.get("top") or [])[:limit]:
    imp = r.get("impact") or 0
    dot = "🔴" if imp < 0 else ("🟢" if imp > 0 else "⚪")
    title = _esc(r.get("title"))
    if r.get("link"):
      title = f'<a href="{_esc(r["link"])}" target="_blank" rel="noopener noreferrer">{title}</a>'
    rows.append(f'<div class="nf-item"><div>{dot}</div><div>{_esc(r.get("emoji"))} <b>{_esc(r.get("category"))}</b> <span class="nf-meta">{_esc(r.get("time_tpe"))} 台北 · {_esc(r.get("publisher"))} · 影響 {imp:+d}</span><br>{title}'
                f'<div class="nf-why">→ {_esc(r.get("why_zh"))}</div></div></div>')
  cautions = "".join(f'<div class="nf-caution">⚠️ {_esc(c.get("text"))}<br><span class="nf-meta">依據：{_esc((c.get("evidence") or {}).get("publisher"))}「{_esc((c.get("evidence") or {}).get("title"))}」</span></div>' for c in (fl.get("cautions") or [])[:4])
  sa_items = fl.get("seeking_alpha") or []
  sa_html = ""
  if sa_items:
    lis = []
    for t in sa_items[:6]:
      imp = t.get("impact") or 0
      dot = "🔴" if imp < 0 else ("🟢" if imp > 0 else "⚪")
      title = _esc(t.get("title"))
      if t.get("link"):
        title = f'<a href="{_esc(t["link"])}" target="_blank" rel="noopener noreferrer">{title}</a>'
      lis.append(f'<div class="nf-item"><div>{dot}</div><div><span class="nf-meta">{_esc(t.get("symbol"))} · {_esc(t.get("kind"))} · {_esc(t.get("time_tpe"))} 台北 · {_esc(t.get("tone"))}</span><br>{title}</div></div>')
    sa_html = (f'<div class="nf-bar" style="margin-top:10px"><b>Seeking Alpha 觀點</b>（SOXL / SOXX / NVDA 近 72 小時；「分析」= 投稿作者意見，「新聞」= SA 新聞台）</div>{"".join(lis)}')
  err = f'<div class="tp-note">來源部分失敗：{_esc("；".join(str(e) for e in fl["errors"][:2]))}</div>' if fl.get("errors") else ""
  return (f'<style>{BEGIN_CSS}</style><section class="card box"><h2>{heading} <small>關鍵字規則分類，不是 AI 判讀；影響分 −2 到 +2</small></h2>{bar}{"".join(rows)}{sa_html}{cautions}{err}'
          f'<div class="tp-note">{_esc(fl.get("method"))} 這一區只是閱讀輔助，不改變 24 因子評級；交易計畫只把旗標當作警語。</div></section>')


DASH_CSS = """
.dz-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:8px}
@media(max-width:860px){.dz-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.dz-grid{grid-template-columns:1fr}}
.dz-tile{border:1px solid rgba(148,163,184,.25);border-radius:12px;padding:10px 12px;background:rgba(148,163,184,.06);min-width:0;overflow-wrap:anywhere;word-break:break-word}
.dz-tile.green{border-color:rgba(34,197,94,.55)}.dz-tile.yellow{border-color:rgba(245,158,11,.6)}.dz-tile.red{border-color:rgba(239,68,68,.6)}
.dz-t{font-size:.78rem;opacity:.8}.dz-v{font-size:1.05rem;font-weight:800;margin:3px 0;line-height:1.35;overflow-wrap:anywhere}.dz-m{font-size:.8rem;line-height:1.55;opacity:.9}
.dz-tile details{margin-top:6px;font-size:.76rem;opacity:.85;overflow-wrap:anywhere}.dz-tile summary{cursor:pointer;opacity:.75}.dz-tile code{font-size:.7rem;opacity:.8;white-space:normal;overflow-wrap:anywhere;word-break:break-all}
.dz-grades{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px}.dz-g{display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(148,163,184,.4);border-radius:999px;padding:2px 9px;font-size:.78rem}
.dz-g b{font-size:.9rem}.dz-g.gA b{color:#22c55e}.dz-g.gB b{color:#86efac}.dz-g.gC b{color:#cbd5e1}.dz-g.gD b{color:#f59e0b}.dz-g.gF b{color:#ef4444}
.dz-voices{margin-top:8px;font-size:.84rem}.dz-voices div{padding:5px 0;border-top:1px solid rgba(148,163,184,.18);display:flex;gap:8px;flex-wrap:wrap}.dz-voices span:first-child{opacity:.75;min-width:11em}
"""


def dashboard_card_html(p: dict, heading: str = "📟 六個儀表：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌") -> str:
  d = p.get("dashboard") or {}
  if not d.get("gauges"):
    return f'<section class="card box"><h2>{heading}</h2><div class="tp-note">這次更新沒有產生儀表（dashboard 步驟失敗）。</div></section>'
  tiles = []
  for g in d["gauges"]:
    fields = "、".join(f"<code>{_esc(f)}</code>" for f in (g.get("fields") or [])[:5])
    tiles.append(f'<div class="dz-tile {_esc(g.get("light"))}"><div class="dz-t">{_esc(g.get("emoji"))} {_esc(g.get("title"))}</div><div class="dz-v">{_esc(g.get("short") or g.get("value"))}</div>'
                 f'<div class="dz-m">{_esc(g.get("meaning"))}</div><details><summary>讀數與依據</summary>{_esc(g.get("value"))}<br>{_esc(g.get("detail"))}'
                 + (f'<br>⚠ {_esc(g.get("caveat"))}' if g.get("caveat") else "") + f'<br>欄位：{fields}</details></div>')
  grades = d.get("factor_grades") or []
  pills = "".join(f'<span class="dz-g g{_esc(str(x.get("grade"))[:1])}">{_esc(x.get("short"))} <b>{_esc(x.get("grade"))}</b></span>' for x in grades)
  pills += f'<span class="dz-g g{_esc(str(d.get("overall_grade"))[:1])}">總評 <b>{_esc(d.get("overall_grade"))}</b></span>'
  vc = d.get("voices") or {}
  tone_dot = {"bear": "🔴", "bull": "🟢", "neutral": "🟡"}
  voices = "".join(f'<div><span>{_esc(r.get("voice"))}</span><span>{tone_dot.get(r.get("tone"), "⚪")} {_esc(r.get("reading"))}</span></div>' for r in (vc.get("rows") or []))
  return (f'<style>{DASH_CSS}</style><section class="card box"><h2>{heading} <small>每格一個答案、一句為什麼，點「讀數與依據」看數字來源</small></h2>'
          f'<div class="dz-grid">{"".join(tiles)}</div>'
          f'<div class="tp-note" style="margin-top:12px"><b>因子等級</b>（借 Seeking Alpha 的 A+ … F 寫法；分數來自 24 因子評分表的 7 個類別，A+ ≥ +1.5、F < −1.0）</div><div class="dz-grades">{pills}</div>'
          f'<div class="tp-note"><b>{_esc(vc.get("summary"))}</b></div><div class="dz-voices">{voices}</div>'
          f'<div class="tp-note">{_esc(d.get("method"))}</div></section>')
