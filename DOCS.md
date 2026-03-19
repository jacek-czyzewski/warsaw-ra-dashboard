# Warsaw RA Dashboard — Code Documentation

## Architecture

The entire application is a single static file: `index.html`. There is no build step, no framework, and no server-side logic. The browser loads the file directly and fetches one data file.

```
index.html   ~1100 lines  — all HTML, CSS, and JavaScript
data.json    ~3 MB        — 7,482 event records
```

**Technology stack:**
| Layer | Technology |
|---|---|
| Markup | HTML5 |
| Styling | Embedded CSS (dark theme) |
| Logic | Vanilla JavaScript (ES2020) |
| Charts | [Chart.js 4.4.0](https://www.chartjs.org/) via jsDelivr CDN |
| Data | Static JSON fetched at runtime |

---

## Data Source

**File:** `data.json`
**Loaded at:** top of `<script>` block

```js
fetch('data.json')
  .then(r => r.json())
  .then(init);
```

The fetch result is passed directly into `init()`. No caching or persistence — data is re-filtered in memory on every user interaction.

### Event record shape

Each of the 7,482 objects in the array has these fields:

| Field | Type | Example |
|---|---|---|
| `date` | `string` (YYYY-MM-DD) | `"2003-10-17"` |
| `title` | `string` | `"Mixologia"` |
| `url` | `string` | `"https://ra.co/events/…"` |
| `venue_id` | `string` | `"264153"` |
| `venue_name` | `string` | `"TBA - Nowa Lokomotywa"` |
| `venue_address` | `string` | `"Chłodna 35/37, Warsaw"` |
| `artists` | `string[]` | `["Chris Liebing", "Carla Roca"]` |
| `attending` | `number` | `142` |
| `cost` | `string` | `"45"` |
| `start` | `string` (HH:MM) | `"23:00"` |
| `end` | `string` (HH:MM) | `"06:00"` |
| `image` | `string` | `""` (mostly empty) |

After loading, `rawData` is sorted once by `date` ascending. All subsequent filtering operates on this sorted array without mutating it.

---

## Months Index

**Helper:** `buildMonths()` near the bottom of `<script>`

```js
const months = buildMonths(rawData);
```

`buildMonths` scans the dataset for the earliest and latest YYYY-MM strings, then walks month-by-month to produce a contiguous array even if some months have no events. Each entry is:

```js
{ ym: "2003-10", label: "Oct 2003" }
```

`label` is produced by `Date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })`, giving locale-formatted month names.

The resulting array is used as the slider's index space, the source for year buttons, and the x-axis labels for the two time-series charts.

---

## Venue Stats Map

Pre-computed once inside `init()` before any UI setup:

```js
const venueStats = {};
rawData.forEach(e => {
  if (!venueStats[e.venue_id]) {
    venueStats[e.venue_id] = { name: e.venue_name, address: e.venue_address, count: 0 };
  }
  venueStats[e.venue_id].count++;
});
```

Keyed by `venue_id`. Used by:
- The venue tooltip to look up address and total event count
- The Venues chart tooltip's `afterLabel` callback to display the address

`count` reflects the **total** across all time, not the filtered count. The chart re-counts per refresh from the filtered set.

---

## Header

```html
<header>
  <h1>Warsaw Parties</h1>
  <span>Resident Advisor · 2003–2026</span>
  <div id="total-badge">0 events</div>
</header>
```

The `#total-badge` element is updated on every `refresh()` call:

```js
document.getElementById('total-badge').textContent = `${filtered.length.toLocaleString()} events`;
```

Key CSS:
- `margin-left: auto` on `#total-badge` — pushes it to the far right of the flex header
- `background: #ff7a00` — the orange accent color used consistently across the UI for highlights

---

## Date Range Slider

Two overlapping `<input type="range">` elements share the same track. Both have `pointer-events: none` on the input itself; only the thumb (`::-webkit-slider-thumb`) has `pointer-events: all`. This lets both handles sit on top of each other and receive independent drag events.

```html
<input type="range" id="slider-min" min="0" step="1">
<input type="range" id="slider-max" min="0" step="1">
```

`min` and `max` attributes are set to integer indices into the `months` array, not to actual dates:

```js
[sliderMin, sliderMax].forEach(s => { s.min = MIN_IDX; s.max = MAX_IDX; });
```

**`updateFill()`** calculates the orange fill bar position as percentages of the total range:

```js
const pct = v => ((v - MIN_IDX) / (MAX_IDX - MIN_IDX)) * 100;
fill.style.left  = pct(lo) + '%';
fill.style.width = (pct(hi) - pct(lo)) + '%';
```

Guard clauses prevent the handles from crossing each other:

```js
if (+sliderMin.value > +sliderMax.value) sliderMin.value = sliderMax.value;
```

Changing either handle fires `refresh()` on every `input` event (i.e., while dragging, not only on release). Both handlers also call `activeYear = null; updateYearButtons()` to deactivate any highlighted year button when the slider is moved manually.

### Year Buttons

A row of pill buttons is rendered inside the slider section, one per calendar year found in the dataset. They are generated dynamically in JS from the `months` array:

```js
const years = [...new Set(months.map(m => m.ym.slice(0, 4)))];
years.forEach(year => {
  const btn = document.createElement('button');
  btn.className = 'year-btn';
  btn.textContent = year;
  btn.addEventListener('click', () => {
    const lo = months.findIndex(m => m.ym.startsWith(year));
    const hi = months.reduce((acc, m, i) => m.ym.startsWith(year) ? i : acc, lo);
    sliderMin.value = lo;
    sliderMax.value = hi;
    activeYear = year;
    updateYearButtons();
    updateFill();
    refresh();
  });
  yearButtonsEl.appendChild(btn);
});
```

`findIndex` locates the first month of the year; `reduce` scans for the last. This correctly handles partial years at the start (Oct 2003) and end (Mar 2026) of the dataset.

**`activeYear`** state variable (`let activeYear = null`) tracks the currently highlighted year. **`updateYearButtons()`** toggles the `.active` CSS class on matching buttons:

```js
function updateYearButtons() {
  yearButtonsEl.querySelectorAll('.year-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent === activeYear);
  });
}
```

Active year buttons are styled orange (`background: #ff7a00`). Dragging either slider handle sets `activeYear = null` and clears all highlights.

---

## Search Filter

```html
<input type="text" id="search" placeholder="Search title, venue, artist…">
```

Fires on every keystroke (`input` event) and resets to page 1. Builds a single lowercase haystack by joining multiple fields:

```js
const haystack = [e.title, e.venue_name, ...e.artists].join(' ').toLowerCase();
if (!haystack.includes(q)) return false;
```

Key characteristics:
- **Substring match** — no tokenisation or fuzzy logic
- **Case-insensitive** — both haystack and query are lowercased
- `...e.artists` spreads the entire artists array, so partial artist name matches work
- Combines additively with date range and artist filter — all three must pass

---

## State Variables

All mutable state lives inside the `init()` closure:

| Variable | Type | Purpose |
|---|---|---|
| `sortCol` | `string` | Active sort column key |
| `sortDir` | `1` or `-1` | Sort direction |
| `selectedArtist` | `string \| null` | Artist filter set by chart/table click |
| `activeYear` | `string \| null` | Currently highlighted year button (`"2015"` etc.) |
| `lastFiltered` | `Event[]` | Snapshot of filtered array for CSV export |
| `topPartiesData` | `Event[]` | Top 10 events by attendance, for chart tooltip lookups |
| `currentPage` | `number` | Current pagination page |

---

## Artist Filter (`selectedArtist`)

When set, adds an exact artist name match to the filter pipeline (case-insensitive):

```js
if (selectedArtist) {
  const sel = selectedArtist.toLowerCase();
  if (!e.artists.some(a => a.toLowerCase() === sel)) return false;
}
```

Note the difference from the search filter: `some()` matches any artist in the array exactly, whereas the search uses a substring match on a joined string. This prevents partial-name collisions.

`selectedArtist` is set from two places:
1. Clicking a bar in the Top Artists chart (`onClick` option in the Chart.js config)
2. Clicking an artist name span in the table (`.artist-link` click handler, re-attached after each render)

Clicking the currently selected artist sets `selectedArtist = null`, toggling the filter off. Both entry points call `updateArtistBadge()` then `refresh()`.

**Artist filter badge** — an orange pill element (`#artist-filter-badge`) appears inline next to the Top Artists chart title when a filter is active. The `×` button inside it clears `selectedArtist`.

---

## Events per Month Chart

Vertical bar chart, `type: 'bar'`, orange bars.

Key Chart.js parameters:
- `maintainAspectRatio: false` — fixed `height: 260px` container controls height
- `backgroundColor: '#ff7a00'` — orange bars
- `borderRadius: 3`, `borderSkipped: false` — rounded corners on all four sides
- `maxTicksLimit: 36` — Chart.js auto-skips x-axis labels beyond this count
- `maxRotation: 45` — tick labels rotate up to 45° when space is tight
- `chart.update('none')` — skips transition animations for instant re-render

Data population in `refresh()`:

```js
const monthCounts = {};
filtered.forEach(e => {
  const ym = e.date.slice(0, 7);
  monthCounts[ym] = (monthCounts[ym] || 0) + 1;
});
const chartMonths = months.filter(m => m.ym >= lo && m.ym <= hi);
chart.data.labels = chartMonths.map(m => m.label);
chart.data.datasets[0].data = chartMonths.map(m => monthCounts[m.ym] || 0);
```

`chartMonths` uses the pre-built contiguous months array so months with zero events still appear as zero-height bars rather than being absent.

---

## Attendance per Month Chart

Identical structure to the Events per Month chart. Key difference: sums `e.attending` per month rather than counting events.

```js
const attendanceCounts = {};
filtered.forEach(e => {
  if (!e.attending) return;   // skip events with 0 or missing attending
  attendanceCounts[ym] = (attendanceCounts[ym] || 0) + e.attending;
});
```

The `if (!e.attending) return` guard skips falsy values (0, null, undefined), so events without attendance data do not distort the sum.

Both this chart and the Events per Month chart use `backgroundColor: '#ff7a00'` (orange). They are visually distinguished by their y-axis scale and tooltip text rather than color.

---

## Top Venues Chart

Horizontal bar chart, `indexAxis: 'y'`, orange bars. Sorted **descending from the top** — the most-visited venue appears at position 1.

```js
const topVenues = Object.entries(venueCounts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, topN);
```

The chart height is dynamic to avoid label crowding:

```js
document.getElementById('venues-chart-wrap').style.height =
  Math.max(160, topVenues.length * 28) + 'px';
venuesChart.resize();   // re-measures the canvas before update
```

`28px` per bar is an empirical value that prevents label overlap. `venuesChart.resize()` must precede `update()`.

**Top-N dropdown** — `<select id="venues-top-n">` with options 10/20/30. Changing it fires `refresh()` directly.

**Tooltip `afterLabel`** looks up the venue address from `venueStats` by matching the label name:

```js
afterLabel: ctx => {
  const entry = Object.values(venueStats).find(v => v.name === ctx.label);
  return entry?.address ? entry.address : '';
}
```

---

## Top Artists Chart and Top Parties Row

The Top Artists and Top Parties charts share a two-column CSS Grid row:

```html
<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px">
  <!-- Top Artists -->
  <!-- Top Parties -->
</div>
```

### Top Artists Chart

Horizontal bar chart, `indexAxis: 'y'`, sorted **descending from the top**.

```js
const topArtists = Object.entries(artistCounts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, topNA);   // no .reverse() — highest count at top
```

Data aggregation counts per artist across all events in the filtered set. Because events can have multiple artists, a single event contributes once per artist it contains — the total across all bars can exceed the filtered event count.

**Click-to-filter** via Chart.js `onClick` option:

```js
onClick: (evt, elements) => {
  if (!elements.length) return;
  const label = artistsChart.data.labels[elements[0].index];
  selectedArtist = selectedArtist === label ? null : label;
  currentPage = 1;
  updateArtistBadge();
  refresh();
}
```

**Per-bar color** is set dynamically on each refresh. The selected artist's bar turns white; all others stay orange:

```js
artistsChart.data.datasets[0].backgroundColor = topArtists.map(a =>
  selectedArtist && a[0] === selectedArtist ? '#fff' : '#ff7a00'
);
```

**Top-N dropdown** — `<select id="artists-top-n">` with options 10/20/30.

### Top 10 Parties by Attendance Chart

Horizontal bar chart showing the 10 individual events with the highest `attending` count within the current filtered set. Fixed at 10 — no top-N selector.

```js
topPartiesData = filtered
  .filter(e => e.attending > 0)
  .sort((a, b) => b.attending - a.attending)
  .slice(0, 10);
```

Labels are event titles (`e.title`). The chart tooltip uses the `topPartiesData` array (stored as a state variable in the `init()` closure) to look up the event date and venue for the `afterLabel` line:

```js
afterLabel: ctx => {
  const e = topPartiesData[ctx.dataIndex];
  return e ? `${e.date}  ·  ${e.venue_name}` : '';
}
```

`topPartiesData[ctx.dataIndex]` works because the chart labels array and `topPartiesData` are always built together in the same `refresh()` pass and maintain the same order.

---

## Table Column Sorting

`data-col` attributes on `<th>` elements identify sortable columns. A single delegated listener covers all headers:

```js
let sortCol = 'date', sortDir = 1;
document.querySelectorAll('thead th[data-col]').forEach(th => {
  th.addEventListener('click', () => {
    if (col === sortCol) sortDir *= -1;
    else { sortCol = col; sortDir = 1; }
    …
  });
});
```

`sortDir` is `1` (ascending) or `-1` (descending). Clicking the active column flips direction; clicking a different column resets to ascending.

The `.sorted` CSS class turns the sort icon orange. Sort comparison in `refresh()` handles string columns with `.toLowerCase()` and numeric `attending`. Columns without a comparator (`time`, `artists`, `cost`) return `0`.

---

## Events Table

The table body is fully re-rendered on every `refresh()` via `tbody.innerHTML = ''` followed by row construction for each event in the current page slice.

**Columns rendered per row:**
- `date` — YYYY-MM-DD, `font-variant-numeric: tabular-nums` for alignment
- `time` — concatenated `start` + `end`, e.g. `"23:00–06:00"`
- `title` — linked to `e.url` with `target="_blank" rel="noopener"`
- `venue` — plain text if no `venue_id`; wrapped in `.venue-name` span if `venue_id` exists, enabling the hover tooltip
- `artists` — first 4 artists rendered as clickable `.artist-link` spans; clicking one sets `selectedArtist`
- `attending` — empty string if falsy (avoids displaying `0`)
- `cost` — raw string from data, no currency formatting

**`esc()` helper** is applied to all user-visible strings before insertion into `innerHTML` to prevent XSS:

```js
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
```

Event listeners for venue tooltips and artist links are re-attached after every render, since `innerHTML = ''` destroys previous listeners.

### Export CSV

A button (`#btn-export`) sits in the table header to the left of the search box. On click it exports the current `lastFiltered` array — the full filtered result set in its current sort order, all pages — as a CSV download.

```js
document.getElementById('btn-export').addEventListener('click', () => {
  const cols = ['date','time','title','url','venue','address','artists','attending','cost'];
  const rows = lastFiltered.map(e => [ … ]
    .map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
  const csv = [cols.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'warsaw-ra-events.csv'; a.click();
  URL.revokeObjectURL(url);
});
```

`lastFiltered` is a snapshot taken at the start of each `refresh()` call (after filtering and sorting, before pagination). Fields are double-quote wrapped with internal `"` escaped as `""` per RFC 4180. The `artists` field joins all artist names with `; ` as a separator.

---

## Venue Tooltip

A `position: fixed` div (`#tooltip`) with `pointer-events: none` follows the cursor via a global `mousemove` listener:

```js
document.addEventListener('mousemove', e => {
  if (tooltip.style.display === 'block') {
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top  = (e.clientY - 10) + 'px';
  }
});
```

The +14 / -10 offsets place it slightly below and to the right of the cursor. `showTooltip(venueId)` reads from `venueStats`. `ttCount` shows the all-time count (from `venueStats`), not the filtered count. `z-index: 9999` keeps it above Chart.js canvases.

---

## Pagination

```js
const PAGE_SIZE = 50;
let currentPage = 1;
```

`PAGE_SIZE` is a hardcoded constant. `currentPage` is reset to `1` by the search input, artist filter, year buttons, and sort column click handlers. It is clamped to `totalPages` each refresh:

```js
currentPage = Math.min(currentPage, totalPages);
```

Prev/next buttons are disabled via the `disabled` attribute at the boundaries.

---

## `refresh()` — Central Orchestrator

Called whenever any filter or UI state changes. Runs top-to-bottom in one synchronous pass:

1. Read filter state from DOM (`sliderMin.value`, `sliderMax.value`, `searchEl.value`)
2. Filter `rawData` into `filtered` — date range, text search, and `selectedArtist` in one `.filter()` call
3. Sort `filtered` in place by `sortCol` / `sortDir`
4. Snapshot `lastFiltered = filtered` for CSV export
5. Update `#total-badge`
6. Aggregate `monthCounts` → update Events per Month chart
7. Aggregate `attendanceCounts` → update Attendance per Month chart
8. Aggregate `venueCounts` → update Top Venues chart (resize container, `venuesChart.resize()`)
9. Aggregate `artistCounts` → update Top Artists chart (resize container, `artistsChart.resize()`)
10. Compute `topPartiesData` → update Top Parties chart (resize container, `partiesChart.resize()`)
11. Clamp pagination, compute page slice
12. Render table rows, re-attach venue tooltip and artist link listeners

All chart updates use `chart.update('none')` to suppress animations, keeping the dashboard responsive during rapid slider or search interactions.

---

## CSS Design Tokens

The colour palette is defined inline throughout the CSS. Key values:

| Value | Role |
|---|---|
| `#0d0d0d` | Page background |
| `#161616` | Card/section background |
| `#2a2a2a` | Borders, inactive slider track |
| `#ff7a00` | Primary accent — orange (all bars, badges, active states, hover highlights) |
| `#e0e0e0` | Primary text |
| `#888` | Secondary text (dates, axis labels) |
| `#555` / `#666` | Tertiary text (chart tick labels, pagination info) |
| `#fff` | Selected artist bar highlight |

There is a single accent color (`#ff7a00`) used for all interactive and highlighted elements — bars in every chart, the slider fill and thumb border, active year buttons, the artist filter badge, sort icons, and hover states. The only exception is the selected artist bar, which uses `#fff` (white) to stand out from the orange background.

**Layout:**
- Three-chart row: CSS Grid `grid-template-columns: 1fr 1fr 1fr`
- Top Artists + Top Parties row: CSS Grid `grid-template-columns: 1fr 1fr`
- Header, slider header, section headers: Flexbox
- Max content width: `1400px`, centered with `margin: 0 auto`
