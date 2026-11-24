# Page markers

The page is one file. The pipeline writes the same bytes to `index.html`,
`soxl_analysis_report.html` and `soxl_simple.html`. This document lists the markers that
a script can rely on. Markers are `data-*` attributes and a few ids. Class names are
styling and can change.

`soxl_quant/report_page.py` builds the first screen. `soxl_quant/report_chart.py` draws
the chart and the evidence strip from `stress_chart.for_payload(payload)`. The chart
data is described in `docs/stress_chart_data.md`.

## 1. First screen: the seven items

Each item is one element with `data-r2="<number>"` and `data-r2-name="<name>"`.
Each value inside is an element with `data-f="<field>"`. Its text is what the reader
sees. `data-v`, where present, is the same value as plain data.

| Item | Find it with | Fields inside |
|---|---|---|
| 1 rating label and buy answer | `[data-r2="1"]`, name `verdict` | `rating-label`, `buy-answer` |
| 2 data date and data status | `[data-r2="2"]`, name `data`, inside `<header>` | `data-date`, `data-status`, and `data-missing` when a source failed (`data-n` = how many) |
| 3 close and 1-day change | `[data-r2="3"]`, name `price` | `close` (`data-v` dollars, 2 decimals), `ret-1d` (`data-v` percent, 2 decimals) |
| 4 level to watch and its kind | `[data-r2="4"]`, name `watch` | `watch-price` (`data-v` dollars), `watch-kind` |
| 5 crash index and zone | `[data-r2="5"]`, name `crash` | `crash-score` (`data-v`, 1 decimal), `crash-zone` |
| 6 VIX and spike state | `[data-r2="6"]`, name `vix` | `vix` (`data-v`, 2 decimals), `spike-state` (`data-v` is `spike`, `no-spike` or `unknown`), and `vix-date` (`data-v` = date) when the reading is older than the latest session |
| 7 combined chart | `[data-r2="7"]`, name `chart`. It is `section[data-chart-box]`. | Section 2 |

Volume against its average sits in `[data-readout="volume"]`: `volume` (`data-v`
shares), `volume-vs-avg` (`data-v` is `above`, `below` or `equal`), `volume-ratio`.

Rules for a script:

- A field name is unique inside its block, not on the page. `close`, `vix` and
  `volume` also name fields of the crosshair read-out. Write
  `[data-r2="3"] [data-f="close"]`, not `[data-f="close"]`.
- A missing value has no `data-v`. The field then says in words what is missing. With
  no trade plan, item 4 has no `watch-price` and `watch-kind` reads `沒有單一關鍵價位`.
- `rating-label` and `buy-answer` come from the same fields and the same function as
  `verdict.label` and `beginner.buy.answer` in `feed/latest.json`.
- `<main data-first-screen>` holds items 1 and 3 to 7. Item 2 is in the `<header>`
  above it.

Ids: `#readouts` (items 1, 3 to 6 and volume), `#chart` (item 7), `#chart-rules`,
`#evidence`.

## 2. The chart

```
div[data-chart]                         data-active-view, data-views
  section[data-chart-box]  (item 7)     data-available = 1 or 0
    button[data-view-switch]            one per view
    div[data-crosshair-readout]         one per view
    div[data-pane]                      one per view: drawing and axis labels
      div[data-cross-target]            the drawing: svg + labels + crosshair line
    ul[data-chart-legend]               one per view
  section[data-chart-rulebox]           ul[data-chart-rules], one per view
```

- `data-views` lists the views the page has, for example `daily weekly`.
  `data-active-view` names the one that is shown.
- Every element of a view carries `data-pane="daily"` or `data-pane="weekly"`. The
  elements of the other view are `display:none`.
- When the data has no bar, `data-available="0"` and the box holds one line,
  `p[data-chart-missing]`.
- When a view does not exist, the switch is replaced by `[data-view-only="daily"]` and
  one line, `p[data-view-missing="weekly"]`.

### 2.1 Switching the view

Any of these works:

- Click `button[data-view-switch="weekly"]`. `aria-pressed` follows.
- Load the page with `#view=weekly` or `#view=daily`. A later `hashchange` works too.
- A click stores the choice in `localStorage["soxl.chartView"]` and in the URL hash.

On load the page takes the hash, then the stored choice, then `data-active-view`.

### 2.2 The drawing

`svg[data-view-svg="<view>"]` has `viewBox="0 0 1000 1000"` and
`preserveAspectRatio="none"`. It stretches to its box, so the chart never scrolls
sideways. It holds shapes only. Every label is an HTML element over it.

