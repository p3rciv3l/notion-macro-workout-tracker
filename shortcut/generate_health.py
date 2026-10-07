import re, os, sys
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shortcut_lib.py')).read())

if not ENDPOINT:
    sys.exit('Set HEALTH_INGEST_ENDPOINT to your worker ingest URL first (see worker/wrangler.toml.example comments).')

# (picker label, canonical metric, confidence, include in catch-up)
TYPES = [
 ("Steps","StepCount","proven",True),
 ("Weight","BodyMass","proven",True),
 ("Heart Rate","HeartRate","proven",True),
 ("Walking + Running Distance","DistanceWalkingRunning","reference",True),
 ("Exercise Minutes","AppleExerciseTime","reference",True),
 ("Active Calories","ActiveEnergyBurned","reference",True),
 ("Sleep","SleepAnalysis","reference",True),
 ("Body Fat Percentage","BodyFatPercentage","health-app",True),
 ("Lean Body Mass","LeanBodyMass","health-app",True),
 ("Body Mass Index","BodyMassIndex","health-app",True),
 ("Flights Climbed","FlightsClimbed","health-app",True),
 ("Resting Heart Rate","RestingHeartRate","health-app",True),
 ("Heart Rate Variability","HeartRateVariabilitySDNN","health-app",True),
 ("Walking Heart Rate Average","WalkingHeartRateAverage","health-app",True),
 ("Blood Oxygen","OxygenSaturation","health-app",True),
 ("Respiratory Rate","RespiratoryRate","health-app",True),
 ("Resting Energy","BasalEnergyBurned","health-app",True),
 ("Stand Minutes","AppleStandTime","health-app",True),
 ("Cycling Distance","DistanceCycling","health-app",True),
 ("Cardio Fitness","VO2Max","health-app",True),
 ("Cardio Recovery","HeartRateRecoveryOneMinute","health-app",True),
 ("Wrist Temperature","AppleSleepingWristTemperature","health-app",True),
 ("Time In Daylight","TimeInDaylight","health-app",False),
 ("Physical Effort","PhysicalEffort","health-app",False),
 ("Walking Speed","WalkingSpeed","health-app",False),
 ("Walking Step Length","WalkingStepLength","health-app",False),
 ("Walking Asymmetry","WalkingAsymmetryPercentage","health-app",False),
 ("Double Support Time","WalkingDoubleSupportPercentage","health-app",False),
 ("Walking Steadiness","AppleWalkingSteadiness","health-app",False),
 ("Stair Speed: Up","StairAscentSpeed","health-app",False),
 ("Stair Speed: Down","StairDescentSpeed","health-app",False),
 ("Running Power","RunningPower","health-app",False),
 ("Running Speed","RunningSpeed","health-app",False),
 ("Running Stride Length","RunningStrideLength","health-app",False),
 ("Vertical Oscillation","RunningVerticalOscillation","health-app",False),
 ("Ground Contact Time","RunningGroundContactTime","health-app",False),
 ("Breathing Disturbances","AppleSleepingBreathingDisturbances","health-app",False),
]
RANK = {"proven": 0, "reference": 1, "health-app": 2}
TYPES.sort(key=lambda t: RANK[t[2]])

# The key is pasted into ONE Text action at the top and referenced as a variable
# by every request. iOS Shortcuts has no credential store, and the file-read
# approach was pulled from this build because those actions are unproven on their
# iOS - see README.
def key_preamble(acts):
    acts.append(comment(
        "SETUP, ONCE: tap the Text action directly below and replace\n"
        "PASTE_INGEST_KEY_HERE with the ingest key. That is the only edit\n"
        "this shortcut needs. Every request below reads it from the variable."))
    t = u()
    acts.append(text_action([KEY_PLACEHOLDER], t, "key_text"))
    acts.append(set_var(out_ref(t, "key_text"), "ingest_key"))
    return var_ref("ingest_key")


def sample_block(acts, label, metric, varname, tag, backfill=False, limit=None):
    f = u()
    acts.append(find_health(label, f, tag + "_s", backfill=backfill, limit=limit))
    grp, r0, r1 = u(), u(), u()
    acts.append({"WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
                 "WFWorkflowActionParameters": {"UUID": r0, "GroupingIdentifier": grp,
                    "WFControlFlowMode": 0, "WFInput": attach(out_ref(f, tag + "_s"))}})
    gv, gd, ge, gu, gs, tx = u(), u(), u(), u(), u(), u()
    acts.append(get_details("Value", var_ref("Repeat Item"), gv, tag + "_val"))
    acts.append(get_details("Start Date", var_ref("Repeat Item"), gd, tag + "_st"))
    acts.append(get_details("End Date", var_ref("Repeat Item"), ge, tag + "_en"))
    acts.append(get_details("Unit", var_ref("Repeat Item"), gu, tag + "_un"))
    acts.append(get_details("Source", var_ref("Repeat Item"), gs, tag + "_src"))
    acts.append(text_action(['{"metric":"', metric, '","ts":"', out_ref(gd, tag + "_st"),
        '","end":"', out_ref(ge, tag + "_en"), '","value":"', out_ref(gv, tag + "_val"),
        '","unit":"', out_ref(gu, tag + "_un"), '","source":"', out_ref(gs, tag + "_src"),
        '"}'], tx, tag + "_line"))
    acts.append(append_var(out_ref(tx, tag + "_line"), varname))
    acts.append({"WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
                 "WFWorkflowActionParameters": {"UUID": r1, "GroupingIdentifier": grp,
                    "WFControlFlowMode": 2}})

