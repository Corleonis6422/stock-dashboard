#!/usr/bin/env python3
"""Agent operator pack — a zip an AI agent (Meta AI / Muse or any agent with a shell) can follow to
put this repo live on GitHub, confirm the automation, wire every API, and consume the output daily.

Why a separate pack from ``meta/``
  ``meta/`` is what an agent READS every day (the brief).  This pack is what an agent DOES once
  (publish + wire) plus the standing operating procedure.  It bundles:

    README.md       the runbook, written as an operator spec: facts, decision tree, numbered steps with the
                    exact command, the expected output and the failure branch; API map in three layers
                    (upstream data APIs the pipeline calls, published endpoints the agent fetches, delivery
                    channels that push into the agent); daily loop; acceptance checklist; troubleshooting
    RUNBOOK.json    the same steps machine-readable (id, run, expect, on_fail)
    APIS.md / apis.json
                    every endpoint with purpose, auth (all upstream feeds are keyless), cache TTL, what breaks
                    when it fails, and a one-line test
    meta/           the daily knowledge pack (copied)
    stock-dashboard_repo_<date>.zip
                    the repository with its .git history (what gets pushed)

Everything here is generated from the live repo state so the facts (HEAD, data_as_of, remote, URLs) are
never stale copies.  Nothing secret is written: tokens stay in environment variables / GitHub Secrets.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import subprocess

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://corleonis6422.github.io/stock-dashboard/"
REPO_HTTPS = "https://github.com/Corleonis6422/stock-dashboard"
REPO_SSH = "git@github.com:Corleonis6422/stock-dashboard.git"
PACK_VERSION = "soxl-agent-pack/1"


# --------------------------------------------------------------------------- #
# facts (measured from the working copy at build time)
# --------------------------------------------------------------------------- #
def _git(*args: str) -> str:
  try:
    r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip()
  except Exception:  # noqa: BLE001
    return ""


def facts(br: dict | None, base_url: str | None = None, repo_zip: Path | None = None) -> dict:
  br = br or {}
  base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
  head = _git("rev-parse", "--short", "HEAD")
  return {
      "pack": PACK_VERSION, "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "built_at_tz": "Asia/Taipei",
      "data_as_of": br.get("data_as_of"), "generated_at": br.get("generated_at"), "verdict": (br.get("verdict") or {}).get("label"),
      "plan_side": (br.get("trade_plan") or {}).get("side"), "schema": br.get("schema"),
      "git": {"head": head, "head_subject": _git("log", "-1", "--format=%s"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "main",
              "commits": _git("rev-list", "--count", "HEAD"), "remote": _git("remote", "get-url", "origin") or REPO_SSH, "dirty": bool(_git("status", "--porcelain")),
              "remote_history_shared": False},
      "github": {"owner": "Corleonis6422", "repo": "stock-dashboard", "https": REPO_HTTPS, "ssh": REPO_SSH, "default_branch": "main",
                 "pages_base_url": base, "workflows": ["daily-update.yml", "deploy.yml"]},
      "schedule": {"actions_utc": ["22:15 Mon-Fri", "23:00 Mon-Fri", "00:30 Tue-Sat"], "actions_taipei": ["06:15", "07:00", "08:30"], "mac_launchd_taipei": "07:30 Tue-Sat",
                   "agent_fetch_taipei": "07:30, retry 09:00"},
      "repo_zip": (repo_zip.name if repo_zip else None), "repo_zip_bytes": (repo_zip.stat().st_size if repo_zip and repo_zip.exists() else None),
  }


# --------------------------------------------------------------------------- #
# API inventory (three layers)
# --------------------------------------------------------------------------- #
def apis(base: str) -> list[dict]:
  up = "upstream"
  return [
      # ---- upstream data (the pipeline calls these; keyless; cached under .cache/)
      {"id": "nasdaq_history", "layer": up, "name": "Nasdaq 日線 (SOXL / SOXX / 16 成分股 / SOXS / SPY / QQQ)", "url": "https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass={etf|stocks}&fromdate=…&todate=…&limit=…", "method": "GET", "auth": "none", "ttl_sec": 21600,
       "used_by": "technicals, backtest (10y), heatmap, benchmarks, dashboard.soxx", "on_failure": "pipeline 中斷（這是核心價格來源）；重試 3 次後整次更新失敗", "test": "curl -s -A Mozilla 'https://api.nasdaq.com/api/quote/SOXL/historical?assetclass=etf&limit=5' | head -c 300"},
      {"id": "nasdaq_quote", "layer": up, "name": "Nasdaq 即時報價 (含盤前 / 盤後)", "url": "https://api.nasdaq.com/api/quote/{symbol}/info?assetclass={etf|stocks}", "method": "GET", "auth": "none", "ttl_sec": 120,
       "used_by": "quotes.snapshot, data_status（收盤即時報價補齊）", "on_failure": "報價區段為 n/a；收盤後若官方日線未出，當日 K 線缺", "test": "curl -s -A Mozilla 'https://api.nasdaq.com/api/quote/SOXL/info?assetclass=etf' | head -c 300"},
      {"id": "nasdaq_chart", "layer": up, "name": "Nasdaq 當日分時 (補當日 K 線)", "url": "https://api.nasdaq.com/api/quote/{symbol}/chart?assetclass={etf|stocks}", "method": "GET", "auth": "none", "ttl_sec": 600, "used_by": "datafeed._augment_latest", "on_failure": "data_status.provisional=true", "test": "—"},
      {"id": "nasdaq_earnings", "layer": up, "name": "Nasdaq 財報日曆", "url": "https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD", "method": "GET", "auth": "none", "ttl_sec": 43200, "used_by": "events (成分股財報)", "on_failure": "events.upcoming 少了財報列", "test": "curl -s -A Mozilla 'https://api.nasdaq.com/api/calendar/earnings?date=2026-10-28' | head -c 300"},
      {"id": "nasdaq_rss", "layer": up, "name": "Nasdaq 個股新聞 RSS", "url": "https://www.nasdaq.com/feed/rssoutbound?symbol={sym}", "method": "GET", "auth": "none", "ttl_sec": 1800, "used_by": "news", "on_failure": "新聞數變少", "test": "curl -s 'https://www.nasdaq.com/feed/rssoutbound?symbol=soxl' | head -c 300"},
      {"id": "cboe_chain", "layer": up, "name": "CBOE 延遲選擇權鏈 (SOXL / SOXX / SOXS)", "url": "https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json", "method": "GET", "auth": "none", "ttl_sec": 3600,
       "used_by": "options_flow: Put/Call、Call/Put 牆、GEX、Gamma 翻正、IV、大戶 (whale)、預期波動", "on_failure": "options 區段降級；trade_plan 的期權衍生價位缺", "test": "curl -s 'https://cdn.cboe.com/api/global/delayed_quotes/options/SOXL.json' | head -c 300"},
      {"id": "cboe_quote", "layer": up, "name": "CBOE 延遲指數報價 (VIX / VIX3M / VIX9D / SKEW / VVIX)", "url": "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{_SYMBOL}.json", "method": "GET", "auth": "none", "ttl_sec": 120, "used_by": "quotes, sentiment.vix", "on_failure": "VIX 家族為 n/a", "test": "curl -s 'https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json' | head -c 300"},
      {"id": "cboe_index_history", "layer": up, "name": "CBOE 指數歷史 CSV (VIX、VIX3M…)", "url": "https://cdn.cboe.com/api/global/us_indices/daily_prices/{NAME}_History.csv", "method": "GET", "auth": "none", "ttl_sec": 21600, "used_by": "sentiment, early_warning, backtest (VIX 期限結構訊號)", "on_failure": "VIX 類訊號跳過", "test": "curl -s 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv' | head -3"},
      {"id": "cboe_putcall", "layer": up, "name": "CBOE 全市場 Put/Call 日統計", "url": "https://cdn.cboe.com/data/us/options/market_statistics/daily/?dt=YYYY-MM-DD", "method": "GET", "auth": "none", "ttl_sec": 604800, "used_by": "sentiment.put_call, dashboard.put_call", "on_failure": "全市場 P/C 為 n/a（SOXL 自身 P/C 仍在）", "test": "—"},
      {"id": "cnn_fear_greed", "layer": up, "name": "CNN Fear & Greed", "url": "https://production.dataviz.cnn.io/index/fearandgreed/graphdata", "method": "GET", "auth": "none (需瀏覽器 UA + Referer cnn.com)", "ttl_sec": 3600, "used_by": "sentiment.fear_greed", "on_failure": "F&G 為 n/a，評分表該因子中性", "test": "curl -s -A Mozilla -H 'Referer: https://www.cnn.com/markets/fear-and-greed' 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata' | head -c 200"},
      {"id": "treasury_yields", "layer": up, "name": "美國財政部殖利率 CSV", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{YEAR}/all?type=daily_treasury_yield_curve&field_tdr_date_value={YEAR}&page&_format=csv", "method": "GET", "auth": "none", "ttl_sec": 21600, "used_by": "macro (10Y / 30Y)", "on_failure": "macro 殖利率缺、相關係數缺", "test": "—"},
      {"id": "fed_fomc", "layer": up, "name": "Fed FOMC 日程頁", "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "method": "GET", "auth": "none", "ttl_sec": 604800, "used_by": "events.next_fomc", "on_failure": "48 小時事件少了 FOMC", "test": "curl -s https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm | head -c 200"},
      {"id": "fed_press_rss", "layer": up, "name": "Fed 新聞稿 RSS", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "method": "GET", "auth": "none", "ttl_sec": 1800, "used_by": "news, newsflash (fed_statement_24h 旗標)", "on_failure": "旗標無法亮", "test": "curl -s https://www.federalreserve.gov/feeds/press_all.xml | head -c 300"},
      {"id": "yahoo_chart", "layer": up, "name": "Yahoo Finance 歷史 (宏觀代理: ^TNX ^TYX BNO UUP HYG GLD CPER IBIT, 以及備援)", "url": "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=…&interval=1d", "method": "GET", "auth": "none (每 2.2 秒一次，避免 429)", "ttl_sec": 21600, "used_by": "macro, sentiment.cross_asset", "on_failure": "macro.missing 列出缺的 KPI", "test": "curl -s -A Mozilla 'https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?range=5d&interval=1d' | head -c 300"},
      {"id": "yahoo_search_news", "layer": up, "name": "Yahoo Finance 新聞搜尋", "url": "https://query2.finance.yahoo.com/v1/finance/search?q={query}&newsCount=…", "method": "GET", "auth": "none", "ttl_sec": 1800, "used_by": "news", "on_failure": "新聞數變少", "test": "—"},
      {"id": "google_news_rss", "layer": up, "name": "Google News RSS 搜尋 (newsflash 23 題 + news 數題)", "url": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en", "method": "GET", "auth": "none", "ttl_sec": 1800, "used_by": "newsflash (今日時事 / 旗標 / 今天最大的事), news", "on_failure": "flash.errors 列出失敗的查詢；簡報「今日時事」縮水", "test": "curl -s 'https://news.google.com/rss/search?q=Iran&hl=en-US&gl=US&ceid=US:en' | head -c 300"},
      {"id": "cnbc_rss", "layer": up, "name": "CNBC Markets / Tech RSS", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id={20910258|19854910}", "method": "GET", "auth": "none", "ttl_sec": 1800, "used_by": "news, newsflash", "on_failure": "新聞數變少", "test": "—"},
      {"id": "marketwatch_rss", "layer": up, "name": "MarketWatch Top Stories / Market Pulse RSS", "url": "https://feeds.content.dowjones.io/public/rss/{mw_topstories|mw_marketpulse}", "method": "GET", "auth": "none", "ttl_sec": 1800, "used_by": "news, newsflash", "on_failure": "新聞數變少", "test": "—"},
      {"id": "seekingalpha_rss", "layer": up, "name": "Seeking Alpha 公開 RSS (個股 combined、Wall Street Breakfast、Market Outlook、Macro View)", "url": "https://seekingalpha.com/api/sa/combined/{SYM}.xml ; https://seekingalpha.com/tag/{wall-st-breakfast|market-outlook|macro-view}.xml", "method": "GET", "auth": "none (每 1 秒一次)", "ttl_sec": 1800, "used_by": "news, newsflash (flash.seeking_alpha[]、宏觀標題)", "on_failure": "Seeking Alpha 觀點區塊空白", "test": "curl -s 'https://seekingalpha.com/api/sa/combined/SOXL.xml' | head -c 300"},
      # ---- published endpoints (what an agent fetches every day)
      {"id": "pub_manifest", "layer": "publish", "name": "meta/manifest.json（先抓這個：data_as_of、檔案清單）", "url": base + "meta/manifest.json", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "agent 新鮮度檢查", "on_failure": "網址 404 = Pages 尚未部署；data_as_of 落後 = 雲端更新尚未跑完（07:00 / 08:30 會重試）", "test": f"curl -s {base}meta/manifest.json | python3 -c \"import json,sys;m=json.load(sys.stdin);print(m['data_as_of'], m['verdict'], m['plan_side'])\""},
      {"id": "pub_brief_md", "layer": "publish", "name": "一頁簡報 Markdown（= meta/01_brief_today.md）", "url": base + "feed/latest.md", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "agent 日報（先讀「新手一眼看懂」與「六個儀表」）", "on_failure": "改讀 latest.json", "test": f"curl -s {base}feed/latest.md | head -20"},
      {"id": "pub_brief_json", "layer": "publish", "name": "結構化簡報 JSON（schema soxl-quant-brief/2）", "url": base + "feed/latest.json", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "agent：beginner.buy / dashboard.gauges / trade_plan / flash / events", "on_failure": "—", "test": f"curl -s {base}feed/latest.json | python3 -c \"import json,sys;b=json.load(sys.stdin);print(b['data_as_of'], b['beginner']['buy']['answer'], b['dashboard']['one_liner'])\""},
      {"id": "pub_brief_txt", "layer": "publish", "name": "短訊版（≤ 900 字）", "url": base + "feed/latest.txt", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "手機 / 推播", "on_failure": "—", "test": f"curl -s {base}feed/latest.txt"},
      {"id": "pub_schema", "layer": "publish", "name": "JSON Schema", "url": base + "feed/schema.json", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "agent 讀欄位定義", "on_failure": "—", "test": "—"},
      {"id": "pub_rss", "layer": "publish", "name": "RSS 2.0（一天一則）", "url": base + "feed/rss.xml", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "RSS 訂閱", "on_failure": "—", "test": "—"},
      {"id": "pub_archive", "layer": "publish", "name": "歷史簡報索引（120 天）", "url": base + "feed/index.json → " + base + "feed/YYYY-MM-DD.{json,md}", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "事後驗證", "on_failure": "—", "test": "—"},
      {"id": "pub_meta", "layer": "publish", "name": "Muse 知識包（README、01…09、prompts、data）", "url": base + "meta/", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "agent 第一次吸收：06_rules_for_agents.md、05_glossary.md；每天：01、09、08、02", "on_failure": "—", "test": f"curl -s {base}meta/09_market_dashboard.md | head -12"},
      {"id": "pub_full_json", "layer": "publish", "name": "完整分析 JSON（~600 KB，含 dashboard / newsflash / backtest）", "url": base + "soxl_analysis_data.json", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "需要全部欄位時", "on_failure": "—", "test": "—"},
      {"id": "pub_html", "layer": "publish", "name": "人看的頁面", "url": base + "soxl_simple.html（新手版）, " + base + "soxl_analysis_report.html（完整版 = index.html）", "method": "GET", "auth": "none", "ttl_sec": 0, "used_by": "人", "on_failure": "—", "test": "—"},
      # ---- delivery (optional: the repo pushes INTO the agent)
      {"id": "dl_webhook", "layer": "delivery", "name": "通用 HTTPS webhook（Muse 的 inbox）", "url": "你提供的 https://… 端點", "method": "POST application/json", "auth": "可選 Authorization: Bearer <token>；可選 HMAC-SHA256 簽章 X-SOXL-Signature: sha256=<hex of body>", "ttl_sec": 0,
       "used_by": "auto_update.py run / push（本機排程；雲端 Actions 需設 repo secret SOXL_NOTIFY_CONFIG_JSON）", "on_failure": "push 結果寫進 logs/auto_update.log 與 get_status()", "test": ".venv/bin/python auto_update.py push-test --only webhook"},
      {"id": "dl_chat", "layer": "delivery", "name": "Google Chat / Slack / Discord incoming webhook、Telegram Bot、LINE Messaging、Email (SMTP)", "url": "各平台 webhook / API", "method": "POST", "auth": "各平台 token（放環境變數，設定檔用 $ENV:NAME）", "ttl_sec": 0, "used_by": "同上", "on_failure": "同上", "test": ".venv/bin/python auto_update.py push-test"},
      {"id": "dl_agentapi", "layer": "delivery", "name": "Antigravity agentapi（在 agent 環境內開新對話 / 傳訊息）", "url": "agentapi new-conversation / send-message", "method": "CLI", "auth": "需 ANTIGRAVITY_LS_ADDRESS（只在 agent 環境內）", "ttl_sec": 0, "used_by": "sidecar 07:50 每日對話", "on_failure": "—", "test": ".venv/bin/python auto_update.py sidecar-install"},
      # ---- local tooling
      {"id": "mcp_server", "layer": "local", "name": "MCP server soxl_mcp.py（stdio）", "url": "tools: get_brief, get_latest(section=dashboard|newsflash|…), get_quotes, get_news(live=true), get_events, get_history, get_status, refresh", "method": "MCP/stdio", "auth": "none", "ttl_sec": 0, "used_by": "任何 MCP host（Antigravity / Gemini CLI / Claude / Cursor）", "on_failure": "—", "test": ".venv/bin/python tools/test_mcp.py"},
      {"id": "gh_actions", "layer": "github", "name": "GitHub Actions：daily-update.yml（雲端重算）與 deploy.yml（Pages 部署）", "url": REPO_HTTPS + "/actions", "method": "cron + workflow_dispatch", "auth": "GITHUB_TOKEN（workflow 內建；permissions: contents: write / pages: write）", "ttl_sec": 0, "used_by": "每日 06:15 / 07:00 / 08:30 台北", "on_failure": "Actions 頁紅叉；Pages 的 data_as_of 不前進", "test": "gh run list --repo Corleonis6422/stock-dashboard --limit 5"},
  ]


# --------------------------------------------------------------------------- #
# runbook (machine-readable) + README (operator spec)
# --------------------------------------------------------------------------- #
def runbook(f: dict) -> dict:
  base = f["github"]["pages_base_url"]
  zipname = f.get("repo_zip") or "stock-dashboard_repo_<date>.zip"
  head = f["git"]["head"]
  check_fresh = ("python3 - <<'PY'\nimport json,urllib.request\nm=json.load(urllib.request.urlopen('" + base + "meta/manifest.json'))\nprint('data_as_of', m['data_as_of'], 'verdict', m['verdict'], 'plan', m['plan_side'])\nPY")
  return {
      "pack": f["pack"], "built_at": f["built_at"], "facts": f,
      "capability_routes": {
          "A_shell_git_github_write": "執行 steps_A 全部",
          "B_browser_only": "把 steps_A 的指令原文交給有終端機的人或 agent；自己只做 steps_C（消費端）",
          "C_consume_only": "steps_C",
      },
      "steps_A": [
          {"id": "A1", "title": "解壓並確認 HEAD", "run": f"unzip -q {zipname} && cd stock-dashboard && git log --oneline -n 1", "expect": f"{head} {f['git']['head_subject']}", "on_fail": "zip 損毀或解錯層；重新解壓，確認目錄內有 .git/"},
          {"id": "A2", "title": "確認遠端", "run": "git remote -v", "expect": f"origin {f['git']['remote']} (fetch/push)", "on_fail": f"git remote add origin {REPO_SSH}"},
          {"id": "A3", "title": "確認 GitHub 寫入權（SSH）", "run": "ssh -T git@github.com", "expect": "Hi Corleonis6422! You've successfully authenticated（exit code 1 是正常的）", "on_fail": "沒有 SSH 金鑰 → 走 A3b（HTTPS + PAT）或把 ~/.ssh/id_ed25519.pub 加到 GitHub → Settings → SSH and GPG keys"},
          {"id": "A3b", "title": "（替代）HTTPS + Personal Access Token，或 GitHub CLI", "run": f"git remote set-url origin {REPO_HTTPS}.git && git config credential.helper store   # 或：gh auth login && gh auth setup-git", "expect": "下一步 push 時輸入帳號 Corleonis6422 與 PAT（fine-grained：只給此 repo、Contents: Read and write）；credential.helper store 會把 PAT 明文存在 ~/.git-credentials，推完可刪", "on_fail": "PAT 權限不足 → 403；重新建立 token"},
          {"id": "A4", "title": "確認與遠端的關係", "run": "git fetch origin main && git merge-base HEAD origin/main; echo exit=$?", "expect": "exit=0 表示有共同祖先，走 rebase 路線（A5）；exit=1 表示無共同祖先，停下來人工處理，絕不覆蓋推送", "on_fail": "fetch 失敗 = 認證問題，回 A3"},
          {"id": "A5", "title": "推送（先 rebase 再正常推送，絕不覆蓋）", "run": "git fetch origin main && git rebase origin/main && git push origin main", "expect": "main -> main（正常快轉或 rebase 後推送）；被拒絕時停下來人工解衝突", "on_fail": "Permission denied → A3；rejected → 停下來解衝突後再推，絕不覆蓋推送；protected branch → 走 PR 流程"},
          {"id": "A6", "title": "驗證遠端 HEAD = 本機 HEAD", "run": "git ls-remote origin refs/heads/main && git rev-parse HEAD", "expect": "兩個 hash 相同", "on_fail": "重做 A5"},
          {"id": "A7", "title": "GitHub 設定：Pages 來源 = GitHub Actions", "run": f"open {REPO_HTTPS}/settings/pages  （或 gh api repos/Corleonis6422/stock-dashboard/pages）", "expect": "Build and deployment → Source: GitHub Actions", "on_fail": "改成 GitHub Actions 後存檔；第一次 push 後 deploy.yml 會自動跑"},
          {"id": "A8", "title": "GitHub 設定：Actions 允許執行、workflow 可寫", "run": f"open {REPO_HTTPS}/settings/actions", "expect": "Actions permissions: Allow all actions；Workflow permissions: Read and write permissions", "on_fail": "沒有 Read and write 時 daily-update.yml 的 git push 會 403"},
          {"id": "A9", "title": "等 Pages 部署（push 後 1–3 分鐘）並驗證端點", "run": check_fresh, "expect": f"data_as_of {f.get('data_as_of')}（= 本機資料日）", "on_fail": f"404 → 看 {REPO_HTTPS}/actions 的 Deploy to GitHub Pages 是否紅叉；通常是 A7 沒設"},
          {"id": "A10", "title": "（建議）手動觸發一次雲端更新，驗證端到端", "run": "gh workflow run daily-update.yml --repo Corleonis6422/stock-dashboard -f force=true && sleep 240 && gh run list --repo Corleonis6422/stock-dashboard --limit 3", "expect": "Daily update (cloud fallback) 成功；repo 多一個 commit「data: <date> … [github-actions]」；Pages 的 generated_at 變新", "on_fail": "看 run log：上游 API 失敗會列在 warnings；push 403 回 A8"},
          {"id": "A11", "title": "（可選）讓雲端也推播給 agent", "run": "gh secret set SOXL_NOTIFY_CONFIG_JSON --repo Corleonis6422/stock-dashboard < notify_config.json", "expect": "下一次 daily-update 的 run log 出現「delivery: enabled from secret」，簡報 POST 到 notify_config.json 裡啟用的 webhook / chat 頻道", "on_fail": "secret 內容必須是完整 JSON（先 .venv/bin/python auto_update.py notify-config 產生範本，填入實際 url / token，不要用 $ENV:，並把 macos 頻道 enabled 設 false）；無效 JSON 時 run log 會有 warning 並跳過推播"},
      ],
      "steps_C": [
          {"id": "C1", "title": "每個美股交易日台北 07:30 抓 manifest", "run": check_fresh, "expect": "data_as_of = 最近一個已收盤的美股交易日（美東 16:00 後約 75 分鐘換日；週末、NYSE 假日順延）", "on_fail": "09:00 再抓一次；仍舊 → 回報「網址今天沒更新，資料日是 X」"},
          {"id": "C2", "title": "讀簡報", "run": f"GET {base}feed/latest.json（或 {base}meta/01_brief_today.md）", "expect": "beginner.buy.answer、dashboard.one_liner、trade_plan、flash.beginner_line、events.upcoming", "on_fail": "改讀 meta/01_brief_today.md"},
          {"id": "C3", "title": "發日報（固定格式）", "run": "見 README 第 5 節 / meta/prompts/first_time.md", "expect": "三句話 + 六個儀表一行 + 48 小時風險一行 + 免責", "on_fail": "—"},
          {"id": "C4", "title": "只在這些情況多寫", "run": "changes.verdict_changed / crash_risk.score 跨 60 或 80 / trade_plan.side 變 long 或 long_pending / 48h 內 FOMC 或龍頭財報 / warnings 非空 / flash.flags 任一 true", "expect": "—", "on_fail": "—"},
      ],
      "acceptance": [
          {"id": "V1", "check": f"GET {base}meta/manifest.json → 200 且 data_as_of = 最近交易日"},
          {"id": "V2", "check": f"GET {base}feed/latest.json → schema = soxl-quant-brief/2，含 beginner、dashboard、flash、trade_plan"},
          {"id": "V3", "check": f"{REPO_HTTPS}/actions：Deploy to GitHub Pages 綠勾；隔天 07:00 後 Daily update (cloud fallback) 有執行紀錄"},
          {"id": "V4", "check": "隔天 07:30 agent 抓到的 data_as_of 比前一天前進一個交易日"},
          {"id": "V5", "check": "（若設了 webhook）auto_update.py push-test 後 inbox 收到 event=soxl.test 的 JSON"},
      ],
  }


def readme(f: dict, api_rows: list[dict], rb: dict) -> str:
  base = f["github"]["pages_base_url"]
  g = f["git"]
  zipname = f.get("repo_zip") or "stock-dashboard_repo_<date>.zip"
  mb = (f.get("repo_zip_bytes") or 0) / 1024 / 1024

  def steps_md(steps: list[dict]) -> str:
    out = ""
    for s in steps:
      out += f"**{s['id']}. {s['title']}**\n\n```bash\n{s['run']}\n```\n\n- 期望：{s['expect']}\n- 失敗時：{s['on_fail']}\n\n"
    return out

  up = [a for a in api_rows if a["layer"] == "upstream"]
  pub = [a for a in api_rows if a["layer"] == "publish"]
  dl = [a for a in api_rows if a["layer"] in ("delivery", "local", "github")]

  def api_table(rows: list[dict], cols=("name", "url", "used_by", "on_failure"), heads=("端點", "URL / 位置", "誰在用", "失敗時")) -> str:
    out = "| " + " | ".join(heads) + " |\n|" + "---|" * len(heads) + "\n"
    for a in rows:
      cells = [str(a.get(c, "")).replace("|", "／") for c in cols]
      out += "| " + " | ".join(cells) + " |\n"
    return out

  return f"""# SOXL Quant · Agent Operator Pack（給 Muse / 任何能執行指令的 AI agent）

