# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-11-18**（美股交易日）· 產生 2026-11-19 02:42:30 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🔴 空頭 -17%/20日｜大戶：🟢 偏多 +0.39｜P/C：🟡 SOXL 0.68，個股第 93 百分位（恐慌）｜崩跌：🟡 77/100 注意

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：VIX/VIX3M 1.01 倒掛：歷史上這種狀態加碼的賠率最差，只能減碼或空手。
- 細節：跌破 $38.43 全出；反彈到 $52.53 / $53.65 先減
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 Trump Says Iran Looking at Gas, Bioweapons But Downplays Threat（Bloomberg）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 5.070%（-3.0 bps）；油 $58.02（-1.59%）；VIX 24.56（-3.53%）；美元 29.62（+0.27%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -17%/20日

- 讀數：空頭｜$141.85（+0.28%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -8.7%、20 日 -16.6%；距 20MA -7.2%、50MA -16.5%、200MA -11.8%；16 檔成分股站上 50MA 25.0%、200MA 25.0%；年線濾網：空手（出場線 $155.95）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🟢 大戶怎麼走：偏多 +0.39

- 讀數：偏多 +0.39｜大單 Call $32.73M vs Put $13.36M（50 筆）
- 一句話：大單權利金偏向 Call：大戶在買反彈或賣 Put 收權利金，和評級偏空時是分歧，值得盯但不是買點。
- 細節：最大單 2026-11-20 $50 Call $5.87M（看多 (買 Call)）；大戶 C/P 2.45 vs 散戶 C/P 0.43；SOXL/SOXS 資金流 2.2x（20 日均 2.45x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟡 Put/Call：SOXL 0.68，個股第 93 百分位（恐慌）

- 讀數：SOXL 成交 0.68（偏樂觀）｜全市場個股 0.72（1 年第 93 百分位）
- 一句話：恐慌區（個股 P/C 第 93 百分位）：底部常出現在這裡，但這是恐慌的證據不是買點，配合站回 20 日線才算。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.074；全市場總 P/C 1.05（偏避險 (0.9-1.1)）；個股 P/C 讀法 偏防禦 (0.70-0.85)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟡 崩跌指數：77/100 注意

- 讀數：77 / 100（注意）
- 一句話：分數進入注意區：盯 VIX 期限結構與派發日，不加碼。
- 細節：成立中的症狀：VIX 期限結構走平/倒掛 (VIX/VIX3M 0.88→1.00)、15 日內出現 3~6 個放量下跌『派發日』、VIX 從低檔 (≤18) 5 日急升 ＞25%；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；注意 (高於歷史 60~80%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | -0.15 | **C-** |
| 量能 | 14 | -0.64 | **D-** |
| 技術趨勢 | 26 | -1.12 | **F** |
| 廣度 | 10 | -1.60 | **F** |
| 宏觀 | 10 | +0.40 | **B** |
| 情緒 | 15 | +0.27 | **C+** |
| 消息 | 6 | -2.00 | **F** |

- 總評 **D**（綜合分 -0.60）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.60） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.59） | 🔴 空 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：3 空 / 1 中性 / 0 多 → 一致偏空，不加碼**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-11-18） | $141.85（+0.28%） |
| 5 日 / 20 日 | -8.72% / -16.62% |
| 20MA / 50MA / 200MA | $152.85（-7.20%） / $169.85（-16.50%） / $160.77（-11.80%） |
| 20 日高 / 低 | $173.98 / $131.90 |
| 距 52 週高 | -35.00% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | NVDA・分析・11/19 07:35 | [Nvidia Is Teaching The Market A Serious Lesson](https://seekingalpha.com/article/4969822-nvidia-is-teaching-the-market-a-serious-lesson?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/19 07:16 | [Nvidia Q3: Hasn't Been This Cheap In A Decade](https://seekingalpha.com/article/4969817-nvidia-q3-hasnt-been-this-cheap-in-a-decade?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/19 06:53 | [Nvidia Q3: Jensen Is Gone, The Momentum Is Not](https://seekingalpha.com/article/4969813-nvidia-q3-jensen-is-gone-the-momentum-is-not?source=feed_symbol_NVDA) |
| 利空 | NVDA・新聞・11/19 05:32 | [Nvidia declines, adding to evidence of an AI bubble destined to pop, says SA analyst](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/19 05:29 | [Nvidia: I Can See A Path Towards A $346 Price Post-Jensen Era](https://seekingalpha.com/article/4969787-nvidia-i-can-see-a-path-towards-a-346-price-post-jensen-era?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/19 04:56 | [Micron expects even tighter supply in 2027-28 than 2026; continues to work with Nvidia](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利多 | NVDA・分析・11/19 04:43 | [Nvidia's Q3 Earnings Say Buy The Stock, Not The Panic (Rating Upgrade)](https://seekingalpha.com/article/4969779-nvidias-q3-earnings-say-buy-the-stock-not-the-panic-rating-upgrade?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/19 04:26 | [Nvidia slides as interim CEO Kress speaks to employees, says, 'Let's move forward'](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
