#!/usr/bin/env python3
"""SOXL Quant MCP server — lets any MCP-capable agent (Antigravity, Gemini CLI,
Claude Desktop/Code, Cursor, Muse …) pull the daily brief, live quotes, news,
events and history, or trigger a refresh.  Standard library only; stdio
transport (newline-delimited JSON-RPC 2.0, MCP protocol 2024-11-05 → 2025-06-18).

Register (prints the snippet / writes it for you):
    .venv/bin/python auto_update.py mcp-config
    .venv/bin/python auto_update.py mcp-install

Tools
  get_brief(format="markdown"|"text"|"json")   latest one-page brief
  get_latest(section=None)                      full analysis JSON or one top-level section
  get_quotes(include_leaders=True)              live quotes (Nasdaq / CBOE, ~real-time)
  get_news(days=3, max_per_day=6)               classified bull / bear headlines by day
  get_events(horizon_days=14)                   FOMC, constituent earnings, opex, holidays
  get_history(days=30)                          daily verdict log + forward returns
  get_status()                                  schedule, last run, push & publish results
  refresh(if_stale=True, wait=False)            run the pipeline (background by default)

Resources   soxl://brief/latest.md, soxl://brief/latest.json, soxl://feed/rss.xml,
            soxl://report/simple.html, soxl://report/full.html, soxl://data/full.json
Prompts     daily_briefing — "read the brief and tell me buy / sell / hold in 3 sentences"
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import traceback

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

from soxl_quant import brief as briefmod  # noqa: E402
from soxl_quant import scheduler  # noqa: E402

SERVER_INFO = {"name": "soxl-quant", "version": "1.0.0"}
SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "SOXL Quant 每日量化儀表板的資料來源。先呼叫 get_brief 取得一頁式簡報（評級、關鍵價位、情緒、消息、事件）；"
    "需要即時價格用 get_quotes；需要細節用 get_latest(section)。所有內容為自動計算的研究參考，不是投資建議。"
)
_refresh_lock = threading.Lock()
_refresh_proc: subprocess.Popen | None = None


def _log(msg: str) -> None:
  print(f"[soxl-mcp] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# tool implementations
# --------------------------------------------------------------------------- #
def _read(p: Path, limit: int | None = None) -> str:
  if not p.exists():
    raise FileNotFoundError(f"{p.name} 不存在，先執行 auto_update.py run")
  s = p.read_text(encoding="utf-8")
  return s if limit is None or len(s) <= limit else s[:limit] + f"\n…（截斷，共 {len(s)} 字元）"


def t_get_brief(args: dict) -> str:
  fmt = str(args.get("format") or "markdown").lower()
  if fmt == "json":
    return _read(briefmod.FEED_DIR / "latest.json")
  if fmt == "text":
    return _read(briefmod.FEED_DIR / "latest.txt")
  return _read(briefmod.FEED_DIR / "latest.md")


def t_get_latest(args: dict) -> str:
  p = BASE_DIR / "soxl_analysis_data.json"
  data = json.loads(_read(p))
  section = args.get("section")
  if section:
    if section not in data:
      raise KeyError(f"沒有 '{section}'；可用：{', '.join(k for k in data.keys() if not k.startswith('_'))}")
    data = data[section]
  else:
    # the full payload is ~500 KB; default to a trimmed view
    data = {k: v for k, v in data.items() if k not in ("technicals", "options", "macro", "early_warning", "heatmap", "news", "sentiment", "postmortem", "benchmarks_recent", "soxl_recent", "light_history")}
    data["_sections"] = ["technicals", "options", "sentiment", "heatmap", "macro", "early_warning", "news", "scoring", "playbook", "postmortem", "benchmarks_recent", "soxl_recent", "verdict_history", "schedule"]
    data["_hint"] = "呼叫 get_latest(section='options') 等取得完整區段"
  return json.dumps(data, ensure_ascii=False, indent=1)


def t_get_quotes(args: dict) -> str:
  from soxl_quant import quotes
  return json.dumps(quotes.snapshot(include_leaders=bool(args.get("include_leaders", True))), ensure_ascii=False, indent=1)


def t_get_news(args: dict) -> str:
  data = json.loads(_read(BASE_DIR / "soxl_analysis_data.json"))
  n = data.get("news") or {}
  days = max(1, min(int(args.get("days") or 3), 14))
  k = max(1, min(int(args.get("max_per_day") or 6), 12))
  out = {"as_of": data.get("data_as_of"), "bull_7d": n.get("recent_bull_count"), "bear_7d": n.get("recent_bear_count"), "bull_bear_ratio": n.get("bull_bear_ratio"),
         "themes_7d": (n.get("themes_7d") or [])[:8], "sources": n.get("sources"), "days": []}
  for d in (n.get("daily_feed") or [])[:days]:
    out["days"].append({"date": d.get("date"), "bull_count": d.get("bull_count"), "bear_count": d.get("bear_count"), "soxl_perf": d.get("soxl_perf"),
                        "bull": [{k2: h.get(k2) for k2 in ("time", "publisher", "title", "zh_tag", "link")} for h in (d.get("top_bull_headlines") or [])[:k]],
                        "bear": [{k2: h.get(k2) for k2 in ("time", "publisher", "title", "zh_tag", "link")} for h in (d.get("top_bear_headlines") or [])[:k]],
                        "neutral": [{k2: h.get(k2) for k2 in ("time", "publisher", "title", "link")} for h in (d.get("top_neutral_headlines") or [])[:3]]})
  return json.dumps(out, ensure_ascii=False, indent=1)


def t_get_events(args: dict) -> str:
  from soxl_quant import events
  return json.dumps(events.analyze(horizon_days=max(1, min(int(args.get("horizon_days") or 14), 60))), ensure_ascii=False, indent=1)


def t_get_history(args: dict) -> str:
  from soxl_quant import history
  return json.dumps(history.load(max(1, min(int(args.get("days") or 30), 365))), ensure_ascii=False, indent=1)


def t_get_status(_: dict) -> str:
  from soxl_quant import publish
  cfg = scheduler.load_config(create=False)
  out = {"schedule": scheduler.schedule_summary(cfg), "staleness": dict(zip(("needs_update", "why"), scheduler.staleness(cfg))), "git": publish.status(),
         "feed_base_url": cfg["feed"]["base_url"], "refresh_running": _refresh_running()}
  return json.dumps(out, ensure_ascii=False, indent=1, default=str)


def _refresh_running() -> bool:
  return _refresh_proc is not None and _refresh_proc.poll() is None


def t_refresh(args: dict) -> str:
  global _refresh_proc
  if_stale = bool(args.get("if_stale", True))
  wait = bool(args.get("wait", False))
  with _refresh_lock:
    if _refresh_running():
      return json.dumps({"started": False, "detail": "已有一次更新在跑", "log": str(scheduler.LOG_DIR / "auto_update.log")}, ensure_ascii=False)
    argv = [str(scheduler.python_path()), str(BASE_DIR / "auto_update.py"), "run"] + (["--if-stale"] if if_stale else [])
    env = {**os.environ, "SOXL_TRIGGER": "mcp", "PYTHONUTF8": "1"}
    _refresh_proc = subprocess.Popen(argv, cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
  if wait:
    try:
      rc = _refresh_proc.wait(timeout=1500)
    except subprocess.TimeoutExpired:
      return json.dumps({"started": True, "finished": False, "detail": "25 分鐘內未完成，背景繼續"}, ensure_ascii=False)
    return json.dumps({"started": True, "finished": True, "exit_code": rc, "last_run": scheduler.read_last_run()}, ensure_ascii=False, default=str)
  return json.dumps({"started": True, "finished": False, "pid": _refresh_proc.pid, "detail": "背景更新中，約 1–5 分鐘；之後再呼叫 get_brief / get_status", "log": str(scheduler.LOG_DIR / "auto_update.log")}, ensure_ascii=False)


TOOLS = [
    {"name": "get_brief", "description": "取得 SOXL 最新一頁式每日簡報（評級、綜合分數、關鍵價位、期權牆、情緒、宏觀、崩跌前兆、消息多空、近期事件、行動計畫、即時報價）。先呼叫這個。",
     "inputSchema": {"type": "object", "properties": {"format": {"type": "string", "enum": ["markdown", "text", "json"], "default": "markdown", "description": "markdown=一頁式；text=手機短訊版；json=結構化 (schema soxl-quant-brief/2：含 trade_plan / signals / validation)"}}}, "fn": t_get_brief},
    {"name": "get_latest", "description": "完整分析 JSON（soxl_analysis_data.json）。不給 section 回傳精簡總覽；給 section 名稱（technicals / options / sentiment / heatmap / macro / early_warning / news / scoring / playbook / postmortem）回傳該區段全部欄位。",
     "inputSchema": {"type": "object", "properties": {"section": {"type": "string", "description": "頂層區段名稱，可省略"}}}, "fn": t_get_latest},
    {"name": "get_quotes", "description": "即時報價快照：SOXL / SOXS / SOXX / SPY / QQQ、NVDA 等 7 檔龍頭、VIX / VIX3M / VIX9D / SKEW，含盤後價與市場狀態（Nasdaq 近即時、CBOE 延遲 15 分）。",
     "inputSchema": {"type": "object", "properties": {"include_leaders": {"type": "boolean", "default": True}}}, "fn": t_get_quotes},
    {"name": "get_news", "description": "依日期分組、已分類為利多 / 利空 / 中性的半導體新聞標題（Yahoo、Google News、Nasdaq、Seeking Alpha、CNBC、MarketWatch、Fed），附 SOXL 當日漲跌。",
     "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 3, "minimum": 1, "maximum": 14}, "max_per_day": {"type": "integer", "default": 6, "minimum": 1, "maximum": 12}}}, "fn": t_get_news},
    {"name": "get_events", "description": "未來事件：FOMC 會議（Fed 官網）、16 檔成分股財報日（Nasdaq）、週/月選擇權到期、美股休市。",
     "inputSchema": {"type": "object", "properties": {"horizon_days": {"type": "integer", "default": 14, "minimum": 1, "maximum": 60}}}, "fn": t_get_events},
    {"name": "get_history", "description": "每日評級紀錄（history/verdicts.jsonl）：日期、收盤、綜合分數、評級、倉位上限、崩跌前兆、F&G、VIX，以及之後 5 / 10 日實際報酬（自我驗證）。",
     "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 30, "minimum": 1, "maximum": 365}}}, "fn": t_get_history},
    {"name": "get_status", "description": "排程狀態、上次更新結果（含推播與 git 發佈結果）、資料是否過期、GitHub Pages 網址。",
     "inputSchema": {"type": "object", "properties": {}}, "fn": t_get_status},
    {"name": "refresh", "description": "重新抓取所有 API 並重算（約 1–5 分鐘）。預設 if_stale=true 只在資料落後最近交易日時執行；wait=false 背景執行立即回傳。",
     "inputSchema": {"type": "object", "properties": {"if_stale": {"type": "boolean", "default": True}, "wait": {"type": "boolean", "default": False}}}, "fn": t_refresh},
]
TOOL_MAP = {t["name"]: t for t in TOOLS}

RESOURCES = [
    {"uri": "soxl://brief/latest.md", "name": "SOXL 每日簡報 (Markdown)", "mimeType": "text/markdown", "path": briefmod.FEED_DIR / "latest.md"},
    {"uri": "soxl://brief/latest.json", "name": "SOXL 每日簡報 (JSON)", "mimeType": "application/json", "path": briefmod.FEED_DIR / "latest.json"},
    {"uri": "soxl://brief/latest.txt", "name": "SOXL 每日簡報 (短訊)", "mimeType": "text/plain", "path": briefmod.FEED_DIR / "latest.txt"},
    {"uri": "soxl://feed/rss.xml", "name": "SOXL 簡報 RSS", "mimeType": "application/rss+xml", "path": briefmod.FEED_DIR / "rss.xml"},
    {"uri": "soxl://feed/quotes.json", "name": "上次更新時的報價快照", "mimeType": "application/json", "path": briefmod.FEED_DIR / "quotes.json"},
    {"uri": "soxl://report/simple.html", "name": "新手版頁面", "mimeType": "text/html", "path": BASE_DIR / "soxl_simple.html"},
    {"uri": "soxl://report/full.html", "name": "完整報告頁面", "mimeType": "text/html", "path": BASE_DIR / "soxl_analysis_report.html"},
    {"uri": "soxl://data/full.json", "name": "完整分析 JSON", "mimeType": "application/json", "path": BASE_DIR / "soxl_analysis_data.json"},
    {"uri": "soxl://docs/agents.md", "name": "Agent 串接說明", "mimeType": "text/markdown", "path": BASE_DIR / "AGENTS.md"},
]
RES_MAP = {r["uri"]: r for r in RESOURCES}

PROMPTS = [
    {"name": "daily_briefing", "description": "讀取最新簡報並用三句話回答：該買 / 該賣 / 觀望、理由、要盯的價位。",
     "arguments": [{"name": "style", "description": "beginner（預設）或 pro", "required": False}]},
]


# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #
def _result(id_, result):
  return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, code: int, message: str, data=None):
  err = {"code": code, "message": message}
  if data is not None:
    err["data"] = data
  return {"jsonrpc": "2.0", "id": id_, "error": err}


def handle(msg: dict):
  method = msg.get("method")
  id_ = msg.get("id")
  params = msg.get("params") or {}
  if method == "initialize":
    want = str(params.get("protocolVersion") or SUPPORTED[0])
    ver = want if want in SUPPORTED else SUPPORTED[0]
    return _result(id_, {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}, "prompts": {"listChanged": False}},
                         "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS})
  if method in ("notifications/initialized", "notifications/cancelled", "notifications/roots/list_changed"):
    return None
  if method == "ping":
    return _result(id_, {})
  if method == "tools/list":
    return _result(id_, {"tools": [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]})
  if method == "tools/call":
    name = params.get("name")
    t = TOOL_MAP.get(name)
    if not t:
      return _error(id_, -32602, f"Unknown tool: {name}")
    try:
      text = t["fn"](params.get("arguments") or {})
      return _result(id_, {"content": [{"type": "text", "text": text}], "isError": False})
    except Exception as e:  # noqa: BLE001
      _log(f"tool {name} failed: {e}\n{traceback.format_exc()}")
      return _result(id_, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True})
  if method == "resources/list":
    return _result(id_, {"resources": [{k: r[k] for k in ("uri", "name", "mimeType")} for r in RESOURCES if r["path"].exists()]})
  if method == "resources/read":
    uri = params.get("uri")
    r = RES_MAP.get(uri)
    if not r:
      return _error(id_, -32002, f"Resource not found: {uri}")
    try:
      return _result(id_, {"contents": [{"uri": uri, "mimeType": r["mimeType"], "text": _read(r["path"])}]})
    except Exception as e:  # noqa: BLE001
      return _error(id_, -32002, str(e))
  if method == "resources/templates/list":
    return _result(id_, {"resourceTemplates": []})
  if method == "prompts/list":
    return _result(id_, {"prompts": PROMPTS})
  if method == "prompts/get":
    if params.get("name") != "daily_briefing":
      return _error(id_, -32602, f"Unknown prompt: {params.get('name')}")
    style = str((params.get("arguments") or {}).get("style") or "beginner")
    try:
      body = _read(briefmod.FEED_DIR / "latest.md")
    except FileNotFoundError as e:
      body = f"（{e}）"
    ask = ("請用新手聽得懂的話，三句以內回答：今天該買、該賣還是觀望？最重要的理由是什麼？要盯哪一個價位？直接轉述「交易計畫」表的進場觸發、停損、T1/T2 與風報比（風報比不足就說不開新倉）；提到勝率時一定連同基準與樣本數一起講。最後一行列出 48 小時內的風險事件。" if style == "beginner"
           else "請以專業交易員角度，列出：評級與信心、交易計畫（進場觸發 / 停損 / T1 / T2 / 加權風報比 / 倉位 / 失效條件）、今日觸發或待觸發的驗證訊號及其基準勝率與 p 值、關鍵支撐/壓力與期權牆、兩種 200 日線濾網的讀法、情緒與宏觀風險。")
    return _result(id_, {"description": "SOXL 每日簡報問答", "messages": [{"role": "user", "content": {"type": "text", "text": f"{ask}\n\n以下是今天自動產生的 SOXL 簡報：\n\n{body}"}}]})
  if method == "logging/setLevel":
    return _result(id_, {})
  if id_ is None:
    return None  # unknown notification: ignore
  return _error(id_, -32601, f"Method not found: {method}")


def serve() -> None:
  _log(f"serving on stdio (cwd={BASE_DIR})")
  out = sys.stdout
  for line in sys.stdin:
    line = line.strip()
    if not line:
      continue
    try:
      msg = json.loads(line)
    except json.JSONDecodeError:
      out.write(json.dumps(_error(None, -32700, "Parse error")) + "\n")
      out.flush()
      continue
    msgs = msg if isinstance(msg, list) else [msg]
    responses = []
    for m in msgs:
      if not isinstance(m, dict):
        responses.append(_error(None, -32600, "Invalid Request"))
        continue
      try:
        r = handle(m)
      except Exception as e:  # noqa: BLE001
        _log(f"handler crashed: {e}\n{traceback.format_exc()}")
        r = _error(m.get("id"), -32603, "Internal error", str(e))
      if r is not None:
        responses.append(r)
    if not responses:
      continue
    payload = responses if isinstance(msg, list) else responses[0]
    out.write(json.dumps(payload, ensure_ascii=False) + "\n")
    out.flush()
  _log("stdin closed, exiting")


if __name__ == "__main__":
  serve()
