#!/usr/bin/env python3
"""Offline tests for soxl_quant.agent_pack: the operator runbook must be complete, consistent and secret-free."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soxl_quant import agent_pack  # noqa: E402

BAD = 0


def check(cond, msg):
  global BAD
  print(("PASS" if cond else "FAIL"), msg)
  BAD += not cond


br = {"data_as_of": "2026-10-23", "generated_at": "2026-10-26 19:51:41", "schema": "soxl-quant-brief/2", "verdict": {"label": "賣出 / 減碼"}, "trade_plan": {"side": "no_trade"}}
with tempfile.TemporaryDirectory() as td:
  fake_zip = Path(td) / "stock-dashboard_repo_2026-10-23.zip"
  fake_zip.write_bytes(b"0" * 2048)
  docs = agent_pack.build_docs(br, "https://example.github.io/stock-dashboard/", fake_zip)

check(set(docs) == {"README.md", "APIS.md", "apis.json", "RUNBOOK.json"}, f"four documents {sorted(docs)}")
readme = docs["README.md"]
for h in ("## 0. 事實", "## 1. 判斷你的能力", "## 2. 路徑 A", "## 3. 推完之後", "## 4. API 全圖", "### 4.1", "### 4.2", "### 4.3", "## 5. 你的每日迴圈", "## 6. 驗收清單", "## 7. 故障排除", "## 8. 安全邊界", "## English operator brief"):
  check(h in readme, f"README has section {h}")
check("git push origin main" in readme and "git rebase origin/main" in readme and "push --force" not in readme and "git ls-remote origin refs/heads/main" in readme, "README has the rebase+push flow, no force-push, and the verification command")
check("https://example.github.io/stock-dashboard/meta/manifest.json" in readme, "README uses the configured base URL")
check("stock-dashboard_repo_2026-10-23.zip" in readme and "2026-10-23" in readme, "README names the repo zip and the data day")
check("SOXL_NOTIFY_CONFIG_JSON" in readme and "SOXL_NOTIFY_CONFIG`" not in readme.replace("SOXL_NOTIFY_CONFIG_JSON", ""), "README uses the JSON secret name (the bare name is a file path in notify.py)")
check("beginner.buy.answer" in readme and "dashboard.one_liner" in readme and "trade_plan.stop.price" in readme.replace(".stop.price", "trade_plan.stop.price"), "README names the JSON paths the agent reads")
check("$ENV:" in readme and "ghp_" not in readme and "sk-" not in readme, "README references env tokens only, no literal secrets")

apis = json.loads(docs["apis.json"])["apis"]
layers = {a["layer"] for a in apis}
check({"upstream", "publish", "delivery", "local", "github"} <= layers, f"api layers {sorted(layers)}")
check(all(a.get("url") and a.get("auth") and a.get("used_by") and a.get("on_failure") and "test" in a for a in apis), "every api row has url / auth / used_by / on_failure / test")
check(sum(1 for a in apis if a["layer"] == "upstream") >= 18, f"{sum(1 for a in apis if a['layer'] == 'upstream')} upstream sources listed")
check(all(a["auth"].startswith("none") for a in apis if a["layer"] == "upstream"), "all upstream sources are keyless")
check(any("seekingalpha" in a["id"] for a in apis) and any("google_news" in a["id"] for a in apis), "Seeking Alpha and Google News are in the inventory")
pub = [a for a in apis if a["layer"] == "publish"]
check(all(a["url"].startswith("https://example.github.io/stock-dashboard/") for a in pub), "published endpoints use the base URL")

rb = json.loads(docs["RUNBOOK.json"])
check(len(rb["steps_A"]) >= 10 and all(s.get("run") and s.get("expect") and s.get("on_fail") for s in rb["steps_A"]), "every publish step has run / expect / on_fail")
check([s["id"] for s in rb["steps_A"]][:3] == ["A1", "A2", "A3"] and rb["steps_A"][0]["expect"].split()[0] == rb["facts"]["git"]["head"], "A1 expects the measured HEAD")
check(any("rebase" in s["run"] for s in rb["steps_A"]) and all("--force" not in s["run"] for s in rb["steps_A"]) and any("ls-remote" in s["run"] for s in rb["steps_A"]), "runbook rebases then pushes normally (no force) and verifies")
check(len(rb["steps_C"]) >= 3 and len(rb["acceptance"]) >= 5, "daily loop and acceptance present")
check(rb["facts"]["github"]["pages_base_url"] == "https://example.github.io/stock-dashboard/" and rb["facts"]["repo_zip_bytes"] == 2048, "facts carry base URL and zip size")
check("README.md" in docs and len(readme.encode()) < 60 * 1024, f"README size {len(readme.encode()) // 1024} KB")
print("agent_pack tests:", "ALL PASS" if BAD == 0 else f"{BAD} FAILED")
sys.exit(1 if BAD else 0)
