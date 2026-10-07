# Legacy Shortcut diagnostics

Historical diagnostics for the retained Shortcut generator. This is not
the current recommended phone-sync workflow and does not establish that
automatic sync is working. Health export parsing and authenticated ingest
are separate supported project components.

## Reading the first real run

Owner's first manual run of the Shortcut is a one-shot source of truth. Almost
everything the phone side had to guess at is answered by it, and if it is only
half-read the guesses stay guesses. Work through all five.

Data to pull (needs the ingest key, which lives on the phone and in the Worker
secret - not in this repo):

    GET /health/status      totals and last write
    GET /health/data        the snapshot the page renders from

## 1. Did the catch-up pass fetch recent data or ancient data?

The catch-up queries are capped at 150 samples per type and sorted newest-first
by an explicit sort order. If iOS honours the sort, the oldest stored rows taper
back a few days per metric and today is dense. If iOS IGNORES the sort, the
oldest rows cluster at the start of history and today is thin - that means every
future catch-up run re-fetches the same ancient 150 readings.

Look at: min and max sample day per metric, and where the bulk sits.

That failure is not corruption. Today's numbers come from a separate uncapped
"is today" query, so they are unaffected either way. What is lost is the safety
net for a day where every run failed; see RECOVERY below.

## 2. unparsed_timestamps

Every ingest response reports how many timestamps it could not read, with up to
three examples. Anything above zero means Health's date format on this phone is
one the parser does not know yet. The examples are the fix: they go straight
into parseSampleTs, server-side, no new Shortcut.

## 3. Distinct sources per metric

    SELECT metric, COUNT(DISTINCT src) FROM hsample GROUP BY metric

Two or more sources on StepCount, DistanceWalkingRunning or the energy metrics
means the richest-source rule is doing real work - an iPhone and a Watch are
being kept apart instead of added together. One source everywhere means either
they only wears one device that day, or Source came back empty and everything
collapsed into "unknown". The second case is worth checking: empty sources make
the cumulative rule a no-op.

## 4. Which guessed picker labels are real

Only four of roughly 190 Find Health Samples labels are confirmed by
observation; the rest are SDK-derived guesses, and several metrics are queried
under two labels because I do not know which exists. Whichever label returned
rows is the real one.

Any metric with zero rows is either absent from their Health data or has a wrong
label - those two look identical from here, so compare against the export.zip
catalogue before concluding a label is wrong.

Record the confirmed labels in `shortcut/generate_shortcut.py` (the ALIASES
table) so the next generated file starts from fact rather than guesswork.

## 5. Sleep, workouts, category logs

- sleep_daily should hold one row for the waking day with core/deep/rem/awake
  minutes. Duplicate stage windows arrive on purpose (start-of-day and
  end-of-day queries overlap) and are deduped by start|end|stage.
- workouts should show duration in minutes and distance in km, parsed from the
  phone's display strings ("32:30", "3.24 mi").
- Category logs store the word in hsample.txt with value NULL, plus a daily
  count under `<Type>Count`. A category row with value 0 and no txt means the
  numeric coercion regressed.

## RECOVERY: what to do if the sort was ignored

No new Shortcut is needed, in any of these cases.

1. Nothing is corrupted. Stale catch-up rows are real readings with real
   timestamps; they upsert onto the days they belong to and are keyed on
   metric+time+source, so re-sending them forever is idempotent.
2. The only cost is bandwidth and wasted D1 writes. If that becomes annoying,
   the Worker can drop sample rows older than N days at write time - a few
   lines in healthIngestShortcut, server-side.
3. The thing actually lost is the safety net for a day where every scheduled run
   failed. That gap is covered by re-importing Export All Health Data through
   `parser/hkparse.py`, which backfills any day at full resolution.

So a failed sort costs bandwidth and a safety net, not correctness, and both
have server-side answers.
