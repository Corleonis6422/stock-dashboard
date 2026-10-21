# AGENTS.md — 給 Muse 與任何 AI Agent 的吸收指南

> 這個 repo 每個美股交易日收盤後自動產生 **SOXL（三倍做多半導體 ETF）** 的量化評級、關鍵價位、情緒、消息與事件簡報。
> 本文件告訴一個 agent：**去哪裡拿、拿什麼、怎麼解讀、什麼時候算新鮮、怎麼把結果推回給人**。
> English summary at the bottom.

---

## 0. 三十秒版

| 你要什麼 | 去哪裡 |
|---|---|
| 一頁式人話簡報（Markdown，約 7 KB） | `https://corleonis6422.github.io/stock-dashboard/feed/latest.md` 或本機 `feed/latest.md` |
| 結構化資料（JSON，schema `soxl-quant-brief/1`，約 45 KB） | `…/feed/latest.json`，欄位說明見 `…/feed/schema.json` |
| 手機短訊版（≤ 900 字） | `…/feed/latest.txt` |
| 訂閱（RSS 2.0，一天一則） | `…/feed/rss.xml` |
| 即時報價（更新當下的 SOXL / 龍頭股 / VIX 複合體） | `…/feed/quotes.json`；要真正即時用 MCP `get_quotes` 或 `auto_update.py quotes` |
| 完整分析（所有模組，約 500 KB） | `…/soxl_analysis_data.json` |
| 人看的頁面 | 新手版 `…/soxl_simple.html`、完整版 `…/soxl_analysis_report.html`（＝ `…/index.html`） |
| 歷史簡報 | `…/feed/index.json` 列表 → `…/feed/YYYY-MM-DD.{json,md}`（保留 120 天） |

**先讀 `feed/latest.md`，需要數字再開 `feed/latest.json`。** 兩者來自同一個 dict，內容一致。

---

## 1. 三種接法（擇一或併用）

### A. Pull：直接抓網址（最無痛，零安裝）

每天台北 07:30 左右（美股收盤後 3.5 小時）內容更新；GitHub Actions 的雲端備援在 UTC 22:15 / 00:30 另外檢查一次。
Agent 端只需要：

1. `GET feed/latest.json`
2. 檢查 `data_as_of` 是否等於「最近一個已收盤的美股交易日」（見第 3 節的新鮮度規則）
3. 讀 `verdict`、`price`、`levels`、`plan`、`changes`、`events`、`news`，必要時讀 `feed/latest.md` 直接餵給 LLM

```bash
curl -s https://corleonis6422.github.io/stock-dashboard/feed/latest.json | python3 -c "import json,sys; b=json.load(sys.stdin); print(b['data_as_of'], b['verdict']['emoji'], b['verdict']['label'], b['verdict']['composite'], b['plan']['stop'])"
```

### B. MCP：在本機把它變成工具（Antigravity / Gemini CLI / Claude / Cursor / 任何 MCP host）

```bash
.venv/bin/python auto_update.py mcp-config    # 印出設定片段
.venv/bin/python auto_update.py mcp-install   # 直接寫進 ~/.gemini/config/mcp_config.json（先備份）
```

MCP server `soxl_mcp.py`（stdio、純標準函式庫）提供：

| 工具 | 用途 |
|---|---|
| `get_brief(format=markdown\|text\|json)` | 最新簡報（先呼叫這個） |
| `get_latest(section=None)` | 完整 JSON；給 `section` 名稱（`options` / `technicals` / `sentiment` / `early_warning` / `news` / `scoring` / `playbook` …）取該區段 |
| `get_quotes(include_leaders=true)` | **即時**報價：SOXL / SOXS / SOXX / SPY / QQQ、NVDA 等 7 檔、VIX / VIX3M / VIX9D / SKEW（含盤後價、市場狀態） |
| `get_news(days=3, max_per_day=6)` | 依日分組、已分多空的新聞標題與連結 |
| `get_events(horizon_days=14)` | FOMC（Fed 官網）、成分股財報（Nasdaq）、週/月選擇權到期、休市 |
| `get_history(days=30)` | 每日評級紀錄與之後 5 / 10 日實際報酬（自我驗證） |
| `get_status()` | 排程、上次更新、推播與 git 發佈結果、是否過期 |
| `refresh(if_stale=true, wait=false)` | 觸發重新抓取與重算（背景執行，1–5 分鐘） |

