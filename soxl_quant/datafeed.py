#!/usr/bin/env python3
"""Secure, cached, rate-limit-aware data feed layer for the SOXL quant engine.

All outbound requests are restricted to an explicit HTTPS host allow-list
(Yahoo Finance chart/search, CBOE delayed quotes & market statistics, and the
CNN Fear & Greed data API).  Responses are cached on disk (JSON) with a TTL so
that repeated runs during development never hammer upstream APIs (Yahoo returns
HTTP 429 after bursts of ~40 requests), and failures degrade gracefully.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from . import marketclock

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

ALLOWED_HOSTS = {
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
    "cdn.cboe.com",
    "production.dataviz.cnn.io",
    "api.nasdaq.com",
    "home.treasury.gov",
    "news.google.com",
}
ALLOWED_TICKER_RE = re.compile(r"^[\^A-Z0-9=.\-]{1,12}$")
ALLOWED_CBOE_SYMBOL_RE = re.compile(r"^_?[A-Z]{1,6}$")
ALLOWED_NASDAQ_RE = re.compile(r"^[A-Z]{1,6}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)
_LAST_CALL_TS: dict[str, float] = {}
# Yahoo starts returning HTTP 429 after bursts of ~40 requests; pace calls.
_MIN_SPACING_SEC = {
    "query1.finance.yahoo.com": 2.2,
    "query2.finance.yahoo.com": 2.2,
    "api.nasdaq.com": 0.9,
    "home.treasury.gov": 0.5,
}


class FeedError(RuntimeError):
  """Raised when an upstream feed cannot be fetched after retries."""


def _cache_path(key: str) -> Path:
  digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
  return CACHE_DIR / f"{digest}.json"


def _cache_get(key: str, ttl_sec: int) -> dict | list | None:
  p = _cache_path(key)
  if not p.exists():
    return None
  try:
    payload = json.loads(p.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return None
  if time.time() - float(payload.get("_fetched_at", 0)) > ttl_sec:
    return None
  return payload.get("data")


def _cache_put(key: str, data: dict | list) -> None:
  p = _cache_path(key)
  p.write_text(
      json.dumps({"_fetched_at": time.time(), "_key": key, "data": data}),
      encoding="utf-8",
  )


def _throttle(host: str) -> None:
  spacing = _MIN_SPACING_SEC.get(host, 0.25)
  last = _LAST_CALL_TS.get(host, 0.0)
  wait = spacing - (time.time() - last)
  if wait > 0:
    time.sleep(wait)
  _LAST_CALL_TS[host] = time.time()


_HOST_BLOCKED_UNTIL: dict[str, float] = {}
_RATE_LIMIT_COOLDOWN_SEC = {"query1.finance.yahoo.com": 600.0, "query2.finance.yahoo.com": 600.0}


def safe_https_get(
    url: str,
    extra_headers: dict[str, str] | None = None,
    timeout: int = 20,
    max_retries: int = 3,
) -> str:
  """GET text from an allow-listed HTTPS endpoint with throttle, backoff and a
  per-host circuit breaker (a rate-limited host is skipped for a cooldown period
  so the pipeline degrades gracefully instead of stalling)."""
  parsed = urllib.parse.urlparse(url)
  if parsed.scheme != "https" or parsed.netloc not in ALLOWED_HOSTS:
    raise ValueError(f"Disallowed URL host or scheme: {url}")
  host = parsed.netloc
  if time.time() < _HOST_BLOCKED_UNTIL.get(host, 0.0):
    raise FeedError(f"{host} is rate-limited (circuit open); skipping {url}")
  headers = {
      "User-Agent": _BROWSER_UA,
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
  }
  if extra_headers:
    headers.update(extra_headers)

  backoff = 8.0
  last_err: Exception | None = None
  retries = 2 if host in _RATE_LIMIT_COOLDOWN_SEC else max_retries
  for attempt in range(retries):
    _throttle(host)
    req = urllib.request.Request(url, headers=headers)
    try:
      with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
      last_err = e
      if e.code in (429, 418) and host in _RATE_LIMIT_COOLDOWN_SEC:
        if attempt < retries - 1:
          time.sleep(backoff)
          backoff *= 2.0
          continue
        _HOST_BLOCKED_UNTIL[host] = time.time() + _RATE_LIMIT_COOLDOWN_SEC[host]
        break
      if e.code in (429, 418, 503, 502) and attempt < retries - 1:
        time.sleep(backoff)
        backoff *= 2.0
        continue
      if e.code in (400, 401, 403, 404, 410):  # definitive answers — retrying cannot help
        raise
      if attempt < retries - 1:
        time.sleep(backoff)
        backoff *= 2.0
        continue
    except (urllib.error.URLError, TimeoutError, OSError) as e:
      last_err = e
      if attempt < retries - 1:
        time.sleep(backoff)
        backoff *= 2.0
        continue
  raise FeedError(f"Failed to fetch {url}: {last_err}")


def safe_https_get_json(
    url: str, extra_headers: dict[str, str] | None = None, timeout: int = 20
) -> dict | list:
  return json.loads(safe_https_get(url, extra_headers, timeout))


# --------------------------------------------------------------------------- #
# Yahoo Finance — OHLCV history & news search
# --------------------------------------------------------------------------- #
def fetch_yahoo_ohlcv(
    ticker: str,
    period_range: str = "1y",
    interval: str = "1d",
    ttl_sec: int = 6 * 3600,
) -> list[dict]:
  """Fetch daily OHLCV history (list of dict rows) for a validated ticker."""
  if not ALLOWED_TICKER_RE.match(ticker):
    raise ValueError(f"Invalid ticker symbol: {ticker}")
  if period_range not in {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"}:
    raise ValueError(f"Invalid range: {period_range}")
  if interval not in {"1d", "1wk"}:
    raise ValueError(f"Invalid interval: {interval}")

  key = f"yahoo_chart|{ticker}|{period_range}|{interval}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached

  encoded = urllib.parse.quote(ticker)
  hosts = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]
  raw = None
  err: Exception | None = None
  for host in hosts:
    url = (
        f"https://{host}/v8/finance/chart/{encoded}"
        f"?range={period_range}&interval={interval}&includePrePost=false"
    )
    try:
      raw = safe_https_get_json(url)
      break
    except (FeedError, urllib.error.HTTPError) as e:
      err = e
      continue
  if raw is None:
    raise FeedError(f"Yahoo chart failed for {ticker}: {err}")

  result = raw["chart"]["result"][0]
  timestamps = result.get("timestamp", [])
  quote = result["indicators"]["quote"][0]
  rows = []
  for i, ts in enumerate(timestamps):
    c = quote["close"][i]
    o = quote["open"][i]
    h = quote["high"][i]
    l = quote["low"][i]
    if c is None or o is None or h is None or l is None:
      continue
    rows.append({
        "timestamp": ts,
        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": int(quote["volume"][i] or 0),
    })
  _cache_put(key, rows)
  return rows


def fetch_yahoo_news(query: str, count: int = 20, ttl_sec: int = 1800) -> list[dict]:
  """Fetch recent news headlines for a ticker / keyword via Yahoo search API."""
  if not re.match(r"^[A-Za-z0-9 \^=.\-]{1,40}$", query):
    raise ValueError(f"Invalid news query: {query}")
  count = max(1, min(int(count), 50))
  key = f"yahoo_news|{query}|{count}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  url = (
      "https://query2.finance.yahoo.com/v1/finance/search?q="
      f"{urllib.parse.quote(query)}&newsCount={count}&quotesCount=0"
      "&enableFuzzyQuery=false"
  )
  try:
    raw = safe_https_get_json(url)
  except (FeedError, urllib.error.HTTPError):
    return []
  items = []
  for n in raw.get("news", []) or []:
    ts = int(n.get("providerPublishTime") or 0)
    items.append({
        "timestamp": ts,
        "title": str(n.get("title", "")).strip(),
        "publisher": str(n.get("publisher", "")).strip(),
        "link": str(n.get("link", "")).strip(),
        "query": query,
    })
  _cache_put(key, items)
  return items


def fetch_google_news(query: str, ttl_sec: int = 1800) -> list[dict]:
  """Fetch headlines from Google News RSS search (no key, generous limits)."""
  if not re.match(r"^[A-Za-z0-9 \^=.\-+&]{1,60}$", query):
    raise ValueError(f"Invalid news query: {query}")
  key = f"google_news|{query}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
  try:
    text = safe_https_get(url, extra_headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"}, timeout=20)
  except (FeedError, urllib.error.HTTPError):
    return []
  import xml.etree.ElementTree as ET
  from email.utils import parsedate_to_datetime
  items = []
  try:
    root = ET.fromstring(text)
  except ET.ParseError:
    return []
  for it in root.iter("item"):
    title = (it.findtext("title") or "").strip()
    link = (it.findtext("link") or "").strip()
    pub = (it.findtext("pubDate") or "").strip()
    src_el = it.find("source")
    publisher = (src_el.text or "").strip() if src_el is not None else ""
    if publisher and title.endswith(f" - {publisher}"):
      title = title[: -(len(publisher) + 3)].strip()
    try:
      ts = int(parsedate_to_datetime(pub).timestamp()) if pub else 0
    except (TypeError, ValueError):
      ts = 0
    if title:
      items.append({"timestamp": ts, "title": title, "publisher": publisher, "link": link, "query": query})
  _cache_put(key, items)
  return items


# --------------------------------------------------------------------------- #
# CBOE — delayed option chains & daily market-wide put/call statistics
# --------------------------------------------------------------------------- #
def fetch_cboe_chain(symbol: str, ttl_sec: int = 3600) -> dict:
  """Fetch the full delayed options chain JSON for a symbol (e.g. SOXL, SOXX, _SPX)."""
  if not ALLOWED_CBOE_SYMBOL_RE.match(symbol):
    raise ValueError(f"Invalid CBOE symbol: {symbol}")
  key = f"cboe_chain|{symbol}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
  raw = safe_https_get_json(url, timeout=45)
  _cache_put(key, raw)
  return raw


def fetch_cboe_daily_stats(date_str: str, ttl_sec: int = 7 * 24 * 3600) -> dict | None:
  """Fetch CBOE daily market statistics (TOTAL / INDEX / EQUITY put-call ratios).

  Returns None for non-trading days (HTTP 404)."""
  if not ISO_DATE_RE.match(date_str):
    raise ValueError(f"Invalid date: {date_str}")
  key = f"cboe_daily_stats|{date_str}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    if isinstance(cached, dict) and cached.get("_missing"):
      # 404 = non-trading day (hard miss, full TTL); 403 = not published yet (soft miss, re-check hourly)
      if not cached.get("_soft") or _cache_get(key, 3600) is not None:
        return None
    else:
      return cached
  url = (
      "https://cdn.cboe.com/data/us/options/market_statistics/daily/"
      f"{date_str}_daily_options"
  )
  try:
    raw = safe_https_get_json(url)
  except urllib.error.HTTPError as e:
    if e.code == 404:
      _cache_put(key, {"_missing": True})
      return None
    if e.code == 403:
      _cache_put(key, {"_missing": True, "_soft": True})
      return None
    raise
  except FeedError:
    _cache_put(key, {"_missing": True, "_soft": True})
    return None
  _cache_put(key, raw)
  return raw


def fetch_cboe_pc_history(num_days: int = 45) -> list[dict]:
  """Build a daily time-series of CBOE market-wide put/call ratios for the last N calendar days."""
  out = []
  today = datetime.now(timezone.utc).date()
  for back in range(num_days, -1, -1):
    d = today - timedelta(days=back)
    if d.weekday() >= 5:
      continue
    raw = fetch_cboe_daily_stats(d.strftime("%Y-%m-%d"))
    if not raw:
      continue
    ratios = {r.get("name"): r.get("value") for r in raw.get("ratios", [])}

    def _f(name: str) -> float | None:
      v = ratios.get(name)
      try:
        return float(v) if v not in (None, "") else None
      except ValueError:
        return None

    sum_all = {x.get("name"): x for x in raw.get("SUM OF ALL PRODUCTS", [])}
    vol = sum_all.get("VOLUME", {})
    out.append({
        "date": d.strftime("%Y-%m-%d"),
        "total_pc": _f("TOTAL PUT/CALL RATIO"),
        "index_pc": _f("INDEX PUT/CALL RATIO"),
        "equity_pc": _f("EQUITY PUT/CALL RATIO"),
        "etp_pc": _f("EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),
        "spx_pc": _f("SPX + SPXW PUT/CALL RATIO"),
        "vix_pc": _f("CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO"),
        "total_call_vol": int(vol.get("call") or 0),
        "total_put_vol": int(vol.get("put") or 0),
    })
  return out


# --------------------------------------------------------------------------- #
# CNN Fear & Greed Index (composite + 7 sub-indicators, ~250 days history)
# --------------------------------------------------------------------------- #
def fetch_cnn_fear_greed(ttl_sec: int = 3600) -> dict | None:
  """Fetch CNN Fear & Greed graph data.  Returns None if blocked/unavailable."""
  key = "cnn_fear_greed|graphdata"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
  headers = {
      "Referer": "https://www.cnn.com/markets/fear-and-greed",
      "Origin": "https://www.cnn.com",
  }
  try:
    raw = safe_https_get_json(url, extra_headers=headers)
  except (FeedError, urllib.error.HTTPError, json.JSONDecodeError):
    return None
  if not isinstance(raw, dict) or "fear_and_greed" not in raw:
    return None
  _cache_put(key, raw)
  return raw


# --------------------------------------------------------------------------- #
# CBOE — official daily index histories (VIX complex), CSV
# --------------------------------------------------------------------------- #
CBOE_INDEX_CSV = {"VIX", "VIX9D", "VIX3M", "VIX6M", "VIX1D", "VVIX", "SKEW"}


def fetch_cboe_index_history(name: str, ttl_sec: int = 6 * 3600) -> list[dict]:
  """Fetch official CBOE daily history for a volatility index as rows {date, close, [open, high, low]}."""
  if name not in CBOE_INDEX_CSV:
    raise ValueError(f"Unsupported CBOE index: {name}")
  key = f"cboe_index_csv|{name}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
  text = safe_https_get(url, extra_headers={"Accept": "text/csv, */*"}, timeout=30)
  rows = []
  lines = text.strip().splitlines()
  if not lines:
    return rows
  header = [h.strip().upper() for h in lines[0].split(",")]
  idx = {h: i for i, h in enumerate(header)}
  close_col = idx.get("CLOSE", idx.get(name, len(header) - 1))
  for line in lines[1:]:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) <= close_col or not parts[0]:
      continue
    try:
      d = datetime.strptime(parts[0], "%m/%d/%Y").strftime("%Y-%m-%d")
      close = float(parts[close_col])
    except ValueError:
      continue
    row = {"date": d, "close": close}
    for col in ("OPEN", "HIGH", "LOW"):
      if col in idx:
        try:
          row[col.lower()] = float(parts[idx[col]])
        except ValueError:
          pass
    rows.append(row)
  rows.sort(key=lambda r: r["date"])
  _cache_put(key, rows)
  return rows


# --------------------------------------------------------------------------- #
# Nasdaq.com — daily history for US stocks / ETFs (reliable 5-year fallback)
# --------------------------------------------------------------------------- #
def _num(s: str) -> float | None:
  s = str(s).replace("$", "").replace(",", "").strip()
  if s in ("", "--", "N/A"):
    return None
  try:
    return float(s)
  except ValueError:
    return None


def fetch_nasdaq_history(symbol: str, asset_class: str = "etf", years: int = 5, ttl_sec: int = 6 * 3600) -> list[dict]:
  """Fetch daily OHLCV from api.nasdaq.com (assetclass: 'etf' | 'stocks' | 'index')."""
  if not ALLOWED_NASDAQ_RE.match(symbol) or asset_class not in {"etf", "stocks", "index"}:
    raise ValueError(f"Invalid Nasdaq request: {symbol}/{asset_class}")
  key = f"nasdaq_hist|{symbol}|{asset_class}|{years}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  today = datetime.now(timezone.utc).date()
  start = today.replace(year=today.year - years)
  url = (
      f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass={asset_class}"
      f"&fromdate={start.isoformat()}&limit=9999&todate={today.isoformat()}"
  )
  raw = safe_https_get_json(url, extra_headers={"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}, timeout=40)
  table = ((raw.get("data") or {}).get("tradesTable") or {}).get("rows") or []
  rows = []
  for r in table:
    try:
      d = datetime.strptime(r.get("date", ""), "%m/%d/%Y")
    except ValueError:
      continue
    c, o, h, l = _num(r.get("close")), _num(r.get("open")), _num(r.get("high")), _num(r.get("low"))
    if c is None:
      continue
    v = _num(r.get("volume"))
    rows.append({
        "timestamp": int(d.replace(tzinfo=timezone.utc).timestamp()), "date": d.strftime("%Y-%m-%d"),
        "open": o if o is not None else c, "high": h if h is not None else c, "low": l if l is not None else c,
        "close": c, "volume": int(v or 0),
    })
  rows.sort(key=lambda x: x["date"])
  if not rows:
    raise FeedError(f"Nasdaq returned no rows for {symbol}")
  _cache_put(key, rows)
  return rows


# --------------------------------------------------------------------------- #
# Nasdaq latest session — the historical endpoint only publishes a day's row
# several hours after the close, so right after the bell (or intraday) we build
# the current session's bar from the 1-minute chart + the official close quote.
# --------------------------------------------------------------------------- #
AUGMENT_LATEST = True
_ET = ZoneInfo("America/New_York")
_NASDAQ_HEADERS = {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
_NASDAQ_TS_RE = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4})(?:\s+(\d{1,2}:\d{2} [AP]M))?")


def _parse_nasdaq_ts(s: str) -> datetime | None:
  m = _NASDAQ_TS_RE.search(s or "")
  if not m:
    return None
  try:
    if m.group(2):
      return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%b %d, %Y %I:%M %p").replace(tzinfo=_ET)
    return datetime.strptime(m.group(1), "%b %d, %Y").replace(tzinfo=_ET)
  except ValueError:
    return None


def latest_session_date(now: datetime | None = None) -> date:
  """Most recent US trading day whose 09:30 ET open has already happened (holiday-aware)."""
  return marketclock.latest_session_date(now)


def fetch_nasdaq_latest_session(symbol: str, asset_class: str = "etf", ttl_sec: int = 600) -> dict | None:
  """Build today's (or the last session's) OHLCV bar from Nasdaq's intraday chart.

  Returns None when no regular-session points exist yet. The bar is flagged
  ``provisional`` (not the official daily row) and ``final`` once the session is
  over; the official close from the quote endpoint replaces the last tick when
  the market is in after-hours / closed state.
  """
  if not ALLOWED_NASDAQ_RE.match(symbol) or asset_class not in {"etf", "stocks", "index"}:
    raise ValueError(f"Invalid Nasdaq request: {symbol}/{asset_class}")
  key = f"nasdaq_latest|{symbol}|{asset_class}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached or None
  raw = safe_https_get_json(f"https://api.nasdaq.com/api/quote/{symbol}/chart?assetclass={asset_class}", extra_headers=_NASDAQ_HEADERS, timeout=40)
  d = raw.get("data") or {}
  reg: list[tuple[datetime, float]] = []
  for p in d.get("chart") or []:
    try:
      x, y = int(p["x"]) / 1000.0, float(p["y"])
    except (KeyError, TypeError, ValueError):
      continue
    t = datetime.fromtimestamp(x, tz=_ET)
    if dtime(9, 30) <= t.time() <= dtime(16, 0):
      reg.append((t, y))
  if not reg:
    _cache_put(key, {})
    return None
  reg.sort(key=lambda z: z[0])
  sess = reg[0][0].date()
  ys = [y for _, y in reg]
  open_, high, low, close = ys[0], max(ys), min(ys), ys[-1]
  vol = _num(d.get("volume")) or 0
  final = False
  try:  # official close (after the closing auction) + market status
    info = (safe_https_get_json(f"https://api.nasdaq.com/api/quote/{symbol}/info?assetclass={asset_class}", extra_headers=_NASDAQ_HEADERS, timeout=30).get("data") or {})
    status = str(info.get("marketStatus") or "").lower()
    for blk in (info.get("secondaryData") or {}, info.get("primaryData") or {}):
      ts = str(blk.get("lastTradeTimestamp") or "")
      dt = _parse_nasdaq_ts(ts)
      px = _num(blk.get("lastSalePrice"))
      if not (dt and px and dt.date() == sess):
        continue
      m = _NASDAQ_TS_RE.search(ts)
      date_only = bool(m) and not m.group(2)
      if ts.lower().startswith("closed at") or (status == "closed" and date_only):
        close, final = px, True
        break
    if not final and status in {"closed", "after-hours", "after hours"}:
      final = True
  except Exception:  # noqa: BLE001
    pass
  now_et = datetime.now(_ET)
  if not final and (now_et.date() > sess or now_et.time() >= dtime(16, 5)):
    final = True
  row = {
      "timestamp": int(datetime(sess.year, sess.month, sess.day, tzinfo=timezone.utc).timestamp()), "date": sess.isoformat(),
      "open": round(open_, 4), "high": round(max(high, close), 4), "low": round(min(low, close), 4), "close": round(close, 4),
      "volume": int(vol), "provisional": True, "final": final, "asof_et": now_et.strftime("%Y-%m-%d %H:%M ET"),
      "last_tick_et": reg[-1][0].strftime("%H:%M"),
  }
  _cache_put(key, row)
  return row


def _augment_latest(symbol: str, asset_class: str, rows: list[dict]) -> list[dict]:
  """Append the current session's provisional bar when the official series lags."""
  if not AUGMENT_LATEST or not rows:
    return rows
  if rows[-1]["date"] >= latest_session_date().isoformat():
    return rows
  try:
    row = fetch_nasdaq_latest_session(symbol, asset_class)
  except Exception:  # noqa: BLE001
    return rows
  if not row or row["date"] <= rows[-1]["date"]:
    return rows
  return rows + [row]


