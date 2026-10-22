# 06 給 AI Agent 的解讀規則

> 資料日 data_as_of **2026-10-21**（美股交易日）· 產生 2026-10-22 21:27:52 台北 · 資料狀態 官方日線 · schema `soxl-quant-brief/2` · 來源 `feed/latest.json`
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
8. **有變化才值得打擾**：`changes.verdict_changed = true`、`crash_risk.score` 跨過 60 / 80、48 小時內有 FOMC 或龍頭財報、`warnings` 非空、`trade_plan.side` 變成 `long` → 主動推；否則一句話即可。
9. **引用來源**：新聞附 `publisher` 與 `link`（在 JSON `news.top_bull[].link`），數字附 `data_as_of`。
10. **免責**：每次輸出都帶 `disclaimer`。

## 回答模板（三句話版）

> （1）今天 **{verdict.label}**：{trade_plan.headline}。（2）最重要的理由：{verdict.tldr[1]}。（3）要盯的價位：停損 {trade_plan.stop.price}、T1 {trade_plan.t1.price}、Gamma 翻正 {options.gamma_flip}。48 小時內：{events.upcoming 內 days_ahead ≤ 2 的項目，沒有就寫「無」}。{disclaimer}

今天套進去會是：

> （1）今天 **減碼 / 觀望**：⛔ 不開新倉：沒有驗證過的買點成立；下面是觸發後才執行的條件計畫。（2）最重要的理由：最大空方理由：均線結構 (20 / 50 / 200MA)（跌破年線 (Below 200MA) | 距 20MA -23.2% / 50MA -18.9% / 200MA -16.0%）；最大多方理由：大戶 (Whale) 期權淨方向（淨分數 0.686 | 大單 Call $17.2M vs Put $23.0M (C/P 0.75)）。（3）要盯的價位：停損 $91.35、T1 $120.00、Gamma 翻正 $106.9。48 小時內：10/23（五） 週選擇權到期。

## 好句子與壞句子（數字取自今天的資料）

- 壞：「連3黑收5MA下 勝率 76%，很準。」 好：「連3黑收5MA下 用 5 日線出場的勝率 76%，但那種出場規則的基準就是 64%，N=59，p=0.0268，等級 B。」
- 壞：「跌破 20 日線就該賣。」 好：「首破 20 日線後 10 日內收更低的比例 39%，基準 42%（N=46）；它不是賣出預測，停損 $91.35 才是出場依據。」
- 壞：「Call 牆在 $120，上不去。」 好：「Call 牆 $120（OI 64,746）是用未平倉推算的壓力參考，會隨每天 OI 變動；它只是階梯上的一格，不是天花板。」
- 壞：「現在很便宜可以買。」 好：「今天沒有驗證過的買訊成立，計畫是 no_trade；條件是 收盤站上 EMA5 $103.93 且量能 RVOL ≥ 1.2 → 條件成立後次日開盤進場（反彈單），倉位 8.3%，守 $91.35。」

## 哪個檔案回答哪個問題

| 問題 | 讀哪裡 |
|---|---|
| 今天該買還是該賣 | 02_trade_plan.md（或 `trade_plan`） |
| 為什麼 | 01_brief_today.md 的 TL;DR 與「什麼會改變結論」 |
| 這個買點歷史上準嗎 | 03_signals.md（或 `signals[]`） |
| 數字怎麼算 / 可信度 | 04_methodology.md、`validation` |
| 看不懂的名詞 | 05_glossary.md |
| 過去幾天說對了嗎 | 07_history.md、`history[]` |

---
_本簡報由公開資料自動計算，僅供研究參考，不構成投資建議；SOXL 為三倍槓桿 ETF，單日波動可達 ±15%，請自行評估風險。_