> 你是這個 repo 的「上線 + 串接」操作員。目標只有三個，照順序做，每一步都有可驗證的完成條件：
> （1）把這包 repo 推上 GitHub，一次就好，之後全自動；（2）確認 GitHub Actions 與 Pages 把公開端點發出來並每天更新；（3）把資料接進你自己：每天抓、驗新鮮度、發日報；可選：讓 repo 主動推給你。
> 讀法：先讀第 0 節的事實與第 1 節的能力判斷，再執行對應路徑。每個步驟 = 指令 + 期望輸出 + 失敗分支；做不到的步驟不要猜，照「失敗時」的指示處理或交給人類。
> 機器可讀版在 `RUNBOOK.json`；API 清單在 `apis.json` / `APIS.md`。

## 0. 事實（measured，打包當下 {f['built_at']} 台北）

| 項目 | 值 |
|---|---|
| 這包 | `{f['pack']}`；內含 `{zipname}`（{mb:.1f} MB，含 `.git` 歷史）、`meta/`（每日知識包）、本 README、`RUNBOOK.json`、`apis.json` |
| 本機 HEAD | `{g['head']}` {g['head_subject']}（{g['branch']}，共 {g['commits']} 個 commit） |
| 資料日 | `{f.get('data_as_of')}`（產生 {f.get('generated_at')} 台北）· 評級 {f.get('verdict')} · 計畫 `{f.get('plan_side')}` · schema `{f.get('schema')}` |
| 遠端 | `{g['remote']}`（HTTPS：`{REPO_HTTPS}`） |
| 遠端歷史 | 以 `git merge-base HEAD origin/main` 判斷：有共同祖先就先 rebase 再正常推送；無共同祖先就停下來人工處理，絕不覆蓋推送 |
| 推送為什麼還沒發生 | 產生這包的 Mac 沒有 GitHub 寫入權（`Permission denied (publickey)`），本機排程每天重算但推不上去 |
| 你需要的唯一權限 | GitHub 帳號 `Corleonis6422` 對 repo `stock-dashboard` 的寫入權（SSH key 或 fine-grained PAT）。沒有 → 停在第 2 節，把指令交給人 |
| 需要設定的 secret | **零**。所有上游 API 都免金鑰。唯一可選的 secret 是「推送給你」的 webhook token（第 4.3 節） |
| 發佈網址 | `{base}`（GitHub Pages；push 後 1–3 分鐘上線） |
| 更新節奏 | GitHub Actions 台北 06:15（UTC 22:15）、07:00、08:30 重試，只在 `data_as_of` 落後時真的跑；Mac launchd 07:30 另外算一次；你 07:30 抓、不新 09:00 再抓 |

