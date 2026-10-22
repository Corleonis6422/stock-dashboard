#!/usr/bin/env python3
"""Unit test: Nasdaq quote blocks must never swap regular vs extended prices.

Payload shapes recorded from api.nasdaq.com on 2026-10-22 (pre-market, 9:09 AM ET) plus the other
states Nasdaq serves (after hours, regular, fully closed, legacy prefixed timestamps).
Run: .venv/bin/python tests/test_quote_labels.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from soxl_quant.datafeed import _classify_quote_blocks  # noqa: E402

PRE_MARKET_RECORDED = {  # verbatim shape from the live probe (values rounded)
    "marketStatus": "Pre-Market",
    "primaryData": {"lastSalePrice": "$90.07", "netChange": "-13.17", "percentageChange": "-12.76%", "lastTradeTimestamp": "Oct 22, 2026 9:09 AM ET", "isRealTime": True},
    "secondaryData": {"lastSalePrice": "$103.24", "netChange": "+5.69", "percentageChange": "+5.83%", "lastTradeTimestamp": "Closed at Oct 21, 2026 4:00 PM ET", "isRealTime": False},
}
PRE_MARKET_LEGACY = {
    "marketStatus": "Pre-Market",
    "primaryData": {"lastSalePrice": "$92.18", "percentageChange": "-10.71%", "lastTradeTimestamp": "PRE-MARKET: Oct 22, 2026 8:24 AM ET"},
    "secondaryData": {"lastSalePrice": "$103.24", "percentageChange": "+5.99%", "lastTradeTimestamp": "CLOSED AT 4:00 PM ET ON Oct 21, 2026"},
}
AFTER_HOURS = {
    "marketStatus": "After-Hours",
    "primaryData": {"lastSalePrice": "$103.24", "percentageChange": "+5.83%", "lastTradeTimestamp": "Closed at Oct 21, 2026 4:00 PM ET"},
    "secondaryData": {"lastSalePrice": "$101.90", "percentageChange": "-1.30%", "lastTradeTimestamp": "Oct 21, 2026 7:59 PM ET"},
}
REGULAR = {
    "marketStatus": "Open",
    "primaryData": {"lastSalePrice": "$98.10", "percentageChange": "-4.98%", "lastTradeTimestamp": "Oct 22, 2026 10:15 AM ET"},
    "secondaryData": None,
}
CLOSED_WEEKEND = {
    "marketStatus": "Closed",
    "primaryData": {"lastSalePrice": "$103.24", "percentageChange": "+5.83%", "lastTradeTimestamp": "Closed at Oct 21, 2026 4:00 PM ET"},
    "secondaryData": {"lastSalePrice": "", "percentageChange": "", "lastTradeTimestamp": ""},
}


class QuoteLabels(unittest.TestCase):
  def test_pre_market_recorded_shape(self):
    b = _classify_quote_blocks(PRE_MARKET_RECORDED)
    self.assertEqual(b["regular"]["lastSalePrice"], "$103.24")
    self.assertEqual(b["extended"]["lastSalePrice"], "$90.07")
    self.assertEqual(b["ext_kind"], "pre")

  def test_pre_market_legacy_prefix(self):
    b = _classify_quote_blocks(PRE_MARKET_LEGACY)
    self.assertEqual(b["regular"]["lastSalePrice"], "$103.24")
    self.assertEqual(b["extended"]["lastSalePrice"], "$92.18")
    self.assertEqual(b["ext_kind"], "pre")

  def test_after_hours(self):
    b = _classify_quote_blocks(AFTER_HOURS)
    self.assertEqual(b["regular"]["lastSalePrice"], "$103.24")
    self.assertEqual(b["extended"]["lastSalePrice"], "$101.90")
    self.assertEqual(b["ext_kind"], "post")

  def test_regular_hours(self):
    b = _classify_quote_blocks(REGULAR)
    self.assertEqual(b["regular"]["lastSalePrice"], "$98.10")
    self.assertIsNone(b["extended"])
    self.assertIsNone(b["ext_kind"])

  def test_closed_weekend(self):
    b = _classify_quote_blocks(CLOSED_WEEKEND)
    self.assertEqual(b["regular"]["lastSalePrice"], "$103.24")
    self.assertIsNone(b["extended"])


if __name__ == "__main__":
  unittest.main(verbosity=2)
