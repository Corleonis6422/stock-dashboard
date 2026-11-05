# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-11-04**（美股交易日）· 產生 2026-11-05 01:59:58 台北 · 資料狀態 收盤即時報價補齊 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🔴 不能加碼｜宏觀：🔴 中性，有旗標｜費半：🔴 空頭 -23%/20日｜大戶：🔴 偏空 -0.38｜P/C：🟢 SOXL 0.678，個股第 68 百分位｜崩跌：🟢 21/100 低

## 六個儀表

### 🔴 SOXL 能不能加碼？：不能加碼

- 讀數：不能加碼
- 一句話：VIX/VIX3M 1.11 倒掛：歷史上這種狀態加碼的賠率最差，只能減碼或空手。
- 細節：跌破 $58.47 全出；反彈到 $73.78 / $75.99 先減
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：中性，有旗標

- 讀數：中性｜📉 As Vistra and other energy stocks slide, some analysts warn of an ‘excessive knee-jerk’ reaction（MarketWatch）
- 一句話：整體風險偏好惡化：SOXL 的 Beta 約是大盤的 3 到 4 倍，大盤跌 1% 它常跌 3% 以上。
- 細節：10Y 4.950%（+4.0 bps）；油 $66.11（+0.24%）；VIX 20.83（-1.51%）；美元 29.01（+0.17%）
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🔴 費半（SOXX）整體走向：空頭 -23%/20日

- 讀數：空頭｜$450.41（-3.14%）
- 一句話：費半空頭：SOXL 的反彈多半是空頭回補，T1 / T2 當減碼點。
- 細節：5 日 -13.7%、20 日 -22.7%；距 20MA -10.7%、50MA -14.3%、200MA -5.8%；16 檔成分股站上 50MA 18.8%、200MA 37.5%；年線濾網：持有（出場線 n/a）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🔴 大戶怎麼走：偏空 -0.38

- 讀數：偏空 -0.38｜大單 Call $56.49M vs Put $61.15M（97 筆）
- 一句話：大單權利金偏向 Put：大戶在避險或押跌，和空頭評級同向。
- 細節：最大單 2029-01-19 $45 Put $12.26M（偏空 (Put 價升量增)）；大戶 C/P 0.92 vs 散戶 C/P 0.31；SOXL/SOXS 資金流 3.56x（20 日均 2.98x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟢 Put/Call：SOXL 0.678，個股第 68 百分位

- 讀數：SOXL 成交 0.678（偏樂觀）｜全市場個股 0.6（1 年第 68 百分位）
- 一句話：中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.356；全市場總 P/C 0.86（中性 (0.75-0.9)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：21/100 低

- 讀數：21 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』；分數 ≥ 80 的歷史命中率 12.3%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | -0.80 | **D-** |
| 量能 | 14 | -1.36 | **F** |
| 技術趨勢 | 26 | -1.54 | **F** |
| 廣度 | 10 | -2.00 | **F** |
| 宏觀 | 10 | -0.20 | **C-** |
| 情緒 | 15 | +0.67 | **B+** |
| 消息 | 6 | +0.00 | **C** |

- 總評 **D-**（綜合分 -0.86）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.86） | 🔴 空 |
| 訊號驗證（10 年回測） | 沒有驗證過的買點（不開新倉） | 🟡 中性 |
| 時事 / 宏觀（36 小時） | 中性（淨影響 -0.16） | 🟡 中性 |
| 費半趨勢（SOXX） | 空頭 | 🔴 空 |

- **四個聲音：2 空 / 2 中性 / 0 多 → 沒有任何多方聲音：不加碼、不開新倉**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-11-04） | $450.41（-3.14%） |
| 5 日 / 20 日 | -13.70% / -22.72% |
| 20MA / 50MA / 200MA | $504.22（-10.70%） / $525.69（-14.30%） / $478.13（-5.80%） |
| 20 日高 / 低 | $563.28 / $450.41 |
| 距 52 週高 | -31.20% |
| 走向 | 空頭（年線與短均線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | SOXX・分析・11/05 05:25 | [The Semiconductor Sector May Be Nearing A Meltdown](https://seekingalpha.com/article/4962492-the-semiconductor-sector-may-be-nearing-a-meltdown?source=feed_symbol_SOXX) |
| 利空 | SOXX・分析・11/05 00:00 | [AI Data Centers Just Lost The Election](https://seekingalpha.com/article/4962221-ai-data-centers-just-lost-the-election?source=feed_symbol_SOXX) |
| 利空 | NVDA・新聞・11/04 23:43 | [AI infrastructure stocks drop, hyperscalers gain as Democrats win Congress](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/04 18:39 | [Nvidia to ship 1% of $70B RTX chips ordered by Alibaba, Tencent: report](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/04 00:49 | [Nvidia CEO gave go-ahead on Marvell's mega-acquisition of Lumentum](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/03 21:21 | [Samsung to make chip parts for AMD, Nvidia at Texas plant: report](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・分析・11/03 18:13 | [Nvidia: Trade The Fear With NVDL](https://seekingalpha.com/article/4961354-nvidia-trade-the-fear-with-nvdl?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・11/03 14:04 | [Nvidia tells cloud clients to sell at least 51% of services to non-Chinese firms - FT](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