資源 `soxl://brief/latest.md`、`soxl://brief/latest.json`、`soxl://feed/rss.xml`、`soxl://report/simple.html` …；
提示範本 `daily_briefing`（把簡報與「三句話回答買/賣/觀望」的指令一起送給模型）。

### C. Push：更新完主動推給 Muse / 你

每次成功更新後，`auto_update.py run` 會依 `notify_config.json` 推播（檔案已 `.gitignore`、`chmod 600`；範本 `notify_config.example.json`）：

| `type` | 送到哪 | 需要填 |
|---|---|---|
| `macos` | 這台 Mac 的通知中心 | 無 |
| `webhook` | **任何 HTTPS 端點（Muse 的 inbox）**；`format` = `json`（完整信封含 `brief`）/ `slim`（不含 `brief`）/ `text`（Markdown 本文） | `url`，可選 `bearer_token`、`hmac_secret`（`X-SOXL-Signature: sha256=…`）、`headers` |
| `google_chat` / `slack` / `discord` | 對應 incoming webhook | `url` |
| `telegram` | Bot API | `bot_token`、`chat_id` |
| `line` | LINE Messaging API push | `channel_access_token`、`to` |
| `email` | SMTP（STARTTLS / SSL），附兩個 HTML | `smtp_host`、`username`、`password`、`to` |
| `agentapi` | **Antigravity / Jetski 的 agent 對話**（`new_conversation` 或 `send_message` 到指定對話 ID）。只在 agent 環境內有效（需要 `ANTIGRAVITY_LS_ADDRESS`），所以適合由 Muse 自己執行 `auto_update.py push --only agentapi`；排程推播請用下面的 sidecar | 可選 `recipient_id`、`prompt_prefix`、`model` |
| `command` | 本機任意執行檔（argv 陣列、不經 shell），stdin 收到 JSON 信封；`{title} {text} {markdown} {json_path} {md_path} {html_path}` 會被代入 | `argv` |

```bash
.venv/bin/python auto_update.py notify-config   # 建立 notify_config.json
.venv/bin/python auto_update.py push-test       # 對所有啟用頻道送測試訊息
.venv/bin/python auto_update.py push            # 把最新簡報再推一次（--only webhook,telegram）
```

**D. Antigravity sidecar（Muse 在 Antigravity 裡時最直接的「推給我」）**

```bash
.venv/bin/python auto_update.py sidecar-install          # 預設週二～六 07:50（資料更新 07:30 之後）
.venv/bin/python auto_update.py sidecar-install --time 08:00 --model pro
.venv/bin/python auto_update.py sidecar-uninstall
```

寫入 `~/.gemini/config/sidecars/soxl-daily-brief/sidecar.json`（`builtin: schedule` → `agentapi new-conversation`）。每個交易日早上 Antigravity 會自動開一個標題「SOXL 每日簡報」的新對話，agent 讀 `feed/latest.md`，確認 `data_as_of` 新鮮度，然後用三句話告訴你該買 / 該賣 / 觀望、理由、要盯的價位、倉位上限、停損 / 目標、48 小時內風險事件。

Webhook JSON 信封：

```json
{
  "event": "soxl.daily_brief",          // 或 soxl.update_failed / soxl.test
  "schema": "soxl-quant-brief/1",
  "sent_at": "2026-10-21T07:35:10",
  "title": "SOXL 2026-10-20 🔴 賣出 / 減碼｜$97.6（-1.06%）",
  "text": "…≤ 900 字短訊…",
  "markdown": "…feed/latest.md 全文…",
  "summary": {"data_as_of": "2026-10-20", "verdict": "賣出 / 減碼", "emoji": "🔴", "composite": -0.93, "size_pct": 10, "close": 97.6, "ret_1d": -1.06},
  "links": {"report_html": "…", "simple_html": "…", "brief_json": "…", "rss": "…"},
  "brief": { …feed/latest.json 全文… }
}
```

---

## 2. `feed/latest.json` 欄位指南（agent 該信哪些數字）

