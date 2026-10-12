import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk_engine as risk  # noqa: E402


def student(att=90, score=80, asg=90):
    return {"attendance_rate": att, "academic_score": score, "assignment_rate": asg}


class RiskScoringTests(unittest.TestCase):
    def test_healthy_student_is_low(self):
        r = risk.screen_student(student())
        self.assertEqual((r["score"], r["category"]), (0, "Low"))
        self.assertEqual(r["reasons"], [])

    def test_threshold_boundary_is_strictly_below(self):
        self.assertFalse(risk.screen_student(student(att=75))["triggered_keys"])
        self.assertEqual(risk.screen_student(student(att=74.9))["triggered_keys"], ["attendance"])
        self.assertEqual(risk.screen_student(student(score=49.9))["triggered_keys"], ["score"])
        self.assertEqual(risk.screen_student(student(asg=59.9))["triggered_keys"], ["assignment"])

    def test_single_and_combined_indicators_map_to_categories(self):
        self.assertEqual(risk.screen_student(student(score=40))["category"], "Medium")        # 35
        self.assertEqual(risk.screen_student(student(att=60, score=40))["category"], "High")  # 65
        crit = risk.screen_student(student(att=60, score=40, asg=30))
        self.assertEqual((crit["score"], crit["category"]), (85, "Critical"))
        self.assertEqual(risk.screen_student(student(asg=30))["category"], "Low")             # 20 < 25

    def test_category_boundaries(self):
        expected = {0: "Low", 24: "Low", 25: "Medium", 49: "Medium", 50: "High",
                    74: "High", 75: "Critical", 100: "Critical"}
        for score, cat in expected.items():
            self.assertEqual(risk.category_for_score(score), cat, score)

    def test_missing_value_is_unavailable_not_a_failure(self):
        r = risk.screen_student(student(att=None))
        self.assertIn("Attendance", r["unavailable"])
        self.assertNotIn("attendance", r["triggered_keys"])
        self.assertEqual(r["category"], "Low")
        nan = risk.screen_student(student(att=float("nan")))
        self.assertIn("Attendance", nan["unavailable"])

    def test_all_core_metrics_missing_is_insufficient_data(self):
        r = risk.screen_student(student(None, None, None))
        self.assertEqual(r["category"], risk.INSUFFICIENT)
        self.assertEqual(r["score"], 0)

    def test_decline_needs_enough_history(self):
        two = [{"week_date": "2026-01-01", "academic_score": 80},
               {"week_date": "2026-01-08", "academic_score": 60}]
        r = risk.screen_student(student(), two)
        self.assertNotIn("decline", r["triggered_keys"])
        self.assertIn("Score trend", r["unavailable"])
        three = two + [{"week_date": "2026-01-15", "academic_score": 62}]
        r3 = risk.screen_student(student(), three)
        self.assertIn("decline", r3["triggered_keys"])
        self.assertEqual(r3["score"], 15)

    def test_history_is_sorted_by_date_before_comparing(self):
        shuffled = [{"week_date": "2026-01-15", "academic_score": 60},
                    {"week_date": "2026-01-01", "academic_score": 80},
                    {"week_date": "2026-01-08", "academic_score": 70}]
        self.assertIn("decline", risk.screen_student(student(), shuffled)["triggered_keys"])

    def test_improving_history_is_not_flagged(self):
        up = [{"week_date": f"2026-01-0{i}", "academic_score": 50 + i * 5} for i in range(1, 5)]
        self.assertNotIn("decline", risk.screen_student(student(), up)["triggered_keys"])

    def test_config_changes_outcome(self):
        s = student(att=70)
        self.assertEqual(risk.screen_student(s)["category"], "Medium")
        relaxed = {"attendance_threshold": 60}
        self.assertEqual(risk.screen_student(s, None, relaxed)["category"], "Low")

    def test_config_validation(self):
        self.assertEqual(risk.validate_config({}), [])
        self.assertTrue(risk.validate_config({"attendance_threshold": 150}))
        self.assertTrue(risk.validate_config({"medium_min": 60, "high_min": 50}))
        self.assertTrue(risk.validate_config({"min_history": 1}))

    def test_score_is_capped_at_100(self):
        cfg = {"attendance_weight": 60, "score_weight": 60}
        r = risk.screen_student(student(att=10, score=10), None, cfg)
        self.assertEqual(r["score"], 100)

    def test_reasons_show_actual_values_and_actions_exist(self):
        r = risk.screen_student(student(att=68, score=45))
        self.assertTrue(any("68.0%" in text for text in r["reasons"]))
        self.assertGreaterEqual(len(r["faculty_actions"]), 3)  # two indicators + check-in


if __name__ == "__main__":
    unittest.main()
