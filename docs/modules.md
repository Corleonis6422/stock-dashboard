# 分析模組與頁面：每個數字怎麼算

這份文件是參考資料。它說明每個模組的輸入、規則與輸出，以及頁面怎麼組起來。快速開始與檔案地圖在 [README](../README.md)。給 AI agent 的欄位表在 [AGENTS.md](../AGENTS.md)。

## 頁面元素怎麼讀

| 元素 | 在哪裡 | 怎麼讀 |
|---|---|---|
| 評級 | 第一屏 | 🔴🔴 強力賣出、🔴 賣出・減碼、🟡 觀望、🟢 分批買進、🟢🟢 買進・持有。文字由五格評級加上檢核表成立數決定：評級「買進」但檢核表少於 5 項會降為「觀望偏多（等確認）」，所以顏色不會只因為一個指標翻轉 |
| 現在該不該買 | 第一屏 | 先看交易計畫，再看評級：今天有驗證過的買訊且風報比達標才是「可以買」。所以評級與答案可能不同 |
| 明天只盯一個價 | 第一屏 | 買點觸發價或停損價，旁邊寫明是哪一種 |
| 組合圖 | 第一屏 | 橘色或藍色 K 棒是 VIX 急升的交易日。最下面一格是崩跌指數，60 是注意、80 是警戒。圖下方的規則列寫明急升、通道、成交量分布各自怎麼算 |
| 歷史佐證 | 組合圖下方 | 過去 VIX 急升開始之後、崩跌指數升到 80 以上之後，SOXL 實際怎麼走。每個數字旁邊都有基準、樣本數、樣本期間 |
| 五格評級儀表 | `why` 區塊的摺疊 | 綜合評分 −2 到 +2 線性換算：≤ −1.25 強力賣出、−1.25 到 −0.35 賣出、±0.35 中立、0.35 到 1.25 買進、≥ 1.25 強力買進 |
| 買進、觀望、賣出權重比 | `why` 區塊的摺疊 | 把每項指標的權重依分數正負分三堆。買賣權重比大於 1.5 偏多、小於 0.67 偏空 |
| 信心 | `why` 區塊表下方 | 7 個維度裡有幾成與綜合方向相同：≥ 70% 高、45 到 70% 中、< 45% 低 |
| 三問三答 | `plan` 區塊的摺疊 | 沒部位能買嗎、已持有怎麼辦、什麼時候才能買。每題都是一句可執行的指令，含價位與部位比例 |
| 建議曝險上限 | `plan` 區塊的摺疊 | 佔你原本打算投入 SOXL 的最大金額：檢核表少於 3 項是 0 到 10%，3 到 5 項 25%，6 到 7 項 50%，8 項且偏多 100% |
| 多方與空方論點 | `why` 區塊的摺疊 | 從評分表挑出「分數 × 權重」最大的正負因子 |
| 觀察清單 | `plan` 區塊的摺疊 | 五條：價格、期權到期與 Max Pain、情緒、板塊廣度、崩跌指數。這些數字變了就該重看 |

版型的出處：結論與三行摘要來自 Reddit DD 文的慣例，五格儀表來自 TradingView Technical Rating，權重比來自分析師共識條，曝險上限來自 r/LETFs 常見的部位紀律。

## 技術分析 `technicals.py`

輸入：SOXL 5 年日線。輸出：指標數值、11 列技術指標表（每列含讀數 / 訊號 / −2~+2 分數 / 白話說明）、120 日圖表序列。

| 指標 | 參數 | 訊號 / 評分邏輯（摘要） |
|---|---|---|
| 均線結構 | EMA5/10/20、SMA20/50/100/200 | 價 > 20 > 50 > 200 ⇒ +2 完全多頭；價 < 20 但 > 50 & 200 ⇒ +1 多頭回檔；價 < 50 但 > 200 ⇒ −1 中期修正；價 < 200 ⇒ −2（50 < 200 為空頭排列） |
| MACD | 12, 26, 9 | 零軸上柱體擴張 +2 / 收斂 +1；零軸下柱體擴張 −2 / 收斂 −1；金叉 +1、死叉 −1 |
| KD / KDJ | 9, 3, 3（亞洲式 1/3 平滑） | K<20 且（D<25 或 J<0）為超賣區：勾頭向上 +1、否則 0（低檔鈍化）；K、D >80 為超買區；其餘看金叉/死叉 |
| 慢速 KD | 14, 3, 3 | 僅顯示低檔 / 中軸 / 高檔 |
| RSI | 6 / 14 / 24 + StochRSI(14) | RSI14 <30 超賣（RSI6 <20 再 +1）；>70 超買；14、24 皆 ≥50 ⇒ +1；皆 <50 ⇒ −1 |
| ADX / DMI | 14 | +DI > −DI：ADX ≥25 ⇒ +1（強勢多頭）否則 0；−DI > +DI：ADX ≥35 ⇒ −2、≥25 ⇒ −1、否則 0 |
| Supertrend / SAR | (10, 3) / (0.02, 0.2) | 價在線上 +1、線下 −1 |
| 一目均衡表 | 9, 26, 52 | 雲上且 > 基準線 +2；雲上但 < 基準線 +1；雲中 0；雲下 −2 |
| 布林通道 | 20, 2σ | %B <0 極端超賣 0；<0.2 貼近下軌 0；>1 突破上軌 +1；≥0.5 +1；<0.5 −1 |
| 斐波那契 | 戰術波段 = 最近 40 根 K 的最高/最低；大格局波段 = 最近 160 根 | 自動判斷上升波（回撤支撐）或下降波（反彈反壓）；依價格所在區間給 −2~+2 |
| Williams %R / CCI / ROC | 14 / 20 / 12 | %R < −80 或 CCI < −100 ⇒ 超賣（0 分）；ROC < −10% ⇒ −1、> +10% ⇒ +1 |

