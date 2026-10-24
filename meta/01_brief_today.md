# 01 今日簡報

> 資料日 data_as_of **2026-10-23**（美股交易日）· 產生 2026-10-24 00:45:38 台北 · 資料狀態 收盤即時報價補齊 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> 與 `feed/latest.md` 逐字相同；Muse 每天至少讀這一份。

# SOXL 2026-10-23（五）收盤 · 🔴 賣出 / 減碼 · $83.59（+1.80%）
> 收盤即時報價補齊 · 產生 2026-10-24 00:45:38 台北 · 自動計算的研究參考，不是投資建議 · 三倍槓桿單日可 ±15%｜⚠️ 資料降級：backtest/tradeplan: unsupported format string passed to NoneType.__format__

**TL;DR** 趨勢偏空、底部條件還沒成立：現在不是買點。 綜合 **-0.86**（−2 ~ +2）· 多/中/空 15%/23%/62% · 信心 中 · 倉位上限 **10%** · 底部檢核 2/8
與前一交易日：評級不變（連續 6 個交易日 🔴賣出 / 減碼）；綜合分數 -1.01 → -0.86（+0.15）；崩跌前兆 28 → 31

## 交易計畫
- 進場：站回 $89.46 且量能比 >1 時第一批；或在 $80.22 上方分批試單（僅限反彈單）
- 停損：收盤跌破 $80.22（近 10 日最低）
- 目標：$89.46（價值區下緣 VAL） → $92.30（EMA5）（風報比 1.7）

## 關鍵價位（由上而下）
| 價位 | 類型 | 來源 | 距現價 |
|---|---|---|---|
| $96.37 | 壓力 | 週選 1σ 上緣 | +15.3% |
| $92.30 | 壓力 | EMA5 | +10.4% |
| $89.46 | 壓力 | 價值區下緣 VAL | +7.0% |
| **$83.59** | 現價 | 2026-10-23 收盤 | — |
| $80.22 | 支撐 | 近 10 日最低 | -4.0% |
| $72.68 | 支撐 | 布林下軌 | -13.1% |
| $70.00 | 支撐 | Put 牆 (OI 44,476) / 週選 1σ 下緣 | -16.3% |
- 期權牆：Put 牆 $70 / Call 牆 $120 / Gamma 翻正 $106.8；淨 GEX -15.0M、P/C 成交 0.83、IV30 129%（CBOE 延遲鏈 2026-10-24 00:04:56；牆是以未平倉推算的模型值，不是觀察到的造市商部位）
- 期權定價波動：週選 ±15.9% → $70 到 $96（2026-10-30）；月選 ±29.3% → $59 到 $108
- 均線：20MA $127.8（-34.6%）/ 50MA $124.9 / 200MA $123.2（-32.1%）→ 跌破年線 (Below 200MA)
- 波動：ATR14 14.9%（一天正常波動的尺度，停損距離由它決定）、量能 RVOL 1.12x、20 日實現波動率 112%

## 訊號驗證（2017-08-24 ~ 2026-10-23，非重疊交易，勝率旁為同期基準）
| 訊號 | 勝率 vs 基準（N） | 平均報酬 | 狀態 |
|---|---|---|---|
| 買 帶量破20日高 [B*★] | 83% vs 57%（24） | +12.3% / 20 日 | ⚪ 未觸發 |
| 買 連3黑收5MA下 [B] | 64% vs 55%（62）；動態出場 75% vs 64% | +2.5% / 5 日 | ⚪ 未觸發 |
| 買 KD低檔金叉 [B] | 70% vs 57%（33）；動態出場 63% vs 64% | +6.9% / 10 日 | ⚪ 未觸發 |
| 買 7日新低年線上 [B] | 57% vs 55%（94）；動態出場 66% vs 64% | +2.3% / 7 日 | ⚪ 未觸發 |
| 買 20MA上穿50MA [B] | 58% vs 57%（24） | +6.2% / 20 日 | ⚪ 未觸發 |
| 買 站回20MA [C] | 64% vs 57%（39） | +9.4% / 20 日 | ⏳ 待觸發 >$127.09 |
| 賣 吊燈3ATR [C] | 45% vs 43%（73） | +4.1% / 10 日 | 🟠 10 日內觸發 |
| 賣 KD高檔死叉 [C] | 42% vs 43%（66） | +2.5% / 10 日 | ⚪ 未觸發 |
- 買進訊號的勝率 = 訊號後 h 日收高的比例，賣出訊號的勝率 = 收低的比例；等級 A 可靠、B 尚可、B* 顯著但樣本外薄、C 無優勢；★ = 顯著高於基準（p < 0.05）。18 個有樣本的訊號中 1 個顯著，經多重檢定校正（BH q < 0.10）剩 0 個。
- 賣出訊號：歷史上沒有一個的命中率高於基準，也沒有一個能預測 20 日內 ≥15% 的回撤 → 停損是保險，不是預測。 反轉買點用「收盤站上 5 日線」出場時，勝率基準本身就是 64%，請以該基準比較。
- 200 日線濾網（2017-08 起，無成本）：SOXL 自身 → 空手（距年線 -32.2%；年化 14.2%、切換 91 次）；SOXX 指數 ±3% 帶 2 日確認 → 持有（距年線 n/a；年化 33.9%、最大回撤 -78.0%、切換 14 次）；買進抱牢 年化 33.0%、最大回撤 -90.5%。兩種讀法今天不一致。

