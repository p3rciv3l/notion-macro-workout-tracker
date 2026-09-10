#!/usr/bin/env bash
# Live smoke + feature-preservation gate: edge propagation can flap for tens
# of seconds after upload, so poll with a cache-buster (~2 min cap). MARKERS
# ASSERT USER-FACING FEATURES, not just liveness: if the Average view, the
# time-range selector, or workout blow-up rows/hatching ever disappear from
# the built HTML or the app bundle, this script fails and the run goes red.
set -euo pipefail
: "${SMOKE_K:?missing embed capability token}"
: "${SMOKE_BASE:?missing worker base URL}"
BASE="$SMOKE_BASE"
CB="cb=$(date +%s)"

PAGE_MARKERS=(
  '<title>cbum chart</title>'  # page title - rename for your deployment
  '/app.js'
  'data-avg="1"'        # Average view modifier button (Macros seg)
  'data-w="3"'          # 3 day selector
  'data-w="7"'          # 7 day selector
  'data-w="0"'          # All time selector
  'data-s="Push"'       # workout split tabs
  'data-s="Legs"'
)
APP_MARKERS=(
  'dataset.avg'         # Average modifier click handling (page markers above pin the data-avg attr)
  'Nothing logged yet.' # blow-up empty state (was a ReferenceError 8/17)
  "disp: '-' + wob + ' kcal'"  # "Workout -N kcal" burn row label (Owner 8/26; was "-N est")
  'bseg-wo'             # hatched workout burn segment in the blow-up panel bar (Owner 8/26: blow-up view restored)
  'drawBlowStack(eng, di, i, segs)'  # blow-up in-chart stack drawn via its own decoupled renderer, workout band included (Owner 8/26)
  'splitSlug'           # split tabs keep ?k= and other params on real links
  'custNum.blur()'      # custom-days Enter dismisses the keyboard (Owner 8/26)
  "v - wkBurnFor(date)"  # Calories tooltip shows net (gross minus workout burn) (Owner 8/26)
  'eng.focusBar(f.di, f.i, f.segs)'  # blow-up stack re-applies after re-renders via the generic onRender hook (Owner 8/26: no shading on the green bar)
  'eng.fills.estimate'  # workout band hatched in the in-chart blow-up stack (Owner 8/26: "the green block thing at the top remains")
)

missing=""
html=""
for i in $(seq 1 12); do
  html=$(curl -fsS "$BASE/?k=${SMOKE_K}&$CB&_=1" 2>/dev/null || true)
  missing=""
  for m in "${PAGE_MARKERS[@]}"; do grep -qF "$m" <<<"$html" || missing="$missing page:'$m'"; done
  if [ -n "$html" ] && [ -z "$missing" ]; then echo "page markers present (attempt $i)"; break; fi
  echo "attempt $i: missing$missing - retrying in 10s"; sleep 10
done
[ -z "$missing" ] || { echo "smoke FAILED: page markers missing after 12 attempts:$missing"; exit 1; }

appjs=""
for i in $(seq 1 6); do
  appjs=$(curl -fsS "$BASE/app.js?k=${SMOKE_K}&$CB" 2>/dev/null || true)
  missing=""
  for m in "${APP_MARKERS[@]}"; do grep -qF "$m" <<<"$appjs" || missing="$missing app:'$m'"; done
  if [ -n "$appjs" ] && [ -z "$missing" ]; then echo "app.js markers present (attempt $i)"; break; fi
  echo "attempt $i: missing$missing - retrying in 10s"; sleep 10
done
[ -z "$missing" ] || { echo "smoke FAILED: app.js feature markers missing:$missing"; exit 1; }

curl -fsS "$BASE/health?k=${SMOKE_K}&$CB" -o /tmp/smoke_health.html
grep -q '<title>health</title>' /tmp/smoke_health.html \
  || { echo "smoke FAILED: /health page markers missing"; exit 1; }
echo "health page markers present"

ct=$(curl -fsS -o /tmp/smoke_v.txt -w '%{content_type}' "$BASE/v?k=${SMOKE_K}&$CB" || echo FAIL)
echo "/v: content-type=$ct body=$(head -c 120 /tmp/smoke_v.txt)"
[ "$ct" != FAIL ] && grep -q 'text/plain' <<<"$ct" || { echo "smoke FAILED: /v not text/plain"; exit 1; }

curl -fsS "$BASE/workout.json?k=${SMOKE_K}&$CB" -o /tmp/smoke_wk.json
python3 - <<'PY'
import json, sys
d = json.load(open('/tmp/smoke_wk.json'))
splits = d.get('splits') or {}
assert all(k in splits for k in ('Push', 'Pull', 'Legs')), 'workout splits missing'
assert any(splits[k] for k in splits), 'workout session lists all empty'
print('workout.json: splits OK, most recent dates:', {k: max((e.get('date','') for e in v), default='-') for k, v in splits.items()})
PY

echo "smoke OK"
