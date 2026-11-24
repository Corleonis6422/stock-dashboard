#!/usr/bin/env python3
"""The ten sections below the first screen of the viewer page, and its footer.

Every section answers one question and has the same shape:

  title        a fixed name
  takeaway     one line of at most 40 characters, computed from the data (``takeaways``)
  one visual   one chart, or one table of at most 8 rows
  folds        ``<details>`` blocks, closed on load, that hold the evidence

When the source of a section is missing, the takeaway is one plain line that names the source, and
the section draws no empty chart and no empty table.

Stored model strings can carry placeholder tokens (``None``, ``n/a``) when a source failed.
``clean`` rewrites them for the reader at this boundary.  The stored values stay as they are.

Markers for scripts (``docs/page_markers.md``): ``section[data-sec]``, ``[data-takeaway]``,
``[data-sec-main]``, ``details[data-fold]``, ``[data-footer]``, ``[data-disclaimer]``, and
``[data-ext]`` on text that comes from outside sources (news titles and publishers).

Security: every interpolated value passes through html.escape(); a link is rendered only for an
http(s) URL; the script reads attributes and writes textContent, style and the ``open`` flag only.
It keeps the ids of the folds a reader opened in sessionStorage, so the timed reload leaves them open.
"""

from __future__ import annotations

import html
import math
import re

from .report_html import GLOSSARY, _date_ticks, _legend_text, _meter_svg, _place_x, _ratio_bar, _tw, fg_history_svg, options_wall_svg

NA = "暫缺"
SECTION_IDS = ("plan", "why", "paths", "crash", "mood", "options", "sector", "news", "proof", "lessons")
TITLES = {
    "plan": "今天怎麼做", "why": "為什麼是這個評級", "paths": "價位與劇本", "crash": "崩跌風險", "mood": "情緒、波動與宏觀",
    "options": "期權與大戶", "sector": "成分股與費半", "news": "新聞與時事", "proof": "訊號驗證與評級紀錄", "lessons": "崩跌復盤與教訓",
}
# the one plain line a section shows when its source is missing; it is then the section's takeaway
MISSING = {
    "plan": "交易計畫暫缺：回測步驟這次沒有結果",
    "why": "評分暫缺：評分步驟這次沒有結果",
    "paths": "劇本暫缺：歷史同類情境這次沒有算出機率",
    "crash": "崩跌指數暫缺：前兆系統這次沒有產生分數",
    "mood": "情緒資料暫缺：CNN 與 CBOE 這次都沒有回應",
    "options": "期權資料暫缺：CBOE 選擇權鏈這次沒有回應",
    "sector": "成分股資料暫缺：個股日線這次沒有抓到",
    "news": "時事資料暫缺：新聞來源這次沒有回應",
    "proof": "回測資料暫缺：這次更新沒有回測結果",
    "lessons": "近 30 日無重大回檔可供復盤",
}
ERROR_LINE = "這一區這次沒有產生，其餘區塊不受影響"
TAKEAWAY_MAX = 40
OPT_NOTE = "資料暫缺（CBOE 選擇權鏈這次沒有回應）"
SOURCES_LINE = "資料來源：Nasdaq、CBOE（選擇權鏈、VIX 家族、Put/Call 統計）、CNN Fear & Greed、美國財政部殖利率、Yahoo Finance、Google News。"
TONE_COL = {"bull": "#22c55e", "neutral": "#eab308", "bear": "#ef4444"}
TONE_ZH = {"bull": "偏多", "neutral": "中性", "bear": "偏空"}
TONE_EMOJI = {"bull": "🟢", "neutral": "🟡", "bear": "🔴"}
RATING_EMOJI = {1: "🔴🔴", 2: "🔴", 3: "🟡", 4: "🟢", 5: "🟢🟢"}
SIGNAL_STATE_ZH = {"fired": "🔴 今日觸發", "recent": "🟠 10 日內觸發", "pending": "⏳ 待觸發", "off": "⚪ 未觸發"}
FG_ZH = {"extreme fear": "極度恐懼", "fear": "恐懼", "neutral": "中性", "greed": "貪婪", "extreme greed": "極度貪婪"}
TERM_ZH = {"backwardation": "倒掛", "contango": "正價差", "flat": "持平"}


# --------------------------------------------------------------------------- #
# values and text
# --------------------------------------------------------------------------- #
def esc(v: object) -> str:
  return html.escape("" if v is None else str(v), quote=True)


def g(d: object, *path, default=None):
  """Nested lookup that never raises: dict keys and list indexes.  ``default`` for a missing step or a None."""
  cur = d
  for key in path:
    if isinstance(cur, dict):
      cur = cur.get(key)
    elif isinstance(cur, list) and isinstance(key, int) and -len(cur) <= key < len(cur):
      cur = cur[key]
    else:
      return default
    if cur is None:
      return default
  return cur


def _f(v: object) -> float | None:
  """A finite float, or None."""
  if isinstance(v, bool):
    return None
  try:
    f = float(v)  # type: ignore[arg-type]
  except (TypeError, ValueError):
    return None
  return f if math.isfinite(f) else None


def nv(v: object, nd: int = 2, prefix: str = "", suffix: str = "", sign: bool = False, na: str = NA) -> str:
  """A number for the reader.  A missing value gives ``na`` alone, with no unit and no currency sign."""
  f = _f(v)
  if f is None:
    return na
  return f"{prefix}{f:+,.{nd}f}{suffix}" if sign else f"{prefix}{f:,.{nd}f}{suffix}"


def usd(v: object, nd: int = 2) -> str:
  return nv(v, nd, prefix="$")


def pct(v: object, nd: int = 1, sign: bool = True) -> str:
  return nv(v, nd, suffix="%", sign=sign)


def _gnum(v: object, prefix: str = "") -> str:
  f = _f(v)
  return NA if f is None else f"{prefix}{f:g}"


def _par(text: str) -> str:
  """``（text）``, or nothing when the text is missing."""
  return f"（{text}）" if text and text != NA else ""


_TOKEN = re.compile(r"[$＄]?[+\-−]?(?<![A-Za-z0-9_])(?:None|n/a|nan|null|undefined)(?:%|M|x)?(?![A-Za-z0-9_])", re.I)
_ONLY_NA = re.compile(r"\s*[（(]\s*暫缺\s*[）)]")
_EMPTY_BR = re.compile(r"\s*(?:\(\s*\)|（\s*）)")
_BARE_USD = re.compile(r"[$＄](?![\d+\-−.,])")
_LABEL = re.compile(r"^\s*[^：:。，；]{1,10}：")
_SP_NA = re.compile(r"(?<=[\u3400-\u9fff])[ \t]+(?=暫缺)")


def clean(text: object, note: str = "資料暫缺") -> str:
  """A stored model string as reader text: no placeholder token reaches the page.

  Each token goes together with its unit (``$None``, ``None%``, ``$n/aM``) and becomes 暫缺.  A
  sentence that then holds two or more 暫缺 says nothing, so ``note`` replaces it; a leading label
  such as ``籌碼：`` stays.  Empty brackets and a ``$`` with no number are removed.
  """
  s = "" if text is None else str(text)
  if not s:
    return ""
  if not (_TOKEN.search(s) or _EMPTY_BR.search(s) or _BARE_USD.search(s)):
    return s
  parts = []
  for part in re.split(r"(?<=。)", s):
    t = _ONLY_NA.sub("", _TOKEN.sub(NA, part))
    if t.count(NA) >= 2:
      m = _LABEL.match(part)
      t = (m.group(0) if m else "") + note + ("。" if part.rstrip().endswith("。") else "")
    parts.append(t)
  s = _BARE_USD.sub("", _EMPTY_BR.sub("", "".join(parts)))
  return re.sub(r"[ \t]{2,}", " ", _SP_NA.sub("", s)).strip()


def tx(v: object, note: str = "資料暫缺") -> str:
  """Escaped reader text of a stored model string."""
  return esc(clean(v, note))


def sx(v: object, note: str = "資料暫缺") -> str:
  """Escaped reader text for a table cell or a label.  A text of at most 16 characters stays on one line."""
  t = clean(v, note)
  return f'<span class="nw">{esc(t)}</span>' if 0 < len(t) <= 16 else esc(t)


def _phr(v: object, note: str = "資料暫缺") -> str:
  """A short reading such as ``偏防禦 (0.70-0.85)``: it may break before the bracket and nowhere else."""
  t = clean(v, note)
  if not t or len(t) > 24:
    return esc(t)
  head, sep, tail = t.partition(" (")
  return f'<span class="nw">{esc(head)}</span>' + (f' <span class="nw">({esc(tail)}</span>' if sep else "")


def ext(v: object) -> str:
  """Escaped text from an outside source (a news title, a publisher), marked so a script can tell it from model text."""
  return f'<span data-ext="1">{esc(v)}</span>'


def _link(url: object, inner: str) -> str:
  """``inner`` as a link when the URL is plain http(s); otherwise ``inner`` alone."""
  u = str(url or "").strip()
  if re.fullmatch(r"https?://[^\s<>\"'`]+", u, re.I):
    return f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{inner}</a>'
  return inner


def _pill(score: object) -> str:
  f = _f(score)
  if f is None:
    return f'<span class="pill s-zero">{NA}</span>'
  i = int(f)
  cls = {2: "s-pos2", 1: "s-pos1", 0: "s-zero", -1: "s-neg1", -2: "s-neg2"}.get(i, "s-pos2" if i > 2 else ("s-neg2" if i < -2 else "s-zero"))
  return f'<span class="pill {cls}">{i:+d}</span>'


def _mmdd(d: object) -> str:
  d = str(d or "")
  return d[5:].replace("-", "/") if len(d) >= 10 else d


def _cat_short(cat: object) -> str:
  return re.sub(r"^\s*\d+\.\s*", "", str(cat or "").split("(")[0]).strip()


def _short_title(title: object) -> str:
  return str(title or "").split("：", 1)[-1].split(" (")[0].strip()


def options_missing(p: dict) -> bool:
  o = p.get("options") or {}
  return not o.get("total_contracts") or not o.get("focus_strikes")


def _rows(v: object) -> list[dict]:
  return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []


def _fold(sec: str, k: int, title: str, body: str) -> str:
  if not body:
    return ""
  return f'<details class="fold" data-fold="{sec}-{k}"><summary>{esc(title)}</summary><div class="fold-b">{body}</div></details>'


def _swipe_table(head: str, body: str, cls: str, attrs: str = "") -> str:
  return f'<div class="tbl-wrap"><table class="tbl {cls}"{attrs}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>'


def _gauge_tile(p: dict, key: str, note: str = "資料暫缺") -> str:
  """One of the six dashboard gauges, beside the evidence of its subject.  A grey gauge has no reading and is not drawn."""
  gz = next((x for x in _rows(g(p, "dashboard", "gauges")) if x.get("key") == key), None)
  if not gz or gz.get("light") == "grey":
    return ""
  short, value = clean(gz.get("short") or gz.get("value"), note), clean(gz.get("value"), note)
  lines = [esc(value)] if value and value != short else []
  if gz.get("detail"):
    lines.append(tx(gz.get("detail"), note))
  if gz.get("caveat"):
    lines.append("注意：" + tx(gz.get("caveat"), note))
  fields = "、".join(f"<code>{esc(f)}</code>" for f in (gz.get("fields") or [])[:5])
  if fields:
    lines.append("欄位：" + fields)
  return (f'<div class="dz-tile {esc(gz.get("light"))}" data-gauge="{esc(key)}"><div class="dz-t">{esc(gz.get("emoji"))} {esc(gz.get("title"))}</div>'
          f'<div class="dz-v">{esc(short)}</div><div class="dz-m">{tx(gz.get("meaning"), note)}</div><div class="dz-d">{"<br>".join(lines)}</div></div>')


# --------------------------------------------------------------------------- #
# takeaways: one line per section, computed from the data
# --------------------------------------------------------------------------- #
def _take_plan(p: dict) -> tuple[str, str]:
  tp = p.get("trade_plan") or {}
  if not tp:
    return "missing", MISSING["plan"]
  side, ep, stop = tp.get("side"), _f(g(tp, "entry", "price")), _f(g(tp, "stop", "price"))
  if side == "long" and tp.get("tradeable"):
    return "ok", (f"可以進場 {usd(ep)}；停損 {usd(stop)}" if ep is not None else f"買訊成立；停損 {usd(stop)}")
  if side == "long":
    return "ok", f"買訊成立但風報比 {nv(tp.get('rr_blend'), 2)}R 不到門檻；先等"
  if side == "long_pending":
    return "ok", (f"買點未觸發；收盤站上 {usd(ep)} 才進場" if ep is not None else "買點未觸發；先等")
  return "ok", (f"不開新倉；持有者停損 {usd(stop)}" if stop is not None else "不開新倉；今天沒有買點")


def _take_why(p: dict) -> tuple[str, str]:
  sc = p.get("scoring") or {}
  score = _f(sc.get("composite_score"))
  if score is None:
    return "missing", MISSING["why"]
  cons = sc.get("consensus") or g(p, "playbook", "beginner", "consensus", default={})
  return "ok", f"綜合評分 {score:+.2f}：偏空 {int(_f(cons.get('n_sell')) or 0)} 項、偏多 {int(_f(cons.get('n_buy')) or 0)} 項"


def _take_paths(p: dict) -> tuple[str, str]:
  scen = {s.get("key"): s for s in _rows(g(p, "playbook", "scenarios"))}
  a, c = scen.get("A"), scen.get("C")
  if not a or not c or _f(a.get("prob")) is None or _f(c.get("prob")) is None:
    return "missing", MISSING["paths"]
  return "ok", f"10 日劇本：{_short_title(a.get('title'))} {_f(a['prob']):.0f}%、{_short_title(c.get('title'))} {_f(c['prob']):.0f}%"


def _zone(today: dict) -> str:
  return str(today.get("zone") or "").split("；")[0].split(" (")[0].strip()


def _take_crash(p: dict) -> tuple[str, str]:
  today = g(p, "early_warning", "today", default={})
  score = _f(today.get("score"))
  if score is None:
    return "missing", MISSING["crash"]
  zone = _zone(today)
  return "ok", f"崩跌指數 {score:.1f}" + _par(zone) + f"；{int(_f(today.get('n_active')) or 0)} 項前兆成立"


def _take_mood(p: dict) -> tuple[str, str]:
  sen = p.get("sentiment") or {}
  pulse, vx = sen.get("pulse") or {}, sen.get("vix") or {}
  score, ratio = _f(pulse.get("score")), _f(vx.get("ratio_vix_3m"))
  if score is None and ratio is None:
    return "missing", MISSING["mood"]
  left = f"市場脈搏 {score:.0f}" + _par(str(pulse.get("rating_zh") or "").split(" ")[0]) if score is not None else "市場脈搏暫缺"
  right = f"VIX/VIX3M {ratio:.2f} {TERM_ZH.get(str(vx.get('term_state')), '')}".strip() if ratio is not None else "VIX 期限結構暫缺"
  return "ok", f"{left}；{right}"


def _take_options(p: dict) -> tuple[str, str]:
  o = p.get("options") or {}
  if options_missing(p):
    return "missing", MISSING["options"]
  walls = "、".join(f"{name} 牆 {_gnum(o.get(key), '$')}" for name, key in (("Put", "put_wall"), ("Call", "call_wall")) if _f(o.get(key)) is not None)
  gex = _f(o.get("total_net_gex_m"))
  tail = f"淨 Gamma {gex:+,.1f}M" if gex is not None else "淨 Gamma 暫缺"
  return "ok", f"{walls}；{tail}" if walls else tail


