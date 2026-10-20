#!/usr/bin/env python3
"""SOXL Quant — 每日自動更新 (runner + macOS 排程 CLI)。

    .venv/bin/python auto_update.py install        安裝 launchd 排程（預設週二～六 07:30 = 美股收盤後）
    .venv/bin/python auto_update.py status         查看排程狀態 / 上次結果 / 下次時間
    .venv/bin/python auto_update.py run            立刻更新一次（含重試、macOS 通知）
    .venv/bin/python auto_update.py run --if-stale 只在資料落後最近美股交易日時更新（排程用）
    .venv/bin/python auto_update.py uninstall      移除排程
    .venv/bin/python auto_update.py notify-test    測試 macOS 通知
    .venv/bin/python auto_update.py config         顯示（必要時建立）auto_update_config.json

每次成功更新都會：重新抓取所有 API → 重算評分 → 寫出
soxl_analysis_data.json / soxl_analysis_report.html / soxl_simple.html（新手版）
→ 追加 history/verdicts.jsonl → logs/last_run.json → macOS 通知今日評級。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
import logging.handlers
import os
from pathlib import Path
import sys
import time
import traceback

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from soxl_quant import scheduler  # noqa: E402

LOCK_PATH = scheduler.LOG_DIR / ".auto_update.lock"
LOCK_STALE_SEC = 3 * 3600
SIMPLE_HTML = BASE_DIR / "soxl_simple.html"
log = logging.getLogger("auto_update")


def _setup_logging() -> None:
  scheduler.LOG_DIR.mkdir(parents=True, exist_ok=True)
  fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
  fh = logging.handlers.RotatingFileHandler(scheduler.LOG_DIR / "auto_update.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
  fh.setFormatter(fmt)
  sh = logging.StreamHandler(sys.stdout)
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
      nxt = scheduler.next_runs(cfg, count=1)
      rec = {
          "status": "ok", "trigger": trigger, "attempt": attempt, "attempts": attempts,
          "started": started.isoformat(timespec="seconds"), "finished": finished.isoformat(timespec="seconds"),
          "duration_s": round((finished - started).total_seconds()),
          "next_run": nxt[0].strftime("%Y-%m-%d %H:%M") if nxt else None,
          **s,
      }
      scheduler.write_last_run(rec)
      log.info("OK data_as_of=%s close=%s verdict=%s composite=%s size=%s%% warnings=%s",
               s["data_as_of"], s["close"], s["verdict"], s["composite"], s["size_pct"], s["warnings"] or "none")
      if notify_on:
        title = f"SOXL 今日評級 {s.get('emoji') or ''} {s.get('verdict') or ''}".strip()
        ret = s.get("ret_1d")
        msg = (f"收盤 ${s.get('close')}（{ret:+.2f}%）｜綜合 {s.get('composite'):+.2f}｜賣 {s.get('sell_pct', 0):.0f}% / 觀 {s.get('hold_pct', 0):.0f}% / 買 {s.get('buy_pct', 0):.0f}%｜倉位上限 {s.get('size_pct')}%"
               if isinstance(ret, (int, float)) and isinstance(s.get("composite"), (int, float)) else f"資料 {s.get('data_as_of')} 已更新")
        sub = f"資料 {s.get('data_as_of')} 收盤 · 檢核 {s.get('checklist')}" + ("（部分來源缺）" if s["warnings"] else "")
        scheduler.notify(title, msg, sub, cfg["notify_sound"])
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
    scheduler.write_last_run(rec)
    log.error("GIVING UP after %d attempts: %s", attempts, err_text)
    if notify_on:
      scheduler.notify("SOXL 自動更新失敗", f"{err_text[:160]}", f"已重試 {attempts} 次，沿用上一份報告", "Basso")
    return 1
  finally:
    _release_lock()


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
  else:
    print("上次更新：尚無紀錄")
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


def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  sub = ap.add_subparsers(dest="cmd")
  run_p = sub.add_parser("run", help="立刻更新（預設指令）")
  run_p.add_argument("--if-stale", action="store_true", help="只有資料落後最近美股交易日才更新")
  run_p.add_argument("--retries", type=int, default=None, help="覆寫重試次數")
  run_p.add_argument("--wait-min", type=float, default=None, help="覆寫重試等待分鐘數")
  run_p.add_argument("--no-refresh", action="store_true", help="不清快取")
  run_p.add_argument("--no-notify", action="store_true", help="不顯示 macOS 通知")
  for name in ("install", "uninstall", "status", "notify-test", "config"):
    sub.add_parser(name)
  args = ap.parse_args(argv)
  _setup_logging()
  cmd = args.cmd or "run"
  if cmd == "run" and args.cmd is None:
    args = run_p.parse_args([])
  handlers = {"run": cmd_run, "install": cmd_install, "uninstall": cmd_uninstall, "status": cmd_status, "notify-test": cmd_notify_test, "config": cmd_config}
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
