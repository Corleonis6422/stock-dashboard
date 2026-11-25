# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-11-24**（美股交易日）· 產生 2026-11-25 04:24:17 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🔴 空頭 -24%/20日｜大戶：⚪ 資料不足｜P/C：🟢 SOXL None，個股第 33 百分位｜崩跌：🟡 64/100 注意

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：VIX/VIX3M 1.03 倒掛：歷史上這種狀態加碼的賠率最差，只能減碼或空手。
- 細節：跌破 $29.82 全出；反彈到 $39.89 / $46.44 先減
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 Houthi attack on Saudi Arabian sovereign wealth fund PIF's tower injures 11（CNBC）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 4.910%（-1.0 bps）；油 $57.75（+1.92%）；VIX 26.36（-0.98%）；美元 29.63（-0.50%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -24%/20日

- 讀數：空頭｜$128.62（-8.27%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -9.1%、20 日 -24.5%；距 20MA -12.4%、50MA -22.9%、200MA -20.2%；16 檔成分股站上 50MA 0.0%、200MA 0.0%；年線濾網：空手（出場線 $156.31）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### ⚪ 大戶怎麼走：資料不足

- 讀數：資料不足
- 一句話：CBOE 選擇權鏈沒有大單資料。
- 來源欄位：`options.whale`

### 🟢 Put/Call：SOXL None，個股第 33 百分位

- 讀數：SOXL 成交 None（n/a）｜全市場個股 0.57（1 年第 33 百分位）
- 一句話：中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C None；全市場總 P/C 0.95（偏避險 (0.9-1.1)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟡 崩跌指數：64/100 注意

- 讀數：64 / 100（注意）
- 一句話：分數進入注意區：盯 VIX 期限結構與派發日，不加碼。
- 細節：成立中的症狀：VIX 期限結構走平/倒掛 (VIX/VIX3M 0.88→1.00)、15 日內出現 3~6 個放量下跌『派發日』、布林通道寬度處 1 年高檔 (波動擴張)；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；注意 (高於歷史 60~80%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 16 | -0.50 | **D** |
| 量能 | 14 | -1.29 | **F** |
| 技術趨勢 | 26 | -1.54 | **F** |
| 廣度 | 10 | -2.00 | **F** |
| 宏觀 | 10 | +0.40 | **B** |
| 情緒 | 15 | +0.27 | **C+** |
| 消息 | 6 | -2.00 | **F** |

- 總評 **D-**（綜合分 -0.93）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.93） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.51） | 🔴 空 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：3 空 / 1 中性 / 0 多 → 一致偏空，不加碼**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-11-24） | $128.62（-8.27%） |
| 5 日 / 20 日 | -9.08% / -24.50% |
| 20MA / 50MA / 200MA | $146.75（-12.40%） / $166.85（-22.90%） / $161.15（-20.20%） |
| 20 日高 / 低 | $173.98 / $123.40 |
| 距 52 週高 | -41.10% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | NVDA・新聞・11/25 12:17 | [Trump says a pardon for Jensen Huang was "always an option": NY Post](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/25 05:50 | [SA Asks: What should Nvidia investors be watching for in the next few weeks?](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/25 03:48 | [Nvidia CEO says he has no succession plan during all-hands meeting: report](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/25 03:04 | [Nvidia: Ignore The Drama, The AI Factory Moat Is Widening](https://seekingalpha.com/article/4971559-nvidia-ignore-the-drama-the-ai-factory-moat-is-widening?source=feed_symbol_NVDA) |
| 利多 | NVDA・新聞・11/25 00:08 | [AI and chip stocks pull back sharply following Nvidia-driven rally](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | SOXX・分析・11/24 23:20 | [Beware, The AI Trade May Not Have Bottomed Yet](https://seekingalpha.com/article/4971464-beware-the-ai-trade-may-not-have-bottomed-yet?source=feed_symbol_SOXX) |
| 利多 | NVDA・分析・11/24 22:30 | [Nvidia And Its Real Value (Rating Upgrade)](https://seekingalpha.com/article/4971447-nvidia-and-its-real-value-rating-upgrade?source=feed_symbol_NVDA) |
| 利多 | NVDA・新聞・11/24 21:43 | [Nvidia CDS spreads surge as stock swings rattle markets](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
