#!/usr/bin/env python3
"""Daily auto-update plumbing (macOS launchd, user-level, no sudo).

* ``auto_update_config.json``                 schedule / retry / notification settings
* ``~/Library/LaunchAgents/<label>.plist``    the LaunchAgent that runs
                                              ``auto_update.py run --if-stale``
* staleness                                   decide whether a run is needed, based on
                                              the last completed US trading day (America/New_York)
* notify                                      macOS banner via osascript; the texts are
                                              passed as *argv*, never spliced into AppleScript

launchd (unlike cron) runs a missed StartCalendarInterval job as soon as the Mac
wakes from sleep, and RunAtLoad + ``--if-stale`` catches up right after login if
the machine was switched off at the scheduled time.

Security: every subprocess call uses a fixed absolute binary with a fixed
argument shape; the only user-controlled values (times / weekdays / label /
sound) are validated against strict patterns before they reach a command line.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

from . import marketclock
from .fsio import atomic_write_bytes, atomic_write_text

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "auto_update_config.json"
LOG_DIR = BASE_DIR / "logs"
LAST_RUN_PATH = LOG_DIR / "last_run.json"
LAUNCHD_LOG_DIR = Path.home() / "Library" / "Logs" / "soxl_quant"
ENTRY = BASE_DIR / "auto_update.py"
LAUNCHCTL = "/bin/launchctl"
OSASCRIPT = "/usr/bin/osascript"
OPEN = "/usr/bin/open"
ET = marketclock.ET

DEFAULT_CONFIG: dict = {
    "label": "com.soxlquant.autoupdate",
    "times": ["07:30"],
    "weekdays": [2, 3, 4, 5, 6],
    "run_at_login_if_stale": True,
    "retries": 3,
    "retry_wait_min": [10, 30],
    "refresh_cache": True,
    "notify": True,
    "notify_sound": "Glass",
    "open_after_update": False,
    "_help": {
        "times": "本機時間 HH:MM，可放多個，例如 [\"07:30\", \"23:30\"]（23:30 ≈ 美股盤中快照）",
        "weekdays": "launchd 星期代碼 0=日 1=一 … 6=六；預設二～六 = 美股一～五收盤後",
        "run_at_login_if_stale": "登入/開機時若資料落後最近交易日就立刻補跑（排程時間關機也不會漏）",
        "retries": "失敗重試次數（含第一次）",
        "retry_wait_min": "第 n 次重試前等待的分鐘數（最後一個值會重複使用）",
        "refresh_cache": "排程第一次嘗試是否清快取（確保抓到當日收盤）；重試時沿用快取",
        "notify": "完成/失敗時顯示 macOS 通知",
        "notify_sound": "通知音效名稱（Glass / Ping / Pop / 空字串 = 靜音）",
        "open_after_update": "更新成功後自動用瀏覽器開啟新手版頁面",
    },
}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{2,63}$")
_SOUND_RE = re.compile(r"^[A-Za-z0-9 _-]{0,32}$")
_WD_ZH = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def validate(cfg: dict) -> dict:
  out = {k: v for k, v in DEFAULT_CONFIG.items() if k != "_help"}
  out.update({k: v for k, v in (cfg or {}).items() if k != "_help"})
  if not isinstance(out["label"], str) or not _LABEL_RE.match(out["label"]):
    raise ValueError("label 只能是 3–64 個英數字 . _ -，且以字母開頭")
  times = out["times"] if isinstance(out["times"], list) else [out["times"]]
  if not times or not all(isinstance(t, str) and _TIME_RE.match(t) for t in times):
    raise ValueError("times 必須是 HH:MM 格式的字串清單")
  out["times"] = sorted(set(times))
  wds = out["weekdays"] if isinstance(out["weekdays"], list) else [out["weekdays"]]
  if not wds or not all(isinstance(w, int) and not isinstance(w, bool) and 0 <= w <= 6 for w in wds):
    raise ValueError("weekdays 必須是 0–6 的整數清單（0=週日）")
  out["weekdays"] = sorted(set(wds))
  if not isinstance(out["retries"], int) or isinstance(out["retries"], bool) or not 1 <= out["retries"] <= 6:
    raise ValueError("retries 必須是 1–6 的整數")
  waits = out["retry_wait_min"] if isinstance(out["retry_wait_min"], list) else [out["retry_wait_min"]]
  if not waits or not all(isinstance(w, (int, float)) and not isinstance(w, bool) and 0 <= w <= 240 for w in waits):
    raise ValueError("retry_wait_min 必須是 0–240 的數字清單")
  out["retry_wait_min"] = [float(w) for w in waits]
  for key in ("run_at_login_if_stale", "refresh_cache", "notify", "open_after_update"):
    out[key] = bool(out[key])
  snd = out.get("notify_sound") or ""
  if not isinstance(snd, str) or not _SOUND_RE.match(snd):
    raise ValueError("notify_sound 只能是英數字 / 空白")
  out["notify_sound"] = snd
  return out


def load_config(create: bool = True) -> dict:
  if CONFIG_PATH.exists():
    try:
      raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
      raise ValueError(f"{CONFIG_PATH.name} 不是合法 JSON: {e}") from e
    if not isinstance(raw, dict):
      raise ValueError(f"{CONFIG_PATH.name} 必須是 JSON 物件")
    return validate(raw)
  if create:
    atomic_write_text(CONFIG_PATH, json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n")
  return validate(DEFAULT_CONFIG)


def weekday_text(cfg: dict) -> str:
  wds = cfg["weekdays"]
  if wds == [0, 1, 2, 3, 4, 5, 6]:
    return "每天"
  return "週" + "、".join(_WD_ZH[w] for w in wds)


# --------------------------------------------------------------------------- #
# Schedule arithmetic
# --------------------------------------------------------------------------- #
def _launchd_weekday(d: date) -> int:
  return (d.weekday() + 1) % 7  # python Mon=0..Sun=6 → launchd Sun=0..Sat=6


def next_runs(cfg: dict, now: datetime | None = None, count: int = 3) -> list[datetime]:
  now = now or datetime.now()
  out: list[datetime] = []
  for off in range(0, 15):
    d = (now + timedelta(days=off)).date()
    if _launchd_weekday(d) not in cfg["weekdays"]:
      continue
    for t in cfg["times"]:
      hh, mm = (int(x) for x in t.split(":"))
      dt = datetime.combine(d, time(hh, mm))
      if dt > now:
        out.append(dt)
  out.sort()
  return out[:count]


def expected_latest_trading_date(now: datetime | None = None) -> date:
  """Most recent US trading day whose 16:00 ET close (+75 min settle buffer) has passed (holiday-aware)."""
  return marketclock.expected_latest_trading_date(now)


# --------------------------------------------------------------------------- #
# Run bookkeeping
# --------------------------------------------------------------------------- #
def read_last_run() -> dict | None:
  if not LAST_RUN_PATH.exists():
    return None
  try:
    data = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError):
    return None
  return data if isinstance(data, dict) else None


def write_last_run(data: dict) -> None:
  LOG_DIR.mkdir(parents=True, exist_ok=True)
  atomic_write_text(LAST_RUN_PATH, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def staleness(cfg: dict, now: datetime | None = None) -> tuple[bool, str]:
  now = now or datetime.now()
  last = read_last_run()
  if not last or last.get("status") != "ok":
    return True, "尚無成功的更新紀錄"
  try:
    fin = datetime.fromisoformat(str(last.get("finished")))
  except ValueError:
    return True, "上次紀錄的時間無法解析"
  if now - fin < timedelta(hours=3):
    return False, f"3 小時內（{fin:%m/%d %H:%M}）剛更新過"
  exp = expected_latest_trading_date(now)
  das = str(last.get("data_as_of") or "")
  if not das or das < exp.isoformat():
    return True, f"資料 {das or 'n/a'} 落後最近美股交易日 {exp.isoformat()}"
  if not last.get("data_final", True):
    return True, f"上次為 {das} 盤中快照，收盤後需重算"
  return False, f"資料已是最近交易日 {das}"


# --------------------------------------------------------------------------- #
# launchd
# --------------------------------------------------------------------------- #
def python_path() -> Path:
  venv = BASE_DIR / ".venv" / "bin" / "python"
  return venv if venv.exists() else Path(sys.executable)


def plist_path(cfg: dict) -> Path:
  return Path.home() / "Library" / "LaunchAgents" / f"{cfg['label']}.plist"


def _domain() -> str:
  return f"gui/{os.getuid()}"


def build_plist(cfg: dict) -> bytes:
  LAUNCHD_LOG_DIR.mkdir(parents=True, exist_ok=True)
  intervals = []
  for wd in cfg["weekdays"]:
    for t in cfg["times"]:
      hh, mm = (int(x) for x in t.split(":"))
      intervals.append({"Weekday": wd, "Hour": hh, "Minute": mm})
  data = {
      "Label": cfg["label"],
      "ProgramArguments": [str(python_path()), str(ENTRY), "run", "--if-stale"],
      "WorkingDirectory": str(BASE_DIR),
      "StartCalendarInterval": intervals,
      "RunAtLoad": bool(cfg["run_at_login_if_stale"]),
      "StandardOutPath": str(LAUNCHD_LOG_DIR / "launchd.out.log"),
      "StandardErrorPath": str(LAUNCHD_LOG_DIR / "launchd.err.log"),
      "EnvironmentVariables": {
          "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin",
          "LANG": "en_US.UTF-8",
          "LC_ALL": "en_US.UTF-8",
          "PYTHONUTF8": "1",
          "PYTHONUNBUFFERED": "1",
          "SOXL_TRIGGER": "launchd",
      },
      "ProcessType": "Background",
      "Nice": 5,
      "LowPriorityIO": True,
  }
  return plistlib.dumps(data, sort_keys=False)


def launchctl(*args: str) -> subprocess.CompletedProcess:
  return subprocess.run([LAUNCHCTL, *args], capture_output=True, text=True, timeout=60, check=False)


def agent_state(cfg: dict) -> dict:
  """Parse `launchctl print gui/<uid>/<label>` into a small dict."""
  res = launchctl("print", f"{_domain()}/{cfg['label']}")
  if res.returncode != 0:
    return {"loaded": False}
  info: dict = {"loaded": True}
  for line in res.stdout.splitlines():
    s = line.strip()
    for key, name in (("state = ", "state"), ("last exit code = ", "last_exit_code"), ("runs = ", "runs"), ("pid = ", "pid")):
      if s.startswith(key):
        info[name] = s[len(key):].strip()
  return info


def is_installed(cfg: dict) -> bool:
  return plist_path(cfg).exists()


def install(cfg: dict) -> dict:
  if sys.platform != "darwin":
    raise RuntimeError("launchd 排程只支援 macOS；其他系統請用 cron / Task Scheduler 執行 auto_update.py run")
  path = plist_path(cfg)
  path.parent.mkdir(parents=True, exist_ok=True)
  LOG_DIR.mkdir(parents=True, exist_ok=True)
  atomic_write_bytes(path, build_plist(cfg))
  os.chmod(path, 0o644)
  target = f"{_domain()}/{cfg['label']}"
  launchctl("bootout", target)  # ignore errors: not loaded yet
  res = launchctl("bootstrap", _domain(), str(path))
  method = "bootstrap"
  if res.returncode != 0:
    res = launchctl("load", "-w", str(path))
    method = "load -w"
  if res.returncode != 0:
    raise RuntimeError(f"launchctl {method} 失敗: {(res.stderr or res.stdout).strip()}")
  launchctl("enable", target)
  return {"plist": str(path), "method": method, "state": agent_state(cfg), "next_runs": [d.strftime("%Y-%m-%d %H:%M") for d in next_runs(cfg)]}


def uninstall(cfg: dict) -> dict:
  path = plist_path(cfg)
  target = f"{_domain()}/{cfg['label']}"
  res = launchctl("bootout", target)
  if res.returncode != 0:
    launchctl("unload", "-w", str(path))
  existed = path.exists()
  if existed:
    path.unlink()
  return {"plist": str(path), "removed": existed}


def kickstart(cfg: dict) -> subprocess.CompletedProcess:
  return launchctl("kickstart", "-k", f"{_domain()}/{cfg['label']}")


# --------------------------------------------------------------------------- #
# Notifications / open
# --------------------------------------------------------------------------- #
def notify(title: str, message: str, subtitle: str = "", sound: str | None = None) -> bool:
  if sys.platform != "darwin" or not Path(OSASCRIPT).exists():
    return False
  snd = sound if (sound and _SOUND_RE.match(sound)) else ""
  script = [
      "on run argv",
      "set theMsg to item 1 of argv",
      "set theTitle to item 2 of argv",
      "set theSub to item 3 of argv",
      "set theSound to item 4 of argv",
      "if theSound is \"\" then",
      "display notification theMsg with title theTitle subtitle theSub",
      "else",
      "display notification theMsg with title theTitle subtitle theSub sound name theSound",
      "end if",
      "end run",
  ]
  cmd = [OSASCRIPT]
  for line in script:
    cmd += ["-e", line]
  cmd += [str(message)[:220], str(title)[:90], str(subtitle)[:140], snd]
  try:
    return subprocess.run(cmd, capture_output=True, timeout=20, check=False).returncode == 0
  except (OSError, subprocess.SubprocessError):
    return False


def open_file(path: Path) -> bool:
  if sys.platform != "darwin" or not Path(OPEN).exists():
    return False
  try:
    return subprocess.run([OPEN, str(path)], capture_output=True, timeout=20, check=False).returncode == 0
  except (OSError, subprocess.SubprocessError):
    return False


# --------------------------------------------------------------------------- #
# Summary for the HTML pages
# --------------------------------------------------------------------------- #
def schedule_summary(cfg: dict | None = None) -> dict:
  try:
    cfg = cfg or load_config(create=False)
  except ValueError:
    return {"installed": False, "error": "設定檔無法解析"}
  nxt = next_runs(cfg, count=1)
  return {
      "installed": is_installed(cfg),
      "times": cfg["times"],
      "weekday_text": weekday_text(cfg),
      "next_run": nxt[0].strftime("%Y-%m-%d %H:%M") if nxt else None,
      "next_run_short": (f"{nxt[0]:%m/%d}（{_WD_ZH[_launchd_weekday(nxt[0].date())]}）{nxt[0]:%H:%M}" if nxt else None),
      "last_run": read_last_run(),
      "install_cmd": ".venv/bin/python auto_update.py install",
  }
