import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_service as ds  # noqa: E402
import database as db  # noqa: E402

HEADER = "student_id,name,department,semester,attendance_rate,academic_score,assignment_rate\n"


def csv(*rows, header=HEADER):
    return (header + "\n".join(rows) + "\n").encode("utf-8")


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.db")
        db.init_db(self.path, seed=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_import_inserts_rows(self):
        r = ds.import_students_csv(csv("A1,Ann,CS,3,80,70,90", "A2,Ben,EC,4,60,40,55"), db_path=self.path)
        self.assertIsNone(r["error"])
        self.assertEqual((r["inserted"], r["updated"]), (2, 0))
        self.assertTrue(r["rejected_df"].empty)
        self.assertEqual(len(ds.list_students_df(self.path)), 2)

    def test_dry_run_writes_nothing(self):
        r = ds.import_students_csv(csv("A1,Ann,CS,3,80,70,90"), db_path=self.path, dry_run=True)
        self.assertEqual(len(r["accepted_df"]), 1)
        self.assertEqual(len(ds.list_students_df(self.path)), 0)

    def test_missing_required_columns(self):
        r = ds.import_students_csv(b"student_id,name\nA1,Ann\n", db_path=self.path)
        self.assertIn("Missing required column", r["error"])
        self.assertIn("department", r["error"])

    def test_headers_are_case_and_space_insensitive(self):
        header = "Student ID,Name,Department,Semester,Attendance Rate,Academic Score,Assignment Rate\n"
        r = ds.import_students_csv(csv("A1,Ann,CS,3,80,70,90", header=header), db_path=self.path)
        self.assertEqual(r["inserted"], 1)

    def test_bad_rows_are_rejected_with_reasons_and_good_rows_still_imported(self):
        data = csv("A1,Ann,CS,3,80,70,90",
                   "A2,Ben,EC,4,150,40,55",        # range
                   "A3,Cy,EC,x,60,40,55",          # semester not number
                   "A4,Di,EC,4,abc,40,55",         # not a number
                   ",NoId,EC,4,60,40,55",          # missing id
                   "A6,,EC,4,60,40,55")            # missing name
        r = ds.import_students_csv(data, db_path=self.path)
        self.assertEqual(r["inserted"], 1)
        self.assertEqual(len(r["rejected_df"]), 5)
        reasons = " ".join(r["rejected_df"]["reason"])
        for word in ("between 0 and 100", "semester", "not a number", "student_id is required", "name is required"):
            self.assertIn(word, reasons)
        self.assertEqual(list(r["rejected_df"]["row"]), [3, 4, 5, 6, 7])  # header = line 1

    def test_duplicate_ids_inside_file_are_rejected(self):
        r = ds.import_students_csv(csv("A1,Ann,CS,3,80,70,90", "A1,Again,CS,3,80,70,90"), db_path=self.path)
        self.assertEqual(r["inserted"], 1)
        self.assertIn("duplicate", r["rejected_df"].iloc[0]["reason"])
        self.assertEqual(ds.get_student("A1", self.path)["name"], "Ann")

    def test_existing_records_are_not_silently_overwritten(self):
        ds.add_student({"student_id": "A1", "name": "Original", "department": "CS", "semester": 3}, self.path)
        r = ds.import_students_csv(csv("A1,Changed,CS,3,80,70,90", "A2,New,CS,3,80,70,90"), db_path=self.path)
        self.assertEqual((r["inserted"], r["updated"]), (1, 0))
        self.assertIn("already exists", r["rejected_df"].iloc[0]["reason"])
        self.assertEqual(ds.get_student("A1", self.path)["name"], "Original")

    def test_update_mode_overwrites_only_present_columns(self):
        ds.add_student({"student_id": "A1", "name": "Original", "department": "CS", "semester": 3,
                        "email": "keep@example.edu"}, self.path)
        r = ds.import_students_csv(csv("A1,Changed,CS,3,80,70,90"), mode="update_existing", db_path=self.path)
        self.assertEqual(r["updated"], 1)
        s = ds.get_student("A1", self.path)
        self.assertEqual((s["name"], s["attendance_rate"]), ("Changed", 80.0))
        self.assertEqual(s["email"], "keep@example.edu")  # column absent from CSV is untouched

    def test_updating_a_demo_student_protects_it_from_demo_reset(self):
        db.init_db(self.path)  # seeds DEMO001...
        self.assertEqual(ds.get_student("DEMO001", self.path)["is_synthetic"], 1)
        data = csv("DEMO001,My Real Student,CS,3,80,70,90")
        r = ds.import_students_csv(data, mode="update_existing", db_path=self.path)
        self.assertEqual(r["updated"], 1)
        self.assertEqual(ds.get_student("DEMO001", self.path)["is_synthetic"], 0)
        db.reset_demo_data(self.path)
        self.assertEqual(ds.get_student("DEMO001", self.path)["name"], "My Real Student")

    def test_blank_metrics_import_as_unavailable_with_note(self):
        r = ds.import_students_csv(csv("A1,Ann,CS,3,,70,"), db_path=self.path)
        self.assertEqual(r["inserted"], 1)
        self.assertIn("unavailable", r["accepted_df"].iloc[0]["notes"])
        s = ds.get_student("A1", self.path)
        self.assertIsNone(s["attendance_rate"])
        self.assertIsNone(s["assignment_rate"])

    def test_bad_files(self):
        self.assertIn("empty", ds.import_students_csv(b"", db_path=self.path)["error"])
        self.assertIn("UTF-8", ds.import_students_csv(b"\xff\xfe\x00bad", db_path=self.path)["error"])
        self.assertIn("no rows", ds.import_students_csv(HEADER.encode(), db_path=self.path)["error"])

    def test_sample_csv_template_is_importable_and_export_roundtrips(self):
        r = ds.import_students_csv(ds.sample_csv_text().encode(), db_path=self.path)
        self.assertIsNone(r["error"])
        self.assertEqual(r["inserted"], 4)
        self.assertTrue(r["rejected_df"].empty)
        exported = ds.roster_csv(ds.get_screened_df(self.path)).encode()
        self.assertTrue(exported.startswith(b"student_id,name,department,semester"))
        self.assertEqual(len(exported.splitlines()), 5)

    def test_utf8_bom_is_accepted(self):
        data = b"\xef\xbb\xbf" + csv("A1,Ann,CS,3,80,70,90")
        self.assertEqual(ds.import_students_csv(data, db_path=self.path)["inserted"], 1)


if __name__ == "__main__":
    unittest.main()
