#!/usr/bin/env python3
"""Meta / Muse pack — a self-contained folder of Markdown an AI agent can absorb whole.

``meta/`` is rebuilt on every pipeline run (and by ``auto_update.py meta``) from the same
brief dict that produces ``feed/latest.{json,md}``, so every number here is traceable to
``feed/latest.json``.  Layout (numbers give the reading order):

  README.md                 what this is, how to feed it to Muse, file map, refresh URLs
  llms.txt                  one-screen index for LLM agents (llms.txt convention)
  01_brief_today.md         today's one-page brief (identical to feed/latest.md)
  02_trade_plan.md          the plan card alone: side, trigger, stop, T1/T2, R:R, size, invalidation
  03_signals.md             all validated signals: rule, win rate vs base, N, p, grade, today's state, trigger price
  04_methodology.md         data sources, 24-factor scorecard, backtest protocol, grades, plan rules, regime grid, crash gauge, option walls
  05_glossary.md            plain-language definitions of every term the brief uses
  06_rules_for_agents.md    how an agent must read, quote and caveat these numbers (freshness, base rates, disclaimer)
  07_history.md             last 15 sessions: verdict, plan, realised 5 / 10-day returns
  prompts/*.md              ready-to-paste prompts (daily briefing, holder check, weekly review)
  data/latest.json          structured brief (schema soxl-quant-brief/2), data/schema.json, data/signals.json
  manifest.json             file list with sizes, data_as_of, generated_at, public URLs

Design rules (so any renderer, including a chat window, shows it the same way):
  plain Markdown only, ATX headings, dash bullets, tables with <= 4 columns, no HTML, no LaTeX,
  every file starts with a header block that states data_as_of and the source, every win rate
  is printed next to its base rate and N, and every file ends with the disclaimer.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from . import brief as briefmod
from . import fsio

BASE_DIR = Path(__file__).resolve().parent.parent
META_DIR = BASE_DIR / "meta"
DEFAULT_BASE_URL = briefmod.DEFAULT_BASE_URL

_f, _pct, _usd, _num = briefmod._f, briefmod._pct, briefmod._usd, briefmod._num


def _hdr(title: str, br: dict, purpose: str) -> str:
  return (f"# {title}\n\n"
          f"> 資料日 data_as_of **{br.get('data_as_of')}**（美股交易日）· 產生 {br.get('generated_at')} 台北 · 資料狀態 {(br.get('data_status') or {}).get('label') or 'n/a'} · "
          f"schema `{br.get('schema')}` · 來源 `feed/latest.json`\n>\n> {purpose}\n\n")


def _foot(br: dict) -> str:
  return f"\n---\n_{br.get('disclaimer')}_\n"


def _state_zh(state: str | None) -> str:
  return {"fired": "🔴 今日觸發", "recent": "🟠 10 日內觸發", "pending": "⏳ 待觸發", "off": "⚪ 未觸發"}.get(state or "", "⚪ 未觸發")


# --------------------------------------------------------------------------- #
# individual documents
# --------------------------------------------------------------------------- #
def doc_trade_plan(br: dict) -> str:
  tp = br.get("trade_plan") or {}
  v = br.get("verdict") or {}
  pr = br.get("price") or {}
  out = _hdr("02 今日交易計畫（單頁）", br, "只回答一件事：明天要不要做、在哪裡做、哪裡錯了就走。數字全部來自 `trade_plan` 區塊。")
  if not tp:
    return out + "這次更新沒有產生交易計畫（回測步驟失敗或資料不足）。請改讀 01_brief_today.md 的「行動計畫」。\n" + _foot(br)
  st, t1, t2, sz, ts, en = tp.get("stop") or {}, tp.get("t1") or {}, tp.get("t2") or {}, tp.get("size") or {}, tp.get("time_stop") or {}, tp.get("entry") or {}
  out += f"## {tp.get('headline')}\n\n"
  out += f"評級 {v.get('emoji')} **{v.get('label')}**（綜合 {_num(v.get('composite'), 2, True)}，倉位上限 {v.get('size_pct')}%）· 收盤 {_usd(pr.get('close'))}（{_pct(pr.get('ret_1d'))}）\n\n"
  out += "| 欄位 | 值 |\n|---|---|\n"
  out += f"| 方向 | `{tp.get('side')}`（long = 今日有驗證過的買訊成立；long_pending = 等觸發；no_trade = 不開新倉，下面是條件計畫） |\n"
  out += f"| 進場 | {en.get('rule')} |\n"
  out += f"| 停損（唯一出場價） | **{_usd(st.get('price'))}**（{_pct(st.get('dist_pct'), 1)}；{'結構支撐' if st.get('kind') == 'structural' else str(st.get('k_atr')) + '×ATR14'}） |\n"
  out += f"| 目標 T1 | {_usd(t1.get('price'))}（{t1.get('label')}，{_num(t1.get('rr'), 2)}R） |\n"
  out += f"| 目標 T2 | {_usd(t2.get('price'))}（{t2.get('label')}，{_num(t2.get('rr'), 2)}R） |\n"
  gate = "達標" if (tp.get("rr_blend") or 0) >= (tp.get("min_rr") or 1.5) else f"不足；同樣停損與目標下，進場價需 ≤ {_usd(tp.get('trade_if_entry'))}"
  out += f"| 加權風報比 | {_num(tp.get('rr_blend'), 2)}R（門檻 {tp.get('min_rr')}R，{gate}） |\n"
  out += f"| 倉位 | {'觸發後 ' if tp.get('side') == 'no_trade' else ''}{sz.get('if_triggered_pct')}% 帳戶 = 每筆風險 {sz.get('risk_per_trade_pct')}% ÷ 停損距離；評級上限 {_num(sz.get('verdict_cap_pct'), 0)}%；連續 3 次停損 = {sz.get('three_stops_pct')}% 帳戶 |\n"
  out += f"| 時間停損 | {ts.get('rule')} |\n"
  out += f"| 失效條件 | {'；'.join(tp.get('invalidation') or [])} |\n\n"
  out += "## 為什麼是這些價位\n\n" + "".join(f"- {e}\n" for e in tp.get("explain") or []) + "\n"
  hd = tp.get("holder") or {}
  out += "## 已持有者\n\n"
  if hd.get("verdict_action"):
    out += f"- {hd['verdict_action']}\n"
  out += f"- 硬停損 {_usd(hd.get('hard_stop'))}（{hd.get('hard_stop_label')}）；{hd.get('trail_note')}。\n"
  if hd.get("reduce_into"):
    out += "- 減碼點：" + "、".join(f"{_usd(r.get('price'))}（{r.get('label')}）" for r in hd["reduce_into"]) + "\n"
  out += f"- {hd.get('edge_note')}\n\n"
  if tp.get("signals_fired") or tp.get("signals_pending"):
    out += "## 相關訊號\n\n"
    for s in tp.get("signals_fired") or []:
      out += f"- 今日觸發：{s['short_name']}（等級 {s['grade']}，勝率 {s['win_pct']}% vs 基準 {s['base_win_pct']}%，N={s['n']}，p={s['p_value']}）\n"
    for s in tp.get("signals_pending") or []:
      out += f"- 待觸發：{s['short_name']}（等級 {s['grade']}）收盤 {s.get('op') or ''} {_usd(s.get('price'))}（距現價 {_pct(s.get('dist_pct'), 1)}）{'，' + s['needs'] if s.get('needs') else ''}\n"
    out += "\n"
  rg = tp.get("regime") or {}
  own, idx = rg.get("soxl_own") or {}, rg.get("underlying") or {}
  if own and idx:
    out += "## 200 日線濾網（兩種讀法）\n\n"
    out += f"- SOXL 自身：{'持有' if own.get('in_market') else '空手'}（距年線 {_pct(own.get('dist_pct'), 1)}；9 年年化 {_num(own.get('cagr_pct'), 1)}%、切換 {own.get('switches')} 次）\n"
    out += f"- {idx.get('series')} 指數（{idx.get('rule')}）：{'持有' if idx.get('in_market') else '空手'}（距年線 {_pct(idx.get('dist_pct'), 1)}，出場線 {_usd(idx.get('exit_below'))}、進場線 {_usd(idx.get('enter_above'))}；年化 {_num(idx.get('cagr_pct'), 1)}%、最大回撤 {_num(idx.get('max_dd_pct'), 1)}%、切換 {idx.get('switches')} 次）\n"
    out += f"- {'兩種讀法今天不一致：長期持有者看指數那條，短線反彈單看 SOXL 自身。' if rg.get('agree') is False else '兩種讀法今天一致。'}\n\n"
  out += f"方法：{tp.get('method')}\n"
  return out + _foot(br)


def doc_signals(br: dict, payload: dict | None = None) -> str:
  sigs = br.get("signals") or []
  val = br.get("validation") or {}
  meth, summ = val.get("method") or {}, val.get("summary") or {}
  out = _hdr("03 訊號驗證表（買點與賣點的歷史命中率）", br,
             "23 條固定規則在 10 年 SOXL 日線上的實測。**任何勝率都必須連同右邊的基準與 N 一起引用**；p 是單尾二項檢定（對基準），q 是 Benjamini-Hochberg 多重檢定校正。")
  out += f"樣本 {meth.get('sample')}（{meth.get('bars')} 根）· 進場 {meth.get('entry')} · 出場 {meth.get('exit')} · 非重疊交易 · 樣本外 {meth.get('oos')} · 信賴區間 {meth.get('ci')}\n\n"
  names = {s.get("key"): s.get("short_name") for s in sigs}
  fmt = lambda keys: "、".join(names.get(k, k) for k in keys) if keys else "無"  # noqa: E731
  out += f"摘要：{summ.get('n_graded')} 條有樣本的規則中 **{summ.get('n_significant')} 條**勝率顯著高於基準（p < 0.05），多重檢定校正後（q < 0.10）剩 **{summ.get('n_q_lt_10')} 條**；今日觸發 {fmt(summ.get('fired_today'))}；待觸發 {fmt(summ.get('pending'))}；有預測力的賣出訊號 {fmt(summ.get('exits_predictive'))}。\n\n"
  out += "## 等級與欄位\n\n- A 可靠：N ≥ 30、樣本外 N ≥ 10、樣本外勝率 ≥ 60% 且 ≥ 基準 + 5、獲利因子 ≥ 1.5、樣本內外差 ≤ 12、鄰近參數皆優於基準、p < 0.05\n- B 尚可：樣本外勝率 ≥ 基準 + 3 且獲利因子 ≥ 1.2\n- B* 顯著但樣本外薄：p < 0.05 但樣本外 N < 8\n- C 無優勢：有樣本但沒有贏過基準\n- — 樣本不足：N < 20\n- 買進訊號的「勝率」= 訊號後 h 日收盤高於進場的比例；賣出訊號的「勝率」= 收盤更低的比例（看它有沒有躲過下跌）\n\n"
  out += "## 買進訊號\n\n| 訊號 [等級] | 勝率 vs 基準（N） | 平均 / 期間 | 今日狀態 |\n|---|---|---|---|\n"
  for s in sigs:
    if s.get("side") != "long":
      continue
    st = _state_zh(s.get("state"))
    if s.get("state") == "pending" and s.get("pending"):
      st += f" 收盤 {s['pending'].get('op') or ''}{_usd(s['pending'].get('price'))}"
    tag = f"{s.get('grade')}{'★' if s.get('significant') else ''}"
    out += f"| {s.get('short_name')} [{tag}] | {_num(s.get('win_pct'), 1)}% vs {_num(s.get('base_win_pct'), 1)}%（{s.get('n')}）p={s.get('p_value')} | {_pct(s.get('mean'), 1)} / {s.get('horizon')} 日 | {st} |\n"
  out += "\n## 賣出 / 出場訊號\n\n| 訊號 [等級] | 勝率 vs 基準（N） | 20 日內回撤 ≥15% 比例 vs 基準 | 今日狀態 |\n|---|---|---|---|\n"
  for s in sigs:
    if s.get("side") != "exit":
      continue
    dd = s.get("dd15") or {}
    tag = f"{s.get('grade')}{'★' if s.get('significant') else ''}"
    out += f"| {s.get('short_name')} [{tag}] | {_num(s.get('win_pct'), 1)}% vs {_num(s.get('base_win_pct'), 1)}%（{s.get('n')}）p={s.get('p_value')} | {_num(dd.get('rate_pct'), 1)}% vs {_num(dd.get('base_pct'), 1)}% | {_state_zh(s.get('state'))} |\n"
  out += "\n## 反轉買點的動態出場（Connors 式：收盤站上 5 日線出場，最多 10 日）\n\n"
  out += f"這個出場規則本身只挑上漲日，所以基準勝率就有 {_num(summ.get('dyn_base_win_pct'), 1)}%；比較時請用這個基準，不要用上表的固定期間基準。\n\n| 訊號 | 動態出場勝率 vs 基準（N） | 平均 / 平均持有 | p |\n|---|---|---|---|\n"
  for s in sigs:
    d = s.get("dyn") or {}
    if d and d.get("win_pct") is not None:
      out += f"| {s.get('short_name')} | {_num(d.get('win_pct'), 1)}% vs {_num(d.get('base_win_pct'), 1)}%（{d.get('n')}） | {_pct(d.get('mean'), 2)} / {d.get('avg_bars')} 日 | {d.get('p_value')} |\n"
  out += "\n## 每條規則的定義\n\n"
  for s in sigs:
    out += f"- **{s.get('short_name')}**（`{s.get('key')}`，{s.get('family')}，{'買' if s.get('side') == 'long' else '賣'}，結算 {s.get('horizon')} 日）：{s.get('rule')}"
    if s.get("stop_k_atr"):
      out += f"；樣本內校準停損 {s['stop_k_atr']}×ATR"
    if s.get("last_signal"):
      out += f"；上次觸發 {s['last_signal'].get('date')}（{_pct(s['last_signal'].get('ret'), 1)}）"
    out += "\n"
  grid = val.get("regime_grid") or []
  if grid:
    bh = val.get("buy_hold") or {}
    out += "\n## 200 日線濾網比較（同一套規則，不同訊號來源；無交易成本）\n\n| 訊號來源 / 帶寬 / 確認 | 年化 % | 最大回撤 % | 切換次數 · 在場 % |\n|---|---|---|---|\n"
    for g in grid:
      out += f"| {g.get('series')} ±{_num(g.get('band_pct'), 0)}% {g.get('confirm_days')} 日 → {'持有' if g.get('in_market') else '空手'} | {_num(g.get('cagr_pct'), 1)} | {_num(g.get('max_dd_pct'), 1)} | {g.get('switches')} · {_num(g.get('time_in_market_pct'), 0)} |\n"
    out += f"| 買進抱牢 | {_num(bh.get('cagr_pct'), 1)} | {_num(bh.get('max_dd_pct'), 1)} | — |\n\n"
    out += f"{val.get('regime_note')}\n"
  return out + _foot(br)


def doc_methodology(br: dict) -> str:
  sc = br.get("scorecard") or {}
  val = br.get("validation") or {}
  meth = val.get("method") or {}
  cr = br.get("crash_risk") or {}
  es = (cr.get("event_study") or {}).get("stats_top_80") or {}
  out = _hdr("04 方法論：數字是怎麼算出來的", br, "讀完這份就知道每個欄位的來源、單位與極限。沒有任何手動輸入的數字。")
  out += """## 1. 標的與資料

