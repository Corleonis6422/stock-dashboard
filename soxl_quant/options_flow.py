#!/usr/bin/env python3
"""CBOE options-chain analytics: put/call, walls, GEX & gamma-flip, max pain,
whale (institutional) vs retail flow, and an options-implied forecast.

All strike windows are expressed relative to spot so the module works at any
price level (SOXL has ranged $10–$170 over the past years).
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import statistics

from . import datafeed
from .indicators import norm_cdf

OPT_SYMBOL_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_chain(raw: dict, fallback_spot: float) -> tuple[float, list[dict], dict]:
  """Parse a CBOE delayed-quotes chain into contract dicts. Returns (spot, contracts, meta)."""
  data = raw.get("data", {})
  spot = float(data.get("current_price") or fallback_spot)
  meta = {
      "symbol": data.get("symbol"),
      "timestamp": raw.get("timestamp"),
      "spot": spot,
      "spot_prev_close": float(data.get("prev_day_close") or 0.0),
      "spot_change_pct": float(data.get("price_change_percent") or 0.0),
      "iv30": float(data.get("iv30") or 0.0),
      "iv30_change": float(data.get("iv30_change") or 0.0),
      "underlying_volume": int(float(data.get("volume") or 0)),
  }
  ref_dt = datetime.now(timezone.utc).date()
  contracts = []
  for item in data.get("options", []):
    m = OPT_SYMBOL_RE.match(str(item.get("option", "")))
    if not m:
      continue
    _, yymmdd, typ, strike_raw = m.groups()
    exp = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    try:
      dte = (datetime.strptime(exp, "%Y-%m-%d").date() - ref_dt).days
    except ValueError:
      continue
    if dte < 0:
      continue
    strike = int(strike_raw) / 1000.0
    vol = int(float(item.get("volume") or 0))
    oi = int(float(item.get("open_interest") or 0))
    iv = float(item.get("iv") or 0.0)
    delta = float(item.get("delta") or 0.0)
    gamma = float(item.get("gamma") or 0.0)
    bid = float(item.get("bid") or 0.0)
    ask = float(item.get("ask") or 0.0)
    last = float(item.get("last_trade_price") or 0.0)
    theo = float(item.get("theo") or 0.0)
    chg = float(item.get("change") or 0.0)
    mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else (last if last > 0 else theo)
    sign = 1.0 if typ == "C" else -1.0
    # Dealer gamma exposure per 1% move (standard convention: long calls / short puts)
    gex = sign * gamma * oi * 100.0 * spot * spot * 0.01
    # Aggressor inference: last print vs NBBO; if the print sits inside the spread,
    # fall back to the option's own daily price change (demand lifts price with volume).
    if last > 0 and ask > 0 and last >= ask - 0.005:
      side = "buy"
    elif last > 0 and bid > 0 and last <= bid + 0.005:
      side = "sell"
    elif chg > 0:
      side = "buy_lean"
    elif chg < 0:
      side = "sell_lean"
    else:
      side = "mid"
    contracts.append({
        "symbol": item.get("option"), "expiration": exp, "dte": dte, "type": typ, "strike": strike,
        "volume": vol, "open_interest": oi, "iv": iv, "delta": delta, "gamma": gamma,
        "bid": bid, "ask": ask, "last": last, "mid": mid, "theo": theo, "change": chg, "side": side,
        "gex": gex, "premium": vol * mid * 100.0,
        "vol_oi": (vol / oi) if oi > 0 else (float(vol) if vol > 0 else 0.0),
        "last_trade_time": item.get("last_trade_time"),
    })
  return spot, contracts, meta


# --------------------------------------------------------------------------- #
# Black-Scholes helpers (for gamma-flip profile & probability cones)
# --------------------------------------------------------------------------- #
def _bs_gamma(S: float, K: float, T: float, sigma: float) -> float:
  if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
    return 0.0
  d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
  return math.exp(-0.5 * d1 * d1) / (math.sqrt(2 * math.pi) * S * sigma * math.sqrt(T))


def gamma_flip_level(contracts: list[dict], spot: float) -> dict:
  """Re-price dealer gamma across a spot grid and find where total GEX crosses zero."""
  usable = [c for c in contracts if c["open_interest"] > 0 and c["iv"] > 0.02 and c["dte"] <= 120]
  if not usable:
    return {"flip": None, "profile": []}
  grid = [spot * (0.55 + 0.01 * i) for i in range(0, 91)]  # 55% .. 145% of spot
  profile = []
  for S in grid:
    tot = 0.0
    for c in usable:
      T = max(c["dte"], 0.5) / 365.0
      g = _bs_gamma(S, c["strike"], T, c["iv"])
      tot += (1.0 if c["type"] == "C" else -1.0) * g * c["open_interest"] * 100.0 * S * S * 0.01
    profile.append({"spot": round(S, 2), "gex_m": round(tot / 1e6, 2)})
  flip = None
  # Choose the zero-crossing closest to spot
  best_dist = None
  for a, b in zip(profile, profile[1:]):
    if (a["gex_m"] <= 0 < b["gex_m"]) or (a["gex_m"] >= 0 > b["gex_m"]):
      x = a["spot"] + (b["spot"] - a["spot"]) * (0 - a["gex_m"]) / ((b["gex_m"] - a["gex_m"]) or 1e-9)
      dist = abs(x - spot)
      if best_dist is None or dist < best_dist:
        best_dist, flip = dist, round(x, 2)
  return {"flip": flip, "profile": profile[::3]}


def max_pain(contracts: list[dict]) -> float | None:
  strikes = sorted({c["strike"] for c in contracts if c["open_interest"] > 0})
  if not strikes:
    return None
  best, best_pain = strikes[0], float("inf")
  for s in strikes:
    pain = 0.0
    for c in contracts:
      if c["open_interest"] <= 0:
        continue
      if c["type"] == "C" and s > c["strike"]:
        pain += (s - c["strike"]) * c["open_interest"]
      elif c["type"] == "P" and s < c["strike"]:
        pain += (c["strike"] - s) * c["open_interest"]
    if pain < best_pain:
      best, best_pain = s, pain
  return best


# --------------------------------------------------------------------------- #
# Whale vs retail flow
# --------------------------------------------------------------------------- #
def whale_flow(contracts: list[dict], spot: float) -> dict:
  """Separate large 'whale' prints from small retail lots and score direction.

  Whale definition (per contract line, using today's traded volume):
    premium traded >= $250K  OR  (volume >= 1,500 and premium >= $100K),
    and vol/OI >= 0.4  (fresh positioning rather than closing old inventory).
  Direction: call buy / put sell = bullish, put buy / call sell = bearish,
  mid-market prints split 50/50.
  """
  whales, retail_c, retail_p = [], 0.0, 0.0
  for c in contracts:
    if c["volume"] <= 0 or c["mid"] <= 0:
      continue
    if c["volume"] <= 50:
      if c["type"] == "C":
        retail_c += c["premium"]
      else:
        retail_p += c["premium"]
    big = (c["premium"] >= 250_000) or (c["volume"] >= 1500 and c["premium"] >= 100_000)
    if big and c["vol_oi"] >= 0.4:
      whales.append(c)

  w_call = sum(c["premium"] for c in whales if c["type"] == "C")
  w_put = sum(c["premium"] for c in whales if c["type"] == "P")
  bull = bear = 0.0
  buy_w = {"buy": 1.0, "buy_lean": 0.7, "mid": 0.5, "sell_lean": 0.3, "sell": 0.0}
  for c in whales:
    p = c["premium"]
    b = buy_w.get(c["side"], 0.5)  # probability the print was buyer-initiated
    if c["type"] == "C":
      bull += p * b; bear += p * (1.0 - b)
    else:
      bear += p * b; bull += p * (1.0 - b)
  tot = bull + bear
  net_score = (bull - bear) / tot if tot > 0 else 0.0  # -1 .. +1
  whales_sorted = sorted(whales, key=lambda c: -c["premium"])[:15]
  top = []
  for c in whales_sorted:
    moneyness = (c["strike"] / spot - 1.0) * 100.0
    sd = c["side"]
    if c["type"] == "C":
      bias = {"buy": "看多 (買 Call)", "buy_lean": "偏多 (Call 價升量增)", "sell": "看空/收租 (賣 Call)", "sell_lean": "偏空 (Call 價跌量增)"}.get(sd, "Call 中價成交")
    else:
      bias = {"buy": "避險/看空 (買 Put)", "buy_lean": "偏空 (Put 價升量增)", "sell": "看多/收租 (賣 Put)", "sell_lean": "偏多 (Put 價跌量增)"}.get(sd, "Put 中價成交")
    top.append({
        "symbol": c["symbol"], "expiration": c["expiration"], "dte": c["dte"], "type": c["type"],
        "strike": c["strike"], "moneyness_pct": round(moneyness, 1), "volume": c["volume"],
        "open_interest": c["open_interest"], "vol_oi": round(c["vol_oi"], 2), "mid": round(c["mid"], 2),
        "premium_m": round(c["premium"] / 1e6, 2), "iv_pct": round(c["iv"] * 100, 1),
        "side": c["side"], "bias": bias,
    })
  return {
      "whale_count": len(whales),
      "whale_call_prem_m": round(w_call / 1e6, 2),
      "whale_put_prem_m": round(w_put / 1e6, 2),
      "whale_cp_ratio": round(w_call / w_put, 2) if w_put > 0 else None,
      "whale_pc_ratio": round(w_put / w_call, 2) if w_call > 0 else None,
      "whale_bull_prem_m": round(bull / 1e6, 2),
      "whale_bear_prem_m": round(bear / 1e6, 2),
      "whale_net_score": round(net_score, 3),
      "retail_call_prem_m": round(retail_c / 1e6, 2),
      "retail_put_prem_m": round(retail_p / 1e6, 2),
      "retail_cp_ratio": round(retail_c / retail_p, 2) if retail_p > 0 else None,
      "top_whale_trades": top,
  }


# --------------------------------------------------------------------------- #
# Options-implied forecast
# --------------------------------------------------------------------------- #
def _nearest_expiry(exps: list[dict], target_dte: int, min_dte: int = 1) -> dict | None:
  cands = [e for e in exps if e["dte"] >= min_dte]
  if not cands:
    return None
  return min(cands, key=lambda e: abs(e["dte"] - target_dte))


def options_forecast(contracts: list[dict], spot: float, exps: list[dict], by_exp: dict) -> dict:
  """Expected move (ATM straddle), IV cones, delta-implied probabilities, IV term structure."""

  def atm_straddle(exp: dict) -> dict | None:
    cs = by_exp.get(exp["expiration"], [])
    if not cs:
      return None
    strikes = sorted({c["strike"] for c in cs}, key=lambda s: abs(s - spot))
    call = put = None
    k = None
    for cand in strikes[:5]:
      call = next((c for c in cs if c["type"] == "C" and c["strike"] == cand and (c["mid"] > 0 or c["theo"] > 0)), None)
      put = next((c for c in cs if c["type"] == "P" and c["strike"] == cand and (c["mid"] > 0 or c["theo"] > 0)), None)
      if call and put:
        k = cand
        break
    if not call or not put:
      return None
    em = (call["mid"] or call["theo"]) + (put["mid"] or put["theo"])
    ivs = [c["iv"] for c in (call, put) if c["iv"] > 0.02]
    return {
        "expiration": exp["expiration"], "dte": exp["dte"], "atm_strike": k,
        "straddle": round(em, 2), "expected_move_pct": round(em / spot * 100.0, 1),
        "low": round(spot - em, 2), "high": round(spot + em, 2),
        "atm_iv_pct": round(statistics.mean(ivs) * 100.0, 1) if ivs else None,
    }

  weekly = _nearest_expiry(exps, 7, 3)
  monthly = _nearest_expiry(exps, 30, 15)
  quarterly = _nearest_expiry(exps, 90, 60)
  em_w = atm_straddle(weekly) if weekly else None
  em_m = atm_straddle(monthly) if monthly else None
  em_q = atm_straddle(quarterly) if quarterly else None

  # IV cone from ~30 DTE ATM IV
  iv_ref = (em_m or em_w or {}).get("atm_iv_pct")
  cone = []
  if iv_ref:
    sig = iv_ref / 100.0
    for label, days in (("1 週", 5), ("2 週", 10), ("1 個月", 21), ("3 個月", 63)):
      s = sig * math.sqrt(days / 252.0)
      cone.append({
          "horizon": label, "trading_days": days,
          "one_sigma_pct": round(s * 100.0, 1),
          "p16": round(spot * math.exp(-s), 2), "p84": round(spot * math.exp(s), 2),
          "p2_5": round(spot * math.exp(-2 * s), 2), "p97_5": round(spot * math.exp(2 * s), 2),
      })

  # Delta-implied probabilities at the monthly expiry for key levels
  probs = []
  if monthly and iv_ref:
    T = max(monthly["dte"], 1) / 365.0
    sig = iv_ref / 100.0
    for mult in (0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30, 1.50):
      K = round(spot * mult / 5.0) * 5.0 if spot > 40 else round(spot * mult, 1)
      d2 = (math.log(spot / K) - 0.5 * sig * sig * T) / (sig * math.sqrt(T))
      p_above = norm_cdf(d2)
      probs.append({
          "level": K, "vs_spot_pct": round((K / spot - 1.0) * 100.0, 1),
          "prob_above_at_expiry_pct": round(p_above * 100.0, 1),
          "prob_below_at_expiry_pct": round((1 - p_above) * 100.0, 1),
          "prob_touch_pct": round(min(100.0, 2.0 * (p_above if K > spot else 1 - p_above) * 100.0), 1),
      })

  # IV term structure: near (≤10 DTE) vs mid (20-45) vs far (60-120)
  def avg_atm_iv(lo: int, hi: int) -> float | None:
    vals = [c["iv"] for c in contracts if lo <= c["dte"] <= hi and abs(c["strike"] / spot - 1.0) <= 0.06 and c["iv"] > 0.02]
    return round(statistics.mean(vals) * 100.0, 1) if vals else None

  iv_near, iv_mid, iv_far = avg_atm_iv(1, 10), avg_atm_iv(20, 45), avg_atm_iv(60, 120)
  term = None
  if iv_near and iv_far:
    term = "倒掛 Backwardation (近月 IV > 遠月，恐慌/事件定價)" if iv_near > iv_far * 1.05 else (
        "正價差 Contango (遠月 IV > 近月，常態)" if iv_far > iv_near * 1.05 else "平坦 Flat")
  return {
      "weekly": em_w, "monthly": em_m, "quarterly": em_q, "iv_cone": cone,
      "prob_table": probs, "iv_near_pct": iv_near, "iv_mid_pct": iv_mid, "iv_far_pct": iv_far,
      "iv_term_structure": term,
  }


# --------------------------------------------------------------------------- #
# Main entry
# --------------------------------------------------------------------------- #
def analyze(symbol: str, fallback_spot: float, with_secondary: bool = True) -> dict:
  raw = datafeed.fetch_cboe_chain(symbol)
  spot, contracts, meta = parse_chain(raw, fallback_spot)
  calls = [c for c in contracts if c["type"] == "C"]
  puts = [c for c in contracts if c["type"] == "P"]
  cv, pv = sum(c["volume"] for c in calls), sum(c["volume"] for c in puts)
  co, po = sum(c["open_interest"] for c in calls), sum(c["open_interest"] for c in puts)
  cp_prem, pp_prem = sum(c["premium"] for c in calls), sum(c["premium"] for c in puts)
  net_gex = sum(c["gex"] for c in contracts)

  by_exp: dict[str, list[dict]] = {}
  for c in contracts:
    by_exp.setdefault(c["expiration"], []).append(c)
  exps = []
  for exp in sorted(by_exp):
    cs = by_exp[exp]
    e_cv = sum(c["volume"] for c in cs if c["type"] == "C")
    e_pv = sum(c["volume"] for c in cs if c["type"] == "P")
    e_co = sum(c["open_interest"] for c in cs if c["type"] == "C")
    e_po = sum(c["open_interest"] for c in cs if c["type"] == "P")
    atm = [c["iv"] for c in cs if abs(c["strike"] / spot - 1.0) <= 0.06 and c["iv"] > 0.02]
    exps.append({
        "expiration": exp, "dte": cs[0]["dte"], "call_vol": e_cv, "put_vol": e_pv,
        "pc_vol": round(e_pv / e_cv, 2) if e_cv else None, "call_oi": e_co, "put_oi": e_po,
        "pc_oi": round(e_po / e_co, 2) if e_co else None, "max_pain": max_pain(cs),
        "net_gex_m": round(sum(c["gex"] for c in cs) / 1e6, 2),
        "atm_iv_pct": round(statistics.mean(atm) * 100.0, 1) if atm else None,
    })

  # Strike aggregation within ±45% of spot
  smap: dict[float, dict] = {}
  for c in contracts:
    if not (0.55 * spot <= c["strike"] <= 1.45 * spot):
      continue
    e = smap.setdefault(c["strike"], {"strike": c["strike"], "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0, "net_gex": 0.0})
    if c["type"] == "C":
      e["call_oi"] += c["open_interest"]; e["call_vol"] += c["volume"]
    else:
      e["put_oi"] += c["open_interest"]; e["put_vol"] += c["volume"]
    e["net_gex"] += c["gex"]
  strike_rows = sorted(smap.values(), key=lambda x: x["strike"])
  for r in strike_rows:
    r["net_gex_m"] = round(r["net_gex"] / 1e6, 3)
    r["net_oi"] = r["call_oi"] - r["put_oi"]
  call_wall = max([r for r in strike_rows if r["strike"] >= spot] or strike_rows, key=lambda x: x["call_oi"]) if strike_rows else None
  put_wall = max([r for r in strike_rows if r["strike"] <= spot] or strike_rows, key=lambda x: x["put_oi"]) if strike_rows else None
  # Focus strikes for charting: keep at most ~26 rows around spot
  step = 5.0 if spot >= 60 else (2.5 if spot >= 25 else 1.0)
  focus = [r for r in strike_rows if (abs((r["strike"] / step) - round(r["strike"] / step)) < 1e-6) or (r["call_oi"] + r["put_oi"] > 4000)]
  focus = [r for r in focus if 0.6 * spot <= r["strike"] <= 1.4 * spot]

  # 25-delta skew from 7..45 DTE
  midc = [c for c in contracts if 7 <= c["dte"] <= 45 and c["iv"] > 0.05]
  c25 = [c["iv"] for c in midc if c["type"] == "C" and 0.18 <= c["delta"] <= 0.35]
  p25 = [c["iv"] for c in midc if c["type"] == "P" and -0.35 <= c["delta"] <= -0.18]
  c25iv = statistics.mean(c25) * 100 if c25 else 0.0
  p25iv = statistics.mean(p25) * 100 if p25 else 0.0

  flip = gamma_flip_level(contracts, spot)
  whales = whale_flow(contracts, spot)
  fc = options_forecast(contracts, spot, exps, by_exp)
  near_mp = max_pain([c for e in exps[:3] for c in by_exp[e["expiration"]]])
  monthly_exp = fc["monthly"]["expiration"] if fc["monthly"] else None
  monthly_mp = max_pain(by_exp.get(monthly_exp, [])) if monthly_exp else None

  top_vol = sorted(contracts, key=lambda c: -c["volume"])[:10]
  out = {
      "symbol": symbol, "cboe_spot": round(spot, 2), "chain_timestamp": meta["timestamp"],
      "iv30_pct": round(meta["iv30"] * 100.0, 1) if meta["iv30"] < 20 else round(meta["iv30"], 1),
      "iv30_change": round(meta["iv30_change"], 3),
      "total_contracts": len(contracts),
      "total_call_vol": cv, "total_put_vol": pv,
      "pc_vol_ratio": round(pv / cv, 3) if cv else None, "cp_vol_ratio": round(cv / pv, 3) if pv else None,
      "total_call_oi": co, "total_put_oi": po,
      "pc_oi_ratio": round(po / co, 3) if co else None, "cp_oi_ratio": round(co / po, 3) if po else None,
      "total_call_prem_m": round(cp_prem / 1e6, 2), "total_put_prem_m": round(pp_prem / 1e6, 2),
      "cp_prem_ratio": round(cp_prem / pp_prem, 2) if pp_prem else None,
      "total_net_gex_m": round(net_gex / 1e6, 2),
      "gamma_flip": flip["flip"], "gex_profile": flip["profile"],
      "call_wall": call_wall["strike"] if call_wall else None, "call_wall_oi": call_wall["call_oi"] if call_wall else 0,
      "put_wall": put_wall["strike"] if put_wall else None, "put_wall_oi": put_wall["put_oi"] if put_wall else 0,
      "near_max_pain": near_mp, "monthly_max_pain": monthly_mp, "monthly_expiration": monthly_exp,
      "avg_call_25d_iv": round(c25iv, 1), "avg_put_25d_iv": round(p25iv, 1), "iv_skew_25d": round(p25iv - c25iv, 1),
      "expirations": exps[:12], "focus_strikes": focus,
      "whale": whales, "forecast": fc,
      "top_vol_contracts": [{k: c[k] for k in ("symbol", "expiration", "dte", "type", "strike", "volume", "open_interest", "mid", "iv", "side")} for c in top_vol],
  }

  if with_secondary:
    out["secondary"] = {}
    for sym in ("SOXX", "SOXS"):
      try:
        raw2 = datafeed.fetch_cboe_chain(sym)
        sp2, cs2, m2 = parse_chain(raw2, 0.0)
        c2 = [c for c in cs2 if c["type"] == "C"]
        p2 = [c for c in cs2 if c["type"] == "P"]
        cv2, pv2 = sum(c["volume"] for c in c2), sum(c["volume"] for c in p2)
        co2, po2 = sum(c["open_interest"] for c in c2), sum(c["open_interest"] for c in p2)
        out["secondary"][sym] = {
            "spot": round(sp2, 2), "pc_vol_ratio": round(pv2 / cv2, 2) if cv2 else None,
            "pc_oi_ratio": round(po2 / co2, 2) if co2 else None,
            "net_gex_m": round(sum(c["gex"] for c in cs2) / 1e6, 2),
            "iv30_pct": round(m2["iv30"] * 100.0, 1) if m2["iv30"] < 20 else round(m2["iv30"], 1),
            "whale_net_score": whale_flow(cs2, sp2)["whale_net_score"] if sp2 > 0 else None,
        }
      except Exception as e:  # noqa: BLE001 - degrade gracefully per symbol
        out["secondary"][sym] = {"error": str(e)[:120]}
  return out
