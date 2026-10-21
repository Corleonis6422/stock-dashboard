#!/usr/bin/env python3
"""Re-render both HTML pages (+ index.html) and the agent feed from the existing
soxl_analysis_data.json — no model recomputation, no market-data download.

    .venv/bin/python generate_html_report.py            # HTML + feed (fetches only events / live quotes)
    .venv/bin/python generate_html_report.py --offline  # HTML + feed, zero network

Outputs: soxl_analysis_report.html (完整版) = index.html, soxl_simple.html (新手版),
         feed/latest.{json,md,txt}, feed/rss.xml, feed/<date>.{json,md}, feed/index.json
"""

import json
from pathlib import Path
import sys

from soxl_quant import fsio, history, pipeline, report_html, report_simple, scheduler

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
  payload = json.loads((BASE_DIR / "soxl_analysis_data.json").read_text(encoding="utf-8"))
  payload.setdefault("light_history", history.technical_lights((payload.get("technicals") or {}).get("chart_series") or []))
  payload["verdict_history"] = history.load(60)
  try:
    payload["schedule"] = scheduler.schedule_summary()
  except Exception as e:  # noqa: BLE001
    payload["schedule"] = {"installed": False, "error": str(e)}
  out = BASE_DIR / "soxl_analysis_report.html"
  html_text = report_html.render(payload)
  fsio.atomic_write_text(out, html_text)
  fsio.atomic_write_text(BASE_DIR / "index.html", html_text)
  print(f"Rendered {out} ({out.stat().st_size / 1024:.0f} KB) + index.html")
  out2 = BASE_DIR / "soxl_simple.html"
  fsio.atomic_write_text(out2, report_simple.render(payload))
  print(f"Rendered {out2} ({out2.stat().st_size / 1024:.0f} KB)")
  if "--no-feed" not in sys.argv:
    info = pipeline.build_feed(payload, with_quotes="--offline" not in sys.argv)
    print(f"Feed {'ok' if info.get('ok') else 'FAILED'} → {info.get('paths', {}).get('md')}" + (f"  notes: {info['notes']}" if info.get("notes") else ""))
