"""Unit tests for Academic Analytics:
1. K1, K2, K3 Cognitive-Level Analysis (data availability, calculation, lowest level detection, advice)
2. Subject Performance Analysis (averages, highest/lowest, pass %, attention threshold, record counts)
3. Marks Distribution Analysis (binning, normalization, mean, median, min, max, std dev, pass/fail)
4. Missing marks and empty dataset edge cases
"""
import os
import tempfile
import unittest
import pandas as pd

import database as db
import data_service as ds


class TestAcademicAnalytics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        # Initialize clean test db
        db.init_db(self.db_path, seed=False)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_empty_dataset_handling(self):
        """Ensure analytics gracefully return has_data=False and empty DataFrames when DB is empty."""
        cog = ds.get_cognitive_analysis(db_path=self.db_path)
        self.assertFalse(cog["has_data"])
        self.assertEqual(cog["raw_records_count"], 0)
        self.assertIsNone(cog["lowest_level"])
        self.assertTrue(cog["summary_df"].empty)

        subj = ds.get_subject_performance_analysis(db_path=self.db_path)
        self.assertFalse(subj["has_data"])
        self.assertEqual(subj["raw_records_count"], 0)
        self.assertEqual(subj["needs_attention"], [])

        dist = ds.get_marks_distribution_analysis(db_path=self.db_path)
        self.assertFalse(dist["has_data"])
        self.assertEqual(dist["raw_records_count"], 0)

    def test_cognitive_levels_calculation_and_recommendation(self):
        """Create assessment with K1, K2, K3 questions and verify calculation accuracy."""
        # Add 2 test students
        ds.add_student({"student_id": "S101", "name": "Student A", "department": "Computer Science", "semester": 2}, db_path=self.db_path)
        ds.add_student({"student_id": "S102", "name": "Student B", "department": "Computer Science", "semester": 2}, db_path=self.db_path)

        # Create assessment
        asm_id = ds.create_assessment("Midterm Exam", "Data Structures", "2026-03-01", 50.0, db_path=self.db_path)
        
        # Add questions: K1 (10 marks), K2 (20 marks), K3 (30 marks)
        questions = [
            {"question_number": 1, "cognitive_level": "K1", "max_marks": 10.0, "topic": "Definitions"},
            {"question_number": 2, "cognitive_level": "K2", "max_marks": 20.0, "topic": "Explain Trees"},
            {"question_number": 3, "cognitive_level": "K3", "max_marks": 30.0, "topic": "Implement Graph"}
        ]
        ds.add_assessment_questions(asm_id, questions, db_path=self.db_path)
        
        fetched_q = ds.get_assessment_questions(asm_id, db_path=self.db_path)
        q_map = {q["question_number"]: q["id"] for q in fetched_q}

        # Student scores:
        # S101: Q1 (K1)=9/10 (90%), Q2 (K2)=14/20 (70%), Q3 (K3)=12/30 (40%)
        # S102: Q1 (K1)=8/10 (80%), Q2 (K2)=16/20 (80%), Q3 (K3)=15/30 (50%)
        # Overall K1: avg 8.5/10 = 85.0%
        # Overall K2: avg 15.0/20 = 75.0%
        # Overall K3: avg 13.5/30 = 45.0% -> Lowest should be K3
        scores = [
            {"question_id": q_map[1], "student_id": "S101", "marks_obtained": 9.0},
            {"question_id": q_map[2], "student_id": "S101", "marks_obtained": 14.0},
            {"question_id": q_map[3], "student_id": "S101", "marks_obtained": 12.0},
            {"question_id": q_map[1], "student_id": "S102", "marks_obtained": 8.0},
            {"question_id": q_map[2], "student_id": "S102", "marks_obtained": 16.0},
            {"question_id": q_map[3], "student_id": "S102", "marks_obtained": 15.0},
        ]
        ds.record_question_scores(scores, db_path=self.db_path)

        res = ds.get_cognitive_analysis(db_path=self.db_path)
        self.assertTrue(res["has_data"])
        self.assertEqual(res["raw_records_count"], 6)
        self.assertEqual(res["lowest_level"], "K3")
        self.assertEqual(res["lowest_level_name"], "Apply")
        self.assertIn("problem-solving application", res["suggestion"])

        summary = res["summary_df"]
        k1_row = summary[summary["Level"] == "K1"].iloc[0]
        k2_row = summary[summary["Level"] == "K2"].iloc[0]
        k3_row = summary[summary["Level"] == "K3"].iloc[0]

        self.assertAlmostEqual(k1_row["Performance %"], 85.0, places=1)
        self.assertAlmostEqual(k2_row["Performance %"], 75.0, places=1)
        self.assertAlmostEqual(k3_row["Performance %"], 45.0, places=1)

        # Test student-level filtering
        s1_res = ds.get_cognitive_analysis(student_id="S101", db_path=self.db_path)
        self.assertTrue(s1_res["has_data"])
        self.assertEqual(s1_res["raw_records_count"], 3)
        s1_k3 = s1_res["summary_df"][s1_res["summary_df"]["Level"] == "K3"].iloc[0]
        self.assertAlmostEqual(s1_k3["Performance %"], 40.0, places=1)

    def test_subject_performance_analysis(self):
        """Verify subject averages, highest/lowest marks, pass rates, and attention threshold."""
        ds.add_student({"student_id": "S201", "name": "A", "department": "CS", "semester": 2}, db_path=self.db_path)
        ds.add_student({"student_id": "S202", "name": "B", "department": "CS", "semester": 2}, db_path=self.db_path)
        ds.add_student({"student_id": "S203", "name": "C", "department": "CS", "semester": 2}, db_path=self.db_path)

        # Subject Grades:
        # Math: S201=80, S202=90, S203=40 -> Avg: 70.0, Max: 90, Min: 40, Passed (>=50): 2/3 (66.7%)
        # Physics: S201=45, S202=40, S203=35 -> Avg: 40.0, Max: 45, Min: 35, Passed (>=50): 0/3 (0.0%)
        with db.transaction(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO subject_grades (student_id, subject, marks) VALUES (?, ?, ?)",
                [
                    ("S201", "Mathematics", 80.0),
                    ("S202", "Mathematics", 90.0),
                    ("S203", "Mathematics", 40.0),
                    ("S201", "Physics", 45.0),
                    ("S202", "Physics", 40.0),
                    ("S203", "Physics", 35.0),
                ]
            )

        res = ds.get_subject_performance_analysis(pass_mark=50.0, db_path=self.db_path)
        self.assertTrue(res["has_data"])
        self.assertEqual(res["raw_records_count"], 6)
        self.assertEqual(res["needs_attention"], ["Physics"])

        summary = res["summary_df"]
        math_row = summary[summary["Subject"] == "Mathematics"].iloc[0]
        self.assertAlmostEqual(math_row["Average %"], 70.0, places=1)
        self.assertEqual(math_row["Highest Mark"], 90.0)
        self.assertEqual(math_row["Lowest Mark"], 40.0)
        self.assertAlmostEqual(math_row["Pass %"], 66.7, places=1)
        self.assertEqual(math_row["Records Assessed"], 3)

        phys_row = summary[summary["Subject"] == "Physics"].iloc[0]
        self.assertAlmostEqual(phys_row["Average %"], 40.0, places=1)
        self.assertAlmostEqual(phys_row["Pass %"], 0.0, places=1)

    def test_marks_distribution_statistics_and_binning(self):
        """Verify marks distribution binning, percentages, and statistical measures."""
        scores = [25.0, 45.0, 55.0, 65.0, 75.0, 85.0, 95.0, 72.0]
        # Insert students with academic scores
        for idx, s in enumerate(scores):
            ds.add_student({
                "student_id": f"S30{idx}",
                "name": f"Student {idx}",
                "department": "Mechanical",
                "semester": 4,
                "academic_score": s
            }, db_path=self.db_path)

        res = ds.get_marks_distribution_analysis(department="Mechanical", pass_mark=50.0, db_path=self.db_path)
        self.assertTrue(res["has_data"])
        stats = res["stats"]
        self.assertEqual(stats["count"], 8)
        self.assertEqual(stats["min"], 25.0)
        self.assertEqual(stats["max"], 95.0)
        self.assertAlmostEqual(stats["mean"], pd.Series(scores).mean(), places=2)
        self.assertAlmostEqual(stats["median"], pd.Series(scores).median(), places=2)
        self.assertAlmostEqual(stats["std_dev"], pd.Series(scores).std(), places=2)

        # Pass / fail distribution:
        # Passed (>=50): 55, 65, 75, 85, 95, 72 -> 6 students (75.0%)
        # Failed (<50): 25, 45 -> 2 students (25.0%)
        pf = res["pass_fail"]
        self.assertEqual(pf["passed_count"], 6)
        self.assertAlmostEqual(pf["passed_pct"], 75.0, places=1)
        self.assertEqual(pf["failed_count"], 2)
        self.assertAlmostEqual(pf["failed_pct"], 25.0, places=1)

        # Bins: 0-39 (1: 25), 40-49 (1: 45), 70-79 (2: 75, 72)
        bins_df = res["summary_df"]
        b0_39 = bins_df[bins_df["Range"] == "0–39%"].iloc[0]
        self.assertEqual(b0_39["Student Count"], 1)
        b70_79 = bins_df[bins_df["Range"] == "70–79%"].iloc[0]
        self.assertEqual(b70_79["Student Count"], 2)

    def test_missing_marks_not_treated_as_zero(self):
        """Ensure None/NaN marks in database are omitted and not treated as zero in statistics."""
        ds.add_student({"student_id": "S401", "name": "One", "department": "Civil", "semester": 2, "academic_score": 80.0}, db_path=self.db_path)
        ds.add_student({"student_id": "S402", "name": "Two", "department": "Civil", "semester": 2, "academic_score": None}, db_path=self.db_path)

        res = ds.get_marks_distribution_analysis(department="Civil", db_path=self.db_path)
        self.assertTrue(res["has_data"])
        self.assertEqual(res["raw_records_count"], 1)
        # If None were treated as zero, mean would be 40; since omitted, mean is 80
        self.assertEqual(res["stats"]["mean"], 80.0)

    def test_student_score_improvement_plan(self):
        """Verify generation of personalized, actionable study recommendations."""
        ds.add_student({
            "student_id": "S501", "name": "Deepa Roy", "department": "Electronics",
            "semester": 4, "academic_score": 70.0
        }, db_path=self.db_path)

        with db.transaction(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO subject_grades (student_id, subject, marks) VALUES (?, ?, ?)",
                [
                    ("S501", "Digital Circuits", 85.0),
                    ("S501", "Signals and Systems", 52.0),
                ]
            )

        plan = ds.get_student_score_improvement_plan("S501", db_path=self.db_path)
        self.assertTrue(plan["has_student"])
        self.assertEqual(plan["strongest_subject"]["name"], "Digital Circuits")
        self.assertEqual(plan["focus_subject"]["name"], "Signals and Systems")
        self.assertGreaterEqual(len(plan["action_items"]), 1)
        self.assertGreaterEqual(len(plan["daily_plan"]), 5)
        # Check that the 3 questions are answered:
        item = plan["action_items"][0]
        self.assertIn("what", item)
        self.assertIn("why", item)
        self.assertIn("next_step", item)


if __name__ == "__main__":
    unittest.main()
