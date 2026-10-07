"""
Streaming parser for Apple Health export.xml (inside export.zip).

Design notes:
 - Never loads the document into memory: xml.etree.ElementTree.iterparse with
   aggressive element clearing. Reads the zip member as a stream.
 - Emits daily aggregates keyed on the LOCAL calendar day carried by the
   record's own UTC offset (Apple writes "2026-07-18 07:14:22 -0700").
 - Deduplicates records written by multiple sources.
 - Normalizes units to one canonical unit per metric.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------- units

# canonical unit per dimension
MASS_KG = {"kg": 1.0, "lb": 0.45359237, "lbs": 0.45359237, "st": 6.35029318, "g": 0.001}
DIST_KM = {"km": 1.0, "mi": 1.609344, "m": 0.001, "ft": 0.0003048, "yd": 0.0009144}
ENERGY_KCAL = {"kcal": 1.0, "Cal": 1.0, "cal": 0.001, "kJ": 0.239005736, "J": 0.000239005736}
TIME_MIN = {"min": 1.0, "sec": 1.0 / 60, "s": 1.0 / 60, "hr": 60.0, "h": 60.0, "ms": 1.0 / 60000}

UNIT_TABLES = [MASS_KG, DIST_KM, ENERGY_KCAL, TIME_MIN]

# metric type -> (canonical unit, aggregation kind)
#   kind "sum"  : cumulative within the day (steps, distance, energy, minutes)
#   kind "disc" : discrete samples (weight, heart rate, VO2 max)
CUMULATIVE = {
    "StepCount": ("count", "sum"),
    "DistanceWalkingRunning": ("km", "sum"),
    "DistanceCycling": ("km", "sum"),
    "DistanceSwimming": ("km", "sum"),
    "DistanceWheelchair": ("km", "sum"),
    "DistanceDownhillSnowSports": ("km", "sum"),
    "FlightsClimbed": ("count", "sum"),
    "ActiveEnergyBurned": ("kcal", "sum"),
    "BasalEnergyBurned": ("kcal", "sum"),
    "AppleExerciseTime": ("min", "sum"),
    "AppleStandTime": ("min", "sum"),
    "AppleMoveTime": ("min", "sum"),
    "SwimmingStrokeCount": ("count", "sum"),
    "PushCount": ("count", "sum"),
    "DietaryEnergyConsumed": ("kcal", "sum"),
    "DietaryProtein": ("g", "sum"),
    "DietaryCarbohydrates": ("g", "sum"),
    "DietaryFatTotal": ("g", "sum"),
    "DietarySodium": ("mg", "sum"),
    "DietaryWater": ("L", "sum"),
    "TimeInDaylight": ("min", "sum"),
    "MindfulSession": ("min", "sum"),
}

DISCRETE_UNITS = {
    "BodyMass": "kg",
    "LeanBodyMass": "kg",
    "BodyFatPercentage": "%",
    "BodyMassIndex": "count",
    "Height": "m",
    "WaistCircumference": "cm",
    "HeartRate": "count/min",
    "RestingHeartRate": "count/min",
    "WalkingHeartRateAverage": "count/min",
    "HeartRateVariabilitySDNN": "ms",
    "VO2Max": "mL/min·kg",
    "OxygenSaturation": "%",
    "RespiratoryRate": "count/min",
    "BodyTemperature": "degC",
    "AppleSleepingWristTemperature": "degC",
    "BloodPressureSystolic": "mmHg",
    "BloodPressureDiastolic": "mmHg",
    "WalkingSpeed": "km/hr",
    "WalkingStepLength": "cm",
    "WalkingAsymmetryPercentage": "%",
    "WalkingDoubleSupportPercentage": "%",
    "StairAscentSpeed": "m/s",
    "StairDescentSpeed": "m/s",
    "SixMinuteWalkTestDistance": "m",
    "EnvironmentalAudioExposure": "dBASPL",
    "HeadphoneAudioExposure": "dBASPL",
    "PhysicalEffort": "kcal/hr·kg",
    "AppleWalkingSteadiness": "%",
    "BloodGlucose": "mg/dL",
}

PERCENT_METRICS = {m for m, u in DISCRETE_UNITS.items() if u == "%"}

TYPE_RE = re.compile(r"^HK(?:Quantity|Category)TypeIdentifier(.+)$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})$")

SLEEP_STAGES = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAwake": "awake",
}


def short_type(t: str) -> str:
    m = TYPE_RE.match(t or "")
    return m.group(1) if m else (t or "")


def parse_dt(s: str):
    """Apple writes '2026-07-18 07:14:22 -0700'. Returns (aware datetime, local_date_str)."""
    if not s:
        return None, None
    m = DATE_RE.match(s.strip())
    if not m:
        try:
            dt = datetime.fromisoformat(s.strip())
        except ValueError:
            return None, None
        return dt, dt.date().isoformat()
    y, mo, d, hh, mm, ss, off = m.groups()
    sign = 1 if off[0] == "+" else -1
    tzmin = sign * (int(off[1:3]) * 60 + int(off[3:5]))
    from datetime import timezone
    dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss),
                  tzinfo=timezone(timedelta(minutes=tzmin)))
    return dt, f"{y}-{mo}-{d}"


def convert(value: float, unit: str, canonical: str):
    """Convert value to canonical unit. Returns (value, unit_used)."""
    if unit == canonical or not unit or not canonical:
        return value, canonical or unit
    for table in UNIT_TABLES:
        if unit in table and canonical in table:
            return value * table[unit] / table[canonical], canonical
    # count/min vs count/min variants, mg vs g, etc.
    if unit == "g" and canonical == "mg":
        return value * 1000.0, canonical
    if unit == "mg" and canonical == "g":
        return value / 1000.0, canonical
    if unit == "cm" and canonical == "m":
        return value / 100.0, canonical
    if unit == "m" and canonical == "cm":
        return value * 100.0, canonical
    if unit == "in" and canonical == "cm":
        return value * 2.54, canonical
    if unit == "degF" and canonical == "degC":
        return (value - 32.0) * 5.0 / 9.0, canonical
    return value, unit  # unknown pairing: keep as-is, report the unit we saw


class Agg:
    __slots__ = ("sum", "count", "min", "max", "last", "last_t", "unit", "sources")

    def __init__(self):
        self.sum = 0.0
        self.count = 0
        self.min = None
        self.max = None
        self.last = None
        self.last_t = None
        self.unit = None
        self.sources = defaultdict(float)

    def add(self, v, unit, t, source):
        self.sum += v
        self.count += 1
        self.min = v if self.min is None else min(self.min, v)
        self.max = v if self.max is None else max(self.max, v)
        if self.last_t is None or (t is not None and t > self.last_t):
            self.last, self.last_t = v, t
        self.unit = self.unit or unit
        self.sources[source] += v

    def as_row(self, kind):
        avg = self.sum / self.count if self.count else None
        row = {
            "unit": self.unit,
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "avg": avg,
            "last": self.last,
        }
        if kind == "sum":
            # Overlapping sources (iPhone + Watch both log steps) would double
            # count a plain sum, so the day's value is the single richest
            # source, matching how Health picks a priority source.
            best = max(self.sources.values()) if self.sources else 0.0
            row["value"] = best
            row["sum_all_sources"] = self.sum
            row["sources"] = dict(self.sources)
        else:
            row["value"] = avg
        return row


def sleep_night(dt) -> str:
    """A sleep segment belongs to the morning it ends on: anything starting at
    or after 18:00 local rolls into the next calendar day."""
    d = dt.date()
    if dt.hour >= 18:
        d = d + timedelta(days=1)
    return d.isoformat()


def parse_stream(fh, progress=None):
    """Parse an export.xml stream. Returns a dict of aggregates."""
    daily = defaultdict(lambda: defaultdict(Agg))       # metric -> day -> Agg
    kinds = {}                                          # metric -> "sum"|"disc"
    sleep = defaultdict(lambda: defaultdict(float))     # night -> stage -> minutes
    sleep_window = {}                                   # night -> [start, end]
    workouts = []
    seen = set()                                        # dedupe keys
    counts = defaultdict(int)
    sources = defaultdict(set)
    dupes = 0
    n = 0

    cur_workout = None
    for event, elem in ET.iterparse(fh, events=("start", "end")):
        if event == "start":
            if elem.tag == "Workout":
                cur_workout = {"stats": {}}
            continue

        tag = elem.tag
        if tag == "Record":
            n += 1
            if progress and n % 250000 == 0:
                progress(n)
            rtype = elem.get("type", "")
            short = short_type(rtype)
            src = elem.get("sourceName", "?")
            start_s = elem.get("startDate")
            end_s = elem.get("endDate") or start_s
            val_s = elem.get("value")
            unit = elem.get("unit") or ""
            counts[short] += 1
            sources[short].add(src)

            if short == "SleepAnalysis":
                stage = SLEEP_STAGES.get(val_s or "")
                sdt, _ = parse_dt(start_s)
                edt, _ = parse_dt(end_s)
                if stage and sdt and edt:
                    key = ("S", start_s, end_s, val_s)
                    if key in seen:
                        dupes += 1
                    else:
                        seen.add(key)
                        night = sleep_night(sdt)
                        mins = max(0.0, (edt - sdt).total_seconds() / 60.0)
                        sleep[night][stage] += mins
                        w = sleep_window.setdefault(night, [sdt, edt])
                        if stage != "in_bed":
                            if sdt < w[0]:
                                w[0] = sdt
                            if edt > w[1]:
                                w[1] = edt
                elem.clear()
                continue

            try:
                val = float(val_s)
            except (TypeError, ValueError):
                elem.clear()
                continue

            dt, day = parse_dt(start_s)
            if day is None:
                elem.clear()
                continue

            # exact-duplicate suppression across sources
            key = (short, start_s, end_s, val_s)
            if key in seen:
                dupes += 1
                elem.clear()
                continue
            seen.add(key)

            if short in CUMULATIVE:
                canon, kind = CUMULATIVE[short]
            else:
                canon, kind = DISCRETE_UNITS.get(short, unit), "disc"
            kinds[short] = kind
            val, used = convert(val, unit, canon)
            if short in PERCENT_METRICS and val is not None and 0 < val <= 1.0:
                val *= 100.0          # Apple writes some percentages as fractions
                used = "%"
            daily[short][day].add(val, used, dt, src)
            elem.clear()

        elif tag == "Workout":
            start_s = elem.get("startDate")
            end_s = elem.get("endDate")
            sdt, day = parse_dt(start_s)
            edt, _ = parse_dt(end_s)
            dur = elem.get("duration")
            dur_u = elem.get("durationUnit") or "min"
            try:
                dur_min = convert(float(dur), dur_u, "min")[0]
            except (TypeError, ValueError):
                dur_min = (edt - sdt).total_seconds() / 60.0 if (sdt and edt) else None
            wtype = (elem.get("workoutActivityType") or "").replace("HKWorkoutActivityType", "")
            stats = cur_workout["stats"] if cur_workout else {}
            # older exports carry totals as attributes
            def attr_num(a, u_attr, canon):
                v = elem.get(a)
                if v is None:
                    return None
                try:
                    return convert(float(v), elem.get(u_attr) or canon, canon)[0]
                except ValueError:
                    return None
            dist = stats.get("DistanceWalkingRunning") or stats.get("DistanceCycling") \
                or stats.get("DistanceSwimming") or attr_num("totalDistance", "totalDistanceUnit", "km")
            energy = stats.get("ActiveEnergyBurned") or attr_num("totalEnergyBurned", "totalEnergyBurnedUnit", "kcal")
            wkey = ("W", start_s, end_s, wtype)
            if wkey in seen:
                dupes += 1
            else:
                seen.add(wkey)
                workouts.append({
                    "type": wtype,
                    "day": day,
                    "start": start_s,
                    "end": end_s,
                    "duration_min": dur_min,
                    "distance_km": dist,
                    "energy_kcal": energy,
                    "avg_hr": stats.get("HeartRate"),
                    "max_hr": stats.get("HeartRateMax"),
                    "source": elem.get("sourceName", "?"),
                })
            cur_workout = None
            elem.clear()

        elif tag == "WorkoutStatistics" and cur_workout is not None:
            short = short_type(elem.get("type", ""))
            unit = elem.get("unit") or ""
            raw = elem.get("sum") or elem.get("average")
            try:
                v = float(raw)
            except (TypeError, ValueError):
                v = None
            if v is not None:
                canon = CUMULATIVE.get(short, (DISCRETE_UNITS.get(short, unit),))[0]
                cur_workout["stats"][short] = convert(v, unit, canon)[0]
                if short == "HeartRate" and elem.get("maximum"):
                    try:
                        cur_workout["stats"]["HeartRateMax"] = float(elem.get("maximum"))
                    except ValueError:
                        pass
            elem.clear()

        elif tag in ("MetadataEntry", "HeartRateVariabilityMetadataList",
                     "InstantaneousBeatsPerMinute", "WorkoutEvent", "WorkoutRoute",
                     "Location", "FileReference", "ClinicalRecord", "Correlation"):
            elem.clear()

    return {
        "daily": {m: {d: a.as_row(kinds.get(m, "disc")) for d, a in days.items()}
                  for m, days in daily.items()},
        "kinds": kinds,
        "sleep": {night: dict(stages) for night, stages in sleep.items()},
        "sleep_window": {n_: [w[0].isoformat(), w[1].isoformat()] for n_, w in sleep_window.items()},
        "workouts": workouts,
        "catalog": {m: {"records": c, "sources": sorted(sources[m])} for m, c in counts.items()},
        "record_count": n,
        "duplicates_skipped": dupes,
    }


def open_export(path):
    if path.endswith(".zip"):
        zf = zipfile.ZipFile(path)
        name = next((n for n in zf.namelist()
                     if n.endswith("export.xml") and "cda" not in n.lower()), None)
        if name is None:
            raise SystemExit("no export.xml inside the zip")
        return zf.open(name)
    return open(path, "rb")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: hkparse.py <export.zip|export.xml> [out.json]")
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/health/parsed.json"
    with open_export(src) as fh:
        res = parse_stream(fh, progress=lambda n: print(f"  {n:,} records", file=sys.stderr))
    with open(out, "w") as f:
        json.dump(res, f)
    print(f"records={res['record_count']:,} dupes={res['duplicates_skipped']:,} "
          f"metrics={len(res['daily'])} workouts={len(res['workouts'])} -> {out}")


if __name__ == "__main__":
    main()
