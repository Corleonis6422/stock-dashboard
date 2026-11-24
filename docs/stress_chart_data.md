# Stress chart data: `payload["stress_chart"]`

This document is the contract for the data behind the combined chart: SOXL price, VIX
spikes, volume and the crash index on one date axis. It names every key and its unit,
states every rule with its parameters, and defines every figure of the evidence strip.
A reader who has this document and the legend lines in `rules` can recompute the block.

The block describes. It feeds no rating, no score, no level and no trade plan.

- Code: `soxl_quant/stress_chart.py`. The pipeline builds the block in step 8d of
  `soxl_quant/pipeline.py`. A failure there is caught, appended to `warnings`, and the
  payload carries `"stress_chart": {}`.
- Tests: `python3 tools/test_stress_chart.py` (synthetic series with known answers, then
  the stored payloads). Extra payload files or folders may follow on the command line.
- Schema name: `soxl-stress-chart/1`.
- Size. On the data of 2026-11-20 the block is 105,504 bytes as compact JSON and
  160,346 bytes with the one-space indent of `soxl_analysis_data.json`. A reduced block
  is 23,484 bytes compact. `tools/test_stress_chart.py` fails when a stored block
  reaches 200,000 bytes in either form.

## 1. One function for any payload

```python
from soxl_quant import stress_chart
block = stress_chart.for_payload(payload)   # never raises
```

- A payload that carries a valid block returns it (`source` is `"pipeline"`).
- Any other payload returns a **reduced block** (`source` is `"reduced"`), built from
  `technicals.chart_series`, `sentiment.vix.history` and `early_warning.chart`. See
  section 11.
- A payload with no usable bars returns a block with `available: false`, a `reason` and
  one line of text in `text_zh`.

Helpers for Python callers:

| Function | Returns |
|---|---|
| `table_dicts(table)` | The rows of a table as a list of dicts, oldest first. |
| `view_bars(block, "daily" or "weekly")` | The bars of a view as dicts. |
| `crash_history(block)` | Every crash index reading in the block, oldest first. |
| `block_bytes(block)` | Size as compact UTF-8 JSON. |

## 2. Tables

A table stores one array per column. All arrays have `n` values. Row `i` is the `i`-th
value of each array. Rows run oldest first.

```json
{"columns": ["date", "close", "spike"], "n": 3,
 "date": ["2026-11-18", "2026-11-19", "2026-11-20"],
 "close": [24.56, 28.44, 35.89],
 "spike": [true, true, true]}
```

`null` means the value does not exist.

## 3. Top-level keys

| Key | Type | Meaning |
|---|---|---|
| `schema` | string | `soxl-stress-chart/1`. |
| `available` | bool | False when there is no bar to draw. Then `reason` and `text_zh` say why. |
| `source` | string | `pipeline` (full block) or `reduced`. |
| `symbol` | string | `SOXL`. |
| `as_of` | date | Date of the latest daily session in the block. |
| `data_final` | bool | False when the latest session was an intraday snapshot (`data_status.final`). |
| `daily` | table | Daily series. Section 4. |
| `vix` | table | Stored VIX series. Section 5. |
| `weekly` | table | Weekly bars built from `daily`. Section 6. |
| `views` | object | `daily` and `weekly` views. Section 8. |
| `rules` | object | Each rule as parameters and one legend line. Section 7. |
| `legend` | object | Legend lines that are not rules. Section 9. |
| `latest` | object | The latest session and the latest VIX reading. Section 9. |
| `spike_stats` | object | Share of sessions the spike rule marks. Section 7.1. |
| `evidence` | object | Figures of the evidence strip. Section 10. |

An unavailable block (`available: false`) still carries every key above, so a reader
needs no key test. `symbol` is `SOXL`. `as_of`, `data_final`, `latest` and `spike_stats`
are `null`. The three tables are empty. Both views are unavailable with the block's
`reason` and `text_zh`. `evidence` is unavailable. `reason` is `no_bars`, or `error`
when the reduced build raised. In that case the block also has `error`, the exception
as an English string for the log. Do not show `error` to the reader.