def _take_sector(p: dict) -> tuple[str, str]:
  hm = p.get("heatmap") or {}
  cons = _rows(hm.get("constituents"))
  if not cons:
    return "missing", MISSING["sector"]
  up = sum(1 for c in cons if c.get("above_sma20"))
  ret = _f(hm.get("weighted_ret_1d"))
  return "ok", f"{len(cons)} 檔成分股 {up} 檔站上月線" + (f"；加權單日 {ret:+.1f}%" if ret is not None else "")


def _take_news(p: dict) -> tuple[str, str]:
  fl = p.get("newsflash") or {}
  if not fl or not fl.get("label"):
    return "missing", MISSING["news"]
  flags = sum(1 for v in (fl.get("flags") or {}).values() if v)
  net = _f(fl.get("net"))
  return "ok", f"新聞氣壓{fl.get('label')}" + (f"（淨影響 {net:+.2f}）" if net is not None else "") + f"；{flags} 個風險旗標"


def _take_proof(p: dict) -> tuple[str, str]:
  bt = p.get("backtest") or {}
  sm = bt.get("summary") or {}
  if not bt.get("signals") or not sm:
    return "missing", MISSING["proof"]
  return "ok", f"今日觸發 {len(sm.get('fired_today') or [])} 個訊號；A/B 級買訊 {len(sm.get('fired_long_ab') or [])} 個"


def _take_lessons(p: dict) -> tuple[str, str]:
  pm = p.get("postmortem") or {}
  if not pm or _f(pm.get("peak_close")) is None or _f(pm.get("trough_close")) is None:
    return "missing", MISSING["lessons"]
  return "ok", f"高點 {usd(pm.get('peak_close'))} → 低點 {usd(pm.get('trough_close'))}：{pct(pm.get('soxl_drawdown_pct'))}"


_TAKERS = {"plan": _take_plan, "why": _take_why, "paths": _take_paths, "crash": _take_crash, "mood": _take_mood,
           "options": _take_options, "sector": _take_sector, "news": _take_news, "proof": _take_proof, "lessons": _take_lessons}


def takeaways(p: dict) -> dict[str, dict]:
  """``{section id: {"state": "ok" | "missing" | "error", "text": the takeaway}}`` in page order.  Never raises."""
  out: dict[str, dict] = {}
  for sid in SECTION_IDS:
    try:
      state, text = _TAKERS[sid](p)
      text = clean(text)
    except Exception:  # noqa: BLE001 - a broken input must not take the page down
      state, text = "error", ERROR_LINE
    if len(text) > TAKEAWAY_MAX:
      text = text[: TAKEAWAY_MAX - 1].rstrip() + "…"
    out[sid] = {"state": state, "text": text}
  return out


# --------------------------------------------------------------------------- #
# 1. plan
# --------------------------------------------------------------------------- #
def _beginner_block(p: dict) -> dict:
  """The feed's own beginner block (``brief._beginner_block``), so the page and the feed read the same."""
  from . import brief as briefmod
  b = g(p, "playbook", "beginner", default={})
  try:
    return briefmod._beginner_block(p.get("scoring") or {}, b, p.get("trade_plan") or {}, b.get("plan") or {}, p.get("newsflash") or None, [],
                                    g(p, "early_warning", "today", default={}), p.get("technicals") or {})
  except Exception:  # noqa: BLE001
    return {}


def _kv(rows: list[tuple[str, str]], attrs: str = "") -> str:
  body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows if v)
  return f'<table class="kv"{attrs}><tbody>{body}</tbody></table>' if body else ""


def _simple_plan(p: dict) -> str:
  plan = g(p, "playbook", "beginner", "plan", default={})
  if not plan:
    return ""
  levels = "".join(
      f'<div class="{cls}"><div class="lv-k">{name}</div><div class="lv-p">{usd(plan.get(key + "_price"))}</div><div class="lv-l">{tx(plan.get(key + "_label"))}{_par(pct(plan.get(key + "_dist_pct")))}</div></div>'
      for cls, name, key in (("stop", "跌破就要跑（停損）", "stop"), ("t1", "第一道關卡（反彈減碼點）", "target1"), ("t2", "站上才算轉強", "target2")))
  rr = _f(plan.get("risk_reward"))
  tail = [f"進場條件：{tx(plan.get('entry'))}" if plan.get("entry") else "", f"第一目標對停損的報酬風險比 {rr:g}" if rr is not None else "",
          f"部位上限 {nv(plan.get('max_size_pct'), 0)}% 的規劃金額" if _f(plan.get("max_size_pct")) is not None else ""]
  return (f'<div class="card" data-block="simple-plan"><div class="card-h">以現價計算的簡易計畫<span class="small">舊版的反彈單算法；正式計畫以上面的交易計畫為準</span></div>'
          f'<div class="lv">{levels}</div><div class="small lv-n">{"。".join(t for t in tail if t)}。</div></div>')


def _plan_parts(p: dict, state: str) -> tuple[str, list[str]]:
  tp = p.get("trade_plan") or {}
  pb = p.get("playbook") or {}
  b = pb.get("beginner") or {}
  bg = _beginner_block(p)
  note = OPT_NOTE if options_missing(p) else "資料暫缺"
  main = ""
  detail = ""
  if tp:
    st, t1, t2, sz, ts, en = (tp.get(k) or {} for k in ("stop", "t1", "t2", "size", "time_stop", "entry"))
    side = tp.get("side")
    rr, min_rr = _f(tp.get("rr_blend")), _f(tp.get("min_rr")) or 1.5
    gate = ""
    if rr is not None:
      need = _f(tp.get("trade_if_entry"))
      gate = ' <span class="g-ok">達標</span>' if rr >= min_rr else ' <span class="g-bad">不足</span>' + (f'<span class="nw">：進場價需 ≤ {usd(need)}</span>' if need is not None else "")
    if side == "no_trade":
      size = f"今天 0%；觸發後 {nv(sz.get('if_triggered_pct'), 1)}% 帳戶"
    elif side == "long_pending":
      size = f"觸發後 {nv(sz.get('if_triggered_pct'), 1)}% 帳戶"
    else:
      size = f"{nv(sz.get('pct'), 1)}% 帳戶"
    main = _kv([
        ("進場" if side == "long" else "進場條件", tx(en.get("rule")) or NA),
        ("停損", f'<span class="nw"><b data-f="stop">{usd(st.get("price"))}</b>{_par(pct(st.get("dist_pct")))}</span>'),
        ("目標", f'<span class="nw">T1 <b data-f="t1">{usd(t1.get("price"))}</b>{_par(nv(t1.get("rr"), 2, suffix="R"))}</span>｜<span class="nw">T2 <b data-f="t2">{usd(t2.get("price"))}</b>{_par(nv(t2.get("rr"), 2, suffix="R"))}</span>'),
        ("風報比", f'<span class="nw">加權 <b data-f="rr">{nv(rr, 2, suffix="R")}</b></span><span class="nw">（門檻 {nv(min_rr, 1)}R）</span>{gate}'),
        ("倉位", size + _par("評級上限 " + nv(sz.get("verdict_cap_pct"), 0, suffix="%", na=""))),
    ], ' data-plan-table')
    rows = [
        ("停損依據", "；".join(x for x in (tx(st.get("basis")), "新倉與舊倉唯一的出場價") if x)),
        ("T1 來源", tx(t1.get("label"))), ("T2 來源", tx(t2.get("label"))),
        ("倉位算法", f"每筆風險 {nv(sz.get('risk_per_trade_pct'), 1)}% ÷ 停損距離；連續 3 次停損 = {nv(sz.get('three_stops_pct'), 1)}%" if _f(sz.get("risk_per_trade_pct")) is not None else ""),
        ("時間停損", tx(ts.get("rule"))),
        ("失效條件", "；".join(tx(x) for x in (tp.get("invalidation") or []))),
    ]
    why = "".join(f"<li>{tx(e)}</li>" for e in (tp.get("explain") or [])[:4])
    hd = tp.get("holder") or {}
    holder = ""
    if hd:
      reduce = "、".join(f"{usd(r.get('price'))}{_par(clean(r.get('label')))}" for r in _rows(hd.get("reduce_into")))
      holder = (f'<div class="note"><b>已持有者</b>：{tx(hd.get("verdict_action"))} 硬停損 {usd(hd.get("hard_stop"))}{_par(clean(hd.get("hard_stop_label")))}；{tx(hd.get("trail_note"))}。'
                + (f" 減碼點：{esc(reduce)}。" if reduce else "") + f" {tx(hd.get('edge_note'))}</div>")
    rg = tp.get("regime") or {}
    own, idx = rg.get("soxl_own") or {}, rg.get("underlying") or {}
    regime = ""
    if own and idx:
      regime = (f'<div class="note"><b>200 日線濾網（兩種讀法）</b>：SOXL 自身 → {"持有" if own.get("in_market") else "空手"}（距年線 {pct(own.get("dist_pct"))}；9 年年化 {pct(own.get("cagr_pct"), 1, False)}、切換 {nv(own.get("switches"), 0)} 次）；'
                f'{tx(idx.get("series"))} 指數 ±3% 帶 2 日確認 → {"持有" if idx.get("in_market") else "空手"}（距年線 {pct(idx.get("dist_pct"))}，出場線 {usd(idx.get("exit_below"))}；年化 {pct(idx.get("cagr_pct"), 1, False)}、'
                f'最大回撤 {pct(idx.get("max_dd_pct"), 1, False)}、切換 {nv(idx.get("switches"), 0)} 次）。'
                + ("兩種讀法今天不一致：長期持有者看指數那條，短線反彈單看 SOXL 自身。" if rg.get("agree") is False else "") + "</div>")
    detail = (f'<div class="plan-head">{tx(tp.get("headline"))}</div>{_kv(rows)}' + (f'<ul class="bul">{why}</ul>' if why else "") + holder + regime)
  detail += _gauge_tile(p, "add_on", note) + _simple_plan(p)

  qa = "".join(f'<div class="qa"><div class="qa-q">{q}</div><div class="qa-a">{tx(b.get(key), note)}</div></div>'
               for q, key in (("我沒有部位，現在能買嗎？", "q_no_position"), ("我已經持有，該怎麼辦？", "q_holder"), ("什麼時候才可以買？", "q_when")) if b.get(key))
  answer = ""
  buy = bg.get("buy") or {}
  if buy.get("text"):
    answer = f'<div class="note" data-block="buy-text"><b>為什麼是「{esc(buy.get("answer"))}」</b>：{tx(buy.get("text"), note)}</div>'
  size_html = ""
  if _f(b.get("size_pct")) is not None:
    size = int(_f(b.get("size_pct")) or 0)
    tone = "bull" if size >= 50 else ("neutral" if size >= 25 else "bear")
    size_html = (f'<div class="card"><div class="card-h">建議 SOXL 曝險上限<span class="small">佔你原本打算投入 SOXL 的最大金額</span></div>'
                 f'<div class="size-bar"><div class="size-fill {tone}" style="width:{max(min(size, 100), 2)}%"></div><span class="size-lbl">{size}%</span></div>'
                 f'<div class="small">{tx(b.get("size_note"), note)}。3 倍槓桿 ETF 不管燈號多綠，都不要超過總資產的 10–15%。</div></div>')
  risks = [clean(r, note) for r in (bg.get("risk_48h") or []) if r]
  risk_html = f'<div class="note"><b>48 小時內風險</b>（新聞旗標與崩跌指數）：{esc("；".join(risks))}</div>' if risks else ""
  qa_html = answer + (f'<div class="qa-grid">{qa}</div>' if qa else "") + size_html + risk_html

  checks = ""
  for c in _rows(pb.get("checklist")):
    now = clean(c.get("now"), note)
    blank = now in ("", NA)
    mark = "✅" if c.get("ok") else "❌"
    checks += (f'<li class="{"ok" if c.get("ok") else "no"}"><span class="chk">{mark}</span> {sx(c.get("item"), note)} '
               f'<span class="chk-now">{"資料暫缺" if blank else esc(now)}</span>' + ('<div class="small">沒有讀數；模型仍把這一項算作成立</div>' if blank and c.get("ok") else "") + "</li>")
  watch = "".join(f"<li>{tx(w, note)}</li>" for w in (b.get("watch") or []) if w)
  n_ok, n_all = _f(pb.get("checklist_passed")), _f(pb.get("checklist_total"))
  count = f"（{n_ok:.0f}/{n_all:.0f} 項成立）" if n_ok is not None and n_all is not None else ""
  chk_html = ((f'<div class="small">{tx(pb.get("checklist_verdict"), note)}</div><ul class="checks">{checks}</ul>' if checks else "")
              + (f'<div class="card"><div class="card-h">本週觀察清單<span class="small">哪些數字變了就要重看</span></div><ul class="bul">{watch}</ul></div>' if watch else ""))
  return main, [_fold("plan", 1, "計畫細節與持有者規則", detail), _fold("plan", 2, "三問三答與倉位上限", qa_html),
                _fold("plan", 3, f"重返多頭檢核表{count}與觀察清單" if checks else "本週觀察清單", chk_html)]


