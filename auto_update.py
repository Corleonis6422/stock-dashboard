#!/usr/bin/env python3
"""SOXL Quant — 每日自動更新 (runner + macOS 排程 + 推播 + 發佈 CLI)。

排程 / 更新
    .venv/bin/python auto_update.py install        安裝 launchd 排程（預設週二～六 07:30 = 美股收盤後）
    .venv/bin/python auto_update.py status         查看排程狀態 / 上次結果 / 下次時間 / 推播與發佈結果
    .venv/bin/python auto_update.py run            立刻更新一次（抓 API → 評分 → HTML → feed → 推播 → git push）
    .venv/bin/python auto_update.py run --if-stale 只在資料落後最近美股交易日時更新（排程用）
    .venv/bin/python auto_update.py uninstall      移除排程
    .venv/bin/python auto_update.py config         顯示（必要時建立）auto_update_config.json

給 Agent / Muse 用
    .venv/bin/python auto_update.py brief          印出最新一頁式簡報（Markdown）；--json / --text 換格式
    .venv/bin/python auto_update.py feed           不重算模型，用既有 JSON 重建 feed/（含最新事件與報價）
    .venv/bin/python auto_update.py meta           用既有 feed/latest.json 重建 meta/（Muse / AI agent 的 Markdown 吸收包）
    .venv/bin/python auto_update.py pack-repo      把整個 repo（含 .git）壓成 zip，帶去有 GitHub 權限的電腦 push（見 PUBLISHING.md）
    .venv/bin/python auto_update.py pack-agent     給 AI agent（Muse）的操作包：README 操作員規格 + RUNBOOK.json + apis.json + meta/ + repo zip（推送、串 API、每日抓取）
    .venv/bin/python auto_update.py quotes         即時報價快照（SOXL / 成分股 / VIX 複合體）；--json
    .venv/bin/python auto_update.py mcp-config     印出 MCP server 設定片段（Antigravity / Gemini CLI / Claude）
    .venv/bin/python auto_update.py mcp-install    把 MCP server 寫進 ~/.gemini/config/mcp_config.json（自動備份）
    .venv/bin/python auto_update.py sidecar-install  Antigravity sidecar：每個交易日早上自動開一個 agent 對話讀簡報並回報（--time 07:50）
    .venv/bin/python auto_update.py sidecar-uninstall

推播 / 發佈
    .venv/bin/python auto_update.py notify-config  建立 notify_config.json（從範本，chmod 600）
    .venv/bin/python auto_update.py push           把最新簡報再推一次到所有啟用頻道；--only webhook,telegram
    .venv/bin/python auto_update.py push-test      對所有啟用頻道送測試訊息
    .venv/bin/python auto_update.py push-status    顯示推播設定（金鑰遮罩）
    .venv/bin/python auto_update.py publish        立刻 git commit + push 輸出檔（→ GitHub Pages）
    .venv/bin/python auto_update.py notify-test    測試 macOS 通知

每次成功更新都會：重新抓取所有 API → 重算評分 → 寫出 soxl_analysis_data.json /
soxl_analysis_report.html (= index.html) / soxl_simple.html → feed/latest.{json,md,txt} + rss.xml
→ 追加 history/verdicts.jsonl → logs/last_run.json → 推播（macOS + notify_config.json 頻道）→ git push。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import logging.handlers
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from soxl_quant import brief as briefmod  # noqa: E402
from soxl_quant import notify as notifymod  # noqa: E402
from soxl_quant import publish as publishmod  # noqa: E402
from soxl_quant import scheduler  # noqa: E402

LOCK_PATH = scheduler.LOG_DIR / ".auto_update.lock"
LOCK_STALE_SEC = 3 * 3600
SIMPLE_HTML = BASE_DIR / "soxl_simple.html"
REPORT_HTML = BASE_DIR / "soxl_analysis_report.html"
MCP_SERVER = BASE_DIR / "soxl_mcp.py"
log = logging.getLogger("auto_update")


def _setup_logging() -> None:
  scheduler.LOG_DIR.mkdir(parents=True, exist_ok=True)
  fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
  fh = logging.handlers.RotatingFileHandler(scheduler.LOG_DIR / "auto_update.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
  fh.setFormatter(fmt)
  sh = logging.StreamHandler(sys.stderr)
  sh.setFormatter(fmt)
  logging.basicConfig(level=logging.INFO, handlers=[fh, sh])


def _acquire_lock() -> bool:
  scheduler.LOG_DIR.mkdir(parents=True, exist_ok=True)
  try:
    if LOCK_PATH.exists() and time.time() - LOCK_PATH.stat().st_mtime > LOCK_STALE_SEC:
      LOCK_PATH.unlink()
  except OSError:
    pass
  try:
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
  except FileExistsError:
    return False
  with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n")
  return True


def _release_lock() -> None:
  try:
    LOCK_PATH.unlink()
  except OSError:
    pass


def _summary(payload: dict) -> dict:
  tech = payload.get("technicals") or {}
  sc = payload.get("scoring") or {}
  pb = payload.get("playbook") or {}
  b = pb.get("beginner") or {}
  cons = sc.get("consensus") or {}
  return {
      "data_as_of": payload.get("data_as_of"), "generated_at": payload.get("generated_at"),
      "close": tech.get("close"), "ret_1d": tech.get("ret_1d"),
      "composite": sc.get("composite_score"), "rating_5": sc.get("rating_5"), "rating_label": sc.get("rating_label"),
      "verdict": b.get("verdict"), "emoji": b.get("emoji"), "size_pct": b.get("size_pct"),
      "checklist": f"{pb.get('checklist_passed', 0)}/{pb.get('checklist_total', 0)}",
      "sell_pct": cons.get("sell_pct"), "hold_pct": cons.get("hold_pct"), "buy_pct": cons.get("buy_pct"),
      "warnings": payload.get("warnings") or [],
      "data_final": bool((payload.get("data_status") or {}).get("final", True)),
      "data_label": (payload.get("data_status") or {}).get("label"),
  }


# --------------------------------------------------------------------------- #
# brief / push helpers shared by run, push, push-test
# --------------------------------------------------------------------------- #
def _feed_paths() -> dict:
  d = briefmod.FEED_DIR
  return {"json": str(d / "latest.json"), "md": str(d / "latest.md"), "txt": str(d / "latest.txt"), "simple_html": str(SIMPLE_HTML), "report_html": str(REPORT_HTML)}


def _message_from_feed(kind: str = "daily_brief") -> notifymod.Message | None:
  br = briefmod.load_latest()
  if not br:
    return None
  md_p, txt_p = briefmod.FEED_DIR / "latest.md", briefmod.FEED_DIR / "latest.txt"
  md = md_p.read_text(encoding="utf-8") if md_p.exists() else briefmod.to_markdown(br)
  txt = txt_p.read_text(encoding="utf-8").strip() if txt_p.exists() else briefmod.to_text(br)
  v, pr = br.get("verdict") or {}, br.get("price") or {}
  title = f"SOXL {br.get('data_as_of')} {v.get('emoji') or ''} {v.get('label') or ''}｜${pr.get('close')}（{(pr.get('ret_1d') or 0):+.2f}%）".strip()
  return notifymod.Message(br, md, txt, title, kind, _feed_paths())


def _push(m: notifymod.Message, cfg_sched: dict, only: set[str] | None = None, success: bool = True) -> list[dict]:
  try:
    ncfg = notifymod.load_config()
  except ValueError as e:
    log.error("notify_config.json 錯誤：%s", e)
    return [{"channel": "config", "type": "config", "ok": False, "detail": str(e)}]
  if not cfg_sched.get("notify", True):
    return []
  changed = ((m.brief or {}).get("changes") or {}).get("verdict_changed")
  ok, why = notifymod.should_send(ncfg, success, changed)
  if not ok:
    log.info("push skipped: %s", why)
    return [{"channel": "all", "type": "policy", "ok": True, "detail": f"skipped: {why}"}]
  # the macOS banner uses the scheduler's sound setting unless overridden per channel
  for ch in ncfg.get("channels", []):
    if ch.get("type") == "macos" and "sound" not in ch:
      ch["sound"] = cfg_sched.get("notify_sound", "Glass")
  return notifymod.dispatch(m, ncfg, only)


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  trigger = os.environ.get("SOXL_TRIGGER", "manual")
  if args.if_stale:
    stale, why = scheduler.staleness(cfg)
    if not stale:
      log.info("skip (%s): %s", trigger, why)
      return 0
    log.info("stale (%s): %s", trigger, why)
  if not _acquire_lock():
    log.warning("another update is already running (lock %s) — exiting", LOCK_PATH)
    return 0
  attempts = max(1, cfg["retries"] if args.retries is None else args.retries)
  waits = [float(args.wait_min)] if args.wait_min is not None else cfg["retry_wait_min"]
  started = datetime.now()
  notify_on = cfg["notify"] and not args.no_notify
  err_text = ""
  try:
    from soxl_quant.pipeline import run as run_pipeline
    for attempt in range(1, attempts + 1):
      t0 = time.time()
      refresh = bool(cfg["refresh_cache"]) and attempt == 1 and not args.no_refresh
      log.info("attempt %d/%d (trigger=%s, refresh=%s)", attempt, attempts, trigger, refresh)
      try:
        payload = run_pipeline(write_html=True, refresh=refresh)
      except KeyboardInterrupt:
        raise
      except Exception as e:  # noqa: BLE001
        err_text = f"{type(e).__name__}: {e}"
        log.error("attempt %d failed after %.0fs: %s", attempt, time.time() - t0, err_text)
        log.debug("%s", traceback.format_exc())
        if attempt < attempts:
          wait_min = waits[min(attempt - 1, len(waits) - 1)]
          log.info("retrying in %.0f min", wait_min)
          if notify_on:
            scheduler.notify("SOXL 自動更新失敗，稍後重試", f"{err_text[:120]} — {wait_min:.0f} 分鐘後重試", f"第 {attempt}/{attempts} 次", "")
          time.sleep(wait_min * 60.0)
        continue
      finished = datetime.now()
      s = _summary(payload)
      feed_info = payload.get("_feed") or {}
      nxt = scheduler.next_runs(cfg, count=1)
      rec = {
          "status": "ok", "trigger": trigger, "attempt": attempt, "attempts": attempts,
          "started": started.isoformat(timespec="seconds"), "finished": finished.isoformat(timespec="seconds"),
          "duration_s": round((finished - started).total_seconds()),
          "next_run": nxt[0].strftime("%Y-%m-%d %H:%M") if nxt else None,
          "feed_ok": bool(feed_info.get("ok")), "feed_notes": feed_info.get("notes") or [],
          **s,
      }
      log.info("OK data_as_of=%s close=%s verdict=%s composite=%s size=%s%% warnings=%s",
               s["data_as_of"], s["close"], s["verdict"], s["composite"], s["size_pct"], s["warnings"] or "none")
      # ---- push (macOS + configured channels)
      if notify_on:
        try:
          m = _message_from_feed()
          if m:
            if s["warnings"]:
              m.title += "（部分來源缺）"
            rec["push"] = _push(m, cfg, success=True)
          else:
            title = f"SOXL 今日評級 {s.get('emoji') or ''} {s.get('verdict') or ''}".strip()
            scheduler.notify(title, f"資料 {s.get('data_as_of')} 已更新（簡報產生失敗）", "", cfg["notify_sound"])
            rec["push"] = [{"channel": "macos", "type": "macos", "ok": True, "detail": "fallback banner (no brief)"}]
        except Exception as e:  # noqa: BLE001
          log.error("push stage crashed: %s", e)
          rec["push"] = [{"channel": "all", "type": "internal", "ok": False, "detail": f"{type(e).__name__}: {e}"}]
      # ---- publish to GitHub (Pages)
      if not args.no_publish:
        pub = publishmod.publish(cfg, s)
        rec["publish"] = pub
        (log.info if pub.get("status") in ("ok", "nochange", "skipped", "disabled") else log.warning)("publish: %s", pub)
      scheduler.write_last_run(rec)
      if cfg["open_after_update"] and SIMPLE_HTML.exists():
        scheduler.open_file(SIMPLE_HTML)
      return 0
    # all attempts failed
    finished = datetime.now()
    rec = {
        "status": "error", "trigger": trigger, "attempt": attempts, "attempts": attempts,
        "started": started.isoformat(timespec="seconds"), "finished": finished.isoformat(timespec="seconds"),
        "duration_s": round((finished - started).total_seconds()), "error": err_text[:300],
    }
    last_ok = scheduler.read_last_run()
    if last_ok and last_ok.get("status") == "ok":
      rec["last_ok"] = {k: last_ok.get(k) for k in ("finished", "data_as_of", "verdict", "composite")}
    log.error("GIVING UP after %d attempts: %s", attempts, err_text)
    if notify_on:
      scheduler.notify("SOXL 自動更新失敗", f"{err_text[:160]}", f"已重試 {attempts} 次，沿用上一份報告", "Basso")
      prev = briefmod.load_latest() or {}
      m = notifymod.Message(prev, f"# SOXL 自動更新失敗\n\n{err_text}\n\n已重試 {attempts} 次，沿用上一份簡報（{prev.get('data_as_of')}）。", f"自動更新失敗：{err_text[:160]}", "SOXL 自動更新失敗", "update_failed", _feed_paths())
      rec["push"] = _push(m, cfg, success=False)
    scheduler.write_last_run(rec)
    return 1
  finally:
    _release_lock()


# --------------------------------------------------------------------------- #
# schedule commands
# --------------------------------------------------------------------------- #
def cmd_install(_: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  res = scheduler.install(cfg)
  print(f"✅ 已安裝 LaunchAgent：{res['plist']}  (launchctl {res['method']})")
  print(f"   排程：{scheduler.weekday_text(cfg)} {'、'.join(cfg['times'])}（本機時間）  登入補跑：{'開' if cfg['run_at_login_if_stale'] else '關'}")
  print(f"   下次：{' / '.join(res['next_runs']) or 'n/a'}")
  print(f"   狀態：{res['state']}")
  print("   提示：第一次由 launchd 執行時 macOS 可能跳出「python 想要存取 Documents 資料夾」→ 請按「好」。")
  return 0


def cmd_uninstall(_: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  res = scheduler.uninstall(cfg)
  print(f"🗑  已移除排程：{res['plist']} ({'刪除' if res['removed'] else '原本就不存在'})")
  return 0


def cmd_status(_: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  installed = scheduler.is_installed(cfg)
  print(f"排程檔：{scheduler.plist_path(cfg)}  → {'已安裝' if installed else '未安裝（執行 auto_update.py install）'}")
  print(f"排程：{scheduler.weekday_text(cfg)} {'、'.join(cfg['times'])}（本機時間）；登入補跑 {'開' if cfg['run_at_login_if_stale'] else '關'}；重試 {cfg['retries']} 次")
  st = scheduler.agent_state(cfg)
  print(f"launchd：{st}")
  if st.get("state") == "running" and str(st.get("pid", "")).isdigit():
    try:
      import subprocess
      et = subprocess.run(["/bin/ps", "-p", str(int(st["pid"])), "-o", "etime="], capture_output=True, text=True, timeout=10, check=False).stdout.strip()
      days, _, rest = et.rpartition("-")
      parts = [int(x) for x in rest.split(":")] if rest else []
      alive_s = (int(days) * 86400 if days else 0) + sum(v * m for v, m in zip(reversed(parts), (1, 60, 3600)))
    except (OSError, ValueError, subprocess.SubprocessError):
      alive_s = 0
    if alive_s > 45 and not LOCK_PATH.exists():
      print(f"⚠️ launchd 啟動的程序 (pid {st['pid']}) 已跑 {alive_s}s 但還沒開始工作 → 很可能卡在 macOS 權限對話框")
      print("   請在螢幕上找「python3.14 想要取用你的「文件」檔案夾」並按「好」（只會問一次）；")
      print("   或到 系統設定 → 隱私權與安全性 → 檔案與檔案夾 / 完整磁碟取用權 → 允許 python3.14。")
  nx = scheduler.next_runs(cfg)
  print(f"下次執行：{' / '.join(d.strftime('%Y-%m-%d %H:%M') for d in nx) or 'n/a'}")
  stale, why = scheduler.staleness(cfg)
  print(f"現在需要更新嗎：{'是' if stale else '否'}（{why}）")
  last = scheduler.read_last_run()
  if last:
    if last.get("status") == "ok":
      print(f"上次更新：✅ {last.get('finished')}（{last.get('duration_s')}s, 第 {last.get('attempt')} 次嘗試, 來源 {last.get('trigger')}）")
      print(f"   資料 {last.get('data_as_of')} 收盤 ${last.get('close')}（{last.get('ret_1d')}%）→ {last.get('emoji')} {last.get('verdict')}，綜合 {last.get('composite')}，倉位上限 {last.get('size_pct')}%")
      if last.get("warnings"):
        print(f"   ⚠️ 警告：{last['warnings']}")
    else:
      print(f"上次更新：❌ {last.get('finished')} 失敗：{last.get('error')}")
    for r in last.get("push") or []:
      print(f"   推播 {r.get('channel')}: {'✅' if r.get('ok') else '❌'} {r.get('detail')}")
    if last.get("publish"):
      p = last["publish"]
      detail = str(p.get("detail") or p.get("message") or "").strip().splitlines()
      print(f"   發佈 git: {p.get('status')} {p.get('commit') or ''} {detail[0] if detail else ''}" + (f"（{p['hint']}）" if p.get("hint") else ""))
  else:
    print("上次更新：尚無紀錄")
  try:
    ncfg = notifymod.load_config()
    chans = [c.get("name") or c.get("type") for c in notifymod.enabled_channels(ncfg)]
    print(f"推播頻道（{notifymod.CONFIG_PATH.name}{'，預設' if ncfg.get('_default') else ''}）：{', '.join(chans) or '無'}")
  except ValueError as e:
    print(f"推播設定錯誤：{e}")
  gs = publishmod.status()
  if gs.get("git"):
    print(f"git：{gs.get('branch')}@{gs.get('head')} → {gs.get('remote') or '（無遠端）'}；未推送 commit {gs.get('ahead')}；工作區{'有' if gs.get('dirty') else '無'}未提交變更；自動發佈 {'開' if cfg['publish']['git_push'] else '關'}")
  fp = briefmod.FEED_DIR / "latest.json"
  if fp.exists():
    print(f"feed：{fp}（{datetime.fromtimestamp(fp.stat().st_mtime):%Y-%m-%d %H:%M}）；公開網址 {cfg['feed']['base_url']}feed/latest.json")
  err_log = scheduler.LAUNCHD_LOG_DIR / "launchd.err.log"
  if err_log.exists() and err_log.stat().st_size:
    tail = err_log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
    print("launchd stderr（最後 5 行）：")
    for line in tail:
      print("   " + line)
  print(f"紀錄檔：{scheduler.LOG_DIR / 'auto_update.log'}；launchd 輸出：{scheduler.LAUNCHD_LOG_DIR}")
  return 0


def cmd_notify_test(_: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  ok = scheduler.notify("SOXL 自動更新測試", "如果你看到這則通知，表示排程完成時也會這樣提醒你。", "auto_update.py notify-test", cfg["notify_sound"])
  print("通知已送出" if ok else "通知失敗（非 macOS 或 osascript 不可用）")
  return 0 if ok else 1


def cmd_config(_: argparse.Namespace) -> int:
  cfg = scheduler.load_config(create=True)
  print(f"設定檔：{scheduler.CONFIG_PATH}")
  for k, v in cfg.items():
    print(f"  {k}: {v}")
  return 0


# --------------------------------------------------------------------------- #
# agent-facing commands
# --------------------------------------------------------------------------- #
def cmd_brief(args: argparse.Namespace) -> int:
  br = briefmod.load_latest()
  if not br:
    print("尚無 feed/latest.json — 先執行 auto_update.py run 或 auto_update.py feed", file=sys.stderr)
    return 1
  if args.json:
    print(json.dumps(br, ensure_ascii=False, indent=1))
  elif args.text:
    print(briefmod.to_text(br))
  else:
    p = briefmod.FEED_DIR / "latest.md"
    print(p.read_text(encoding="utf-8") if p.exists() else briefmod.to_markdown(br))
  return 0


def cmd_feed(args: argparse.Namespace) -> int:
  from soxl_quant import history, pipeline
  jp = BASE_DIR / "soxl_analysis_data.json"
  if not jp.exists():
    print("找不到 soxl_analysis_data.json — 先執行 auto_update.py run", file=sys.stderr)
    return 1
  payload = json.loads(jp.read_text(encoding="utf-8"))
  payload["verdict_history"] = history.load(60)
  try:
    payload["schedule"] = scheduler.schedule_summary()
  except Exception as e:  # noqa: BLE001
    payload["schedule"] = {"installed": False, "error": str(e)}
  info = pipeline.build_feed(payload, with_quotes=not args.offline)
  for k, v in (info.get("paths") or {}).items():
    print(f"  {k:9s} {v}")
  if info.get("notes"):
    print("  notes:", info["notes"])
  return 0 if info.get("ok") else 1


def cmd_meta(_: argparse.Namespace) -> int:
  """Rebuild meta/ (the Muse / AI-agent Markdown pack) from the existing feed/latest.json without recomputing."""
  from soxl_quant import brief as briefmod, meta_pack
  br = briefmod.load_latest()
  if not br:
    print("尚無 feed/latest.json — 先執行 auto_update.py run 或 auto_update.py feed", file=sys.stderr)
    return 1
  try:
    cfg = scheduler.load_config(create=False)
    base_url = (cfg.get("feed") or {}).get("base_url")
  except Exception:  # noqa: BLE001
    base_url = None
  res = meta_pack.build(br, None, base_url)
  for name, size in res["files"]:
    print(f"  {size / 1024:6.1f} KB  {name}")
  print(f"meta/ 重建完成：{len(res['files'])} 個檔案，{res['total_bytes'] // 1024} KB，資料日 {br.get('data_as_of')} → {res['dir']}")
  if getattr(_, "zip", None) is not None:
    import shutil
    target = Path(_.zip).expanduser() if _.zip else Path.home() / "Downloads" / f"soxl_meta_pack_{br.get('data_as_of')}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    out = shutil.make_archive(str(target.with_suffix("")), "zip", root_dir=str(Path(res["dir"]).parent), base_dir="meta")
    print(f"壓縮檔（可直接上傳給 Muse）：{out}（{Path(out).stat().st_size // 1024} KB）")
  return 0


PACK_EXCLUDE_DIRS = {".venv", ".cache", ".qa", "logs", "__pycache__", ".pytest_cache", ".DS_Store"}
PACK_EXCLUDE_FILES = {"notify_config.json", "meta.zip"}


def _pack_repo(target: Path) -> tuple[int, int]:
  """Zip the whole repo INCLUDING .git into ``target``; returns (files, skipped).  Raises RuntimeError if secrets leak."""
  import zipfile
  target.parent.mkdir(parents=True, exist_ok=True)
  root = BASE_DIR
  top = "stock-dashboard"
  n = skipped = 0
  with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for p in sorted(root.rglob("*")):
      rel = p.relative_to(root)
      parts = rel.parts
      if any(part in PACK_EXCLUDE_DIRS for part in parts) or rel.name in PACK_EXCLUDE_FILES or rel.name.endswith(".pyc") or (rel.name.startswith("notify_config") and rel.suffix == ".json" and rel.name != "notify_config.example.json"):
        skipped += 1
        continue
      if rel.match("*.bak.*.json"):
        skipped += 1
        continue
      if p.is_dir():
        continue
      zf.write(p, f"{top}/{rel.as_posix()}")
      n += 1
    guide = root / "PUBLISHING.md"
    if guide.exists():
      zf.write(guide, "PUSH_ME_FIRST.md")
  with zipfile.ZipFile(target) as zf:
    names = zf.namelist()
    bad = [x for x in names if "notify_config.json" in x or "/.venv/" in x or "/.cache/" in x or "/logs/" in x]
    has_git = any(x.startswith(f"{top}/.git/") for x in names)
  if bad or not has_git:
    raise RuntimeError(f"打包驗證失敗：secrets/cache 混入 {bad[:3]}，.git 存在 {has_git}")
  return n, skipped


def cmd_pack_repo(args: argparse.Namespace) -> int:
  """Zip the whole repo INCLUDING .git (so the commits travel) for pushing from another machine.

  Excludes the venv, caches, logs, QA screenshots, compiled files and every secret-bearing file
  (notify_config.json and *.bak.*.json), then verifies the archive by listing it.
  """
  from soxl_quant import brief as briefmod
  br = briefmod.load_latest() or {}
  stamp = br.get("data_as_of") or datetime.now().strftime("%Y-%m-%d")
  target = Path(args.out).expanduser() if args.out else Path.home() / "Downloads" / f"stock-dashboard_repo_{stamp}.zip"
  try:
    n, skipped = _pack_repo(target)
  except RuntimeError as e:
    print(str(e), file=sys.stderr)
    return 1
  print(f"repo 壓縮檔：{target}（{target.stat().st_size // 1024 // 1024} MB，{n} 個檔案，含 .git 歷史；略過 {skipped} 個快取 / 密鑰 / 暫存項目）")
  print("另一台電腦：unzip → cd stock-dashboard → 先 git fetch origin main + rebase 再正常推送（詳見 PUBLISHING.md；絕不覆蓋推送）")
  return 0


def cmd_pack_agent(args: argparse.Namespace) -> int:
  """Build the agent operator pack: README runbook + RUNBOOK.json + APIS.md / apis.json + meta/ + the repo zip, in one zip.

  Written for an AI agent (Muse or any agent with a shell): how to push this repo to GitHub once, how to confirm
  Actions + Pages, every API in three layers (upstream data, published endpoints, delivery into the agent), and the
  daily consumption loop.  Facts (HEAD, remote, data_as_of) are measured at build time.
  """
  import shutil
  import tempfile
  import zipfile
  from soxl_quant import agent_pack, brief as briefmod, meta_pack
  br = briefmod.load_latest()
  if not br:
    print("找不到 feed/latest.json — 先執行 auto_update.py run", file=sys.stderr)
    return 1
  stamp = br.get("data_as_of") or datetime.now().strftime("%Y-%m-%d")
  cfg = scheduler.load_config(create=False)
  base_url = (cfg.get("feed") or {}).get("base_url")
  payload = None
  jp = BASE_DIR / "soxl_analysis_data.json"
  if jp.exists():
    try:
      payload = json.loads(jp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
      payload = None
  man_p = Path(meta_pack.META_DIR) / "manifest.json"
  try:
    man = json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else {}
  except json.JSONDecodeError:
    man = {}
  if man.get("generated_at") == br.get("generated_at") and man.get("files"):
    mp = {"dir": str(meta_pack.META_DIR), "files": man["files"], "total_bytes": man.get("total_bytes", 0)}  # already current: keep the committed copy byte-identical
  else:
    mp = meta_pack.build(br, payload, base_url)
  out = Path(args.out).expanduser() if args.out else Path.home() / "Downloads" / f"soxl_agent_pack_{stamp}.zip"
  out.parent.mkdir(parents=True, exist_ok=True)
  top = "soxl-agent-pack"
  with tempfile.TemporaryDirectory() as td:
    repo_zip = Path(td) / f"stock-dashboard_repo_{stamp}.zip"
    try:
      n_repo, _ = _pack_repo(repo_zip)
    except RuntimeError as e:
      print(str(e), file=sys.stderr)
      return 1
    docs = agent_pack.build_docs(br, base_url, repo_zip)
    # keep a copy of the repo zip in Downloads too (same artifact the push instructions name)
    repo_copy = out.parent / repo_zip.name
    shutil.copyfile(repo_zip, repo_copy)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
      for name, text in docs.items():
        zf.writestr(f"{top}/{name}", text)
      meta_dir = Path(mp["dir"])
      for p in sorted(meta_dir.rglob("*")):
        if p.is_file():
          zf.write(p, f"{top}/meta/{p.relative_to(meta_dir).as_posix()}")
      zf.write(repo_zip, f"{top}/{repo_zip.name}", compress_type=zipfile.ZIP_STORED)
    with zipfile.ZipFile(out) as zf:
      names = zf.namelist()
  must = {f"{top}/README.md", f"{top}/RUNBOOK.json", f"{top}/apis.json", f"{top}/APIS.md", f"{top}/meta/README.md", f"{top}/meta/data/latest.json", f"{top}/{repo_zip.name}"}
  missing = sorted(must - set(names))
  if missing:
    print(f"打包驗證失敗：缺 {missing}", file=sys.stderr)
    return 1
  print(f"agent 操作包：{out}（{out.stat().st_size // 1024 // 1024} MB，{len(names)} 個項目）")
  print(f"  README.md（操作員規格：事實 / 路徑 / 步驟 + 期望輸出 / API 三層 / 每日迴圈 / 驗收 / 故障排除）、RUNBOOK.json、APIS.md、apis.json")
  print(f"  meta/（{len(mp['files'])} 個檔案，資料日 {stamp}）、{repo_zip.name}（{n_repo} 個檔案，含 .git）")
  print(f"  repo 壓縮檔另存一份：{repo_copy}")
  print("給 agent 的一句話：把這個 zip 給它，說「照 README.md 做：先推上 GitHub，再照第 5 節每天抓」。")
  return 0


def cmd_quotes(args: argparse.Namespace) -> int:
  from soxl_quant import quotes
  q = quotes.snapshot()
  if args.json:
    print(json.dumps(q, ensure_ascii=False, indent=1))
    return 0
  print(f"{q['fetched_at_tpe']}（{q['fetched_at_et']}）市場狀態 {q.get('market_status') or 'n/a'}")
  print(q["one_liner"])
  for r in q["core"] + q["leaders"] + q["volatility"]:
    if r.get("available"):
      ext = f"  盤後 {r['ext_last']} ({r['ext_change_pct']:+.2f}%)" if r.get("ext_last") and r.get("ext_change_pct") is not None else ""
      print(f"  {r['symbol']:6s} {r['last']:>10.2f}  {(r.get('change_pct') or 0):+6.2f}%  {r['label']}{ext}")
    else:
      print(f"  {r['symbol']:6s} {'n/a':>10s}  {r['label']}")
  return 0


def _mcp_entry() -> dict:
  py = scheduler.python_path()
  return {"soxl-quant": {"command": str(py), "args": [str(MCP_SERVER)], "env": {"PYTHONUTF8": "1"}}}


def cmd_mcp_config(_: argparse.Namespace) -> int:
  entry = _mcp_entry()
  print("# Antigravity / Gemini CLI（~/.gemini/config/mcp_config.json 的 mcpServers 內）")
  print(json.dumps({"mcpServers": entry}, ensure_ascii=False, indent=2))
  print("\n# Claude Desktop（claude_desktop_config.json）/ Cursor（.cursor/mcp.json）格式相同；")
  print("# 任何支援 MCP stdio 的 agent 都能直接呼叫 get_brief / get_latest / get_news / get_quotes / get_events / get_history / refresh。")
  return 0


def cmd_mcp_install(args: argparse.Namespace) -> int:
  target = Path(args.path or (Path.home() / ".gemini" / "config" / "mcp_config.json")).expanduser()
  data: dict = {}
  if target.exists():
    try:
      data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
      print(f"{target} 不是合法 JSON，未修改：{e}", file=sys.stderr)
      return 2
    backup = target.with_suffix(f".bak.{datetime.now():%Y%m%d_%H%M%S}.json")
    shutil.copy2(target, backup)
    print(f"備份：{backup}")
  servers = data.setdefault("mcpServers", {})
  if not isinstance(servers, dict):
    print("mcpServers 不是物件，未修改", file=sys.stderr)
    return 2
  servers.update(_mcp_entry())
  target.parent.mkdir(parents=True, exist_ok=True)
  from soxl_quant import fsio
  fsio.atomic_write_text(target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
  json.loads(target.read_text(encoding="utf-8"))  # re-validate
  print(f"✅ 已寫入 {target} → mcpServers.soxl-quant（重新載入 MCP / 重啟 agent 後生效）")
  return 0


# --------------------------------------------------------------------------- #
# Antigravity sidecar: every trading morning open a new agent conversation with the brief
# --------------------------------------------------------------------------- #
SIDECAR_ID = "soxl-daily-brief"
SIDECAR_DIR = Path.home() / ".gemini" / "config" / "sidecars" / SIDECAR_ID
SIDECAR_PROMPT = (
    "每日 SOXL 簡報（自動排程）。請讀取 {md}（需要數字時再讀 {js}），"
    "先確認 data_as_of 是最近一個已收盤的美股交易日（若不是，先說明資料日期與原因，可執行 `{py} {au} status` 查看）。"
    "然後用新手聽得懂的話、三句以內回答：今天 SOXL 該買、該賣還是觀望（先講「新手一眼看懂」的答案）？最重要的理由是什麼（帶上「今天最大的事」）？要盯哪一個價位？再用一行列出六個儀表的燈號（能不能加碼、宏觀、費半、大戶、Put/Call、崩跌指數）。"
    "接著列出：建議倉位上限、停損 / 目標價、48 小時內的風險事件（FOMC / 財報 / 到期）、消息面一句話。"
    "最後附一句免責聲明。不要修改任何檔案。"
)


def _sidecar_json(time_hhmm: str, weekdays: list[int], model: str) -> dict:
  hh, mm = (int(x) for x in time_hhmm.split(":"))
  cron_days = ",".join(str(d) for d in weekdays)  # cron: 0=Sun … 6=Sat (same as launchd)
  prompt = SIDECAR_PROMPT.format(md=str(briefmod.FEED_DIR / "latest.md"), js=str(briefmod.FEED_DIR / "latest.json"), py=str(scheduler.python_path()), au=str(BASE_DIR / "auto_update.py"))
  args = [f"{mm} {hh} * * {cron_days}", "agentapi", "new-conversation", "--title=SOXL 每日簡報"]
  if model in ("flash_lite", "flash", "pro"):
    args.append(f"--model={model}")
  args.append(prompt)
  return {"builtin": "schedule", "args": args, "restart_policy": "always",
          "description": f"每個美股交易日隔天 {time_hhmm}（台北）開一個新的 agent 對話，請它讀 feed/latest.md 並用三句話告訴你今天 SOXL 該買 / 該賣 / 觀望（由 {BASE_DIR.name}/auto_update.py sidecar-install 建立）。"}


def cmd_sidecar_install(args: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  t = args.time or "07:50"
  if not scheduler._TIME_RE.match(t):  # noqa: SLF001
    print("時間格式必須是 HH:MM", file=sys.stderr)
    return 2
  from soxl_quant import fsio
  SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
  data = _sidecar_json(t, cfg["weekdays"], args.model or "")
  fsio.atomic_write_text(SIDECAR_DIR / "sidecar.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
  print(f"✅ 已建立 Antigravity sidecar：{SIDECAR_DIR / 'sidecar.json'}")
  print(f"   排程：{scheduler.weekday_text(cfg)} {t}（本機時間；資料更新排程為 {'、'.join(cfg['times'])}，請留 15 分鐘以上）")
  print("   效果：每個交易日早上自動開一個新的 agent 對話，agent 會讀 feed/latest.md 並用三句話告訴你該買 / 該賣 / 觀望。")
  print("   移除：auto_update.py sidecar-uninstall")
  return 0


def cmd_sidecar_uninstall(_: argparse.Namespace) -> int:
  p = SIDECAR_DIR / "sidecar.json"
  if p.exists():
    p.unlink()
    try:
      SIDECAR_DIR.rmdir()
    except OSError:
      pass
    print(f"🗑  已移除 {p}")
  else:
    print("sidecar 原本就不存在")
  return 0


# --------------------------------------------------------------------------- #
# push / publish commands
# --------------------------------------------------------------------------- #
def cmd_notify_config(_: argparse.Namespace) -> int:
  notifymod.write_example()
  if notifymod.CONFIG_PATH.exists():
    print(f"已存在：{notifymod.CONFIG_PATH}（範本更新於 {notifymod.EXAMPLE_PATH}）")
  else:
    notifymod.load_config(create=True)
    print(f"✅ 已建立 {notifymod.CONFIG_PATH}（chmod 600，已被 .gitignore 排除）")
  print("把要用的頻道 enabled 改成 true 並填入網址 / 金鑰，然後：.venv/bin/python auto_update.py push-test")
  return 0


def cmd_push(args: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  m = _message_from_feed()
  if not m:
    print("尚無 feed/latest.json — 先執行 auto_update.py run 或 feed", file=sys.stderr)
    return 1
  only = {x.strip() for x in (args.only or "").split(",") if x.strip()} or None
  res = _push(m, {**cfg, "notify": True}, only, success=True)
  for r in res:
    print(f"  {r.get('channel'):12s} {'✅' if r.get('ok') else '❌'} {r.get('detail')}")
  return 0 if res and all(r.get("ok") for r in res) else 1


def cmd_push_test(args: argparse.Namespace) -> int:
  br = briefmod.load_latest() or {"links": {}, "verdict": {}, "price": {}}
  now = datetime.now().strftime("%Y-%m-%d %H:%M")
  md = f"# SOXL 推播測試 {now}\n\n如果你（或你的 agent）收到這則訊息，表示每天收盤後的簡報也會送到這裡。\n\n{briefmod.to_text(br) if br.get('data_as_of') else ''}"
  m = notifymod.Message(br, md, f"SOXL 推播測試 {now}：頻道設定正確。", f"SOXL 推播測試 {now}", "test", _feed_paths())
  try:
    ncfg = notifymod.load_config()
  except ValueError as e:
    print(f"notify_config.json 錯誤：{e}", file=sys.stderr)
    return 2
  only = {x.strip() for x in (args.only or "").split(",") if x.strip()} or None
  chans = notifymod.enabled_channels(ncfg)
  if not chans:
    print("沒有啟用的頻道（notify_config.json → channels[*].enabled）")
    return 1
  res = notifymod.dispatch(m, ncfg, only)
  for r in res:
    print(f"  {r.get('channel'):12s} {'✅' if r.get('ok') else '❌'} {r.get('detail')}")
  return 0 if res and all(r.get("ok") for r in res) else 1


def cmd_push_status(_: argparse.Namespace) -> int:
  try:
    ncfg = notifymod.load_config()
  except ValueError as e:
    print(f"notify_config.json 錯誤：{e}", file=sys.stderr)
    return 2
  print(json.dumps(notifymod.redact(ncfg), ensure_ascii=False, indent=2))
  return 0


def cmd_publish(_: argparse.Namespace) -> int:
  cfg = scheduler.load_config()
  last = scheduler.read_last_run() or {}
  res = publishmod.publish({**cfg, "publish": {**cfg["publish"], "git_push": True}}, last)
  print(json.dumps(res, ensure_ascii=False, indent=1))
  return 0 if res.get("status") in ("ok", "nochange") else 1


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  sub = ap.add_subparsers(dest="cmd")
  run_p = sub.add_parser("run", help="立刻更新（預設指令）")
  run_p.add_argument("--if-stale", action="store_true", help="只有資料落後最近美股交易日才更新")
  run_p.add_argument("--retries", type=int, default=None, help="覆寫重試次數")
  run_p.add_argument("--wait-min", type=float, default=None, help="覆寫重試等待分鐘數")
  run_p.add_argument("--no-refresh", action="store_true", help="不清快取")
  run_p.add_argument("--no-notify", action="store_true", help="不推播（macOS 與所有頻道）")
  run_p.add_argument("--no-publish", action="store_true", help="不 git push")
  for name in ("install", "uninstall", "status", "notify-test", "config", "notify-config", "push-status", "publish", "mcp-config"):
    sub.add_parser(name)
  b = sub.add_parser("brief")
  b.add_argument("--json", action="store_true")
  b.add_argument("--text", action="store_true")
  f = sub.add_parser("feed")
  f.add_argument("--offline", action="store_true", help="不抓即時報價")
  pr = sub.add_parser("pack-repo", help="把整個 repo（含 .git）壓成 zip 帶去另一台電腦推送；不含 venv / 快取 / logs / 密鑰")
  pr.add_argument("--out", default=None, metavar="PATH", help="輸出路徑（預設 ~/Downloads/stock-dashboard_repo_<日期>.zip）")
  pa = sub.add_parser("pack-agent", help="給 AI agent（Muse）的操作包：README 操作員規格 + RUNBOOK.json + apis.json + meta/ + repo zip，一個 zip 搞定推送、串 API、每日抓取")
  pa.add_argument("--out", default=None, metavar="PATH", help="輸出路徑（預設 ~/Downloads/soxl_agent_pack_<日期>.zip）")
  m = sub.add_parser("meta", help="用既有 feed/latest.json 重建 meta/（給 Muse / AI agent 的 Markdown 吸收包）")
  m.add_argument("--zip", nargs="?", const="", default=None, metavar="PATH", help="另外打包成 zip（預設 ~/Downloads/soxl_meta_pack_<日期>.zip）")
  q = sub.add_parser("quotes")
  q.add_argument("--json", action="store_true")
  p = sub.add_parser("push")
  p.add_argument("--only", default="", help="逗號分隔的頻道類型，例如 webhook,telegram")
  pt = sub.add_parser("push-test")
  pt.add_argument("--only", default="")
  mi = sub.add_parser("mcp-install")
  mi.add_argument("--path", default="", help="mcp_config.json 路徑（預設 ~/.gemini/config/mcp_config.json）")
  si = sub.add_parser("sidecar-install")
  si.add_argument("--time", default="", help="每天幾點開新對話（預設 07:50，本機時間）")
  si.add_argument("--model", default="", help="flash_lite / flash / pro（預設沿用 agent 設定）")
  sub.add_parser("sidecar-uninstall")
  args = ap.parse_args(argv)
  _setup_logging()
  cmd = args.cmd or "run"
  if cmd == "run" and args.cmd is None:
    args = run_p.parse_args([])
  handlers = {
      "run": cmd_run, "install": cmd_install, "uninstall": cmd_uninstall, "status": cmd_status, "notify-test": cmd_notify_test, "config": cmd_config,
      "brief": cmd_brief, "feed": cmd_feed, "meta": cmd_meta, "pack-repo": cmd_pack_repo, "pack-agent": cmd_pack_agent, "quotes": cmd_quotes, "mcp-config": cmd_mcp_config, "mcp-install": cmd_mcp_install,
      "sidecar-install": cmd_sidecar_install, "sidecar-uninstall": cmd_sidecar_uninstall,
      "notify-config": cmd_notify_config, "push": cmd_push, "push-test": cmd_push_test, "push-status": cmd_push_status, "publish": cmd_publish,
  }
  try:
    return handlers[cmd](args)
  except ValueError as e:
    print(f"設定錯誤：{e}", file=sys.stderr)
    return 2
  except RuntimeError as e:
    print(f"錯誤：{e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  sys.exit(main())