Dates are ISO strings (`YYYY-MM-DD`). Prices are US dollars. Volumes are shares. VIX is
in index points. The crash index runs from 0 to 100. Every `*_zh` value is one line of
Traditional Chinese for the reader.

## 4. `daily`: one row per SOXL session

| Column | Unit | Definition |
|---|---|---|
| `date` | date | Session date. |
| `open`, `high`, `low`, `close` | USD | The loaded history, rounded to 2 decimals with Python `round(x, 2)`. |
| `volume` | shares | Integer, as loaded. |
| `vol_avg20` | shares | Mean volume of the 20 sessions that end with this one, on the whole loaded history, rounded to an integer with Python `round()`: a mean that ends in exactly .5 goes to the even integer (round half to even), not up. `null` when the loaded history has fewer than 20 sessions up to this one. |
| `vix` | points | VIX close of the same date. `null` when the VIX series has no row for that date. |
| `crash` | 0 to 100 | Crash index of that session, 1 decimal. `null` when the session has no score. |
| `spike` | bool | The spike flag of the VIX row of the same date. `null` when there is no such row or it is not judged. |

- Length. The latest 650 sessions of the loaded SOXL history, minus the leading
  sessions that do not start an ISO week. So the table holds 646 to 650 sessions and its
  first session is the first session of its ISO week. When the loaded history has 650
  sessions or fewer, the table holds all of them. Its first weekly bar can then cover
  only part of a week, and `partial` does not flag that bar.
- `open`, `high`, `low`, `close`, `volume` and `vol_avg20` of the latest 120 rows equal
  `technicals.chart_series` on every shared date (`vol_avg20` is `vol_sma20` there).
- `crash` equals `early_warning.chart[].score` on every shared date. The pipeline takes
  the full series from the same computation (`early_warning.analyze_with_series`) and
  lets `early_warning.chart` win on a shared date.
- `vix` can be `null` on the latest session: the CBOE file does not always hold that
  day's close when the job runs. This is so on 15 of the 24 baseline snapshots, among
  them 2026-10-26 and 2026-10-27. The flag of that session is then `null` too, and
  `latest.vix` gives the latest reading before it (section 9). The session gets its
  value on a later run. No earlier flag changes.
- `vol_avg20` of the first 19 rows uses sessions before the table. Those values cannot
  be recomputed from the block alone.

## 5. `vix`: the stored VIX series

| Column | Unit | Definition |
|---|---|---|
| `date` | date | Date of the VIX row. |
| `close` | points | VIX close as published by CBOE (2 decimals). |
| `spike` | bool | The spike rule of section 7.1 applied to this table alone. |

- The rows are VIX's own sessions. The CBOE history has rows on some US market holidays.
  Those dates have no SOXL session and no row in `daily`.
- The table starts 60 rows before the first VIX row dated on or after `daily.date[0]`
  and runs to the last loaded VIX row.
- The first 60 rows have `spike: null`. Every later row is judged.
- A script that applies the rule to `vix.close` gets exactly `vix.spike`. A `daily` row
  carries the flag of the `vix` row with the same date.
- Do not apply the rule to the `daily.vix` column. That column skips the VIX rows that
  have no SOXL session, so its 60-session windows differ. Measured on the data of
  2026-11-20: 19 such rows lie inside the daily range, and the flag of one session
  (2024-09-03) would come out different.

## 6. `weekly`: one row per ISO week

Built from `daily` by the rule of section 7.3.

| Column | Unit | Definition |
|---|---|---|
| `start`, `end` | date | First and last session of the week. |
| `open` | USD | Open of the first session. |
| `high`, `low` | USD | Highest high and lowest low of the week. |
| `close` | USD | Close of the last session. |
| `volume` | shares | Sum of the sessions' volumes. |
| `vol_avg20w` | shares | Mean `volume` of the 20 weekly bars that end with this one, rounded to an integer with Python `round()` (round half to even, as `vol_avg20`). `null` for the first 19 bars. |
| `vix` | points | `vix` of the last session of the week that has one. |
| `crash` | 0 to 100 | `crash` of the last session of the week that has one. |
| `spike` | bool | True when any session of the week is marked. False when at least one session was judged and none is marked. `null` when no session was judged. |
| `sessions` | count | Number of sessions in the week. |
| `partial` | bool | True only on the last bar, when its week is not over. Section 7.3. |

