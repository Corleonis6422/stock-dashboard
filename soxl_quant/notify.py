#!/usr/bin/env python3
"""Push the daily brief to people and agents — the 「推給我」 half.

Channels (all standard library, no SDKs):

  macos        banner via osascript (existing behaviour)
  webhook      generic HTTPS POST (JSON or plain-text body), optional bearer token and
               HMAC-SHA256 signature — point this at Muse or any agent inbox
  google_chat  Google Chat incoming webhook (text message)
  slack        Slack incoming webhook (mrkdwn text)
  discord      Discord webhook (content ≤ 1900 chars + link)
  telegram     Bot API sendMessage (HTML parse mode)
  line         LINE Messaging API push (channel access token + user/group id)
  email        SMTP (STARTTLS or SSL) with the Markdown brief as body and the two
               HTML pages attached (optional)
  agentapi     Antigravity / Jetski ``agentapi send-message`` or ``new-conversation``
               — drops the brief straight into an agent conversation on this Mac
  command      run a local executable (argv list, no shell) with placeholders
               {title} {text} {markdown} {json_path} {md_path} {html_path}; the brief
               JSON is also written to stdin — the universal adapter for any CLI agent

Configuration lives in ``notify_config.json`` next to this package (git-ignored,
chmod 600 — it holds webhook URLs and tokens).  ``notify_config.example.json`` is
the committed template.  Every value may be ``"$ENV:NAME"`` to read from the
environment instead of the file.

Security: destination hosts are validated per channel (fixed API hosts for the
named services, HTTPS-only for the generic webhook), secrets never enter logs or
the feed, and nothing here is ever interpolated into a shell.
"""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import smtplib
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import fsio, scheduler

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("SOXL_NOTIFY_CONFIG") or (BASE_DIR / "notify_config.json"))
EXAMPLE_PATH = BASE_DIR / "notify_config.example.json"
USER_AGENT = "soxl-quant-notify/1.0"
_HOSTS = {
    "google_chat": {"chat.googleapis.com"}, "slack": {"hooks.slack.com"}, "discord": {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"},
    "telegram": {"api.telegram.org"}, "line": {"api.line.me"},
}
_ENV_RE = re.compile(r"^\$ENV:([A-Z0-9_]{1,64})$")

EXAMPLE_CONFIG: dict = {
    "_readme": "複製成 notify_config.json（已在 .gitignore），把要用的頻道 enabled 改成 true 並填入網址/金鑰；任何值都可以寫 \"$ENV:VAR_NAME\" 改從環境變數讀。測試：.venv/bin/python auto_update.py push-test",
    "send_on": {"success": True, "failure": True, "only_if_verdict_changed": False},
    "channels": [
        {"type": "macos", "enabled": True, "sound": "Glass"},
        {"type": "webhook", "enabled": False, "name": "muse", "url": "https://example.com/muse/inbox", "format": "json", "bearer_token": "$ENV:MUSE_TOKEN", "hmac_secret": "", "headers": {}},
        {"type": "google_chat", "enabled": False, "url": "https://chat.googleapis.com/v1/spaces/XXXX/messages?key=...&token=..."},
        {"type": "slack", "enabled": False, "url": "https://hooks.slack.com/services/T000/B000/XXXX"},
        {"type": "discord", "enabled": False, "url": "https://discord.com/api/webhooks/000/XXXX"},
        {"type": "telegram", "enabled": False, "bot_token": "$ENV:TELEGRAM_BOT_TOKEN", "chat_id": "123456789"},
        {"type": "line", "enabled": False, "channel_access_token": "$ENV:LINE_CHANNEL_TOKEN", "to": "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"type": "email", "enabled": False, "smtp_host": "smtp.gmail.com", "smtp_port": 587, "use_ssl": False, "username": "me@gmail.com", "password": "$ENV:SMTP_APP_PASSWORD",
         "from": "me@gmail.com", "to": ["me@gmail.com"], "attach_html": True},
        {"type": "agentapi", "enabled": False, "mode": "new_conversation", "recipient_id": "", "title": "SOXL 每日簡報", "model": "",
         "prompt_prefix": "以下是今天自動產生的 SOXL 量化簡報。請先吸收全部內容，然後用三句話告訴我：今天該買、該賣還是觀望？理由是什麼？要盯哪個價位？"},
        {"type": "command", "enabled": False, "argv": ["/usr/local/bin/muse", "ingest", "--title", "{title}", "--file", "{md_path}"], "timeout_sec": 60},
    ],
}


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _resolve(v):
  if isinstance(v, str):
    m = _ENV_RE.match(v.strip())
    if m:
      return os.environ.get(m.group(1), "")
    return v
  if isinstance(v, dict):
    return {k: _resolve(x) for k, x in v.items()}
  if isinstance(v, list):
    return [_resolve(x) for x in v]
  return v


def write_example() -> Path:
  fsio.atomic_write_text(EXAMPLE_PATH, json.dumps(EXAMPLE_CONFIG, ensure_ascii=False, indent=2) + "\n")
  return EXAMPLE_PATH


def load_config(create: bool = False) -> dict:
  if not CONFIG_PATH.exists():
    if create:
      fsio.atomic_write_text(CONFIG_PATH, json.dumps(EXAMPLE_CONFIG, ensure_ascii=False, indent=2) + "\n")
      try:
        os.chmod(CONFIG_PATH, 0o600)
      except OSError:
        pass
    else:
      return {"send_on": dict(EXAMPLE_CONFIG["send_on"]), "channels": [{"type": "macos", "enabled": True, "sound": "Glass"}], "_default": True}
  try:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
  except json.JSONDecodeError as e:
    raise ValueError(f"{CONFIG_PATH.name} 不是合法 JSON: {e}") from e
  if not isinstance(raw, dict) or not isinstance(raw.get("channels"), list):
    raise ValueError(f"{CONFIG_PATH.name} 必須是物件且含 channels 陣列")
  cfg = _resolve(raw)
  cfg.setdefault("send_on", {})
  for k, v in EXAMPLE_CONFIG["send_on"].items():
    cfg["send_on"].setdefault(k, v)
  return cfg


def enabled_channels(cfg: dict) -> list[dict]:
  return [c for c in cfg.get("channels", []) if isinstance(c, dict) and c.get("enabled") and c.get("type")]


def redact(cfg: dict) -> dict:
  """Config with secrets masked (for `auto_update.py push-status`)."""
  secret_keys = {"url", "bearer_token", "hmac_secret", "bot_token", "channel_access_token", "password", "headers"}

  def mask(v):
    s = str(v)
    return "***" if len(s) <= 8 else s[:3] + "…" + s[-2:]
  out = {"send_on": cfg.get("send_on"), "config_path": str(CONFIG_PATH), "channels": []}
  for c in cfg.get("channels", []):
    out["channels"].append({k: (mask(v) if k in secret_keys and v else v) for k, v in c.items()})
  return out


# --------------------------------------------------------------------------- #
# transport helpers
# --------------------------------------------------------------------------- #
def _post(url: str, body: bytes, headers: dict[str, str], allowed_hosts: set[str] | None, timeout: int = 20) -> tuple[int, str]:
  parsed = urllib.parse.urlparse(url)
  loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
  if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
    raise ValueError("只允許 https 網址（本機 127.0.0.1 / localhost 可用 http）")
  if allowed_hosts is not None and parsed.hostname not in allowed_hosts:
    raise ValueError(f"主機 {parsed.hostname} 不在此頻道允許清單 {sorted(allowed_hosts)}")
  req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, **headers}, method="POST")
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      return resp.status, resp.read(400).decode("utf-8", "replace")
  except urllib.error.HTTPError as e:
    return e.code, e.read(400).decode("utf-8", "replace")


