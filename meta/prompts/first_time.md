# 提示：第一次附上 meta.zip 時貼這段（Muse 這類能上網的 24/7 agent）

> 附件 meta.zip 是 SOXL（三倍做多半導體 ETF）的量化簡報資料包，當作你的長期知識庫。請照這個順序建立理解：README.md → 06_rules_for_agents.md（10 條解讀規則，之後每次回答都要遵守）→ 05_glossary.md → 04_methodology.md。
>
> 資料來源的規則：附件只是上傳當天的快照。真正最新的版本永遠在這組固定網址，每個美股交易日的台北 06:15 到 06:45 之間由 GitHub Actions 自動換新（失敗時 07:00 與 08:30 重試）：
> https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md（一頁簡報）、https://corleonis6422.github.io/stock-dashboard/meta/09_market_dashboard.md（六個儀表：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌）、https://corleonis6422.github.io/stock-dashboard/meta/08_today_news.md（今日時事）、https://corleonis6422.github.io/stock-dashboard/meta/02_trade_plan.md（交易計畫）、https://corleonis6422.github.io/stock-dashboard/meta/data/latest.json（結構化資料）、https://corleonis6422.github.io/stock-dashboard/meta/manifest.json（data_as_of 與檔案清單）。
> 每次我問 SOXL，或你要主動回報之前，先抓網址，讀 data_as_of，確認它等於最近一個已收盤的美股交易日（美東 16:00 收盤；週末與 NYSE 假日順延）。如果網址抓不到、或 data_as_of 比附件還舊，就改用附件，並且第一句先告訴我「資料是 X 月 X 日的，網址沒有更新」。
>
> 每個美股交易日（週二到週六）的台北 07:30，請自己抓上面的網址並主動傳一則日報給我；如果 data_as_of 還不是最近一個已收盤的美股交易日，先不要發，09:00 再抓一次，還是舊的就告訴我「今天網址沒更新，資料日是 X」。日報格式固定三句話：（1）今天該買、該賣還是觀望：先轉述「新手一眼看懂」的答案（beginner.buy.answer），再轉述交易計畫表的 side、進場觸發、停損、T1、T2 與加權風報比，side 是 no_trade 就說「今天不開新倉，觸發價是 X」；（2）最重要的一個理由，加上「今天最大的事」（beginner.biggest_thing 或 08_today_news.md 的第一則：美伊、川普、聯準會、關稅、龍頭財報等）與它對 SOXL 的影響；（3）要盯的三個價位：停損、T1、期權牆或 Gamma 翻正位。然後用一行列出六個儀表的燈號（dashboard.one_liner：能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數）。最後一行列 48 小時內的風險事件（沒有就寫「無」），再附免責聲明。
> 只有在這些情況才需要多寫：評級改變（changes.verdict_changed）、崩跌前兆分數跨過 60 或 80、trade_plan.side 變成 long 或 long_pending、48 小時內有 FOMC 或龍頭財報、warnings 非空。其他日子三句話就好。
>
> 引用規則：任何勝率都要連同基準與 N 一起講（例如「64%，基準 55%，N=62，p=0.09」），significant 為 false 的訊號不可以說「高勝率」；賣出訊號歷史上沒有預測力，只能用來決定減碼節奏，停損才是出場依據；期權牆是模型推算值，會每天變；兩種 200 日線讀法不一致時兩個都講。不要加入任何資料包以外的價格預測。
>
> 我問「能不能加碼」時只讀 09_market_dashboard.md 第一格（dashboard.gauges 的 add_on），照它的燈號與一句話回答，附停損與減碼點；我追問「我持有中怎麼辦」時用 prompts/holder_check.md 的方式回答；週末用 prompts/weekly_review.md 做檢討。用繁體中文回答。

English version:

> The attached meta.zip is a quant brief pack for SOXL (3x semiconductor ETF); treat it as your standing knowledge base. Build understanding in this order: README.md, then 06_rules_for_agents.md (10 rules you must follow in every answer), then 05_glossary.md and 04_methodology.md.
> Source of truth: the attachment is only a snapshot. The current version always lives at these fixed URLs, refreshed by GitHub Actions between 06:15 and 06:45 Taipei after every US close (retries at 07:00 and 08:30): https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md, https://corleonis6422.github.io/stock-dashboard/meta/09_market_dashboard.md, https://corleonis6422.github.io/stock-dashboard/meta/08_today_news.md, https://corleonis6422.github.io/stock-dashboard/meta/02_trade_plan.md, https://corleonis6422.github.io/stock-dashboard/meta/data/latest.json, https://corleonis6422.github.io/stock-dashboard/meta/manifest.json. Before answering any SOXL question or sending a report, fetch them, read data_as_of, and confirm it equals the last completed US session. If the URLs fail or are older than the attachment, use the attachment and open with "data is from DATE; the URL has not refreshed".
> Every US trading day (Tuesday to Saturday) at 07:30 Taipei, fetch the URLs yourself and send me the daily brief; if data_as_of is not yet the last completed US session, do not send, fetch again at 09:00, and if it is still stale tell me "the URL did not refresh today, data is from DATE". The brief is three sentences: (1) buy, sell or stay out: lead with beginner.buy.answer, then relay the trade plan's side, entry trigger, stop, T1, T2 and blended R:R (for no_trade say "no new position today, trigger is X"); (2) the single most important reason plus "the biggest thing today" (beginner.biggest_thing or the first row of 08_today_news.md: Iran, Trump, the Fed, tariffs, a chip leader's earnings) and its impact on SOXL; (3) the three prices to watch: stop, T1, and the option wall or gamma flip. Then one line with the six gauge lights (dashboard.one_liner: add-on?, macro, SOX index trend, whales, put/call, crash score). End with one line of risk events in the next 48 hours (or "none") and the disclaimer. Write more only when the verdict changed, crash_risk crossed 60 or 80, trade_plan.side became long or long_pending, FOMC or a leader's earnings falls within 48 hours, or warnings is non-empty.
> Quoting rules: every win rate comes with its base rate and N; never call a signal with significant=false "high win rate"; sell signals have no predictive edge and only set the pace of reducing, the stop is the exit; option walls are model estimates that change daily; when the two 200-day regime readings disagree, state both. Do not add price predictions from outside the pack.
> For "can I add to my position" read only the first gauge of 09_market_dashboard.md (dashboard.gauges add_on) and answer with its light, sentence, stop and reduce levels; for "I am holding, what now" use prompts/holder_check.md; on weekends use prompts/weekly_review.md. Answer in Traditional Chinese.

怎麼讓它真的每天自動更新（三選一，新資料都在同一組網址）：

1. Muse 能上網：上面的 prompt 已經要求它每天 07:30 自己抓 https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md。前提是這個 repo 已經推上 GitHub（`git push`）；之後 GitHub Actions 每個交易日台北 06:15 自己重算並更新網址（07:00、08:30 重試），不需要這台電腦開機。
2. Muse 有可以收東西的入口（webhook / email）：在 `notify_config.json` 設定該頻道（範本 `notify_config.example.json`），每次更新後 `auto_update.py run` 會自動把簡報推過去；`auto_update.py push-test` 可先測。
3. 都沒有：每天重新附一次 zip（`auto_update.py meta --zip` 會放到 ~/Downloads），只在前兩條都不通時用。