# --------------------------------------------------------------------------- #
# US Treasury — official daily par yield curve (CSV per year)
# --------------------------------------------------------------------------- #
def fetch_treasury_yields(years: int = 3, ttl_sec: int = 6 * 3600) -> list[dict]:
  """Return daily rows {date, y2, y5, y10, y20, y30} from home.treasury.gov (oldest -> newest)."""
  key = f"treasury_curve|{years}"
  cached = _cache_get(key, ttl_sec)
  if cached is not None:
    return cached
  this_year = datetime.now(timezone.utc).year
  rows = []
  for y in range(this_year - years + 1, this_year + 1):
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
        f"{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"
    )
    try:
      text = safe_https_get(url, extra_headers={"Accept": "text/csv"}, timeout=30)
    except (FeedError, urllib.error.HTTPError):
      continue
    lines = text.strip().splitlines()
    if len(lines) < 2:
      continue
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    col = {name: i for i, name in enumerate(header)}
    for line in lines[1:]:
      parts = [p.strip().strip('"') for p in line.split(",")]
      if len(parts) < len(header):
        continue
      try:
        d = datetime.strptime(parts[0], "%m/%d/%Y").strftime("%Y-%m-%d")
      except ValueError:
        continue

      def g(name: str) -> float | None:
        i = col.get(name)
        return _num(parts[i]) if i is not None and i < len(parts) else None

      rows.append({"date": d, "y2": g("2 Yr"), "y5": g("5 Yr"), "y10": g("10 Yr"), "y20": g("20 Yr"), "y30": g("30 Yr")})
  rows = [r for r in rows if r["y10"] is not None]
  rows.sort(key=lambda x: x["date"])
  if rows:
    _cache_put(key, rows)
  return rows