def _json_post(url: str, payload: dict, headers: dict[str, str], allowed_hosts: set[str] | None, timeout: int = 20) -> tuple[int, str]:
  return _post(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"), {"Content-Type": "application/json; charset=utf-8", **headers}, allowed_hosts, timeout)


def _ok(status: int) -> bool:
  return 200 <= status < 300


# --------------------------------------------------------------------------- #
# the message
# --------------------------------------------------------------------------- #
class Message:
  """One rendering of the brief that every channel can pick from."""

  def __init__(self, brief: dict, markdown: str, text: str, title: str, kind: str = "daily_brief", paths: dict | None = None):
    self.brief, self.markdown, self.text, self.title, self.kind = brief, markdown, text, title, kind
    self.paths = paths or {}

  @property
  def links(self) -> dict:
    return (self.brief or {}).get("links") or {}

  def envelope(self) -> dict:
    v = (self.brief or {}).get("verdict") or {}
    return {
        "event": f"soxl.{self.kind}", "schema": (self.brief or {}).get("schema"), "sent_at": datetime.now().isoformat(timespec="seconds"),
        "title": self.title, "text": self.text, "markdown": self.markdown,
        "summary": {"data_as_of": (self.brief or {}).get("data_as_of"), "verdict": v.get("label"), "emoji": v.get("emoji"), "composite": v.get("composite"),
                    "size_pct": v.get("size_pct"), "close": ((self.brief or {}).get("price") or {}).get("close"), "ret_1d": ((self.brief or {}).get("price") or {}).get("ret_1d")},
        "links": self.links, "brief": self.brief,
    }


# --------------------------------------------------------------------------- #
# channel senders — each returns (ok, detail)
# --------------------------------------------------------------------------- #
def send_macos(ch: dict, m: Message) -> tuple[bool, str]:
  first = m.text.splitlines()
  sub = first[0] if first else ""
  body = " ".join(first[1:3]) if len(first) > 1 else m.text
  ok = scheduler.notify(m.title, body[:220], sub[:140], ch.get("sound", "Glass"))
  return ok, "osascript ok" if ok else "osascript 失敗或非 macOS"


def send_webhook(ch: dict, m: Message) -> tuple[bool, str]:
  url = str(ch.get("url") or "")
  if not url:
    return False, "缺 url"
  headers = {str(k): str(v) for k, v in (ch.get("headers") or {}).items()}
  if ch.get("bearer_token"):
    headers["Authorization"] = f"Bearer {ch['bearer_token']}"
  fmt = str(ch.get("format") or "json").lower()
  if fmt == "text":
    body = (m.title + "\n\n" + m.markdown).encode("utf-8")
    headers["Content-Type"] = "text/markdown; charset=utf-8"
  elif fmt == "slim":
    env = m.envelope()
    env.pop("brief", None)
    body = json.dumps(env, ensure_ascii=False).encode("utf-8")
    headers["Content-Type"] = "application/json; charset=utf-8"
  else:
    body = json.dumps(m.envelope(), ensure_ascii=False).encode("utf-8")
    headers["Content-Type"] = "application/json; charset=utf-8"
  if ch.get("hmac_secret"):
    sig = hmac.new(str(ch["hmac_secret"]).encode("utf-8"), body, hashlib.sha256).hexdigest()
    headers["X-SOXL-Signature"] = f"sha256={sig}"
  headers["X-SOXL-Event"] = f"soxl.{m.kind}"
  status, resp = _post(url, body, headers, None, timeout=int(ch.get("timeout_sec") or 25))
  return _ok(status), f"HTTP {status} {resp[:120]}"


def send_google_chat(ch: dict, m: Message) -> tuple[bool, str]:
  text = f"*{m.title}*\n{m.text}\n<{m.links.get('simple_html', '')}|新手版>｜<{m.links.get('report_html', '')}|完整報告>"
  status, resp = _json_post(str(ch.get("url") or ""), {"text": text[:4000]}, {}, _HOSTS["google_chat"])
  return _ok(status), f"HTTP {status} {resp[:120]}"


def send_slack(ch: dict, m: Message) -> tuple[bool, str]:
  text = f"*{m.title}*\n{m.text}\n<{m.links.get('simple_html', '')}|新手版>｜<{m.links.get('report_html', '')}|完整報告>"
  status, resp = _json_post(str(ch.get("url") or ""), {"text": text[:3900], "unfurl_links": False}, {}, _HOSTS["slack"])
  return _ok(status), f"HTTP {status} {resp[:120]}"


def send_discord(ch: dict, m: Message) -> tuple[bool, str]:
  content = f"**{m.title}**\n{m.text}\n{m.links.get('simple_html', '')}"
  status, resp = _json_post(str(ch.get("url") or ""), {"content": content[:1900]}, {}, _HOSTS["discord"])
  return _ok(status), f"HTTP {status} {resp[:120]}"


def send_telegram(ch: dict, m: Message) -> tuple[bool, str]:
  import html as _h
  token, chat_id = str(ch.get("bot_token") or ""), str(ch.get("chat_id") or "")
  if not re.match(r"^\d{5,12}:[A-Za-z0-9_-]{30,60}$", token) or not re.match(r"^-?\d{1,20}$", chat_id):
    return False, "bot_token / chat_id 格式不正確"
  text = f"<b>{_h.escape(m.title)}</b>\n{_h.escape(m.text)}\n<a href=\"{_h.escape(m.links.get('simple_html', ''))}\">新手版</a>｜<a href=\"{_h.escape(m.links.get('report_html', ''))}\">完整報告</a>"
  status, resp = _json_post(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}, {}, _HOSTS["telegram"])
  return _ok(status), f"HTTP {status} {resp[:120]}"


