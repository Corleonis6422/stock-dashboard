#!/usr/bin/env python3
"""SOXL Quant Playbook — entry point.

Usage (from this folder, using the project virtualenv):
    .venv/bin/python analyze_soxl.py              # fetch (cached 6h) → analyze → JSON + HTML
    .venv/bin/python analyze_soxl.py --refresh    # clear cache and re-download everything
    .venv/bin/python analyze_soxl.py --no-html    # JSON only

Outputs (same folder):
    soxl_analysis_data.json     structured results for every module
    soxl_analysis_report.html   investor dashboard (open in any browser)

The analytics live in the `soxl_quant/` package:
    datafeed      secure, cached, rate-limit-aware data layer (Nasdaq / CBOE / CNN / Treasury / Yahoo / Google News)
    technicals    data-driven technical regime (MA, MACD, KD, RSI, ADX, Ichimoku, Bollinger, Fibonacci ...)
    options_flow  CBOE chain: P/C, walls, GEX & gamma flip, whale vs retail flow, options-implied forecast
    sentiment     CNN Fear & Greed, VIX family (VIX/9D/3M/VVIX/SKEW), CBOE P/C, SOXL/SOXS flows, Market Pulse
    heatmap       16 constituents breadth / heat map
    macro         10Y/30Y Treasury, Brent, VIX, DXY, HYG, gold, copper, BTC correlations
    early_warning crash early-warning system, event study, historical analogs
    scoring       7-dimension -2..+2 scorecard with trend vs contrarian sub-scores
    playbook      next-step verdict, price ladder, scenarios, re-entry checklist
    postmortem    lessons learned from the most recent major drawdown
    report_html   dashboard renderer
"""

import sys

from soxl_quant.pipeline import run

if __name__ == "__main__":
  run(write_html="--no-html" not in sys.argv, refresh="--refresh" in sys.argv)
