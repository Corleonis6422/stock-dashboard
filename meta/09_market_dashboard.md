# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-10-23**（美股交易日）· 產生 2026-10-26 19:51:41 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🟡 修正中 -16%/20日｜大戶：🟢 偏多 +0.23｜P/C：🟡 SOXL 0.826，個股第 93 百分位（恐慌）｜崩跌：🟢 42/100 低

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：評級偏空、吊燈移動停損已觸發：加碼就是攤平三倍槓桿，SOXL 單日可 ±15%。只能減碼或等買訊。
- 細節：反彈到 $89.46 / $92.29 先減碼；跌破 $74.17 全出
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 Trump, Netanyahu and the politics of escalation against Iran（Financial Times）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 5.000%（+4.0 bps）；油 $70.99（+3.02%）；VIX 19.45（+2.21%）；美元 28.96（+0.21%）；10/28（三） FOMC 利率決議 10/27–28
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🟡 費半（SOXX）整體走向：修正中 -16%/20日

- 讀數：修正中｜$478.20（+0.53%）
- 一句話：費半在修正或反彈的半路：SOXL 的 3 倍槓桿會把這段震盪放大，只做有停損的單。
- 細節：5 日 -3.1%、20 日 -16.5%；距 20MA -11.7%、50MA -10.2%、200MA +1.3%；16 檔成分股站上 50MA 18.8%、200MA 50.0%；年線濾網：持有（出場線 $457.87）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🟢 大戶怎麼走：偏多 +0.23

- 讀數：偏多 +0.23｜大單 Call $52.17M vs Put $26.65M（47 筆）
- 一句話：大單權利金偏向 Call：大戶在買反彈或賣 Put 收權利金，和評級偏空時是分歧，值得盯但不是買點。
- 細節：最大單 2028-01-21 $21 Call $13.11M（偏多 (Call 價升量增)）；大戶 C/P 1.96 vs 散戶 C/P 0.46；SOXL/SOXS 資金流 2.38x（20 日均 3.34x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟡 Put/Call：SOXL 0.826，個股第 93 百分位（恐慌）

- 讀數：SOXL 成交 0.826（中性）｜全市場個股 0.67（1 年第 93 百分位）
- 一句話：恐慌區（個股 P/C 第 93 百分位）：底部常出現在這裡，但這是恐慌的證據不是買點，配合站回 20 日線才算。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.575；全市場總 P/C 0.93（偏避險 (0.9-1.1)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：42/100 低

- 讀數：42 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』、VIX 期限結構走平/倒掛 (VIX/VIX3M 0.88→1.00)、VVIX ＞95 (波動率的波動升溫)；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | -0.25 | **C-** |
| 量能 | 14 | -1.64 | **F** |
| 技術趨勢 | 26 | -1.35 | **F** |
| 廣度 | 10 | -1.60 | **F** |
| 宏觀 | 10 | +0.10 | **C+** |
| 情緒 | 15 | +0.47 | **B** |
| 消息 | 6 | -2.00 | **F** |

- 總評 **D-**（綜合分 -0.82）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.82） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.57） | 🔴 空 |
| 費半趨勢（SOXX） | 修正中 | 🟡 中性 |

- **四個聲音：2 空 / 2 中性 / 0 多 → 沒有任何多方聲音：不加碼、不開新倉**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-10-23） | $478.20（+0.53%） |
| 5 日 / 20 日 | -3.08% / -16.50% |
| 20MA / 50MA / 200MA | $541.45（-11.70%） / $532.57（-10.20%） / $472.04（+1.30%） |
| 20 日高 / 低 | $589.51 / $475.69 |
| 距 52 週高 | -27.00% |
| 走向 | 修正中（年線上方，但 20 與 50 日線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | NVDA・新聞・10/26 18:39 | [Jefferies sees semiconductor equipment growth through 2028](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利空 | NVDA・新聞・10/26 05:02 | [Musk warns of AI lending crunch after SpaceX closes $40B GPU financing](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利空 | SOXX・新聞・10/26 00:59 | [BTIG warns stocks may fall after midterms as credit risks mount](https://seekingalpha.com/symbol/SOXX/news?source=feed_symbol_SOXX) |
| 中性 | SOXX・新聞・10/25 23:57 | [U.S.-China AI rivalry forces countries to navigate competing technology blocs](https://seekingalpha.com/symbol/SOXX/news?source=feed_symbol_SOXX) |
| 中性 | NVDA・新聞・10/24 22:30 | [Notable analyst calls this week: Intel, Apple and Zoom among top picks](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利空 | SOXX・分析・10/24 20:30 | [The Great Semiconductor Pullback Looks Like A Generational Buying Opportunity](https://seekingalpha.com/article/4957053-great-semiconductor-pullback-looks-like-generational-buying-opportunity?source=feed_symbol_SOXX) |
| 利多 | SOXX・新聞・10/24 04:44 | [Semiconductors will rally by the end of the year, says SA analyst](https://seekingalpha.com/symbol/SOXX/news?source=feed_symbol_SOXX) |
| 中性 | SOXX・分析・10/23 22:43 | [Black October: What It Could Mean For Chip Manufacturers](https://seekingalpha.com/article/4956931-black-october-what-it-could-mean-for-chip-manufacturers?source=feed_symbol_SOXX) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
