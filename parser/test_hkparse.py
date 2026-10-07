import io, json, unittest
from hkparse import parse_stream, parse_dt, convert, sleep_night, short_type

def xml(body):
    return io.BytesIO(("<?xml version='1.0' encoding='UTF-8'?><HealthData locale='en_US'>"
                       + body + "</HealthData>").encode())

R = ('<Record type="{t}" sourceName="{s}" unit="{u}" startDate="{sd}" endDate="{ed}" value="{v}"/>')

class TestUnits(unittest.TestCase):
    def test_mass(self):
        self.assertAlmostEqual(convert(180.0, "lb", "kg")[0], 81.6466, places=3)
        self.assertAlmostEqual(convert(80.0, "kg", "kg")[0], 80.0)
    def test_distance(self):
        self.assertAlmostEqual(convert(3.0, "mi", "km")[0], 4.828032, places=5)
        self.assertAlmostEqual(convert(500.0, "m", "km")[0], 0.5)
    def test_energy_and_time(self):
        self.assertAlmostEqual(convert(1000.0, "kJ", "kcal")[0], 239.005736, places=4)
        self.assertAlmostEqual(convert(90.0, "sec", "min")[0], 1.5)
    def test_unknown_pair_kept(self):
        v, u = convert(5.0, "widgets", "kg")
        self.assertEqual((v, u), (5.0, "widgets"))

class TestDates(unittest.TestCase):
    def test_offset_local_day(self):
        dt, day = parse_dt("2026-07-18 23:30:00 -0700")
        self.assertEqual(day, "2026-07-18")          # local day, not the UTC day
        self.assertEqual(dt.utcoffset().total_seconds(), -7 * 3600)
    def test_early_morning_other_offset(self):
        _, day = parse_dt("2026-01-02 00:10:00 +0530")
        self.assertEqual(day, "2026-01-02")
    def test_sleep_night_rolls_forward(self):
        dt, _ = parse_dt("2026-07-18 23:10:00 -0700")
        self.assertEqual(sleep_night(dt), "2026-07-19")
        dt2, _ = parse_dt("2026-07-19 02:00:00 -0700")
        self.assertEqual(sleep_night(dt2), "2026-07-19")
    def test_short_type(self):
        self.assertEqual(short_type("HKQuantityTypeIdentifierBodyMass"), "BodyMass")
        self.assertEqual(short_type("HKCategoryTypeIdentifierSleepAnalysis"), "SleepAnalysis")

