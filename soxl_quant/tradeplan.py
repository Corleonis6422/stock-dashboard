#!/usr/bin/env python3
"""Trade plan builder: turns today's data into one explicit, checkable plan.

Why
  A verdict ("減碼 / 觀望") is not a plan.  The brief must state a side, an entry
  trigger with a price, a stop, two targets, the reward-to-risk, a position size,
  a time stop and the conditions that invalidate the idea.  When the numbers do not
  earn a trade, the plan says ``no_trade`` and prints the price that would make it
  one, instead of hiding behind adjectives.

Rules (all deterministic, no fitting)
  side
    * ``long``          a long signal graded A / B / B* fired today -> enter next open
    * ``long_pending``  the nearest graded long trigger is within TRIGGER_NEAR_PCT of the close
                        -> buy-stop at the trigger price
    * ``no_trade``      otherwise; the conditional bounce plan is still printed so the
                        reader knows what would change the answer
  stop   ONE exit price for everyone: the nearest structural support below the entry (10-day low /
         VAL / Bollinger lower / put wall) when it sits at least MIN_STRUCT_ATR × ATR14 below the
         entry, otherwise entry - k_atr × ATR14 (k_atr from the fired signal's in-sample MAE
         calibration, default DEFAULT_K_ATR).  Never tighter than MIN_STOP_PCT.  The same price is
         the holder's hard stop, so the plan never carries two different exit levels.
  T1/T2  first resistance at least 1R / 2R above the entry; synthetic ATR targets when the
         ladder runs out (labelled as such)
  gate   blended reward-to-risk 0.5·R(T1) + 0.5·R(T2) must be >= MIN_RR, else ``tradeable=False``
         and ``trade_if_entry`` = the entry that would satisfy the gate with the same stop and targets
  size   risk-based: RISK_PER_TRADE_PCT of the account / stop distance, capped by the verdict's
         size ceiling; both numbers are reported
  time   the signal's horizon (mean-reversion setups: exit at the first close above SMA5, cap 10 bars)
  exits  historical exit signals have no predictive edge on SOXL (see backtest.summary.exits_predictive),
         so the holder plan is risk control: hard stop + chandelier trail, with the cost stated
"""
from __future__ import annotations

from . import indicators as ind

MIN_RR = 1.5
RISK_PER_TRADE_PCT = 1.0
DEFAULT_K_ATR = 1.2  # median of the in-sample MAE calibrations across the mean-reversion signals
MIN_STOP_PCT = 4.0
MIN_STRUCT_ATR = 0.8   # a structural stop closer than this (in ATR) is noise, fall back to the ATR stop
SPOT_GAP_PCT = 2.0     # above this CBOE-spot vs close gap, IV-band levels are stale and are not used as targets
TRIGGER_NEAR_PCT = 8.0
GOOD_GRADES = ("A", "B", "B*")


def _r2(x):
  return None if x is None else round(float(x), 2)


def _resistances(tech: dict, opt: dict, pb: dict, spot: float, skip_iv_bands: bool = False) -> list[dict]:
  """Every resistance candidate above spot, de-duplicated (1.2%), ascending."""
  c: list[dict] = []

  def add(price, label):
    try:
      p = float(price)
    except (TypeError, ValueError):
      return
    if p > spot * 1.003:
      c.append({"price": p, "label": label})

  for r in pb.get("ladder") or []:
    if r.get("kind") == "res" and not (skip_iv_bands and "1σ" in str(r.get("label"))):
      add(r["price"], r["label"])
  add(tech.get("ema5"), "EMA5")
  add(tech.get("ema10"), "EMA10")
  add(tech.get("sma20"), "20MA 月線")
  add(tech.get("sma50"), "50MA 季線")
  add(tech.get("sma200"), "200MA 年線")
  add(tech.get("bb_mid"), "布林中軌")
  add(tech.get("bb_upper"), "布林上軌")
  add(tech.get("poc_price"), "VPVR POC")
  add(tech.get("vah_price"), "價值區上緣 VAH")
  for k, lbl in (("fib_236", "Fib 23.6%"), ("fib_382", "Fib 38.2%"), ("fib_500", "Fib 50%"), ("fib_618", "Fib 61.8%")):
    add(((tech.get("swing") or {}).get("levels") or {}).get(k), f"{lbl} 反彈位")
  add(opt.get("gamma_flip"), "Gamma 翻正位")
  add(opt.get("call_wall"), "Call 牆")
  fc = opt.get("forecast") or {}
  if not skip_iv_bands:
    for key, lbl in (("weekly", "週選 1σ 上緣"), ("monthly", "月選 1σ 上緣")):
      if isinstance(fc.get(key), dict):
        add(fc[key].get("high"), lbl)
  c.sort(key=lambda x: x["price"])
  out: list[dict] = []
  for lv in c:
    if out and abs(lv["price"] / out[-1]["price"] - 1.0) < 0.012:
      if lv["label"] not in out[-1]["label"]:
        out[-1]["label"] += " / " + lv["label"]
      continue
    out.append(dict(lv))
  return out