- **SOXL**：Direxion 三倍做多半導體 ETF，追蹤 ICE 半導體指數（SOXX 為同指數的一倍 ETF）單日報酬的 3 倍。單日 ±15% 是常態，連續震盪會有複利耗損，所以它不是長期持有工具，而是有條件的趨勢 / 反彈工具。
- 日線：Nasdaq（10 年，拆股調整；2016 年收盤約 $3，2021 年 15:1 拆股已調整）。當天收盤後官方日線通常延後數小時，期間用 Nasdaq 即時報價補成「收盤即時報價補齊」的 K 線，下次更新自動換成官方數據。
- 期權：CBOE 延遲鏈（SOXL 全部到期日）→ Put/Call、各履約價未平倉、Gamma 曝險（GEX）、Put 牆 / Call 牆 / Gamma 翻正位、Max Pain、IV30、週 / 月預期波動（1σ）。
- 情緒：CNN Fear & Greed、CBOE VIX / VIX9D / VIX3M / VIX6M / VVIX / SKEW、CBOE 全市場與個股 Put/Call、SOXL vs SOXS 美元成交量。
- 廣度：16 檔成分股（NVDA、AVGO、AMD、TSM、MU、AMAT、LRCX…）站上 20 / 50 / 200 日線比例、加權日漲跌。
- 宏觀：美國財政部 10Y / 30Y 殖利率、Brent（BNO 代理）、美元（UUP 代理）、HYG、黃金、銅、比特幣與 SOXL 的 20 / 60 / 120 / 250 日相關。
- 新聞：Yahoo / Google News / Nasdaq / Seeking Alpha / CNBC / MarketWatch RSS，關鍵字分類為利多 / 利空 / 中性（不是 LLM 判讀）。
- 事件：Fed 官網 FOMC 日程、Nasdaq 財報日曆（成分股）、週 / 月選擇權到期、NYSE 休市。

