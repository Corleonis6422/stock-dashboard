#!/usr/bin/env python3
"""End-to-end push test without any external service.

Spins up a local HTTP inbox (what a Muse / agent webhook would be), points a
temporary notify config at it (webhook json + hmac, webhook text, slim, and a
`command` channel), dispatches the real latest brief, then verifies: request
count, JSON envelope shape, HMAC-SHA256 signature, bearer header, text format,
command stdin payload, and that send_on policies are honoured.

    .venv/bin/python tools/test_push.py
"""

from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from soxl_quant import brief as briefmod  # noqa: E402
from soxl_quant import notify  # noqa: E402

RECEIVED: list[dict] = []
SECRET = "test-secret-123"


class Inbox(BaseHTTPRequestHandler):
  def do_POST(self):  # noqa: N802
    n = int(self.headers.get("Content-Length") or 0)
    body = self.rfile.read(n)
    RECEIVED.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
    code = 500 if self.path == "/fail" else 200
    self.send_response(code)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(b'{"ok":true}' if code == 200 else b'{"ok":false}')

  def log_message(self, *a):  # silence
    pass


def main() -> int:
  srv = HTTPServer(("127.0.0.1", 0), Inbox)
  port = srv.server_address[1]
  threading.Thread(target=srv.serve_forever, daemon=True).start()
  tmp = Path(tempfile.mkdtemp())
  sink = tmp / "cmd_stdin.json"
  cmd_script = tmp / "sink.py"
  cmd_script.write_text(f"import sys,json,pathlib\nd=json.load(sys.stdin)\npathlib.Path({str(sink)!r}).write_text(json.dumps({{'title': sys.argv[1], 'md_path': sys.argv[2], 'event': d['event'], 'has_brief': 'brief' in d}}))\nprint('ingested')\n", encoding="utf-8")
  os.environ["TEST_BEARER"] = "bearer-xyz"
  cfg = {
      "send_on": {"success": True, "failure": True, "only_if_verdict_changed": False},
      "channels": [
          {"type": "webhook", "enabled": True, "name": "muse-json", "url": f"http://127.0.0.1:{port}/muse", "format": "json", "hmac_secret": SECRET, "bearer_token": "$ENV:TEST_BEARER", "headers": {"X-Test": "1"}},
          {"type": "webhook", "enabled": True, "name": "muse-text", "url": f"http://127.0.0.1:{port}/text", "format": "text"},
          {"type": "webhook", "enabled": True, "name": "muse-slim", "url": f"http://127.0.0.1:{port}/slim", "format": "slim"},
          {"type": "webhook", "enabled": True, "name": "broken", "url": f"http://127.0.0.1:{port}/fail", "format": "json"},
          {"type": "webhook", "enabled": False, "name": "disabled", "url": f"http://127.0.0.1:{port}/never"},
          {"type": "webhook", "enabled": True, "name": "bad-scheme", "url": "http://example.com/not-loopback"},
          {"type": "slack", "enabled": True, "url": f"http://127.0.0.1:{port}/slack-wrong-host"},
          {"type": "command", "enabled": True, "argv": [sys.executable, str(cmd_script), "{title}", "{md_path}"]},
      ],
  }
  cfg_path = tmp / "notify_config.json"
  cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
  notify.CONFIG_PATH = cfg_path  # point the loader at the temp config
  loaded = notify.load_config()
  assert loaded["channels"][0]["bearer_token"] == "bearer-xyz", "$ENV: resolution failed"

  br = briefmod.load_latest()
  assert br, "feed/latest.json missing — run auto_update.py feed first"
  md = (briefmod.FEED_DIR / "latest.md").read_text(encoding="utf-8")
  m = notify.Message(br, md, briefmod.to_text(br), "SOXL test title", "daily_brief", {"json": str(briefmod.FEED_DIR / "latest.json"), "md": str(briefmod.FEED_DIR / "latest.md")})
  results = notify.dispatch(m, loaded)
  by = {r["channel"]: r for r in results}
  fails = 0

  def check(cond: bool, what: str):
    nonlocal fails
    print(f"  {'PASS' if cond else 'FAIL'}  {what}")
    fails += 0 if cond else 1

  check(by["muse-json"]["ok"], "webhook json delivered")
  check(by["muse-text"]["ok"], "webhook text delivered")
  check(by["muse-slim"]["ok"], "webhook slim delivered")
  check(not by["broken"]["ok"] and "500" in by["broken"]["detail"], "HTTP 500 reported as failure")
  check("disabled" not in by, "disabled channel skipped")
  check(not by["bad-scheme"]["ok"] and "https" in by["bad-scheme"]["detail"], "non-loopback http rejected")
  check(not by["slack"]["ok"] and "允許清單" in by["slack"]["detail"], "slack host allow-list enforced")
  check(by["command"]["ok"] and "ingested" in by["command"]["detail"], "command channel ran")
  rx = {r["path"]: r for r in RECEIVED}
  check(set(rx) == {"/muse", "/text", "/slim", "/fail"}, f"inbox saw exactly the expected requests {sorted(rx)}")
  j = rx["/muse"]
  env = json.loads(j["body"])
  sig = "sha256=" + hmac.new(SECRET.encode(), j["body"], hashlib.sha256).hexdigest()
  check(j["headers"].get("x-soxl-signature") == sig, "HMAC signature valid")
  check(j["headers"].get("authorization") == "Bearer bearer-xyz", "bearer header present")
  check(j["headers"].get("x-test") == "1" and j["headers"].get("x-soxl-event") == "soxl.daily_brief", "custom + event headers present")
  check(env["event"] == "soxl.daily_brief" and env["brief"]["schema"] == "soxl-quant-brief/2" and env["summary"]["verdict"], "json envelope shape")
  check(rx["/text"]["headers"].get("content-type", "").startswith("text/markdown") and rx["/text"]["body"].decode().startswith("SOXL test title"), "text format body")
  slim = json.loads(rx["/slim"]["body"])
  check("brief" not in slim and slim["text"], "slim format omits full brief")
  cmd = json.loads(sink.read_text())
  check(cmd["title"] == "SOXL test title" and cmd["md_path"].endswith("latest.md") and cmd["has_brief"], "command received argv placeholders + stdin envelope")
  # policies
  check(notify.should_send(loaded, True, False) == (True, "ok"), "default policy sends")
  check(notify.should_send({"send_on": {"only_if_verdict_changed": True}}, True, False)[0] is False, "only_if_verdict_changed suppresses unchanged")
  check(notify.should_send({"send_on": {"failure": False}}, False, None)[0] is False, "failure=false suppresses failure push")
  red = notify.redact(loaded)
  check(SECRET not in json.dumps(red) and "bearer-xyz" not in json.dumps(red), "redact masks secrets")
  srv.shutdown()
  print("PUSH TEST", "PASS" if fails == 0 else f"FAIL ({fails})")
  return 0 if fails == 0 else 1


if __name__ == "__main__":
  sys.exit(main())