def _supports(tech: dict, opt: dict, pb: dict, spot: float, soxl_rows: list[dict], skip_iv_bands: bool = False) -> list[dict]:
  c: list[dict] = []

  def add(price, label):
    try:
      p = float(price)
    except (TypeError, ValueError):
      return
    if 0 < p < spot * 0.997:
      c.append({"price": p, "label": label})

  for r in pb.get("ladder") or []:
    if r.get("kind") == "sup" and not (skip_iv_bands and "1σ" in str(r.get("label"))):
      add(r["price"], r["label"])
  add(min(r["low"] for r in soxl_rows[-10:]), "近 10 日最低")
  add(tech.get("val_price"), "價值區下緣 VAL")
  add(tech.get("bb_lower"), "布林下軌")
  add(opt.get("put_wall"), "Put 牆")
  fc = opt.get("forecast") or {}
  if isinstance(fc.get("weekly"), dict) and not skip_iv_bands:
    add(fc["weekly"].get("low"), "週選 1σ 下緣")
  c.sort(key=lambda x: -x["price"])
  out: list[dict] = []
  for lv in c:
    if out and abs(lv["price"] / out[-1]["price"] - 1.0) < 0.012:
      if lv["label"] not in out[-1]["label"]:
        out[-1]["label"] += " / " + lv["label"]
      continue
    out.append(dict(lv))
  return out


def _pick_target(res: list[dict], entry: float, risk: float, mult: float, atr: float, tag: str) -> dict:
  for lv in res:
    if (lv["price"] - entry) / risk >= mult:
      return {"price": _r2(lv["price"]), "label": " / ".join(lv["label"].split(" / ")[:2]), "rr": round((lv["price"] - entry) / risk, 2), "synthetic": False}
  px = entry + (1.5 if tag == "t1" else 3.0) * risk
  return {"price": _r2(px), "label": f"合成目標（{'1.5' if tag == 't1' else '3'}R，階梯上無價位）", "rr": 1.5 if tag == "t1" else 3.0, "synthetic": True}