全部免費、免金鑰；任一來源失敗只降級該區段並寫進 `warnings`。

## 2. 評級（verdict）

"""
  out += "24 個因子分 7 類加權投票，每個因子給 −2 … +2 分：\n\n| 類別 | 權重 |\n|---|---|\n"
  for c in sc.get("categories") or []:
    out += f"| {c.get('category')} | {c.get('weight')} |\n"
  out += """
- `composite` = 加權平均（−2 … +2）；`trend_score` 是趨勢面（均線、量能、廣度、宏觀），`contrarian_score` 是逆勢面（情緒、期權、消息）。
- 五級：強力買進 / 買進 / 觀望 / 賣出・減碼 / 強力賣出（`rating_5` 5 → 1）；新手版再用「底部檢核八項」微調文字與倉位上限（`size_pct`：通過 ≥ 8 項且偏多 100%，≥ 6 項 50%，≥ 3 項 25%，否則 10% 或 0%）。
- 評級是投票，不是指令；`consensus.{buy,hold,sell}_pct` 告訴你有多少權重站在哪一邊。

## 3. 訊號驗證（backtest）

"""
  out += f"- 樣本 {meth.get('sample')}（{meth.get('bars')} 根日線）；規則全部固定參數、不在執行期擬合。\n"
  out += f"- 進場 {meth.get('entry')}；出場 {meth.get('exit')}；一筆交易進行中不再開新倉（非重疊），所以 N 是獨立交易數。\n"
  out += f"- 基準 = 同一期間每一根 K 線做同樣的事得到的勝率（買進基準約 55%，賣出基準約 42%）。\n- 樣本外 = {meth.get('oos')}（規則事先固定，所以這是穩定性檢查，不是擬合 / 驗證切分）。\n"
  out += "- 統計：Wilson 95% 信賴區間；單尾精確二項檢定 p（勝場數 vs 基準機率）；Benjamini-Hochberg q 值（全部有樣本的規則一起校正）；逐年勝率；鄰近參數變體（例如 RSI(2) < 5 / < 15）。\n"
  out += "- 停損校準：每條買訊用**樣本內**勝利交易的最大逆向波動 75 分位（以 ATR14 計）當停損距離，再在**樣本外**重跑「停損 k×ATR、目標 1.5 倍停損距離、到期平倉」的模擬，報告樣本外勝率與每筆期望值（R）。\n"
  out += "- 反轉買點另外用 Connors 的動態出場（收盤站上 5 日線，最多 10 日）評估，並附同一出場規則的基準勝率（約 64%）。\n"
  out += "- 賣出訊號再用「訊號後 20 日內自次日開盤回撤 ≥ 15% 的比例」評分（這才是賣訊應該要躲過的事）。\n"
  out += f"- 等級定義：{meth.get('grades')}；加上 B*（p < 0.05 但樣本外 N < 8）。\n\n"
  out += """## 4. 交易計畫（trade_plan）

