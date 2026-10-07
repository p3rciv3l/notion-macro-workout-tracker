# Design

## One worker, no build step

The entire app is a single ES module (`worker/worker.js`) that serves HTML
with the app JS inline. Deploy is a multipart PUT of that file; there is no
bundler, no npm install on the chart side, and the CI deploy script
fetch-merges the existing worker settings so a push can't silently drop a
KV/D1 binding. Small surface, fast ship, easy to audit: 490KB you can read.

## Render-time calculation, thin server state

Notion is the system of record for food and workouts; D1 is the system of
record for health samples. The chart math - day aggregation, goal targets,
the projected average at today's empty slot - happens at render/epoll time
in the browser-embedded app JS with no persistence behind it, so a bad
assumption never stamps itself onto data. KV holds only caches and small
config; Notion's webhook just refreshes those caches in the background and
pollers check the version key.

## Deterministic where it counts

Logs are numbers you defend tomorrow morning, so the paths that write and
transform them are deterministic: the workout cell parser is closed-form
(same cell -> same top set, forever; unparseable cells become gaps, never
zeros); food rows carry their basis in the row itself, and the per-product
bases live in the registry in FORMATTING.md rather than model memory. The
features an ML model might offer in the chart path are deliberately the
boring pieces: labeling, layout, buying beats betting.

## Agents in the loop, under contract

Agents own two lanes and stay out of a third. Logging: an agent writes rows
to the Log DB under the explicit contract in FORMATTING.md (names, bases,
evidence, container math, honesty about estimates). Ops: an agent deploys
through the CI pipeline and verifies green Test -> Deploy -> Smoke. The
chart path itself stays deterministic code. The guard rails assume agents
make mistakes: the feature guard and smoke fail red when a user-facing
piece disappears, and the rules file carries an agent-conduct section
(including "a cart screenshot is not a receipt" - verified post-checkout
data beats anything upstream of it).

## Capability rotation as the sharing answer

There is no account system; sharing boundaries are capability tokens. The
device gate is a password-derived cookie, the Notion embeds carry a
rotatable `?k=` token because third-party storage is blocked in Notion's
webview, and rotation is a KV overwrite plus a version bump - no redeploy,
and every existing link dies at once. Deliberate consequence: one worker =
one tenant. A friend gets their own instance (docs/setup.md), not a view of
yours, unless you hand them the link with open eyes.