## 1. 判斷你的能力，選路徑

| 你有什麼 | 走哪條 |
|---|---|
| shell + git + GitHub 寫入權 | **路徑 A**（第 2 節，約 10 分鐘）→ 第 3 節驗證 → 第 5 節每日迴圈 |
| 只有瀏覽器 / HTTPS，沒有 shell | 把第 2 節的指令原文交給有終端機的人或 agent（不要用 GitHub 網頁逐檔上傳，`.git` 歷史會丟）；自己做第 5 節 |
| 什麼都沒有（只能讀網址） | 第 5 節消費端；Pages 上線前你讀到的會是 404，請回報人類 |

## 2. 路徑 A：推上 GitHub（一次性）

前置：`git --version` ≥ 2.30；`unzip`；可選 `gh`（GitHub CLI，讓 A7–A11 不用開瀏覽器）。

{steps_md(rb['steps_A'])}
## 3. 推完之後會自動發生的事（不用你做）

| 時間（台北） | 誰 | 做什麼 |
|---|---|---|
| push 後 1–3 分鐘 | Actions `deploy.yml` | 把整個 repo 發佈到 GitHub Pages（`{base}`） |
| 06:15（UTC 22:15，週二～六） | Actions `daily-update.yml` | 檢查 repo 內 `data_as_of` 是否落後最近交易日；落後就抓 {len(up)} 個上游 API、重算、產生 HTML / `feed/` / `meta/`，commit「data: <date> … [github-actions]」並 push → 觸發 deploy |
| 07:00、08:30 | Actions | 同上，只在前一次沒成功時真的跑（已是最新就幾秒內結束） |
| 07:30 | 產生這包的 Mac | 本機也重算（給本機 HTML、通知、MCP 用）；push 會失敗但不影響網址 |