- 方向：今日有 A / B / B* 買訊成立 → `long`（次日開盤進場）；最近的驗證過觸發價在 8% 內 → `long_pending`（收盤站上才進）；否則 `no_trade`（仍印出條件計畫）。
- 停損只有一個價位：進場下方最近的結構支撐（近 10 日最低、價值區下緣 VAL、布林下軌、Put 牆），需距進場 ≥ 0.8×ATR14；太近就用 k×ATR14（k 來自該訊號的停損校準，預設 1.2）；永遠不緊於 4%。持有者的硬停損是同一個價位。
- 目標：T1 = 進場上方第一個 ≥ 1R 的壓力，T2 = 第一個 ≥ 2R 的壓力（壓力來自價位階梯：均線、Fib、VPVR、布林、Gamma 翻正位、Call 牆、1σ 區間）。階梯沒有就用合成 ATR 目標並標明。
- 風報比：加權 0.5·R(T1) + 0.5·R(T2) ≥ 1.5 才算可交易；不足就印出「進場價要 ≤ X 才值得」。
- 倉位：每筆冒 1% 帳戶風險 ÷ 停損距離 = 帳戶百分比，再受評級上限約束；同時印出「連續 3 次停損 = −3% 帳戶」。
- 時間停損：訊號的驗證期（h 日）或動態出場規則。
- 失效：收盤 < 停損、VIX/VIX3M ≥ 1.0、崩跌前兆分數 ≥ 80。
- 當 CBOE 即時價與收盤差 ≥ 2%（例如盤前跳空），以即時價為中心的 1σ 區間與 Gamma 翻正位會加 ※ 註記，且不拿來當目標或停損；履約價型的牆照用。

## 5. 200 日線濾網（regime）

Gayed 式年線切換：昨日訊號收盤 > 200 日均線就持有 SOXL，否則空手。同一套規則分別用 SOXL 自身與 SOXX 指數當訊號、0 / 3 / 5% 帶寬、1 / 2 日確認，整張表列在 03_signals.md。重點：用指數當訊號切換少、年化高；帶寬敏感度不單調，所以不要只記一個數字；沒有任何變體能把最大回撤壓到 −74% 以上。

## 6. 崩跌前兆（crash_risk）

"""
  out += f"21 項前兆（動能、量能、波動、宏觀、情緒、期權）加權成 0–100 的歷史百分位。≥ 60 注意、≥ 80 警戒。事件研究：分數 ≥ {_num(es.get('threshold'), 0)} 的日子裡，之後真的出現頂部型崩跌的比例 {_num(es.get('precision_pct'), 1)}%（基準 {_num(es.get('base_rate_pct'), 1)}%，提升 {_num(es.get('lift'), 2)} 倍，召回 {_num(es.get('recall_pct'), 1)}%，樣本 {(cr.get('event_study') or {}).get('n_episodes')} 次事件）。價格已在 200 日線下時，分數代表「壓力持續度」而非新頂部前兆。\n\n"
  out += """## 7. 期權牆與 Gamma

- Call 牆 / Put 牆 = 現價上方 / 下方未平倉與 Gamma 曝險最大的履約價；Gamma 翻正位 = 淨 GEX 由負轉正的價位（上方造市商對沖壓抑波動，下方放大波動）。
- 這些是用公開未平倉**推算**的模型值，不是觀察到的造市商部位；不同資料商會得到不同數字；每天 OI 結算後重算。
- 預期波動 = 期權價格隱含的 1σ 區間（週選 / 月選），不是預測；歷史上 SOXL 收在區間外的比例請看簡報。

## 8. 更新節奏與驗證

