# 09 市場儀表板：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數

> 資料日 data_as_of **2026-10-26**（美股交易日）· 產生 2026-10-27 01:31:09 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 六個最常被問的問題，每個一格：讀數、燈號、一句話、細節、數字來源欄位。全部由 `data/latest.json` 既有欄位推導；燈號規則在 `soxl_quant/dashboard.py`。

## 一行版

加碼：🟢 可以加碼｜宏觀：🔴 偏空，有旗標｜費半：🟡 修正中 -12%/20日｜大戶：🟡 中性 +0.05｜P/C：🟢 SOXL 0.781，個股第 66 百分位｜崩跌：🟢 31/100 低

## 六個儀表

### 🟢 SOXL 能不能加碼？：可以加碼

- 讀數：可以加碼
- 一句話：驗證過的買訊今天成立，可用計畫倉位 6.0% 加碼，總倉位不超過評級上限 25%，新舊部位同一停損 $75.49。
- 細節：進場 $90.50；這是依訊號加碼，不是攤平
- 來源欄位：`trade_plan.side`、`trade_plan.tradeable`、`verdict.rating_5`、`trade_plan.holder.trail_breached`、`crash_risk.score`、`sentiment.vix.ratio_vix_3m`、`levels.sma20`

### 🔴 現在的宏觀消息：偏空，有旗標

- 讀數：偏空｜🌍 Russia committed war crimes in Ukraine by attacking its energy grid, UN-backed inquiry says（AP News）
- 一句話：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。
- 細節：10Y 5.000%（+4.0 bps）；油 $70.99（+3.02%）；VIX 19.45（+2.21%）；美元 28.96（+0.21%）；10/28（三） FOMC 利率決議 10/27–28
- 注意：時事是關鍵字規則分類（非 LLM）；宏觀數字為前一交易日收盤
- 來源欄位：`flash.label`、`flash.top[0]`、`flash.flags`、`macro.kpis[TNX_10Y|BRENT|VIX|DXY]`、`events.upcoming`

### 🟡 費半（SOXX）整體走向：修正中 -12%/20日

- 讀數：修正中｜$491.83（+2.85%）
- 一句話：費半在修正或反彈的半路：SOXL 的 3 倍槓桿會把這段震盪放大，只做有停損的單。
- 細節：5 日 -2.0%、20 日 -12.3%；距 20MA -8.6%、50MA -7.4%、200MA +4.0%；16 檔成分股站上 50MA 25.0%、200MA 50.0%；年線濾網：持有（出場線 $458.71）
- 來源欄位：`soxx_stats`、`breadth.above_sma50_pct`、`breadth.above_sma200_pct`、`trade_plan.regime.underlying`

### 🟡 大戶怎麼走：中性 +0.05

- 讀數：中性 +0.05｜大單 Call $46.29M vs Put $27.02M（60 筆）
- 一句話：大單方向不明顯：沒有誰在明顯站隊。
- 細節：最大單 2026-10-30 $90 Call $7.95M（看空/收租 (賣 Call)）；大戶 C/P 1.71 vs 散戶 C/P 0.64；SOXL/SOXS 資金流 2.89x（20 日均 3.3x）
- 注意：大單 = CBOE 延遲鏈上權利金最大的成交，買賣方向用價量推測（buy_lean / sell_lean），不是真實成交回報
- 來源欄位：`options.whale.whale_net_score`、`options.whale.whale_call_prem_m`、`options.whale.whale_put_prem_m`、`options.whale.top_whale_trades`、`sentiment.flows.ratio`

### 🟢 Put/Call：SOXL 0.781，個股第 66 百分位

- 讀數：SOXL 成交 0.781（中性）｜全市場個股 0.6（1 年第 66 百分位）
- 一句話：中性區：期權市場沒有極端恐慌，也沒有自滿。P/C 越高代表買 Put 避險越多。
- 細節：SOXL 未平倉 P/C 1.575；全市場總 P/C 0.86（中性 (0.75-0.9)）；個股 P/C 讀法 中性 (0.55-0.70)
- 來源欄位：`options.pc_vol_ratio`、`options.pc_oi_ratio`、`sentiment.market_put_call.equity_pc`、`sentiment.market_put_call.equity_pc_percentile`、`sentiment.market_put_call.total_pc`

### 🟢 崩跌指數：31/100 低

- 讀數：31 / 100（低）
- 一句話：分數低不代表安全：價已在年線下，這個分數量的是「壓力持續度」，不是新頂部前兆。
- 細節：成立中的症狀：15 日內出現 3~6 個放量下跌『派發日』、布林通道寬度處 1 年高檔 (波動擴張)；分數 ≥ 80 的歷史命中率 12.2%（基準 9.0%）；低風險 (症狀負荷低於歷史 60%)；價已在 200MA 之下，此分數代表『壓力持續度』而非新頂部前兆
- 來源欄位：`crash_risk.score`、`crash_risk.zone`、`crash_risk.active_signals`、`crash_risk.event_study`

## 因子等級（借 Seeking Alpha 的 A+ … F 寫法）

