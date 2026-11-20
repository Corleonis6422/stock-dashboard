# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-11-19**（美股交易日）· 產生 2026-11-20 02:28:32 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🔴 空頭 -13%/20日｜大戶：⚪ 資料不足｜P/C：🟡 SOXL None，個股第 93 百分位（恐慌）｜崩跌：🟡 67/100 注意

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：VIX/VIX3M 1.05 倒掛：歷史上這種狀態加碼的賠率最差，只能減碼或空手。
- 細節：跌破 $31.98 全出；反彈到 $46.04 / $50.12 先減
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 Oil prices edge higher as Houthi attacks on Riyadh raise supply concerns（Reuters）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 5.040%（-3.0 bps）；油 $58.84（+1.41%）；VIX 28.44（+15.80%）；美元 29.63（+0.03%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -13%/20日

- 讀數：空頭｜$137.95（-2.75%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -11.0%、20 日 -13.0%；距 20MA -9.1%、50MA -18.5%、200MA -14.3%；16 檔成分股站上 50MA 18.8%、200MA 18.8%；年線濾網：空手（出場線 $156.08）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### ⚪ 大戶怎麼走：資料不足

- 讀數：資料不足
- 一句話：CBOE 選擇權鏈沒有大單資料。
- 來源欄位：`options.whale`

### 🟡 Put/Call：SOXL None，個股第 93 百分位（恐慌）

- 讀數：SOXL 成交 None（n/a）｜全市場個股 0.72（1 年第 93 百分位）
- 一句話：恐慌區（個股 P/C 第 93 百分位）：底部常出現在這裡，但這是恐慌的證據不是買點，配合站回 20 日線才算。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C None；全市場總 P/C 1.05（偏避險 (0.9-1.1)）；個股 P/C 讀法 偏防禦 (0.70-0.85)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟡 崩跌指數：67/100 注意

- 讀數：67 / 100（注意）
- 一句話：分數進入注意區：盯 VIX 期限結構與派發日，不加碼。
- 細節：成立中的症狀：VIX 期限結構走平/倒掛 (VIX/VIX3M 0.88→1.00)、15 日內出現 3~6 個放量下跌『派發日』、布林通道寬度處 1 年高檔 (波動擴張)；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；注意 (高於歷史 60~80%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 16 | -0.50 | **D** |
| 量能 | 14 | -0.93 | **D-** |
| 技術趨勢 | 26 | -1.31 | **F** |
| 廣度 | 10 | -1.60 | **F** |
| 宏觀 | 10 | +0.10 | **C+** |
| 情緒 | 15 | +0.47 | **B** |
| 消息 | 6 | -2.00 | **F** |

- 總評 **D-**（綜合分 -0.77）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.77） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.54） | 🔴 空 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：3 空 / 1 中性 / 0 多 → 一致偏空，不加碼**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-11-19） | $137.95（-2.75%） |
| 5 日 / 20 日 | -10.99% / -13.00% |
| 20MA / 50MA / 200MA | $151.82（-9.10%） / $169.16（-18.50%） / $160.91（-14.30%） |
| 20 日高 / 低 | $173.98 / $131.90 |
| 距 52 週高 | -36.80% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | NVDA・新聞・11/20 06:54 | [Calif. AG serves Nvidia investigative subpoena over China issues](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/20 06:33 | [Nvidia Is Financing Its Own Demand, And The Fed Noticed](https://seekingalpha.com/article/4970324-nvidia-is-financing-its-own-demand-and-the-fed-noticed?source=feed_symbol_NVDA) |
| 利空 | NVDA・分析・11/20 06:11 | [Nvidia: Hold Your Horses (Double Downgrade)](https://seekingalpha.com/article/4970319-nvidia-hold-your-horses-double-downgrade?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/20 05:31 | [Nvidia: Rarely Been Cheaper, Yet Uncertainties Mount - Strong Buy Reiterated](https://seekingalpha.com/article/4970308-nvidia-rarely-been-cheaper-yet-uncertainties-mount-strong-buy-reiterated?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/20 04:37 | [Nvidia: The Worst Is Yet To Come](https://seekingalpha.com/article/4970298-nvidia-the-worst-is-yet-to-come?source=feed_symbol_NVDA) |
| 利多 | NVDA・分析・11/20 03:06 | [Nvidia: The CEO Is Gone, The Earnings Engine Isn't (Strong Buy) (Rating Upgrade)](https://seekingalpha.com/article/4970267-nvidia-the-ceo-is-gone-the-earnings-engine-isnt-strong-buy?source=feed_symbol_NVDA) |
| 中性 | SOXX・分析・11/20 02:31 | [Has Nvidia Peaked? TheTechTalk Podcast Episode 3](https://seekingalpha.com/article/4970246-has-nvidia-peaked-techtalk-podcast-episode-3?source=feed_symbol_SOXX) |
| 中性 | NVDA・分析・11/20 01:14 | [Nvidia Is Best Avoided For Now, In Our View](https://seekingalpha.com/article/4970206-nvidia-is-best-avoided-for-now-in-our-view?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
