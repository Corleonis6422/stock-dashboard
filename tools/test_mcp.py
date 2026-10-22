#!/usr/bin/env python3
"""Scripted MCP client: drives soxl_mcp.py over stdio exactly like an agent host would.

    .venv/bin/python tools/test_mcp.py            # full handshake + every tool / resource / prompt
    .venv/bin/python tools/test_mcp.py --refresh  # also triggers a background refresh (if stale)

Exit code 0 only if every response is well-formed and no tool returned isError.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent.parent
PY = BASE / ".venv" / "bin" / "python"
SERVER = BASE / "soxl_mcp.py"


class Client:
  def __init__(self):
    self.p = subprocess.Popen([str(PY if PY.exists() else sys.executable), str(SERVER)], cwd=str(BASE), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    self.n = 0

  def notify(self, method: str, params: dict | None = None) -> None:
    self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
    self.p.stdin.flush()

  def call(self, method: str, params: dict | None = None, timeout: float = 60) -> dict:
    self.n += 1
    self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
    self.p.stdin.flush()
    t0 = time.time()
    line = self.p.stdout.readline()
    if not line:
      raise RuntimeError(f"server closed stdout; stderr: {self.p.stderr.read()[-800:]}")
    msg = json.loads(line)
    assert msg.get("jsonrpc") == "2.0" and msg.get("id") == self.n, f"bad envelope: {line[:200]}"
    print(f"  {method:22s} {time.time() - t0:5.2f}s  {'ERROR ' + json.dumps(msg['error'], ensure_ascii=False)[:120] if 'error' in msg else 'ok'}")
    return msg

  def close(self):
    try:
      self.p.stdin.close()
      self.p.wait(timeout=10)
    except Exception:  # noqa: BLE001
      self.p.kill()


def main() -> int:
  fails = 0
  c = Client()
  try:
    r = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
    assert r["result"]["protocolVersion"] == "2025-06-18" and r["result"]["serverInfo"]["name"] == "soxl-quant"
    c.notify("notifications/initialized")
    assert c.call("ping")["result"] == {}
    tools = c.call("tools/list")["result"]["tools"]
    names = [t["name"] for t in tools]
    print("  tools:", names)
    assert {"get_brief", "get_latest", "get_quotes", "get_news", "get_events", "get_history", "get_status", "refresh"} <= set(names)
    for t in tools:
      assert t["inputSchema"]["type"] == "object"
    checks = [
        ("get_brief", {}, lambda s: s.startswith("# SOXL ") and "## 交易計畫" in s),
        ("get_brief", {"format": "text"}, lambda s: "SOXL" in s and len(s) < 1200),
        ("get_brief", {"format": "json"}, lambda s: json.loads(s)["schema"] == "soxl-quant-brief/2"),
        ("get_latest", {}, lambda s: "_sections" in json.loads(s)),
        ("get_latest", {"section": "options"}, lambda s: "put_wall" in json.loads(s)),
        ("get_news", {"days": 2, "max_per_day": 3}, lambda s: len(json.loads(s)["days"]) >= 1),
        ("get_events", {"horizon_days": 14}, lambda s: "events" in json.loads(s)),
        ("get_history", {"days": 10}, lambda s: isinstance(json.loads(s), list)),
        ("get_status", {}, lambda s: "schedule" in json.loads(s)),
        ("get_quotes", {"include_leaders": False}, lambda s: json.loads(s).get("soxl") is not None),
    ]
    for name, args, ok in checks:
      r = c.call("tools/call", {"name": name, "arguments": args}, timeout=120)
      res = r.get("result") or {}
      txt = (res.get("content") or [{}])[0].get("text", "")
      good = (not res.get("isError")) and ok(txt)
      print(f"     → {name}{json.dumps(args, ensure_ascii=False)}: {'PASS' if good else 'FAIL'} ({len(txt)} chars) {txt[:90]!r}")
      fails += 0 if good else 1
    # error path
    r = c.call("tools/call", {"name": "get_latest", "arguments": {"section": "nope"}})
    assert r["result"]["isError"] is True
    r = c.call("tools/call", {"name": "does_not_exist"})
    assert "error" in r and r["error"]["code"] == -32602
    r = c.call("no/such/method")
    assert r["error"]["code"] == -32601
    res = c.call("resources/list")["result"]["resources"]
    print("  resources:", [x["uri"] for x in res])
    assert any(x["uri"] == "soxl://brief/latest.md" for x in res)
    r = c.call("resources/read", {"uri": "soxl://brief/latest.json"})
    assert json.loads(r["result"]["contents"][0]["text"])["schema"] == "soxl-quant-brief/2"
    pr = c.call("prompts/list")["result"]["prompts"]
    assert pr[0]["name"] == "daily_briefing"
    r = c.call("prompts/get", {"name": "daily_briefing", "arguments": {"style": "beginner"}})
    assert "SOXL 簡報" in r["result"]["messages"][0]["content"]["text"] and "## 交易計畫" in r["result"]["messages"][0]["content"]["text"]
    if "--refresh" in sys.argv:
      r = c.call("tools/call", {"name": "refresh", "arguments": {"if_stale": True, "wait": False}})
      print("     → refresh:", (r["result"]["content"][0]["text"])[:160])
  except AssertionError as e:
    fails += 1
    print("ASSERTION FAILED:", e)
  except Exception as e:  # noqa: BLE001
    fails += 1
    print("ERROR:", type(e).__name__, e)
  finally:
    c.close()
  print("MCP TEST", "PASS" if fails == 0 else f"FAIL ({fails})")
  return 0 if fails == 0 else 1


if __name__ == "__main__":
  sys.exit(main())
