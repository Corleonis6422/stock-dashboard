#!/usr/bin/env python3
"""Publish the regenerated outputs to GitHub (→ GitHub Pages) after each run.

The Pages site is what remote agents pull from (``feed/latest.json`` etc.), so
every successful update commits the generated files and pushes ``main``.
Design goals: never block or break the analysis run, never prompt for
credentials, never force-push, and survive a concurrent publish from the
GitHub Actions fallback workflow (rebase, keeping our newer generated files).

Config (``auto_update_config.json`` → ``publish``):
  git_push     true/false (default true; silently skipped when the folder is not
               a git repo or has no ``origin``)
  remote       "origin"
  branch       "main"
  paths        files/dirs to stage (defaults below)
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATHS = ["soxl_analysis_data.json", "soxl_analysis_report.html", "index.html", "soxl_simple.html", "feed", "history/verdicts.jsonl", "history/snapshots"]
_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
    "HOME": str(Path.home()), "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
    "GIT_TERMINAL_PROMPT": "0",  # never hang on a credential prompt under launchd
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20",
    "GIT_EDITOR": "true",
}


def _git_bin() -> str | None:
  for cand in (shutil.which("git"), "/usr/bin/git", "/usr/local/bin/git", "/opt/homebrew/bin/git"):
    if cand and Path(cand).exists():
      return cand
  return None


def _run(git: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
  env = {**os.environ, **_ENV}
  if "SSH_AUTH_SOCK" in os.environ:
    env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
  return subprocess.run([git, *args], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=timeout, check=False, env=env)


def _tail(s: str, n: int = 240) -> str:
  s = (s or "").strip()
  return s if len(s) <= n else "…" + s[-n:]


def status() -> dict:
  git = _git_bin()
  if not git or not (BASE_DIR / ".git").exists():
    return {"git": False}
  br = _run(git, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
  head = _run(git, "rev-parse", "--short", "HEAD").stdout.strip()
  remote = _run(git, "remote", "get-url", "origin").stdout.strip()
  dirty = bool(_run(git, "status", "--porcelain", "--untracked-files=no").stdout.strip())
  ahead = "n/a"
  if remote:
    r = _run(git, "rev-list", "--count", "@{u}..HEAD")
    if r.returncode != 0:
      r = _run(git, "rev-list", "--count", f"origin/{br}..HEAD")
    if r.returncode == 0:
      ahead = r.stdout.strip() or "0"
    elif _run(git, "rev-parse", "--verify", "-q", f"origin/{br}").returncode != 0:
      ahead = "尚未推送過"
  return {"git": True, "branch": br, "head": head, "remote": remote, "dirty": dirty, "ahead": ahead}


def publish(cfg: dict | None, summary: dict | None = None) -> dict:
  """Stage → commit → (fetch + rebase) → push. Returns a status dict, never raises."""
  try:
    return _publish(cfg, summary)
  except Exception as e:  # noqa: BLE001
    return {"status": "error", "step": "internal", "detail": f"{type(e).__name__}: {e}"}


def _publish(cfg: dict | None, summary: dict | None) -> dict:
  pub = (cfg or {}).get("publish") or {}
  if pub.get("git_push") is False:
    return {"status": "disabled", "detail": "publish.git_push = false"}
  git = _git_bin()
  if not git:
    return {"status": "skipped", "detail": "找不到 git"}
  if not (BASE_DIR / ".git").exists():
    return {"status": "skipped", "detail": "此資料夾不是 git 倉庫（git init 後即可自動發佈）"}
  remote = str(pub.get("remote") or "origin")
  branch = str(pub.get("branch") or "main")
  if _run(git, "remote", "get-url", remote).returncode != 0:
    return {"status": "skipped", "detail": f"沒有名為 {remote} 的遠端"}
  paths = [p for p in (pub.get("paths") or DEFAULT_PATHS) if isinstance(p, str) and (BASE_DIR / p).exists()]
  if not paths:
    return {"status": "skipped", "detail": "沒有可發佈的輸出檔"}
  r = _run(git, "add", "-A", "--", *paths)
  if r.returncode != 0:
    return {"status": "error", "step": "add", "detail": _tail(r.stderr)}
  if _run(git, "diff", "--cached", "--quiet").returncode == 0:
    return {"status": "nochange", "detail": "輸出檔與上次 commit 相同"}
  s = summary or {}
  day = str(s.get("data_as_of") or datetime.now().strftime("%Y-%m-%d"))
  msg = " ".join(x for x in ("data:", day, f"close ${s.get('close')}" if s.get("close") is not None else "", str(s.get("emoji") or ""), str(s.get("verdict") or ""),
                             f"composite {s.get('composite')}" if s.get("composite") is not None else "", "[auto]") if x)
  r = _run(git, "-c", "user.name=soxl-quant-bot", "-c", "user.email=soxl-quant-bot@users.noreply.github.com", "commit", "-q", "-m", msg)
  if r.returncode != 0:
    return {"status": "error", "step": "commit", "detail": _tail(r.stderr or r.stdout)}
  commit = _run(git, "rev-parse", "--short", "HEAD").stdout.strip()
  # integrate anything that landed remotely (e.g. the GitHub Actions fallback run)
  f = _run(git, "fetch", "-q", remote, branch, timeout=90)
  if f.returncode == 0:
    if _run(git, "merge-base", "HEAD", f"{remote}/{branch}").returncode != 0:
      return {"status": "error", "step": "history", "commit": commit,
              "detail": f"本機與 {remote}/{branch} 沒有共同歷史；第一次請手動決定要覆蓋（git push --force）還是合併，之後自動發佈才會接手"}
    behind = _run(git, "rev-list", "--count", f"HEAD..{remote}/{branch}").stdout.strip()
    if behind and behind != "0":
      rb = _run(git, "rebase", f"{remote}/{branch}", timeout=120)
      if rb.returncode != 0:
        # generated files conflict: keep OUR (newer) versions, which are "theirs" during a rebase
        _run(git, "checkout", "--theirs", "--", *paths)
        _run(git, "add", "-A", "--", *paths)
        cont = _run(git, "rebase", "--continue", timeout=120)
        if cont.returncode != 0:
          _run(git, "rebase", "--abort")
          return {"status": "error", "step": "rebase", "commit": commit, "detail": _tail(rb.stderr or rb.stdout)}
  p = _run(git, "push", "-q", "-u", remote, f"HEAD:{branch}", timeout=180)
  if p.returncode != 0:
    return {"status": "error", "step": "push", "commit": commit, "detail": _tail(p.stderr or p.stdout),
            "hint": "若為 Permission denied (publickey)：把 ~/.ssh/id_ed25519.pub 加到 GitHub → Settings → SSH and GPG keys"}
  return {"status": "ok", "commit": _run(git, "rev-parse", "--short", "HEAD").stdout.strip(), "message": msg, "pushed_to": f"{remote}/{branch}", "paths": paths}