| Attribute | Meaning |
|---|---|
| `data-n` | Number of bars. |
| `data-step` | Width of one bar slot in viewBox units. |
| `data-bars-x1` | Right end of the bar area (868). The volume profile sits right of it. |
| `data-price-scale` | `log`. |
| `data-price-y0`, `data-price-y1` | y of the top and the bottom of the price panel. |
| `data-price-top`, `data-price-bottom` | Price at those two y values. |

Price at a y inside the price panel:

```
price = exp( ln(top) - (y - y0) / (y1 - y0) * (ln(top) - ln(bottom)) )
```

### 2.3 x position of bar i

```
x_units = (i + 0.5) * data-step                     # viewBox units, i from 0
x_px    = rect.left + rect.width * x_units / 1000   # rect = svg.getBoundingClientRect()
```

Every series draws bar `i` at this x. Drawn coordinates are rounded to 0.1 unit, which
is under 0.1 px.

| Series | Find it with | Bar i |
|---|---|---|
| Candles | `g[data-series="candles"] > g[data-bar="i"]` | First `<path>` is the wick, `M x yHigh V yLow`. Second `<path>` is the body, `M x0 y h w v h h -w z`. x is the wick x. |
| Volume | `g[data-series="volume"] > rect` | The rect at position `i`. Centre is `x + width / 2`. |
| Volume average | `polyline[data-series="volume-avg"]` | Vertex `k` belongs to bar `data-first + k`. |
| VIX | `polyline[data-series="vix"]` | Same. |
| Crash index | `polyline[data-series="crash"]` | Same. |

A line has one `<polyline>` for each run of bars that have a value. `data-n` is the
number of bars in the run. A run of one bar repeats its point, so it has two vertices.
A series that the view does not draw has no element.

Candle and volume classes: `u` up, `d` down, `su` spike and up, `sd` spike and down.

### 2.4 Stored values of bar i

They sit on `g[data-series="candles"] > g[data-bar="i"]`.

| Attribute | Value |
|---|---|
| `data-d` | Date. In the weekly view, the last session of the week. |
| `data-s` | Weekly view only. First session of the week. |
| `data-partial` | Weekly view only. Present on the last bar when its week is not over. |
| `data-c` | Close in dollars. |
| `data-v` | Volume in shares. |
| `data-vix` | VIX close. Absent when the bar has none. |
| `data-cr` | Crash index. Absent when the bar has none. |

Numbers carry no trailing zeros: `30.5` stands for 30.50. They equal the row of
`stress_chart.view_bars(block, view)` at the same index.

### 2.5 Crosshair

The target is `div[data-cross-target="<view>"]`. It listens to `pointerdown`,
`pointermove`, `mousemove`, `touchstart` and `touchmove`. Each one shows the bar under
`clientX` (for a touch, under `touches[0].clientX`):

```
i = round( (clientX - rect.left) / rect.width * 1000 / data-step - 0.5 )   # clamped to 0 .. n-1
```

`pointerleave` and `mouseleave` from a mouse return to the latest bar. After a touch
the read-out stays on the touched bar. The target has `touch-action: pan-y`, so a
vertical swipe still scrolls the page.

The read-out is `[data-crosshair-readout][data-pane="<view>"]`.

| Marker | Meaning |
|---|---|
| `data-bar` | Index of the bar shown. It starts at the latest bar. |
| class `on` | Set while the crosshair is active. |
| `[data-f="date"]` | `data-v` = `data-d` of the bar. Weekly text is `first～last`. |
| `[data-f="close"]` | `data-v` = `data-c`. |
| `[data-f="volume"]` | `data-v` = `data-v` of the bar. |
| `[data-f="vix"]` | `data-v` = `data-vix`. The field exists only when the view draws VIX. |
| `[data-f="crash"]` | `data-v` = `data-cr`. The field exists only when the view draws the crash index. |

When the bar has no VIX close or no crash index, the field has no `data-v` and shows
the text of `data-na-vix` or `data-na-crash`. The vertical line is
`[data-crosshair-line]` inside the target.

### 2.6 Marks on the chart

