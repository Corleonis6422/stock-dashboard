# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-11-05**（美股交易日）· 產生 2026-11-06 01:42:58 台北 · 資料狀態 收盤即時報價補齊 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🔴 空頭 -77%/20日｜大戶：🟡 中性 -0.19｜P/C：🟡 SOXL 0.487，個股第 5 百分位（自滿）｜崩跌：🟢 41/100 低

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：評級偏空、吊燈移動停損已觸發：加碼就是攤平三倍槓桿，SOXL 單日可 ±15%。只能減碼或等買訊。
- 細節：反彈到 $49.17 / $60.00 先減碼；跌破 $32.27 全出
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜📉 Dow drops 1,800 points; Nasdaq tumbles into correction territory on AI tech wreck: Live updates（CNBC）
- 一句話：整體風險偏好惡化：SOXL 的 Beta 約是大盤的 3 到 4 倍，大盤跌 1% 它常跌 3% 以上。
- 細節：10Y 4.900%（-5.0 bps）；油 $60.40（-8.64%）；VIX 16.61（-20.26%）；美元 28.90（-0.38%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -77%/20日

- 讀數：空頭｜$130.97（-70.92%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -74.5%、20 日 -76.8%；距 20MA -72.9%、50MA -74.7%、200MA -72.5%；16 檔成分股站上 50MA 12.5%、200MA 6.2%；年線濾網：持有（出場線 n/a）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🟡 大戶怎麼走：中性 -0.19

- 讀數：中性 -0.19｜大單 Call $108.13M vs Put $270.84M（231 筆）
- 一句話：大單方向不明顯：沒有誰在明顯站隊。
- 細節：最大單 2026-11-06 $45 Put $21.95M（避險/看空 (買 Put)）；大戶 C/P 0.4 vs 散戶 C/P 0.11；SOXL/SOXS 資金流 1.08x（20 日均 2.79x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟡 Put/Call：SOXL 0.487，個股第 5 百分位（自滿）

- 讀數：SOXL 成交 0.487（偏樂觀）｜全市場個股 0.44（1 年第 5 百分位）
- 一句話：自滿區：期權市場偏樂觀，對 3 倍槓桿不是好事。P/C 越低代表買 Put 避險越少。
- 細節：SOXL 未平倉 P/C 1.254；全市場總 P/C 0.8（中性 (0.75-0.9)）；個股 P/C 讀法 自滿/追多 (＜0.55)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：41/100 低

- 讀數：41 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』、布林通道寬度處 1 年高檔 (波動擴張)、VVIX ＞95 (波動率的波動升溫)；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | -0.60 | **D** |
| 量能 | 14 | -2.00 | **F** |
| 技術趨勢 | 26 | -1.23 | **F** |
| 廣度 | 10 | -2.00 | **F** |
| 宏觀 | 10 | +0.00 | **C** |
| 情緒 | 15 | +0.80 | **B+** |
| 消息 | 6 | -2.00 | **F** |

- 總評 **D-**（綜合分 -0.91）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.91） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.45） | 🔴 空 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：3 空 / 1 中性 / 0 多 → 一致偏空，不加碼**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-11-05） | $130.97（-70.92%） |
| 5 日 / 20 日 | -74.51% / -76.75% |
| 20MA / 50MA / 200MA | $482.60（-72.90%） / $518.00（-74.70%） / $477.04（-72.50%） |
| 20 日高 / 低 | $559.40 / $130.97 |
| 距 52 週高 | -80.00% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 利空 | SOXX・分析・11/06 06:17 | [Don't Buy The Dip: Semiconductors Have Much Further To Fall](https://seekingalpha.com/article/4963487-dont-buy-the-dip-semiconductors-have-much-further-to-fall?source=feed_symbol_SOXX) |
| 利空 | NVDA・新聞・11/06 05:15 | [NVIDIA drops 9%, now down for 2026](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | SOXX・分析・11/06 04:50 | [Maybe It's Time To Rush Outdoors Carrying Washtubs](https://seekingalpha.com/article/4963420-maybe-its-time-to-rush-outdoors-carrying-washtubs?source=feed_symbol_SOXX) |
| 中性 | SOXX・分析・11/06 04:02 | [AI Stocks Are Having The Sale Of The Year, But Avoid These](https://seekingalpha.com/article/4963381-ai-stocks-are-having-the-sale-of-the-year-but-avoid-these?source=feed_symbol_SOXX) |
| 利空 | NVDA・新聞・11/06 03:38 | [Nvidia chips lie stockpiled in Hong Kong amid China's import restrictions: Report](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利空 | NVDA・新聞・11/06 02:50 | [Nvidia repeating Cisco’s fatal dot-com playbook, George Noble warns](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | SOXL・新聞・11/06 01:30 | [Chip stocks under pressure: Twelve semiconductor names with oversold signals](https://seekingalpha.com/symbol/SOXL/news?source=feed_symbol_SOXL) |
| 利空 | NVDA・新聞・11/05 23:20 | [AI and chip stocks plunge in broad selloff on data center outlook](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