驗收清單（第 6 節）全部打勾才算「上線」。

## 4. API 全圖（三層）

### 4.1 上游資料 API：pipeline 自己呼叫，你不需要設定任何東西

全部免金鑰、全部有快取（`.cache/`，TTL 見 `apis.json`）、任一失敗只降級該區段並寫進 `warnings[]`，不會中斷（Nasdaq 日線除外，它是核心價格來源）。你唯一要做的是：看到 `warnings` 非空時，在日報裡說「某來源今天失敗，該區段是降級值」。

{api_table(up)}
### 4.2 發佈端點：你每天要抓的（全部 GET、免驗證、同一組網址每天換內容）

{api_table(pub, ("name", "url", "used_by", "on_failure"), ("端點", "URL", "你用來做什麼", "失敗時"))}
讀取順序：`meta/manifest.json`（看 `data_as_of`）→ `feed/latest.json`（或 `meta/01_brief_today.md`）→ 需要時 `meta/09_market_dashboard.md`（六個儀表）、`meta/08_today_news.md`（時事）、`meta/02_trade_plan.md`。

`feed/latest.json` 裡你最常用的路徑：

| 問題 | JSON 路徑 |
|---|---|
| 新手該不該買 | `beginner.buy.answer`、`beginner.buy.text`、`beginner.watch.price` |
| 今天最大的事 | `beginner.biggest_thing`（= `flash.beginner_line`）；來源 `flash.top[0].publisher` / `.link` |
| 能不能加碼 / 宏觀 / 費半 / 大戶 / Put-Call / 崩跌 | `dashboard.gauges[]`（固定順序 add_on, macro, soxx, whales, put_call, crash；每格 `short`、`light`、`meaning`、`fields`、`caveat`）、一行版 `dashboard.one_liner` |
| 進出場 | `trade_plan.side`、`.entry.price`、`.stop.price`、`.t1.price`、`.t2.price`、`.rr_blend`、`.size.pct` |
| 勝率（一定連同基準與 N） | `signals[].win_pct`、`.base_win_pct`、`.n`、`.p_value`、`.significant` |
| 48 小時風險 | `events.upcoming[]`（`days_ahead` ≤ 2）、`flash.cautions[]`、`beginner.risk_48h[]` |
| 新鮮度 | `data_as_of`、`data_status.provisional`、`warnings[]` |