# --------------------------------------------------------------------------- #
# 2. why
# --------------------------------------------------------------------------- #
def indicator_chart_svg(tech: dict) -> str:
  """Close with the 20, 50 and 200-day averages and the Bollinger band, then MACD, then KD.

  These are the lines of the former price chart that the combined chart does not draw.  Candles and
  volume are on the combined chart and are not repeated here.
  """
  series = [r for r in _rows(tech.get("chart_series")) if _f(r.get("close")) is not None]
  n = len(series)
  if n < 2:
    return ""
  w, h = 760, 536
  pl, pr = 54, 16
  pw, x_r = w - pl - pr, w - pr
  p_top, p_h, m_top, m_h, k_top, k_h, date_y = 40, 188, 268, 104, 412, 92, 524

  def x(i: int) -> float:
    return pl + (i + 0.5) * pw / n

  vals = [f for r in series for key in ("close", "sma20", "sma50", "sma200", "bb_upper", "bb_lower") if (f := _f(r.get(key))) is not None and f > 0]
  lo, hi = min(vals) * 0.97, max(vals) * 1.02
  if hi <= lo:
    hi = lo + 1.0

  def yp(v: float) -> float:
    return p_top + p_h - (v - lo) / (hi - lo) * p_h

  def line(key: str, yf, attrs: str) -> str:
    pts = [f"{x(i):.1f},{yf(f):.1f}" for i, r in enumerate(series) if (f := _f(r.get(key))) is not None]
    return f'<polyline fill="none" {attrs} points="{" ".join(pts)}"/>' if len(pts) > 1 else ""

  def lab(name: str, key: str, fmt: str = "${:,.1f}") -> str:
    f = _f(tech.get(key))
    return f"　{name}" + (" " + fmt.format(f) if f is not None else "")

  out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="SOXL 均線、布林帶、MACD 與 KD"><rect width="100%" height="100%" fill="#0b1120" rx="10"/>']
  out.append(_legend_text(pl, 26, [("收盤與均線", "#f8fafc", True), ("　━ 收盤", "#e2e8f0", False), (lab("━ 20MA", "sma20"), "#38bdf8", False), (lab("━ 50MA", "sma50"), "#f59e0b", False),
                                   (lab("┅ 200MA", "sma200"), "#c084fc", False), ("　┆ 布林帶", "#7dd3fc", False)], 12))
  nd = 0 if hi - lo >= 5 else 2
  for k in range(5):
    pv = lo + (hi - lo) * k / 4
    out.append(f'<line x1="{pl}" y1="{yp(pv):.1f}" x2="{x_r}" y2="{yp(pv):.1f}" stroke="#1e293b" stroke-dasharray="3,3" data-bg="1"/>'
               f'<text x="{pl - 8}" y="{yp(pv) + 4:.1f}" fill="#94a3b8" font-size="12" text-anchor="end">${pv:,.{nd}f}</text>')
  ticks = _date_ticks(n, x, 84)
  for i in ticks:
    for top, hh in ((p_top, p_h), (m_top, m_h), (k_top, k_h)):
      out.append(f'<line x1="{x(i):.1f}" y1="{top}" x2="{x(i):.1f}" y2="{top + hh}" stroke="#1e293b" stroke-width="1" data-bg="1"/>')
  up_pts = [(x(i), yp(f)) for i, r in enumerate(series) if (f := _f(r.get("bb_upper"))) is not None]
  lo_pts = [(x(i), yp(f)) for i, r in enumerate(series) if (f := _f(r.get("bb_lower"))) is not None]
  if len(up_pts) > 2 and len(lo_pts) > 2:
    path = " ".join(f"{a:.1f},{b:.1f}" for a, b in up_pts) + " " + " ".join(f"{a:.1f},{b:.1f}" for a, b in reversed(lo_pts))
    out.append(f'<polygon points="{path}" fill="#38bdf8" fill-opacity="0.06" stroke="none"/>')
  out += [line("bb_upper", yp, 'stroke="#38bdf8" stroke-width="0.8" stroke-dasharray="2,3"'), line("bb_lower", yp, 'stroke="#38bdf8" stroke-width="0.8" stroke-dasharray="2,3"'),
          line("sma200", yp, 'stroke="#c084fc" stroke-width="1.8" stroke-dasharray="5,3"'), line("sma50", yp, 'stroke="#f59e0b" stroke-width="1.8"'),
          line("sma20", yp, 'stroke="#38bdf8" stroke-width="1.8"'), line("close", yp, 'stroke="#f8fafc" stroke-width="1.4"')]
  # ---- MACD
  mv = [abs(f) for r in series for key in ("macd", "macd_signal", "macd_hist") if (f := _f(r.get(key))) is not None]
  if mv:
    m_abs = max(mv) * 1.1 or 1.0
    y0 = m_top + m_h / 2

    def ym(v: float) -> float:
      return y0 - v / m_abs * (m_h / 2)

    out.append(_legend_text(pl, m_top - 12, [("MACD (12,26,9)", "#f8fafc", True), (lab("━ DIF", "macd", "{:+.2f}"), "#38bdf8", False), (lab("━ DEA", "macd_signal", "{:+.2f}"), "#f59e0b", False),
                                             (lab("▮ 柱", "macd_hist", "{:+.2f}"), "#94a3b8", False)], 12))
    out.append(f'<line x1="{pl}" y1="{m_top}" x2="{x_r}" y2="{m_top}" stroke="#334155" data-bg="1"/><line x1="{pl}" y1="{y0:.1f}" x2="{x_r}" y2="{y0:.1f}" stroke="#475569" stroke-dasharray="3,3" data-bg="1"/>'
               f'<text x="{pl - 8}" y="{y0 + 4:.1f}" fill="#64748b" font-size="11.5" text-anchor="end">0</text>')
    bw = max(2.0, pw / n * 0.64)
    for col, keep in (("#10b981", lambda v: v >= 0), ("#f43f5e", lambda v: v < 0)):
      bars = "".join(f'<rect x="{x(i) - bw / 2:.1f}" y="{min(y0, ym(f)):.1f}" width="{bw:.1f}" height="{max(1.0, abs(ym(f) - y0)):.1f}"/>'
                     for i, r in enumerate(series) if (f := _f(r.get("macd_hist"))) is not None and keep(f))
      if bars:
        out.append(f'<g fill="{col}" fill-opacity="0.65">{bars}</g>')
    out += [line("macd", ym, 'stroke="#38bdf8" stroke-width="1.6"'), line("macd_signal", ym, 'stroke="#f59e0b" stroke-width="1.5"')]

  # ---- KD
  def yk(v: float) -> float:
    return k_top + k_h - (max(-15.0, min(115.0, v)) + 15) / 130 * k_h

  if any(_f(r.get("k9")) is not None for r in series):
    out.append(_legend_text(pl, k_top - 12, [("KD / KDJ (9,3,3)", "#f8fafc", True), (lab("━ K", "k9", "{:.1f}"), "#38bdf8", False), (lab("━ D", "d9", "{:.1f}"), "#f59e0b", False),
                                             (lab("┅ J", "j9", "{:.1f}"), "#c084fc", False), ("　80 超買 / 20 超賣", "#94a3b8", False)], 12))
    out.append(f'<line x1="{pl}" y1="{k_top}" x2="{x_r}" y2="{k_top}" stroke="#334155" data-bg="1"/>')
    for lvl, col in ((80, "#f43f5e"), (50, "#475569"), (20, "#10b981")):
      out.append(f'<line x1="{pl}" y1="{yk(lvl):.1f}" x2="{x_r}" y2="{yk(lvl):.1f}" stroke="{col}" stroke-dasharray="3,3" stroke-opacity="0.6" data-bg="1"/>'
                 f'<text x="{pl - 8}" y="{yk(lvl) + 4:.1f}" fill="#64748b" font-size="11.5" text-anchor="end">{lvl}</text>')
    out += [line("k9", yk, 'stroke="#38bdf8" stroke-width="1.6"'), line("d9", yk, 'stroke="#f59e0b" stroke-width="1.6"'), line("j9", yk, 'stroke="#c084fc" stroke-width="1.1" stroke-dasharray="2,2"')]
  for i in ticks:
    lbl = _mmdd(series[i].get("date"))
    out.append(f'<text x="{_place_x(x(i), _tw(lbl, 12), 4, w - 4):.1f}" y="{date_y}" fill="#94a3b8" font-size="12" text-anchor="middle">{esc(lbl)}</text>')
  out.append("</svg>")
  return "".join(out)


def _why_parts(p: dict, state: str) -> tuple[str, list[str]]:
  sc, pb, tech = p.get("scoring") or {}, p.get("playbook") or {}, p.get("technicals") or {}
  b = pb.get("beginner") or {}
  dash = p.get("dashboard") or {}
  opt_gone = options_missing(p)
  note = OPT_NOTE if opt_gone else "資料暫缺"
  grades = {str(x.get("category")): x.get("grade") for x in _rows(dash.get("factor_grades"))}
  cats = _rows(sc.get("category_scores"))
  body = ""
  for c in cats:
    score = _f(c.get("avg_score"))
    tone = "up" if (score or 0) > 0.15 else ("dn" if (score or 0) < -0.15 else "")
    body += (f'<tr><td class="nw">{esc(_cat_short(c.get("category")))}</td><td class="mono nw {tone}">{nv(score, 2, sign=True)}</td>'
             + (f'<td class="nw"><b>{esc(grades.get(str(c.get("category")), "—"))}</b></td>' if grades else "") + f'<td class="mono nw">{nv(c.get("weight"), 0)}</td></tr>')
  main = ""
  if body:
    cap = [f"趨勢面 {nv(sc.get('trend_score'), 2, sign=True)}" if _f(sc.get("trend_score")) is not None else "",
           f"逆勢與情緒面 {nv(sc.get('contrarian_score'), 2, sign=True)}" if _f(sc.get("contrarian_score")) is not None else "",
           (f"信心 {esc(b.get('confidence') or sc.get('confidence'))}" + (f"（7 個維度中 {nv(b.get('agreement_pct') if b.get('agreement_pct') is not None else sc.get('agreement_pct'), 0)}% 同方向）"
                                                                    if _f(b.get("agreement_pct") if b.get("agreement_pct") is not None else sc.get("agreement_pct")) is not None else ""))
           if (b.get("confidence") or sc.get("confidence")) else "",
           f"總評 {esc(dash.get('overall_grade'))}" if dash.get("overall_grade") else ""]
    main = (f'<table class="mt" data-category-table><thead><tr><th>維度</th><th>平均分（±2）</th>' + ("<th>等級</th>" if grades else "") + f'<th>權重</th></tr></thead><tbody>{body}</tbody></table>'
            f'<div class="sec-cap">{"｜".join(x for x in cap if x)}</div>')

  # ---- fold 1: every scored factor
  factors = _rows(sc.get("factors"))
  kind_zh = {"trend": "趨勢", "contrarian": "逆勢", "flow": "籌碼"}
  rows = ""
  n_blank, w_blank = 0, 0.0
  for f in factors:
    blank = opt_gone and "期權籌碼" in str(f.get("category"))
    if blank:
      n_blank += 1
      w_blank += _f(f.get("weight")) or 0.0
    value = "資料暫缺" if blank else sx(f.get("value"), note)
    why = "期權資料暫缺，這一項沒有讀數；模型仍把它計入評分。" if blank else sx(f.get("rationale"), note)
    score = _f(f.get("score"))
    rows += (f'<tr class="row" data-score="{int(score) if score is not None else 0}"{" data-blank=\"1\"" if blank else ""}><td><span class="cat">{esc(_cat_short(f.get("category")))}</span><br>'
             f'<span class="kind k-{esc(f.get("kind"))}">{esc(kind_zh.get(f.get("kind"), f.get("kind")))}</span></td><td class="fw">{sx(f.get("metric"), note)}</td><td class="mono small">{value}</td>'
             f'<td class="center">{_pill(score)}<div class="crit">{tx(f.get("criteria"), note)}</div></td><td class="rat">{why}</td></tr>')
  score_html = ""
  if rows:
    warn = (f'<div class="note" data-block="options-scored-blank">期權資料這次暫缺：期權籌碼的 {n_blank} 項沒有讀數，表中標示「資料暫缺」。模型仍把它們計入評分（權重 {w_blank:g} / {_gnum(sc.get("total_weight"))}）。</div>'
            if n_blank else "")
    score_html = (warn + f'<div class="filters"><button class="fbtn active" type="button" data-filter="all">全部 ({len(factors)})</button><button class="fbtn" type="button" data-filter="bull">🟢 加分</button>'
                  '<button class="fbtn" type="button" data-filter="neutral">⚪ 中性</button><button class="fbtn" type="button" data-filter="bear">🔴 扣分</button></div>'
                  + _swipe_table('<th class="c-grp2">維度/類型</th><th class="c-name">指標</th><th class="c-read">實測</th><th class="center c-score">評分 / 標準</th><th>意義</th>', rows, "w-760", " data-score-table"))

  # ---- fold 2: the rating meter, the weight bar, both cases, the context of the score
  cons = b.get("consensus") or sc.get("consensus") or {}
  meter = ""
  pos = _f(b.get("rating_pos") if b.get("rating_pos") is not None else sc.get("rating_pos"))
  if pos is not None and cons:
    ratio = cons.get("buy_sell_ratio")
    meter = (f'<div class="card"><div class="card-h">五區評級儀表與權重比<span class="small">{len(factors)} 項指標加權投票</span></div>{_meter_svg(pos, str(b.get("rating_label") or sc.get("rating_label") or ""))}'
             f'<div class="small center">🔴 偏空 {esc(cons.get("n_sell", 0))} 項（其中 −2 有 {esc(cons.get("n_strong_sell", 0))}）· 🟡 中性 {esc(cons.get("n_hold", 0))} 項 · 🟢 偏多 {esc(cons.get("n_buy", 0))} 項（其中 +2 有 {esc(cons.get("n_strong_buy", 0))}）</div>'
             f'{_ratio_bar(cons)}<div class="small">買進對賣出的權重比 {esc(ratio) if _f(ratio) is not None else "∞"}（大於 1.5 偏多，小於 0.67 偏空）。紅色超過一半就不要買；綠色超過一半，加上檢核表 6 項以上成立，才是買點。'
             f'頁首的評級再看趨勢與檢核條件，所以可能和儀表的分區不同。</div></div>')
  tldr = "".join(f"<li>{tx(t, note)}</li>" for t in (b.get("tldr") or []) if t)

  def case(items: object, up: bool) -> str:
    lis = "".join(f'<li><div class="case-h"><b>{sx(x.get("metric"), note)}</b><span class="pts {"up" if up else "dn"}">{nv(x.get("pts"), 0, sign=True)}</span></div><div class="small">{tx(x.get("value"), note)}</div></li>'
                  for x in _rows(items))
    return lis or f'<li class="small">目前沒有明顯的{"多" if up else "空"}方因子</li>'

  cases = (f'<div class="two"><div class="card case bull"><div class="card-h">多方論點（為什麼可能漲）</div><ul class="case-list">{case(b.get("bull_case"), True)}</ul></div>'
           f'<div class="card case bear"><div class="card-h">空方論點（為什麼可能跌）</div><ul class="case-list">{case(b.get("bear_case"), False)}</ul></div></div>'
           '<div class="small">每一項的說明在上一格評分表的「意義」欄。</div>') if (b.get("bull_case") or b.get("bear_case")) else ""
  ctx = [f"5 日 {pct(tech.get('ret_5d'))}" if _f(tech.get("ret_5d")) is not None else "", f"20 日 {pct(tech.get('ret_20d'))}" if _f(tech.get("ret_20d")) is not None else "",
         f"距 52 週高點 {pct(tech.get('drawdown_from_52w_high_pct'))}" if _f(tech.get("drawdown_from_52w_high_pct")) is not None else "",
         f"連跌 {nv(tech.get('consec_down_days'), 0)} 日" if _f(tech.get("consec_down_days")) is not None else ""]
  bullets = "".join(f"<li>{tx(x, note)}</li>" for x in (pb.get("bullets") or []) if x)
  score_line = (f'綜合評分 {nv(sc.get("composite_score"), 2, sign=True)}（滿分 ±2）' + (f' → {tx(sc.get("verdict"), note)}' if sc.get("verdict") else "")) if _f(sc.get("composite_score")) is not None else ""
  context = (f'<div class="card"><div class="card-h">評分的背景</div>'
             + (f'<div class="score-line">{score_line}</div>' if score_line else "")
             + (f'<div class="small">{"｜".join(x for x in ctx if x)}</div>' if any(ctx) else "")
             + (f'<div class="regime">{tx(sc.get("regime"), note)}</div>' if sc.get("regime") else "")
             + (f'<div class="headline">{tx(pb.get("headline"), note)}</div>' if pb.get("headline") else "")
             + (f'<div class="small">{tx(b.get("one_liner"), note)}</div>' if b.get("one_liner") else "")
             + (f'<ul class="bul">{bullets}</ul>' if bullets else "") + "</div>") if (bullets or sc.get("regime") or pb.get("headline")) else ""
  vc = dash.get("voices") or {}
  dot = {"bear": "🔴", "bull": "🟢", "neutral": "🟡"}
  voices = "".join(f'<div><span class="nw">{tx(r.get("voice"), note)}</span><span>{dot.get(r.get("tone"), "⚪")} {tx(r.get("reading"), note)}</span></div>' for r in _rows(vc.get("rows")))
  voice_html = f'<div class="card"><div class="card-h">四個聲音</div><div class="small"><b>{tx(vc.get("summary"), note)}</b></div><div class="dz-voices">{voices}</div></div>' if voices else ""
  case_html = meter + (f'<div class="tldr"><div class="card-h">三行看完</div><ol>{tldr}</ol></div>' if tldr else "") + cases + context + voice_html

  # ---- fold 3: the indicator table and the lines the combined chart does not draw
  tech_rows = "".join(f'<tr><td class="nw">{sx(t.get("group"))}</td><td class="fw">{sx(t.get("name"))}</td><td class="mono small">{sx(t.get("reading"), note)}</td>'
                      f'<td class="center">{_pill(t.get("score"))}<div class="crit">{tx(t.get("signal"), note)}</div></td><td class="rat">{sx(t.get("detail"), note)}</td></tr>' for t in _rows(tech.get("tech_table")))
  chart = indicator_chart_svg(tech)
  tech_html = ((f'<div class="chart-scroll ind" data-viz="indicators">{chart}</div><div class="swipe">⇆ 圖表可左右滑動</div>' if chart else "")
               + (_swipe_table('<th class="c-grp">類別</th><th class="c-name">指標</th><th class="c-read">讀數</th><th class="center c-score">評分 / 訊號</th><th>說明</th>', tech_rows, "w-760") if tech_rows else ""))
  n_tech = len(_rows(tech.get("tech_table")))
  return main, [_fold("why", 1, f"{len(factors)} 項指標評分表", score_html), _fold("why", 2, "多空論點與評級儀表", case_html),
                _fold("why", 3, f"{n_tech} 項技術指標明細與均線、MACD、KD 圖" if n_tech else "均線、MACD、KD 圖", tech_html)]