| Mark | Find it with | Data |
|---|---|---|
| Spike label | `span[data-spike-label="k"]` | `k` is the index in `views.<view>.spikes.episodes`. `data-bar` is the anchor bar. `data-start` and `data-end` are the episode dates. |
| Spike leader | `i[data-spike-leader="k"]` | `data-bar`. Its `left` is the x of that bar in percent of the drawing. |
| Crash-drop marker | `line[data-marker="crash-drop"]` inside `g[data-series="crash-drops"]` | `data-bar`, `data-date`. The group's `data-panel` names the lowest panel, where the markers sit. |
| Trend channel | `g[data-series="channel"]` | `data-direction`, `data-rsq`. Three `line[data-line="upper"]`, `"mid"`, `"lower"`. `data-p0` and `data-p1` are the prices at the first and the last bar. |
| Volume profile | `g[data-series="profile"] > rect[data-band="k"]` | `data-lo`, `data-hi`, `data-vol`. The busiest band has `data-busiest="1"`. |
| Busiest band label | `[data-busiest-label]` | `data-band`, `data-lo`, `data-hi`. |
| Crash index lines | `line[data-level="60"]`, `line[data-level="80"]` | |
| Latest value of a panel | `[data-latest="price"]`, `"volume"`, `"vix"`, `"crash"` | `data-v`. VIX and crash also carry `data-bar`, the bar of that value. |
| Axis ticks | `[data-tick="price"]`, `"vix"`, `"crash"`, `"date"` | |
| Panel titles and backgrounds | `[data-panel-title="price"]`, `rect[data-panel="price"]`, and the same for `volume`, `vix`, `crash` | |

The latest 3 episodes of a view carry a label. Spike labels, leaders and date ticks
exist twice: class `sx-w` for a page of 700 px or wider, class `sx-n` for a narrower
page. One of the two sets is `display:none`. Filter on the computed display.

### 2.7 Legend and rule lines

- `ul[data-chart-legend][data-pane]` has one `li[data-legend-series="…"]` for each
  series and reference line the view draws: `candles`, `spike-candles`, `channel`,
  `last-close`, `profile`, `volume`, `volume-avg`, `vix`, `crash`, `crash-line` (with
  `data-level`), `crash-drops`. Multi-color items carry `data-colors` listing only the
  swatches drawn in that view. A series that is not drawn has no line.
- `section[data-chart-rulebox]` sits under the chart box. Its
  `ul[data-chart-rules][data-pane]` prints each rule: `span[data-rule="<key>"]` holds
  `rules.<key>.text_zh` of the chart data. `b[data-rule-state="<key>"]` says what the
  rule found in this view. Key `crash_drop` prints `legend.crash_drop_zh`.
- A line that says something is not drawn carries `data-legend-note`:

| `data-legend-note` | When |
|---|---|
| `no-spike` | The view has no VIX spike. |
| `no-channel` | The rule yields no channel. |
| `no-profile` | The view has no volume profile. |
| `last-bar` | Weekly view. States whether the last bar is a partial week. |
| `missing` | One line for each missing source (`views.<view>.missing_zh`). |

## 3. Evidence strip

`section[data-evidence-strip]`, `data-available` 1 or 0. When 0 it holds one line,
`p[data-evidence-missing]`.

- One card for each condition: `div[data-evidence="<key>"]`, with `data-horizon` and
  `data-n`. `<key>` is the `key` in `stress_chart.evidence.conditions`.
- Fields in a card: `gain_share` and `median` (the figures), `gain_base` and
  `median_base` (the base rates), `n` (sample count), `base_n`, `period` (sample
  period). In a card the four percentages also carry `data-v`, with up to 6 decimals.
- `span[data-small-sample="1"]` marks a count under `evidence.small_sample_below` (20).
- `details[data-evidence-fold]` holds every horizon: one
  `tr[data-evidence-row="<key>"][data-horizon]` each, with the fields `gain_share`,
  `gain_base`, `median`, `median_base`, `n` and `period`.

## 4. Sections below the first screen

`soxl_quant/report_sections.py` builds everything below the evidence strip: a row of
links, ten sections, and the footer.

```
nav[data-section-nav]                      one link for each section, href="#sec-<id>"
div[data-sections]
  section#sec-<id>[data-sec="<id>"]        data-state = ok, missing or error
    h2                                     the fixed title
    p[data-takeaway="<id>"]                the one-line takeaway; it carries the same data-state
    div[data-sec-main]                     the default view: one chart or one short table
    details[data-fold="<id>-<n>"]          the folds, closed on load, n from 1
footer[data-footer]
  p[data-disclaimer]                       the `disclaimer` string of the feed, once on the page
  p[data-update-status]                    schedule state and the 30-minute reload
  details[data-fold="foot-1"]              glossary; "foot-2" three rules; "foot-3" method and commands
```

The ten ids in page order: `plan`, `why`, `paths`, `crash`, `mood`, `options`,
`sector`, `news`, `proof`, `lessons`.