def send_line(ch: dict, m: Message) -> tuple[bool, str]:
  token, to = str(ch.get("channel_access_token") or ""), str(ch.get("to") or "")
  if not token or not re.match(r"^[URC][0-9a-f]{32}$", to):
    return False, "channel_access_token / to 格式不正確（to 應為 U/R/C + 32 hex）"
  text = f"{m.title}\n{m.text}\n新手版 {m.links.get('simple_html', '')}"
  status, resp = _json_post("https://api.line.me/v2/bot/message/push", {"to": to, "messages": [{"type": "text", "text": text[:4900]}]}, {"Authorization": f"Bearer {token}"}, _HOSTS["line"])
  return _ok(status), f"HTTP {status} {resp[:120]}"


def send_email(ch: dict, m: Message) -> tuple[bool, str]:
  host, port = str(ch.get("smtp_host") or ""), int(ch.get("smtp_port") or 587)
  to = ch.get("to") or []
  to = [to] if isinstance(to, str) else [str(x) for x in to]
  if not host or not to:
    return False, "缺 smtp_host 或 to"
  msg = EmailMessage()
  msg["Subject"] = m.title
  msg["From"] = str(ch.get("from") or ch.get("username") or "")
  msg["To"] = ", ".join(to)
  msg.set_content(m.markdown)
  if ch.get("attach_html", True):
    for key in ("simple_html", "report_html"):
      p = m.paths.get(key)
      if p and Path(p).exists():
        msg.add_attachment(Path(p).read_bytes(), maintype="text", subtype="html", filename=Path(p).name)
  ctx = ssl.create_default_context()
  try:
    if ch.get("use_ssl"):
      with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as s:
        if ch.get("username"):
          s.login(str(ch["username"]), str(ch.get("password") or ""))
        s.send_message(msg)
    else:
      with smtplib.SMTP(host, port, timeout=30) as s:
        s.ehlo()
        s.starttls(context=ctx)
        if ch.get("username"):
          s.login(str(ch["username"]), str(ch.get("password") or ""))
        s.send_message(msg)
  except (smtplib.SMTPException, OSError) as e:
    return False, f"{type(e).__name__}: {e}"
  return True, f"已寄給 {len(to)} 位"