# --------------------------------------------------------------------------- #
# 3. paths
# --------------------------------------------------------------------------- #
def _paths_parts(p: dict, state: str) -> tuple[str, list[str]]:
  pb = p.get("playbook") or {}
  scen = _rows(pb.get("scenarios"))
  main = ""
  if state == "ok":
    bars = ""
    for s in scen:
      tone = s.get("tone") if s.get("tone") in TONE_COL else "neutral"
      prob = max(0.0, min(100.0, _f(s.get("prob")) or 0.0))
      bars += (f'<div class="pb-name" data-scenario="{esc(s.get("key"))}">{TONE_EMOJI[tone]} {esc(_short_title(s.get("title")))}</div>'
               f'<div class="pb-bar"><div class="pb-fill" style="width:{max(prob, 2):.0f}%;background:{TONE_COL[tone]}"></div></div><div class="pb-pct" data-prob="{prob:.0f}">{prob:.0f}%</div>')
    ref = clean(pb.get("analog_reference")) or "全部交易日"
    # the sample behind the three odds: the days that met the condition overlap, so the count of separate episodes sits next to it
    cond = next((c for c in _rows(g(p, "early_warning", "analogs", "conditions")) if c.get("condition") == pb.get("analog_reference")), {})
    n_days, n_eps = _f(cond.get("n_days")), _f(cond.get("n_episodes"))
    sample = ""
    if n_days is not None:
      sample = f'<span class="nw" data-analog-n="{n_days:.0f}">，樣本 {n_days:.0f} 個交易日</span>' + (f'<span class="nw" data-analog-episodes="{n_eps:.0f}">、{n_eps:.0f} 次獨立事件</span>' if n_eps is not None else "")
    main = f'<div class="pb" data-viz="scenarios">{bars}</div><div class="sec-cap">機率來自歷史同類情境之後 10 日的實際分佈：{esc(ref)}{sample}</div>'
  cards = "".join(
      f'<div class="scen {esc(s.get("tone") if s.get("tone") in TONE_COL else "neutral")}"><div class="scen-head"><span class="scen-title">{tx(s.get("title"))}</span>'
      + (f'<span class="scen-prob">機率 {nv(s.get("prob"), 0)}%</span>' if _f(s.get("prob")) is not None else "") + "</div>"
      f'<div class="scen-row"><b>觸發：</b>{tx(s.get("trigger"))}</div><div class="scen-row"><b>目標：</b>{tx(s.get("target"))}</div><div class="scen-act">{tx(s.get("action"))}</div></div>' for s in scen)
  scen_html = (f'<div class="scen-grid">{cards}</div><div class="small">機率是過去出現同樣情境後的實際結果，不是預言。用它決定倉位大小，不是用來重押。</div>') if cards else ""
  ladder = "".join(f'<div class="rung {esc(l.get("kind"))}"><div class="rung-val">{usd(l.get("price"))}</div><div class="rung-lbl">{tx(l.get("label"))}</div><div class="rung-note">{tx(l.get("note"))}</div></div>'
                   for l in _rows(pb.get("ladder")))
  ladder_html = f'<div class="small">由上而下：反壓、現價、支撐</div><div class="ladder">{ladder}</div>' if ladder else ""
  return main, [_fold("paths", 1, "三種劇本的觸發與做法", scen_html), _fold("paths", 2, "關鍵價位階梯", ladder_html)]


# --------------------------------------------------------------------------- #
# 4. crash
# --------------------------------------------------------------------------- #
def _crash_parts(p: dict, state: str) -> tuple[str, list[str]]:
  ews = p.get("early_warning") or {}
  today = ews.get("today") or {}
  es = ews.get("event_study") or {}
  active = sorted((c for c in _rows(ews.get("contributions")) if (_f(c.get("points")) or 0) > 0), key=lambda c: -(_f(c.get("points")) or 0))

  def rows(items: list[dict]) -> str:
    return "".join(f'<tr><td>{sx(c.get("label"))}</td><td class="nw">{sx(c.get("family"))}</td><td class="mono nw">{nv(c.get("points"), 1, sign=True)}</td></tr>' for c in items)

  head = "<thead><tr><th>成立的前兆</th><th>家族</th><th>分數</th></tr></thead>"
  main = ""
  if state == "ok":
    main = (f'<table class="mt" data-precursor-table>{head}<tbody>{rows(active[:3])}</tbody></table>' if active else '<p class="sec-none">目前沒有前兆成立</p>')
  zone_note = "；".join(str(today.get("zone") or "").split("；")[1:]).strip()
  rest = active[3:]
  st80 = es.get("stats_top_80") or {}
  buckets = "".join(f'<tr><td class="mono">{sx(b.get("bucket"))}</td><td class="mono center">{nv(b.get("days"), 0)}</td><td class="mono center">{pct(b.get("pct_drop10"), 1, False)}</td>'
                    f'<td class="mono center">{pct(b.get("pct_crash"), 1, False)}</td><td class="mono center">{pct(b.get("median_fwd_min"))}</td></tr>' for b in _rows(es.get("buckets_top")))
  study = ""
  if es.get("n_days"):
    study = (f'<div class="note" data-block="event-study">過去 {nv(es.get("n_days"), 0)} 個交易日中，5 日內跌 20% 以上的事件共 {nv(es.get("n_episodes"), 0)} 次（每年約 {esc(es.get("episodes_per_year"))} 次）。'
             f'其中起點在 200 日線之上的「頂部型」{nv(es.get("n_top_episodes"), 0)} 次，事前分數達 80 的有 {nv(es.get("top_episodes_flagged"), 0)} 次。</div>')
  bucket_html = ""
  if buckets:
    bucket_html = (f'<div class="card"><div class="card-h">價在 200 日線之上時，依分數分組的後 5 日表現</div>'
                   f'<div class="tbl-wrap"><table class="tbl small w-480"><thead><tr><th>分數區間</th><th class="center">交易日</th><th class="center">5 日內跌 ≥10%</th><th class="center">5 日內跌 ≥20%</th><th class="center">5 日內最大跌幅中位數</th></tr></thead><tbody>{buckets}</tbody></table></div>'
                   f'<div class="note">逐日統計（門檻 80）：命中率 {pct(st80.get("precision_pct"), 1, False)}（基準 {pct(st80.get("base_rate_pct"), 1, False)}，提升 {nv(st80.get("lift"), 2)} 倍）、召回 {pct(st80.get("recall_pct"), 1, False)}。'
                   f'事件統計：分數達 80 的警報段共 {nv(es.get("alert_episodes"), 0)} 次，其中 {nv(es.get("alert_episodes_followed_by_crash"), 0)} 次在 15 個交易日內出現 5 日跌 20% 以上（命中 {pct(es.get("alert_hit_rate_pct"), 0, False)}）。'
                   f'權重是人工設定、不是擬合，樣本有限。請當作風險溫度計：分數高代表減碼，不是放空的理由。</div></div>')
  detail = ((f'<div class="note">{tx(zone_note)}</div>' if zone_note else "")
            + (f'<div class="tbl-wrap"><table class="tbl small" data-precursor-rest>{head}<tbody>{rows(rest)}</tbody></table></div>' if rest else "")
            + _gauge_tile(p, "crash") + study + bucket_html)
  sig_name = {r.get("key"): (str(r.get("label")).split("：")[0] if "：" in str(r.get("label")) else str(r.get("label")).split(" (")[0]) for r in _rows(g(ews, "peak_checklist", "rows")) if r.get("key")}

  def top_signals(e: dict) -> str:
    out = []
    for item in e.get("top_signals") or []:
      if isinstance(item, (list, tuple)) and len(item) == 2:
        out.append(f"{sig_name.get(item[0], item[0])} {nv(item[1], 2)}")
    return "、".join(out)

  episodes = _rows(es.get("episodes"))[::-1]
  ep_rows = "".join(f'<tr><td>{sx(e.get("date"))}</td><td>{usd(e.get("close"))}</td><td class="dn">{pct(e.get("fwd_min_pct"))}</td><td class="t nw">{esc(str(e.get("regime") or "").split(" (")[0])}</td>'
                    f'<td class="center">{nv(e.get("score_max_prev5"), 0, na="—")}</td><td class="center">{"✅" if e.get("flagged") else "✗"}</td><td class="t">{esc(top_signals(e))}</td></tr>' for e in episodes)
  ep_html = (f'<div class="small">類型：頂部型是起點時價在 200 日線之上；下跌延續型是已在 200 日線之下。最新的在上。</div><div class="tbl-wrap tall"><table class="tbl small num w-640"><thead><tr><th>起點</th><th>價格</th><th>5 日最大跌幅</th><th>類型</th>'
             f'<th class="center">事前最高分</th><th class="center">≥80</th><th>當時主要訊號</th></tr></thead><tbody>{ep_rows}</tbody></table></div><div class="swipe t">⇆ 表格可左右滑動</div>') if ep_rows else ""
  return main, [_fold("crash", 1, "全部前兆與歷史實證", detail), _fold("crash", 2, f"逐次崩跌事件（{len(episodes)} 次）", ep_html)]


# --------------------------------------------------------------------------- #
# 5. mood
# --------------------------------------------------------------------------- #
def _mood_parts(p: dict, state: str) -> tuple[str, list[str]]:
  sen, mac, opt = p.get("sentiment") or {}, p.get("macro") or {}, p.get("options") or {}
  fg, vx, pc, fl, xa, pulse = (sen.get(k) or {} for k in ("fear_greed", "vix", "put_call", "flows", "cross_asset", "pulse"))
  note = OPT_NOTE if options_missing(p) else "資料暫缺"
  y10 = next((k for k in _rows(mac.get("macro_kpis")) if "10 年" in str(k.get("name")) or "TNX" in str(k.get("name"))), {})
  main = ""
  if state == "ok":
    term = TERM_ZH.get(str(vx.get("term_state")), "") or str(vx.get("term_zh") or "").split("：")[0]
    table = [
        ("市場脈搏", nv(pulse.get("score"), 0), str(pulse.get("rating_zh") or "").split(" ")[0]),
        ("CNN Fear &amp; Greed", nv(fg.get("score"), 0), str(fg.get("rating_zh") or "").split(" ")[0]),
        ("VIX", nv(vx.get("vix"), 2), clean(vx.get("vix_regime"))),
        ("VIX ÷ VIX3M", nv(vx.get("ratio_vix_3m"), 2), term),
        ("個股 Put/Call", nv(pc.get("equity_pc"), 2), clean(pc.get("equity_read"))),
        ("10 年期殖利率", clean(y10.get("latest")) or NA, clean(y10.get("regime"))),
    ]
    body = "".join(f'<tr><td class="nw">{name}</td><td class="mono nw">{esc(val)}</td><td>{_phr(read) if read and val != NA else ("" if val != NA else "這個來源這次沒有回應")}</td></tr>' for name, val, read in table)
    main = f'<table class="mt" data-mood-table><thead><tr><th>指標</th><th>讀數</th><th>判讀</th></tr></thead><tbody>{body}</tbody></table>'

  comp_rows = "".join(f'<tr><td>{sx(c.get("label"))}</td><td class="center"><b>{nv(c.get("score"), 0)}</b></td><td class="nw">{esc(FG_ZH.get(str(c.get("rating", "")).lower(), clean(c.get("rating"))))}</td></tr>' for c in _rows(fg.get("components")))
  fg_chart = fg_history_svg(fg.get("history") or []) if _rows(fg.get("history")) else ""
  fg_html = ""
  if _f(fg.get("score")) is not None:
    was = "｜".join(f"{name} {nv(fg.get(key), 0)}" for name, key in (("前日", "previous_close"), ("一週前", "week_ago"), ("一月前", "month_ago"), ("一年前", "year_ago")) if _f(fg.get(key)) is not None)
    fg_html = (f'<div class="card"><div class="card-h">CNN Fear &amp; Greed：{nv(fg.get("score"), 0)}{_par(clean(fg.get("rating_zh")))}<span class="small">{was}</span></div>'
               + (f'<div class="chart-scroll sm">{fg_chart}</div><div class="swipe sm">⇆ 圖表可左右滑動</div>' if fg_chart else "")
               + (f'<div class="tbl-wrap"><table class="tbl small nw1"><thead><tr><th>七大子指標</th><th class="center">分數</th><th>評級</th></tr></thead><tbody>{comp_rows}</tbody></table></div>' if comp_rows else "") + "</div>")
  pulse_rows = "".join(f'<tr><td>{sx(x.get("label"))}</td><td class="center"><b>{nv(x.get("score"), 0)}</b></td><td class="center">{nv((_f(x.get("weight")) or 0) * 100, 0)}%</td><td class="rat">{sx(x.get("note"), note)}</td></tr>'
                       for x in _rows(pulse.get("parts")))
  pulse_html = (f'<div class="card"><div class="card-h">市場脈搏的組成（0 恐懼到 100 貪婪）：{nv(pulse.get("score"), 0)} {tx(pulse.get("rating_zh"))}</div>'
                f'<div class="tbl-wrap"><table class="tbl small nw1 w-480"><thead><tr><th>指標</th><th class="center">分數</th><th class="center">權重</th><th>讀數</th></tr></thead><tbody>{pulse_rows}</tbody></table></div></div>') if pulse_rows else ""
  fear_html = (f'<div class="small">這些是逆勢指標：極端恐懼代表反彈機率升高，不等於底部確認。</div><div class="two">{fg_html}{pulse_html}</div>') if (fg_html or pulse_html) else ""

  vix_html = ""
  if _f(vx.get("vix")) is not None:
    vix_html = (f'<div class="card"><div class="card-h">VIX 全家族<span class="small">CBOE 官方資料 {tx(vx.get("date"))}</span></div><div class="tbl-wrap"><table class="tbl small nw1"><tbody>'
                f'<tr><td>VIX / VIX9D / VIX3M / VIX6M</td><td class="mono">{nv(vx.get("vix"), 2)} / {nv(vx.get("vix9d"), 2)} / {nv(vx.get("vix3m"), 2)} / {nv(vx.get("vix6m"), 2)}</td></tr>'
                f'<tr><td>期限結構 VIX/VIX3M</td><td class="mono">{nv(vx.get("ratio_vix_3m"), 3)} → {tx(vx.get("term_zh")) or NA}</td></tr>'
                f'<tr><td>VIX 1 年百分位 / 5 日變化 / 近 5 日盤中高</td><td class="mono">{pct(vx.get("vix_percentile_1y"), 0, False)} / {pct(vx.get("vix_5d_chg_pct"), 0)} / {nv(vx.get("vix_intraday_high_5d"), 2)}</td></tr>'
                f'<tr><td>VVIX（波動率的波動）</td><td class="mono">{nv(vx.get("vvix"), 1)}{_par(clean(vx.get("vvix_regime")))}</td></tr>'
                f'<tr><td>SKEW（尾部風險定價）</td><td class="mono">{nv(vx.get("skew"), 1)}{_par(clean(vx.get("skew_regime")))}</td></tr>'
                f'<tr><td>VIX1D（當日事件恐慌）</td><td class="mono">{nv(vx.get("vix1d"), 2)}</td></tr></tbody></table></div></div>')
  pc_html = ""
  if _f(pc.get("total_pc")) is not None or _f(pc.get("equity_pc")) is not None:
    pc_html = (f'<div class="card"><div class="card-h">Put/Call 與資金流<span class="small">CBOE 市場統計 {tx(pc.get("date"))}</span></div><div class="tbl-wrap"><table class="tbl small"><tbody>'
               f'<tr><td>全市場 Total P/C（單日 / 5 日 / 20 日）</td><td class="mono">{nv(pc.get("total_pc"), 2)} / {nv(pc.get("total_pc_5d"), 2)} / {nv(pc.get("total_pc_20d"), 2)}{_par(clean(pc.get("total_read")))}</td></tr>'
               f'<tr><td>個股 Equity P/C（單日 / 5 日 / 20 日）</td><td class="mono">{nv(pc.get("equity_pc"), 2)} / {nv(pc.get("equity_pc_5d"), 2)} / {nv(pc.get("equity_pc_20d"), 2)}{_par(clean(pc.get("equity_read")))}</td></tr>'
               f'<tr><td>指數 / SPX / VIX 選擇權 P/C</td><td class="mono">{nv(pc.get("index_pc"), 2)} / {nv(pc.get("spx_pc"), 2)} / {nv(pc.get("vix_pc"), 2)}</td></tr>'
               + (f'<tr><td>SOXL / SOXS 成交金額比（散戶行為）</td><td class="mono">{nv(g(fl, "latest", "ratio"), 2)}（20 日均 {nv(fl.get("ratio_avg20"), 2)}）{_par(clean(fl.get("read")))}</td></tr>' if _f(g(fl, "latest", "ratio")) is not None else "")
               + "</tbody></table></div></div>")
  vol_html = (f'<div class="two">{vix_html}{pc_html}</div>' if (vix_html or pc_html) else "") + _gauge_tile(p, "put_call", note)

  mac_rows = "".join(f'<tr><td class="fw">{sx(k.get("name"))}</td><td class="mono">{sx(k.get("latest")) or NA}</td><td class="mono">{sx(k.get("chg_1d")) or NA}</td><td class="mono">{sx(k.get("chg_20d")) or NA}</td>'
                     f'<td class="mono center">{nv(k.get("corr_20d"), 2, sign=True)}</td><td class="mono center">{nv(k.get("corr_60d"), 2, sign=True)}</td><td class="rat">{sx(k.get("regime"))} {tx(k.get("beta_note"))}</td></tr>'
                     for k in _rows(mac.get("macro_kpis")))
  xa_rows = "".join(f'<tr><td>{sx(a.get("label"))}</td><td class="mono">{nv(a.get("last"), 2)}</td><td class="mono">{pct(a.get("chg_5d_pct"), 2)}</td><td class="mono">{pct(a.get("chg_20d_pct"), 2)}</td>'
                    f'<td class="mono">{pct(a.get("percentile_1y"), 0, False)}</td></tr>' for a in _rows(xa.get("assets")) if a.get("available"))
  macro_html = ((_swipe_table('<th>指標</th><th>最新</th><th>1 日</th><th>20 日</th><th class="center">20 日相關</th><th class="center">60 日相關</th><th>解讀</th>', mac_rows, "small nw1 nwm w-760") if mac_rows
                 else '<p class="sec-none">宏觀資料暫缺：Yahoo Finance 這次沒有回應</p>')
                + (f'<div class="tbl-wrap"><table class="tbl small nw1 nwm w-480"><thead><tr><th>跨資產風險溫度計</th><th>最新</th><th>5 日</th><th>20 日</th><th>1 年百分位</th></tr></thead><tbody>{xa_rows}</tbody></table></div>' if xa_rows else "")
                + _gauge_tile(p, "macro", note))
  return main, [_fold("mood", 1, "Fear & Greed 與市場脈搏", fear_html), _fold("mood", 2, "VIX 家族與 Put/Call", vol_html), _fold("mood", 3, "宏觀跨資產與 SOXL 的相關性", macro_html)]