- 本機 launchd 週二～六 07:30 台北（美股收盤後）；GitHub Actions 在 UTC 22:15 / 00:30 備援。
- 每次更新都跑：`tools/qa_brief.py`（計畫算術、訊號統計一致、新鮮度、Markdown 形狀、每個數字可在 JSON 找到）、`tools/test_backtest.py`（無前視、去重疊、合成序列）、`tests/test_quote_labels.py`。
- 簡報的「自我驗證」會回填每日評級與計畫之後 5 / 10 日的實際報酬。
"""
  return out + _foot(br)


GLOSSARY = [
    ("SOXL / SOXS", "三倍做多 / 三倍做空半導體 ETF（追蹤 ICE 半導體指數單日報酬 ×3 / ×−3）。SOXX 是同指數的一倍 ETF。"),
    ("複利耗損（volatility decay）", "槓桿 ETF 每日重設，震盪市中漲跌抵銷後淨值仍下滑；SOXX 橫盤、SOXL 卻可能虧。"),
    ("ATR14", "14 日平均真實波幅，一天「正常」上下波動的尺度；SOXL 常在 8–12%。停損距離用它來定，而不是憑感覺。"),
    ("RVOL", "今日成交量 ÷ 20 日均量；≥ 1.2 才算有量。"),
    ("20MA / 50MA / 200MA", "20 / 50 / 200 日簡單移動平均；200MA 是年線，長線多空分界。"),
    ("EMA5 / EMA10", "5 / 10 日指數移動平均，極短線均線；反彈單的第一道壓力常在這裡。"),
    ("Fib 反彈位", "從波段高點跌到波段低點後，反彈 23.6% / 38.2% / 50% / 61.8% 的價位。"),
    ("VPVR POC / VAH / VAL", "半年成交量分布的最大成交價位（籌碼峰）、價值區上緣、價值區下緣。"),
    ("布林通道", "20 日均線 ± 2 倍標準差；%B 是價格在通道內的位置（0 = 下軌，1 = 上軌）。"),
    ("RSI(2) / RSI(14)", "2 日 / 14 日相對強弱；RSI(2) < 10 是 Connors 的極短線超賣定義。"),
    ("KD", "隨機指標 K / D；K < 20 由下穿 D 是低檔金叉。"),
    ("MACD 柱", "快慢線差的柱狀圖；由負翻正代表動能止跌。"),
    ("派發日（distribution day）", "O'Neil 定義：下跌 ≥ 0.2% 且成交量大於前一日 / 均量；25 日內累積多個代表法人出貨。"),
    ("跟進日（follow-through day）", "O'Neil 定義：20 日新低後的反彈嘗試第 4 日起，單日大漲且量增，代表新一輪上漲確認。"),
    ("吊燈出場（chandelier exit）", "22 日最高 − 3×ATR22 的移動停損，只上移不下移。"),
    ("Put 牆 / Call 牆", "現價下方 / 上方未平倉與 Gamma 曝險最大的履約價，常形成支撐 / 壓力（模型推算值）。"),
    ("Gamma 翻正位（gamma flip）", "淨 Gamma 曝險由負轉正的價位；上方造市商對沖會壓抑波動，下方會放大波動。"),
    ("GEX", "Gamma exposure，造市商對沖需求的估計（百萬美元 / 1% 變動）。"),
    ("Max Pain", "讓期權買方總損失最大的到期價位；到期前常被吸引，但離現價太遠時效果弱。"),
    ("IV30 / 預期波動", "30 日隱含波動率；1σ 預期波動 = 現價 × IV × √(天數/365)。"),
    ("P/C（Put/Call）", "賣權 / 買權成交量比；> 1 偏避險或看空，< 0.7 偏樂觀。"),
    ("大戶期權（whale）", "權利金 ≥ 25 萬美元的單筆成交；淨方向 = 看多權利金與看空權利金的差額比例。"),
    ("VIX / VIX3M / VIX9D / VVIX / SKEW", "30 天 / 3 個月 / 9 天隱含波動率、VIX 的波動率、尾部風險定價。VIX/VIX3M ≥ 1.0 = 期限結構倒掛 = 恐慌。"),
    ("CNN Fear & Greed", "0–100 情緒指數，< 25 極度恐懼、> 75 極度貪婪（逆勢指標）。"),
    ("廣度（breadth）", "16 檔成分股站上均線的比例；< 20% 代表板塊普跌。"),
    ("崩跌前兆分數", "21 項前兆的加權歷史百分位，0–100；≥ 60 注意、≥ 80 警戒。"),
    ("勝率 vs 基準", "勝率必須和同一期間隨機進場的勝率（基準）比；SOXL 長期上漲，買進基準約 55%，所以 60% 不算高。"),
    ("N、p、q", "N = 獨立交易數；p = 勝率高於基準純屬運氣的機率（< 0.05 算顯著）；q = 多重檢定校正後的 p（一次測 20 條規則，總會有一條碰巧好看）。"),
    ("樣本內 / 樣本外", "前 60% / 後 40% 的日期；兩段勝率差太多代表不穩。"),
    ("R（風險單位）", "進場價到停損價的距離；T1 1.3R 代表目標距離是停損距離的 1.3 倍。"),
    ("加權風報比", "0.5×R(T1) + 0.5×R(T2)，假設一半在 T1 出、一半在 T2 出；≥ 1.5 才值得做。"),
    ("時間停損", "到了期限還沒到目標就平倉，避免資金卡在不動的部位。"),
    ("200 日線濾網 / 帶寬 / 確認日", "年線上持有、年線下空手；帶寬 ±3% 與連續 2 日確認是為了減少假突破的來回切換。"),
    ("data_as_of / generated_at", "數字描述的美股交易日 / 檔案產生的台北時間；兩者不同是正常的。"),
]


def doc_glossary(br: dict) -> str:
  out = _hdr("05 名詞表（新手版）", br, "簡報與訊號表用到的每個名詞，一句話說清楚。")
  for term, desc in GLOSSARY:
    out += f"- **{term}**：{desc}\n"
  return out + _foot(br)


def _rule_examples(br: dict) -> str:
  """Good / bad sentence pairs built from today's numbers so the examples never go stale."""
  tp = br.get("trade_plan") or {}
  sigs = br.get("signals") or []
  o = br.get("options") or {}
  st = (tp.get("stop") or {}).get("price")
  lines = []
  dyn_sig = max((s for s in sigs if (s.get("dyn") or {}).get("win_pct") is not None and (s.get("dyn") or {}).get("n", 0) >= 20), key=lambda s: s["dyn"]["win_pct"], default=None)
  if dyn_sig:
    d = dyn_sig["dyn"]
    lines.append(f"- 壞：「{dyn_sig['short_name']} 勝率 {_num(d.get('win_pct'), 0)}%，很準。」 好：「{dyn_sig['short_name']} 用 5 日線出場的勝率 {_num(d.get('win_pct'), 0)}%，但那種出場規則的基準就是 {_num(d.get('base_win_pct'), 0)}%，N={d.get('n')}，p={d.get('p_value')}，等級 {dyn_sig.get('grade')}。」")
  ex = next((s for s in sigs if s.get("key") == "first_close_below_sma20"), None)
  if ex:
    lines.append(f"- 壞：「跌破 20 日線就該賣。」 好：「首破 20 日線後 {ex.get('horizon')} 日內收更低的比例 {_num(ex.get('win_pct'), 0)}%，基準 {_num(ex.get('base_win_pct'), 0)}%（N={ex.get('n')}）；它不是賣出預測，停損 {_usd(st)} 才是出場依據。」")
  if o.get("call_wall"):
    lines.append(f"- 壞：「Call 牆在 {_usd(o.get('call_wall'), 0)}，上不去。」 好：「Call 牆 {_usd(o.get('call_wall'), 0)}（OI {o.get('call_wall_oi'):,}）是用未平倉推算的壓力參考，會隨每天 OI 變動；它只是階梯上的一格，不是天花板。」")
  en, sz = tp.get("entry") or {}, tp.get("size") or {}
  if tp.get("side") == "no_trade":
    lines.append(f"- 壞：「現在很便宜可以買。」 好：「今天沒有驗證過的買訊成立，計畫是 no_trade；條件是 {en.get('rule')}，倉位 {sz.get('if_triggered_pct')}%，守 {_usd(st)}。」")
  elif tp.get("side") == "long_pending":
    lines.append(f"- 壞：「明天開盤就買。」 好：「計畫是 long_pending：{en.get('rule')}；沒觸發就不做，觸發後倉位 {sz.get('if_triggered_pct')}%，守 {_usd(st)}。」")
  else:
    lines.append(f"- 壞：「訊號出現，全部押進去。」 好：「{en.get('rule')}；倉位 {sz.get('if_triggered_pct')}%（每筆風險 {sz.get('risk_per_trade_pct')}%），守 {_usd(st)}，T1 {_usd((tp.get('t1') or {}).get('price'))}。」")
  return "\n".join(lines)


