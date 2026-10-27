# 06 給 AI Agent 的解讀規則

> 資料日 data_as_of **2026-10-27**（美股交易日）· 產生 2026-10-27 23:49:56 台北 · 資料狀態 收盤即時報價補齊 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
>
> Muse 或任何 agent 轉述這份資料時必須遵守的規則；違反任何一條就會把研究參考講成投資建議。

## 必守規則

1. **先看新鮮度**：`data_as_of` 必須等於最近一個已收盤的美股交易日（美東 16:00 後約 75 分鐘換日；週末與 NYSE 假日順延）。落後就先說「資料是 X 月 X 日的」，再給結論。最新版永遠在 `https://corleonis6422.github.io/stock-dashboard/feed/latest.json` 與 `https://corleonis6422.github.io/stock-dashboard/meta/`。
2. **盤中快照不是結論**：`data_status.provisional = true` 且 `final = false` 時，只能說「盤中暫時讀數」。
3. **評級是投票不是指令**：轉述 `verdict.label` 時一定帶 `composite`、`consensus` 三個百分比與 `size_pct`，並提醒三倍槓桿單日可 ±15%。
4. **價位優先於形容詞**：至少給三個數字：停損 `trade_plan.stop.price`、第一目標 `trade_plan.t1.price`、關鍵牆（`options.put_wall` / `call_wall` / `gamma_flip`）。`trade_plan.side = no_trade` 就直說「今天不開新倉，觸發價是 X」。
5. **勝率一定帶基準與 N**：寫成「勝率 64%（基準 55%，N=62，p=0.09）」。`significant = false` 的訊號不可以說「高勝率」。賣出訊號歷史上沒有預測力，只能用來決定減碼節奏，停損是保險。
6. **兩種 200 日線讀法可能不一致**：SOXL 自身 vs SOXX 指數。長期持有者看指數那條，短線反彈單看 SOXL 自身；不一致時兩個都講。
7. **期權牆是模型值**：由公開未平倉推算，不是觀察到的部位；CBOE 即時價與收盤差 ≥ 2% 時（簡報會加 ※），1σ 區間與 Gamma 翻正位會在下次更新改變。
8. **有變化才值得打擾**：`changes.verdict_changed = true`、`crash_risk.score` 跨過 60 / 80、48 小時內有 FOMC 或龍頭財報、`warnings` 非空、`trade_plan.side` 變成 `long`、`flash.flags` 任一為 true（聯準會決議 / 地緣升溫 / 關稅收緊 / 龍頭資本支出轉弱）→ 主動推；否則一句話即可。
9. **引用來源**：新聞附 `publisher` 與 `link`（在 JSON `news.top_bull[].link` 與 `flash.top[].link`），數字附 `data_as_of`。時事的 `impact` 與 `why_zh` 是關鍵字規則套出來的，轉述時說「依標題分類」，不要說成「分析指出」。
10. **免責**：每次輸出都帶 `disclaimer`。
11. **問「能不能加碼」只念 `dashboard.gauges[key=add_on]`**：它和交易計畫同源；「可以加碼」只在有驗證過的買訊成立、或評級 ≥ 4 且價在 20 日線上、費半在年線濾網內時出現。問費半、大戶、Put/Call、崩跌指數就念對應的那一格，連同 `meaning` 與 `caveat`（大戶方向是 CBOE 大額權利金推估，不是 13F）。因子等級 A+ … F 是本 repo 評分表的字母化，不是 Seeking Alpha 的評級。

## 回答模板（三句話版）

> （1）今天 **{verdict.label}**：{trade_plan.headline}。（2）最重要的理由：{verdict.tldr[1]}；今天最大的事：{beginner.biggest_thing}。（3）要盯的價位：停損 {trade_plan.stop.price}、T1 {trade_plan.t1.price}、Gamma 翻正 {options.gamma_flip}。48 小時內：{events.upcoming 內 days_ahead ≤ 2 的項目，沒有就寫「無」}。{disclaimer}

今天套進去會是：

> （1）今天 **觀望 / 持有不加碼**：⛔ 不開新倉：沒有驗證過的買點成立；下面是觸發後才執行的條件計畫。（2）最重要的理由：最大空方理由：均線結構 (20 / 50 / 200MA)（空頭排列 (Bearish Alignment) | 距 20MA -17.8% / 50MA -17.7% / 200MA -18.2%）；最大多方理由：Call/Put 成交量比 (今日)（1.66x (Call 187,965 / Put 113,133)）；今天最大的事：Live updates: Iran war threatens GOP’s midterm hopes as Trump campaigns in Texas（AP News，10/28 06:46 台北）→ 🌍 地緣政治，對 SOXL 利空：地緣風險升溫：油價與 VIX 上升時資金先逃離高 Beta 的半導體，三倍槓桿的 SOXL 通常跌最多。（3）要盯的價位：停損 $88.38、T1 $120.00、Gamma 翻正 $96.4。48 小時內：10/28（三） FOMC 利率決議 10/27–28；10/28（三） KLAC 財報（盤後）；10/29（四） INTC 財報（盤後）。

## 好句子與壞句子（數字取自今天的資料）

- 壞：「連3黑收5MA下 勝率 75%，很準。」 好：「連3黑收5MA下 用 5 日線出場的勝率 75%，但那種出場規則的基準就是 64%，N=60，p=0.0431，等級 B。」
- 壞：「跌破 20 日線就該賣。」 好：「首破 20 日線後 10 日內收更低的比例 40%，基準 43%（N=47）；它不是賣出預測，停損 $88.38 才是出場依據。」
- 壞：「Call 牆在 $120，上不去。」 好：「Call 牆 $120（OI 79,619）是用未平倉推算的壓力參考，會隨每天 OI 變動；它只是階梯上的一格，不是天花板。」
- 壞：「現在很便宜可以買。」 好：「今天沒有驗證過的買訊成立，計畫是 no_trade；條件是 收盤站上 VPVR POC 籌碼峰 $103.32 且量能 RVOL ≥ 1.2 → 條件成立後次日開盤進場（反彈單），倉位 6.9%，守 $88.38。」

## 哪個檔案回答哪個問題

| 問題 | 讀哪裡 |
|---|---|
| 今天該買還是該賣 | 02_trade_plan.md（或 `trade_plan`） |
| 為什麼 | 01_brief_today.md 的 TL;DR 與「什麼會改變結論」 |
| 這個買點歷史上準嗎 | 03_signals.md（或 `signals[]`） |
| 數字怎麼算 / 可信度 | 04_methodology.md、`validation` |
| 看不懂的名詞 | 05_glossary.md |
| 過去幾天說對了嗎 | 07_history.md、`history[]` |
| 今天發生了什麼大事、對 SOXL 有什麼影響 | 08_today_news.md（或 `flash`、`beginner.biggest_thing`） |
| 新手只想要一個答案 | 01_brief_today.md 的「新手一眼看懂」（或 `beginner.buy`） |
| 能不能加碼、費半走向、大戶怎麼走、Put/Call、崩跌指數 | 09_market_dashboard.md（或 `dashboard.gauges[]`，每格有 `fields` 指出數字來源） |

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