def _agentapi_bin() -> str | None:
  for cand in (shutil.which("agentapi"), str(Path.home() / ".gemini" / "jetski" / "bin" / "agentapi")):
    if cand and Path(cand).exists():
      return cand
  return None


def send_agentapi(ch: dict, m: Message) -> tuple[bool, str]:
  binp = _agentapi_bin()
  if not binp:
    return False, "找不到 agentapi（Antigravity / Jetski CLI）"
  if not os.environ.get("ANTIGRAVITY_LS_ADDRESS"):
    return False, "agentapi 只能在 Antigravity agent 的環境內使用（缺 ANTIGRAVITY_LS_ADDRESS）；排程推播請改用 sidecar：auto_update.py sidecar-install"
  prefix = str(ch.get("prompt_prefix") or "").strip()
  content = (prefix + "\n\n" if prefix else "") + m.markdown
  mode = str(ch.get("mode") or "new_conversation")
  title = str(ch.get("title") or m.title)
  if mode == "send_message":
    rid = str(ch.get("recipient_id") or "")
    if not re.match(r"^[A-Za-z0-9_\-/]{6,120}$", rid):
      return False, "send_message 需要合法 recipient_id（對話 ID）"
    argv = [binp, "send-message", f"--title={title}", rid, content]
  else:
    argv = [binp, "new-conversation", f"--title={title}"]
    if ch.get("model") in ("flash_lite", "flash", "pro"):
      argv.append(f"--model={ch['model']}")
    argv.append(content)
  try:
    r = subprocess.run(argv, capture_output=True, text=True, timeout=int(ch.get("timeout_sec") or 60), check=False)
  except (OSError, subprocess.SubprocessError) as e:
    return False, f"{type(e).__name__}: {e}"
  out = (r.stdout or r.stderr or "").strip()
  return r.returncode == 0, f"exit {r.returncode} {out[:160]}"