## 7. Rules

`rules` holds five entries. Each has `params` (the parameters as data) and `text_zh`
(the one legend line). `views.<view>.rules` lists the entries that a view's legend
prints, in order:

- daily: `vix_spike`, `trend_channel`, `volume_profile_daily`
- weekly: `weekly_bars`, `vix_spike`, `trend_channel`, `volume_profile_weekly`

Every parameter is a constant at the top of `soxl_quant/stress_chart.py`. Nothing is
fitted at run time.

### 7.1 VIX spike (`rules.vix_spike`)

Parameters: lookback 60 sessions, multiple 1.4, join gap 5 sessions, cap 10%.

Take the VIX closes `c[0..n-1]` of a series, oldest first.

- `t < 60`: the session is **not judged** (`null`).
- `t >= 60`: let `m` be the median of `c[t-60] .. c[t-1]`. With 60 values that is the
  mean of the 30th and 31st smallest. The session is **marked** when `c[t] >= 1.4 * m`.

Properties:

- **No repaint.** The mark of session `t` reads `c[t-60] .. c[t]` and nothing else.
  Cutting the series after `t`, or appending later data, never changes it.
- **Locality.** Any slice of the series gives the same mark for every session that
  still has 60 sessions before it. So 260 stored rows give the right marks for their
  latest 200 rows.
- **Ties.** A close equal to the threshold is a spike. The code decides this in exact
  integer arithmetic: with `q = round(c * 10000)` and `a`, `b` the two middle values of
  the sorted window, the session is marked when `10 * q[t] >= 7 * (a + b)`. Plain
  floating point (`c[t] >= 1.4 * statistics.median(window)`) agrees unless the close
  sits exactly on the threshold. On the history loaded on 2026-11-23 (9,321 sessions)
  no session sits on the threshold and the two methods agree on every session.

**Episodes.** Take a list of flags on any session axis. A run of marked sessions is an
episode. Two runs with at most 5 unmarked sessions between them are one episode. A
session that is `null` counts as unmarked. The first session of an episode is a marked
session with no marked session among the 6 before it.

The same episode rule runs on three axes:

| Where | Axis |
|---|---|
| `views.<view>.spikes.episodes` | The daily sessions inside the view. |
| `spike_stats.episodes` | VIX's own sessions, whole loaded history. |
| `evidence` condition `vix_spike_start` | The SOXL sessions of the price history. |

**`spike_stats`**

| Key | Meaning |
|---|---|
| `scope` | `loaded_vix_history` in a full block. `stored_vix_rows` in a reduced block. |
| `first_date`, `last_date` | First and last date of that VIX series. |
| `sessions` | Number of sessions in it. |
| `evaluated` | Sessions that are judged (`sessions - 60`). |
| `marked` | Sessions that are marked. |
| `share_pct` | `marked / sessions * 100`, 2 decimals. |
| `share_of_evaluated_pct` | `marked / evaluated * 100`, 2 decimals. |
| `episodes` | Episode count on that series. |
| `cap_pct` | 10.0. |
| `within_cap` | `share_pct <= 10` for scope `loaded_vix_history`. `null` otherwise. |

When `within_cap` is false the pipeline appends a line to `warnings`.

The loaded VIX history is the whole CBOE daily file of VIX, from 1990-01-02. The
pipeline loads it in step 6 together with four other CBOE indexes, and drops all five
when any one fails. In that case step 8d uses the 5-year VIX rows of step 5 (the
latest 1,300 rows of the same file). The stored flags are the same, by locality.
`spike_stats` and the `vix_spike_start` figures then cover 5 years only.
`spike_stats.first_date` shows which history a block used.