class TestRecords(unittest.TestCase):
    def test_exact_duplicates_dropped(self):
        body = R.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count",
                        sd="2026-07-18 09:00:00 -0700", ed="2026-07-18 09:10:00 -0700", v="500") * 3
        res = parse_stream(xml(body))
        self.assertEqual(res["duplicates_skipped"], 2)
        self.assertEqual(res["daily"]["StepCount"]["2026-07-18"]["value"], 500.0)

    def test_two_sources_do_not_double_count_steps(self):
        body = (R.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count",
                         sd="2026-07-18 09:00:00 -0700", ed="2026-07-18 09:10:00 -0700", v="500")
                + R.format(t="HKQuantityTypeIdentifierStepCount", s="Apple Watch", u="count",
                           sd="2026-07-18 09:00:01 -0700", ed="2026-07-18 09:10:01 -0700", v="620"))
        res = parse_stream(xml(body))
        row = res["daily"]["StepCount"]["2026-07-18"]
        self.assertEqual(row["value"], 620.0)              # richest single source wins
        self.assertEqual(row["sum_all_sources"], 1120.0)   # naive sum kept for inspection
        self.assertEqual(sorted(row["sources"]), ["Apple Watch", "iPhone"])

    def test_mixed_units_normalized(self):
        body = (R.format(t="HKQuantityTypeIdentifierBodyMass", s="ScaleApp", u="lb",
                         sd="2026-07-18 07:00:00 -0700", ed="2026-07-18 07:00:00 -0700", v="180")
                + R.format(t="HKQuantityTypeIdentifierBodyMass", s="ScaleApp", u="kg",
                           sd="2026-07-19 07:00:00 -0700", ed="2026-07-19 07:00:00 -0700", v="81.6466"))
        res = parse_stream(xml(body))
        d = res["daily"]["BodyMass"]
        self.assertAlmostEqual(d["2026-07-18"]["value"], d["2026-07-19"]["value"], places=3)
        self.assertEqual(d["2026-07-18"]["unit"], "kg")

    def test_percent_fraction_and_whole_both_land_as_percent(self):
        body = (R.format(t="HKQuantityTypeIdentifierBodyFatPercentage", s="ScaleApp", u="%",
                         sd="2026-07-18 07:00:00 -0700", ed="2026-07-18 07:00:00 -0700", v="0.182")
                + R.format(t="HKQuantityTypeIdentifierBodyFatPercentage", s="ScaleApp", u="%",
                           sd="2026-07-19 07:00:00 -0700", ed="2026-07-19 07:00:00 -0700", v="18.4"))
        res = parse_stream(xml(body))
        d = res["daily"]["BodyFatPercentage"]
        self.assertAlmostEqual(d["2026-07-18"]["value"], 18.2, places=6)
        self.assertAlmostEqual(d["2026-07-19"]["value"], 18.4, places=6)

    def test_discrete_daily_stats(self):
        body = "".join(R.format(t="HKQuantityTypeIdentifierHeartRate", s="Watch", u="count/min",
                                sd=f"2026-07-18 09:0{i}:00 -0700", ed=f"2026-07-18 09:0{i}:00 -0700",
                                v=str(60 + i * 5)) for i in range(4))
        res = parse_stream(xml(body))
        row = res["daily"]["HeartRate"]["2026-07-18"]
        self.assertEqual((row["min"], row["max"], row["count"]), (60.0, 75.0, 4))
        self.assertAlmostEqual(row["avg"], 67.5)
        self.assertEqual(row["last"], 75.0)

    def test_day_boundary_uses_record_offset(self):
        body = (R.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count",
                         sd="2026-07-18 23:50:00 -0700", ed="2026-07-18 23:55:00 -0700", v="100")
                + R.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count",
                           sd="2026-07-19 00:05:00 -0700", ed="2026-07-19 00:10:00 -0700", v="200"))
        res = parse_stream(xml(body))
        self.assertEqual(res["daily"]["StepCount"]["2026-07-18"]["value"], 100.0)
        self.assertEqual(res["daily"]["StepCount"]["2026-07-19"]["value"], 200.0)

    def test_travel_offset_change_keeps_local_days(self):
        body = (R.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count",
                         sd="2026-03-01 22:00:00 -0800", ed="2026-03-01 22:30:00 -0800", v="300")
                + R.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count",
                           sd="2026-03-02 09:00:00 +0530", ed="2026-03-02 09:30:00 +0530", v="400"))
        res = parse_stream(xml(body))
        self.assertEqual(sorted(res["daily"]["StepCount"]), ["2026-03-01", "2026-03-02"])

class TestSleep(unittest.TestCase):
    def test_stages_bucket_to_wake_day(self):
        seg = lambda v, sd, ed: ('<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" '
                                 f'startDate="{sd}" endDate="{ed}" value="{v}"/>')
        body = (seg("HKCategoryValueSleepAnalysisInBed", "2026-07-18 22:30:00 -0700", "2026-07-19 06:30:00 -0700")
                + seg("HKCategoryValueSleepAnalysisAsleepCore", "2026-07-18 23:00:00 -0700", "2026-07-19 02:00:00 -0700")
                + seg("HKCategoryValueSleepAnalysisAsleepDeep", "2026-07-19 02:00:00 -0700", "2026-07-19 03:00:00 -0700")
                + seg("HKCategoryValueSleepAnalysisAsleepREM", "2026-07-19 03:00:00 -0700", "2026-07-19 04:30:00 -0700")
                + seg("HKCategoryValueSleepAnalysisAwake", "2026-07-19 04:30:00 -0700", "2026-07-19 04:45:00 -0700"))
        res = parse_stream(xml(body))
        n = res["sleep"]["2026-07-19"]
        self.assertAlmostEqual(n["core"], 180.0)
        self.assertAlmostEqual(n["deep"], 60.0)
        self.assertAlmostEqual(n["rem"], 90.0)
        self.assertAlmostEqual(n["awake"], 15.0)
        self.assertAlmostEqual(n["in_bed"], 480.0)
        self.assertEqual(len(res["sleep"]), 1)

    def test_duplicate_sleep_segments_dropped(self):
        seg = ('<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" '
               'startDate="2026-07-18 23:00:00 -0700" endDate="2026-07-19 02:00:00 -0700" '
               'value="HKCategoryValueSleepAnalysisAsleepCore"/>')
        res = parse_stream(xml(seg * 2))
        self.assertAlmostEqual(res["sleep"]["2026-07-19"]["core"], 180.0)
        self.assertEqual(res["duplicates_skipped"], 1)