# --------------------------------------------------------------------------- #
# 6. options
# --------------------------------------------------------------------------- #
def _options_parts(p: dict, state: str) -> tuple[str, list[str]]:
  if state != "ok":
    return "", []   # the one missing line stands for every options block: no chart, no table, no fold
  opt, tech = p.get("options") or {}, p.get("technicals") or {}
  spot = _f(opt.get("cboe_spot")) or _f(tech.get("close")) or 0.0
  wall = options_wall_svg(_rows(opt.get("focus_strikes")), spot, _f(opt.get("gamma_flip")), _f(opt.get("near_max_pain")))
  main = (f'<div class="legend"><i class="lg c"></i>Call 未平倉<i class="lg p"></i>Put 未平倉<span class="lg-note">虛線：現價、Gamma 翻正、近月 Max Pain</span></div>'
          f'<div class="chart-scroll sm" data-viz="options-wall">{wall}</div><div class="swipe sm">⇆ 圖表可左右滑動</div>') if wall else ""
  gex = _f(opt.get("total_net_gex_m"))
  kpis = (f'<div class="kpis"><div class="kpi"><div class="kpi-l">Put/Call 成交</div><div class="kpi-v">{nv(opt.get("pc_vol_ratio"), 2)}</div></div>'
          f'<div class="kpi"><div class="kpi-l">淨 Gamma</div><div class="kpi-v {"dn" if (gex or 0) < 0 else "up"}">{nv(gex, 1, suffix="M", sign=True)}</div></div>'
          f'<div class="kpi"><div class="kpi-l">Gamma 翻正位</div><div class="kpi-v">{nv(opt.get("gamma_flip"), 0, prefix="$", na="算不出來")}</div></div>'
          f'<div class="kpi"><div class="kpi-l">IV30</div><div class="kpi-v">{pct(opt.get("iv30_pct"), 0, False)}</div></div></div>')
  walls = "｜".join(x for x in (
      f"CBOE 選擇權鏈 {nv(opt.get('total_contracts'), 0)} 檔合約" if _f(opt.get("total_contracts")) is not None else "",
      f"Put 牆 {_gnum(opt.get('put_wall'), '$')}（未平倉 {nv(opt.get('put_wall_oi'), 0)}）" if _f(opt.get("put_wall")) is not None else "",
      f"Call 牆 {_gnum(opt.get('call_wall'), '$')}（未平倉 {nv(opt.get('call_wall_oi'), 0)}）" if _f(opt.get("call_wall")) is not None else "",
      f"近月 Max Pain {_gnum(opt.get('near_max_pain'), '$')}" if _f(opt.get("near_max_pain")) is not None else "",
      f"月選 Max Pain {_gnum(opt.get('monthly_max_pain'), '$')}{_par(clean(opt.get('monthly_expiration')))}" if _f(opt.get("monthly_max_pain")) is not None else "") if x)
  wh = opt.get("whale") or {}
  trades = _rows(wh.get("top_whale_trades"))[:12]
  whale_rows = "".join(
      f'<tr><td class="mono">{sx(t.get("expiration"))}{_par(nv(t.get("dte"), 0, suffix="d"))}</td><td class="center"><b class="{"up" if t.get("type") == "C" else "dn"}">{tx(t.get("type"))}</b> {_gnum(t.get("strike"), "$")} '
      f'<span class="small">{_par(pct(t.get("moneyness_pct"), 0))}</span></td><td class="mono">{nv(t.get("volume"), 0)}</td><td class="mono">{nv(t.get("open_interest"), 0)} <span class="small">{_par(nv(t.get("vol_oi"), 1, suffix="x"))}</span></td>'
      f'<td class="mono">{nv(t.get("premium_m"), 2, prefix="$", suffix="M")}</td><td class="mono">{pct(t.get("iv_pct"), 0, False) if _f(t.get("iv_pct")) else "—"}</td><td>{sx(t.get("bias"))}</td></tr>' for t in trades)
  whale_html = ""
  if whale_rows:
    whale_html = (f'<div class="card"><div class="card-h">大戶期權大單<span class="small">權利金 ≥ $25 萬或 ≥ 1,500 口，且成交量對未平倉 ≥ 0.4</span></div>'
                  + (f'<div class="small" data-block="whale-net">大戶淨方向 <b>{nv(wh.get("whale_net_score"), 2, sign=True)}</b>（−1 全看空，+1 全看多）：看多 {nv(wh.get("whale_bull_prem_m"), 1, prefix="$", suffix="M")} 對看空 {nv(wh.get("whale_bear_prem_m"), 1, prefix="$", suffix="M")}</div>'
                     if _f(wh.get("whale_net_score")) is not None else "")
                  + f'<div class="small">{nv(wh.get("whale_count"), 0)} 筆｜大單 Call {nv(wh.get("whale_call_prem_m"), 1, prefix="$", suffix="M")} 對 Put {nv(wh.get("whale_put_prem_m"), 1, prefix="$", suffix="M")}｜散戶小單 Call/Put {nv(wh.get("retail_cp_ratio"), 2)}</div>'
                  + _swipe_table('<th>到期</th><th class="center">合約</th><th>成交量</th><th>未平倉 (Vol/OI)</th><th>權利金</th><th>IV</th><th>解讀</th>', whale_rows, "small nwm w-760") + "</div>")
  sec = opt.get("secondary") or {}
  soxx, soxs = sec.get("SOXX") or {}, sec.get("SOXS") or {}
  peers = "｜".join(x for x in (
      f"SOXX 期權 Put/Call 成交 {nv(soxx.get('pc_vol_ratio'), 2)}" if _f(soxx.get("pc_vol_ratio")) is not None else "",
      f"SOXX 淨 Gamma {nv(soxx.get('net_gex_m'), 0, suffix='M')}" if _f(soxx.get("net_gex_m")) is not None else "",
      f"SOXS Put/Call 成交 {nv(soxs.get('pc_vol_ratio'), 2)}" if _f(soxs.get("pc_vol_ratio")) is not None else "") if x)
  detail = (kpis + (f'<div class="note">{esc(walls)}</div>' if walls else "") + whale_html + _gauge_tile(p, "whales")
            + (f'<div class="note" data-block="peer-options">{esc(peers)}</div>' if peers else ""))

  fc = opt.get("forecast") or {}
  em_rows = "".join(f'<tr><td>{lbl}</td><td class="mono">{sx(e.get("expiration"))}{_par(nv(e.get("dte"), 0, suffix="d"))}</td><td class="mono">±{nv(e.get("expected_move_pct"), 1)}%</td>'
                    f'<td class="mono">{usd(e.get("low"))} ~ {usd(e.get("high"))}</td><td class="mono">{pct(e.get("atm_iv_pct"), 0, False)}</td></tr>'
                    for lbl, e in (("週選", fc.get("weekly")), ("月選", fc.get("monthly")), ("季選", fc.get("quarterly"))) if isinstance(e, dict) and e)
  cone_rows = "".join(f'<tr><td>{sx(c.get("horizon"))}</td><td class="mono">±{nv(c.get("one_sigma_pct"), 1)}%</td><td class="mono">{usd(c.get("p16"))} ~ {usd(c.get("p84"))}</td>'
                      f'<td class="mono">{usd(c.get("p2_5"))} ~ {usd(c.get("p97_5"))}</td></tr>' for c in _rows(fc.get("iv_cone")))
  prob_rows = "".join(f'<tr><td class="mono">{_gnum(r.get("level"), "$")}{_par(pct(r.get("vs_spot_pct"), 0))}</td><td class="mono">{pct(r.get("prob_above_at_expiry_pct"), 0, False)}</td>'
                      f'<td class="mono">{pct(r.get("prob_below_at_expiry_pct"), 0, False)}</td><td class="mono">{pct(r.get("prob_touch_pct"), 0, False)}</td></tr>' for r in _rows(fc.get("prob_table")))
  term = "；".join(x for x in (
      "IV 期限結構：" + " / ".join(f"{name} {pct(fc.get(key), 0, False)}" for name, key in (("近月", "iv_near_pct"), ("中期", "iv_mid_pct"), ("遠月", "iv_far_pct")) if _f(fc.get(key)) is not None)
      + (f" → {clean(fc.get('iv_term_structure'))}" if fc.get("iv_term_structure") else "") if any(_f(fc.get(k)) is not None for k in ("iv_near_pct", "iv_mid_pct", "iv_far_pct")) else "",
      f"25Δ 偏度（Put IV − Call IV）{pct(opt.get('iv_skew_25d'))}" if _f(opt.get("iv_skew_25d")) is not None else "") if x)
  move_html = ""
  if em_rows or cone_rows:
    move_html = (f'<div class="card"><div class="card-h">期權隱含的預期波動（ATM 跨式）</div>'
                 + (f'<div class="tbl-wrap"><table class="tbl small nw1 nwm"><thead><tr><th>到期</th><th>日期</th><th>預期波動</th><th>1σ 區間</th><th>ATM IV</th></tr></thead><tbody>{em_rows}</tbody></table></div>' if em_rows else "")
                 + (f'<div class="note">{esc(term)}</div>' if term else "")
                 + (f'<div class="tbl-wrap"><table class="tbl small nw1 nwm"><thead><tr><th>IV 機率錐</th><th>1σ</th><th>68% 區間</th><th>95% 區間</th></tr></thead><tbody>{cone_rows}</tbody></table></div>' if cone_rows else "") + "</div>")
  prob_html = ""
  if prob_rows:
    exp = clean(g(fc, "monthly", "expiration"))
    prob_html = (f'<div class="card"><div class="card-h">月選到期{_par(exp)}的價位機率</div>'
                 f'<div class="tbl-wrap"><table class="tbl small nw1 nwm"><thead><tr><th>價位</th><th>到期在上方</th><th>到期在下方</th><th>期間觸及</th></tr></thead><tbody>{prob_rows}</tbody></table></div>'
                 '<div class="note">機率由選擇權隱含波動率推算（對數常態、風險中性），反映市場定價而不是預言。3 倍 ETF 的 IV 本身很高，區間會很寬。</div></div>')
  forecast_html = f'<div class="two">{move_html}{prob_html}</div>' if (move_html or prob_html) else ""
  return main, [_fold("options", 1, "未平倉牆數字與大戶大單", detail), _fold("options", 2, "預期波動與價位機率", forecast_html)]


# --------------------------------------------------------------------------- #
# 7. sector
# --------------------------------------------------------------------------- #
def _tile_bg(v: float) -> str:
  return "rgba(16,185,129,.42)" if v >= 5 else ("rgba(16,185,129,.22)" if v >= 0 else ("rgba(244,63,94,.22)" if v > -3 else "rgba(244,63,94,.42)"))


