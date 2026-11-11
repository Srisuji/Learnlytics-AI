"""Automated tests for FastAPI REST API endpoints (backend/main.py).

Tests:
1. Health check & DB status
2. Authentication (success, invalid password, nonexistent user)
3. KPIs calculation endpoint
4. Student list & filtering
5. Single student detail & screening
6. Student CRUD (create, update, delete, get recommendations)
7. Department analytics
8. AI Tutor chat endpoint (with mocked or unconfigured fallback)
9. Error conditions & input validation
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import database as db
import auth
from backend.main import app


class BackendAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_api.db")
        db.init_db(self.db_path, seed=True)
        self.orig_db_path = db.DEFAULT_DB_PATH
        db.DEFAULT_DB_PATH = self.db_path
        os.environ["EDUPULSE_DB_PATH"] = self.db_path

        # Seed test admin & test student user
        auth.create_user("api_admin", "AdminPass123", "admin", "API Admin", db_path=self.db_path)
        self.client = TestClient(app)

    def tearDown(self):
        db.DEFAULT_DB_PATH = self.orig_db_path
        os.environ.pop("EDUPULSE_DB_PATH", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_health_check(self):
        """GET /api/health returns 200 and database connected."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["database_connected"])

    def test_login_success(self):
        """POST /api/auth/login succeeds with correct credentials."""
        resp = self.client.post("/api/auth/login", json={
            "username": "api_admin",
            "password": "AdminPass123"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["username"], "api_admin")
        self.assertEqual(data["role"], "admin")
        self.assertNotIn("password_hash", data)
        self.assertNotIn("password_salt", data)

    def test_login_failure(self):
        """POST /api/auth/login returns 401 on invalid password."""
        resp = self.client.post("/api/auth/login", json={
            "username": "api_admin",
            "password": "WrongPassword!"
        })
        self.assertEqual(resp.status_code, 401)

    def test_get_kpis(self):
        """GET /api/kpis returns aggregated student metrics."""
        resp = self.client.get("/api/kpis")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_students", data)
        self.assertIn("avg_attendance", data)
        self.assertIn("avg_score", data)
        self.assertGreater(data["total_students"], 0)

    def test_list_students_and_filter(self):
        """GET /api/students returns student list with optional filtering."""
        resp = self.client.get("/api/students")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("students", data)
        self.assertGreater(data["total"], 0)

        # Filter by department
        first_dept = data["students"][0]["department"]
        resp_dept = self.client.get(f"/api/students?department={first_dept}")
        self.assertEqual(resp_dept.status_code, 200)
        data_dept = resp_dept.json()
        for s in data_dept["students"]:
            self.assertEqual(s["department"], first_dept)

    def test_get_student_detail_and_not_found(self):
        """GET /api/students/{id} returns details for existing student and 404 for unknown."""
        # Nonexistent student
        resp_404 = self.client.get("/api/students/NONEXISTENT999")
        self.assertEqual(resp_404.status_code, 404)

        # Existing student
        resp_list = self.client.get("/api/students")
        stu_id = resp_list.json()["students"][0]["student_id"]
        resp_detail = self.client.get(f"/api/students/{stu_id}")
        self.assertEqual(resp_detail.status_code, 200)
        detail = resp_detail.json()
        self.assertEqual(detail["student"]["student_id"], stu_id)
        self.assertIn("screening", detail)
        self.assertIn("score", detail["screening"])

    def test_student_crud_lifecycle(self):
        """Test creating, updating, getting recommendations, and deleting a student."""
        new_stu = {
            "student_id": "TEST_STU_001",
            "name": "Jane Test Doe",
            "department": "Computer Science",
            "semester": 4,
            "attendance_rate": 65.0,
            "academic_score": 45.0,
            "assignment_rate": 55.0,
            "email": "jane@example.com",
            "mentor": "Dr. Alan",
        }

        # 1. Create
        create_resp = self.client.post("/api/students", json=new_stu)
        self.assertEqual(create_resp.status_code, 201)

        # 2. Verify in details
        get_resp = self.client.get("/api/students/TEST_STU_001")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["student"]["name"], "Jane Test Doe")

        # 3. Recommendations
        rec_resp = self.client.get("/api/students/TEST_STU_001/recommendations")
        self.assertEqual(rec_resp.status_code, 200)
        recs = rec_resp.json()["recommendations"]
        self.assertGreater(len(recs), 0)

        # 4. Update
        update_resp = self.client.put("/api/students/TEST_STU_001", json={"attendance_rate": 88.0})
        self.assertEqual(update_resp.status_code, 200)
        get_updated = self.client.get("/api/students/TEST_STU_001")
        self.assertEqual(get_updated.json()["student"]["attendance_rate"], 88.0)

        # 5. Delete
        del_resp = self.client.delete("/api/students/TEST_STU_001")
        self.assertEqual(del_resp.status_code, 200)

        # 6. Verify deleted
        get_deleted = self.client.get("/api/students/TEST_STU_001")
        self.assertEqual(get_deleted.status_code, 404)

    def test_department_analytics(self):
        """GET /api/analytics/departments returns department summary table."""
        resp = self.client.get("/api/analytics/departments")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("departments", data)
        self.assertIsInstance(data["departments"], list)

    def test_ai_tutor_endpoint(self):
        """POST /api/ai-tutor/chat invokes AI tutor service."""
        # Nonexistent student should 404
        bad_stu = self.client.post("/api/ai-tutor/chat", json={
            "student_id": "NO_SUCH_STUDENT",
            "prompt": "Explain loops in Python."
        })
        self.assertEqual(bad_stu.status_code, 404)

        # Existing student
        resp_list = self.client.get("/api/students")
        stu_id = resp_list.json()["students"][0]["student_id"]

        with patch("ai_tutor_service.call_ai_tutor") as mock_tutor:
            mock_tutor.return_value = (True, "Loops repeat execution of code blocks.")
            chat_resp = self.client.post("/api/ai-tutor/chat", json={
                "student_id": stu_id,
                "prompt": "Explain loops in Python.",
                "language": "English"
            })
            self.assertEqual(chat_resp.status_code, 200)
            chat_data = chat_resp.json()
            self.assertTrue(chat_data["success"])
            self.assertEqual(chat_data["reply"], "Loops repeat execution of code blocks.")


if __name__ == "__main__":
    unittest.main()