### 4.3 推送進你（可選；repo → 你）

| 通道 | 怎麼接 | 誰會送 |
|---|---|---|
| 通用 HTTPS webhook | 在 `notify_config.json`（`auto_update.py notify-config` 產生範本）啟用 `type: webhook`，填你的 `url`，可選 `bearer_token`（`$ENV:MUSE_TOKEN`）與 `hmac_secret`；`format` = `json`（完整信封含 `brief`）/ `slim` / `text`。測試：`auto_update.py push-test --only webhook` | 本機 07:30 排程；雲端 Actions 只在設了 repo secret `SOXL_NOTIFY_CONFIG_JSON`（內容 = 整份 notify_config.json，用實際 token）後才會送（A11） |
| Google Chat / Slack / Discord / Telegram / LINE / Email | 同一個設定檔，各填 webhook / token | 同上 |
| MCP（你是 MCP host 時） | `auto_update.py mcp-install` 把 `soxl_mcp.py` 寫進 host 設定；工具：`get_brief`、`get_latest(section=dashboard)`、`get_news(live=true)`、`get_quotes`、`get_events`、`get_history`、`get_status`、`refresh` | 你自己呼叫 |
| Antigravity sidecar | `auto_update.py sidecar-install`：每個交易日 07:50 自動開一個「SOXL 每日簡報」對話 | agent 環境內 |

