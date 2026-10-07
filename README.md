# Notion macro and workout tracker

A personal tracker operated through conversational food and workout reports.
Notion holds the records; a Cloudflare Worker renders the macros and workout
charts. An optional Apple Health dashboard stores imported measurements in D1.

![The macros chart](docs/assets/hero.png)

![Tap a day, switch the window, flip to the average](docs/assets/demo.gif)

| Day blow-up | Workout progress |
|---|---|
| ![Item breakdown](docs/assets/blow-up.png) | ![Push / Pull / Legs over time](docs/assets/workout.png) |

## The workflow

1. Describe food, portions, or a workout in a message, or provide a label photo.
2. The assistant checks product-label records and published nutrition sources,
   scales the stated portions, and writes one Notion row per ingredient or item.
3. The chart refreshes from those records. Tap a day for its item breakdown,
   search logged items, change the time window, or compare averages.
4. Workout text such as `165x6, 175x6` becomes plotted sets without replacing
   the original record.

The person still supplies portions, resolves unclear products or dates,
corrects estimates, and decides which behavior and design changes to keep.
Nutrition estimates remain estimates. This repository is the chart, data model,
import code, and operating documentation, not a bundled messaging assistant.

## Current implementation

- Eight nutrition measures, goal lines, item breakdowns, logged-item search,
  3-day / 7-day / all-time windows, averages, and multiple chart views.
- Push / Pull / Legs charts, workout entry, set parsing, and progress views.
- Password-gated pages and a separate rotatable Notion-embed capability.
- Apple Health import endpoints, D1 schema, export parser, and Health dashboard.
  The legacy Shortcut generator is retained, but automatic phone sync is not
  presented as a completed feature. There is no Fitbit integration.
- Feature-preservation checks, parser tests, production deployment, and live
  smoke checks.

`main` includes the implementation served by production. CI tests `main`;
production deployment remains on `deploy/prod`. This catch-up changes the
repository, not the behavior of the running app.

Run your own: [setup](docs/setup.md). Food-row conventions:
[FORMATTING.md](FORMATTING.md). Project details: [technical reference](docs/technical.md),
[data model](docs/data-model.md), [design notes](docs/design.md), and
[operation guide](docs/agent-ops.md).

The images are existing project demos, not a live feed. Deploy with your own
Notion databases and secrets. No personal health export or access credentials
are included.