另外計算：ATR(14)、20 日實現波動率（年化）、52 週高低與回撤、距各均線百分比、連跌天數、20 日上漲/下跌量能比與放量吸籌/派發日數、20 日 VWAP、半年 VPVR（126 日、24 格；POC / 價值區 70% VAH–VAL）、CMF(20)、OBV、MFI(14)、古典樞軸點。

## 期權籌碼與預測 `options_flow.py`

輸入：CBOE SOXL 完整鏈（約 3,000 檔），另抓 SOXX、SOXS 做交叉驗證。

- **基本統計**：Call/Put 成交量比與 Put/Call、未平倉比、權利金成交額（Volume × Mid × 100）、各到期日的 P/C、Max Pain、ATM IV。
- **淨 Gamma 曝險（GEX）**：每檔 `±Gamma × OI × 100 × Spot² × 1%`（Call 為正、Put 為負，即造市商做多 Call、做空 Put 的標準假設），加總為總 GEX（百萬美元）。負 GEX = 造市商順勢對沖、放大波動。
- **Gamma 翻正位**：把每檔選擇權用 Black-Scholes 在 55%~145% 現價的網格上重新計算 Gamma，找出總 GEX 由負轉正、距現價最近的價位。站上翻正位後造市商改為逆勢對沖（壓抑波動）。
- **Call / Put 牆**：現價上方 Call OI 最大的履約價 / 下方 Put OI 最大的履約價（視窗為現價 ±45%）。
- **Max Pain**：近 3 個到期日合併，以及月選單獨計算。
- **25Δ 偏度**：7–45 DTE 內 |Delta| 0.18–0.35 的 Put IV − Call IV。
- **大戶（Whale）vs 散戶流**：
  - 大戶定義：單檔**當日權利金 ≥ $25 萬**，或 **成交 ≥ 1,500 口且權利金 ≥ $10 萬**，且 **Vol/OI ≥ 0.4**（新倉而非平舊倉）。
  - 成交方向推斷：最後成交價 ≥ 賣價 ⇒ 買方主動（buy）；≤ 買價 ⇒ 賣方主動（sell）；落在價差內則看該檔**當日價格變化**：上漲 ⇒ 偏買（權重 0.7）、下跌 ⇒ 偏賣（0.3）、持平 0.5。
  - 看多金額 = 買 Call + 賣 Put；看空金額 = 買 Put + 賣 Call；**淨方向分數 = (多 − 空) / (多 + 空)**，介於 −1~+1。
  - 散戶代理：成交 ≤ 50 口的小單，計算其 Call/Put 權利金比。
- **期權隱含預測**：
  - 預期波動 = 最近週選（≥3 DTE）、月選（≥15 DTE，最接近 30）、季選（≥60 DTE）的 **ATM 跨式價格**（找不到有效報價時改用 theo）。
  - IV 機率錐：用月選 ATM IV，對 1 週 / 2 週 / 1 個月 / 3 個月給 ±1σ（68%）與 ±2σ（95%）區間（對數常態）。
  - 價位機率：月選到期時高於/低於 70%~150% 現價各檔位的風險中性機率 `N(d2)`，以及「期間觸及」≈ 2 × 到期機率。
  - IV 期限結構：近月（≤10 DTE）vs 遠月（60–120 DTE）ATM IV，近 > 遠 ×1.05 ⇒ 倒掛（恐慌定價）。

## 市場情緒 `sentiment.py`

| 指標 | 計算 / 判讀 |
|---|---|
| **CNN Fear & Greed** | 綜合分數（0 極度恐懼 → 100 極度貪婪）、前日 / 一週 / 一月 / 一年前、1 年歷史；7 子指標：S&P 動能（vs 125DMA）、52 週新高新低、上漲/下跌成交量、5 日 Put/Call、VIX（vs 50DMA）、垃圾債需求、避險需求。<25 極度恐懼、25–45 恐懼、45–55 中性、55–75 貪婪、>75 極度貪婪 |
| **VIX 家族** | VIX、VIX9D、VIX3M、VIX6M、VIX1D、VVIX、SKEW；VIX 50 日均線乖離、1 年百分位、5 日變化、近 5 日盤中高。水位分級：<13 極度自滿、13–16 低波、16–20 溫和警戒、20–25 恐慌升溫、25–35 高度恐慌、>35 極端 |
| **期限結構** | VIX/VIX3M：<0.95 正價差（常態）、0.95–1.05 走平（回檔前常見的警訊區）、≥1.05 倒掛（恐慌高峰、常伴短線底）；另有 VIX9D/VIX3M |
| **VVIX / SKEW** | VVIX >110 壓力、95–110 偏高；SKEW >150 極高尾部避險、135–150 偏高 |
| **CBOE Put/Call** | Total / Equity / Index / SPX / VIX，單日與 5、20 日均；個股 P/C ≥0.85 散戶恐慌、0.70–0.85 偏防禦、0.55–0.70 中性、<0.55 自滿 |
| **SOXL / SOXS 資金流** | 兩者成交金額比 vs 20 日均：>1.3× 且價跌 ⇒ 散戶接刀狂潮；<0.7× ⇒ 放空/避險升溫 |
| **跨資產溫度計** | HYG、TLT、美元、銅、黃金、BTC、MOVE 的 5 / 20 日變化與 1 年百分位；衍生 HYG−TLT 20 日差、銅金比 20 日變化 |
| **市場脈搏 Market Pulse** | 0 恐懼 → 100 貪婪的加權平均（相對權重）：F&G 30、VIX 水位 20（分段映射 VIX 12→95 … 40→0）、期限結構 10、個股 P/C 5 日 15、HYG−TLT 10、SKEW 5、VVIX 5、銅金比 5、SOXL/SOXS 流 5；缺資料的項目自動剔除並重新正規化 |