Webhook 信封（`event` = `soxl.daily_brief` / `soxl.update_failed` / `soxl.test`）：

```json
{{"event": "soxl.daily_brief", "schema": "{f.get('schema')}", "sent_at": "YYYY-MM-DDTHH:MM:SS",
 "title": "SOXL YYYY-MM-DD 🔴 賣出 / 減碼｜$83.56（+1.77%）", "text": "…≤ 900 字…", "markdown": "…feed/latest.md 全文…",
 "summary": {{"data_as_of": "…", "verdict": "…", "emoji": "…", "composite": -0.82, "size_pct": 10, "close": 83.56, "ret_1d": 1.77}},
 "links": {{"report_html": "…", "simple_html": "…", "brief_json": "…", "rss": "…"}}, "brief": {{ "…feed/latest.json 全文（format=json 時）…": 1 }}}}
```

驗簽：`hex(HMAC_SHA256(hmac_secret, raw_body)) == X-SOXL-Signature` 去掉 `sha256=` 前綴。

{api_table(dl, ("name", "url", "auth", "test"), ("工具 / 通道", "位置", "驗證", "測試"))}
## 5. 你的每日迴圈（消費端 SOP）

1. 每個美股交易日（週二～六）台北 07:30：`GET {base}meta/manifest.json`，讀 `data_as_of`。
2. 新鮮度規則：`data_as_of` 必須等於最近一個已收盤的美股交易日（美東 16:00 收盤後約 75 分鐘換日；週末與 NYSE 假日順延）。不新 → 09:00 再抓；還是舊的 → 只回報「網址今天沒更新，資料日是 X」，不要發舊結論當新結論。
3. 新鮮就 `GET {base}feed/latest.json`，發固定格式日報：
   - 句 1：該買、該賣還是觀望 → 先講 `beginner.buy.answer`，再轉述 `trade_plan`（side、進場觸發、停損、T1、T2、加權風報比；`no_trade` 就說「今天不開新倉，觸發價是 X」）。
   - 句 2：最重要的一個理由 + 「今天最大的事」（`beginner.biggest_thing`，說明那是依標題分類的結果，附 publisher）。
   - 句 3：要盯的三個價位：停損、T1、期權牆或 Gamma 翻正位。
   - 倒數第二行：`dashboard.one_liner`（能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數六個燈號）。
   - 最後一行：48 小時內風險事件（`events.upcoming` 內 `days_ahead` ≤ 2 與 `flash.cautions`，沒有就寫「無」）+ `disclaimer`。
