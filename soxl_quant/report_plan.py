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