## 成分股熱力圖 `heatmap.py`

16 檔核心持股（NVDA 10.2%、AVGO 9.8%、AMD 8.4%、MU 7.6%、QCOM 6.8%、TXN 6.5%、AMAT 6.1%、LRCX 5.6%、KLAC 5.2%、INTC 4.8%、ADI 4.6%、MRVL 4.4%、NXPI 4.1%、MPWR 3.8%、ON 3.5%、TER 3.2%，權重為近似值）。每檔計算 1/5/20/60 日報酬、距 52 週高點、RVOL、RSI(14)、是否站上 20/50/200MA、與 SOXL 的 20 日報酬相關。彙總：站上 20/50/200MA 比例、RSI<30 比例、1D/5D 上漲家數比例、加權動能、子板塊（AI GPU、ASIC 網通、記憶體、設備、類比、車用…）表現。

## 宏觀跨資產相關性 `macro.py`

- 資產：10Y（^TNX）、30Y（^TYX）、30Y−10Y 利差、Brent、VIX（CBOE 官方）、美元、HYG、黃金、銅、BTC（後五項可選，缺少時自動略過）。
- 視窗 20 / 60 / 120 / 250 日，各算 **日報酬相關**（方向同步性）與 **價格水位相關**（趨勢同步性）；完整相關矩陣（20D、60D）。
- Beta：VIX 每 +1% 對 SOXL（20 日）、油價每 +1%（20 日）、10Y / 30Y 每 +10 bps（120 日）。
- 殖利率分級：10Y >5.2% 極端高檔、4.6–5.2 高檔、4.0–4.6 中性、<4.0 寬鬆；30Y >5.5% 多年高點區。
- 滾動 20 日相關序列（120 日）供日後畫圖。

## 崩跌前兆系統與事件研究 `early_warning.py`

**目的**：把常見的「頂部型崩跌」前兆量化成每日 0–100 的分數，並用 SOXL 自己的歷史驗證它有沒有用。

**21 項訊號**（每項 0~1 分，括號為權重）：

| 家族 | 訊號 | 觸發方式（線性漸進，達上限 = 1） |
|---|---|---|
| A 過熱 | 距 200MA 乖離 (8) | +25% → 0，+60% → 1 |
| | 距 20MA 乖離 (6) | +8% → 0，+20% → 1 |
| | 20 日拋物線漲幅 (8) | +20% → 0，+60% → 1 |
| | RSI(14) 超買 (4) | 65 → 0，80 → 1 |
| | 布林帶寬 1 年百分位 (4) | 80% → 0，100% → 1 |
| B 動能 | MACD 柱連 3 日收斂且 <60% 近高 (6) | 二元 |
| | KD 高檔死叉 D>70（近 3 日）(6) | 二元 |
| | 首次跌破 20MA（前 10 日皆在上方）(8) | 二元（持續 3 日） |
| | RSI 頂背離（價創 20 日高、RSI 低於前高 4 點以上）(5) | 二元 |
| | 15 日內放量派發日數 (5) | 2 天 → 0，6 天 → 1 |
| C 波動 | VIX/VIX3M 期限結構 (6) | 0.88 → 0，1.00 → 1 |
| | VIX 從 ≤18 低檔 5 日急升 (5) | +10% → 0，+40% → 1 |
| | VVIX (3) | 95 → 0，115 → 1 |
| | SKEW (3) | 140 → 0，165 → 1 |
| | VIX9D/VIX 倒掛 (3) | 0.98 → 0，1.08 → 1 |
| D 宏觀 | 10Y 20 日急升且 ≥4.5%，或 30Y 處 1 年 97 百分位 (5) | +10 bps → 0，+40 bps → 1 |
| | 信用背離：HYG 10 日下跌而 SPY 未跌 (5) | −0.5% → 0，−2% → 1 |
| E 情緒 | CNN F&G 貪婪 (2) | 60 → 0，85 → 1 |
| | F&G 5 日內從 ≥50 急跌 (2) | −8 分 → 0，−23 分 → 1 |
| | 個股 P/C 5 日均自滿 (3) | 0.60 → 0，0.45 → 1 |
| | SOXL/SOXS 資金比暴增且價跌 (3) | 1.1× → 0，1.5× → 1 |

- **原始分數** = 加權平均 × 100（缺資料的訊號不計入分母）。
- **校準**：原始分數換算成 **2021 年以來的歷史百分位**（排除最近 60 日，避免最新事件改變自己的尺度）。分區：<60 低風險、60–80 注意、≥80 警戒（建議減碼 3x 部位）。價已在 200MA 之下時，分數代表「壓力持續度」而非新頂部前兆（報告會註明）。
- **事件研究**（驗證）：
  - 事件 = 之後 5 個交易日內最低收盤 ≤ −20%；相隔 ≥10 日視為獨立事件；依事件起點是否在 200MA 之上分為「頂部型」與「下跌延續型」。
  - 指標：逐日精準度 / 召回 / 基準率 / 提升倍數（門檻 80、90）；頂部型事件中事前 5 日內分數 ≥80 的比例；「警報段」（連續 ≥80 的日子，間隔 ≥5 日分段）在 15 日內是否真的發生事件；依分數分組（0–60 / 60–80 / 80–90 / 90–100）的後 5 日跌 ≥10% / ≥20% 機率。