def _sector_parts(p: dict, state: str) -> tuple[str, list[str]]:
  hm = p.get("heatmap") or {}
  cons = _rows(hm.get("constituents"))
  if state != "ok":
    return "", []
  tiles = ""
  for c in cons:
    r1 = _f(c.get("ret_1d"))
    data = "".join(f' data-r{h}="{_f(c.get(key)):.2f}"' for h, key in ((1, "ret_1d"), (5, "ret_5d"), (20, "ret_20d")) if _f(c.get(key)) is not None)
    tiles += (f'<div class="tile"{data} style="background:{_tile_bg(r1) if r1 is not None else "rgba(148,163,184,.14)"}"><b>{tx(c.get("ticker"))}</b>'
              f'<span class="tile-r">{pct(r1, 1) if r1 is not None else NA}</span></div>')
  main = (f'<div class="hm-bar"><span class="small">單一成分股的報酬</span><span class="btns"><button class="fbtn active" type="button" data-h="1">1 日</button><button class="fbtn" type="button" data-h="5">5 日</button>'
          f'<button class="fbtn" type="button" data-h="20">20 日</button></span></div><div class="tiles hm" data-tiles data-viz="heatmap">{tiles}</div>')
  rows = "".join(
      f'<tr><td class="nw"><b>{tx(c.get("ticker"))}</b> <span class="small">{tx(c.get("name"))}</span></td><td class="mono">{pct(c.get("weight"), 1, False)}</td><td class="mono">{usd(c.get("close"), 1)}</td>'
      f'<td class="mono">{pct(c.get("ret_1d"), 2)}</td><td class="mono">{pct(c.get("ret_5d"), 1)}</td><td class="mono">{pct(c.get("ret_20d"), 1)}</td><td class="mono">{nv(c.get("rsi14"), 0)}</td>'
      f'<td class="center">{"上" if c.get("above_sma20") else "下"} / {"上" if c.get("above_sma50") else "下"} / {"上" if c.get("above_sma200") else "下"}</td></tr>' for c in cons)
  breadth = "｜".join(f"站上 {name} {pct(hm.get(key), 0, False)}" for name, key in (("20 日線", "breadth_above_sma20_pct"), ("50 日線", "breadth_above_sma50_pct"), ("200 日線", "breadth_above_sma200_pct")) if _f(hm.get(key)) is not None)
  sub_rows = "".join(f'<tr><td>{sx(s.get("subsector"))}</td><td class="mono">{pct(s.get("weight"), 1, False)}</td><td class="mono">{nv(s.get("count"), 0)}</td><td class="mono">{pct(s.get("ret_1d"), 2)}</td>'
                     f'<td class="mono">{pct(s.get("ret_5d"), 1)}</td><td class="mono">{pct(s.get("ret_20d"), 1)}</td><td class="mono">{nv(s.get("avg_rsi"), 0)}</td></tr>' for s in _rows(hm.get("subsectors")))
  detail = ((f'<div class="small">{esc(breadth)}</div>' if breadth else "")
            + _swipe_table('<th>成分股</th><th>權重</th><th>收盤</th><th>1 日</th><th>5 日</th><th>20 日</th><th>RSI</th><th class="center">20 / 50 / 200 日線</th>', rows, "small nwm w-640")
            + (_swipe_table('<th>次產業</th><th>權重</th><th>檔數</th><th>1 日</th><th>5 日</th><th>20 日</th><th>平均 RSI</th>', sub_rows, "small nw1 nwm w-480") if sub_rows else "")
            + _gauge_tile(p, "soxx"))
  return main, [_fold("sector", 1, f"{len(cons)} 檔明細、次產業與費半走向", detail)]


# --------------------------------------------------------------------------- #
# 8. news
# --------------------------------------------------------------------------- #
def _dot(impact: object) -> str:
  v = _f(impact) or 0
  return "🔴" if v < 0 else ("🟢" if v > 0 else "⚪")


def _news_parts(p: dict, state: str) -> tuple[str, list[str]]:
  fl = p.get("newsflash") or {}
  nws = p.get("news") or {}
  top = _rows(fl.get("top"))
  main = ""
  if state == "ok" and top:
    body = ""
    for r in top[:3]:
      meta = " · ".join(x for x in (ext(r.get("publisher")) if r.get("publisher") else "", esc(r.get("time_tpe")) + " 台北" if r.get("time_tpe") else "") if x)
      body += (f'<tr><td class="nw">{_dot(r.get("impact"))} {nv(r.get("impact"), 0, sign=True)}</td><td class="nw">{sx(r.get("category"))}</td><td>{_link(r.get("link"), ext(r.get("title")))}'
               + (f'<div class="nf-meta">{meta}</div>' if meta else "") + (f'<div class="nf-why">→ {tx(r.get("why_zh"))}</div>' if r.get("why_zh") else "") + "</td></tr>")
    main = f'<table class="mt nf-top" data-news-table><thead><tr><th>影響</th><th>類別</th><th>標題與對 SOXL 的影響</th></tr></thead><tbody>{body}</tbody></table>'
  elif state == "ok":
    main = '<p class="sec-none">過去 36 小時沒有與 SOXL 相關的重大時事</p>'

  flash_html = ""
  if fl:
    bg = _beginner_block(p)
    biggest = str(bg.get("biggest_thing") or "").replace("今天最大的事：", "", 1)
    cats = " ".join(f'<span class="nf-tag">{tx(c.get("emoji"))}{tx(c.get("category"))} {nv(c.get("neg"), 0)} 空 / {nv(c.get("pos"), 0)} 多</span>' for c in _rows(fl.get("by_category"))[:6])
    items = ""
    for r in top[3:8]:
      items += (f'<div class="nf-item"><div>{_dot(r.get("impact"))}</div><div><b>{tx(r.get("emoji"))} {tx(r.get("category"))}</b> <span class="nf-meta">{esc(r.get("time_tpe"))} 台北 · {ext(r.get("publisher"))} · 影響 {nv(r.get("impact"), 0, sign=True)}</span><br>'
                f'{_link(r.get("link"), ext(r.get("title")))}<div class="nf-why">→ {tx(r.get("why_zh"))}</div></div></div>')
    sa = ""
    for t in _rows(fl.get("seeking_alpha"))[:6]:
      sa += (f'<div class="nf-item"><div>{_dot(t.get("impact"))}</div><div><span class="nf-meta">{tx(t.get("symbol"))} · {tx(t.get("kind"))} · {esc(t.get("time_tpe"))} 台北 · {tx(t.get("tone"))}</span><br>{_link(t.get("link"), ext(t.get("title")))}</div></div>')
    cautions = "".join(f'<div class="nf-caution">⚠️ {tx(c.get("text"))}<br><span class="nf-meta">依據：{ext(g(c, "evidence", "publisher"))}「{ext(g(c, "evidence", "title"))}」</span></div>' for c in _rows(fl.get("cautions"))[:4])
    errs = [str(e) for e in (fl.get("errors") or [])[:2]]
    flash_html = ((f'<div class="note" data-block="biggest-thing"><b>今天最大的事</b>：{ext(biggest)}</div>' if biggest else "")
                  + f'<div class="nf-bar">{nv(fl.get("n_relevant"), 0)} 則相關時事，抓取時間 {esc(fl.get("fetched_at_tpe"))} 台北<br>{cats}</div>{items}'
                  + (f'<div class="nf-bar nf-sa"><b>Seeking Alpha 觀點</b>（SOXL、SOXX、NVDA 近 72 小時；「分析」是投稿作者意見，「新聞」是 SA 新聞台）</div>{sa}' if sa else "") + cautions
                  + (f'<div class="small">部分來源這次失敗（{len(errs)} 個）</div>' if errs else "")
                  + f'<div class="small">{tx(fl.get("method"))} 這一區只是閱讀輔助，不改變 24 因子評級；交易計畫只把旗標當作警語。</div>')

  def day(d: dict) -> str:
    def heads(items: object, dot: str) -> str:
      return "".join(f'<li data-ext="1">{dot} <span class="tagz">{tx(h.get("zh_tag"))}</span> {esc(h.get("title"))} <span class="small{" nw" if len(str(h.get("publisher") or "")) <= 14 else ""}">（{esc(h.get("publisher"))}）</span></li>' for h in _rows(items)[:4])
    ratio = _f(d.get("net_sentiment_ratio")) or 0.0
    tone = "bull" if ratio >= 0.15 else ("bear" if ratio <= -0.15 else "neutral")
    perf = "｜".join(f"{name} {clean(d.get(key))}" for name, key in (("SOXL", "soxl_perf"), ("VIX", "vix_perf"), ("10Y", "tnx_perf")) if clean(d.get(key)) not in ("", NA))
    return (f'<div class="news {tone}"><div class="news-h"><b>{tx(d.get("date"))}</b> {esc(perf)} <span class="badge">利多 {nv(d.get("bull_count"), 0)} 對 利空 {nv(d.get("bear_count"), 0)}</span></div>'
            f'<ul>{heads(d.get("top_bull_headlines"), "🟢")}{heads(d.get("top_bear_headlines"), "🔴")}</ul></div>')

  feed = _rows(nws.get("daily_feed"))
  daily_html = ""
  if feed:
    daily_html = (f'<div class="small">近 7 日利多 {nv(nws.get("recent_bull_count"), 0)} 則、利空 {nv(nws.get("recent_bear_count"), 0)} 則，共 {nv(nws.get("total_unique_articles"), 0)} 則。依關鍵字分類，不是 AI 判讀。</div>'
                  + "".join(day(d) for d in feed))
  return main, [_fold("news", 1, "其餘時事與警語", flash_html), _fold("news", 2, f"近 {len(feed)} 個交易日的利多與利空新聞", daily_html)]


