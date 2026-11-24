#!/usr/bin/env python3
"""Tests for the SOXL_OFFLINE replay switch in soxl_quant/datafeed.py — no network, temporary cache only.

Run: python3 tools/test_offline.py

The real ``.cache/`` is never used: the module is pointed at a temporary directory, and
``urllib.request.urlopen`` is replaced by a fake for the whole run, so no request can leave the machine.

Covers
  1. flag parsing: 1 / true / yes / anything → offline; unset / empty / 0 / false / no / off → online; read per call
  2. offline: no network request (urlopen is never reached) and the FeedError carries the URL
  3. offline: a cached response is served whatever its age, through the raw cache and through a public fetcher
  4. offline: the cache is never written, also not by the "remember this miss" writes, and never cleared
  5. offline: an uncached source degrades the way a failed fetch does (FeedError, or the fetcher's empty value)
  6. offline: a refresh request to the pipeline clears nothing
  7. online: the TTL is honoured, the cache is written and cleared, and a request reaches urlopen (behaviour unchanged)
  8. import: an offline import does not create the cache directory, an online import does
  9. the real cache directory is untouched by this test
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REAL_CACHE = REPO / ".cache"
os.environ["SOXL_OFFLINE"] = "1"  # import in offline mode: the import itself must not touch the real cache
sys.path.insert(0, str(REPO))
from soxl_quant import datafeed  # noqa: E402
from soxl_quant import pipeline  # noqa: E402

FAILS: list[str] = []
CALLS: list[str] = []
VIX_CSV = b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,14.0,15.0,13.5,14.5\n01/05/2026,14.5,16.0,14.0,15.5\n"
CHAIN_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/SOXL.json"


def check(cond: bool, msg: str) -> None:
  print(("  ok   " if cond else "  FAIL ") + msg)
  if not cond:
    FAILS.append(msg)


class _FakeResponse:
  def __init__(self, body: bytes):
    self._body = body

  def __enter__(self):
    return self

  def __exit__(self, *exc):
    return False

  def read(self) -> bytes:
    return self._body


def _fake_urlopen(req, *args, **kwargs):  # noqa: ARG001 - stands in for the network; nothing leaves the machine
  url = req.full_url if hasattr(req, "full_url") else str(req)
  CALLS.append(url)
  return _FakeResponse(VIX_CSV if url.endswith("VIX_History.csv") else b'{"ok": true}')


def listing(d: Path) -> list[tuple[str, int, int]]:
  return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in d.iterdir()) if d.exists() else []


def set_mode(value: str | None) -> None:
  if value is None:
    os.environ.pop("SOXL_OFFLINE", None)
  else:
    os.environ["SOXL_OFFLINE"] = value


def raises(fn, exc_type) -> BaseException | None:
  try:
    fn()
  except exc_type as e:  # noqa: BLE001
    return e
  return None


def age_cache_file(key: str, seconds: float) -> None:
  """Rewrite one temporary cache entry so that it looks ``seconds`` old."""
  p = datafeed._cache_path(key)
  payload = json.loads(p.read_text(encoding="utf-8"))
  payload["_fetched_at"] = time.time() - seconds
  p.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
  print("test_offline")
  real_before = listing(REAL_CACHE)
  real_urlopen = urllib.request.urlopen
  real_cache_dir = datafeed.CACHE_DIR
  real_throttle = datafeed._throttle
  tmp = Path(tempfile.mkdtemp(prefix="soxl_offline_test_"))
  urllib.request.urlopen = _fake_urlopen
  datafeed.CACHE_DIR = tmp
  datafeed._throttle = lambda host: None
  try:
    if datafeed.CACHE_DIR.resolve() == REAL_CACHE.resolve():  # hard stop: nothing below may run on the real cache
      print("  FAIL temporary cache directory was not installed; aborting")
      return 1

    # 1. flag parsing
    for v in ("1", "true", "YES", " on ", "replay"):
      set_mode(v)
      check(datafeed.offline() is True, f"SOXL_OFFLINE={v!r} → offline")
    for v in (None, "", "0", "false", "No", "OFF"):
      set_mode(v)
      check(datafeed.offline() is False, f"SOXL_OFFLINE={v!r} → online")

    # 7a. online: a request reaches urlopen, the cache is written, the TTL is honoured
    set_mode(None)
    body = datafeed.safe_https_get("https://cdn.cboe.com/probe")
    check(body == '{"ok": true}' and CALLS == ["https://cdn.cboe.com/probe"], f"online: safe_https_get reaches urlopen ({len(CALLS)} call)")
    rows = datafeed.fetch_cboe_index_history("VIX")
    check([r["date"] for r in rows] == ["2026-01-02", "2026-01-05"] and rows[-1]["close"] == 15.5, "online: fetcher parses the response")
    vix_file = datafeed._cache_path("cboe_index_csv|VIX")
    check(vix_file.exists() and vix_file.parent == tmp, "online: fetcher writes the response to the cache")
    n_calls = len(CALLS)
    datafeed.fetch_cboe_index_history("VIX")
    check(len(CALLS) == n_calls, "online: a fresh cached response is served without a request")
    age_cache_file("cboe_index_csv|VIX", 30 * 24 * 3600.0)
    check(datafeed._cache_get("cboe_index_csv|VIX", 6 * 3600) is None, "online: a response older than the TTL is not served")
    stale_listing = listing(tmp)

    # 2. offline: no request, FeedError with the URL
    set_mode("1")
    del CALLS[:]
    e = raises(lambda: datafeed.safe_https_get(CHAIN_URL), datafeed.FeedError)
    check(e is not None and CHAIN_URL in str(e), f"offline: safe_https_get raises FeedError with the URL ({str(e)[:60]}…)")
    e = raises(lambda: datafeed.safe_https_get_json(CHAIN_URL), datafeed.FeedError)
    check(e is not None and CHAIN_URL in str(e), "offline: safe_https_get_json raises FeedError with the URL")
    e = raises(lambda: datafeed.safe_https_get("https://example.com/x"), ValueError)
    check(e is not None, "offline: a host outside the allow-list is still a ValueError")

    # 3. offline: any age is served
    check(datafeed._cache_get("cboe_index_csv|VIX", 1) is not None, "offline: a 30-day-old response is served with ttl 1 s")
    rows_off = datafeed.fetch_cboe_index_history("VIX")
    check(rows_off == rows, "offline: the fetcher serves the 30-day-old cached rows")
    hist = datafeed.fetch_history("^VIX", "5y")
    check([r["close"] for r in hist] == [14.5, 15.5], "offline: fetch_history('^VIX') is built from the cached rows")

    # 5. offline: uncached sources degrade as on a failed fetch
    e = raises(lambda: datafeed.fetch_cboe_chain("SOXL"), datafeed.FeedError)
    check(e is not None and CHAIN_URL in str(e), "offline: uncached option chain raises FeedError with its URL")
    e = raises(lambda: datafeed.fetch_cboe_index_history("VVIX"), datafeed.FeedError)
    check(e is not None and "VVIX_History.csv" in str(e), "offline: uncached index history raises FeedError with its URL")
    e = raises(lambda: datafeed.fetch_history("SOXL", "5y"), datafeed.FeedError)
    check(e is not None and "https://" in str(e), "offline: uncached SOXL history raises FeedError with a URL")
    check(datafeed.fetch_rss("cnbc_markets") == [], "offline: uncached RSS source returns []")
    check(datafeed.fetch_google_news("SOXL") == [], "offline: uncached news search returns []")
    check(datafeed.fetch_cboe_daily_stats("2026-11-20") is None, "offline: uncached daily statistics return None")
    check(datafeed.fetch_nasdaq_quote("SOXL") is None, "offline: uncached quote returns None")
    check(datafeed.fetch_cboe_quote("_VIX") is None, "offline: uncached index quote returns None")
    check(datafeed.fetch_nasdaq_earnings_calendar("2026-11-23") == [], "offline: uncached earnings calendar returns []")
    fomc = datafeed.fetch_fomc_calendar(2026)
    check(fomc["source"] == "static" and len(fomc["meetings"]) == 8, "offline: FOMC calendar falls back to the static list")
    check(datafeed.fetch_cnn_fear_greed() is None, "offline: uncached Fear & Greed returns None")

    # 4. offline: nothing written, nothing cleared
    datafeed._cache_put("probe|key", {"x": 1})
    check(not datafeed._cache_path("probe|key").exists(), "offline: _cache_put writes nothing")
    check(listing(tmp) == stale_listing, "offline: cache listing (names, sizes, mtimes) is unchanged after every call above")
    check(datafeed.clear_cache() == 0 and listing(tmp) == stale_listing, "offline: clear_cache removes nothing and returns 0")
    check(CALLS == [], f"offline: urlopen was never reached ({len(CALLS)} calls)")

    # 6. a refresh request to the pipeline
    cleared: list[int] = []
    real_clear, real_fetch = datafeed.clear_cache, datafeed.fetch_history

    class _Stop(Exception):
      pass

    def _stop(*a, **k):  # noqa: ARG001 - end the run right after the refresh decision
      raise _Stop()

    datafeed.clear_cache = lambda: cleared.append(1) or 0
    datafeed.fetch_history = _stop
    try:
      check(raises(lambda: pipeline.run(write_html=False, refresh=True), _Stop) is not None and cleared == [], "offline: pipeline.run(refresh=True) does not ask for a cache clear")
      set_mode(None)
      check(raises(lambda: pipeline.run(write_html=False, refresh=True), _Stop) is not None and cleared == [1], "online: pipeline.run(refresh=True) clears the cache once (stubbed)")
    finally:
      datafeed.clear_cache, datafeed.fetch_history = real_clear, real_fetch

    # 7b. online: the stale entry is refetched and the cache can be cleared
    set_mode("0")
    del CALLS[:]
    datafeed.fetch_cboe_index_history("VIX")
    check(len(CALLS) == 1 and CALLS[0].endswith("VIX_History.csv"), "online: the stale entry triggers one request")
    datafeed._cache_put("probe|key", {"x": 1})
    check(datafeed._cache_path("probe|key").exists(), "online: _cache_put writes")
    if datafeed.CACHE_DIR.resolve() != REAL_CACHE.resolve():
      n = datafeed.clear_cache()
      check(n >= 2 and listing(tmp) == [], f"online: clear_cache removes the temporary entries ({n} files)")
    else:
      check(False, "temporary cache directory lost; online clear_cache not exercised")

    # 8. import-time behaviour, on a private copy of the two modules the data layer needs
    pkg_root = tmp / "import_probe"
    (pkg_root / "soxl_quant").mkdir(parents=True)
    for name in ("__init__.py", "datafeed.py", "marketclock.py"):
      shutil.copy(REPO / "soxl_quant" / name, pkg_root / "soxl_quant" / name)
    code = "import soxl_quant.datafeed as d; print(d.offline())"
    env_off = {**os.environ, "SOXL_OFFLINE": "1", "PYTHONPATH": str(pkg_root), "PYTHONDONTWRITEBYTECODE": "1"}
    r_off = subprocess.run([sys.executable, "-c", code], cwd=str(pkg_root), env=env_off, capture_output=True, text=True, timeout=60, check=False)
    check(r_off.returncode == 0 and r_off.stdout.strip() == "True" and not (pkg_root / ".cache").exists(), "offline import does not create the cache directory")
    env_on = {k: v for k, v in env_off.items() if k != "SOXL_OFFLINE"}
    r_on = subprocess.run([sys.executable, "-c", code], cwd=str(pkg_root), env=env_on, capture_output=True, text=True, timeout=60, check=False)
    check(r_on.returncode == 0 and r_on.stdout.strip() == "False" and (pkg_root / ".cache").is_dir(), "online import creates the cache directory (unchanged behaviour)")
  finally:
    urllib.request.urlopen = real_urlopen
    datafeed.CACHE_DIR = real_cache_dir
    datafeed._throttle = real_throttle
    set_mode("1")
    shutil.rmtree(tmp, ignore_errors=True)

  # 9. the real cache
  check(listing(REAL_CACHE) == real_before, f"real .cache untouched ({len(real_before)} files, same names, sizes and mtimes)")

  print("FAILURES:" if FAILS else "ALL PASS", len(FAILS))
  return 1 if FAILS else 0


if __name__ == "__main__":
  sys.exit(main())
