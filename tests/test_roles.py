"""Unit tests for server-side role-based authorization and student privacy isolation."""
import os
import shutil
import tempfile
import unittest

import auth
import data_service as ds
import database as db


class RoleAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_roles.db")
        db.init_db(self.db_path, seed=True)  # Seeds DEMO001, DEMO002...

        # Create admin, staff, and student users
        self.admin, _ = auth.create_user("admin_user", "AdminSecret123", "admin", "Admin A", db_path=self.db_path)
        self.staff, _ = auth.create_user("staff_user", "StaffSecret123", "staff", "Demo Mentor A", staff_department="Computer Science", db_path=self.db_path)
        self.student, _ = auth.create_user("student_user", "StudentSecret123", "student", "Aarav Sharma", student_id="DEMO001", db_path=self.db_path)
        self.student2, _ = auth.create_user("student_user2", "StudentSecret123", "student", "Diya Iyer", student_id="DEMO002", db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_require_role_enforcement(self):
        # Admin allowed for admin-only functions
        self.assertTrue(ds.require_role(self.admin, ("admin",)))
        self.assertTrue(ds.require_role(self.admin, ("admin", "staff")))

        # Staff disallowed for admin-only functions
        with self.assertRaises(ds.AuthorizationError):
            ds.require_role(self.staff, ("admin",))

        # Student disallowed for staff functions
        with self.assertRaises(ds.AuthorizationError):
            ds.require_role(self.student, ("admin", "staff"))

        # Unauthenticated disallowed
        with self.assertRaises(ds.AuthorizationError):
            ds.require_role(None, ("admin", "staff", "student"))

    def test_student_data_isolation(self):
        # Student requesting own record
        s = ds.get_student("DEMO001", self.db_path, user=self.student)
        self.assertEqual(s["student_id"], "DEMO001")

        # Student attempting to query another student's record -> ignored, returns own record
        s_other = ds.get_student("DEMO002", self.db_path, user=self.student)
        self.assertEqual(s_other["student_id"], "DEMO001")

        # Staff can query any student
        s_staff_view = ds.get_student("DEMO002", self.db_path, user=self.staff)
        self.assertEqual(s_staff_view["student_id"], "DEMO002")

    def test_student_cannot_add_or_delete_students(self):
        new_data = {
            "student_id": "HACK01", "name": "Hack", "department": "Civil", "semester": 2,
            "attendance_rate": 80, "academic_score": 80, "assignment_rate": 80
        }
        with self.assertRaises(ds.AuthorizationError):
            ds.add_student(new_data, self.db_path, user=self.student)

        with self.assertRaises(ds.AuthorizationError):
            ds.delete_student("DEMO001", self.db_path, user=self.student)

        with self.assertRaises(ds.AuthorizationError):
            ds.update_student("DEMO001", new_data, self.db_path, user=self.student)

    def test_student_screened_df_only_returns_own_record(self):
        df_student = ds.get_screened_df(self.db_path, user=self.student)
        self.assertEqual(len(df_student), 1)
        self.assertEqual(df_student.iloc[0]["student_id"], "DEMO001")

        # Staff sees all students
        df_staff = ds.get_screened_df(self.db_path, user=self.staff)
        self.assertGreater(len(df_staff), 1)

    def test_student_subject_grades_and_history_isolation(self):
        grades = ds.get_subject_grades_df("DEMO002", self.db_path, user=self.student)
        # Even if passing DEMO002 in parameter, student user gets their own grades (DEMO001)
        self.assertFalse(grades.empty)
        # Confirm student gets DEMO001's subjects, which include Mathematics
        self.assertIn("Mathematics", list(grades["Subject"]))

        # History is similarly isolated
        hist = ds.get_history_df(["DEMO002"], self.db_path, user=self.student)
        if not hist.empty:
            self.assertEqual(set(hist["student_id"]), {"DEMO001"})

    def test_staff_student_mapping_stability_after_display_name_change(self):
        # Create a new student assigned with mentor_username
        st_data = {
            "student_id": "STABLE01",
            "name": "Target Mentee",
            "department": "Computer Science",
            "semester": 3,
            "attendance_rate": 78.0,
            "academic_score": 75.0,
            "assignment_rate": 80.0,
            "email": "mentee@school.edu",
            "mentor": "Demo Mentor A",
            "mentor_username": "staff_user",
            "mentor_user_id": self.staff["id"]
        }
        ok, errs = ds.add_student(st_data, db_path=self.db_path, user=self.admin)
        self.assertTrue(ok)
        self.assertEqual(errs, [])

        # Verify mentor_username matches staff user
        s_rec = ds.get_student("STABLE01", db_path=self.db_path)
        self.assertEqual(s_rec["mentor_username"], "staff_user")
        self.assertEqual(s_rec["mentor_user_id"], self.staff["id"])

        # Change staff display name (e.g. from 'Demo Mentor A' to 'Dr. Alice Mentor')
        ok_up, _ = auth.update_profile(self.staff["id"], "Dr. Alice Mentor", "alice@school.edu", db_path=self.db_path)
        self.assertTrue(ok_up)

        # Retrieve updated staff object
        updated_staff = auth.get_user_by_id(self.staff["id"], db_path=self.db_path)
        self.assertEqual(updated_staff["display_name"], "Dr. Alice Mentor")

        # Stable link check: mentor_username still matches updated_staff['username']
        self.assertEqual(s_rec["mentor_username"], updated_staff["username"].lower())

    def test_login_portal_role_validation(self):
        # Authenticate student account
        u_stu, err = auth.authenticate("student_user", "StudentSecret123", db_path=self.db_path)
        self.assertIsNotNone(u_stu)
        self.assertEqual(u_stu["role"], "student")
        # Attempting to use student account for staff portal is blocked server-side
        with self.assertRaises(ds.AuthorizationError):
            ds.require_role(u_stu, ("staff", "admin"))

        # Authenticate staff account
        u_stf, err = auth.authenticate("staff_user", "StaffSecret123", db_path=self.db_path)
        self.assertIsNotNone(u_stf)
        self.assertEqual(u_stf["role"], "staff")
        # Attempting to use staff account for admin functions is blocked server-side
        with self.assertRaises(ds.AuthorizationError):
            ds.require_role(u_stf, ("admin",))

    def test_student_recommendations_and_goals_isolation(self):
        # Student cannot query or track recommendations for another student
        recs, screening = ds.get_recommendations_for_student("DEMO002", db_path=self.db_path, user=self.student)
        # Should return recommendations for self (DEMO001) because resolve_target_student enforces it
        self.assertIsNotNone(screening)
        self.assertIsNotNone(recs)

        # Student cannot view or modify other student's review status
        with self.assertRaises(ds.AuthorizationError):
            ds.set_review_status("DEMO002", "Under review", db_path=self.db_path, user=self.student)


if __name__ == "__main__":
    unittest.main()
