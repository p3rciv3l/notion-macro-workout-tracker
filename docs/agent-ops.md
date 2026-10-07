# Running this repo as an agent

Two lanes: logging rows and operating the worker. The contract for the
first is [FORMATTING.md](../FORMATTING.md); read it fully before writing a
single row. This file is the ops half.

## Logging

- Photos are primary input (FORMATTING.md Rule 11): read the label off the
  photo and attach it as the row's evidence. Label text beats established
  bases, bases beat published sources, published sources beat estimates;
  never guess a macro a label doesn't show.
- One row per item, brand + product in the title when the brand is
  established, ingredients list instead of meals.
- Container tallies run exactly: `% of block/carton` in Items, with dates
  and the running total.
- The receipt beats the cart. A cart screenshot is a pre-checkout guess;
  when the post-checkout receipt disagrees, the wrong row is deleted, not
  adjusted.
- Never email companies for nutrition info. If numbers can't be grounded,
  estimate honestly and say so in Items.

## Operating

- Deploys go through CI: push to `deploy/prod`, confirm Test -> Deploy -> Smoke all
  land green. `main` runs tests without deploying. Secrets are snapshotted at run creation, so rotate before
  pushing.
- After a UI/JS deploy, purge the page cache (`cbum:page:html`,
  `cbum:health:html` in KV) so the next render picks up the new bundle; the
  data caches refresh themselves via the Notion webhook.
- Health ingest visibility: `/health/status` and `/health/attempts` are the
  probes. A silent phone-side Shortcut produces `key_ok` attempts with zero
  samples; the fix is phone-side, and `docs/first-run-readout.md` covers the
  read, not rerun-blind.
- Never rename Log DB property names; the worker reads them. Conventions
  change at the content level only.
- Secrets live in the owner's password manager and in Worker secret
  bindings. Echoes in logs/messages are redacted; persistent secrets go
  through the user's vault flow, never chat.
