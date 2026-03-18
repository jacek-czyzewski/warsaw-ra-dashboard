# Warsaw RA Dashboard — Code Documentation

## Architecture

The entire application is a single static file: `index.html`. There is no build step, no framework, and no server-side logic. The browser loads the file directly and fetches one data file.

```
index.html   ~930 lines  — all HTML, CSS, and JavaScript
data.json    ~3 MB       — 7,482 event records
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
**Loaded at:** `index.html:469–471`

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

After loading, `rawData` is sorted once by `date` ascending (`index.html:475`). All subsequent filtering operates on this sorted array without mutating it.

---

## Months Index

**Code:** `index.html:487–490`, helper `buildMonths()` at `index.html:904–921`

```js
const months = buildMonths(rawData);
```

`buildMonths` scans the dataset for the earliest and latest YYYY-MM strings, then walks month-by-month to produce a contiguous array even if some months have no events. Each entry is:

```js
{ ym: "2003-10", label: "Oct 2003" }
```

`label` is produced by `Date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })`, giving locale-formatted month names.

The resulting array is used as the slider's index space and as the x-axis labels for the two time-series charts.

---

## Venue Stats Map

**Code:** `index.html:477–485`

```js
const venueStats = {};
rawData.forEach(e => {
  if (!venueStats[e.venue_id]) {
    venueStats[e.venue_id] = { name: e.venue_name, address: e.venue_address, count: 0 };
  }
  venueStats[e.venue_id].count++;
});
```

Pre-computed once on init. Keyed by `venue_id`. Used by:
- The venue tooltip to look up address and total event count
- The Venues chart tooltip's `afterLabel` callback to display the address

`count` here reflects the **total** across all time, not the filtered count. The chart itself re-counts per refresh from the filtered set.

---

## Header

**HTML:** `index.html:343–347`
**CSS:** `index.html:18–37`

```html
<header>
  <h1>Warsaw Parties</h1>
  <span>Resident Advisor · 2003–2026</span>
  <div id="total-badge">0 events</div>
</header>
```

The `#total-badge` element is updated on every `refresh()` call (`index.html:775`):

```js
document.getElementById('total-badge').textContent = `${filtered.length.toLocaleString()} events`;
```

Key CSS parameters:
- `margin-left: auto` on `#total-badge` — pushes it to the far right of the flex header
- `background: #e8ff00` — the neon yellow accent color used consistently across the UI for highlights

---

## Date Range Slider

**HTML:** `index.html:357–373`
**CSS:** `index.html:41–113`
**JS:** `index.html:492–527`

Two overlapping `<input type="range">` elements share the same track. Both have `pointer-events: none` on the input itself; only the thumb (`::-webkit-slider-thumb`) has `pointer-events: all`. This lets both handles sit on top of each other and receive independent drag events.

```html
<input type="range" id="slider-min" min="0" step="1">
<input type="range" id="slider-max" min="0" step="1">
```

`min` and `max` attributes are set to integer indices into the `months` array, not to actual dates:

```js
[sliderMin, sliderMax].forEach(s => { s.min = MIN_IDX; s.max = MAX_IDX; });
```

**`updateFill()`** (`index.html:510–516`) calculates the yellow fill bar position using percentages:

```js
const pct = v => ((v - MIN_IDX) / (MAX_IDX - MIN_IDX)) * 100;
fill.style.left  = pct(lo) + '%';
fill.style.width = (pct(hi) - pct(lo)) + '%';
```

Guard clauses prevent the handles from crossing each other (`index.html:521–526`):

```js
if (+sliderMin.value > +sliderMax.value) sliderMin.value = sliderMax.value;
```

Changing either handle fires `refresh()` immediately on every `input` event (i.e., while dragging, not only on release).

---

## Search Filter

**HTML:** `index.html:439`
**CSS:** `index.html:180–191`
**JS:** `index.html:529–531`, applied at `index.html:752–754`

```html
<input type="text" id="search" placeholder="Search title, venue, artist…">
```

The search fires on every keystroke (`input` event) and resets to page 1. The filter builds a single lowercase haystack by joining four fields:

```js
const haystack = [e.title, e.venue_name, ...e.artists].join(' ').toLowerCase();
if (!haystack.includes(q)) return false;
```

Key characteristics:
- **Substring match** — no tokenisation or fuzzy logic
- **Case-insensitive** — both haystack and query are lowercased
- `...e.artists` spreads the entire artists array, so partial artist name matches work
- The search combines additively with the date range and artist filter — all three must pass

---

## Artist Filter (selectedArtist state)

**JS:** `index.html:535`, `index.html:756–759`

```js
let selectedArtist = null;
```

This is the only piece of non-UI state. When set, it adds an exact artist name match to the filter pipeline (case-insensitive):

```js
if (selectedArtist) {
  const sel = selectedArtist.toLowerCase();
  if (!e.artists.some(a => a.toLowerCase() === sel)) return false;
}
```

Note the difference from the search filter: `some()` matches any artist in the array exactly, whereas the search uses a substring match on a joined string. This means selecting an artist via the chart/table will not inadvertently match partial names.