### 7.2 Trend channel (`rules.trend_channel`)

Parameters: band 2 sigma, minimum R² 0.5, minimum 30 bars.

Input: the closes of the bars in view, oldest first, `n` bars.

1. `x[i] = i` for `i = 0 .. n-1`. `y[i] = ln(close[i])`.
2. Fit `y = a + b x` by least squares.
3. `e[i] = y[i] - (a + b i)`. `sigma = sqrt(sum(e[i]^2) / n)`. This is the root mean
   square of the residuals. Divide by `n`, not by `n - 2`.
4. `R² = 1 - sum(e[i]^2) / sum((y[i] - mean(y))^2)`. When every close is equal, `R²` is 0.
5. The price of a line at bar `i` is `exp(a + b i + s)`, with `s = +2 sigma` for the
   upper line, `0` for the middle line and `-2 sigma` for the lower line.

No channel when `n < 30` (`reason: too_few_bars`), when a close is missing or not
positive (`bad_prices`), or when `R² < 0.5` (`low_r2`).

A line is straight in `ln(price)`. Between its end points it is a curve on a linear
price axis. Use `intercept_log`, `slope_log_per_bar` and `sigma_log` to place any point.

### 7.3 Weekly bars (`rules.weekly_bars`)

- A week is an ISO week, Monday to Sunday. Two sessions belong to the same bar when
  `date.isocalendar()` gives the same ISO year and week. The days around New Year can
  share one ISO week across two calendar years.
- Columns are defined in section 6.
- `vol_avg20w` includes the current bar.
- **`partial`** is false on every bar but the last. The last bar is partial when
  `data_final` is false, or when a NYSE trading day follows its last session inside the
  same ISO week. A NYSE trading day is a weekday that is not in `US_MARKET_HOLIDAYS` of
  `soxl_quant/marketclock.py` (full-day closures, 2025 to 2027; other years fall back to
  weekdays).
- **`partial` is reliable only for the years that table lists** (2025, 2026 and 2027).
  In any other year every weekday counts as a trading day. A week that ends with a
  full-day holiday is then flagged partial although it is over. The flag never misses
  a week that is really unfinished. Add the new year to `US_MARKET_HOLIDAYS` before
  2028.

### 7.4 Volume profile: one rule per view

Both rules share these steps. Input: the bars in view that have `high`, `low` and
`close` above zero, oldest first.

1. `lo` = lowest `low`. `hi` = highest `high`. No profile when `hi <= lo`
   (`reason: flat_range`), when there is no bar (`no_bars`), or when the total volume
   is zero (`no_volume`).
2. There are 24 bands, numbered `k = 0` (lowest price) to `k = 23`.
3. For each bar, `tp = ((high + low) + close) / 3`. Compute the band `k` of `tp` by the
   formula of the rule below, with `floor`, and keep it between 0 and 23. Add the
   **whole** volume of the bar to band `k`. A `tp` that sits exactly on a bound goes to
   the band above it. A `tp` equal to `hi` goes to band 23.
4. Up and down volume. A bar counts as up when its `close >=` the close of the bar
   before it in the view. The first bar counts as up when its `close >=` its own `open`.
   Every other bar counts as down.
5. **Busiest band**: the band with the largest total volume. **Tie-break**: when two
   or more bands hold the same largest volume, the band with the lowest price wins.
6. **Runner-up**: the largest of the other 23 bands, by the same tie-break.
   `lead_pts = (busiest volume - runner-up volume) / total volume * 100`, 1 decimal.

Do the arithmetic in IEEE double precision in the order written.

**Daily view: `rules.volume_profile_daily`, bands of equal width.** This is the exact
method of `technicals.volume_profile`.

- `w = (hi - lo) / 24`
- Band `k` runs from `lo + k * w` to `lo + (k + 1) * w`.
- `k = floor((tp - lo) / w)`

**Weekly view: `rules.volume_profile_weekly`, bands of equal ratio.**