- **歷史同類情境（Analogs）**：9 種條件（噴出後首根長黑、過熱後首次破 20MA、KD 高檔死叉當日大跌、5 日跌 ≥20%、10 日跌 ≥30%、RSI<25、52 週回撤 ≥40% 且 VIX ≥20、跌破 200MA >10%、F&G <20），各算 5 / 10 / 20 / 60 日後報酬的中位數、四分位、上漲機率、≥+10% 與 ≤−10% 的機率、最佳/最差；樣本 <8 日標示「樣本不足」。
- **高點檢核表**：最近 30 根 K 的最高收盤為「高點」，列出高點前 2 日～後 6 日每項訊號的值與首次觸發日。

## −2~+2 評分表 `scoring.py`

每項因子附：實測值、權重、評分標準、白話意義，以及 **類型**：`trend`（順勢）、`contrarian`（逆勢/情緒極端）、`flow`（籌碼）。

| 維度 | 因子（權重） |
|---|---|
| 1. 期權籌碼 | Call/Put 成交量比 (4)、淨 GEX & Gamma 翻正位 (5)、25Δ IV 偏度 (3)、大戶淨方向 (4)、Max Pain 與牆位置 (4) |
| 2. 量能結構 | 20 日上漲/下跌量能比 (5)、CMF/OBV/MFI (4)、VWAP/POC/價值區位階 (5) |
| 3. 技術趨勢 | 均線結構 (8)、MACD (5)、KD (4, 逆勢)、RSI (4, 逆勢)、斐波那契/一目/Supertrend 共振 (5) |
| 4. 板塊廣度 | 站上 20/50/200MA 比例 (6)、權值股加權動能 (4) |
| 5. 宏觀 | 10Y/30Y 殖利率 (4)、原油 (3；代理時改用 20 日變化)、VIX 水位 (3) |
| 6. 市場情緒 | CNN F&G (4, 逆勢)、VIX 期限結構 (3, 逆勢)、CBOE 個股 P/C (3, 逆勢)、SOXL/SOXS 資金流 (2, 逆勢)、崩跌前兆分數 (3) |
| 7. 消息面 | 近 7 日利多/利空新聞比 (6) |

- **綜合分數** = 加權平均（−2~+2）；≥1.25 強勢看多、0.35~1.25 偏多、±0.35 中性、−1.25~−0.35 偏空、≤−1.25 強勢看空。
- 另給 **趨勢面子分數** 與 **逆勢面子分數**，並據此判定格局，例如「空頭趨勢 + 情緒極端 → 超賣反彈格局：只做短線反彈、不做趨勢多單」或「多頭 + 情緒過熱 → 漲多拉回風險區」。
- **彙總輸出**（頁面第一屏與 `why` 區塊使用）：
  - `rating_5` / `rating_label`：五格評級 1 強力賣出 → 5 強力買進（門檻同上）；`rating_pos` 為儀表位置（0–100）。
  - `consensus`：把 22 項的**權重**依分數正負分成 買進 / 觀望 / 賣出 三堆的百分比（`buy_pct` / `hold_pct` / `sell_pct`）、各堆項數、+2 與 −2 的項數、買賣權重比。
  - `confidence` / `agreement_pct`：7 個維度平均分與綜合方向一致的比例，≥70% 高、45–70% 中、<45% 低。

## 下一步劇本 `playbook.py`

- **標題結論**：由趨勢面 / 逆勢面子分數的組合產生。
- **價位階梯**：自動收集所有有意義的價位（EMA5/10、20/50/200MA、VWAP、POC、價值區下緣、戰術斐波那契、Gamma 翻正位、Call/Put 牆、Max Pain、週/月選 ±1σ、近 10 日高低、布林下軌、前波恐慌低點、52 週低），依現價分為反壓/支撐，相近（1.2% 內）的合併，各取最近 6 個。
- **三劇本與機率**：從歷史同類情境中選「今日成立、樣本 ≥8」且最貼切的條件（優先序：10 日跌 ≥30% → 5 日跌 ≥20% → RSI<25 → 52 週回撤 ≥40% 且 VIX ≥20 → 跌破 200MA → F&G<20 → 全部交易日），用其 **10 日後 ≥+10% / ≤−10% 的歷史比例** 作為 A（反彈）/ C（續跌）機率，其餘為 B（區間）。觸發與目標價位直接取自價位階梯與期權 1σ。
- **重返多頭檢核表**（8 項）：站回 20MA、前兆分數 <60、VIX/VIX3M <0.92、成分股 >40% 站回月線、大戶淨方向 ≥0、MACD 柱翻正、F&G >25 且回升、20 日量能比 >1。≥6 項可分批建立趨勢部位；3–5 項只做小量反彈單；<3 項觀望。
- **新手區塊 `beginner`**（頁面第一屏的評級，以及 `plan`、`why` 區塊摺疊裡的內容）：
  - `verdict` / `color` / `emoji` / `one_liner`：由五格評級 × 檢核表成立數決定（評級買進但檢核 <5 → 「觀望偏多 (等確認)」；評級賣出且檢核 <3 → 「現在不是買點」；趨勢空 + 逆勢多 → 加註「只適合小量短線」）。
  - `q_no_position` / `q_holder` / `q_when`：三問三答，價位取自價位階梯（停損 = 第一道支撐、目標 = 前兩道反壓），第三題列出最先要成立的 3 項檢核。
  - `size_pct` / `size_note`：建議曝險上限（檢核 <3 → 0–10%、3–5 → 25%、6–7 → 50%、8 且偏多 → 100%）。
  - `tldr`（3 行）、`bull_case` / `bear_case`（分數 × 權重最大的正負因子各 4 條）、`plan`（進場 / 停損 / 目標 / 報酬風險比 / 部位上限）、`watch`（本週 5 條觀察）。