`selectedArtist` is set from two places:
1. Clicking a bar in the Top Artists chart (`index.html:660–667`)
2. Clicking an artist name in the table (`index.html:889–897`)

In both cases, clicking the currently selected artist sets `selectedArtist = null`, toggling the filter off.

---

## Events per Month Chart

**HTML:** `index.html:378–383`
**JS (init):** `index.html:549–582`
**JS (update):** `index.html:777–787`

Vertical bar chart. Technology: Chart.js 4.4.0, `type: 'bar'`.

Key Chart.js parameters:
- `maintainAspectRatio: false` — required so the fixed `height: 260px` container controls chart height rather than an aspect ratio
- `backgroundColor: '#e8ff00'` — neon yellow bars
- `borderRadius: 3`, `borderSkipped: false` — rounded corners on all four sides of each bar
- `maxTicksLimit: 36` — prevents x-axis from becoming illegible when showing many years; Chart.js auto-skips labels beyond this count
- `maxRotation: 45` — tick labels rotate up to 45° when space is tight
- `chart.update('none')` — the `'none'` animation mode skips transitions for instant re-render on filter change

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

**HTML:** `index.html:385–390`
**JS (init):** `index.html:584–611`
**JS (update):** `index.html:789–798`

Identical structure to the Events per Month chart. Key difference:
- `backgroundColor: '#00c9ff'` — cyan accent to visually distinguish it
- Sums `e.attending` per month rather than counting events

```js
const attendanceCounts = {};
filtered.forEach(e => {
  if (!e.attending) return;   // skip events with 0 or missing attending
  attendanceCounts[ym] = (attendanceCounts[ym] || 0) + e.attending;
});
```

The `if (!e.attending) return` guard skips falsy values (0, null, undefined), so events without attendance data do not contribute zeros that would distort the sum.

Tooltip callback formats numbers with `toLocaleString()` for thousands separators:

```js
label: ctx => ` ${ctx.raw.toLocaleString()} attending`
```

---

## Top Venues Chart

**HTML:** `index.html:392–408`
**JS (init):** `index.html:613–649`
**JS (update):** `index.html:800–819`

Horizontal bar chart. Technology: Chart.js 4.4.0 with `indexAxis: 'y'`.

The chart height is dynamic — it grows with the number of bars so labels are not squished:

```js
document.getElementById('venues-chart-wrap').style.height =
  Math.max(160, topVenues.length * 28) + 'px';
venuesChart.resize();   // tells Chart.js to re-measure the canvas
```

The `28px` per bar is an empirical value that keeps label text from overlapping. `venuesChart.resize()` must be called before `update()` so Chart.js redraws into the new dimensions.

Results are reversed before being assigned to the chart:

```js
const topVenues = Object.entries(venueCounts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, topN)
  .reverse();   // highest count appears at the bottom of a horizontal bar chart
```

Chart.js renders horizontal bars top-to-bottom in label order, so reversing makes the longest bar sit at the bottom (conventional for ranked lists).

**Top-N dropdown** (`index.html:397–401`, `index.html:648–649`) — `<select id="venues-top-n">` with options 10/20/30. Changing the dropdown fires `refresh()` directly.

**Tooltip `afterLabel`** (`index.html:627–631`) looks up the venue address from `venueStats` by matching the label name:

```js
afterLabel: ctx => {
  const entry = Object.values(venueStats).find(v => v.name === ctx.label);
  return entry?.address ? entry.address : '';
}
```

---

## Top Artists Chart

**HTML:** `index.html:411–433`
**JS (init):** `index.html:651–708`
**JS (update):** `index.html:821–844`

Horizontal bar chart, structurally identical to the Venues chart. Key additions:

**Click-to-filter** via Chart.js `onClick` option (`index.html:660–667`):

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

`elements[0].index` is the bar's position in the labels array. `artistsChart.data.labels[…]` retrieves the artist name. Clicking the already-selected artist sets `selectedArtist = null`, clearing the filter.

**Per-bar color** is set dynamically during each refresh (`index.html:840–842`):

```js
artistsChart.data.datasets[0].backgroundColor = topArtists.map(a =>
  selectedArtist && a[0] === selectedArtist ? '#fff' : '#e8ff00'
);
```

The selected artist's bar turns white; all others stay yellow. When no artist is selected, all bars are yellow.

**Artist filter badge** (`index.html:416–419`, `index.html:701–708`) — a yellow pill element that appears inline next to the chart title when a filter is active:

```js
function updateArtistBadge() {
  if (selectedArtist) {
    artistFilterName.textContent = selectedArtist;
    artistFilterBadge.style.display = 'inline-flex';
  } else {
    artistFilterBadge.style.display = 'none';
  }
}
```

The `×` button inside the badge (`#artist-filter-clear`) clears `selectedArtist` and calls `refresh()` (`index.html:694–699`).

Data aggregation iterates the `artists` array on each event (events can have multiple artists):

```js
filtered.forEach(e => {
  e.artists.forEach(a => {
    if (!a) return;
    artistCounts[a] = (artistCounts[a] || 0) + 1;
  });
});
```