4. 只在這些情況多寫：`changes.verdict_changed`、`crash_risk.score` 跨過 60 / 80、`trade_plan.side` 變成 `long` / `long_pending`、48 小時內 FOMC 或龍頭財報、`warnings` 非空、`flash.flags` 任一為 true。
5. 引用規則：勝率一定帶基準與 N（`significant=false` 不可說「高勝率」）；賣出訊號沒有預測力，停損才是出場；期權牆是模型值；兩種 200 日線讀法不一致時兩個都講；大戶方向是 CBOE 大額權利金推估，不是 13F；時事與 Seeking Alpha 標題的方向是關鍵字規則，不是 LLM 判讀。
6. 被問「能不能加碼」只念 `dashboard.gauges[0]`（add_on）：燈號、`meaning`、停損與減碼點。
7. 完整規則見 `meta/06_rules_for_agents.md`（11 條），第一次吸收時連同 `meta/05_glossary.md` 讀一次。

## 6. 驗收清單

{chr(10).join(f"- [ ] **{v['id']}** {v['check']}" for v in rb['acceptance'])}

## 7. 故障排除

| 症狀 | 原因 | 處置 |
|---|---|---|
| `git push` → `Permission denied (publickey)` | 這台機器的 SSH key 沒在 GitHub 帳號 | A3：加 key，或 A3b 改 HTTPS + PAT |
| `git push` → `! [rejected] … (fetch first)` | 遠端已有新 commit，本機落後 | `git fetch origin main && git rebase origin/main`，解衝突後再 `git push origin main`；絕不覆蓋推送 |
| `git push` → 403 / protected branch | PAT 沒有 Contents write，或 main 受保護 | 重建 PAT；Settings → Branches 解除保護 |
| Pages 網址 404 | Pages 來源不是 GitHub Actions，或 deploy 還沒跑完 | A7；看 Actions 的 Deploy to GitHub Pages |
| Actions `daily-update` push 403 | Workflow permissions 是 Read-only | A8：改 Read and write |
| `data_as_of` 不前進 | 三次 cron 都還沒到、或上游 API 失敗 | 看 Actions run log 的 `warnings`；手動 `gh workflow run daily-update.yml -f force=true` |
| `warnings` 非空 | 某個上游來源當天失敗 | 日報裡標「降級」；通常隔天自癒；持續 3 天以上才需要改 `soxl_quant/datafeed.py` |
| `flash` / `dashboard` 為 null | newsflash / dashboard 步驟例外 | `warnings` 會寫原因；簡報其餘區段照常 |
| webhook 沒收到 | 本機沒跑 / 設定檔沒啟用 / 雲端沒設 secret | `auto_update.py push-status`；`push-test --only webhook`；A11 |

