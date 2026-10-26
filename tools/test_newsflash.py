#!/usr/bin/env python3
"""Offline tests for soxl_quant.newsflash (no network): classification, flags, ranking."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soxl_quant import newsflash  # noqa: E402

NOW = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)  # 12:00 Taipei

CASES = [
    # (title, expected category, expected impact)
    ("Futures are getting crushed after Trump said the U.S. is not negotiating with Iran", "地緣政治", -2),
    ("Iran Plots, Houthi Attacks Spur US Departure Orders in Mideast", "地緣政治", -2),
    ("Iran and US agree to ceasefire, oil falls 5%", "地緣政治", 2),
    ("Israel, Hamas reach a deal after weeks of strikes", "地緣政治", -1),
    ("White House lifts tariffs on some Canadian goods as midterm elections loom", "政策與關稅", 1),
    ("Tracking Trump: Trump rolls back Canada tariffs; Hegseth bans insiders", "政策與關稅", 0),
    ("Trump threatens 100% tariffs on chips made abroad", "政策與關稅", -2),
    ("US imposes new export controls on Nvidia chips to China", "政策與關稅", -2),
    ("Federal Reserve issues FOMC statement", "聯準會與利率", 0),
    ("Fed cuts rates by a quarter point, signals pause", "聯準會與利率", 2),
    ("Powell says Fed is in no hurry, pushes back on rate cut hopes", "聯準會與利率", 0),
    ("Fed's Waller: higher for longer is the base case", "聯準會與利率", -1),
    ("Nvidia beats estimates, raises guidance on record revenue", "半導體與 AI", 2),
    ("Microsoft earnings: capex cut spooks AI trade", "半導體與 AI", -1),
    ("Investors piled a record sum into a leveraged semiconductor ETF last week. Things didn't work out", "半導體與 AI", -1),
    ("Nvidia's Huang reveals investment in AI video unicorn Higgsfield", "半導體與 AI", 1),
    ("CPI comes in hotter than expected, yields jump", "經濟數據", -2),
    ("Inflation cools in September, yields fall", "經濟數據", 2),
    ("U.S. Stocks Fall as Credit Fears Haunt Tech Sector", "市場波動", -2),
    ("Dow jumps 500 points as stocks rebound", "市場波動", 2),
    # false-positive guards (whole-word matching)
    ("Software stocks rally on cloud demand", "市場波動", 1),            # "war" must not match "software"
    ("Housing market cools down in October", None, 0),                  # "dow" must not match "down"
    ("India's Bharat Petroleum profit drops amid crude oil price volatility", None, 0),
    ("Terrorism charges filed after attack on mall", "地緣政治", -2),    # "ism" must not trigger 經濟數據 first
    ("Photo essay: hot summer in Spain", None, 0),
]


def test_classify() -> int:
  bad = 0
  for title, cat, imp in CASES:
    got = newsflash.classify(title)
    ok = got == (cat, imp)
    bad += not ok
    print(("PASS" if ok else "FAIL"), got, "| expected", (cat, imp), "|", title[:80])
  return bad


def _item(title, age_h, publisher="Reuters", source="google:x"):
  return {"title": title, "publisher": publisher, "link": "https://example.com/" + str(abs(hash(title))), "timestamp": NOW.timestamp() - age_h * 3600, "source": source}


def test_analyze() -> int:
  raw = [
      _item("Futures are getting crushed after Trump said the U.S. is not negotiating with Iran", 3, "Bloomberg"),
      _item("Futures are getting crushed after Trump said the U.S. is not negotiating with Iran", 2, "Some Blog"),  # duplicate, lower weight
      _item("Iran and US agree to ceasefire, oil falls 5%", 30, "Reuters"),
      _item("Trump threatens 100% tariffs on chips made abroad", 5, "CNBC"),
      _item("Microsoft earnings: capex cut spooks AI trade", 6, "WSJ"),
      _item("Federal Reserve issues FOMC statement", 4, "", "fed_press"),
      _item("Fed's Waller: higher for longer is the base case", 7, "Reuters"),
      _item("Nvidia beats estimates, raises guidance on record revenue", 8, "Reuters"),
      _item("Dow jumps 500 points as stocks rebound", 9, "AP News"),
      _item("U.S. Stocks Fall as Credit Fears Haunt Tech Sector", 10, "WSJ"),
      _item("Old news: Iran strikes Israel", 60, "Reuters"),             # outside window
      _item("Random recipe of the day", 1, "Reuters"),                   # no category
      _item("Trump threatens new tariffs on EU wine", 20, "Small Site"),  # weight 0.48, must not drive a flag
  ]
  f = newsflash.analyze(now=NOW, raw=raw)
  bad = 0

  def check(cond, msg):
    nonlocal bad
    print(("PASS" if cond else "FAIL"), msg)
    bad += not cond

  check(f["n_relevant"] == 10, f"n_relevant 10 (got {f['n_relevant']})")
  check(f["top"][0]["title"].startswith("Futures are getting crushed"), "top1 is the Iran headline")
  check(f["top"][0]["publisher"] == "Bloomberg", "dedupe keeps the heavier publisher")
  check(len(f["top"]) <= newsflash.TOP_N, "top size")
  cats = {}
  for r in f["top"]:
    cats[r["category"]] = cats.get(r["category"], 0) + 1
  check(max(cats.values()) <= newsflash.PER_CATEGORY, "≤ 2 per category in top")
  check(f["flags"]["geo_escalation_24h"] is True, "geo flag on")
  check(f["flags"]["tariff_shock_24h"] is True, "tariff flag on (CNBC headline)")
  check(f["flags"]["capex_warning_24h"] is True, "capex flag on")
  check(f["flags"]["fed_statement_24h"] is True, "fed statement flag on")
  check(f["flags"]["fed_hawkish_24h"] is True, "fed hawkish flag on")
  check(f["flag_evidence"]["tariff_shock_24h"]["publisher"] == "CNBC", "tariff evidence is the weighted source")
  check(all(c["evidence"]["title"] for c in f["cautions"]), "every caution carries evidence")
  check(f["label"] in ("偏空", "中性", "偏多"), "label")
  check("今天最大的事" in f["beginner_line"], "beginner line")
  check(all(k in f for k in ("top", "more", "by_category", "flags", "cautions", "method", "errors")), "keys")
  empty = newsflash.analyze(now=NOW, raw=[])
  check(empty["top"] == [] and "沒有抓到" in empty["beginner_line"], "empty input handled")
  return bad


if __name__ == "__main__":
  bad = test_classify() + test_analyze()
  print("newsflash tests:", "ALL PASS" if bad == 0 else f"{bad} FAILED")
  sys.exit(1 if bad else 0)
