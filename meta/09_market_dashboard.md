# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-10-28**（美股交易日）· 產生 2026-10-29 01:07:06 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🟡 先不加碼｜宏觀：🔴 偏空，有旗標｜費半：🟡 修正中 -8%/20日｜大戶：🟢 偏多 +0.47｜P/C：🟢 SOXL 0.813，個股第 63 百分位｜崩跌：🟢 25/100 低

## 六個儀表

### 🟡 SOXL 能不能加碼？：先不加碼

- 讀數：先不加碼
- 一句話：評級「觀望」：多空打平，沒有買訊。等收盤站回 20 日線 $120.93 或計畫的觸發條件成立再說。
- 細節：既有部位守 $94.28
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 US warns allies to prepare for possible Iran strikes, retaliation after elections, AP sources say（AP News）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 4.990%（-1.0 bps）；油 $69.67（-0.57%）；VIX 17.52（-4.73%）；美元 29.12（+0.38%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🟡 費半（SOXX）整體走向：修正中 -8%/20日

- 讀數：修正中｜$521.94（+2.13%）
- 一句話：費半在修正或反彈的半路：SOXL 的 3 倍槓桿會把這段震盪放大，只做有停損的單。
- 細節：5 日 +2.3%、20 日 -8.2%；距 20MA -2.0%、50MA -1.6%、200MA +9.9%；16 檔成分股站上 50MA 50.0%、200MA 56.2%；年線濾網：持有（出場線 $460.52）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🟢 大戶怎麼走：偏多 +0.47

- 讀數：偏多 +0.47｜大單 Call $46.88M vs Put $20.36M（47 筆）
- 一句話：大單權利金偏向 Call：大戶在買反彈或賣 Put 收權利金，和評級偏空時是分歧，值得盯但不是買點。
- 細節：最大單 2029-01-19 $220 Put $11.03M（偏多 (Put 價跌量增)）；大戶 C/P 2.3 vs 散戶 C/P 1.19；SOXL/SOXS 資金流 3.22x（20 日均 3.25x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟢 Put/Call：SOXL 0.813，個股第 63 百分位

- 讀數：SOXL 成交 0.813（中性）｜全市場個股 0.59（1 年第 63 百分位）
- 一句話：中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.517；全市場總 P/C 0.93（偏避險 (0.9-1.1)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：25/100 低

- 讀數：25 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』、布林通道寬度處 1 年高檔 (波動擴張)；分數 ≥ 80 的歷史命中率 12.3%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | +0.90 | **B+** |
| 量能 | 14 | -0.64 | **D-** |
| 技術趨勢 | 26 | -1.00 | **D-** |
| 廣度 | 10 | -1.00 | **D-** |
| 宏觀 | 10 | -0.20 | **C-** |
| 情緒 | 15 | +0.20 | **C+** |
| 消息 | 6 | +1.00 | **A** |

- 總評 **C-**（綜合分 -0.20）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 中立 / 觀望（綜合 -0.20） | 🟡 中性 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.36） | 🔴 空 |
| 費半趨勢（SOXX） | 修正中 | 🟡 中性 |

- **四個聲音：1 空 / 3 中性 / 0 多 → 沒有任何多方聲音：不加碼、不開新倉**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-10-28） | $521.94（+2.13%） |
| 5 日 / 20 日 | +2.27% / -8.21% |
| 20MA / 50MA / 200MA | $532.85（-2.00%） / $530.25（-1.60%） / $474.77（+9.90%） |
| 20 日高 / 低 | $589.51 / $475.69 |
| 距 52 週高 | -20.30% |
| 走向 | 修正中（年線上方，但 20 與 50 日線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | NVDA・新聞・10/29 03:01 | [Dept of Justice studying Nvidia's $12.9B acquisition of Hugging Face - Reuters](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/28 23:36 | [Nvidia says RTX Spark Windows laptops add new models, AI tools, and more](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・10/28 21:37 | [Nvidia May Actually Raise Its 70% Growth Guide In November](https://seekingalpha.com/article/4958511-nvidia-may-actually-raise-its-70-percent-growth-guide-in-november?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・10/28 21:30 | [Nvidia: Brace For The Worst](https://seekingalpha.com/article/4958219-nvidia-brace-for-the-worst?source=feed_symbol_NVDA) |
| 中性 | SOXL・新聞・10/28 19:26 | [Semiconductor stocks in focus after SK Hynix results; Micron, Nvidia top Quant list](https://seekingalpha.com/symbol/SOXL/news?source=feed_symbol_SOXL) |
| 中性 | NVDA・分析・10/28 16:54 | [Nvidia: Risk Building, Earnings Revisions Can Turn Negative](https://seekingalpha.com/article/4958366-nvidia-risk-building-earnings-revisions-can-turn-negative?source=feed_symbol_NVDA) |
| 利多 | NVDA・新聞・10/28 12:25 | [Indian trading apps roll out access to U.S. stocks, boosting retail demand for Nvidia, SpaceX, Apple](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | SOXX・分析・10/28 04:15 | [The Next 24 Hours Will Be Crucial For The End Of The Year](https://seekingalpha.com/article/4958058-the-next-24-hours-will-be-crucial-for-the-end-of-the-year?source=feed_symbol_SOXX) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