| 區段 | 關鍵欄位 | 意義與單位 |
|---|---|---|
| 頂層 | `data_as_of` | 這份數字描述的**美股交易日**（YYYY-MM-DD）。`generated_at` 是產生時間（Asia/Taipei） |
| | `data_status.label` / `provisional` / `final` | `官方日線`＝Nasdaq 正式日線；`收盤即時報價補齊`＝收盤後用即時報價補的當日 K 線（與官方可能差幾分錢）；`盤中快照`＝還沒收盤，**不要當成收盤結論** |
| | `warnings[]` | 本次失敗的資料來源；非空時相關區段是降級值 |
| `verdict` | `label` | 五級之一：`強力買進` / `買進` / `觀望` / `賣出 / 減碼` / `強力賣出`（`rating_5` 5→1） |
| | `composite` | 加權綜合分 **−2 … +2**；`trend_score`（趨勢面）與 `contrarian_score`（逆勢/情緒面）分開給 |
| | `consensus.{buy,hold,sell}_pct` | 24 個因子依權重的多 / 中性 / 空比例 |
| | `size_pct` | 建議**倉位上限**（風險資金 %），已考慮三倍槓桿與波動 |
| | `confidence`、`agreement_pct` | 因子一致程度 |
| | `tldr[]`、`one_liner`、`q_no_position`、`q_holder`、`q_when` | 給人看的結論與「沒部位 / 有部位 / 何時」三問三答 |
| `price` | `close`、`ret_1d/5d/20d`（%）、`drawdown_52w_pct`、`rvol20`（相對 20 日均量倍數） | |
| `levels` | `sma20/50/200`、`ma_structure`、`fib`、`pivot`、`ladder[]`（由上而下的壓力 / 支撐階梯，`kind`=`res`/`sup`） | 價位皆為美元 |
| `plan` | `stop_price`（停損）、`target1_price`、`target2_price`、`entry`、`risk_reward` | 劇本 A 反彈單的操作參數；`max_size_pct` 同 `verdict.size_pct` |
| `options` | `put_wall`、`call_wall`、`gamma_flip`、`net_gex_m`（百萬美元）、`pc_vol_ratio`、`iv30_pct`、`expected_move.{weekly,monthly}`（±% 與價格區間）、`whale.whale_net_score`（−1…+1） | CBOE 延遲鏈 |
| `sentiment` | `fear_greed.score`（0–100）、`vix.{vix,vix3m,ratio_vix_3m,term_state,skew,vvix}`、`market_put_call.equity_pc`、`flows.ratio`（SOXL/SOXS 美元成交量比） | |
| `breadth` | `above_sma20_pct` 等（16 檔成分股站上均線比例）、`constituents[]` | |
| `macro` | `kpis[]`（10Y/30Y 殖利率、Brent、VIX、DXY、HYG…；`chg_1d`、`corr_20d`） | |
| `crash_risk` | `score`（0–100 百分位；≥ 80 警戒、≥ 60 注意）、`zone`、`active_signals[]`、`event_study.stats_top_80` | 崩跌前兆系統 |
| `scenarios[]` | 劇本 A / B / C：`prob`（%）、`trigger`、`target`、`action` | 來自歷史同類情境 |
| `checklist[]` | 底部確認八項：`item`、`ok`、`now` | `verdict.checklist` = 通過數 |
| `watch[]` | 明天要盯的價位 / 指標 | |
| `news` | `bull_7d`、`bear_7d`、`bull_bear_ratio`、`themes_7d[]`、`top_bull[]`、`top_bear[]`（`title`、`publisher`、`link`） | 關鍵字分類，非 LLM 判讀 |
| `events` | `upcoming[]`（`date`、`type`=`fomc`/`earnings`/`opex`/`holiday`、`label`、`days_ahead`）、`next_fomc` | |
| `quotes` | `one_liner`、`rows[]`、`fetched_at_tpe` | **產生當下**的即時快照，不是收盤價 |
| `changes` | `verdict_changed`、`composite_delta`、`same_verdict_streak_days`、`notes[]` | 跟前一交易日比 |
| `history[]` | 最近 15 個交易日的評級、收盤、`fwd_ret_5d/10d` | 事後驗證 |
| `links` | 所有公開網址 | |

---

## 3. 解讀規則（請 agent 遵守）