def doc_rules(br: dict, base: str) -> str:
  tp = br.get("trade_plan") or {}
  tldr = (br.get("verdict") or {}).get("tldr") or []
  reason = (tldr[1] if len(tldr) > 1 else "n/a").rstrip("。")
  ev48 = [e for e in ((br.get("events") or {}).get("upcoming") or []) if (e.get("days_ahead") or 99) <= 2]
  events48 = "；".join(f"{e.get('when_zh')} {e.get('label')}" for e in ev48) if ev48 else "無"
  examples = _rule_examples(br)
  out = _hdr("06 給 AI Agent 的解讀規則", br, "Muse 或任何 agent 轉述這份資料時必須遵守的規則；違反任何一條就會把研究參考講成投資建議。")
  out += f"""## 必守規則

1. **先看新鮮度**：`data_as_of` 必須等於最近一個已收盤的美股交易日（美東 16:00 後約 75 分鐘換日；週末與 NYSE 假日順延）。落後就先說「資料是 X 月 X 日的」，再給結論。最新版永遠在 `{base}feed/latest.json` 與 `{base}meta/`。
2. **盤中快照不是結論**：`data_status.provisional = true` 且 `final = false` 時，只能說「盤中暫時讀數」。
3. **評級是投票不是指令**：轉述 `verdict.label` 時一定帶 `composite`、`consensus` 三個百分比與 `size_pct`，並提醒三倍槓桿單日可 ±15%。
4. **價位優先於形容詞**：至少給三個數字：停損 `trade_plan.stop.price`、第一目標 `trade_plan.t1.price`、關鍵牆（`options.put_wall` / `call_wall` / `gamma_flip`）。`trade_plan.side = no_trade` 就直說「今天不開新倉，觸發價是 X」。
5. **勝率一定帶基準與 N**：寫成「勝率 64%（基準 55%，N=62，p=0.09）」。`significant = false` 的訊號不可以說「高勝率」。賣出訊號歷史上沒有預測力，只能用來決定減碼節奏，停損是保險。
6. **兩種 200 日線讀法可能不一致**：SOXL 自身 vs SOXX 指數。長期持有者看指數那條，短線反彈單看 SOXL 自身；不一致時兩個都講。
7. **期權牆是模型值**：由公開未平倉推算，不是觀察到的部位；CBOE 即時價與收盤差 ≥ 2% 時（簡報會加 ※），1σ 區間與 Gamma 翻正位會在下次更新改變。
8. **有變化才值得打擾**：`changes.verdict_changed = true`、`crash_risk.score` 跨過 60 / 80、48 小時內有 FOMC 或龍頭財報、`warnings` 非空、`trade_plan.side` 變成 `long` → 主動推；否則一句話即可。
9. **引用來源**：新聞附 `publisher` 與 `link`（在 JSON `news.top_bull[].link`），數字附 `data_as_of`。
10. **免責**：每次輸出都帶 `disclaimer`。

## 回答模板（三句話版）

> （1）今天 **{{verdict.label}}**：{{trade_plan.headline}}。（2）最重要的理由：{{verdict.tldr[1]}}。（3）要盯的價位：停損 {{trade_plan.stop.price}}、T1 {{trade_plan.t1.price}}、Gamma 翻正 {{options.gamma_flip}}。48 小時內：{{events.upcoming 內 days_ahead ≤ 2 的項目，沒有就寫「無」}}。{{disclaimer}}

今天套進去會是：

> （1）今天 **{(br.get('verdict') or {}).get('label')}**：{str(tp.get('headline', 'n/a')).rstrip('。')}。（2）最重要的理由：{reason}。（3）要盯的價位：停損 {_usd((tp.get('stop') or {}).get('price'))}、T1 {_usd((tp.get('t1') or {}).get('price'))}、Gamma 翻正 {_usd((br.get('options') or {}).get('gamma_flip'), 1)}。48 小時內：{events48}。

## 好句子與壞句子（數字取自今天的資料）

{examples}

## 哪個檔案回答哪個問題

| 問題 | 讀哪裡 |
|---|---|
| 今天該買還是該賣 | 02_trade_plan.md（或 `trade_plan`） |
| 為什麼 | 01_brief_today.md 的 TL;DR 與「什麼會改變結論」 |
| 這個買點歷史上準嗎 | 03_signals.md（或 `signals[]`） |
| 數字怎麼算 / 可信度 | 04_methodology.md、`validation` |
| 看不懂的名詞 | 05_glossary.md |
| 過去幾天說對了嗎 | 07_history.md、`history[]` |
"""
  return out + _foot(br)


def doc_history(br: dict) -> str:
  hist = br.get("history") or []
  ch = br.get("changes") or {}
  out = _hdr("07 最近 15 個交易日：評級、計畫與事後結果", br, "自我驗證。`fwd_ret_5d / 10d` 是該日收盤之後 5 / 10 個交易日的實際報酬，要等日期到了才會回填。")
  out += "| 日期 | 評級（綜合 / 倉位上限） | 收盤（日變動） | 之後 5 日 / 10 日 |\n|---|---|---|---|\n"
  for h in hist[-15:]:
    out += f"| {h.get('date')} | {h.get('emoji') or ''} {h.get('verdict')}（{_num(h.get('composite'), 2, True)} / {h.get('size_pct')}%） | {_usd(h.get('close'))}（{_pct(h.get('ret_1d'))}） | {_pct(h.get('fwd_ret_5d'), 1) if h.get('fwd_ret_5d') is not None else '待回填'} / {_pct(h.get('fwd_ret_10d'), 1) if h.get('fwd_ret_10d') is not None else '待回填'} |\n"
  hits, n, txt = briefmod._history_check(hist)
  out += f"\n- {txt}。\n- 與前一交易日：{'；'.join(ch.get('notes') or []) or 'n/a'}；連續同評級 {ch.get('same_verdict_streak_days')} 個交易日。\n"
  out += "- 從 2026-10-21 起每日紀錄也存了計畫（`history/verdicts.jsonl` 的 `plan_*` 欄位），之後會加上「T1 先到還是停損先到」的統計。\n"
  return out + _foot(br)


