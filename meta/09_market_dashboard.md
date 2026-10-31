# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-10-30**（美股交易日）· 產生 2026-10-31 00:56:33 台北 · 資料狀態 收盤即時報價補齊 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 偏空，有旗標｜費半：🔴 空頭 -20%/20日｜大戶：🔴 偏空 -0.56｜P/C：🟢 SOXL 0.837，個股第 62 百分位｜崩跌：🟢 32/100 低

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：評級偏空、吊燈移動停損已觸發：加碼就是攤平三倍槓桿，SOXL 單日可 ±15%。只能減碼或等買訊。
- 細節：反彈到 $79.90 / $91.38 先減碼；跌破 $63.88 全出
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜📉 US stocks end sharply lower as AI cash burn fears spark tech selloff（Reuters）
- 一句話：整體風險偏好惡化：SOXL 的 Beta 約是大盤的 3 到 4 倍，大盤跌 1% 它常跌 3% 以上。
- 細節：10Y 4.980%（-7.0 bps）；油 $70.76（+0.88%）；VIX 17.20（+1.71%）；美元 29.04（-0.07%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -20%/20日

- 讀數：空頭｜$471.51（-8.24%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -1.4%、20 日 -19.9%；距 20MA -10.0%、50MA -10.9%、200MA -1.0%；16 檔成分股站上 50MA 18.8%、200MA 43.8%；年線濾網：持有（出場線 n/a）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🔴 大戶怎麼走：偏空 -0.56

- 讀數：偏空 -0.56｜大單 Call $124.5M vs Put $99.21M（178 筆）
- 一句話：大單權利金偏向 Put：大戶在避險或押跌，和空頭評級同向。
- 細節：最大單 2029-01-19 $45 Put $22.35M（偏空 (Put 價升量增)）；大戶 C/P 1.25 vs 散戶 C/P 0.43；SOXL/SOXS 資金流 3.08x（20 日均 3.19x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟢 Put/Call：SOXL 0.837，個股第 62 百分位

- 讀數：SOXL 成交 0.837（中性）｜全市場個股 0.58（1 年第 62 百分位）
- 一句話：中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.63；全市場總 P/C 0.85（中性 (0.75-0.9)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：32/100 低

- 讀數：32 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』、布林通道寬度處 1 年高檔 (波動擴張)、VVIX ＞95 (波動率的波動升溫)；分數 ≥ 80 的歷史命中率 12.3%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | -1.00 | **D-** |
| 量能 | 14 | -1.07 | **F** |
| 技術趨勢 | 26 | -1.38 | **F** |
| 廣度 | 10 | -2.00 | **F** |
| 宏觀 | 10 | -0.20 | **C-** |
| 情緒 | 15 | +0.67 | **B+** |
| 消息 | 6 | -1.00 | **D-** |

- 總評 **D-**（綜合分 -0.88）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.88） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.62） | 🔴 空 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：3 空 / 1 中性 / 0 多 → 一致偏空，不加碼**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-10-30） | $471.51（-8.24%） |
| 5 日 / 20 日 | -1.40% / -19.93% |
| 20MA / 50MA / 200MA | $523.86（-10.00%） / $529.12（-10.90%） / $476.37（-1.00%） |
| 20 日高 / 低 | $589.51 / $471.51 |
| 距 52 週高 | -28.00% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 利空 | SOXX・新聞・10/31 02:30 | [Intel, AMD lead semiconductor rout as SOXX drops about 10%](https://seekingalpha.com/symbol/SOXX/news?source=feed_symbol_SOXX) |
| 中性 | NVDA・分析・10/31 00:33 | [Nvidia: Time To Lock In The Profits](https://seekingalpha.com/article/4960307-nvidia-time-to-lock-in-the-profits?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/30 19:16 | [GPU rental rates show pricing power for scarce compute, Citadel’s Flight says](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/30 13:02 | [Nvidia weighs billions in credit guarantees for Nscale’s Anthropic data center - report](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/30 01:44 | [Nvidia refutes NYT article claiming Chinese spy targeted CEO and US failed to act](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/30 00:11 | [Nvidia-backed Cohere closes in on $5B funding round](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/29 03:01 | [Dept of Justice studying Nvidia's $12.9B acquisition of Hugging Face - Reuters](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/28 23:36 | [Nvidia says RTX Spark Windows laptops add new models, AI tools, and more](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
