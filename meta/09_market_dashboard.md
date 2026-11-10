# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-11-09**（美股交易日）· 產生 2026-11-10 03:41:11 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🔴 空頭 -19%/20日｜大戶：🟢 偏多 +0.47｜P/C：🟢 SOXL 0.681，個股第 40 百分位｜崩跌：🟢 43/100 低

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：評級偏空、吊燈移動停損已觸發：加碼就是攤平三倍槓桿，SOXL 單日可 ±15%。只能減碼或等買訊。
- 細節：反彈到 $57.51 / $59.73 先減碼；跌破 $41.39 全出
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 Trump after meeting with Qatari PM says he believes war with Iran is militarily 'effectively over'（AP News）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 4.880%（+2.0 bps）；油 $58.93（-5.29%）；VIX 19.92（-22.31%）；美元 28.97（-0.55%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -19%/20日

- 讀數：空頭｜$146.76（+7.49%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -3.0%、20 日 -19.2%；距 20MA -8.9%、50MA -15.3%、200MA -8.1%；16 檔成分股站上 50MA 25.0%、200MA 37.5%；年線濾網：空手（出場線 $154.92）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🟢 大戶怎麼走：偏多 +0.47

- 讀數：偏多 +0.47｜大單 Call $109.11M vs Put $44.35M（115 筆）
- 一句話：大單權利金偏向 Call：大戶在買反彈或賣 Put 收權利金，和評級偏空時是分歧，值得盯但不是買點。
- 細節：最大單 2027-05-21 $70 Put $12.78M（偏多 (Put 價跌量增)）；大戶 C/P 2.46 vs 散戶 C/P 0.39；SOXL/SOXS 資金流 2.59x（20 日均 2.72x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟢 Put/Call：SOXL 0.681，個股第 40 百分位

- 讀數：SOXL 成交 0.681（偏樂觀）｜全市場個股 0.56（1 年第 40 百分位）
- 一句話：中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.088；全市場總 P/C 0.88（中性 (0.75-0.9)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：43/100 低

- 讀數：43 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』、VIX 期限結構走平/倒掛 (VIX/VIX3M 0.88→1.00)、布林通道寬度處 1 年高檔 (波動擴張)；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | +0.05 | **C** |
| 量能 | 14 | -1.29 | **F** |
| 技術趨勢 | 26 | -1.19 | **F** |
| 廣度 | 10 | -2.00 | **F** |
| 宏觀 | 10 | +0.30 | **B** |
| 情緒 | 15 | +0.20 | **C+** |
| 消息 | 6 | -1.00 | **D-** |

- 總評 **D-**（綜合分 -0.67）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.67） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.26） | 🔴 空 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：3 空 / 1 中性 / 0 多 → 一致偏空，不加碼**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-11-09） | $146.76（+7.49%） |
| 5 日 / 20 日 | -2.95% / -19.19% |
| 20MA / 50MA / 200MA | $161.04（-8.90%） / $173.20（-15.30%） / $159.72（-8.10%） |
| 20 日高 / 低 | $181.30 / $131.90 |
| 距 52 週高 | -32.80% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 利空 | NVDA・新聞・11/10 06:31 | [NVIDIA slips 4% amid board probe into CEO allegations](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 05:04 | [Where To Buy The Dip](https://seekingalpha.com/article/4965290-where-to-buy-the-dip?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 03:00 | [Nvidia: The Jensen Affair Saga Is Just Noise](https://seekingalpha.com/article/4965209-nvidia-the-jensen-affair-saga-is-just-noise?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 02:56 | [Wall Street Lunch: Megaspeed In The Crosshairs](https://seekingalpha.com/article/4965212-wall-street-lunch-megaspeed-in-the-crosshairs?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 02:30 | [Nvidia: China Spy Saga Not Enough To Shake Me Off](https://seekingalpha.com/article/4965187-nvidia-china-spy-saga-not-enough-to-shake-me-off?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 02:00 | [Nvidia: Attractive Even Under Cautious Assumptions, Especially With This Strategy](https://seekingalpha.com/article/4965184-nvidia-attractive-even-under-cautious-assumptions-especially-with-this-strategy?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 01:00 | [The Midterm Elections Are Not A Risk For Nvidia, But Huang's News Is](https://seekingalpha.com/article/4965089-the-midterm-elections-are-not-a-risk-for-nvidia-but-huangs-news-is?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/10 00:30 | [Nvidia: Jensen Huang's Crisis Puts $5.5 Trillion To The Test](https://seekingalpha.com/article/4965050-nvidia-jensen-huang-crisis-puts-5-5-trillion-to-the-test?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