def send_command(ch: dict, m: Message) -> tuple[bool, str]:
  argv = ch.get("argv")
  if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
    return False, "argv 必須是字串陣列"
  subs = {"{title}": m.title, "{text}": m.text, "{markdown}": m.markdown, "{json_path}": str(m.paths.get("json", "")), "{md_path}": str(m.paths.get("md", "")),
          "{txt_path}": str(m.paths.get("txt", "")), "{html_path}": str(m.paths.get("simple_html", "")), "{report_path}": str(m.paths.get("report_html", ""))}
  final = []
  for a in argv:
    for k, v in subs.items():
      a = a.replace(k, v)
    final.append(a)
  if not Path(final[0]).exists() and not shutil.which(final[0]):
    return False, f"找不到執行檔 {final[0]}"
  try:
    r = subprocess.run(final, input=json.dumps(m.envelope(), ensure_ascii=False), capture_output=True, text=True, timeout=int(ch.get("timeout_sec") or 60), check=False, cwd=str(BASE_DIR))
  except (OSError, subprocess.SubprocessError) as e:
    return False, f"{type(e).__name__}: {e}"
  return r.returncode == 0, f"exit {r.returncode} {(r.stdout or r.stderr or '').strip()[:160]}"


SENDERS = {"macos": send_macos, "webhook": send_webhook, "google_chat": send_google_chat, "slack": send_slack, "discord": send_discord,
           "telegram": send_telegram, "line": send_line, "email": send_email, "agentapi": send_agentapi, "command": send_command}


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
def dispatch(m: Message, cfg: dict | None = None, only_types: set[str] | None = None) -> list[dict]:
  cfg = cfg or load_config()
  results = []
  for ch in enabled_channels(cfg):
    t = str(ch.get("type"))
    if only_types and t not in only_types:
      continue
    name = ch.get("name") or t
    fn = SENDERS.get(t)
    if not fn:
      results.append({"channel": name, "type": t, "ok": False, "detail": "未知頻道類型"})
      continue
    try:
      ok, detail = fn(ch, m)
    except Exception as e:  # noqa: BLE001
      ok, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
    results.append({"channel": name, "type": t, "ok": bool(ok), "detail": detail, "at": datetime.now().isoformat(timespec="seconds")})
    print(f"push {name:12s} {'OK ' if ok else 'ERR'} {detail}", file=sys.stderr)
  return results


def should_send(cfg: dict, success: bool, verdict_changed: bool | None) -> tuple[bool, str]:
  so = cfg.get("send_on") or {}
  if success and not so.get("success", True):
    return False, "send_on.success = false"
  if not success and not so.get("failure", True):
    return False, "send_on.failure = false"
  if success and so.get("only_if_verdict_changed") and verdict_changed is False:
    return False, "評級未改變（only_if_verdict_changed）"
  return True, "ok"