## 訊號驗證與交易計畫 `backtest.py` / `tradeplan.py`

**為什麼**：「買點 / 賣點」必須是可以每天重新驗證命中率的規則，不是形容詞。每次更新都用 10 年 SOXL 日線（2,512 根，Nasdaq 拆股調整）重跑 23 條固定規則，列出每條規則的歷史表現與今天的狀態。

- **規則庫**（每條都是固定參數、不在執行期擬合）：反轉買點（Connors RSI(2)<10 / <5、連 3 黑收 5MA 下、Double 7s、布林下軌回收、投降量反轉、IBD 跟進日、KD 低檔金叉、MACD 翻正、VIX 期限結構回正、VIX 高峰回落）、趨勢買點（站回 20MA、20MA 上穿 50MA、帶量突破 20 日高）、出場（首破 20MA、吊燈 3×ATR、派發日第 4 個、拋物線噴出、RSI14>80、KD 高檔死叉、VIX 首次倒掛、死亡交叉、前兆分數 ≥80）。
- **評估方式**：訊號日次一交易日開盤進場、第 h 日收盤結算，非重疊交易；基準 = 同一期間每根 K 線的相同統計；樣本外 = 最近 40%；每條都算 Wilson 95% 信賴區間、**單尾二項檢定 p 值（vs 基準）**、Benjamini-Hochberg q 值、逐年表現、鄰近參數變體。反轉買點另外用 Connors 的動態出場（收盤站上 5 日線）評估，並附同一出場規則的基準勝率（約 64%，因為出場規則本身只挑上漲日）。賣出訊號再用「20 日內回撤 ≥15% 的比例」評分。
- **等級**：A 可靠（N≥30、OOS N≥10、OOS 勝率 ≥60% 且 ≥基準+5、PF≥1.5、IS/OOS 差 ≤12、變體皆優於基準、**p<0.05**）、B 尚可、B* 顯著但樣本外薄、C 無優勢、— 樣本不足。2026-10 的結果：18 條有樣本的規則只有「帶量突破 20 日高」顯著（83% vs 57%，N=24，p=0.007），多重檢定校正後 0 條；**所有賣出規則的命中率都不高於基準**，所以簡報把停損定位為保險，不是預測。
- **200 日線濾網**：同一套 Gayed 式年線切換，分別用 SOXL 自身與 SOXX 指數當訊號、0/3/5% 帶寬、1/2 日確認，列成一張表（無交易成本）。用 SOXL 自身：年化 14.2%、切換 91 次；用 SOXX ±5%：年化 38.3%、切換 10 次；買進抱牢 36.1%、最大回撤 −90.5%。帶寬敏感度不單調，所以簡報給整張表而不是一個數字，而且兩種讀法可能同一天不一致（長期持有者看指數，短線看 SOXL 自身）。
- **交易計畫 `tradeplan.py`**：`side` = `long`（今日有 A/B/B* 買訊成立 → 次日開盤）/ `long_pending`（最近的驗證過觸發價在 8% 內 → 收盤站上才進）/ `no_trade`（條件計畫）。停損 = 進場下方最近的結構支撐（近 10 日低 / VAL / 布林下軌 / Put 牆，需距進場 ≥ 0.8×ATR），太近才改用 k×ATR14（k 來自該訊號勝利交易的最大逆向波動 75 分位，預設 1.2），不緊於 4%，同一價位也是持有者的硬停損（整份簡報只有一個出場價）；T1/T2 = 進場上方第一個 ≥1R / ≥2R 的壓力（階梯沒有就用合成 ATR 目標並標明）；加權風報比 0.5·R(T1)+0.5·R(T2) ≥ 1.5 才算可交易，不足就印出「進場價要 ≤ X 才值得」；倉位 = 每筆 1% 帳戶風險 ÷ 停損距離，再受評級上限約束；時間停損 = 訊號 horizon 或動態出場；失效條件含停損、結構支撐、VIX/VIX3M ≥1.0、前兆分數 ≥80。已持有者另給硬停損、吊燈移動停損與減碼點。
- **驗證工具**：`tools/test_backtest.py`（無網路：無前視、去重疊、已知結果的合成序列、Wilson / 二項 / BH 數值、觸發價反推、外部序列濾網）與 `tools/qa_brief.py`（計畫不變量、訊號統計一致性、新鮮度、Markdown 形狀 ≤12 KB / 表格 ≤4 欄、**每個數字都能在 latest.json 找到**、短訊 ≤900 字）。

## 崩跌復盤 `postmortem.py`

- 以最近 30 根 K 的最高收盤為起點，列到最新日的**逐日時間軸**：SOXL 漲跌、量能倍數、SOXX / SPY 同日漲跌、VIX 與期限結構、SKEW、VVIX、10Y / 30Y、F&G、個股 P/C、前兆分數，並自動產生備註（放量長黑、爆量、SKEW 跳升、VIX 急升、期限結構走平、F&G 極度恐懼、開高走低假突破、前兆分數 ≥45…）。
- **3 倍槓桿數學**：高點→低點 SOXL vs SOXX vs SPY 跌幅對比。
- **大格局偵測**：往前 160 根 K 找更大的「高點→低點」段，計算這次反彈收復了多少（<50% 判定為失敗的熊市反彈），並給 38.2% / 50% 回撤位。
- **亮燈 vs 沉默**：直接引用高點檢核表。
- **七條教訓**：槓桿數學、看大不看小、VIX/F&G 的侷限、真正領先的訊號、能否預測（引用同類情境與分組統計的實際數字）、負 Gamma + 高 IV 結構（自動找出開高走低的例子）、重建部位的紀律。每條都附可執行的「規則」。

