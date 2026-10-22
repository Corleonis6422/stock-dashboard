#!/usr/bin/env python3
"""QA for the agent brief (feed/latest.{json,md,txt}) — run after every pipeline run.

Run: .venv/bin/python tools/qa_brief.py            (checks feed/latest.*)
     .venv/bin/python tools/qa_brief.py --strict   (untraceable numbers fail the run)

Checks
  plan invariants   stop < entry <= t1 < t2 (long side), rr values consistent with prices,
                    tradeable implies rr_blend >= min_rr, no_trade implies size.pct == 0,
                    trade_if_entry present whenever rr_blend < min_rr, invalidation non-empty
  signals           every row has p_value/q_value/base_win_pct, grades from the fixed set,
                    significant <=> p < 0.05, win rate inside its Wilson CI, A grade implies p < 0.05
  freshness         data_as_of == backtest data_as_of == history last date
  markdown shape    <= 12 KB, no raw HTML, no LaTeX, tables <= 4 columns with a header separator,
                    no line over 400 chars, required headings present, no em dashes outside quoted titles
  traceability      every numeric token in the markdown exists in latest.json (exact, 1 dp or 0 dp),
                    URLs and small counters excluded
  text              latest.txt <= 900 chars and carries the stop / T1 / T2 numbers
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FEED = BASE / "feed"
STRICT = "--strict" in sys.argv
FAILS: list[str] = []
WARNS: list[str] = []


def fail(msg: str) -> None:
  FAILS.append(msg)
  print("  FAIL", msg)


def warn(msg: str) -> None:
  WARNS.append(msg)
  print("  warn", msg)


def ok(msg: str) -> None:
  print("  ok  ", msg)


def flatten_numbers(x, out: set) -> None:
  if isinstance(x, bool):
    return
  if isinstance(x, (int, float)):
    out.add(round(float(x), 2))
  elif isinstance(x, dict):
    for v in x.values():
      flatten_numbers(v, out)
  elif isinstance(x, list):
    for v in x:
      flatten_numbers(v, out)
  elif isinstance(x, str):
    for m in NUM.finditer(x):
      try:
        out.add(round(float(m.group(0).replace("$", "").replace(",", "").replace("%", "").replace("−", "-")), 2))
      except ValueError:
        pass


NUM = re.compile(r"(?<![\w.])[+−-]?\$?\d[\d,]*(?:\.\d+)?%?")
REQUIRED_HEADINGS = ["## 交易計畫", "## 關鍵價位", "## 崩跌前兆", "## 48 小時內事件", "## 什麼會改變結論", "## 自我驗證"]


def main() -> int:
  print("qa_brief")
  br = json.loads((FEED / "latest.json").read_text(encoding="utf-8"))
  md = (FEED / "latest.md").read_text(encoding="utf-8")
  txt = (FEED / "latest.txt").read_text(encoding="utf-8")

  # ------------------------------------------------------------ schema + freshness
  if br.get("schema") != "soxl-quant-brief/2":
    fail(f"schema {br.get('schema')} != soxl-quant-brief/2")
  else:
    ok("schema v2")
  tp = br.get("trade_plan") or {}
  sigs = br.get("signals") or []
  val = br.get("validation") or {}
  if not tp or not sigs or not val:
    fail("trade_plan / signals / validation missing (backtest step failed?)")
  bt_as_of = ((val.get("method") or {}).get("data_as_of"))
  if bt_as_of and bt_as_of != br.get("data_as_of"):
    fail(f"backtest data_as_of {bt_as_of} != brief data_as_of {br.get('data_as_of')}")
  else:
    ok(f"data_as_of {br.get('data_as_of')} consistent with backtest")
  hist = br.get("history") or []
  if hist and hist[-1].get("date") != br.get("data_as_of"):
    fail(f"history last date {hist[-1].get('date')} != data_as_of")

  # ------------------------------------------------------------ plan invariants
  if tp:
    e, s, t1, t2 = (tp.get("entry") or {}).get("price"), (tp.get("stop") or {}).get("price"), (tp.get("t1") or {}).get("price"), (tp.get("t2") or {}).get("price")
    if not (s and e and t1 and t2 and s < e <= t1 < t2):
      fail(f"plan ordering stop {s} < entry {e} <= t1 {t1} < t2 {t2} violated")
    else:
      ok(f"plan ordering stop {s} < entry {e} <= T1 {t1} < T2 {t2}")
    risk = (e or 0) - (s or 0)
    for key, tgt in (("t1", t1), ("t2", t2)):
      rr_claim = (tp.get(key) or {}).get("rr")
      if risk > 0 and rr_claim is not None and abs((tgt - e) / risk - rr_claim) > 0.02:
        fail(f"{key} rr {rr_claim} inconsistent with prices ({(tgt - e) / risk:.2f})")
    blend = tp.get("rr_blend")
    if blend is not None and abs(blend - (0.5 * (tp["t1"]["rr"] + tp["t2"]["rr"]))) > 0.02:
      fail(f"rr_blend {blend} != mean of t1/t2 rr")
    if tp.get("tradeable") and (blend or 0) < (tp.get("min_rr") or 1.5):
      fail("tradeable=True but rr_blend below min_rr")
    if tp.get("side") == "no_trade" and (tp.get("size") or {}).get("pct") not in (0, 0.0):
      fail("no_trade but size.pct != 0")
    if (blend or 0) < (tp.get("min_rr") or 1.5) and tp.get("trade_if_entry") is None:
      fail("rr_blend below min_rr but trade_if_entry missing")
    if tp.get("trade_if_entry") is not None and not (s < tp["trade_if_entry"] < t1):
      fail(f"trade_if_entry {tp['trade_if_entry']} not between stop and T1")
    if not tp.get("invalidation"):
      fail("invalidation list empty")
    stop_pct = (tp.get("stop") or {}).get("dist_pct")
    if stop_pct is not None and stop_pct > -4.0:
      fail(f"stop distance {stop_pct}% tighter than 4% (3x ETF daily range)")
    ok(f"plan: side={tp.get('side')} tradeable={tp.get('tradeable')} rr_blend={blend} size={(tp.get('size') or {}).get('if_triggered_pct')}%")

  # ------------------------------------------------------------ signals
  grades = {"A", "B", "B*", "C", "—"}
  for x in sigs:
    if x.get("grade") not in grades:
      fail(f"{x.get('key')}: grade {x.get('grade')} not in {grades}")
    if (x.get("n") or 0) >= 20:
      if x.get("p_value") is None or x.get("q_value") is None or x.get("base_win_pct") is None:
        fail(f"{x.get('key')}: missing p/q/base")
      if bool(x.get("significant")) != bool(x.get("p_value") is not None and x["p_value"] < 0.05):
        fail(f"{x.get('key')}: significant flag inconsistent with p={x.get('p_value')}")
      if x.get("grade") == "A" and not x.get("significant"):
        fail(f"{x.get('key')}: grade A without significance")
      ci = x.get("ci") or []
      if len(ci) == 2 and not (ci[0] - 0.05 <= x["win_pct"] <= ci[1] + 0.05):
        fail(f"{x.get('key')}: win {x['win_pct']} outside CI {ci}")
  if sigs:
    ok(f"{len(sigs)} signals; significant {sum(1 for x in sigs if x.get('significant'))}; grades {sorted({x.get('grade') for x in sigs})}")

  # ------------------------------------------------------------ markdown shape
  size = len(md.encode())
  (ok if size <= 12 * 1024 else fail)(f"markdown {size} bytes (budget 12,288)")
  if re.search(r"<(?!https?://)[a-zA-Z/][^>]*>", md):
    fail("raw HTML tag in markdown")
  if "$$" in md or "\\frac" in md or "\\(" in md:
    fail("LaTeX in markdown")
  for h in REQUIRED_HEADINGS:
    if h not in md:
      fail(f"heading missing: {h}")
  lines = md.splitlines()
  long_lines = [l for l in lines if len(l) > 400]
  (ok if not long_lines else fail)(f"{len(long_lines)} lines over 400 chars")
  tables, cur = [], []
  for l in lines + [""]:
    if l.startswith("|"):
      cur.append(l)
    elif cur:
      tables.append(cur)
      cur = []
  for t in tables:
    cols = len(t[0].strip("|").split("|"))
    if cols > 4:
      fail(f"table with {cols} columns (max 4): {t[0][:60]}")
    if len(t) < 2 or not re.match(r"^\|(\s*:?-+:?\s*\|)+$", t[1].replace(" ", "")):
      fail(f"table without header separator: {t[0][:60]}")
  ok(f"{len(tables)} tables, all <= 4 columns" if not any(len(t[0].strip('|').split('|')) > 4 for t in tables) else "table width issue above")
  if md.count("—") > md.count("Bubble—") + 2:
    warn("em dashes present outside quoted titles")

  # ------------------------------------------------------------ traceability
  nums: set[float] = set()
  flatten_numbers(br, nums)
  n1 = {round(x, 1) for x in nums}
  n0 = {round(x, 0) for x in nums}
  untraced = []
  for l in lines:
    if "http" in l:
      continue
    for m in NUM.finditer(l):
      tok = m.group(0)
      raw = tok.replace("$", "").replace(",", "").replace("%", "").replace("−", "-")
      try:
        v = round(float(raw), 2)
      except ValueError:
        continue
      if v in nums or round(v, 1) in n1 or round(v, 0) in n0:
        continue
      if re.fullmatch(r"[+-]?\d{1,2}", raw) or re.fullmatch(r"\d{4}", raw) or re.fullmatch(r"\d{1,2}/\d{1,2}", tok) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", tok):
        continue
      untraced.append((tok, l[:60]))
  if untraced:
    (fail if STRICT else warn)(f"{len(untraced)} numbers in markdown not found in JSON, e.g. {untraced[:4]}")
  else:
    ok("every number in the markdown traces to latest.json")

  # ------------------------------------------------------------ text
  (ok if len(txt) <= 901 else fail)(f"latest.txt {len(txt)} chars (<= 900)")
  if tp:
    for v in ((tp.get("stop") or {}).get("price"), (tp.get("t1") or {}).get("price"), (tp.get("t2") or {}).get("price")):
      if v is not None and f"{v:,.2f}" not in txt:
        fail(f"latest.txt lacks plan price {v}")
  # ------------------------------------------------------------ meta pack (Muse folder)
  meta_dir = BASE / "meta"
  man_p = meta_dir / "manifest.json"
  if not man_p.exists():
    fail("meta/manifest.json missing (run auto_update.py meta)")
  else:
    man = json.loads(man_p.read_text(encoding="utf-8"))
    if man.get("data_as_of") != br.get("data_as_of"):
      fail(f"meta pack data_as_of {man.get('data_as_of')} != brief {br.get('data_as_of')}")
    missing = [f["name"] for f in man.get("files", []) if not (meta_dir / f["name"]).exists()]
    if missing:
      fail(f"meta files listed but missing: {missing}")
    body = (meta_dir / "01_brief_today.md").read_text(encoding="utf-8") if (meta_dir / "01_brief_today.md").exists() else ""
    if md.strip() not in body:
      fail("meta/01_brief_today.md does not contain feed/latest.md verbatim")
    mjson = json.loads((meta_dir / "data" / "latest.json").read_text(encoding="utf-8")) if (meta_dir / "data" / "latest.json").exists() else {}
    if mjson.get("generated_at") != br.get("generated_at"):
      fail("meta/data/latest.json is not the same build as feed/latest.json")
    wide = []
    for f in man.get("files", []):
      if f["name"].endswith(".md"):
        for l in (meta_dir / f["name"]).read_text(encoding="utf-8").splitlines():
          if l.startswith("|") and not l.startswith("|---") and len(l.strip("|").split("|")) > 4:
            wide.append(f["name"])
            break
    if wide:
      fail(f"meta tables wider than 4 columns in {wide}")
    if not FAILS or all("meta" not in f_ for f_ in FAILS):
      ok(f"meta pack: {len(man.get('files', []))} files, {man.get('total_bytes', 0) // 1024} KB, data_as_of {man.get('data_as_of')}")
  print("QA BRIEF", "FAIL" if FAILS else "PASS", f"({len(FAILS)} fail, {len(WARNS)} warn)")
  return 1 if FAILS else 0


if __name__ == "__main__":
  sys.exit(main())
