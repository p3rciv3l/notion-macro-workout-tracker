#!/usr/bin/env node
/* Feature-preservation guard: fails CI if a user-facing feature disappears
 * from the worker bundle. Each check names the feature it protects so a red
 * run says exactly what was lost. Run: node tests/feature-guard.mjs */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const src = readFileSync(new URL('../worker/worker.js', import.meta.url), 'utf8');
const appJsMatch = src.match(/const APP_JS = `([\s\S]*?)`;\nfunction appVer/);
const appJs = appJsMatch ? appJsMatch[1] : '';
const pageTpl = src.slice(src.indexOf('function chartPage'), src.indexOf('const HAPP_JS'));

let failures = 0;
const check = (feature, ok, detail = '') => {
  if (ok) console.log(`  ok   ${feature}`);
  else { failures++; console.log(`  FAIL ${feature}${detail ? ': ' + detail : ''}`); }
};

console.log('== static feature markers ==');
check('No Fitbit/Google Health bridge anywhere (Owner 9/10: "there\'s no fitbit ever" - weight arrives only via Wyze/Apple Health ingest or manual text-ins; bridge code, OAuth routes, and the cron handler must stay gone)', !/ghealth|fitbit/i.test(src), 'Fitbit/Google Health bridge reference reappeared in worker source');

