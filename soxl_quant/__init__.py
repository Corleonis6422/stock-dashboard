"""SOXL Quant Engine — modular quantitative analysis package.

Modules:
  datafeed       secure cached HTTPS data layer (Yahoo / CBOE / CNN F&G)
  indicators     pure technical-indicator math (SMA, EMA, RSI, KDJ, ADX, ...)
  technicals     price / volume / technical regime analysis for SOXL
  options_flow   CBOE chain analytics: P/C, walls, GEX, whale flow, forecast
  sentiment      market pulse: CNN Fear & Greed, VIX complex, CBOE P/C, flows
  macro          cross-asset correlations (10Y/30Y, Brent, VIX, DXY, HYG ...)
  heatmap        semiconductor constituents breadth & heat map
  news           daily bullish vs bearish news classification
  early_warning  crash early-warning system, event study & lessons learned
  scoring        -2 ~ +2 multi-factor scorecard
  report_html    investor-friendly HTML dashboard renderer
"""
