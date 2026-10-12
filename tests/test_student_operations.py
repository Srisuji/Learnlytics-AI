import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_service as ds  # noqa: E402
import database as db  # noqa: E402
import recommendations as rec  # noqa: E402

GOOD = {"student_id": "S1", "name": "Test One", "department": "CS", "semester": 3,
        "attendance_rate": 80, "academic_score": 70, "assignment_rate": 90}


class StudentOperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.db")
        db.init_db(self.path, seed=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, **over):
        return ds.add_student({**GOOD, **over}, self.path)

    # ---- CRUD -----------------------------------------------------------
    def test_create_read_update_delete(self):
        self.assertEqual(self.add(), (True, []))
        self.assertEqual(ds.get_student("S1", self.path)["name"], "Test One")
        ok, errs = ds.update_student("S1", {**GOOD, "name": "Renamed", "academic_score": ""}, self.path)
        self.assertTrue(ok, errs)
        s = ds.get_student("S1", self.path)
        self.assertEqual(s["name"], "Renamed")
        self.assertIsNone(s["academic_score"])
        self.assertTrue(ds.delete_student("S1", self.path))
        self.assertIsNone(ds.get_student("S1", self.path))
        self.assertFalse(ds.delete_student("S1", self.path))

    def test_duplicate_id_is_prevented(self):
        self.add()
        ok, errs = self.add(name="Other")
        self.assertFalse(ok)
        self.assertIn("already exists", errs[0])
        self.assertEqual(ds.get_student("S1", self.path)["name"], "Test One")

    def test_validation_rules(self):
        cases = [({"student_id": ""}, "student_id"), ({"name": " "}, "name"), ({"department": ""}, "department"),
                 ({"semester": 0}, "semester"), ({"semester": 2.5}, "semester"), ({"semester": "x"}, "semester"),
                 ({"attendance_rate": 101}, "attendance_rate"), ({"academic_score": -1}, "academic_score"),
                 ({"assignment_rate": "abc"}, "assignment_rate"), ({"email": "nope"}, "email"),
                 ({"student_id": "has space"}, "student_id")]
        for over, word in cases:
            ok, errs = self.add(**over)
            self.assertFalse(ok, over)
            self.assertTrue(any(word in e for e in errs), (over, errs))
        self.assertEqual(len(ds.list_students_df(self.path)), 0)

    def test_blank_metric_is_stored_as_missing_and_percent_sign_is_accepted(self):
        self.assertTrue(self.add(attendance_rate="", academic_score="72%")[0])
        s = ds.get_student("S1", self.path)
        self.assertIsNone(s["attendance_rate"])
        self.assertEqual(s["academic_score"], 72.0)

    def test_update_unknown_student(self):
        ok, errs = ds.update_student("NOPE", GOOD, self.path)
        self.assertFalse(ok)

    # ---- screening, filters, KPIs ----------------------------------------
    def seed_cohort(self):
        self.add(student_id="A", name="Alice", department="CS", attendance_rate=90, academic_score=80, assignment_rate=95)
        self.add(student_id="B", name="Bob", department="CS", attendance_rate=60, academic_score=40, assignment_rate=50)
        self.add(student_id="C", name="Cara", department="EC", semester=5, attendance_rate=80, academic_score=60, assignment_rate="")
        self.add(student_id="D", name="Dan", department="EC", semester=5, attendance_rate="", academic_score="", assignment_rate="")

    def test_kpis_come_from_data_and_ignore_missing(self):
        self.seed_cohort()
        df = ds.get_screened_df(self.path)
        k = ds.compute_kpis(df)
        self.assertEqual(k["total_students"], 4)
        self.assertAlmostEqual(k["avg_score"], (80 + 40 + 60) / 3)
        self.assertAlmostEqual(k["avg_attendance"], (90 + 60 + 80) / 3)
        self.assertAlmostEqual(k["avg_assignment"], (95 + 50) / 2)
        self.assertEqual(k["risk_counts"]["Critical"], 1)
        self.assertEqual(k["risk_counts"]["Insufficient data"], 1)
        self.assertEqual(k["needs_follow_up"], 1)

    def test_review_status_changes_follow_up_count(self):
        self.seed_cohort()
        self.assertTrue(ds.set_review_status("B", "Support plan in place", self.path))
        k = ds.compute_kpis(ds.get_screened_df(self.path))
        self.assertEqual(k["needs_follow_up"], 0)
        self.assertFalse(ds.set_review_status("B", "Bogus", self.path))

    def test_department_semester_risk_and_search_filters(self):
        self.seed_cohort()
        df = ds.get_screened_df(self.path)
        self.assertEqual(set(ds.filter_df(df, departments=["CS"])["student_id"]), {"A", "B"})
        self.assertEqual(set(ds.filter_df(df, semesters=[5])["student_id"]), {"C", "D"})
        self.assertEqual(list(ds.filter_df(df, categories=["Critical"])["student_id"]), ["B"])
        self.assertEqual(list(ds.filter_df(df, search="ali")["student_id"]), ["A"])
        self.assertEqual(len(ds.filter_df(df, departments=["EC"], categories=["Low"])), 1)

    def test_changing_config_changes_flags(self):
        self.seed_cohort()
        ok, errs = ds.save_config({"attendance_threshold": 50, "score_threshold": 30,
                                   "assignment_threshold": 40}, self.path)
        self.assertTrue(ok, errs)
        df = ds.get_screened_df(self.path)
        self.assertEqual(df.set_index("student_id").loc["B", "risk_category"], "Low")
        ds.reset_config(self.path)
        self.assertEqual(ds.get_config(self.path)["attendance_threshold"], 75.0)

    def test_invalid_config_is_rejected(self):
        ok, errs = ds.save_config({"attendance_threshold": 500}, self.path)
        self.assertFalse(ok)
        self.assertTrue(errs)

    def test_department_summary(self):
        self.seed_cohort()
        summary = ds.department_summary_df(ds.get_screened_df(self.path)).set_index("Department")
        self.assertEqual(summary.loc["CS", "Students"], 2)
        self.assertEqual(summary.loc["CS", "High/Critical flags"], 1)

    def test_empty_database_does_not_break_summaries(self):
        df = ds.get_screened_df(self.path)
        self.assertTrue(df.empty)
        k = ds.compute_kpis(df)
        self.assertEqual(k["total_students"], 0)
        self.assertIsNone(k["avg_score"])
        self.assertTrue(ds.department_summary_df(df).empty)
        self.assertIn("Students in this report: 0", ds.executive_summary_text(df))

    # ---- interventions ----------------------------------------------------
    def test_intervention_logging_and_validation(self):
        self.add()
        today = dt.date.today()
        ok, errs = ds.add_intervention("S1", today, "Low attendance", "Spoke with student",
                                       today + dt.timedelta(days=7), "Agreed a plan", self.path)
        self.assertTrue(ok, errs)
        df = ds.list_interventions_df("S1", db_path=self.path)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["follow_up_date"], (today + dt.timedelta(days=7)).isoformat())
        bad = [("NOPE", today, "c", "a", None), ("S1", "not-a-date", "c", "a", None),
               ("S1", today, "", "a", None), ("S1", today, "c", " ", None),
               ("S1", today, "c", "a", today - dt.timedelta(days=1))]
        for args in bad:
            self.assertFalse(ds.add_intervention(*args, db_path=self.path)[0], args)
        self.assertEqual(len(ds.list_interventions_df(db_path=self.path)), 1)

    def test_follow_up_queue_due_labels_and_resolved_exclusion(self):
        self.add()
        today = dt.date.today()
        for delta in (-3, 0, 5):
            ds.add_intervention("S1", today - dt.timedelta(days=10), "c", "a",
                                today + dt.timedelta(days=delta), db_path=self.path)
        q = ds.follow_up_queue(self.path)
        self.assertEqual(sorted(q["due"]), ["Due today", "Overdue", "Upcoming"])
        ds.set_review_status("S1", "Resolved", self.path)
        self.assertTrue(ds.follow_up_queue(self.path).empty)

    # ---- recommendations --------------------------------------------------
    def test_recommendations_reflect_indicators_and_track_progress(self):
        self.add(attendance_rate=60, academic_score=40, assignment_rate=95)
        recs, screening = ds.get_recommendations_for_student("S1", self.path)
        keys = [r["key"] for r in recs]
        self.assertEqual(keys[0], "check_in")
        self.assertIn("low_score", keys)
        self.assertIn("low_attendance", keys)
        self.assertNotIn("low_assignment", keys)
        for r in recs:
            for field in ("action", "reason", "timeframe", "goal", "status"):
                self.assertTrue(r[field])
        self.assertTrue(ds.track_recommendation("S1", recs[0], db_path=self.path))
        self.assertTrue(ds.track_recommendation("S1", recs[0], "In progress", self.path))
        self.assertTrue(ds.track_recommendation("S1", recs[0], db_path=self.path))  # keeps status
        recs2, _ = ds.get_recommendations_for_student("S1", self.path)
        self.assertEqual(recs2[0]["status"], "In progress")
        self.assertEqual(len(ds.list_tracked_recommendations("S1", self.path)), 1)
        self.assertFalse(ds.track_recommendation("S1", recs[0], "Nonsense", self.path))

    def test_recommendation_variants(self):
        self.add(student_id="OK", attendance_rate=95, academic_score=90, assignment_rate=95)
        self.add(student_id="NONE", attendance_rate="", academic_score="", assignment_rate="")
        ok_recs, _ = ds.get_recommendations_for_student("OK", self.path)
        self.assertEqual([r["key"] for r in ok_recs], ["maintain"])
        none_recs, _ = ds.get_recommendations_for_student("NONE", self.path)
        self.assertEqual([r["key"] for r in none_recs], ["missing_data"])

    def test_llm_wording_falls_back_when_not_configured(self):
        os.environ.pop("EDUPULSE_USE_LLM", None)
        recs = [{"key": "x", "action": "Original text"}]
        self.assertEqual(rec.enhance_wording(recs), recs)
        self.assertFalse(rec.llm_enabled())

    # ---- exports ----------------------------------------------------------
    def test_exports_reflect_filters_and_omit_email(self):
        self.seed_cohort()
        df = ds.get_screened_df(self.path)
        cs = ds.filter_df(df, departments=["CS"])
        roster = ds.roster_csv(cs)
        self.assertIn("Alice", roster)
        self.assertNotIn("Cara", roster)
        self.assertNotIn("email", roster.splitlines()[0])
        risk_csv = ds.risk_report_csv(df)
        self.assertEqual(risk_csv.splitlines()[1].split(",")[0], "B")  # highest score first
        self.assertIn("below", risk_csv)
        dept_csv = ds.department_summary_csv(cs)
        self.assertIn("CS", dept_csv)
        self.assertNotIn("EC", dept_csv)
        self.assertIn("Department", ds.department_summary_csv(df))
        self.assertTrue(ds.intervention_summary_csv(db_path=self.path).startswith("intervention_id"))
        text = ds.executive_summary_text(df, ds.list_interventions_df(db_path=self.path))
        self.assertIn("Students in this report: 4", text)
        self.assertIn("not a prediction", text)

    def test_data_quality_summary_and_backup(self):
        self.seed_cohort()
        q = ds.data_quality_summary(self.path).set_index("Check")
        self.assertEqual(q.loc["Total students", "Count"], 4)
        self.assertEqual(q.loc["Missing attendance rate", "Count"], 1)
        data = ds.export_backup_bytes(self.path)
        self.assertTrue(data.startswith(b"SQLite format 3"))


if __name__ == "__main__":
    unittest.main()