## 新聞多空分類 `news.py`

- 來源：Yahoo Finance 搜尋（SOXL 與主要成分股）+ Google News RSS（semiconductor stocks、chip stocks selloff、Nvidia/AMD/Micron/Broadcom stock、SOXL ETF、Philadelphia Semiconductor Index、AI stocks bubble、Treasury yields、Fed）；標題去重。
- 關鍵字法分類為利多 / 利空 / 中性，並貼中文主題標籤（宏觀緩和利多、訂單/資本支出利多、分析師升評、個股動能；殖利率/通膨/關稅利空、內部人/機構減持、AI 估值/融資疑慮、監管/地緣政治、獲利了結…）。
- 以日期分組，配上當日 SOXL / VIX / 10Y / Brent 實際變動；近 7 日利多/利空比進入評分表；7 日主題統計。

## 今日時事與「新手一眼看懂」 `newsflash.py` / `brief._beginner_block`

- **問題**：新手要的不是 24 個因子，而是「今天該不該買」與「今天發生了什麼大事」。Reddit 上最受歡迎的盤前筆記（r/TradingEdge 的 premarket report）第一句永遠是那則讓期貨跳動的頭條，然後才是價位。
- **時事 `newsflash.py`**：Google News RSS 搜尋 23 個主題（Iran、Israel Iran strike、Taiwan China military、Trump tariffs、semiconductor export controls、Federal Reserve、FOMC decision、CPI、payrolls、Nvidia、TSMC、AI capex、chip stocks、stock market futures、VIX…）+ Fed 新聞稿 + CNBC / MarketWatch 頭條，只看最近 36 小時。每則標題：
  - 類別（命中第一個）：聯準會與利率 → 政策與關稅 → 地緣政治 → 半導體與 AI → 經濟數據 → 市場波動。整字比對（`war` 不命中 `software`、`dow` 不命中 `down`、`ism` 不命中 `mechanism`），`word*` 為字首比對。
  - 影響分 −2…+2：類別專屬利空 / 利多詞表相減（同一詞族不重複計）；地緣與政策類只要利空詞多於利多詞就記 −2；混合措辭的政策標題記 0、地緣標題記 −1。
  - 權重 = 新鮮度（≤12h 1.0 / ≤24h 0.8 / 其餘 0.5）× 來源（Fed 1.0、Reuters / Bloomberg / WSJ / AP / CNBC 0.9、BBC / MarketWatch / Barron's 0.8、未知 0.6）。排序 = |影響| × 權重；前 8 則每類最多 2 則，優先權重 ≥ 0.7 的來源。
  - 旗標（24 小時內且來源權重 ≥ 0.7，附依據標題）：`fed_statement_24h`、`geo_escalation_24h`、`tariff_shock_24h`、`capex_warning_24h`、`fed_hawkish_24h`；每個亮的旗標變成交易計畫區的一句警語。
  - 輸出 `payload["newsflash"]`：`top[]`（title / publisher / link / time_tpe / category / impact / why_zh）、`more[]`、`by_category[]`、`net`（−1…+1）與 `label`（偏空 / 中性 / 偏多）、`flags`、`flag_evidence`、`cautions[]`、`beginner_line`（「今天最大的事：… → 類別，對 SOXL 利空：為什麼」）。`auto_update.py feed` 在線上模式下若快照超過 30 分鐘會重抓。
- **新手一眼看懂 `brief._beginner_block`**：五行。「現在該不該買？」由 `trade_plan.side` 先決定（`long` 且風報比達標 → ✅ 可以買；`long` 但不達標 → ⏸ 等更好的價位；`long_pending` → ⏳ 等觸發），其次才看 `rating_5`（≤2 ❌ 不該買、3 ⏸ 等確認、4 🟢 可以分批小量、5 ✅ 可以買）；「今天最大的事」= `newsflash.beginner_line`；「已持有的人」= 硬停損 / 吊燈線 / 減碼點；「明天只盯一個價」= 觸發價或停損；「48 小時內風險」= 排定事件 + 亮起的旗標（附來源）+ 前兆分數 ≥ 60。Markdown、頁面第一屏的答案與 `beginner` JSON 由同一個函式產生，不會互相矛盾；`tools/qa_brief.py` 檢查答案與 `trade_plan.side` 一致。
- **限制**：是關鍵字規則，不是 LLM 判讀；`why_zh` 是依類別與方向套用的固定句，標題是英文原文。要判讀個別新聞請點 `link`。時事不改變 24 因子評級。
- 測試：`tools/test_newsflash.py`（離線，25 個標題的類別 / 影響期望值 + 旗標、去重、每類上限、空輸入）。

## 六個儀表 `dashboard.py`