# --------------------------------------------------------------------------- #
# Unified dispatcher
# --------------------------------------------------------------------------- #
_NASDAQ_ETFS = {"SOXL", "SOXX", "SOXS", "SPY", "QQQ", "HYG", "TLT", "SMH", "TQQQ", "SQQQ", "IWM", "LQD", "GLD", "USO", "BNO", "UUP", "CPER", "IBIT", "BITO"}
# When a Yahoo-only instrument is unavailable, fall back to a liquid ETF proxy (Nasdaq source)
PROXY_FALLBACK = {"BZ=F": ("BNO", "Brent 原油 (BNO ETF 代理)"), "DX-Y.NYB": ("UUP", "美元指數 (UUP ETF 代理)"),
                  "GC=F": ("GLD", "黃金 (GLD ETF 代理)"), "HG=F": ("CPER", "銅 (CPER ETF 代理)"), "BTC-USD": ("IBIT", "比特幣 (IBIT ETF 代理)")}
_YEARS_BY_RANGE = {"5d": 1, "1mo": 1, "3mo": 1, "6mo": 1, "1y": 1, "2y": 2, "5y": 5, "10y": 10, "max": 10}


def fetch_history(symbol: str, period_range: str = "1y") -> list[dict]:
  """Fetch daily OHLCV for a symbol using the most reliable source available.

  * ^VIX                         -> official CBOE CSV
  * US ETFs / stocks (plain)     -> Nasdaq.com (5y), fallback Yahoo
  * ^TNX / ^TYX                  -> US Treasury CSV (10Y/30Y), fallback Yahoo
  * futures / FX / crypto / idx  -> Yahoo only
  """
  years = _YEARS_BY_RANGE.get(period_range, 1)
  if symbol == "^VIX":
    rows = fetch_cboe_index_history("VIX")
    out = [{"timestamp": 0, "date": r["date"], "open": r.get("open", r["close"]), "high": r.get("high", r["close"]),
            "low": r.get("low", r["close"]), "close": r["close"], "volume": 0} for r in rows]
    return out[-(years * 260):]
  if symbol in ("^TNX", "^TYX"):
    try:
      t = fetch_treasury_yields(max(2, years))
      k = "y10" if symbol == "^TNX" else "y30"
      out = [{"timestamp": 0, "date": r["date"], "open": r[k], "high": r[k], "low": r[k], "close": r[k], "volume": 0} for r in t if r.get(k) is not None]
      if out:
        return out[-(years * 260):]
    except Exception:  # noqa: BLE001
      pass
    return fetch_yahoo_ohlcv(symbol, period_range)
  plain = re.fullmatch(r"[A-Z]{1,5}", symbol) is not None
  if plain:
    cls = "etf" if symbol in _NASDAQ_ETFS else "stocks"
    try:
      return _augment_latest(symbol, cls, fetch_nasdaq_history(symbol, cls, years=max(1, min(years, 5))))
    except Exception:  # noqa: BLE001
      try:
        other = "stocks" if cls == "etf" else "etf"
        return _augment_latest(symbol, other, fetch_nasdaq_history(symbol, other, years=max(1, min(years, 5))))
      except Exception:  # noqa: BLE001
        return fetch_yahoo_ohlcv(symbol, period_range)
  return fetch_yahoo_ohlcv(symbol, period_range)


def fetch_history_with_proxy(symbol: str, period_range: str = "1y") -> tuple[list[dict], str | None]:
  """fetch_history() with ETF-proxy fallback. Returns (rows, proxy_label_or_None)."""
  try:
    return fetch_history(symbol, period_range), None
  except Exception:  # noqa: BLE001
    proxy = PROXY_FALLBACK.get(symbol)
    if not proxy:
      raise
    return fetch_history(proxy[0], period_range), proxy[1]


def clear_cache() -> int:
  """Delete all cached payloads. Returns number of files removed."""
  n = 0
  for p in CACHE_DIR.glob("*.json"):
    p.unlink(missing_ok=True)
    n += 1
  return n