def doc_readme(br: dict, base: str, files: list[tuple[str, int]]) -> str:
  tp = br.get("trade_plan") or {}
  v = br.get("verdict") or {}
  pr = br.get("price") or {}
  summ = (br.get("validation") or {}).get("summary") or {}
  out = f"""# SOXL Quant → Meta AI（Muse）吸收包

> 這個資料夾是給 AI agent 整包讀的。全部是純 Markdown 加一份 JSON，沒有程式碼、沒有圖片、沒有金鑰。
> 每個美股交易日收盤後自動重建（台北 07:30 左右）；資料日 **{br.get('data_as_of')}**，產生 {br.get('generated_at')} 台北。

## 三十秒版

今天：{v.get('emoji')} **{v.get('label')}** · 收盤 {_usd(pr.get('close'))}（{_pct(pr.get('ret_1d'))}）· 綜合 {_num(v.get('composite'), 2, True)} · 倉位上限 {v.get('size_pct')}%
計畫：**{tp.get('headline', 'n/a')}** · 停損 {_usd((tp.get('stop') or {}).get('price'))} · T1 {_usd((tp.get('t1') or {}).get('price'))} · T2 {_usd((tp.get('t2') or {}).get('price'))} · 加權風報比 {_num(tp.get('rr_blend'), 2)}R

## 怎麼餵給 Muse（擇一）

1. **上傳整個 `meta/` 資料夾**（或壓縮檔）到 Muse 的專案 / 知識庫。檔名開頭的數字是建議閱讀順序；`README.md` 與 `llms.txt` 是索引。
2. **貼網址**：公開版在 `{base}meta/`（例如 `{base}meta/01_brief_today.md`、`{base}meta/data/latest.json`）。每天更新同一組網址，Muse 只要重新抓。
3. **貼內容**：把 `prompts/daily_briefing.md` 的提示連同 `01_brief_today.md` 一起貼進對話；提示已經包含解讀規則。

Muse 第一次吸收時請讓它讀 `06_rules_for_agents.md` 與 `05_glossary.md`（穩定內容），之後每天只需要 `01_brief_today.md`（或 `02_trade_plan.md`）與 `data/latest.json`。

## 檔案地圖

| 檔案 | 內容 | 更新 |
|---|---|---|
| `01_brief_today.md` | 今日一頁簡報：TL;DR、交易計畫表、價位階梯、訊號驗證、崩跌前兆、事件、什麼會改變結論、情緒籌碼、新聞、自我驗證 | 每日 |
| `02_trade_plan.md` | 只有計畫：方向、進場觸發、停損、T1/T2、風報比、倉位、時間停損、失效條件、持有者做法、兩種年線讀法 | 每日 |
| `03_signals.md` | 23 條買賣規則：定義、勝率 vs 基準、N、p、等級、今日狀態、觸發價；動態出場；200 日線濾網比較表 | 每日 |
| `04_methodology.md` | 資料來源、24 因子評級、回測協定、等級、計畫規則、崩跌前兆、期權牆 | 每日（文字穩定、數字更新） |
| `05_glossary.md` | {len(GLOSSARY)} 個名詞的新手定義 | 穩定 |
| `06_rules_for_agents.md` | agent 必守的 10 條解讀規則、回答模板、好壞句子對照、問題 → 檔案對照表 | 穩定 |
| `07_history.md` | 最近 15 個交易日的評級、計畫與事後 5 / 10 日報酬 | 每日 |
| `prompts/` | `first_time.md`（第一次附上 zip 時貼）、`daily_briefing.md`（每日三句話）、`holder_check.md`（持有者）、`weekly_review.md`（每週自我檢討） | 穩定 |
| `data/latest.json` | 結構化全部內容（schema `soxl-quant-brief/2`）；`data/schema.json` 欄位定義；`data/signals.json` 精簡訊號表 | 每日 |
| `manifest.json` / `llms.txt` | 檔案清單、大小、`data_as_of`、公開網址 | 每日 |

## 這包資料的誠實聲明

- 數字全部由公開資料自動計算；任何一份檔案裡的數字都能在 `data/latest.json` 找到同一個值（`tools/qa_brief.py` 每天驗證）。
- 回測結論目前是：{summ.get('n_graded')} 條有樣本的規則只有 {summ.get('n_significant')} 條勝率顯著高於基準，經多重檢定校正後 {summ.get('n_q_lt_10')} 條；{'所有賣出規則都不優於基準' if not summ.get('exits_predictive') else '有預測力的賣出規則：' + '、'.join(summ['exits_predictive'])}。所以計畫裡的停損是風險控制，不是預測。
- 三倍槓桿 ETF 單日可 ±15%；200 日線濾網的任何變體都沒有把最大回撤壓到 −74% 以內。
- 這是研究參考，不是投資建議。

## 怎麼重建這個資料夾

```bash
.venv/bin/python auto_update.py meta         # 用既有 feed/latest.json 重建 meta/（不重算模型）
.venv/bin/python auto_update.py meta --zip   # 同上，並打包成 ~/Downloads/soxl_meta_pack_<日期>.zip 方便上傳給 Muse
.venv/bin/python auto_update.py run          # 完整更新：抓資料 → 重算 → HTML → feed/ → meta/ → 推播 → git push
```

程式在 `soxl_quant/meta_pack.py`；完整專案說明見上一層的 `README.md` 與 `AGENTS.md`。

## 本次檔案

| 檔案 | 大小 |
|---|---|
"""
  for name, size in files:
    out += f"| `{name}` | {size / 1024:.1f} KB |\n"
  out += f"""
## English summary

`meta/` is a self-contained Markdown pack for an AI agent (Meta AI / Muse). Read `06_rules_for_agents.md` once, then `01_brief_today.md` (or `02_trade_plan.md`) every trading day; the structured twin is `data/latest.json` (schema `soxl-quant-brief/2`). Public copies live under `{base}meta/` and refresh daily after the US close. Every win rate is printed with its base rate and N; the trade plan carries one stop, two targets, a blended reward-to-risk gate (1.5), a risk-based size and explicit invalidation. Not investment advice.
"""
  return out + _foot(br)


def doc_llms_txt(br: dict, base: str) -> str:
  tp = br.get("trade_plan") or {}
  v = br.get("verdict") or {}
  return (f"# SOXL Quant daily brief (Meta / Muse pack)\n\n"
          f"> Automated research brief for SOXL (3x semiconductor ETF). data_as_of {br.get('data_as_of')}, generated {br.get('generated_at')} Asia/Taipei. Not investment advice.\n\n"
          f"Today: {v.get('emoji')} {v.get('label')} | composite {_num(v.get('composite'), 2, True)} | plan {tp.get('side')} | stop {_usd((tp.get('stop') or {}).get('price'))} | T1 {_usd((tp.get('t1') or {}).get('price'))} | T2 {_usd((tp.get('t2') or {}).get('price'))} | R:R {_num(tp.get('rr_blend'), 2)}\n\n"
          f"## Read in this order\n\n"
          f"- [Rules for agents]({base}meta/06_rules_for_agents.md): freshness, base rates, disclaimer (read once)\n"
          f"- [Today's brief]({base}meta/01_brief_today.md): one page, zh-TW\n"
          f"- [Trade plan]({base}meta/02_trade_plan.md): side, trigger, stop, T1/T2, R:R, size, invalidation\n"
          f"- [Signals]({base}meta/03_signals.md): 23 rules with win rate vs base, N, p, grade, today's state\n"
          f"- [Methodology]({base}meta/04_methodology.md)\n- [Glossary]({base}meta/05_glossary.md)\n- [History]({base}meta/07_history.md)\n"
          f"- [Structured JSON]({base}meta/data/latest.json) (schema soxl-quant-brief/2), [schema]({base}meta/data/schema.json)\n\n"
          f"## Optional\n\n- [Full report HTML]({base}soxl_analysis_report.html)\n- [Beginner HTML]({base}soxl_simple.html)\n- [RSS]({base}feed/rss.xml)\n")


