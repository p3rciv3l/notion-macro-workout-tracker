# Setting up your own copy

Accounts you need first: a Notion workspace you control, a Cloudflare
account, and an iPhone for the Apple Health half (optional if you only want
food and workouts).

1. **Notion.** Create five databases and share them with a Notion
   integration: a rollup (one row per day, numeric columns per macro), a Log
   (one row per item; the column contract is in
   [FORMATTING.md](../FORMATTING.md)), and three workout databases (Push,
   Pull, Legs). Wire `POST /notion-webhook` as the webhook target so edits
   refresh the chart cache.
2. **Cloudflare.** Create one D1 database and one KV namespace; fill
   `worker/wrangler.toml.example` -> `wrangler.toml` (git-ignored).
3. **Env vars (plain text, on the worker):** `DATABASE_ID` (rollup),
   `NOTION_LOG_DB` (Log), `WORKOUT_DB_PUSH` / `WORKOUT_DB_PULL` /
   `WORKOUT_DB_LEGS`, `DAY_PAGES_JSON` (date -> Notion page URL map, used for
   day-popup deep links).
4. **Secrets:** `NOTION_TOKEN`, `GATE_PASSWORD`, `HEALTH_INGEST_KEY`,
   `EMBED_TOKEN` (legacy - the live embed capability rotates via the
   `embed_token_v1` KV key described in
   [technical.md](technical.md#access-model)).
5. **CI secrets/vars:** `CF_API_TOKEN` + `CF_ACCOUNT_ID` (secrets) for the
   Deploy job; `SMOKE_K` (secret) + `SMOKE_BASE` (variable) for Smoke.
6. **Deploy.** Push to `main` to run tests only. Push to `deploy/prod` for production;
   Actions runs Test (`node --check` + parser
   unit tests + the feature guard), Deploy (`ci/deploy.sh`), then Smoke
   (`ci/smoke.sh` fails red if user-facing features vanish from the served
   HTML, so a silent feature rollback cannot ship).
7. **Optional legacy iOS Shortcut.** `HEALTH_INGEST_ENDPOINT=... python3
   shortcut/generate_health.py /tmp/out` writes the shortcut files; the
   ingest key is read at run time from a text file in iCloud Drive, never
   baked into the shortcut.

Check Cloudflare's current plan limits before choosing a hosting plan.

An agent can drive this entire setup: creating the Notion databases, wiring
the worker bindings, and importing a Health export. The Shortcut generator
is retained as a legacy option, not a claim that automatic phone sync is working. Point it at this repo and at
[FORMATTING.md](../FORMATTING.md) and it picks up the logging conventions
automatically, photo-driven logging included.
