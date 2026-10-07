"""Builds the final Apple Health -> Worker shortcut.

Design goals, in order:
  1. Owner installs this file once. Every future change is a Worker change.
  2. The key is never in the file. It is read at run time from a text file in
     iCloud Drive, so the shortcut carries no credential.
  3. A picker label the app does not recognise HALTS the run with Apple's
     "No Samples Found" alert. Confirmed labels therefore run first and post
     before any uncertain label is touched.
  4. Metrics are posted in chunks, so a failure late in the run cannot cost the
     data already gathered, and the Worker's replies say exactly how far it got.
"""
import plistlib, uuid, json, sys

import os
# Your worker's ingest endpoint, set when running generate_health.py:
#   export HEALTH_INGEST_ENDPOINT="https://YOUR-WORKER.YOUR-SUB.workers.dev/health/ingest"
ENDPOINT = os.environ.get("HEALTH_INGEST_ENDPOINT", "")
KEY_PLACEHOLDER = "PASTE_INGEST_KEY_HERE"
OBJ = "\ufffc"
CHUNK = 20
BACKFILL_LIMIT = 150

def u(): return str(uuid.uuid4()).upper()
def out_ref(uid, name): return {"OutputUUID": uid, "OutputName": name, "Type": "ActionOutput"}
def var_ref(name): return {"Type": "Variable", "VariableName": name}
def attach(ref): return {"Value": ref, "WFSerializationType": "WFTextTokenAttachment"}

def token_string(parts):
    s, atts = "", {}
    for p in parts:
        if isinstance(p, str):
            s += p
        else:
            atts["{%d, 1}" % len(s)] = p
            s += OBJ
    v = {"string": s}
    if atts: v["attachmentsByRange"] = atts
    return {"Value": v, "WFSerializationType": "WFTextTokenString"}

def dict_items(pairs):
    return [{"WFItemType": 0, "WFKey": token_string([k]),
             "WFValue": token_string(v if isinstance(v, list) else [v])} for k, v in pairs]

def comment(text):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.comment",
            "WFWorkflowActionParameters": {"UUID": u(), "WFCommentActionText": text}}

def text_action(parts, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFTextActionText": token_string(parts)}}

BACKFILL_FROM = __import__("datetime").datetime(2020, 1, 1)

def find_health(label, uid, name, date_prop="Start Date", limit=None, backfill=False):
    tmpl = [{"Bounded": True, "Operator": 4, "Property": "Type", "Removable": False,
             "Values": {"Enumeration": {"Value": label,
                        "WFSerializationType": "WFStringSubstitutableState"}}}]
    bounded = False
    if backfill:
        # Operator 1003 is the documented bounded-range row: a literal lower
        # bound and Current Date as the upper. Worst case, if iOS drops the row,
        # the query becomes all history - which the result cap keeps survivable
        # and which is still real, correctly timestamped data.
        bounded = True
        tmpl.append({"Bounded": True, "Operator": 1003, "Property": date_prop,
                     "Removable": False,
                     "Values": {"Date": BACKFILL_FROM,
                                "AnotherDate": {"Value": {"Type": "CurrentDate"},
                                                "WFSerializationType": "WFTextTokenAttachment"}}})
    elif date_prop:
        # Operator 1002 renders as "is today" - proven on device. The Number and
        # Unit beside it are vestigial; Apple's own exports emit them.
        tmpl.append({"Bounded": True, "Operator": 1002, "Property": date_prop,
                     "Removable": False, "Values": {"Number": "7", "Unit": 16}})
    params = {"UUID": uid, "CustomOutputName": name,
              "WFContentItemFilter": {"Value": {
                  "WFActionParameterFilterPrefix": 1,
                  "WFContentPredicateBoundedDate": bounded,
                  "WFActionParameterFilterTemplates": tmpl},
                  "WFSerializationType": "WFContentPredicateTableTemplate"}}
    if limit:
        params["WFContentItemLimitEnabled"] = True
        params["WFContentItemLimitNumber"] = limit
        # A cap without a sort is a lottery: iOS would be free to hand back the
        # OLDEST 150 samples, forever, and the rows would look perfectly valid.
        # Sort newest-first explicitly so the cap trims history, not today.
        params["WFContentItemSortProperty"] = "Start Date"
        params["WFContentItemSortOrder"] = "Latest First"
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.filter.health.quantity",
            "WFWorkflowActionParameters": params}

def get_details(prop, input_ref, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.properties.health.quantity",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFContentItemPropertyName": prop, "WFInput": attach(input_ref)}}

# Input AND WFInput on every list-consuming action. With WFInput alone the editor
# renders a grey unbound placeholder and the action emits nothing - proven on device.
def stats(op, input_ref, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.statistics",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFStatisticsOperation": op,
                "WFInput": attach(input_ref), "Input": attach(input_ref)}}

def count_items(input_ref, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.count",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFCountType": "Items", "WFInput": attach(input_ref), "Input": attach(input_ref)}}

def first_item(input_ref, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFItemSpecifier": "First Item",
                "WFInput": attach(input_ref), "Input": attach(input_ref)}}

def combine(input_ref, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.text.combine",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFInput": attach(input_ref), "Input": attach(input_ref),
                "WFTextSeparator": "New Lines"}}

def set_var(input_ref, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.setvariable",
            "WFWorkflowActionParameters": {"UUID": u(), "WFVariableName": name,
                "WFInput": attach(input_ref)}}

def append_var(input_ref, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.appendvariable",
            "WFWorkflowActionParameters": {"UUID": u(), "WFVariableName": name,
                "WFInput": attach(input_ref)}}

def post_file(body_ref, key_ref, uid, name):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {"UUID": uid, "CustomOutputName": name,
                "WFURL": ENDPOINT, "WFHTTPMethod": "POST", "WFHTTPBodyType": "File",
                "WFRequestVariable": attach(body_ref),
                "WFFormValues": {"Value": {"WFDictionaryFieldValueItems": []},
                    "WFSerializationType": "WFDictionaryFieldValue"},
                "WFHTTPHeaders": {"Value": {"WFDictionaryFieldValueItems": dict_items(
                    [("X-Health-Key", [key_ref]), ("Content-Type", "application/x-ndjson")])},
                    "WFSerializationType": "WFDictionaryFieldValue"}}}

# ---------------------------------------------------------------- metric table

# How many past samples the catch-up file requests per type. Bounded so a long
# gap cannot produce a run that never finishes.
BACKFILL_LIMIT = 150