- `w = (ln(hi) - ln(lo)) / 24`
- Band `k` runs from `exp(ln(lo) + k * w)` to `exp(ln(lo) + (k + 1) * w)`.
- `k = floor((ln(tp) - ln(lo)) / w)`

In both rules band 0 starts at `lo` and band 23 ends at `hi`. Every band carries its
own `price_low` and `price_high`, rounded to 4 decimals. The data assumes nothing about
the scale of the price axis. Assign a bar with the formula, not by comparing `tp` with
the stored bounds: the stored bounds are rounded.

Why two rules. The daily view shares the method of the model's POC level
(`technicals.poc_price`), which the page and the feed already show. It also shares the
window: the model computes its POC on the latest 126 sessions, and the daily view of a
full block holds the same 126 sessions. The weekly view spans a price range that 24
equal widths cannot resolve. Three limits remain:

- The model uses unrounded prices. The daily view rounds prices to 2 decimals. The two
  can still name different bands when two bands are close in volume.
- A reduced block (section 11) has 120 bars, not 126. Its profile covers a shorter
  window than the POC level does.
- A busiest band can lead by a small margin. Read `lead_pts` and `runner_up` before
  treating the band as a clear level.

Measured on 2026-11-23. On the data of 2026-11-20 the daily view has 126 bars,
`technicals.poc_price` (46.83) lies inside its busiest band (41.16 to 52.50), and that
band leads by 4.9 points. The weekly busiest band leads by 0.3 points. The 24 baseline
snapshots carry no block, so each gets a reduced block of 120 bars: the POC lies inside
the busiest band on 19 of them. The five misses are 2026-10-20 to 2026-10-26. On each
the POC sits in the band just above the busiest band, and the busiest band leads by 0.2
to 1.3 points.

## 8. Views

`views.daily` is the latest 126 rows of `daily`. That is the window of the model's POC
level (`technicals.volume_profile`), so both describe the same sessions. A reduced block
(section 11) holds 120 rows, and its daily view has those 120 bars. `views.weekly` is
the latest 104 rows of `weekly`. A view that cannot be built has `available: false`,
`kind`, `reason` and `text_zh`. The weekly view needs at least 30 weekly bars.

| Key | Meaning |
|---|---|
| `available` | True when the view can be drawn. |
| `kind` | `daily` or `weekly`. |
| `first`, `last` | Zero-based row positions of the view's first and last bar in its table, inclusive. |
| `bars` | Number of bars (`last - first + 1`). |
| `start`, `end` | Date of the first session and of the last session in the view. |
| `rules` | Keys of `rules` that this view's legend prints. |
| `series` | Which series have data in view: `price`, `volume`, `volume_avg`, `vix`, `crash`. |
| `spikes` | Spike episodes in view. Below. |
| `crash_drops` | Crash-drop markers in view. Below. |
| `channel` | Trend channel of the bars in view. Below. |
| `profile` | Volume profile of the bars in view. Below. |
| `missing_zh` | One line for each series whose source is missing. |
| `last_bar_partial` | Weekly view only. `partial` of the last bar. |
| `last_bar_sessions` | Weekly view only. Sessions in the last bar. |
| `last_bar_text_zh` | Weekly view only. One line that says whether the last bar is a whole week. |

A bar position below is zero-based **inside the view**: position 0 is row `first` of the
table. In the weekly view a session's position is the weekly bar that holds it.

**`spikes`**

| Key | Meaning |
|---|---|
| `status` | `ok` (at least one episode), `none` (judged, no spike), `no_vix` (no VIX value in view), `too_short` (VIX values but no judged session). |
| `judged_sessions` | Daily sessions in view with a flag that is not `null`. |
| `text_zh` | `null` for `ok`. Otherwise the line the legend prints. |
| `episodes` | List, oldest first. Computed from the daily sessions inside the view only. |

Each episode:

