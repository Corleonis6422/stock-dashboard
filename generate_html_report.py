#!/usr/bin/env python3
"""Re-render both HTML pages from the existing soxl_analysis_data.json (no network).

    .venv/bin/python generate_html_report.py

Outputs: soxl_analysis_report.html (完整版) + soxl_simple.html (新手版)
"""

import json
from pathlib import Path

from soxl_quant import fsio, history, report_html, report_simple, scheduler

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
  fsio.atomic_write_text(out, report_html.render(payload))
  print(f"Rendered {out} ({out.stat().st_size / 1024:.0f} KB)")
  out2 = BASE_DIR / "soxl_simple.html"
  fsio.atomic_write_text(out2, report_simple.render(payload))
  print(f"Rendered {out2} ({out2.stat().st_size / 1024:.0f} KB)")
