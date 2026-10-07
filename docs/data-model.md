# Data model

## Notion: the rollup database (`DATABASE_ID`)

One row per day; one numeric column per macro. The chart reads the day
totals from here for the fast path and aggregates the Log when needed. Date
is the row's date property; macros are numeric columns named for the eight
tracked macros.

## Notion: the Log database (`NOTION_LOG_DB`)

One row per food item. The full column contract and writing rules are in
[FORMATTING.md](../FORMATTING.md); the summary:

- `Meal` (title) - the item name; brand + product when established
- `Items` (rich text) - the basis note: label values, arithmetic, source
- `Date` (date) - the day it belongs to
- `Type` (select) - e.g. `Home - packaged label`, `Restaurant - estimated`
- `Calories`, `Protein`, `Carbs`, `Fat`, `Saturated Fat`, `Fiber`, `Sugar`,
  `Sodium` (numbers)
- `Source` (url) - the macro evidence: label photo or supplier page/email
- `Day`, `Recipe` (relations) - optional links to the rollup row or a
  recipe record

The worker reads these property names. Conventions change at the content
level (see FORMATTING.md Rule 9), never by renaming schema properties.

## Notion: the workout databases (Push / Pull / Legs)

One row per session; columns are exercises, cells are free text:
`165x6, 175x6 (good reps)`. The parser pulls `weight x reps` pairs, drops
parenthesized text, and takes the top set. A 2-rep-or-fewer top set counts
as a max-attempt signal and falls back to the next heaviest set. Pull-up
columns invert slightly: the number is assist weight, so the parser takes
the minimum. Unparseable cell = gap, never a zero. Parsed top sets are
written back into per-exercise `(wt)` number columns; the free-text cell
stays authoritative.

## D1 (Apple Health)

Auto-created from `worker/schema.sql` on first request. Times are seconds
since epoch and values are canonical SI; the pages convert to imperial at
render so the stored data never double-converts.

- `metric_daily(metric, day, unit, value, mn, mx, cnt, src, updated_at)` -
  per-day aggregates per metric (`cnt` = contributing samples, `src` =
  winning device)
- `sleep_daily(day, core, deep, rem, awake, in_bed, updated_at)` - sleep
  minutes by stage per night
- `workouts(id, day, type, duration_min, distance_km, energy_kcal, avg_hr,
  source)` - Apple Watch/other workouts
- `hsample(metric, ts, end_ts, src, day, unit, value)` - raw samples; the
  richest-source rule keeps one device per metric (iPhone vs Watch) instead
  of adding both

## KV (chart cache + config)

Cache keys that refresh in the background when Notion fires the webhook:
`cbum:page:html`, `cbum:health:html`, `rows_cache_v1`, `workout_cache_v*`,
`items_cache_v*`. Config and rotation keys: `ver_v1` (page data version),
`embed_token_v1` (the live Notion-embed capability), `goals_v1` (macro goal
overrides), `ingest_attempts_v1` and `last_event` (ingest forensics),
`chartjs_umd_v441` (vendored Chart.js pin). After a worker deploy that
changes chart-page JS, delete `cbum:page:html` and `cbum:health:html` so the
next render picks up the new bundle.