def flush(acts, key, varname, tag):
    cb, uid = u(), u()
    acts.append(combine(var_ref(varname), cb, varname + "_body"))
    acts.append(post_file(out_ref(cb, varname + "_body"), key, uid, tag + "_response"))

def save(acts, path):
    plist = {"WFWorkflowActions": acts, "WFWorkflowClientVersion": "2605.0.5",
             "WFWorkflowMinimumClientVersion": 900, "WFWorkflowMinimumClientVersionString": "900",
             "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4251333119,
                                "WFWorkflowIconGlyphNumber": 59511},
             "WFWorkflowImportQuestions": [], "WFWorkflowTypes": ["NCWidget"],
             "WFWorkflowInputContentItemClasses": ["WFStringContentItem", "WFURLContentItem"]}
    plistlib.dump(plist, open(path, "wb"), fmt=plistlib.FMT_XML)
    import collections
    a = plistlib.load(open(path, "rb"))["WFWorkflowActions"]
    uu = [x["WFWorkflowActionParameters"]["UUID"] for x in a]
    assert len(set(uu)) == len(uu)
    seen, bad = set(), []
    def walk(o):
        if isinstance(o, dict):
            if o.get("Type") == "ActionOutput" and o.get("OutputUUID") not in seen: bad.append(o.get("OutputName"))
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    for x in a:
        walk(x["WFWorkflowActionParameters"]); seen.add(x["WFWorkflowActionParameters"]["UUID"])
    assert not bad, bad[:3]
    g = collections.defaultdict(list)
    for x in a:
        p = x["WFWorkflowActionParameters"]
        if "GroupingIdentifier" in p: g[p["GroupingIdentifier"]].append(p.get("WFControlFlowMode"))
    assert all(v == [0, 2] for v in g.values())
    appended = set(x["WFWorkflowActionParameters"]["WFVariableName"] for x in a
                   if x["WFWorkflowActionIdentifier"].endswith("appendvariable"))
    for x in a:
        if x["WFWorkflowActionIdentifier"].endswith("text.combine"):
            v = x["WFWorkflowActionParameters"]["WFInput"]["Value"]
            if v.get("Type") == "Variable": assert v["VariableName"] in appended
    posts = sum(1 for x in a if x["WFWorkflowActionIdentifier"].endswith("downloadurl"))
    return len(a), posts, os.path.getsize(path)

outdir = sys.argv[1] if len(sys.argv) > 1 else "/downloads"

confirmed = [t for t in TYPES if t[2] != "health-app"]
unconfirmed = [t for t in TYPES if t[2] == "health-app"]
back = [t for t in TYPES if t[3]]


def build_today(acts, key):
    """Everything recorded today."""
    for label, metric, _, _ in confirmed:
        sample_block(acts, label, metric, "sure_lines", metric.lower() + "_t")
    # Sleep starts before midnight, so also take windows that END today.
    sample_block(acts, "Sleep", "SleepAnalysis", "sure_lines", "sleep_end", limit=200)
    acts[-10]["WFWorkflowActionParameters"]["WFContentItemFilter"]["Value"][
        "WFActionParameterFilterTemplates"][1]["Property"] = "End Date"
    # Confirmed names post BEFORE any unconfirmed name is touched: if one of
    # those stops the run, today's core data has already landed.
    flush(acts, key, "sure_lines", "confirmed")
    for label, metric, _, _ in unconfirmed:
        sample_block(acts, label, metric, "rest_lines", metric.lower() + "_t")
    flush(acts, key, "rest_lines", "rest")



def build_catchup(acts, key):
    """Recent history for the types that keep producing data, capped per type."""
    for label, metric, _, _ in back:
        sample_block(acts, label, metric, "back_lines", metric.lower() + "_b",
                     backfill=True, limit=BACKFILL_LIMIT)
    flush(acts, key, "back_lines", "catchup")


# The single file Owner installs. Today first, catch-up after, so a stall late in
# the run can only cost history that the next run re-sends anyway.
acts = []
key = key_preamble(acts)
build_today(acts, key)
build_catchup(acts, key)
one_stats = save(acts, outdir + "/CBUM Health.shortcut")

# Fallback pair, kept generated in case the single file is too large to import.
acts = []
key = key_preamble(acts)
build_today(acts, key)
today_stats = save(acts, outdir + "/CBUM Health Today.shortcut")

acts = []
key = key_preamble(acts)
build_catchup(acts, key)
catch_stats = save(acts, outdir + "/CBUM Health Catchup.shortcut")

print("Single : %d actions, %d posts, %d B" % one_stats)
print("Today  : %d actions, %d posts, %d B" % today_stats)
print("Catchup: %d actions, %d posts, %d B (%d types)" % (catch_stats + (len(back),)))
print("confirmed-first order:", [t[0] for t in confirmed])
