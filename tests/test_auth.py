"""Unit tests for auth.py authentication, hashing, lockout, and user management."""
import os
import shutil
import tempfile
import unittest

import auth
import database as db


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_auth.db")
        db.init_db(self.db_path, seed=True)  # Seeds DEMO001, DEMO002...

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hash_and_verify_password(self):
        raw = "SecureP@ss123"
        h, s = auth.hash_password(raw)
        self.assertTrue(auth.verify_password(raw, h, s))
        self.assertFalse(auth.verify_password("WrongPassword!", h, s))

    def test_create_user_and_validation(self):
        # Admin
        user, errs = auth.create_user("admin1", "Password123", "admin", "Admin User", db_path=self.db_path)
        self.assertEqual(errs, [])
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "admin1")
        self.assertEqual(user["role"], "admin")

        # Duplicate username
        u2, errs = auth.create_user("admin1", "Password123", "admin", "Other", db_path=self.db_path)
        self.assertIsNone(u2)
        self.assertTrue(any("already taken" in e for e in errs))

        # Short password
        u3, errs = auth.create_user("user2", "short", "staff", "Staff User", db_path=self.db_path)
        self.assertIsNone(u3)
        self.assertTrue(any("at least 8" in e for e in errs))

        # Invalid student linkage
        u4, errs = auth.create_user("student1", "Password123", "student", "Student",
                                    student_id="NON_EXISTENT", db_path=self.db_path)
        self.assertIsNone(u4)
        self.assertTrue(any("No student record exists" in e for e in errs))

        # Valid student linkage
        u5, errs = auth.create_user("student_real", "Password123", "student", "Student A",
                                    student_id="DEMO001", db_path=self.db_path)
        self.assertEqual(errs, [])
        self.assertIsNotNone(u5)
        self.assertEqual(u5["student_id"], "DEMO001")

    def test_authenticate_success_and_failure(self):
        auth.create_user("teacher", "MySecretPass", "staff", "Teacher T", db_path=self.db_path)

        # Success
        user, err = auth.authenticate("teacher", "MySecretPass", db_path=self.db_path)
        self.assertIsNone(err)
        self.assertEqual(user["username"], "teacher")

        # Generic error on wrong password
        u_fail, err = auth.authenticate("teacher", "BadPassword!", db_path=self.db_path)
        self.assertIsNone(u_fail)
        self.assertEqual(err, "Incorrect username or password")

        # Generic error on unknown user
        u_unk, err = auth.authenticate("unknown_user", "AnyPassword!", db_path=self.db_path)
        self.assertIsNone(u_unk)
        self.assertEqual(err, "Incorrect username or password")

    def test_lockout_after_five_failed_attempts(self):
        auth.create_user("target_user", "CorrectPassword123", "staff", "Target User", db_path=self.db_path)

        for attempt in range(4):
            u, err = auth.authenticate("target_user", "WrongPwd", db_path=self.db_path)
            self.assertEqual(err, "Incorrect username or password")

        # 5th attempt locks the account
        u, err = auth.authenticate("target_user", "WrongPwd", db_path=self.db_path)
        self.assertIn("locked for 10 minutes", err)

        # Subsequent attempts are rejected due to lock even with correct password
        u, err = auth.authenticate("target_user", "CorrectPassword123", db_path=self.db_path)
        self.assertIn("temporarily locked", err)

    def test_change_and_reset_password(self):
        admin, _ = auth.create_user("admin_lead", "AdminPass123", "admin", "Admin Lead", db_path=self.db_path)
        staff, _ = auth.create_user("staff_member", "StaffPass123", "staff", "Staff M", db_path=self.db_path)

        # Staff changes password
        ok, errs = auth.change_password(staff["id"], "StaffPass123", "BrandNewPass123", db_path=self.db_path)
        self.assertTrue(ok)
        self.assertEqual(errs, [])

        # Old password no longer works
        u, err = auth.authenticate("staff_member", "StaffPass123", db_path=self.db_path)
        self.assertIsNone(u)

        # New password works
        u, err = auth.authenticate("staff_member", "BrandNewPass123", db_path=self.db_path)
        self.assertIsNotNone(u)
        self.assertEqual(u["must_change_password"], 0)

        # Admin resets password
        temp_pwd, errs = auth.reset_password(admin, staff["id"], db_path=self.db_path)
        self.assertEqual(errs, [])
        self.assertIsNotNone(temp_pwd)

        # Authenticate with temp password
        u, err = auth.authenticate("staff_member", temp_pwd, db_path=self.db_path)
        self.assertIsNotNone(u)
        self.assertEqual(u["must_change_password"], 1)

    def test_preferences(self):
        staff, _ = auth.create_user("pref_user", "Password123", "staff", "Pref User", db_path=self.db_path)
        auth.save_preferences(staff["id"], default_department="Computer Science", default_page="My Dashboard", db_path=self.db_path)

        prefs = auth.get_preferences(staff["id"], db_path=self.db_path)
        self.assertEqual(prefs["default_department"], "Computer Science")
        self.assertEqual(prefs["default_page"], "My Dashboard")

    def test_demo_mode_seeding(self):
        os.environ["EDUPULSE_DEMO_MODE"] = "1"
        try:
            seeded = auth.seed_demo_users_if_needed(self.db_path)
            self.assertIn("demo_admin", seeded)
            self.assertIn("demo_staff", seeded)
            self.assertIn("demo_student1", seeded)
            self.assertIn("demo_student2", seeded)

            # Check demo student link
            u_s1 = auth.get_user_by_username("demo_student1", self.db_path)
            self.assertEqual(u_s1["student_id"], "DEMO001")
        finally:
            os.environ.pop("EDUPULSE_DEMO_MODE", None)

    def test_deactivate_and_reactivate_user(self):
        admin, _ = auth.create_user("super_admin", "AdminPass123", "admin", "Admin Super", db_path=self.db_path)
        staff, _ = auth.create_user("staff_suspend", "StaffPass123", "staff", "Staff Suspend", db_path=self.db_path)

        # Deactivate by non-admin should fail
        ok, err = auth.deactivate_user(staff, staff["id"], db_path=self.db_path)
        self.assertFalse(ok)
        self.assertIn("Unauthorized", err)

        # Admin cannot deactivate self
        ok, err = auth.deactivate_user(admin, admin["id"], db_path=self.db_path)
        self.assertFalse(ok)
        self.assertIn("cannot deactivate your own", err)

        # Admin deactivates staff account
        ok, err = auth.deactivate_user(admin, staff["id"], db_path=self.db_path)
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Deactivated user cannot authenticate
        u, err = auth.authenticate("staff_suspend", "StaffPass123", db_path=self.db_path)
        self.assertIsNone(u)
        self.assertIn("deactivated", err.lower())

        # Admin reactivates staff account
        ok, err = auth.activate_user(admin, staff["id"], db_path=self.db_path)
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Authenticate succeeds again
        u, err = auth.authenticate("staff_suspend", "StaffPass123", db_path=self.db_path)
        self.assertIsNotNone(u)
        self.assertEqual(u["username"], "staff_suspend")


if __name__ == "__main__":
    unittest.main()
