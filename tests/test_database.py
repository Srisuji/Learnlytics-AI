import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db  # noqa: E402
import data_service as ds  # noqa: E402


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_creates_all_tables_and_persists(self):
        db.init_db(self.path)
        conn = sqlite3.connect(self.path)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        for table in ("students", "subject_grades", "weekly_performance", "early_warnings",
                      "ai_recommendations", "faculty_interventions", "app_meta"):
            self.assertIn(table, names)
        self.assertTrue(os.path.exists(self.path))

    def test_seed_has_30_plus_synthetic_students_across_departments(self):
        result = db.init_db(self.path)
        df = ds.list_students_df(self.path)
        self.assertGreaterEqual(result["seeded"], 30)
        self.assertEqual(len(df), result["seeded"])
        self.assertTrue((df["is_synthetic"] == 1).all())
        self.assertGreaterEqual(df["department"].nunique(), 4)

    def test_seed_is_idempotent_across_restarts(self):
        db.init_db(self.path)
        first = len(ds.list_students_df(self.path))
        again = db.init_db(self.path)
        self.assertEqual(again["seeded"], 0)
        self.assertEqual(len(ds.list_students_df(self.path)), first)

    def test_restart_preserves_user_data_and_does_not_reseed_after_delete(self):
        db.init_db(self.path)
        ok, _ = ds.add_student({"student_id": "REAL1", "name": "Real One", "department": "CS",
                                "semester": 3, "attendance_rate": 80}, self.path)
        self.assertTrue(ok)
        for sid in list(ds.list_students_df(self.path)["student_id"]):
            if sid != "REAL1":
                ds.delete_student(sid, self.path)
        db.init_db(self.path)  # simulated app restart
        self.assertEqual(list(ds.list_students_df(self.path)["student_id"]), ["REAL1"])

    def test_user_data_first_means_no_demo_seed(self):
        db.init_db(self.path, seed=False)
        ds.add_student({"student_id": "A1", "name": "A", "department": "CS", "semester": 1}, self.path)
        result = db.init_db(self.path)
        self.assertEqual(result["seeded"], 0)
        self.assertEqual(len(ds.list_students_df(self.path)), 1)

    def test_reset_demo_only_removes_synthetic_students(self):
        db.init_db(self.path)
        ds.add_student({"student_id": "REAL1", "name": "Real", "department": "CS", "semester": 3}, self.path)
        ds.delete_student("DEMO001", self.path)
        inserted = db.reset_demo_data(self.path)
        df = ds.list_students_df(self.path)
        self.assertEqual(inserted, db.SEED_STUDENT_COUNT)
        self.assertIn("REAL1", set(df["student_id"]))
        self.assertIn("DEMO001", set(df["student_id"]))

    def test_meta_roundtrip(self):
        db.init_db(self.path)
        db.set_meta("k", "v1", self.path)
        db.set_meta("k", "v2", self.path)
        self.assertEqual(db.get_meta("k", None, self.path), "v2")
        self.assertEqual(db.get_meta("missing", "dflt", self.path), "dflt")

    def test_foreign_keys_enforced_and_cascade(self):
        db.init_db(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaction(self.path) as conn:
                conn.execute("INSERT INTO subject_grades (student_id, subject, marks) VALUES ('NOPE','X',50)")
        ds.delete_student("DEMO002", self.path)
        with db.transaction(self.path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM subject_grades WHERE student_id='DEMO002'").fetchone()[0]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