class TestWorkouts(unittest.TestCase):
    def test_modern_workout_statistics(self):
        body = ('<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="32.5" '
                'durationUnit="min" sourceName="Watch" startDate="2026-07-18 07:00:00 -0700" '
                'endDate="2026-07-18 07:32:30 -0700">'
                '<MetadataEntry key="HKIndoorWorkout" value="0"/>'
                '<WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="3.1" unit="mi"/>'
                '<WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" sum="1200" unit="kJ"/>'
                '<WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" average="152" maximum="176" unit="count/min"/>'
                '</Workout>')
        w = parse_stream(xml(body))["workouts"][0]
        self.assertEqual(w["type"], "Running")
        self.assertEqual(w["day"], "2026-07-18")
        self.assertAlmostEqual(w["duration_min"], 32.5)
        self.assertAlmostEqual(w["distance_km"], 4.988, places=2)
        self.assertAlmostEqual(w["energy_kcal"], 286.8, places=1)
        self.assertEqual(w["avg_hr"], 152.0)
        self.assertEqual(w["max_hr"], 176.0)

    def test_legacy_workout_attributes(self):
        body = ('<Workout workoutActivityType="HKWorkoutActivityTypeWalking" duration="45" '
                'durationUnit="min" totalDistance="2" totalDistanceUnit="mi" '
                'totalEnergyBurned="150" totalEnergyBurnedUnit="kcal" sourceName="iPhone" '
                'startDate="2026-05-02 18:00:00 -0700" endDate="2026-05-02 18:45:00 -0700"/>')
        w = parse_stream(xml(body))["workouts"][0]
        self.assertAlmostEqual(w["distance_km"], 3.2187, places=3)
        self.assertAlmostEqual(w["energy_kcal"], 150.0)

    def test_duplicate_workouts_dropped(self):
        one = ('<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30" durationUnit="min" '
               'sourceName="Watch" startDate="2026-07-18 07:00:00 -0700" endDate="2026-07-18 07:30:00 -0700"/>')
        res = parse_stream(xml(one * 2))
        self.assertEqual(len(res["workouts"]), 1)

class TestCatalog(unittest.TestCase):
    def test_catalog_enumerates_long_tail(self):
        body = (R.format(t="HKQuantityTypeIdentifierEnvironmentalAudioExposure", s="Watch", u="dBASPL",
                         sd="2026-07-18 09:00:00 -0700", ed="2026-07-18 09:10:00 -0700", v="72")
                + R.format(t="HKQuantityTypeIdentifierSomeFutureThing", s="NewApp", u="widgets",
                           sd="2026-07-18 09:00:00 -0700", ed="2026-07-18 09:10:00 -0700", v="3"))
        res = parse_stream(xml(body))
        self.assertIn("SomeFutureThing", res["catalog"])           # unknown types still surface
        self.assertEqual(res["daily"]["SomeFutureThing"]["2026-07-18"]["unit"], "widgets")
        self.assertEqual(res["catalog"]["EnvironmentalAudioExposure"]["sources"], ["Watch"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
