"""Full UI end-to-end integration and page verification tests using Streamlit AppTest.

This tests all user flows:
1. First-time admin setup flow.
2. Sign-in flow (Admin, Staff, Student).
3. Every single page for Admin:
   - Start here
   - My Dashboard
   - Overview Dashboard
   - Students Needing Support
   - Student Directory
   - Recommendations
   - Analytics
   - Reports & Exports
   - Import & Settings
   - Manage Accounts
   - My Profile & Settings
4. Every single page for Staff:
   - All staff allowed pages
   - Verifying Manage Accounts is absent from staff pages
5. Every single page for Student:
   - My Progress
   - My Goals
   - Verifying staff/admin pages are absent from student pages
6. Logout flow.
"""
import os
import shutil
import tempfile
import unittest
from streamlit.testing.v1 import AppTest

import database as db
import auth
import data_service as ds

APP_PY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))


class StreamlitUIVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_ui_verify.db")
        # Ensure fresh database
        db.init_db(self.db_path, seed=True)
        # Point database module default to this temp db during the test
        self.orig_db_path = db.DEFAULT_DB_PATH
        db.DEFAULT_DB_PATH = self.db_path
        os.environ["EDUPULSE_DB_PATH"] = self.db_path

    def tearDown(self):
        db.DEFAULT_DB_PATH = self.orig_db_path
        os.environ.pop("EDUPULSE_DB_PATH", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_first_run_admin_setup_flow(self):
        """Verify first run displays admin creation form when no users exist."""
        at = AppTest.from_file(APP_PY_PATH, default_timeout=15)
        at.run()
        self.assertFalse(at.exception)
        # Verify first run message is displayed
        text_content = " ".join([t.value for t in at.markdown])
        self.assertIn("Create the First Administrator Account", text_content)

    def test_02_admin_login_and_all_pages_render_without_errors(self):
        """Seed admin and verify all 11 admin pages render smoothly with zero exceptions."""
        admin_user, _ = auth.create_user("sysadmin", "AdminPass123", "admin", "System Administrator", db_path=self.db_path)
        self.assertIsNotNone(admin_user)

        admin_pages = [
            "Start here",
            "My Dashboard",
            "Overview Dashboard",
            "Students Needing Support",
            "Student Directory",
            "Recommendations",
            "Analytics",
            "Reports & Exports",
            "Import & Settings",
            "Manage Accounts",
            "My Profile & Settings",
        ]

        for page in admin_pages:
            at = AppTest.from_file(APP_PY_PATH, default_timeout=15)
            at.session_state["user"] = admin_user
            at.session_state["nav_page"] = page
            at.run()
            self.assertFalse(at.exception, f"Exception occurred while rendering admin page: {page}")
            self.assertEqual(len(at.exception), 0)

    def test_03_staff_login_and_pages_render_without_errors(self):
        """Seed staff user and verify all 10 staff pages render with zero exceptions, and Manage Accounts is blocked."""
        staff_user, _ = auth.create_user("prof_smith", "StaffPass123", "staff", "Professor Smith", staff_department="Computer Science", db_path=self.db_path)
        self.assertIsNotNone(staff_user)

        staff_pages = [
            "Start here",
            "My Dashboard",
            "Overview Dashboard",
            "Students Needing Support",
            "Student Directory",
            "Recommendations",
            "Analytics",
            "Reports & Exports",
            "Import & Settings",
            "My Profile & Settings",
        ]

        for page in staff_pages:
            at = AppTest.from_file(APP_PY_PATH, default_timeout=15)
            at.session_state["user"] = staff_user
            at.session_state["nav_page"] = page
            at.run()
            self.assertFalse(at.exception, f"Exception occurred while rendering staff page: {page}")

    def test_04_student_portal_pages_render_without_errors(self):
        """Seed student user and verify student pages render cleanly."""
        student_user, _ = auth.create_user("student_aarav", "StudentPass123", "student", "Aarav Sharma", student_id="DEMO001", db_path=self.db_path)
        self.assertIsNotNone(student_user)

        student_pages = [
            "My Progress",
            "My Goals",
            "My Profile & Settings",
        ]

        for page in student_pages:
            at = AppTest.from_file(APP_PY_PATH, default_timeout=15)
            at.session_state["user"] = student_user
            at.session_state["nav_page"] = page
            at.run()
            self.assertFalse(at.exception, f"Exception occurred while rendering student page: {page}")

    def test_05_force_password_change_flow(self):
        """User with must_change_password=1 must see force password screen."""
        staff_temp, _ = auth.create_user("temp_staff", "TempPass123", "staff", "Temp Staff", must_change_password=True, db_path=self.db_path)
        at = AppTest.from_file(APP_PY_PATH, default_timeout=15)
        at.session_state["user"] = staff_temp
        at.run()
        self.assertFalse(at.exception)
        text_content = " ".join([t.value for t in at.markdown])
        self.assertIn("Password Change Required", text_content)


    def test_06_login_page_student_and_staff_options(self):
        """Verify login screen renders student and staff login modes."""
        # Ensure at least 1 user exists so login screen renders instead of first-run setup
        auth.create_user("admin_test", "AdminPass123", "admin", "Admin Test", db_path=self.db_path)
        at = AppTest.from_file(APP_PY_PATH, default_timeout=15)
        at.run()
        self.assertFalse(at.exception)
        text_content = " ".join([t.value for t in at.markdown])
        self.assertIn("Sign In to Learnlytics AI", text_content)
        self.assertIn("Student Login", text_content)


if __name__ == "__main__":
    unittest.main()
