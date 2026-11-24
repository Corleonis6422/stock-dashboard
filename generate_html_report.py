#!/usr/bin/env python3
"""Re-render the viewer page and the agent feed from the existing
soxl_analysis_data.json — no model recomputation, no market-data download.

    .venv/bin/python generate_html_report.py            # HTML + feed (fetches only events / live quotes)
    .venv/bin/python generate_html_report.py --offline  # HTML + feed, zero network

Outputs: the one page under its three names (index.html = soxl_analysis_report.html = soxl_simple.html),
         feed/latest.{json,md,txt}, feed/rss.xml, feed/<date>.{json,md}, feed/index.json
"""

import json
from pathlib import Path
import sys

from soxl_quant import history, pipeline, report_page, scheduler

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
  payload = json.loads((BASE_DIR / "soxl_analysis_data.json").read_text(encoding="utf-8"))
  payload.setdefault("light_history", history.technical_lights((payload.get("technicals") or {}).get("chart_series") or []))
  payload["verdict_history"] = history.load(60)
  try:
    payload["schedule"] = scheduler.schedule_summary()
  except Exception as e:  # noqa: BLE001
    payload["schedule"] = {"installed": False, "error": str(e)}
  pages = report_page.write_pages(payload, BASE_DIR)
  print(f"Rendered {pages[0]} ({pages[0].stat().st_size / 1024:.0f} KB) = " + " = ".join(q.name for q in pages[1:]))
  if "--no-feed" not in sys.argv:
    info = pipeline.build_feed(payload, with_quotes="--offline" not in sys.argv)
    print(f"Feed {'ok' if info.get('ok') else 'FAILED'} → {info.get('paths', {}).get('md')}" + (f"  notes: {info['notes']}" if info.get("notes") else ""))