## 8. 安全邊界

- repo 裡沒有任何 secret；`notify_config.json` 在 `.gitignore`，zip 也排除它。token 一律用環境變數（設定檔寫 `$ENV:NAME`）或 GitHub Secrets。
- 上游 API 全部是公開端點，有速率節流（Yahoo 2.2 秒、Nasdaq 0.9 秒、Seeking Alpha 1 秒一次）；不要繞過 `datafeed.safe_https_get` 的主機白名單。
- 這是自動計算的研究參考，不是投資建議；每一則輸出都附 `disclaimer`。

---

## English operator brief

You are the operator for this repo. Three goals in order, each with a verifiable done-state:

1. **Publish once.** Unzip `{zipname}`, `cd stock-dashboard`, confirm `git log -1` shows `{g['head']}`, confirm `git remote -v` is `{g['remote']}`, authenticate (SSH key on the GitHub account `Corleonis6422`, or HTTPS with a fine-grained PAT that has Contents: read/write), then `git fetch origin main && git rebase origin/main && git push origin main` (if the push is rejected, stop and resolve the conflict manually; never overwrite the remote branch). Verify `git ls-remote origin refs/heads/main` equals `git rev-parse HEAD`. In GitHub settings: Pages → Source = GitHub Actions; Actions → Workflow permissions = Read and write. Wait 1–3 minutes and verify `GET {base}meta/manifest.json` returns `data_as_of = {f.get('data_as_of')}`. Optionally `gh workflow run daily-update.yml -f force=true` to prove the cloud path end to end.
2. **Wire the APIs.** Nothing to configure upstream: all {len(up)} data sources are keyless and cached; failures degrade one section and appear in `warnings[]`. Published endpoints you consume: `meta/manifest.json` (freshness), `feed/latest.json` (schema soxl-quant-brief/2: `beginner`, `dashboard`, `trade_plan`, `flash`, `events`), `feed/latest.md`, `meta/*.md`. Optional push into you: enable a `webhook` channel in `notify_config.json` (bearer token and HMAC-SHA256 `X-SOXL-Signature` supported); for cloud pushes add the file content as the repo secret `SOXL_NOTIFY_CONFIG_JSON`. MCP server `soxl_mcp.py` exposes `get_brief`, `get_latest(section=dashboard)`, `get_news(live=true)`, `get_quotes`, `get_events`, `get_history`, `get_status`, `refresh`.
3. **Daily loop.** Each US trading day at 07:30 Taipei fetch the manifest; `data_as_of` must equal the last completed US session (else retry 09:00, then report stale). Then fetch `feed/latest.json` and send the fixed-format brief: (1) buy / sell / wait, leading with `beginner.buy.answer` then the trade plan; (2) the single most important reason plus `beginner.biggest_thing` (keyword-classified headline, cite publisher); (3) the three prices to watch; then `dashboard.one_liner` (six gauge lights); then the 48-hour risk line and the disclaimer. Every win rate comes with its base rate and N; sell signals have no edge; option walls are model values; whale direction is inferred from CBOE large prints, not 13F. Full rules: `meta/06_rules_for_agents.md`.

Not investment advice.
"""


def apis_md(f: dict, rows: list[dict]) -> str:
  out = f"# APIs — 全部端點（打包時 {f['built_at']} 台北，資料日 {f.get('data_as_of')}）\n\n"
  out += "三層：`upstream`（pipeline 呼叫的資料來源，全部免金鑰）、`publish`（你每天抓的公開網址）、`delivery` / `local` / `github`（推送進 agent、MCP、Actions）。機器可讀版 `apis.json`。\n\n"
  for layer, title in (("upstream", "上游資料 API"), ("publish", "發佈端點"), ("delivery", "推送通道"), ("local", "本機工具"), ("github", "GitHub")):
    rs = [r for r in rows if r["layer"] == layer]
    if not rs:
      continue
    out += f"## {title}\n\n"
    for r in rs:
      out += f"### `{r['id']}` {r['name']}\n\n- URL：`{r['url']}`\n- 方法 / 驗證：{r['method']} / {r['auth']}\n- 快取 TTL：{r['ttl_sec']} 秒\n- 誰在用：{r['used_by']}\n- 失敗時：{r['on_failure']}\n- 測試：`{r['test']}`\n\n"
  return out


def build_docs(br: dict | None, base_url: str | None = None, repo_zip: Path | None = None) -> dict[str, str]:
  f = facts(br, base_url, repo_zip)
  rows = apis(f["github"]["pages_base_url"])
  rb = runbook(f)
  return {
      "README.md": readme(f, rows, rb),
      "APIS.md": apis_md(f, rows),
      "apis.json": json.dumps({"pack": f["pack"], "built_at": f["built_at"], "base_url": f["github"]["pages_base_url"], "apis": rows}, ensure_ascii=False, indent=1) + "\n",
      "RUNBOOK.json": json.dumps(rb, ensure_ascii=False, indent=1) + "\n",
  }