PROMPTS = {
    "first_time.md": """# 提示：第一次附上 meta.zip 時貼這段

> 附件是 SOXL（三倍做多半導體 ETF）的量化簡報資料包。請先讀 README.md 和 06_rules_for_agents.md，照裡面的 10 條規則解讀，再讀 05_glossary.md 認識名詞。然後讀 01_brief_today.md 與 02_trade_plan.md，用三句話告訴我：今天該買、該賣還是觀望；最重要的理由；要盯的停損、T1 和期權牆價位。先確認 data_as_of 是最近一個已收盤的美股交易日，不是就先說資料是哪一天的。引用勝率一定連同基準與 N，賣出訊號不是預測。最後一行列 48 小時內的風險事件，並附免責聲明。之後我每天會給你新的 01_brief_today.md，請用同樣格式回答。

English version:

> The attachment is a quant brief pack for SOXL (3x semiconductor ETF). Read README.md and 06_rules_for_agents.md first and follow its 10 rules, then 05_glossary.md for terms. Then read 01_brief_today.md and 02_trade_plan.md and answer in three sentences: buy, sell or stay out today; the single most important reason; the stop, T1 and option-wall prices to watch. Check that data_as_of is the last completed US session and say so if it is not. Quote every win rate with its base rate and N; sell signals are not predictions. End with one line of risk events in the next 48 hours and the disclaimer. I will send a new 01_brief_today.md each day; answer in the same format.
""",
    "daily_briefing.md": """# 提示：每日三句話簡報

把下面這段和 `01_brief_today.md`（或 `data/latest.json`）一起貼給 Muse：

> 以下是今天自動產生的 SOXL 簡報。請先確認 data_as_of 是最近一個已收盤的美股交易日，不是就先告訴我資料是哪一天的。然後用新手聽得懂的話，三句以內回答：今天該買、該賣還是觀望？最重要的理由是什麼？要盯哪一個價位？請直接轉述「交易計畫」表的進場觸發、停損、T1/T2 與加權風報比；trade_plan.side 是 no_trade 就直說「今天不開新倉，觸發價是 X」。提到任何勝率都要連同基準與 N 一起講，significant=false 的不要說「高勝率」。最後用一行列出 48 小時內的風險事件，並附上免責聲明。
""",
    "holder_check.md": """# 提示：我已經持有 SOXL，怎麼辦

> 我持有 SOXL，成本 {{你的成本}}，部位佔總資產 {{百分比}}。請根據 02_trade_plan.md 的「已持有者」段落與 trade_plan.holder：告訴我硬停損價、移動停損是否已觸發、兩個減碼點，以及今天的評級是否要求減碼。不要預測方向；賣出訊號歷史上沒有預測力，只用停損與減碼節奏回答。如果 crash_risk.score ≥ 80 或 VIX/VIX3M ≥ 1.0，請特別標出。附免責聲明。
""",
    "weekly_review.md": """# 提示：每週自我檢討（週末用）

> 讀 07_history.md 與 data/latest.json 的 history[]。列出過去 5 個交易日每天的評級、計畫停損 / T1，以及已回填的 5 日報酬；算出方向正確的次數。再讀 03_signals.md，告訴我哪些訊號本週觸發過、它們的勝率 vs 基準與 N，以及有沒有任何一條是 significant=true。最後用兩句話說：模型本週哪裡說對、哪裡說錯，以及下週要盯的兩個價位（來自 trade_plan）。附免責聲明。
""",
}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build(br: dict, payload: dict | None = None, base_url: str | None = None) -> dict:
  base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
  META_DIR.mkdir(parents=True, exist_ok=True)
  (META_DIR / "data").mkdir(exist_ok=True)
  (META_DIR / "prompts").mkdir(exist_ok=True)
  docs: dict[str, str] = {
      "01_brief_today.md": _hdr("01 今日簡報", br, "與 `feed/latest.md` 逐字相同；Muse 每天至少讀這一份。") + briefmod.to_markdown(br),
      "02_trade_plan.md": doc_trade_plan(br),
      "03_signals.md": doc_signals(br, payload),
      "04_methodology.md": doc_methodology(br),
      "05_glossary.md": doc_glossary(br),
      "06_rules_for_agents.md": doc_rules(br, base),
      "07_history.md": doc_history(br),
      "llms.txt": doc_llms_txt(br, base),
  }
  for name, text in PROMPTS.items():
    docs[f"prompts/{name}"] = text
  docs["data/latest.json"] = json.dumps(br, ensure_ascii=False, indent=1) + "\n"
  docs["data/schema.json"] = json.dumps(briefmod.schema(), ensure_ascii=False, indent=1) + "\n"
  docs["data/signals.json"] = json.dumps({"data_as_of": br.get("data_as_of"), "method": (br.get("validation") or {}).get("method"), "summary": (br.get("validation") or {}).get("summary"),
                                          "signals": [{k: s.get(k) for k in ("key", "short_name", "side", "horizon", "n", "win_pct", "base_win_pct", "ci", "mean", "pf", "p_value", "q_value", "significant", "grade", "state", "pending")} for s in (br.get("signals") or [])],
                                          "regime_grid": (br.get("validation") or {}).get("regime_grid"), "disclaimer": br.get("disclaimer")}, ensure_ascii=False, indent=1) + "\n"
  written: list[tuple[str, int]] = []
  for name, text in docs.items():
    _check_markdown(name, text)
    fsio.atomic_write_text(META_DIR / name, text)
    written.append((name, len(text.encode("utf-8"))))
  readme = doc_readme(br, base, written)
  fsio.atomic_write_text(META_DIR / "README.md", readme)
  written.insert(0, ("README.md", len(readme.encode("utf-8"))))
  manifest = {
      "pack": "soxl-quant-meta-pack/1", "schema": br.get("schema"), "data_as_of": br.get("data_as_of"), "generated_at": br.get("generated_at"), "generated_at_tz": "Asia/Taipei",
      "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "base_url": base + "meta/", "read_order": ["06_rules_for_agents.md", "01_brief_today.md", "02_trade_plan.md", "03_signals.md", "04_methodology.md", "05_glossary.md", "07_history.md"],
      "files": [{"name": n, "bytes": s, "url": base + "meta/" + n} for n, s in written], "total_bytes": sum(s for _, s in written),
      "verdict": (br.get("verdict") or {}).get("label"), "plan_side": (br.get("trade_plan") or {}).get("side"), "disclaimer": br.get("disclaimer"),
  }
  fsio.atomic_write_text(META_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
  return {"dir": str(META_DIR), "files": written, "total_bytes": manifest["total_bytes"]}


def _check_markdown(name: str, text: str) -> None:
  """Fail loudly if a document breaks the pack's rendering rules (plain Markdown, <= 4-column tables, no HTML / LaTeX)."""
  if not name.endswith(".md"):
    return
  import re
  if re.search(r"<(?!https?://)[a-zA-Z/][^>\n]*>", text):
    raise ValueError(f"{name}: raw HTML tag")
  if "$$" in text or "\\frac" in text:
    raise ValueError(f"{name}: LaTeX")
  for line in text.splitlines():
    if line.startswith("|") and len(line.strip("|").split("|")) > 4 and not line.startswith("|---"):
      raise ValueError(f"{name}: table wider than 4 columns: {line[:60]}")
  if len(text.encode("utf-8")) > 120 * 1024:
    raise ValueError(f"{name}: over 120 KB")