def build(tech: dict, opt: dict, pb: dict, score: dict, bt: dict | None, soxl_rows: list[dict], sen: dict | None = None) -> dict:
  spot = float(tech["close"])
  atr = float((bt or {}).get("atr14") or tech.get("atr14") or spot * tech.get("atr_pct", 8.0) / 100.0)
  rating = int(score.get("rating_5") or 3)
  beginner = pb.get("beginner") or {}
  verdict_size = beginner.get("size_pct")
  vx = (sen or {}).get("vix") or {}
  vix_ratio = vx.get("ratio_vix_3m")
  crash = float(((bt or {}).get("ews_today") or {}).get("score") or pb.get("crash_score") or 0)
  signals = (bt or {}).get("signals") or []
  spot_gap = abs((float(opt.get("cboe_spot") or spot) / spot - 1.0) * 100.0) if spot else 0.0
  stale_iv = spot_gap >= SPOT_GAP_PCT
  res = _resistances(tech, opt, pb, spot, skip_iv_bands=stale_iv)
  sup = _supports(tech, opt, pb, spot, soxl_rows, skip_iv_bands=stale_iv)
  explain: list[str] = []
  if stale_iv:
    explain.append(f"期權鏈的即時價 ${float(opt.get('cboe_spot')):,.2f} 與收盤差 {spot_gap:.1f}%，週/月選 1σ 區間以即時價為中心，暫不拿來當目標或停損；牆（履約價）照用。")

  fired_long = [s for s in signals if s["side"] == "long" and s["today"]["state"] == "fired" and s["grade"] in GOOD_GRADES]
  fired_long.sort(key=lambda s: (GOOD_GRADES.index(s["grade"]), s.get("p_value") or 1.0))
  pend = [s for s in signals if s["side"] == "long" and s["grade"] in GOOD_GRADES and s["today"]["state"] == "pending" and (s["today"].get("pending") or {}).get("price")]
  pend.sort(key=lambda s: abs((s["today"]["pending"]["price"] / spot - 1.0) * 100.0))
  fired_exit = [s for s in signals if s["side"] == "exit" and s["today"]["state"] == "fired"]
  recent_exit = [s for s in signals if s["side"] == "exit" and s["today"]["state"] == "recent"]

  # ------------------------------------------------------------ side + entry
  trigger: dict
  if fired_long:
    s0 = fired_long[0]
    side = "long"
    entry = spot  # next open ≈ close for planning; the brief says 次日開盤
    k_atr = float((s0.get("stop") or {}).get("k_atr") or DEFAULT_K_ATR)
    horizon = int(s0["horizon"])
    trigger = {"type": "market_next_open", "price": _r2(spot), "rule": f"{s0['short_name']} 今日觸發（勝率 {s0['win_pct']}% vs 基準 {s0['base']['win_pct']}%，N={s0['n']}，p={s0['p_value']}）→ 次日開盤進場",
               "signal": s0["key"]}
    explain.append(f"進場：{s0['name']} 今日成立，歷史 N={s0['n']} 勝率 {s0['win_pct']}%（基準 {s0['base']['win_pct']}%，p={s0['p_value']}），等級 {s0['grade']}。")
  elif pend and abs((pend[0]["today"]["pending"]["price"] / spot - 1.0) * 100.0) <= TRIGGER_NEAR_PCT and pend[0]["today"]["pending"]["price"] > spot:
    s0 = pend[0]
    pd_ = s0["today"]["pending"]
    side = "long_pending"
    entry = float(pd_["price"])
    k_atr = float((s0.get("stop") or {}).get("k_atr") or DEFAULT_K_ATR)
    horizon = int(s0["horizon"])
    trigger = {"type": "buy_stop_on_close", "price": _r2(entry), "rule": f"收盤 {pd_.get('op', '>')} ${entry:,.2f}" + (f"（{pd_['needs']}）" if pd_.get("needs") else "") + f" → {s0['short_name']} 成立，次日開盤進場", "signal": s0["key"]}
    explain.append(f"進場觸發：{s0['name']} 尚未成立，收盤 {pd_.get('op', '>')} ${entry:,.2f} 才算（距現價 {pd_.get('dist_pct')}%）。")
  else:
    side = "no_trade"
    first_res = res[0] if res else None
    entry = float(first_res["price"]) if first_res else spot * 1.02
    k_atr = DEFAULT_K_ATR
    horizon = 10
    trigger = {"type": "conditional", "price": _r2(entry),
               "rule": (f"收盤站上 {first_res['label']} ${entry:,.2f} 且量能 RVOL ≥ 1.2 → 條件成立後次日開盤進場（反彈單）" if first_res else "出現帶量長紅且收盤站回 EMA5 → 次日開盤進場"), "signal": None}
    explain.append("今天沒有任何 A/B 級買進訊號成立，也沒有觸發價在 8% 內的待觸發訊號：不開新倉。下面的計畫是『如果觸發才執行』的條件單。")

  # ------------------------------------------------------------ stop
  struct = next((s for s in sup if s["price"] < entry * 0.997), None)
  atr_stop = entry - k_atr * atr
  if struct and (entry - struct["price"]) >= MIN_STRUCT_ATR * atr:
    stop = struct["price"]
    stop_kind = "structural"
    stop_basis = f"結構支撐 {struct['label']}（距進場 {(entry - struct['price']) / atr:.2f}×ATR，≥ {MIN_STRUCT_ATR}×ATR 才採用）"
  else:
    stop = atr_stop
    stop_kind = "atr"
    stop_basis = f"{k_atr:.1f}×ATR14（ATR ${atr:,.2f}）" + (f"；結構支撐 {struct['label']} ${struct['price']:,.2f} 太近（< {MIN_STRUCT_ATR}×ATR）不採用" if struct else "；下方沒有結構支撐")
  stop = min(stop, entry * (1.0 - MIN_STOP_PCT / 100.0))
  risk = entry - stop
  stop_dist_pct = (stop / entry - 1.0) * 100.0
  explain.append(f"停損 ${stop:,.2f}（{stop_dist_pct:+.1f}%）：{stop_basis}。這是唯一的出場價，新倉與舊倉都用它；勝利交易 75% 的最大逆向波動在 {k_atr:.1f}×ATR 以內，比這更緊會砍掉贏家。")

  # ------------------------------------------------------------ targets + gate
  res_above_entry = [r for r in res if r["price"] > entry * 1.003]
  t1 = _pick_target(res_above_entry, entry, risk, 1.0, atr, "t1")
  t2 = _pick_target([r for r in res_above_entry if r["price"] > (t1["price"] or 0) * 1.003], entry, risk, 2.0, atr, "t2")
  rr_blend = round(0.5 * t1["rr"] + 0.5 * t2["rr"], 2)
  tradeable = rr_blend >= MIN_RR and side in ("long", "long_pending")
  trade_if_entry = None
  if rr_blend < MIN_RR and t2["price"]:
    # entry E with the same stop and targets: 0.5*(T1-E)/(E-S) + 0.5*(T2-E)/(E-S) = MIN_RR  ->  E = (0.5*T1 + 0.5*T2 + MIN_RR*S) / (1 + MIN_RR)
    trade_if_entry = _r2((0.5 * t1["price"] + 0.5 * t2["price"] + MIN_RR * stop) / (1.0 + MIN_RR))
    explain.append(f"風報比不足：T1 {t1['rr']}R / T2 {t2['rr']}R，加權 {rr_blend}R < {MIN_RR}R。同樣的停損與目標下，進場價要 ≤ ${trade_if_entry:,.2f} 才值得做。")
  else:
    explain.append(f"目標：T1 {t1['label']} ${t1['price']:,.2f}（{t1['rr']}R）、T2 {t2['label']} ${t2['price']:,.2f}（{t2['rr']}R），加權 {rr_blend}R。")

  # ------------------------------------------------------------ size
  size_risk = round(RISK_PER_TRADE_PCT / max(abs(stop_dist_pct), 0.1) * 100.0, 1)
  cap = float(verdict_size) if isinstance(verdict_size, (int, float)) else 100.0
  size_if = round(min(size_risk, cap), 1)
  size_pct = size_if if side != "no_trade" else 0.0
  explain.append(f"倉位：每筆只冒 {RISK_PER_TRADE_PCT}% 帳戶風險 ÷ 停損距離 {abs(stop_dist_pct):.1f}% = {size_risk}% 帳戶；評級上限 {cap:.0f}% → {'觸發後' if side == 'no_trade' else ''}採 {size_if}%。連續 3 次停損 = −{3 * RISK_PER_TRADE_PCT:.0f}% 帳戶。")

  # ------------------------------------------------------------ time stop + exit style
  sig0 = fired_long[0] if fired_long else (pend[0] if side == "long_pending" else None)
  if sig0 and sig0.get("dyn"):
    time_stop = {"days": 10, "rule": sig0["dyn"]["exit_rule"], "kind": "dynamic"}
  else:
    time_stop = {"days": horizon, "rule": f"{horizon} 個交易日內未觸及 T1 即平倉（訊號的驗證期）", "kind": "fixed"}

  # ------------------------------------------------------------ invalidation
  inval = [f"收盤 < ${stop:,.2f}（停損，唯一的出場價）"]
  if vix_ratio is not None:
    inval.append(f"VIX/VIX3M ≥ 1.0（目前 {vix_ratio:.3f}）")
  if crash:
    inval.append(f"崩跌前兆分數 ≥ 80（目前 {crash:.0f}）")
  if side == "long_pending":
    inval.append(f"觸發前收盤 < ${min(spot, stop) * 0.98:,.2f} 則取消條件單（結構已變）")

  # ------------------------------------------------------------ holder plan (risk control, not prediction)
  hh22 = max(r["high"] for r in soxl_rows[-22:])
  atr22 = ind.atr(soxl_rows, 22)[-1] if len(soxl_rows) > 22 else atr
  trail = hh22 - 3.0 * atr22
  exits_pred = ((bt or {}).get("summary") or {}).get("exits_predictive") or []
  holder = {
      "hard_stop": _r2(stop), "hard_stop_label": (struct["label"] if stop_kind == "structural" and struct else f"{k_atr:.1f}×ATR 停損"),
      "trail_stop": _r2(trail), "trail_rule": f"吊燈出場：22 日高 ${hh22:,.2f} − 3×ATR22 ${atr22:,.2f}", "trail_breached": bool(trail > spot),
      "trail_note": (f"現價已在吊燈線 ${trail:,.2f} 之下（{(spot / trail - 1.0) * 100.0:+.1f}%）：移動停損早已觸發，剩餘部位以硬停損為準" if trail > spot else f"移動停損 ${trail:,.2f}（距現價 {(trail / spot - 1.0) * 100.0:+.1f}%），每日隨 22 日高上移、不下移"),
      "reduce_into": [{"price": r["price"], "label": r["label"]} for r in res[:2]],
      "exit_signals_fired": [s["short_name"] for s in fired_exit], "exit_signals_recent": [s["short_name"] for s in recent_exit],
      "edge_note": ("歷史上沒有任何賣出訊號的命中率顯著高於基準，停損是保險不是預測；賣出訊號只用來決定減碼節奏。" if not exits_pred else f"歷史上有預測力的賣出訊號：{', '.join(exits_pred)}"),
      "verdict_action": beginner.get("q_holder"),
  }

  # ------------------------------------------------------------ regime context
  grid = ((bt or {}).get("regime") or {}).get("grid") or []
  own = next((g for g in grid if g.get("series") == "SOXL" and g.get("band_pct") == 0.0), None)
  idx = next((g for g in grid if g.get("series") != "SOXL" and g.get("band_pct") == 3.0 and g.get("confirm_days") == 2), None)
  regime = {
      "soxl_own": {"in_market": own["today"]["in_market"], "sma200": own["today"]["sma200"], "dist_pct": own["today"]["dist_pct"], "cagr_pct": own["strategy"]["cagr_pct"], "switches": own["switches"]} if own else None,
      "underlying": {"series": idx["series"], "in_market": idx["today"]["in_market"], "sma200": idx["today"]["sma200"], "signal_close": idx["today"]["signal_close"], "dist_pct": idx["today"]["dist_pct"],
                     "exit_below": idx["today"]["exit_below"], "enter_above": idx["today"]["enter_above"], "cagr_pct": idx["strategy"]["cagr_pct"], "max_dd_pct": idx["strategy"]["max_dd_pct"], "switches": idx["switches"],
                     "rule": f"{idx['series']} 收盤連續 {idx['confirm_days']} 日在 200 日線 ±{idx['band_pct']:.0f}% 帶外才切換"} if idx else None,
      "agree": (own["today"]["in_market"] == idx["today"]["in_market"]) if (own and idx) else None,
  }
  if own and idx and not regime["agree"]:
    explain.append(f"兩種 200 日線讀法今天不一致：SOXL 自身在年線{'上' if own['today']['in_market'] else '下'}（{own['today']['dist_pct']:+.1f}%），{idx['series']} 指數在年線{'上' if idx['today']['in_market'] else '下'}（{idx['today']['dist_pct']:+.1f}%）。長期持有者看指數那條（切換少、回測較佳），短線反彈單看 SOXL 自身。")

  pending_list = [{"key": s["key"], "short_name": s["short_name"], "grade": s["grade"], "price": s["today"]["pending"]["price"], "op": s["today"]["pending"].get("op"),
                   "dist_pct": s["today"]["pending"].get("dist_pct"), "needs": s["today"]["pending"].get("needs"), "win_pct": s["win_pct"], "base_win_pct": s["base"]["win_pct"], "n": s["n"]} for s in pend[:4]]

  return {
      "side": side, "tradeable": tradeable, "rating_5": rating,
      "headline": ({"long": "✅ 今日有驗證過的買進訊號成立：次日開盤進場，照計畫執行", "long_pending": f"⏳ 等觸發：收盤 {trigger['rule'].split('→')[0].strip()} 才進場",
                    "no_trade": "⛔ 不開新倉：沒有驗證過的買點成立；下面是觸發後才執行的條件計畫"}[side]),
      "entry": trigger,
      "stop": {"price": _r2(stop), "dist_pct": round(stop_dist_pct, 1), "k_atr": k_atr, "atr14": _r2(atr), "kind": stop_kind, "basis": stop_basis},
      "t1": t1, "t2": t2, "rr_t1": t1["rr"], "rr_t2": t2["rr"], "rr_blend": rr_blend, "min_rr": MIN_RR, "trade_if_entry": trade_if_entry,
      "size": {"pct": size_pct, "if_triggered_pct": size_if, "risk_based_pct": size_risk, "verdict_cap_pct": cap, "risk_per_trade_pct": RISK_PER_TRADE_PCT, "three_stops_pct": round(-3 * RISK_PER_TRADE_PCT, 1)},
      "time_stop": time_stop, "invalidation": inval,
      "signals_fired": [{"key": s["key"], "short_name": s["short_name"], "grade": s["grade"], "win_pct": s["win_pct"], "base_win_pct": s["base"]["win_pct"], "n": s["n"], "p_value": s["p_value"]} for s in fired_long],
      "signals_pending": pending_list,
      "holder": holder, "regime": regime, "explain": explain,
      "method": f"停損 = 進場下方最近的結構支撐（需 ≥ {MIN_STRUCT_ATR}×ATR），太近則用 {DEFAULT_K_ATR}×ATR（或訊號校準 k）；同一價位也是持有者的硬停損。T1/T2 = 進場上方首個 ≥1R / ≥2R 的壓力；加權風報比 ≥ {MIN_RR} 才算可交易；倉位 = {RISK_PER_TRADE_PCT}% 帳戶風險 ÷ 停損距離，受評級上限約束。",
  }