## 崩跌前兆
- 分數 **31/100**（低風險 (症狀負荷低於歷史 60%)；≥60 注意、≥80 警戒）；完全成立 3 項；主要壓力來源：15 日內出現 3~6 個放量下跌『派發日』、VVIX >95 (波動率的波動升溫)、布林通道寬度處 1 年高檔 (波動擴張)
- 分數 ≥80 的歷史命中率 12%（基準 9%，提升 1.4x）；歷史同類情境：10 日跌幅 ≤ -30% (崩跌後)

## 48 小時內事件
- 無。
- 14 天內：10/27（二） NXPI 財報（盤後）；10/28（三） FOMC 利率決議 10/27–28；10/28（三） KLAC 財報（盤後）；10/29（四） INTC 財報（盤後）；10/30（五） 週選擇權到期

## 什麼會改變結論
- 轉多：收盤站回 20MA $127.85；再加上 VIX 期限結構回到正價差（目前 0.929）；成分股站上 20MA 比例 > 40%（目前 12%）
- 轉更空：收盤 < $80.22；VIX/VIX3M ≥ 1.0（目前 0.929）；崩跌前兆分數 ≥ 80（目前 31）
- 資料風險：backtest/tradeplan: unsupported format string passed to NoneType.__format__；期權牆與 GEX 為模型推算、每日 OI 結算後重算

## 情緒、廣度與籌碼
- CNN Fear & Greed 21.0（極度恐懼 Extreme Fear；前值 19.8）｜VIX 19.03 / VIX3M 20.48 → 0.929（contango）｜SKEW 152.4｜VVIX 109.7
- 全市場 P/C 0.94、個股 P/C 0.69；大戶期權 48 筆 淨方向 +0.23（多 $48.8M / 空 $30.6M）；SOXL/SOXS 資金流 2.4x
- 16 檔成分股站上 20MA 12% / 50MA 19% / 200MA 50%；權值加權日漲跌 +0.50%；RSI14 31、MACD 柱 -6.19、KD 9/12

## 消息面（近 7 日 利多 98 / 利空 176，比值 0.56）
- 主題：個股動能/買盤利多 ×21、獲利了結/基本面利空 ×15、AI 估值/融資疑慮 ×9、殖利率/通膨/關稅宏觀利空 ×7
- 多 - Micron Technology Stock Price Forecast: CEO Reaffirms Tight Supply for Next Two Years, How Will HBM4 Mass Production and CXMT Controversy Impact Stock Price Expectations?（TradingKey）
- 多 - Prediction: Nvidia Will Outperform Broadcom Over the Next 5 Years（The Motley Fool）
- 多 - Micron Technology Options Spot-On: On October 23rd, 1.16 Million Contracts Were Traded, With 3.5 Million Open Interest（Moomoo）
- 空 - Broadcom stock gets massive $600 call even as AI fears grow（TheStreet）
- 空 - Micron stock gets stunning $3,000 call despite 6% plunge（TheStreet）
- 空 - Turmoil hits AI build-out as neoclouds face pressure, credit risks mount and Solidigm pulls IPO（CNBC）

## 自我驗證
- 最近 1 次有結果的評級，方向正確 1/1（100%）；連續同評級 6 個交易日
- 完整報告 https://corleonis6422.github.io/stock-dashboard/soxl_analysis_report.html ・ 新手版 https://corleonis6422.github.io/stock-dashboard/soxl_simple.html ・ JSON https://corleonis6422.github.io/stock-dashboard/feed/latest.json（新聞連結在 news.top_bull[].link）

_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
