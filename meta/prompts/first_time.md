# 提示：第一次附上 meta.zip 時貼這段

> 附件是 SOXL（三倍做多半導體 ETF）的量化簡報資料包。請先讀 README.md 和 06_rules_for_agents.md，照裡面的 10 條規則解讀，再讀 05_glossary.md 認識名詞。然後讀 01_brief_today.md 與 02_trade_plan.md，用三句話告訴我：今天該買、該賣還是觀望；最重要的理由；要盯的停損、T1 和期權牆價位。先確認 data_as_of 是最近一個已收盤的美股交易日，不是就先說資料是哪一天的。引用勝率一定連同基準與 N，賣出訊號不是預測。最後一行列 48 小時內的風險事件，並附免責聲明。以後每次我問 SOXL，請先自己到 https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md 抓最新版（每個美股交易日收盤後更新，同一個網址），對照 data_as_of 確認是新的再回答；抓不到網路時才用我附的檔案，並說明資料日期。

English version:

> The attachment is a quant brief pack for SOXL (3x semiconductor ETF). Read README.md and 06_rules_for_agents.md first and follow its 10 rules, then 05_glossary.md for terms. Then read 01_brief_today.md and 02_trade_plan.md and answer in three sentences: buy, sell or stay out today; the single most important reason; the stop, T1 and option-wall prices to watch. Check that data_as_of is the last completed US session and say so if it is not. Quote every win rate with its base rate and N; sell signals are not predictions. End with one line of risk events in the next 48 hours and the disclaimer. From now on, whenever I ask about SOXL, first fetch the latest version yourself from https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md (same URL, refreshed after every US close), confirm data_as_of is current, then answer; fall back to the attached files only when you cannot browse, and say which date the data is from.

怎麼讓它真的每天自動更新（三選一，由新到舊的資料都在同一組網址）：

1. Muse 能上網：上面的 prompt 已經要求它每次先抓 https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md。前提是這個 repo 已經推上 GitHub（`git push`），GitHub Pages 才會每天 07:30 台北更新這組網址。
2. Muse 有可以收東西的入口（webhook / email）：在 `notify_config.json` 設定該頻道（範本 `notify_config.example.json`），每次更新後 `auto_update.py run` 會自動把簡報推過去；`auto_update.py push-test` 可先測。
3. 都沒有：每天重新附一次 zip（`auto_update.py meta --zip` 會放到 ~/Downloads），這是最笨的做法，只在前兩條都不通時用。