1. **新鮮度**：`data_as_of` 應等於最近一個已收盤的美股交易日（美東 16:00 + 75 分鐘後換日；週末與 NYSE 假日順延）。若落後，先說「資料是 X 月 X 日的」，再給結論；可呼叫 MCP `refresh` 或等 07:30 的排程。
2. **盤中快照不是結論**：`data_status.provisional=true 且 final=false` 時，評級只反映當下，收盤後會重算。
3. **評級不是指令**：`verdict` 是 24 個因子的加權投票；請一併轉述 `confidence`、`consensus` 與 `size_pct`，並提醒三倍槓桿單日可 ±15%。
4. **價位優先於形容詞**：回覆人類時至少給三個數字：停損 `plan.stop_price`、第一目標 `plan.target1_price`、關鍵牆（`options.put_wall` / `call_wall` / `gamma_flip`）。
5. **有變化才值得打擾**：`changes.verdict_changed=true`、`crash_risk.score` 跨過 60 / 80、`events.upcoming` 內 48 小時有 FOMC 或龍頭財報、`warnings` 非空 → 值得主動推；否則一句話即可。
6. **引用來源**：新聞請附 `publisher` 與 `link`；數字請附 `data_as_of`。
7. **免責**：所有輸出都要帶 `disclaimer`（自動計算的研究參考，不是投資建議）。

建議給 LLM 的開場提示（也就是 MCP `daily_briefing` 提示的內容）：

> 以下是今天自動產生的 SOXL 簡報。請用新手聽得懂的話，三句以內回答：今天該買、該賣還是觀望？最重要的理由是什麼？要盯哪一個價位？最後用一行列出 48 小時內的風險事件。

---

## 4. 更新節奏與資料來源

- **本機 launchd**：週二～六 07:30（台北）＝美股週一～五收盤後；登入 / 喚醒時若資料過期會補跑。流程：抓 API → 重算 → HTML → `feed/` → 推播 → `git push`（→ GitHub Pages）。
- **雲端備援** `.github/workflows/daily-update.yml`：UTC 22:15 與 00:30 檢查 repo 內 `data_as_of` 是否落後，落後才在 GitHub Actions 跑一次並 commit。
- 來源（全部免費免金鑰）：Nasdaq（日線、當日 K 線、即時報價、財報日曆）、CBOE（選擇權鏈、VIX 家族、Put/Call、延遲指數報價）、CNN Fear & Greed、美國財政部殖利率、Fed 官網（FOMC 日程、新聞稿 RSS）、Yahoo Finance、Google News、Nasdaq / Seeking Alpha 個股 RSS、CNBC、MarketWatch。
- 任一來源失敗只會降級該區段並寫進 `warnings`，不會中斷。

---

## 5. 本機指令速查

```bash
.venv/bin/python auto_update.py brief            # 印 feed/latest.md（--json / --text）
.venv/bin/python auto_update.py quotes           # 即時報價（--json）
.venv/bin/python auto_update.py feed             # 不重算模型，重建 feed/（含最新事件與報價）
.venv/bin/python auto_update.py run              # 完整更新 + 推播 + 發佈
.venv/bin/python auto_update.py status           # 排程 / 上次結果 / 推播 / git
.venv/bin/python tools/test_mcp.py               # 驗證 MCP server
.venv/bin/python tools/test_push.py              # 驗證推播（本機假 inbox）
```

---

## English summary

Daily (after the US close) this repo regenerates a SOXL quant brief. Agents should **read `feed/latest.md`** (one page, zh-TW) or **`feed/latest.json`** (schema `soxl-quant-brief/1`; see `feed/schema.json`). Public URLs live under `https://corleonis6422.github.io/stock-dashboard/`. Three integration paths: (A) pull the URLs, (B) run the stdio MCP server `soxl_mcp.py` (tools: `get_brief`, `get_latest`, `get_quotes`, `get_news`, `get_events`, `get_history`, `get_status`, `refresh`), (C) receive pushes configured in `notify_config.json` (generic HTTPS webhook with optional bearer token + HMAC-SHA256, Google Chat, Slack, Discord, Telegram, LINE, e-mail, Antigravity `agentapi`, or any local command). Always check `data_as_of` against the last completed US session, treat `data_status.provisional && !final` as intraday, relay `verdict.size_pct` and the three prices in `plan`, and include the disclaimer. Not investment advice.