- **問題**：看盤的人每天問同樣六件事：SOXL 能不能加碼、現在的宏觀消息、費半整體走向、大戶怎麼走、Put/Call 多少、崩跌指數多少。這些數字原本散在期權、情緒、廣度、前兆四個區塊，現在每個問題一格，格式固定：讀數、燈號（🟢🟡🔴）、一句話、細節、`fields`（數字來自 JSON 哪些欄位）。
- **能不能加碼 `add_on`**：先看硬性否決（崩跌前兆 ≥ 80、VIX/VIX3M ≥ 1.0 → 🔴 不能加碼），再看 `trade_plan.side`（`long` 且風報比達標 → 🟢 可以加碼，用計畫倉位、同一停損；`long_pending` → 🟡 等觸發），再看評級（≤ 2 → 🔴 不能加碼，只能減碼；3 → 🟡 先不加碼；≥ 4 且價在 20MA 上且費半在年線濾網內 → 🟢 可小量加碼，否則 🟡）。
- **宏觀 `macro`**：36 小時新聞氣壓 + 第一則非半導體頭條 + 10Y / Brent / VIX / 美元日變動 + 7 天內的 FOMC；任何旗標亮就 🔴。
- **費半 `soxx`**：用 10 年 SOXX 日線算 20 / 50 / 200MA、1 / 5 / 20 日報酬、20 日高低、距 52 週高；走向五選一（多頭 / 年線上方整理 / 修正中 / 年線下方反彈 / 空頭）加 16 檔成分股廣度與年線濾網狀態。
- **大戶 `whales`**：CBOE 鏈上大額權利金的淨方向（−1…+1）、Call vs Put 權利金、最大一筆（含買賣方向推測）、大戶 vs 散戶 C/P、SOXL/SOXS 資金流；caveat 明寫這是延遲鏈推估，不是 13F。
- **Put/Call `put_call`**：SOXL 成交與未平倉 P/C、全市場個股 P/C 與 1 年百分位；恐慌（≥ 90 百分位或 SOXL ≥ 1.2）與自滿（≤ 10 百分位或 ≤ 0.5）都標 🟡，中性 🟢。
- **崩跌 `crash`**：前兆分數、成立中的症狀、≥ 80 的歷史命中率與基準；價在年線下時提醒「這是壓力持續度，不是新頂部前兆」。
- **借 Seeking Alpha 的兩個呈現法**（只是呈現方式，不是 SA 的資料）：`factor_grades` 把 24 因子評分表的 7 個類別平均分映射成 A+ … F（A+ ≥ +1.5、F < −1.0），像 SA 的 Factor Grades；`voices` 把量化評級、訊號驗證、時事、費半趨勢四個獨立讀數並排，像 SA 的 Ratings Summary，並給一致 / 分歧結論（沒有任何多方聲音 → 不加碼、不開新倉）。
- **Seeking Alpha 當來源**：`newsflash.py` 多抓 SA 公開 RSS（Wall Street Breakfast、Market Outlook、Macro View、SOXL / SOXX / NVDA 個股 combined feed）；投稿文章標成「Seeking Alpha 分析」權重 0.6、新聞台 0.8；`flash.seeking_alpha[]` 列出 72 小時內與 SOXL / SOXX / NVDA 有關的 SA 標題（附連結、新聞 / 分析、方向）。
- 出口：`payload["dashboard"]`、`feed/latest.json` 的 `dashboard`、Markdown「## 六個儀表」表、頁面各區塊摺疊裡的儀表（位置見 [section_log.md](section_log.md) 的 F02）、`meta/09_market_dashboard.md`、MCP `get_latest(section="dashboard")`。`auto_update.py feed` 重抓時事時只重算宏觀那一格與四個聲音（`dashboard.refresh_macro`）。
- 測試：`tools/test_dashboard.py`（等級門檻、SOXX 走向分類、加碼決策矩陣含崩跌 / VIX 否決、燈號、四個聲音、空資料降級）。

## 頁面 `report_page.py`、`report_chart.py`、`report_sections.py`、`report_html.py`

純標準函式庫產生的單一 HTML 檔，寫成三個檔名：`index.html`、`soxl_analysis_report.html`、`soxl_simple.html`。三個檔案內容相同，所以舊連結都還能開。

| 模組 | 做什麼 |
|---|---|
| `report_page.py` | 組頁面：頁首、第一屏七個讀數、組合圖、歷史佐證、十個區塊、頁尾。第一屏的評級與「該不該買」和簡報用同一個函式，所以頁面與 `feed/latest.json` 不會不一致 |
| `report_chart.py` | 組合圖：SOXL K 棒、VIX、成交量與均量、崩跌指數對齊同一條日期軸。日線約 6 個月與週線約 2 年兩個檢視。VIX 急升的 K 棒換色並加標籤，另有趨勢通道、右側成交量分布、十字線。資料與規則來自 `stress_chart.py`，文件在 [stress_chart_data.md](stress_chart_data.md) |
| `report_sections.py` | 十個區塊。每個區塊一行由資料算出的結論（最多 40 字）、一個圖或一張 8 列以內的表，其餘收進摺疊。來源缺漏時只留一行說明。`clean()` 在顯示時把存的字串裡的 `None`、`n/a` 改寫掉 |
| `report_html.py` | 共用零件：跳脫、SVG 小工具、Fear & Greed 走勢圖、期權牆圖、五格評級儀表、名詞小抄、基礎 CSS |

**版面規則（每次產生都一樣，與資料無關）**：

- 組合圖是一張會隨寬度伸縮的 SVG，文字是疊在上面的 HTML，所以任何寬度都不需要左右捲動，字也不會縮小。
- 其他圖表的文字都放在保留區：每個面板上方有標題列兼圖例，標籤不壓在資料線上。寬表格與較寬的圖在窄螢幕改為區塊內水平捲動，並顯示「⇆ 可左右滑動」。
- 短標籤（16 字以內）整段不斷行，避免「下月／線」這種斷法。
- 1100 px 以上十個區塊排兩欄；打開摺疊的區塊會佔滿整列。