| Key | Meaning |
|---|---|
| `start`, `end` | Dates of its first and last marked session in view. |
| `marked_sessions` | Marked sessions in the episode. |
| `span_sessions` | Sessions from `start` to `end`, both included. |
| `peak_vix`, `peak_date` | Highest VIX close among its marked sessions, and its date. The earliest date wins a tie. |
| `first_bar`, `last_bar` | Positions of the bars that hold `start` and `end`. |
| `anchor_bar` | Position of the bar that holds `peak_date`. A label's leader points here. |

**`crash_drops`**: the entries of `early_warning.event_study.episodes` whose `date` is a
session in view. They are copied, not recomputed. Keys: `date`, `bar` (position),
`close`, `fwd_min_pct`, `top_type`, `score_t`, `flagged`.

**`channel`**

| Key | Meaning |
|---|---|
| `available` | False when the rule yields no channel. Then `reason`, `bars`, `text_zh`, and `r2` for `low_r2`. |
| `bars` | `n`. |
| `direction` | `up` when `b > 0`, else `down`. |
| `upper`, `mid`, `lower` | Each `[price at position 0, price at position n-1]`, USD, 4 decimals. |
| `intercept_log` | `a`, 8 decimals. |
| `slope_log_per_bar` | `b`, 8 decimals. |
| `sigma_log` | `sigma`, 8 decimals. |
| `band_sigmas` | 2.0. |
| `slope_pct_per_bar` | `(exp(b) - 1) * 100`, 3 decimals. |
| `r2` | `R²`, 4 decimals. |
| `text_zh` | One line: direction, slope and R², or why there is no channel. |

**`profile`**

| Key | Meaning |
|---|---|
| `rule` | `volume_profile_daily` or `volume_profile_weekly`. |
| `available` | False when there is no profile. Then `reason` and `text_zh`. |
| `spacing` | `equal_width` or `equal_ratio`. |
| `bins` | 24. |
| `range_low`, `range_high` | `lo` and `hi`, USD. |
| `band_width` | `w` in USD for `equal_width`. `null` for `equal_ratio`. |
| `band_ratio` | `exp(w)` for `equal_ratio`. `null` for `equal_width`. |
| `total_volume` | Shares in all bands. |
| `bands` | Table of 24 rows, lowest price first: `price_low`, `price_high`, `total_volume`, `up_volume`, `down_volume`. |
| `busiest` | `index`, `price_low`, `price_high`, `volume`, `share_pct` (1 decimal). |
| `runner_up` | Same keys, for the second band. |
| `lead_pts` | Lead of the busiest band over the runner-up, in points of volume share. |

## 9. `legend` and `latest`

**`legend`**

| Key | Meaning |
|---|---|
| `spike_label_zh` | Text of a spike label. |
| `no_spike_in_view_zh` | Legend line when a view has no spike. |
| `no_channel_zh` | Legend line when a view has no channel. `channel.text_zh` gives the reason with numbers. |
| `no_vix_zh`, `no_crash_zh` | Lines that name a missing source. |
| `crash_lines` | The two lines of the crash index panel: `value` 60 and 80, with `label_zh`. They are the zone bounds of `early_warning.zone`. |
| `crash_drop_zh` | Legend line of the crash-drop marker, from `event_study.drop_pct` and `horizon_days`. `null` when those are missing. |

**`latest`**

| Key | Meaning |
|---|---|
| `date`, `close`, `volume`, `vol_avg20`, `crash` | The last row of `daily`. |
| `volume_ratio` | `volume / vol_avg20`, 2 decimals. |
| `volume_vs_avg` | `above`, `below` or `equal`. |
| `session_spike` | `spike` of the last row of `daily`. `null` when its VIX close is not in yet. |
| `vix.date`, `vix.close` | The latest VIX row dated on or before `date`. |
| `vix.same_session` | True when that row has the same date as the last session. |
| `vix.spike` | Flag of that VIX row. |
| `vix.median_prev` | Median of the 60 closes before it, 3 decimals. |
| `vix.multiple` | `close / median`, 2 decimals. |
| `vix.threshold` | `1.4 * median`, 2 decimals. |
| `vix.lookback_sessions` | 60. |
| `spike_episode` | `start` and `marked_sessions` of the episode that ends on `vix.date`. `null` when that row is not a spike. The episode is taken on the whole `daily` table (every stored session), not on a view. So `start` can lie before the first bar of the daily view, and `marked_sessions` can exceed the marked bars in that view. In a reduced block the table is the 120 stored sessions. |