check('Average modifier button (Macros seg)', /data-avg="1">Average</.test(pageTpl), 'data-avg="1">Average button missing from page template');
check('Logged-item search controls (Owner 9/9: a bare magnifier icon, no box; click or fine-pointer hover unfolds the input INTO the legend row - legend items reflow around it, header never gains a row; no duplicate range picker)', /class="sicn" id="msrchbtn"/.test(pageTpl) && /<svg[^>]*viewBox="0 0 24 24"[^>]*>.*<circle cx="10\.5"/.test(pageTpl) && !/msrchrow/.test(pageTpl) && !/msrchseg/.test(pageTpl) && /sq\.id = 'msrchq'/.test(appJs) && /window\.__msrchq/.test(appJs) && /legEl\.appendChild\(sq\)/.test(appJs) && /legend input#msrchq/.test(src), 'bare search icon missing, a search row/picker is back, or the input is not inside the legend row');
check('Logged-item search results container (minimalist row view, days left / item right)', /id="msrchres"/.test(pageTpl) && /class="sr"><span class="days"/.test(appJs), 'results container or day-left row markup missing');
check('Logged-item search logic: typed text is the regex (literal fallback), matches full title + short name; open state = click-pinned, fine-pointer hover, field focus, or a non-empty query; results follow the head selected range currentW (app.js)', /function srchMatcher/.test(appJs) && /new RegExp\(q, 'i'\)/.test(appJs) && /function srchRender/.test(appJs) && /function srchIsOpen/.test(appJs) && /hover:hover.*pointer:fine/.test(appJs) && /dd\.setDate\(dd\.getDate\(\) - \(currentW - 1\)\)/.test(appJs) && !/msrchseg/.test(appJs) && /No logged items match\./.test(appJs), 'search matcher/renderer/open-state/head-range logic missing from app.js');
check('3 day selector', /data-w="3">3 day</.test(pageTpl));
check('7 day selector', /data-w="7">7 day</.test(pageTpl));
check('Workout x-domain trims edge sessions with no visible lift (Owner 9/9: no dead gap when an edge day holds only a hidden exercise; middle calendar-true spacing stays)', /visAt/.test(appJs) && /slice\(lo, hi \+ 1\)/.test(appJs), 'edge-trim missing from workout render');
check('All-range selectors (Owner 9/9: both cards use the short "All" so the range buttons hold one line)', /<button data-w="0">All<\/button><button data-avg="1">Average</.test(pageTpl) && /data-w="0">All<\/button><button data-w="custom">Custom</.test(pageTpl) && !/data-w="0">All time</.test(pageTpl));
check('Average modifier handler (app.js)', /dataset.avg/.test(appJs), 'avg modifier click handling missing from app.js');
check('Average numbers pane', /avgrow|avgpane|avgAlign/.test(src), 'average numbers pane markup/alignment missing');
check('Workout estimated burn row in Calories blow-up (Owner 8/26: "-N kcal" label)', /disp: '-' \+ wob \+ ' kcal'/.test(appJs), '"Workout -N kcal" row missing');
check('Workout hatched segment in Calories blow-up bar (Owner 8/26: blow-up view restored)', /s\.wo \? '<div class="bseg-wo"/.test(appJs), 'hatched workout segment missing from the blow-up panel bar');
check('Workout burn included in blow-up in-chart stack + tooltip (Owner 8/26: blow-up view exactly pre-change)', /drawBlowStack\(eng, di, i, segs\)/.test(appJs) && !/segs\.filter\(s => !s\.wo\)/.test(appJs), 'workout band missing from the blow-up in-chart stack/tooltip');
check('Blow-up stack decoupled: re-applies via the generic onRender hook, not by name inside renderSVG (Owner 8/26: "break the dependencies")', /eng\.onRender\(function \(\) \{ const f = eng\.focusState\(\); if \(f && f\.segs\) eng\.focusBar\(f\.di, f\.i, f\.segs\)/.test(appJs) && /for \(const h of \(eng\.renderHooks \|\| \[\]\)\) h\(\);/.test(appJs) && !/const f = eng\.focus; focusBar/.test(appJs), 'blow-up stack is still re-applied by name inside renderSVG');
check('Workout band in the in-chart blow-up stack is hatched like the panel (Owner 8/26: "the green block thing at the top remains")', /s\.wo \? Object\.assign\(\{\}, s, \{ fill: eng\.fills\.estimate \}\)/.test(appJs) && /fills: \{ estimate: 'url\(#' \+ uid \+ 'esth\)' \}/.test(appJs) && /rect\.setAttribute\('fill', s\.fill \|\| s\.color\)/.test(appJs) && /id="' \+ uid \+ 'esth"/.test(appJs), 'workout band is still a flat green block in the graph stack');
check('Calories tooltip shows NET (gross minus workout burn) (Owner 8/26)', /vNet = \(!proj && dsm\.key === 'calories' && date\) \? v - wkBurnFor\(date\)/.test(appJs), 'net-calories tooltip adjustment missing');
check('Custom-days Enter blurs the field (Owner 8/26)', /e\.key === 'Enter'\) \{ applyCustom\(\); custNum\.blur\(\);/.test(appJs), 'Enter-to-blur on the custom-days input missing');
check('Workout split tabs are real links', /<a data-s="Push">Push<\/a><a data-s="Pull">Pull<\/a><a data-s="Legs">Legs<\/a>/.test(src));
check('Tab links keep embedded params client-side', /splitSlug/.test(appJs) && /metaKey \|\| ev\.ctrlKey/.test(appJs));
check('Blow-up empty state defined', /Nothing logged yet\./.test(appJs), 'empty_msg reference without definition');
check('Mixed-freshness guard in page build', /freshItems/.test(src), 'buildChartPage items-refetch guard missing');
check('Blow-up renderer present', /function blowPanel|blowPanel\s*=/.test(appJs + src));
check('Clear-view mask geometry', /eng\.smB = eng\.smB \|\| \[\]/.test(src) && /mask="url\(/.test(src), 'smB collect/masked emit pass missing - Clear bands will stack colors');
check('Clear avg band clips to next band top', /bandTops\[q\] !== null/.test(src), 'f2c2dd2 next-band-top clip missing');
check('Workout entry pane (record sheet)', /wkedit/.test(src));
check('/health page + app bundle', /const HAPP_JS = `/.test(src) && /<title>health<\/title>/.test(src));
check('Health ingest route', /\/health\/ingest/.test(src));
check('workout.json endpoint', /workout\.json/.test(src));
check('data.json streams items live', /ITEMS/.test(appJs) && /items/.test(src));
check('Workout-only day synthesis (Owner 8/25)', /negative net calories/.test(src) && /minFoodDay/.test(src), 'freshRows no longer synthesizes zero rows for workout-only days');
check('One-off per-date workout burn overrides (owner-texted actuals: 2026-08-27 = 350 kcal, 2026-09-02 = 600 kcal; NOT a recalibration of the split rule)', /BURN_OVERRIDES = \{ "2026-08-27": 350, "2026-09-02": 600 \}/.test(src) && /if \(o != null\) return o/.test(src), 'per-date burn override missing');
check('Workout burn split rule Legs 250 / else 200', /has\('Legs'\) \? 250 : \(has\('Push'\) \|\| has\('Pull'\)\) \? 200 : 0/.test(src), 'wkBurnFor no longer returns Legs 250 / Push-Pull 200');

console.log('== functional render test ==');
const tmp = mkdtempSync(join(tmpdir(), 'cbum-'));
const modPath = join(tmp, 'worker.mjs');
writeFileSync(modPath, src + '\nexport { chartPage };\n');
const mod = await import(pathToFileURL(modPath).href);
if (typeof mod.chartPage !== 'function') { failures++; console.log('  FAIL chartPage export'); }
else {
  const today = '2026-08-20';
  const rows = [{ date: today, calories: 500, protein: 40, carbs: 50, fat: 20, sugar: 10, sodium: 100, fiber: 5 }];
  const items = { [today]: [{ title: 'guard test meal', cal: 500, p: 40, c: 50, f: 20 }] };
  const wk = { splits: { Legs: [{ date: today, title: '', ex: { 'Ballerina Squat': [[135, 6]] }, w: { 'Ballerina Squat': 135 }, raw: {} }] }, errors: {} };
  const html = mod.chartPage(rows, { source: 'guard' }, wk, '', true, null, null, items);
  check('render: Average button in built HTML', html.includes('data-avg="1"'));
  check('render: search UI in built HTML', html.includes('id="msrchbtn"') && !html.includes('msrchrow') && html.includes('id="msrchres"') && !html.includes('msrchseg'));
  check('render: time selector in built HTML', ['data-w="3"', 'data-w="7"', 'data-w="0"'].every(m => html.includes(m)));
  check('render: item rows embedded for blow-ups', html.includes('guard test meal'), 'items payload not baked into page');
  check('render: workout session embedded', html.includes('Ballerina Squat'), 'workout session payload not baked into page');
  check('render: split tabs markup', html.includes('data-s="Push"') && html.includes('data-s="Legs"'));
  check('render: /app.js script tag', html.includes('/app.js'));
  check('render: app bundle tag', html.includes('/app.js'));
}

console.log(failures ? `\n${failures} feature check(s) FAILED` : '\nall feature checks passed');
process.exit(failures ? 1 : 0);
