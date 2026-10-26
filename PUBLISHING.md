# 發佈到 GitHub：從另一台電腦推送一次，之後全自動

這台 Mac 沒有 GitHub 的 SSH 權限（`git@github.com: Permission denied (publickey)`），所以本機排程每天會重算，但推不上去。
解法是把整個 repo（含 `.git` 歷史）帶到有權限的電腦推送一次；之後 GitHub Actions 會自己每天重算並更新 GitHub Pages，不需要任何一台電腦開機。

## 1. 在這台 Mac 打包

```bash
cd ~/Documents/folder
.venv/bin/python auto_update.py pack-agent       # 給 AI agent（Muse）的操作包 ~/Downloads/soxl_agent_pack_<日期>.zip：
                                                 #   README.md（操作員規格：事實、步驟 + 期望輸出 + 失敗分支、API 三層、每日迴圈、驗收、故障排除）
                                                 #   RUNBOOK.json / APIS.md / apis.json、meta/（每日知識包）、stock-dashboard_repo_<日期>.zip（含 .git）
.venv/bin/python auto_update.py pack-repo        # 只要 repo 壓縮檔：~/Downloads/stock-dashboard_repo_<日期>.zip（含 .git，不含 .venv / .cache / logs / 任何 secrets）
```

把 `soxl_agent_pack_<日期>.zip` 交給 agent，說「照 README.md 做：先推上 GitHub，再照第 5 節每天抓」。README 用 agent 聽得懂的方式寫：每一步都有指令、期望輸出與失敗時的處置；`RUNBOOK.json` 是同一份步驟的機器可讀版。

## 2. 在另一台電腦

```bash
unzip stock-dashboard_repo_*.zip && cd stock-dashboard
git log --oneline -n 3                            # 應看到最新的 commit
git remote -v                                     # origin = git@github.com:Corleonis6422/stock-dashboard.git
git fetch origin main && git rebase origin/main && git push origin main   # 有共同祖先時走 rebase 再正常推送；被拒絕就停下來解衝突，絕不覆蓋推送
```

沒有 SSH 金鑰的電腦改用 HTTPS（會跳 GitHub 登入或要 Personal Access Token，需有 repo 寫入權限）：

```bash
git remote set-url origin https://github.com/Corleonis6422/stock-dashboard.git
git fetch origin main && git rebase origin/main && git push origin main
```

## 3. 推完之後會自動發生的事

| 時間（台北） | 誰 | 做什麼 |
|---|---|---|
| 06:15（UTC 22:15，週二～六） | GitHub Actions `daily-update.yml` | 檢查 repo 內 `data_as_of` 是否落後最近交易日；落後就抓資料、重算、產生 HTML / `feed/` / `meta/`，commit 並 push |
| 07:00、08:30 | GitHub Actions | 同上，只在前一次沒成功時真的跑（已是最新就幾秒內結束） |
| push 後 1～2 分鐘 | GitHub Actions `deploy.yml` | 把整個 repo 發佈到 GitHub Pages |
| 07:30 | 這台 Mac 的 launchd | 本機也重算一次給本機 HTML 與通知用；推送會失敗但不影響網址 |

公開網址（同一組，每天換內容）：

- `https://corleonis6422.github.io/stock-dashboard/meta/01_brief_today.md`
- `https://corleonis6422.github.io/stock-dashboard/meta/02_trade_plan.md`
- `https://corleonis6422.github.io/stock-dashboard/meta/data/latest.json`
- `https://corleonis6422.github.io/stock-dashboard/meta/manifest.json`（看 `data_as_of` 就知道新不新）

## 4. 推完怎麼確認

1. GitHub → repo → Actions：`Deploy to GitHub Pages` 綠勾。
2. 開 `https://corleonis6422.github.io/stock-dashboard/meta/manifest.json`，`data_as_of` 應等於 push 時本機的資料日。
3. 隔天台北 07:00 後再開一次，`data_as_of` 應變成最新交易日；Actions 頁面會多一次 `Daily update (cloud fallback)` 的執行紀錄。
4. 第一次可以手動觸發：Actions → `Daily update (cloud fallback)` → Run workflow → force = true。

## 4b. 讓雲端也推播給 agent（可選）

GitHub Actions 的更新預設不推播（runner 上沒有你的 token）。要讓雲端每天把簡報 POST 到 Muse 的 webhook / Telegram / Slack 等：

```bash
.venv/bin/python auto_update.py notify-config                       # 產生 notify_config.json 範本
# 編輯：要用的頻道 enabled=true，填實際 url / token（不要用 $ENV:，runner 沒有那些環境變數），macos 頻道 enabled=false
gh secret set SOXL_NOTIFY_CONFIG_JSON --repo Corleonis6422/stock-dashboard < notify_config.json
```

`daily-update.yml` 看到這個 secret 就會把它寫成 `notify_config.json`（0600、不 commit）並以通知開啟的模式執行；run log 會印「delivery: enabled from secret」。本機 `notify.py` 讀的環境變數 `SOXL_NOTIFY_CONFIG` 是「設定檔路徑」，所以 secret 名稱刻意用 `_JSON` 結尾。

## 5. 讓 Muse 每天來撈

`meta/prompts/first_time.md` 的 prompt 已經要求 Muse 每個交易日台北 07:30 抓上面的網址、確認 `data_as_of`、不新就 09:00 再抓，然後發三句話日報。Pages 一上線就會生效，不用再改 prompt。

## 6. 之後若想讓這台 Mac 也能推

把 `~/.ssh/id_ed25519.pub` 加到 GitHub → Settings → SSH and GPG keys。之後 `auto_update.py run` 會在每天 07:30 自己 commit 並 push（推送前會 fetch + rebase，與 Actions 的 commit 不會互相覆蓋）。