## 10. `evidence`: the evidence strip

The strip states what SOXL did after two conditions, next to the base rate, the sample
count and the sample period.

| Key | Meaning |
|---|---|
| `available` | True when at least one condition has figures. Otherwise `text_zh` holds one line. |
| `horizons` | `[5, 10, 20]` sessions. |
| `default_horizon` | 10. Chosen before any result was computed. |
| `small_sample_below` | 20. |
| `price_history` | `symbol`, `start`, `end`, `sessions` of the price history used. |
| `convention` | Entry and exit as data, and `text_zh`. |
| `conditions` | The two conditions. Below. |
| `crash_before_daily` | Table `date`, `score`: crash index readings older than `daily.date[0]`. |
| `event_study` | Figures copied from `early_warning.event_study`. Below. |

### 10.1 Inputs

- **Price history `P`.** The rows of the 10-year SOXL history that precede the first
  date of the model's 5-year history, followed by the 5-year history. Prices are raw,
  not rounded. Rows without a positive open and close are dropped. Index the rows
  `i = 0 .. N-1`.
- **VIX.** The whole loaded VIX history.
- **Crash index.** Every scored session. Rebuild it from the block: the rows of
  `crash_before_daily`, then `(daily.date, daily.crash)` for every row with a value.

### 10.2 Convention

The condition is judged on session `i` with data up to and including `i`. Buy the open
of session `i + 1`. Sell the close of session `i + h`.

`return_pct(i, h) = (close[i + h] / open[i + 1] - 1) * 100`

A gain is `return_pct > 0`. This is the convention of `soxl_quant/backtest.py`.

### 10.3 Conditions

Each condition has `key`, `label_zh`, `definition_zh`, `available`, `sample`
(`start`, `end`, `sessions`), `start_dates` and `figures`. An unavailable condition has
`reason` and `text_zh`.

**`vix_spike_start`: a VIX spike episode starts.**

- `flag[i]` is the mark of the VIX row dated like `P[i]`, from the rule on the whole
  VIX history. `null` when there is no such row.
- Build episodes on the axis of `P`. The condition holds on `i` when `i` is the first
  session of an episode.
- Sample: `i` from `f + 6` to `g`, where `f` and `g` are the first and last index with
  a flag that is not `null`. The first 6 sessions are left out because their episode
  start cannot be established.

**`crash_ge80`: the crash index rises to 80 or more.**

- The condition holds on `i` when `score[i] >= 80`, and `score[i - 1]` exists and is
  below 80.
- Sample: `i` from `s + 1` to `e`, where `s` and `e` are the first and last index with
  a score.
- `note_zh` states a limit: the crash index is a percentile on the whole sample, so a
  past score was not known on its day.

`start_dates` lists every session of the sample on which the condition holds.

### 10.4 Figures

One figure per horizon `h`. Walk the sessions of the sample in date order. For each
session `i` on which the condition holds:

1. If an earlier counted or open episode sits at `p` with `i - p < h`, the session is
   **skipped**. Holding periods never overlap.
2. Otherwise, if `i + h > N - 1`, the episode is **open**. Its exit does not exist yet.
   It is not counted. It still blocks later sessions by step 1.
3. Otherwise the episode is **counted**.

