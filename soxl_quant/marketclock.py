#!/usr/bin/env python3
"""US equity market calendar helpers shared by the data feed and the scheduler.

* ``latest_session_date``          — most recent trading day whose 09:30 ET open has happened
                                     (used to decide whether the official daily series is lagging)
* ``expected_latest_trading_date`` — most recent trading day whose close (+ settle buffer) has passed
                                     (used by ``auto_update.py run --if-stale``)

Holidays are a static NYSE list (full-day closures); update ``US_MARKET_HOLIDAYS``
once a year. Unknown future years simply fall back to weekday logic, which only
costs a harmless extra run on a holiday.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

US_MARKET_HOLIDAYS: frozenset[date] = frozenset({
    # 2025
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18), date(2025, 5, 26),
    date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
})

CLOSE_SETTLE_BUFFER = timedelta(minutes=75)


def is_trading_day(d: date) -> bool:
  return d.weekday() < 5 and d not in US_MARKET_HOLIDAYS


def _back_to_trading_day(d: date) -> date:
  while not is_trading_day(d):
    d -= timedelta(days=1)
  return d


def _to_et(now: datetime | None) -> datetime:
  if now is None:
    return datetime.now(ET)
  if now.tzinfo is None:
    now = now.astimezone()  # interpret naive as local time
  return now.astimezone(ET)


def latest_session_date(now: datetime | None = None) -> date:
  """Most recent trading day whose 09:30 ET open has already happened."""
  et = _to_et(now)
  d = et.date()
  if et.time() < time(9, 30):
    d -= timedelta(days=1)
  return _back_to_trading_day(d)


def expected_latest_trading_date(now: datetime | None = None) -> date:
  """Most recent trading day whose 16:00 ET close + settle buffer has passed."""
  et = _to_et(now)
  d = et.date()
  if et.time() < (datetime.combine(d, time(16, 0)) + CLOSE_SETTLE_BUFFER).time():
    d -= timedelta(days=1)
  return _back_to_trading_day(d)


def now_utc() -> datetime:
  return datetime.now(timezone.utc)