| `data-state` | Meaning |
|---|---|
| `ok` | The section has its data. The takeaway is computed from the data and has at most 40 characters. |
| `missing` | The source of the section is missing. The takeaway is one plain line that names the source. The section draws no empty chart and no empty table. |
| `error` | The builder of the section raised. The takeaway is one fixed line, and the other sections are unaffected. |

The default view of each section, and the markers inside the sections:

| Marker | Where | Meaning |
|---|---|---|
| `table[data-plan-table]` | `plan` | Entry, stop, two targets, reward to risk, size. |
| `table[data-category-table]` | `why` | The seven score categories with their grades. |
| `[data-viz="scenarios"]` | `paths` | Three bars. Each `[data-scenario]` name is followed by a `[data-prob]`. |
| `[data-analog-n]`, `[data-analog-episodes]` | `paths`, the caption under the bars | The sessions and the separate episodes behind the three odds. |
| `table[data-precursor-table]` | `crash` | The precursors that are on today. `table[data-precursor-rest]` in `crash-1` holds the others. |
| `table[data-mood-table]` | `mood` | Fear and Greed, market pulse, VIX and its term structure. |
| `[data-viz="options-wall"]` | `options` | The open-interest wall. Absent when the options chain is missing. |
| `[data-viz="heatmap"]` with `[data-tiles]` | `sector` | 16 tiles. A tile carries `data-r1`, `data-r5` and `data-r20`, the returns in percent. |
| `table[data-news-table]` | `news` | The three headlines with the largest impact. |
| `table[data-signal-table]` | `proof` | Four signals. `table[data-signal-table-full]` in `proof-1` holds all of them. |
| `table[data-drawdown-table]` | `lessons` | The drawdown of SOXL, SOXX and SPY over the same days. |
| `[data-viz="indicators"]` | `why-3` | Moving averages, Bollinger band, MACD and KD. |
| `[data-viz="lights"]` | `proof-2` | The 120-day lights with the daily rating dots. |
| `table[data-score-table]` | `why-1` | Every factor. A row carries `data-score`. `tr[data-blank]` marks a factor with no reading. |
| `[data-gauge="<key>"]` | `plan-1`, `crash-1`, `mood-2`, `mood-3`, `sector-1`, `options-1` | One of the six gauges of `dashboard.gauges`: `add_on`, `crash`, `put_call`, `macro`, `soxx`, `whales`. A gauge with a grey light is not drawn. |
| `[data-block="<name>"]` | Inside folds | The blocks that `docs/section_log.md` points at: `simple-plan`, `buy-text`, `biggest-thing`, `event-study`, `whale-net`, `peer-options`, `options-scored-blank`. |
| `[data-ext]` | `news` and its folds | Text from an outside source: a news title or a publisher. It is always escaped. A link exists only for an `http` or `https` URL. |

Rules for a script:

- The default view is the page with every `details[data-fold]` closed. A section shows
  at most one of the `[data-viz]` charts and no table of more than 8 rows there.
- The page remembers the folds a reader opened in `sessionStorage["soxl.folds"]`, so
  the 30-minute reload keeps them open. A fresh browser session starts with every fold
  closed.
- Reader text never holds `None`, `n/a`, `nan`, `null`, `undefined`, a `$` with no
  number, or empty brackets. `report_sections.clean()` rewrites the stored strings.
- A note under the first screen, `[data-status-note]`, exists only while the data is an
  intraday snapshot or a provisional close.

## 5. Commands

```
python3 tools/test_report_chart.py              # offline: geometry, stored values, markers, every stored payload
python3 tools/test_report_sections.py           # offline: takeaways, folds, missing sources, placeholder tokens, escaping
python3 tools/qa_render.py --first-screen       # Chrome: boxes of the seven items and the budgets, each view, nine widths
python3 tools/qa_render.py --crosshair 1440 390 # Chrome: scripted pointer and touch on three bars of each view
python3 tools/qa_render.py                      # Chrome: layout checks, each view at nine widths
python3 tools/qa_render.py --snapshots          # Chrome: the page of every stored daily payload at 1440, 768 and 390 px
python3 tools/qa_stress.py                      # Chrome: the same checks on perturbed payloads
python3 tools/qa_render.py --shot first 390 index.html 700 weekly   # first-screen picture in .qa/
```

`--first-screen` checks: at 1440 px all seven items and the rule lines end inside the
top 800 px. At 390 px items 1 to 6 end inside the top 700 px, the chart starts above
1,400 px and is at most 700 px tall. At every width the page and the chart need no
horizontal scroll, no label covers a candle of the latest 20 bars, and the first
screen shows no placeholder token.