This means a single event counts once per artist it contains, so the total across all bars will exceed the event count when events have multiple artists.

---

## Table Column Sorting

**HTML:** `index.html:444–452` — `data-col` attributes on `<th>` elements
**JS:** `index.html:533–547`

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

The `.sorted` CSS class is added to the active `<th>` to turn the sort icon yellow (`index.html:216`). The icon text is updated to `↑` or `↓`.

Sort comparison in `refresh()` (`index.html:763–772`) handles string columns with `.toLowerCase()` and numeric `attending`. Columns without a comparator (`time`, `artists`, `cost`) return `0`, making them effectively unsorted.

---

## Events Table

**HTML:** `index.html:441–456`
**CSS:** `index.html:165–232`
**JS (render):** `index.html:856–897`

The table body is fully re-rendered on every `refresh()` via `tbody.innerHTML = ''` followed by `createElement` + `appendChild` for each row in the current page slice.

**Columns rendered per row:**
- `date` — YYYY-MM-DD string, styled in `#888` with `font-variant-numeric: tabular-nums` for alignment
- `time` — concatenated `start` + `end`, e.g. `"23:00–06:00"` (`index.html:864`)
- `title` — linked to `e.url` with `target="_blank" rel="noopener"`
- `venue` — plain text if no `venue_id`; wrapped in `.venue-name` span if `venue_id` exists, enabling the hover tooltip
- `artists` — first 4 artists (`e.artists.slice(0, 4)`) rendered as clickable `.artist-link` spans
- `attending` — empty string if falsy (avoids displaying `0`)
- `cost` — raw string from data, no currency formatting

**`esc()` helper** (`index.html:923–926`) is applied to all user-visible strings before insertion into `innerHTML` to prevent XSS from data values:

```js
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
```

Event listeners for venue tooltips and artist links are re-attached after every render (`index.html:882–897`), since `innerHTML = ''` destroys previous listeners.

---

## Venue Tooltip

**HTML:** `index.html:349–353`
**CSS:** `index.html:253–270`
**JS:** `index.html:716–740`

A `position: fixed` div with `pointer-events: none` that follows the cursor via a global `mousemove` listener:

```js
document.addEventListener('mousemove', e => {
  if (tooltip.style.display === 'block') {
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top  = (e.clientY - 10) + 'px';
  }
});
```

The +14 / -10 offsets position it slightly below and to the right of the cursor so the tooltip doesn't cover the element being hovered.

`showTooltip(venueId)` reads from the pre-built `venueStats` map. `ttCount` shows the all-time count, not the filtered count, because `venueStats` is computed once from `rawData`.

`z-index: 9999` ensures the tooltip renders above Chart.js canvases.

---

## Pagination

**HTML:** `index.html:458–462`
**JS:** `index.html:710–714`, `index.html:846–854`

```js
const PAGE_SIZE = 50;
let currentPage = 1;
```

`PAGE_SIZE` is a hardcoded constant. `currentPage` is reset to `1` by the search input, artist filter, and sort column click handlers. It is clamped to `totalPages` each refresh to handle cases where filtering reduces the result set:

```js
currentPage = Math.min(currentPage, totalPages);
```

The prev/next buttons are disabled via the `disabled` attribute when at the first or last page respectively. No direct page-number input is provided.

---

## `refresh()` — Central Orchestrator

**JS:** `index.html:742–898`

`refresh()` is the single function called whenever any filter or UI state changes. It runs top-to-bottom in one synchronous pass:

1. Read current filter state from DOM (`sliderMin.value`, `sliderMax.value`, `searchEl.value`)
2. Filter `rawData` into `filtered` — applies date range, text search, and artist filter in one `.filter()` call
3. Sort `filtered` in place
4. Update `#total-badge`
5. Aggregate `monthCounts` → update Events per Month chart
6. Aggregate `attendanceCounts` → update Attendance chart
7. Aggregate `venueCounts` → update Venues chart (resize container, call `venuesChart.resize()`)
8. Aggregate `artistCounts` → update Artists chart (resize container, call `artistsChart.resize()`)
9. Clamp and compute pagination
10. Render table rows, re-attach event listeners

All chart updates use `chart.update('none')` to suppress animations, keeping the dashboard responsive during rapid slider or search interactions.

---

## CSS Design Tokens

The colour palette is defined inline throughout the CSS. Key values:

| Value | Role |
|---|---|
| `#0d0d0d` | Page background |
| `#161616` | Card/section background |
| `#2a2a2a` | Borders, inactive track |
| `#e8ff00` | Primary accent — yellow (bars, badge, active sort icon, hover states) |
| `#00c9ff` | Secondary accent — cyan (Attendance chart only) |
| `#e0e0e0` | Primary text |
| `#888` | Secondary text (dates, labels) |
| `#555` / `#666` | Tertiary text (chart tick labels, pagination) |

The layout uses CSS Grid for the three-chart row (`grid-template-columns: 1fr 1fr 1fr`, `index.html:137`) and Flexbox for the header, slider header, and section headers.