**安全**：所有插值經 `html.escape()`；頁面帶嚴格的 `Content-Security-Policy`（`default-src 'none'`、script 只允許 nonce、`connect-src 'none'`）；新聞連結只有 http 或 https 才會變成連結；JS 只讀屬性，只寫 `textContent`、樣式、屬性與摺疊的開關，沒有 `innerHTML`，沒有外部資源。它在讀者的瀏覽器裡記住兩件事：選的圖表檢視（`localStorage` 與網址的 `#view=`），以及打開了哪些摺疊（`sessionStorage`，讓 30 分鐘自動重新載入後摺疊維持原狀）。

**驗證工具**：

- `tools/qa_render.py`：headless Chrome 在 9 種寬度檢查 SVG 文字被裁切、互相重疊、壓到資料線，HTML 文字被裁切或溢出，短標籤斷行，整頁水平捲動。`--first-screen` 量第一屏七個讀數的位置，`--crosshair` 用腳本移動滑鼠與手指檢查十字線讀數，`--snapshots` 對每一份每日快照重畫頁面再檢查。
- `tools/qa_stress.py`：用極端假資料（價位全擠在一起、貼邊、密集事件、極短歷史、四位數股價、沒有急升、每天都是急升、缺 VIX、缺崩跌指數、上漲行情加買進評級）壓測排版。
- `tools/test_report_chart.py`、`tools/test_report_sections.py`、`tools/test_stress_chart.py`：離線測試，不需要瀏覽器。
- 給腳本用的頁面標記在 [page_markers.md](page_markers.md)。舊頁面每一塊的去向在 [section_log.md](section_log.md)。

## 輸出 JSON 結構 `soxl_analysis_data.json`

```text
soxl_analysis_data.json
├─ generated_at, data_as_of, warnings[]
├─ data_status       provisional / final / label / note / asof_et（最後一根 K 線是官方日線、收盤即時報價補齊、或盤中快照）
├─ technicals        指標數值、swing / major_swing / fib_levels、volume_profile[]、tech_table[]、chart_series[]
├─ options           cboe_spot、iv30_pct、pc_vol_ratio、total_net_gex_m、gamma_flip、gex_profile[]、call_wall / put_wall、
│                    near_max_pain / monthly_max_pain、iv_skew_25d、expirations[]、focus_strikes[]、
│                    whale{whale_net_score, whale_call/put_prem_m, retail_cp_ratio, top_whale_trades[]}、
│                    forecast{weekly, monthly, quarterly, iv_cone[], prob_table[], iv_term_structure}、secondary{SOXX, SOXS}
├─ sentiment         fear_greed{score, rating_zh, components[], history[]}、vix{...history[]}、put_call{...history[]}、
│                    flows{latest, ratio_avg20, history[]}、cross_asset{assets[]}、pulse{score, rating_zh, parts[]}
├─ heatmap           constituents[]、subsectors[]、breadth_above_sma20/50/200_pct、weighted_ret_1d/5d/20d
├─ macro             macro_kpis[]、horizons{20D,60D,120D,250D}、matrix_20d/60d、beta_*、rolling_series[]、proxies{}
├─ early_warning     today{score, raw, zone}、calibration{p50,p80,p90,p95}、contributions[]、chart[]、
│                    event_study{episodes[], buckets_top[], stats_top_80/90, alert_episodes…}、
│                    analogs{conditions[]}、peak_checklist{rows[], columns[], scores[]}、score_history_90d[]
├─ news              total_unique_articles、sources、recent_bull/bear_count、bull_bear_ratio、themes_7d[]、daily_feed[]
├─ scoring           composite_score、verdict、trend_score、contrarian_score、regime、factors[]、category_scores[]、
│                    rating_5 / rating_label / rating_pos、consensus{buy_pct, hold_pct, sell_pct, n_buy, n_hold, n_sell, …}、confidence、agreement_pct
├─ playbook          headline、bullets[]、ladder[]、scenarios[]、checklist[]、checklist_passed/total/verdict、
│                    beginner{verdict, color, emoji, one_liner, q_no_position, q_holder, q_when, size_pct, size_note, tldr[], bull_case[], bear_case[],
│                             plan{entry, stop, target, risk_reward, max_size_pct, stop_price/label/dist_pct, target1_*, target2_*}, watch[]}
├─ postmortem        peak/trough、soxl/soxx/spy_drawdown_pct、timeline[]、big_picture、warned[]、silent[]、lessons[]
├─ newsflash         top[]、more[]、by_category[]、net、label、flags、flag_evidence、cautions[]、beginner_line、seeking_alpha[]
├─ backtest          method、signals[]、summary、regime、atr14
├─ trade_plan        side、tradeable、headline、entry、stop、t1、t2、rr_blend、min_rr、size、time_stop、invalidation[]、holder、regime、explain[]
├─ dashboard         gauges[]、lights、factor_grades[]、overall_grade、voices、soxx_stats、one_liner、method
├─ stress_chart      組合圖的資料：daily、vix、weekly、views{daily,weekly}、rules、legend、latest、spike_stats、evidence（見 stress_chart_data.md）
├─ soxl_recent[]     最近 30 日 OHLCV
├─ benchmarks_recent SOXX / SPY 最近 40 日收盤
├─ light_history[]   最近 120 日的價格燈號 {date, close, pts, n, light}（`proof` 區塊燈號圖的背景）
├─ verdict_history[] history/verdicts.jsonl 的最近 60 筆（每日評級紀錄 + fwd_ret_5d / fwd_ret_10d 事後驗證）
└─ schedule          installed / times / weekday_text / next_run / last_run（自動更新狀態，給頁面顯示）
```
