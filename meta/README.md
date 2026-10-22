# SOXL Quant → Meta AI（Muse）吸收包

> 這個資料夾是給 AI agent 整包讀的。全部是純 Markdown 加一份 JSON，沒有程式碼、沒有圖片、沒有金鑰。
> 每個美股交易日收盤後自動重建（台北 07:30 左右）；資料日 **2026-10-21**，產生 2026-10-22 21:27:52 台北。

## 三十秒版

今天：🔴 **減碼 / 觀望** · 收盤 $103.24（+5.83%）· 綜合 -0.67 · 倉位上限 25%
計畫：**⛔ 不開新倉：沒有驗證過的買點成立；下面是觸發後才執行的條件計畫** · 停損 $91.35 · T1 $120.00 · T2 $130.59 · 加權風報比 1.70R

## 怎麼餵給 Muse（擇一）

1. **上傳整個 `meta/` 資料夾**（或壓縮檔）到 Muse 的專案 / 知識庫。檔名開頭的數字是建議閱讀順序；`README.md` 與 `llms.txt` 是索引。
2. **貼網址**：公開版在 `https://corleonis6422.github.io/stock-dashboard/meta/`（例如 `https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md`、`https://corleonis6422.github.io/stock-dashboard/meta/data/latest.json`）。每天更新同一組網址，Muse 只要重新抓。
3. **貼內容**：把 `prompts/daily_briefing.md` 的提示連同 `01_brief_today.md` 一起貼進對話；提示已經包含解讀規則。

Muse 第一次吸收時請讓它讀 `06_rules_for_agents.md` 與 `05_glossary.md`（穩定內容），之後每天只需要 `01_brief_today.md`（或 `02_trade_plan.md`）與 `data/latest.json`。

## 檔案地圖

| 檔案 | 內容 | 更新 |
|---|---|---|
| `01_brief_today.md` | 今日一頁簡報：TL;DR、交易計畫表、價位階梯、訊號驗證、崩跌前兆、事件、什麼會改變結論、情緒籌碼、新聞、自我驗證 | 每日 |
| `02_trade_plan.md` | 只有計畫：方向、進場觸發、停損、T1/T2、風報比、倉位、時間停損、失效條件、持有者做法、兩種年線讀法 | 每日 |
| `03_signals.md` | 23 條買賣規則：定義、勝率 vs 基準、N、p、等級、今日狀態、觸發價；動態出場；200 日線濾網比較表 | 每日 |
| `04_methodology.md` | 資料來源、24 因子評級、回測協定、等級、計畫規則、崩跌前兆、期權牆 | 每日（文字穩定、數字更新） |
| `05_glossary.md` | 34 個名詞的新手定義 | 穩定 |
| `06_rules_for_agents.md` | agent 必守的 10 條解讀規則、回答模板、好壞句子對照、問題 → 檔案對照表 | 穩定 |
| `07_history.md` | 最近 15 個交易日的評級、計畫與事後 5 / 10 日報酬 | 每日 |
| `prompts/` | `first_time.md`（第一次附上 zip 時貼）、`daily_briefing.md`（每日三句話）、`holder_check.md`（持有者）、`weekly_review.md`（每週自我檢討） | 穩定 |
| `data/latest.json` | 結構化全部內容（schema `soxl-quant-brief/2`）；`data/schema.json` 欄位定義；`data/signals.json` 精簡訊號表 | 每日 |
| `manifest.json` / `llms.txt` | 檔案清單、大小、`data_as_of`、公開網址 | 每日 |

## 這包資料的誠實聲明

- 數字全部由公開資料自動計算；任何一份檔案裡的數字都能在 `data/latest.json` 找到同一個值（`tools/qa_brief.py` 每天驗證）。
- 回測結論目前是：18 條有樣本的規則只有 1 條勝率顯著高於基準，經多重檢定校正後 0 條；所有賣出規則都不優於基準。所以計畫裡的停損是風險控制，不是預測。
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
| `01_brief_today.md` | 8.8 KB |
| `02_trade_plan.md` | 4.0 KB |
| `03_signals.md` | 10.8 KB |
| `04_methodology.md` | 7.9 KB |
| `05_glossary.md` | 4.5 KB |
| `06_rules_for_agents.md` | 4.7 KB |
| `07_history.md` | 1.5 KB |
| `llms.txt` | 1.5 KB |
| `prompts/first_time.md` | 1.4 KB |
| `prompts/daily_briefing.md` | 0.8 KB |
| `prompts/holder_check.md` | 0.5 KB |
| `prompts/weekly_review.md` | 0.5 KB |
| `data/latest.json` | 73.3 KB |
| `data/schema.json` | 11.3 KB |
| `data/signals.json` | 10.9 KB |

## English summary

`meta/` is a self-contained Markdown pack for an AI agent (Meta AI / Muse). Read `06_rules_for_agents.md` once, then `01_brief_today.md` (or `02_trade_plan.md`) every trading day; the structured twin is `data/latest.json` (schema `soxl-quant-brief/2`). Public copies live under `https://corleonis6422.github.io/stock-dashboard/meta/` and refresh daily after the US close. Every win rate is printed with its base rate and N; the trade plan carries one stop, two targets, a blended reward-to-risk gate (1.5), a risk-based size and explicit invalidation. Not investment advice.

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