| Key | Definition |
|---|---|
| `horizon` | `h` in sessions. |
| `n` | Number of counted episodes. |
| `wins` | Counted episodes with a gain. |
| `median_ret_pct` | Median of `return_pct` over the counted episodes. For an even count, the mean of the two middle values. 6 decimals. `null` when `n` is 0. |
| `gain_share_pct` | `wins / n * 100`. 6 decimals. `null` when `n` is 0. |
| `small_sample` | `n < 20`. |
| `base` | The same four statistics over **every** session `i` of the sample with `i + h <= N - 1`: `n`, `wins`, `median_ret_pct`, `gain_share_pct`. |
| `period` | `start` and `end`: dates of the first and last session in `base`. |
| `episode_dates` | Dates of the counted episodes. |
| `skipped_overlap` | Number of skipped sessions. |
| `open_dates` | Dates of the open episodes. |

Values carry 6 decimals so a page can round once to its display precision.

### 10.5 `event_study`

These figures are copied unchanged from `early_warning.event_study`: `threshold`,
`drop_pct`, `horizon_days`, `n_days`, `n_event_days`, `n_episodes`, `alert_episodes`,
`alert_episodes_followed_by_crash`, `alert_hit_rate_pct`, `stats_all_80`, `stats_top_80`.
`score_period` gives the first and last date of the crash index series. `source` and
`unit` are two English strings that say where the figures come from and what they count.

They count sessions, and their windows overlap. They are not strip figures in the sense
of section 10.4. The key is absent when `early_warning.event_study` has neither
`stats_all_80` nor `stats_top_80`.

## 11. The reduced block

A payload without the block gets one from the series every payload stores.

| Part | Reduced block |
|---|---|
| `daily` | The bars of `technicals.chart_series` (120 sessions). |
| `vix` | The rows of `sentiment.vix.history` (260 rows). The first 60 are not judged. |
| `crash` | `early_warning.chart` (130 points). |
| `views.daily` | Complete: spike episodes, markers, channel, profile. |
| `views.weekly` | `available: false`, with one line in `text_zh`. |
| `weekly` | Empty table. |
| `evidence` | `available: false`, with one line in `text_zh`. |
| `spike_stats` | `scope: stored_vix_rows`. `within_cap` is `null`. |

For a payload that has the block, the 120 bars of the reduced daily view are the latest
120 of the 126 bars in the block's daily view: the same prices, volume, VIX, crash index
and spike flags. The channel, the profile, the episodes and every bar position are
computed on the 120 bars, so they can differ from the block's daily view.
`tools/test_stress_chart.py` checks the shared bars on every stored payload.

## 12. Recomputing

What the block alone supports:

- the spike flags, from `vix`
- every weekly bar, from `daily` (and `data_final` for `partial`)
- the episodes, markers, channel and profile of each view, from its bars
- the conditions of the crash index figures, from `crash_history`

What needs the loaded history:

- `spike_stats`: the whole VIX history
- the returns in `evidence`: the raw SOXL price history
- `vol_avg20` of the first 19 rows of `daily`

Read the loaded history from the cache with the offline switch:

```python
import os
os.environ["SOXL_OFFLINE"] = "1"
from soxl_quant import datafeed
vix = datafeed.fetch_cboe_index_history("VIX")                     # whole VIX history
recent = datafeed.fetch_history("SOXL", "5y")                      # the model's history
older = datafeed.fetch_nasdaq_history("SOXL", "etf", years=10)
prices = [r for r in older if r["date"] < recent[0]["date"]] + recent
```

### The offline switch

`SOXL_OFFLINE=1` puts the data layer (`soxl_quant/datafeed.py`) in replay mode:

- it makes no network request,
- it serves a cached response whatever its age,
- it never writes to the cache and never clears it, also on `--refresh`,
- an uncached source raises `FeedError` with the URL, so callers degrade as on a failed
  fetch.

`analyze_soxl.py`, `generate_html_report.py` and every tool that reads through the data
layer honor it. Any value other than empty, `0`, `false`, `no` or `off` turns it on.
Test: `python3 tools/test_offline.py`.

**Limit.** The switch freezes the cache, not the clock. Some lookups are keyed by
today's date: the CBOE daily put/call statistics by UTC date, the earnings calendar by
local date. A replay reproduces a run exactly only on the UTC date of the cached run.
On a later date those lookups miss the cache and degrade, and numbers that depend on
them can differ.