| 類別 | 權重 | 平均分（−2…+2） | 等級 |
|---|---|---|---|
| 期權籌碼 | 20 | -0.45 | **D** |
| 量能 | 14 | -1.29 | **F** |
| 技術趨勢 | 26 | -1.19 | **F** |
| 廣度 | 10 | -1.00 | **D-** |
| 宏觀 | 10 | +0.10 | **C+** |
| 情緒 | 15 | +0.47 | **B** |
| 消息 | 6 | -1.00 | **D-** |

- 總評 **D-**（綜合分 -0.65）。對照表：A+ ≥ +1.5、A ≥ +1.0、B+ ≥ +0.6、B ≥ +0.3、C+ ≥ +0.1、C ≥ −0.1、C− ≥ −0.3、D ≥ −0.6、D− ≥ −1.0、F < −1.0。
- 這不是 Seeking Alpha 的量化評級；只是用同樣的字母等級呈現本 repo 的 24 因子評分表，讓看慣 SA 的人一眼看懂。

## 四個聲音（借 Seeking Alpha 的 Ratings Summary 寫法）

| 聲音 | 讀數 | 方向 |
|---|---|---|
| 量化評級（24 因子） | 賣出 / 減碼（綜合 -0.65） | 🔴 空 |
| 訊號驗證（10 年回測） | 買進訊號成立 | 🟢 多 |
| 時事 / 宏觀（36 小時） | 偏空（淨影響 -0.32） | 🔴 空 |
| 費半趨勢（SOXX） | 修正中 | 🟡 中性 |

- **四個聲音：2 空 / 1 中性 / 1 多 → 分歧，等對齊再動**

## 費半（SOXX）數字

| 項目 | 值 |
|---|---|
| 收盤（2026-10-26） | $491.83（+2.85%） |
| 5 日 / 20 日 | -2.01% / -12.30% |
| 20MA / 50MA / 200MA | $538.00（-8.60%） / $531.40（-7.40%） / $472.90（+4.00%） |
| 20 日高 / 低 | $589.51 / $475.69 |
| 距 52 週高 | -24.90% |
| 走向 | 修正中（年線上方，但 20 與 50 日線都在頭上） |

- SOXL 追蹤 SOXX 單日報酬的 3 倍：費半 −1% ≈ SOXL −3%；費半在年線上方整理時，SOXL 因為複利損耗，距自己的年線可能遠得多（今天就是）。

## Seeking Alpha 觀點（SOXL / SOXX / NVDA，近 72 小時）

| 方向 | 標的・類型・時間 | 標題 |
|---|---|---|
| 中性 | SOXX・分析・10/27 02:25 | [Is The Bull Market A Bargain Or Broken?](https://seekingalpha.com/article/4957590-is-bull-market-bargain-or-broken?source=feed_symbol_SOXX) |
| 中性 | NVDA・新聞・10/27 00:52 | [Chip sector perks up after Anthropic becomes first AI lab to officially file for IPO](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | SOXX・分析・10/26 21:30 | [I Was Wrong: This Is Not The Bottom For AI Stocks](https://seekingalpha.com/article/4957425-i-was-wrong-this-is-not-the-bottom-for-ai-stocks?source=feed_symbol_SOXX) |
| 中性 | NVDA・分析・10/26 21:25 | [Nvidia Or AMD On This Dip? Pick The Safest](https://seekingalpha.com/article/4957465-nvidia-or-amd-on-this-dip-pick-the-safest?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/26 20:42 | [SpaceX secures $40B Apollo financing deal to expand AI infrastructure](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 中性 | NVDA・新聞・10/26 18:39 | [Jefferies sees semiconductor equipment growth through 2028](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利空 | NVDA・新聞・10/26 05:02 | [Musk warns of AI lending crunch after SpaceX closes $40B GPU financing](https://seekingalpha.com/symbol/NVDA/news?source=feed_symbol_NVDA) |
| 利空 | SOXX・新聞・10/26 00:59 | [BTIG warns stocks may fall after midterms as credit risks mount](https://seekingalpha.com/symbol/SOXX/news?source=feed_symbol_SOXX) |

- 「新聞」= Seeking Alpha 新聞台；「分析」= 投稿作者的意見文章，方向只依標題關鍵字判斷。來源：Seeking Alpha 公開 RSS（個股 combined feed、Wall Street Breakfast、Market Outlook、Macro View）。

## 怎麼用

- 問「能不能加碼」：讀第一格。它由 `trade_plan.side` 先決定（有驗證過的買訊才是「可以加碼」），其次評級、吊燈停損、崩跌分數、VIX 期限結構。
- 問「宏觀怎麼樣」：第二格 + 08_today_news.md。
- 問「費半走向」：第三格 + 上面的 SOXX 數字；長期持有者看 `trade_plan.regime.underlying` 的年線濾網。
- 問「大戶 / Put-Call / 崩跌」：第四到六格。大戶方向是 CBOE 延遲鏈的大額權利金推估，不是 13F 或暗池資料。
- 六個儀表全部由既有欄位推導（欄位名在每個儀表的 fields）；燈號規則寫在 soxl_quant/dashboard.py；因子等級 = 24 因子評分表的 7 個類別平均分對應 A+（≥1.5）… F（＜−1.0），借用 Seeking Alpha 因子等級的呈現方式，不是 Seeking Alpha 的評級。

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