# --------------------------------------------------------------------------- #
# 9. proof
# --------------------------------------------------------------------------- #
def lights_svg(lights: object, hist: object) -> str:
  """Price of the last sessions over the price-only traffic light of each session, with one dot per stored daily rating."""
  pts = [r for r in _rows(lights) if _f(r.get("close")) is not None and r.get("light") in TONE_COL]
  if len(pts) < 5:
    return ""
  w, h = 760, 214
  pl, pr, pt, pb = 52, 70, 16, 44
  cw, ch = w - pl - pr, h - pt - pb
  closes = [_f(r.get("close")) or 0.0 for r in pts]
  lo, hi = min(closes), max(closes)
  rng = (hi - lo) or 1.0
  n = len(pts)
  bw = cw / n

  def ypos(c: float) -> float:
    return pt + ch - (c - lo) / rng * ch

  bands, start = "", 0
  for i in range(1, n + 1):   # one band per run of equal lights
    if i == n or pts[i]["light"] != pts[start]["light"]:
      bands += f'<rect x="{pl + start * bw:.1f}" y="{pt}" width="{(i - start) * bw + 0.6:.1f}" height="{ch}" fill="{TONE_COL[pts[start]["light"]]}" opacity="0.22" data-bg="1" data-light="{pts[start]["light"]}" data-from="{esc(pts[start].get("date"))}" data-n="{i - start}"/>'
      start = i
  path = " ".join(f"{pl + (i + 0.5) * bw:.1f},{ypos(c):.1f}" for i, c in enumerate(closes))
  by_date = {r.get("date"): i for i, r in enumerate(pts)}
  dots = ""
  for rec in _rows(hist):
    i = by_date.get(rec.get("date"))
    c = _f(rec.get("close"))
    if i is None:
      continue
    # the dot sits on the price line of its date, so a record with another close cannot leave the plot
    dots += (f'<circle cx="{pl + (i + 0.5) * bw:.1f}" cy="{ypos(closes[i]):.1f}" r="5.5" fill="{TONE_COL.get(rec.get("color"), "#94a3b8")}" stroke="#0b1120" stroke-width="2">'
             f'<title>{esc(rec.get("date"))} {tx(rec.get("verdict"))}{" " + usd(c) if c is not None else ""}</title></circle>')
  xl = "".join(f'<text x="{pl + (i + 0.5) * bw:.1f}" y="{h - 14}" text-anchor="middle" fill="#94a3b8" font-size="11">{esc(_mmdd(pts[i].get("date")))}</text>' for i in sorted({0, n // 3, 2 * n // 3, n - 1}))
  yl = (f'<text x="{pl - 6}" y="{pt + 10}" text-anchor="end" fill="#94a3b8" font-size="11">${hi:,.0f}</text><text x="{pl - 6}" y="{pt + ch}" text-anchor="end" fill="#94a3b8" font-size="11">${lo:,.0f}</text>')
  lc = closes[-1]
  ly = min(max(ypos(lc), pt + 8), pt + ch - 2)
  tag_txt = f"${lc:,.0f}" if lc >= 1000 else f"${lc:,.2f}"
  tag_fs = min(12.0, (pr - 14) / max(1.0, _tw(tag_txt, 1.0, bold=True)))
  tag = (f'<line x1="{pl + cw:.1f}" y1="{ypos(lc):.1f}" x2="{pl + cw + 6:.1f}" y2="{ly:.1f}" stroke="#f8fafc" stroke-width="1" data-qa-ok="1"/>'
         f'<text x="{pl + cw + 9:.1f}" y="{ly + 4:.1f}" fill="#f8fafc" font-size="{tag_fs:.1f}" font-weight="700">{esc(tag_txt)}</text>')
  legend = "".join(f'<rect x="{pl + k * 50}" y="{h - 8}" width="10" height="6" fill="{TONE_COL[tone]}" opacity=".6"/><text x="{pl + k * 50 + 14}" y="{h - 2}" fill="#94a3b8" font-size="10">{TONE_ZH[tone]}</text>'
                   for k, tone in enumerate(("bull", "neutral", "bear")))
  legend += f'<circle cx="{pl + 160}" cy="{h - 5}" r="4" fill="#94a3b8" stroke="#0b1120" stroke-width="1.5"/><text x="{pl + 168}" y="{h - 2}" fill="#94a3b8" font-size="10">完整模型每日評級（自動更新累積）</text>'
  return (f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="過去 {n} 天價格與技術燈號">{bands}'
          f'<polyline points="{path}" fill="none" stroke="#f8fafc" stroke-width="2"/>{dots}{xl}{yl}{tag}{legend}</svg>')


def _light_stats(lights: list[dict]) -> dict:
  """How long the latest light has been on.  The same count as ``history.light_stats``, for rows that may lack a key."""
  if not lights:
    return {"current": None, "days": 0, "since": None}
  cur, days, since = lights[-1].get("light"), 0, lights[-1].get("date")
  for r in reversed(lights):
    if r.get("light") != cur:
      break
    days += 1
    since = r.get("date")
  return {"current": cur, "days": days, "since": since}


def _signal_rows(sigs: list[dict], wide: bool) -> str:
  out = ""
  for s in sigs:
    td = s.get("today") or {}
    state = SIGNAL_STATE_ZH.get(td.get("state"), SIGNAL_STATE_ZH["off"])
    pend = td.get("pending") or {}
    if td.get("state") == "pending" and _f(pend.get("price")) is not None:
      state += f'</span> <span class="nw">{esc(pend.get("op") or "")}{usd(pend.get("price"))}'
    dyn = s.get("dyn") or {}
    dyn_txt = (f"<br><small>動態出場 {pct(dyn.get('win_pct'), 0, False)} 對基準 {pct(dyn.get('base_win_pct'), 0, False)}</small>" if wide and _f(dyn.get("win_pct")) is not None else "")
    label = ("買 " if s.get("side") == "long" else "賣 ") + clean(s.get("short_name"))
    name = (f'<span class="nw">{esc(label)}</span>' if len(label) <= 14 else esc(label)) + f'<span class="tp-grade">{tx(s.get("grade"))}{"★" if s.get("significant") else ""}</span>'
    win = f'<span class="nw">{pct(s.get("win_pct"), 0, False)} 對 {pct(g(s, "base", "win_pct"), 0, False)}</span><span class="nw">（N {nv(s.get("n"), 0)}）</span>{dyn_txt}'
    mean = f'<td class="nw">{pct(s.get("mean"), 1)} / {nv(s.get("horizon"), 0)} 日</td>' if wide else ""
    out += f'<tr data-signal="{esc(s.get("key"))}" data-state="{esc(td.get("state") or "off")}"><td>{name}</td><td>{win}</td>{mean}<td><span class="nw">{state}</span></td></tr>'
  return out


def _proof_parts(p: dict, state: str) -> tuple[str, list[str]]:
  bt = p.get("backtest") or {}
  sigs = _rows(bt.get("signals"))
  sm, meth = bt.get("summary") or {}, bt.get("method") or {}
  rank = {"A": 0, "B*": 1, "B": 2, "C": 3, "—": 4}
  shown = [s for s in sigs if (_f(s.get("n")) or 0) >= 20 or g(s, "today", "state") in ("fired", "recent", "pending")]
  shown.sort(key=lambda s: (0 if g(s, "today", "state") == "fired" else 1, rank.get(s.get("grade"), 4), _f(s.get("p_value")) if _f(s.get("p_value")) is not None else 1.0))
  shown = shown[:10]
  main, all_html = "", ""
  if state == "ok" and shown:
    main = f'<table class="mt" data-signal-table><thead><tr><th>訊號</th><th>勝率對基準（N）</th><th>今日</th></tr></thead><tbody>{_signal_rows(shown[:4], False)}</tbody></table>'
    exits = "賣出訊號歷史上沒有一個優於基準，也沒有一個能預測 20 日內 15% 以上的回撤：停損是保險，不是預測。" if not sm.get("exits_predictive") else ""
    all_html = (_swipe_table("<th>訊號</th><th>勝率對基準（N = 樣本數）</th><th>平均報酬 / 期間</th><th>今日狀態</th>", _signal_rows(shown, True), "small w-640", " data-signal-table-full")
                + f'<div class="small">買進訊號的勝率是訊號後 h 日收高的比例，賣出訊號是收低的比例；旁邊永遠附同期基準。等級 A 可靠、B 尚可、B* 顯著但樣本外薄、C 無優勢；★ 是顯著高於基準（p &lt; 0.05）。'
                f'{nv(sm.get("n_graded"), 0)} 個有樣本的訊號中 {nv(sm.get("n_significant"), 0)} 個顯著，多重檢定校正後（BH q &lt; 0.10）剩 {nv(sm.get("n_q_lt_10"), 0)} 個。{exits} '
                f'固定規則，樣本 {tx(meth.get("sample"))}，樣本外是{tx(meth.get("oos"))}；非重疊交易，進場為訊號次日開盤。</div>')
  lights, hist = _rows(p.get("light_history")), _rows(p.get("verdict_history"))
  chart = lights_svg(lights, hist)
  ls = _light_stats(lights)
  cur = (f'目前價格燈號：{TONE_EMOJI.get(ls["current"], "")} {TONE_ZH.get(ls["current"], "")}，已持續 {ls["days"]} 個交易日（自 {esc(_mmdd(ls["since"]))}）。' if ls["current"] in TONE_ZH else "")
  chips = ""
  for r in hist[-21:]:
    tone = r.get("color") if r.get("color") in TONE_COL else "neutral"
    chips += (f'<div class="chip {tone}" title="{esc(r.get("date"))} {tx(r.get("verdict"))} 收盤 {usd(r.get("close"))} 綜合 {nv(r.get("composite"), 2, sign=True)}"><div class="chip-d">{esc(_mmdd(r.get("date")))}</div>'
              f'<div class="chip-e">{RATING_EMOJI.get(r.get("rating_5"), "⚪")}</div><div class="chip-p">{usd(r.get("close"), 0)}</div></div>')
  done = [r for r in hist if _f(r.get("fwd_ret_5d")) is not None]
  check = ""
  if len(done) >= 3:
    body = ""
    for r in done[-15:]:
      f5, f10 = _f(r.get("fwd_ret_5d")), _f(r.get("fwd_ret_10d"))
      body += (f'<tr><td class="nw">{esc(r.get("date"))}</td><td><span class="nw">{RATING_EMOJI.get(r.get("rating_5"), "")} {tx(r.get("verdict"))}</span></td><td class="mono">{nv(r.get("composite"), 2, sign=True)}</td>'
               f'<td class="mono {"up" if (f5 or 0) >= 0 else "dn"}">{pct(f5)}</td><td class="mono {"up" if (f10 or 0) >= 0 else "dn"}">{pct(f10) if f10 is not None else "—"}</td></tr>')

    def avg(rows: list[dict], name: str) -> str:
      xs = [_f(x.get("fwd_ret_5d")) for x in rows]
      xs = [x for x in xs if x is not None]
      return f"{name}評級後 5 日平均 {sum(xs) / len(xs):+.1f}%（{len(xs)} 次）" if xs else f"{name}評級後還沒有樣本"

    bear = [r for r in done if (_f(r.get("rating_5")) or 3) <= 2]
    bull = [r for r in done if (_f(r.get("rating_5")) or 3) >= 4]
    check = (f'<div class="card"><div class="card-h">這套評級準不準：當天評級對之後的實際漲跌</div><div class="tbl-wrap"><table class="tbl small"><thead><tr><th>日期</th><th>當日評級</th><th>綜合</th><th>之後 5 天</th><th>之後 10 天</th></tr></thead>'
             f'<tbody>{body}</tbody></table></div><div class="small">{avg(bear, "偏空")}；{avg(bull, "偏多")}。樣本少時不要過度解讀。</div></div>')
  elif hist:
    check = f'<div class="small">系統從 <b>{esc(hist[0].get("date"))}</b> 開始每天記錄評級；累積約兩週後，這裡會顯示當天評級對之後 5 天與 10 天實際漲跌的驗證表。</div>'
  record_html = ((f'<div class="chart-scroll lt" data-viz="lights">{chart}</div><div class="swipe">⇆ 圖表可左右滑動</div>' if chart else "")
                 + (f'<div class="small">{cur}背景色只看價格（20、50、200 日均線、MACD、RSI、SuperTrend），可以回溯；圓點是加入期權、情緒、資金流後的完整評級，每個交易日累積一顆。</div>' if chart else "")
                 + (f'<div class="card"><div class="card-h">每日評級紀錄<span class="small">最近 {min(len(hist), 21)} 個交易日</span></div><div class="strip">{chips}</div></div>' if chips else "") + check)
  return main, [_fold("proof", 1, f"{len(shown)} 個訊號的勝率與方法", all_html), _fold("proof", 2, f"{len(lights)} 天燈號與每日評級紀錄" if lights else "每日評級紀錄", record_html)]


# --------------------------------------------------------------------------- #
# 10. lessons
# --------------------------------------------------------------------------- #
def _lessons_parts(p: dict, state: str) -> tuple[str, list[str]]:
  pm, ews = p.get("postmortem") or {}, p.get("early_warning") or {}
  pc, an = ews.get("peak_checklist") or {}, ews.get("analogs") or {}
  note = "今天的期權讀數暫缺" if options_missing(p) else "資料暫缺"
  main, lesson_html, tl_html = "", "", ""
  if state == "ok":
    falls = [(name, _f(pm.get(key))) for name, key in (("SOXL", "soxl_drawdown_pct"), ("SOXX", "soxx_drawdown_pct"), ("SPY", "spy_drawdown_pct"))]
    worst = max((abs(v) for _, v in falls if v is not None), default=0.0) or 1.0
    body = "".join(f'<tr><td class="nw"><b>{name}</b></td><td class="mono nw dn">{pct(v) if v is not None else NA}</td>'
                   f'<td class="dd-cell"><div class="dd-bar"><div class="dd-fill" style="width:{min(100.0, abs(v or 0.0) / worst * 100):.0f}%"></div></div></td></tr>' for name, v in falls)
    main = (f'<table class="mt" data-drawdown-table><thead><tr><th>標的</th><th>同期跌幅</th><th>相對幅度</th></tr></thead><tbody>{body}</tbody></table>'
            f'<div class="sec-cap">高點 {tx(pm.get("peak_date"))}，低點 {tx(pm.get("trough_date"))}</div>')
    lessons = "".join(f'<div class="lesson"><div class="lesson-t">{tx(l.get("title"), note)}</div><div class="lesson-d">{tx(l.get("detail"), note)}</div><div class="lesson-r">規則：{tx(l.get("rule"), note)}</div></div>'
                      for l in _rows(pm.get("lessons")))
    bp = pm.get("big_picture") or {}
    bp_html = ""
    if _f(bp.get("big_high")) is not None and _f(bp.get("big_low")) is not None:
      bp_html = (f'<div class="note big">大格局：{tx(bp.get("big_high_date"))} 高點 {usd(bp.get("big_high"))} → {tx(bp.get("big_low_date"))} 低點 {usd(bp.get("big_low"))}{_par(pct(bp.get("big_decline_pct")))}；'
                 f'之後反彈到 {tx(bp.get("rally_high_date"))} {usd(bp.get("rally_high"))}，只收復 {nv(bp.get("retrace_pct_of_decline"), 1)}%（38.2% 位於 {usd(bp.get("fib_382_of_decline"))}）'
                 + ("，屬於失敗的熊市反彈。" if bp.get("is_failed_bear_rally") else "。") + "</div>")
    lesson_html = bp_html + (f'<div class="lessons">{lessons}</div>' if lessons else "")
    tl_rows = "".join(
        f'<tr{" class=\"hl\"" if (_f(r.get("chg_pct")) or 0) <= -8 else ""}><td>{sx(r.get("date"))}</td><td>{usd(r.get("close"))}</td><td class="{"dn" if (_f(r.get("chg_pct")) or 0) < 0 else "up"}">{pct(r.get("chg_pct"))}</td>'
        f'<td>{nv(r.get("volume_m"), 0, suffix="M")}{_par(nv(r.get("rvol"), 1, suffix="x"))}</td><td>{pct(r.get("soxx_chg"), 1) if _f(r.get("soxx_chg")) is not None else "—"}</td>'
        f'<td>{pct(r.get("spy_chg"), 1) if _f(r.get("spy_chg")) is not None else "—"}</td>' + "".join(f'<td>{nv(r.get(key), nd, na="—")}</td>' for key, nd in (("vix", 1), ("vix_ratio", 2), ("skew", 0), ("y10", 2), ("fg", 0), ("equity_pc", 2), ("crash_score", 0)))
        + f'<td class="t">{sx(r.get("notes"), note)}</td></tr>' for r in _rows(pm.get("timeline")))
    tl_html = (f'<div class="small">自高點前 4 日起。單日跌 8% 以上的列加底色。</div>'
               + _swipe_table("<th>日期</th><th>SOXL</th><th>漲跌</th><th>量 (RVOL)</th><th>SOXX</th><th>SPY</th><th>VIX</th><th>VIX/3M</th><th>SKEW</th><th>10Y</th><th>F&amp;G</th><th>Eq P/C</th><th>前兆分</th><th>備註</th>", tl_rows, "small num w-900")) if tl_rows else ""

  cols = [str(c) for c in (pc.get("columns") or [])]
  chk_rows = ""
  for r in _rows(pc.get("rows")):
    cells = "".join(f'<td>{"—" if _f(v) is None else ("🔴" if _f(v) >= 0.5 else ("🟡" if _f(v) >= 0.25 else "·"))}</td>' for v in (r.get("values") or []))
    chk_rows += (f'<tr{" class=\"on\"" if r.get("flashed") else ""}><td class="f">{sx(r.get("family"))}</td><td class="l">{sx(r.get("label"))}</td>{cells}<td>{"✅ " + tx(r.get("first_on")) if r.get("flashed") else "✗"}</td></tr>')
  chk_html = ""
  if chk_rows:
    head = "<th>家族</th><th>訊號</th>" + "".join(f"<th>{esc(c[5:])}</th>" for c in cols) + "<th>首次觸發</th>"
    scores = "".join(f'<td><b>{nv(s, 0, na="—")}</b></td>' for s in (pc.get("scores") or []))
    chk_html = (f'<div class="small">高點 {tx(pc.get("peak_date"))} 前後的 {nv(pc.get("n_total"), 0)} 項前兆訊號，其中 {nv(pc.get("n_flashed"), 0)} 項曾觸發。</div>'
                + _swipe_table(head, chk_rows + f'<tr class="tot"><td colspan="2" class="l"><b>崩跌指數（歷史百分位）</b></td>{scores}<td></td></tr>', "small pk w-900")
                + '<div class="note">圖例：🔴 0.5 以上觸發，🟡 0.25 到 0.5 醞釀，· 未觸發，— 無資料。分數以 2021 年以來（排除最近 60 日）的歷史分佈換算百分位。</div>')
  an_rows = ""
  for c in _rows(an.get("conditions")):
    cells = ""
    for k in ("5d", "10d", "20d", "60d"):
      hz = g(c, "horizons", k)
      cells += (f'<td class="mono center">{pct(hz.get("median"))} <span class="small">（{pct(hz.get("pct_positive"), 0, False)} 上漲 / {pct(hz.get("pct_down10"), 0, False)} 再跌 10%）</span></td>'
                if isinstance(hz, dict) and _f(hz.get("median")) is not None else '<td class="center">—</td>')
    tags = (' <b class="nw">（今日成立）</b>' if c.get("active_today") else "") + (' <span class="small nw">（樣本不足）</span>' if c.get("sufficient") is False else "")
    count = nv(c.get("n_days"), 0) + (f" / {nv(c.get('n_episodes'), 0)}" if _f(c.get("n_episodes")) is not None else "")
    an_rows += f'<tr class="{"act" if c.get("active_today") else ""}"><td>{sx(c.get("condition"))}{tags}</td><td class="mono center">{count}</td>{cells}</tr>'
  an_html = (f'<div class="small">SOXL {tx(an.get("sample_range"))}。每格是報酬中位數、上漲的比例、再跌 10% 以上的比例。</div>'
             + _swipe_table('<th>情境</th><th class="center">樣本日 / 事件</th><th class="center">5 日後</th><th class="center">10 日後</th><th class="center">20 日後</th><th class="center">60 日後</th>', an_rows, "small nwm w-900")) if an_rows else ""
  n_less = len(_rows(pm.get("lessons")))
  return main, [_fold("lessons", 1, f"{n_less} 條教訓與操作規則" if n_less else "大格局", lesson_html), _fold("lessons", 2, "逐日時間軸", tl_html),
                _fold("lessons", 3, "事前亮燈的前兆", chk_html), _fold("lessons", 4, "歷史同類情境的後續報酬", an_html)]


# --------------------------------------------------------------------------- #
# the sections, the section links, the footer
# --------------------------------------------------------------------------- #
def _phrases(text: str) -> str:
  """A takeaway as phrases that each stay on one line, so a narrow screen breaks it after ；：、， and nowhere else.  The text itself is unchanged."""
  parts = [x for x in re.split(r"(?<=[；：、，])", text) if x]
  return "".join(f'<span class="nw">{esc(x)}</span>' if len(x) <= 16 else esc(x) for x in parts) if len(parts) > 1 else esc(text)


_BUILDERS = {"plan": _plan_parts, "why": _why_parts, "paths": _paths_parts, "crash": _crash_parts, "mood": _mood_parts,
             "options": _options_parts, "sector": _sector_parts, "news": _news_parts, "proof": _proof_parts, "lessons": _lessons_parts}


def sections_html(p: dict) -> str:
  """The ten sections.  A section whose builder fails shows one line and leaves the others alone."""
  take = takeaways(p)
  out = []
  for sid in SECTION_IDS:
    state, text = take[sid]["state"], take[sid]["text"]
    main, folds = "", []
    if state != "error":
      try:
        main, folds = _BUILDERS[sid](p, state)
      except Exception:  # noqa: BLE001 - one broken section must not take the page down
        state, text, main, folds = "error", ERROR_LINE, "", []
    out.append(f'<section class="sec" id="sec-{sid}" data-sec="{sid}" data-state="{state}"><h2 class="sec-t">{TITLES[sid]}</h2>'
               f'<p class="sec-take" data-takeaway="{sid}" data-state="{state}">{_phrases(text)}</p>'
               + (f'<div class="sec-main" data-sec-main>{main}</div>' if main else "") + "".join(folds) + "</section>")
  return f'<div class="secs" data-sections>{"".join(out)}</div>'


def nav_html() -> str:
  links = "".join(f'<a href="#sec-{sid}">{TITLES[sid]}</a>' for sid in SECTION_IDS)
  return f'<nav class="secnav" aria-label="頁內區塊" data-section-nav>{links}</nav>'


def footer_html(p: dict) -> str:
  """Sources, the disclaimer of the feed (once), the update status, and three folds: glossary, three rules, method and commands."""
  from . import brief as briefmod
  sch = p.get("schedule") or {}
  if sch.get("installed"):
    nxt = clean(sch.get("next_run_short"))
    status = (f"已啟用每日自動更新：{tx(sch.get('weekday_text'))} {esc('、'.join(str(t) for t in (sch.get('times') or [])))}（本機時間）" + (f"，下次 {esc(nxt)}" if nxt and nxt != NA else "")
              + "。開著的分頁每 30 分鐘重新載入一次。")
  else:
    status = "這台機器尚未啟用每日自動更新。開著的分頁每 30 分鐘重新載入一次。"
  last = sch.get("last_run") or {}
  if last.get("status") == "error":
    status += f" 上次自動更新（{tx(last.get('finished'))}）失敗，目前顯示的是最近一次成功的結果。"
  gloss = "".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in GLOSSARY)
  rules = ('<ol class="rules"><li><b>SOXL 是 3 倍槓桿：</b>費城半導體指數跌 10%，它大約跌 30%；長期震盪還會磨損淨值，不適合無腦長抱。</li>'
           '<li><b>不要攤平：</b>紅燈時每往下買一次，就是把風險放大三倍。等燈號轉綠、檢核表 6 項以上成立再分批進。</li>'
           '<li><b>先想停損再想獲利：</b>進場前就決定跌破哪個價位出場（見「今天怎麼做」的停損價），並照做。</li></ol>')
  cmd = clean(sch.get("install_cmd")) or ".venv/bin/python auto_update.py install"
  method = ((f'<p>{tx(g(p, "dashboard", "method"))}</p>' if g(p, "dashboard", "method") else "")
            + f'<p>啟用每日自動更新：在終端機執行 <code>{esc(cmd)}</code> 一次，之後每個美股交易日收盤後自動重跑。</p>'
            '<p>重新產生這一頁：<code>python3 analyze_soxl.py</code>。只用已存的資料重畫：<code>python3 generate_html_report.py --offline</code>。排程狀態：<code>python3 auto_update.py status</code>。</p>')
  return (f'<footer class="pf" data-footer><p class="pf-src">{esc(SOURCES_LINE)}</p><p class="pf-dis" data-disclaimer>{esc(briefmod.DISCLAIMER)}</p><p class="pf-st" data-update-status>{status}</p>'
          f'{_fold("foot", 1, "名詞小抄：看不懂的名詞點這裡", f"<dl class=\"gloss\">{gloss}</dl>")}{_fold("foot", 2, "新手三條鐵律", rules)}{_fold("foot", 3, "方法與更新指令", f"<div class=\"pf-m\">{method}</div>")}</footer>')


CSS = """
.secnav{display:flex;gap:6px;overflow-x:auto;white-space:nowrap;margin:12px 0 10px;padding-bottom:2px;-webkit-overflow-scrolling:touch}
.secnav a{flex:none;background:#1e293b;color:#e2e8f0;padding:4px 11px;border-radius:999px;font-size:.8rem;font-weight:600;text-decoration:none}
.secnav a:hover{background:var(--acc);color:#070b14}
.secs{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
.sec{--sbg:var(--card);background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:12px 14px 10px;min-width:0;scroll-margin-top:12px}
.sec-t{font-size:.84rem;font-weight:700;color:var(--mu)}
.sec-take{font-size:1.1rem;font-weight:800;line-height:1.35;margin:1px 0 8px;text-wrap-style:balance}
.sec[data-state="missing"] .sec-take,.sec[data-state="error"] .sec-take{color:#fbbf24;font-size:1rem;margin-bottom:2px}
.sec[data-state="missing"],.sec[data-state="error"]{align-self:start}
.sec-main{margin-bottom:4px}.sec-cap{font-size:.76rem;color:var(--mu);margin-top:6px}.sec-none{font-size:.9rem;color:#e2e8f0}
.fold{border-top:1px solid var(--bd);margin-top:6px}
.fold>summary{cursor:pointer;color:var(--acc);font-weight:600;font-size:.84rem;padding:6px 0 2px}
.fold:not([open])>*:not(summary){display:none}
.fold-b{padding:6px 0 4px}.fold-b>*+*{margin-top:10px}.fold-b>.small{font-size:.78rem}
.mt{width:100%;border-collapse:collapse;font-size:.86rem}
.mt th{text-align:left;color:var(--mu);font-size:.74rem;font-weight:600;padding:3px 10px 3px 0;border-bottom:1px solid var(--bd);white-space:nowrap}
.mt td{padding:5px 10px 5px 0;border-bottom:1px solid rgba(30,41,59,.7);vertical-align:top;text-wrap-style:pretty}
.mt th:last-child,.mt td:last-child{padding-right:0}.mt tr:last-child td{border-bottom:0}
.num td{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}.num td.t{font-family:inherit;white-space:normal;color:var(--mu)}.num td.nw{white-space:nowrap;color:inherit}
.pk td{text-align:center;white-space:nowrap}.pk th{text-align:center}.pk th:nth-child(-n+2){text-align:left}.pk td.l{text-align:left;white-space:normal}.pk td.f{text-align:left}
.kv{width:100%;border-collapse:collapse;font-size:.86rem}
.kv th{text-align:left;font-weight:600;color:var(--mu);white-space:nowrap;padding:5px 12px 5px 0;vertical-align:top;width:1%;border-bottom:1px solid rgba(30,41,59,.7)}
.kv td{padding:5px 0;border-bottom:1px solid rgba(30,41,59,.7);text-wrap-style:pretty}.kv tr:last-child th,.kv tr:last-child td{border-bottom:0}
.kv b{font-family:ui-monospace,Menlo,monospace}.g-ok{color:#34d399;font-weight:700}.g-bad{color:#fb7185;font-weight:700}
.plan-head{font-weight:700;font-size:.95rem}
.lv{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.lv>div{background:#0b1120;border:1px solid var(--bd);border-radius:10px;padding:8px;text-align:center}
.lv-k{font-size:.74rem;color:var(--mu)}.lv-p{font-size:1.15rem;font-weight:800;font-family:ui-monospace,Menlo,monospace}.lv-l{font-size:.74rem;color:#e2e8f0}.lv-n{margin-top:6px}
.lv .stop{border-top:3px solid #ef4444}.lv .t1{border-top:3px solid #eab308}.lv .t2{border-top:3px solid #22c55e}
.pb{display:grid;grid-template-columns:max-content minmax(0,1fr) max-content;gap:8px 10px;align-items:center;font-size:.9rem}
.pb-name{white-space:nowrap}.pb-bar{height:16px;background:#1e293b;border-radius:8px;overflow:hidden}.pb-fill{height:100%;border-radius:8px}
.pb-pct{font-weight:800;font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}
.hm-bar{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.tiles.hm{grid-template-columns:repeat(8,minmax(0,1fr))}.tiles.hm .tile{padding:5px 2px;text-align:center;display:flex;flex-direction:column;gap:1px;white-space:nowrap;font-size:.78rem}
.tiles.hm .tile-r{font-size:.8rem;font-weight:700;font-family:ui-monospace,Menlo,monospace}
.dd-cell{width:45%}.dd-bar{height:12px;background:#1e293b;border-radius:6px;overflow:hidden;margin-top:4px}.dd-fill{height:100%;background:#f43f5e;border-radius:6px}
.nf-top td:nth-child(3){overflow-wrap:anywhere}.nf-top a,.nf-item a{color:inherit;text-decoration:underline dotted}
.nf-meta{font-size:.74rem;color:var(--mu)}.nf-why{font-size:.8rem;color:#cbd5e1}
.nf-item{display:grid;grid-template-columns:1.4rem minmax(0,1fr);gap:6px;padding:7px 0;border-top:1px solid rgba(148,163,184,.18);font-size:.86rem;line-height:1.55;overflow-wrap:anywhere}
.nf-bar{font-size:.82rem}.nf-tag{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:999px;border:1px solid rgba(148,163,184,.45);margin:2px 4px 0 0;white-space:nowrap}
.nf-caution{font-size:.84rem;padding:6px 10px;border-left:3px solid #f59e0b;background:rgba(245,158,11,.08);border-radius:4px;overflow-wrap:anywhere}
.news li{overflow-wrap:anywhere}
.dz-tile{border:1px solid rgba(148,163,184,.25);border-radius:12px;padding:10px 12px;background:rgba(148,163,184,.06);min-width:0;overflow-wrap:anywhere}
.dz-tile.green{border-color:rgba(34,197,94,.55)}.dz-tile.yellow{border-color:rgba(245,158,11,.6)}.dz-tile.red{border-color:rgba(239,68,68,.6)}
.dz-t{font-size:.78rem;color:var(--mu)}.dz-v{font-size:1.02rem;font-weight:800;margin:2px 0;line-height:1.35}.dz-m{font-size:.82rem;line-height:1.55}
.dz-d{font-size:.76rem;color:var(--mu);margin-top:4px;line-height:1.55}.dz-d code{font-size:.7rem;word-break:break-all}
.dz-voices{margin-top:6px;font-size:.84rem}.dz-voices div{padding:5px 0;border-top:1px solid rgba(148,163,184,.18);display:flex;gap:8px;flex-wrap:wrap}.dz-voices span:first-child{color:var(--mu);min-width:11em}
.tp-grade{display:inline-block;font-size:.7rem;padding:1px 6px;border-radius:999px;border:1px solid rgba(148,163,184,.5);margin-left:4px;white-space:nowrap}
.strip{display:flex;gap:6px;flex-wrap:wrap}.chip{width:58px;border-radius:8px;padding:5px 0;text-align:center;border:1px solid var(--bd);background:#0b1120}
.chip.bear{border-color:rgba(244,63,94,.6);background:rgba(244,63,94,.14)}.chip.bull{border-color:rgba(16,185,129,.6);background:rgba(16,185,129,.14)}.chip.neutral{border-color:rgba(245,158,11,.6);background:rgba(245,158,11,.14)}
.chip-d{font-size:.7rem;color:var(--mu)}.chip-e{font-size:.95rem}.chip-p{font-size:.7rem;font-family:ui-monospace,Menlo,monospace}
.chart-scroll.ind>svg.chart,.chart-scroll.lt>svg.chart{min-width:640px;max-width:940px;margin:0 auto}
.sec .regime{margin:6px 0 2px}.sec .headline{margin:4px 0}.sec .tldr{margin-top:0}.sec .qa-grid{margin-top:0}.sec .two{margin-top:0}.sec .checks{margin-top:6px}
.pf{margin-top:16px;font-size:.78rem;color:var(--mu);line-height:1.6}.pf p+p{margin-top:2px}.pf-dis{color:#cbd5e1}
.pf .fold{margin-top:8px}.pf code{background:#1e293b;padding:1px 6px;border-radius:5px;font-size:.74rem;word-break:break-all}
.pf .rules{padding-left:20px;font-size:.86rem;color:#e2e8f0}.pf .rules li{margin:6px 0}.pf .rules b{color:#fbbf24}.pf-m p+p{margin-top:6px}
@media(min-width:1100px){.secs{grid-template-columns:repeat(2,minmax(0,1fr))}.sec:has(details[open]){grid-column:1/-1}}
@media(max-width:699px){.pb{grid-template-columns:minmax(0,1fr) max-content;row-gap:3px}.pb-name{grid-column:1/-1;margin-top:5px}.tiles.hm{grid-template-columns:repeat(4,minmax(0,1fr))!important}.lv{grid-template-columns:minmax(0,1fr)}.dd-cell{width:34%}.sec{padding:10px 12px 8px}}
"""

# The page script of the sections: the factor filter, the heat-tile period, and the folds a reader
# opened (kept for the 30-minute reload).  It reads attributes and writes textContent, style and
# the ``open`` flag only.
JS = """
(function(){
  var why=document.querySelector('[data-sec="why"]');
  if(why){
    var fb=why.querySelectorAll('.fbtn[data-filter]'),rows=why.querySelectorAll('[data-score-table] tbody .row');
    fb.forEach(function(b){b.addEventListener('click',function(){fb.forEach(function(x){x.classList.remove('active')});b.classList.add('active');var m=b.getAttribute('data-filter');
      rows.forEach(function(r){var s=parseInt(r.getAttribute('data-score'),10);var show=true;if(m==='bull')show=s>0;else if(m==='neutral')show=s===0;else if(m==='bear')show=s<0;r.style.display=show?'':'none';});});});
  }
  var sector=document.querySelector('[data-sec="sector"]');
  if(sector){
    var hb=sector.querySelectorAll('.fbtn[data-h]'),tiles=sector.querySelectorAll('[data-tiles] .tile');
    hb.forEach(function(b){b.addEventListener('click',function(){hb.forEach(function(x){x.classList.remove('active')});b.classList.add('active');var h=b.getAttribute('data-h');
      tiles.forEach(function(t){var raw=t.getAttribute('data-r'+h),el=t.querySelector('.tile-r');if(raw===null||!el)return;var v=parseFloat(raw);el.textContent=(v>=0?'+':'')+v.toFixed(1)+'%';
        t.style.background=v>=5?'rgba(16,185,129,.42)':(v>=0?'rgba(16,185,129,.22)':(v>-3?'rgba(244,63,94,.22)':'rgba(244,63,94,.42)'));});});});
  }
  var KEY='soxl.folds',folds=Array.prototype.slice.call(document.querySelectorAll('details[data-fold]'));
  try{var saved=JSON.parse(sessionStorage.getItem(KEY)||'[]');if(Array.isArray(saved)){folds.forEach(function(d){if(saved.indexOf(d.getAttribute('data-fold'))>=0)d.open=true;});}}catch(e){}
  folds.forEach(function(d){d.addEventListener('toggle',function(){var open=[];folds.forEach(function(x){if(x.open)open.push(x.getAttribute('data-fold'));});try{sessionStorage.setItem(KEY,JSON.stringify(open));}catch(e){}});});
})();
"""
