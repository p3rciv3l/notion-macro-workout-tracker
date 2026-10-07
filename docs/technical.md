# Technical reference

## What the worker serves

- `/` - the macros chart. Stacked daily bars for the eight tracked macros
  (calories, protein, carbs, fat, saturated fat, sugar, fiber, sodium), each
  with a goal line. Clicking a bar expands it into the items logged that day.
  Data comes from two Notion databases: a daily rollup and a per-item Log.
  Daily goals are editable in-page at `/goals`; saved values win over the
  code defaults.
- Workout charts, same page, from three Notion databases (Push / Pull /
  Legs). Cells are free text like `165x6, 175x6 (good reps)`; a
  deterministic parser pulls weight x rep pairs, drops anything in
  parentheses, and takes the session's top set (a 2-rep-or-fewer top set
  falls back to the next heaviest; pull-up columns take the minimum because
  the number there is assist weight). A cell that doesn't parse becomes a
  gap, never a zero. Parse results are written back into per-exercise `(wt)`
  number columns; the free-text cell stays authoritative.
- `/health` - the Apple Health dashboard: body composition, activity, heart,
  sleep by stage, workouts, and the long tail of everything else, imperial
  units over a rolling window. Data lives in D1 in canonical SI units and is
  converted at render.
- JSON feeds the pages poll: `/data.json`, `/workout.json`,
  `/health/data.json`, `/health/samples.json`, plus `/v` (a version string
  an open page polls to refresh itself) and `/status` / `/health/status`.
- `POST /notion-webhook` - Notion fires this on database edits; the worker
  verifies it, 200s, and refreshes its KV cache in the background.
- `POST /health/ingest` and `POST /health/seed` - the Apple Health write
  endpoints, authenticated by an `X-Health-Key` header.

## Access model

The chart is password-gated: a correct password sets a signed device cookie
good for a year (`/logout` clears it). Notion embed frames carry a separate,
rotatable capability token (`?k=`) because the Notion iOS webview blocks
third-party storage. Rotate it by overwriting the `embed_token_v1` KV key
and bumping `ver_v1`; rotate the gate password with
`wrangler secret put GATE_PASSWORD` (or the Cloudflare API) and every device
re-enters it once. Keep the actual password in your password manager
(Bitwarden, 1Password, ...).

## Repo layout

```
worker/worker.js            the worker: charts, health pages, ingest endpoints
worker/schema.sql           the D1 schema (also auto-created on first request)
worker/wrangler.toml.example  every binding and env var, with paste-me placeholders
ci/deploy.sh                settings fetch-merge + multipart PUT (no build step)
ci/smoke.sh                 live feature-preservation smoke; needs SMOKE_BASE + SMOKE_K
.github/workflows/deploy.yml  Test on main; Test -> Deploy -> Smoke on deploy/prod
shortcut/generate_health.py   legacy generator for iOS Shortcuts that POST Apple Health to /health/ingest
shortcut/shortcut_lib.py      plist action builders shared by the generator
parser/hkparse.py           streams the Health app's export.zip into daily-aggregate seed JSON for /health/seed
parser/test_hkparse.py        parser unit tests
tests/feature-guard.mjs     static+render checks that key features can't be deleted silently
tests/PORT_NOTES.md         archaeology notes from a mid-history minification event
docs/first-run-readout.md   how to read the first real Shortcut run
FORMATTING.md               THE contract for agents writing rows to the Log database
```

## CI pipeline

Push to `main` runs Test (`node --check worker/worker.js`, parser unit
tests, and `tests/feature-guard.mjs`). Production changes are pushed to
`deploy/prod`, which runs Test, Deploy
(`ci/deploy.sh` - pulls current worker settings first so bindings survive,
then multipart PUTs the script as `application/javascript+module`), then
Smoke (`ci/smoke.sh` - polls the live page for marker strings that pin
user-facing features: window toggles, the Average view, workout blow-up
rows/hatching). GitHub Action secrets are snapshotted at run creation, so
rotate a secret before pushing, not mid-run.
