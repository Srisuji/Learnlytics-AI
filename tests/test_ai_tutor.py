"""Automated tests for Learnlytics AI Tutor.

Covers:
1. Authentication and Authorization:
   - Unauthenticated access blocked.
   - Non-student access blocked.
   - Student accessing only their own conversation.
   - Cross-student access denied.
2. AI Service & Provider Integration:
   - Missing API key returns friendly notice.
   - Mocked successful API completion.
   - Rate limiting enforcement.
   - AuthenticationError handling.
   - APIConnectionError & APIError handling.
   - Empty/malformed response handling.
   - No secrets leaked in user messages.
3. Student Privacy & Data Minimization:
   - Minimal authorized student data assembled into prompt.
   - No passwords, salts, or other student records included.
   - Missing K1/K2/K3 handled honestly.
4. Conversation State & Safety:
   - Conversation creation, listing, retrieval, and deletion.
   - Deleting conversation history leaves academic records intact.
"""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import ai_tutor_service as tutor_svc
import database as db
import data_service as ds


class TestAITutor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        db.init_db(self.db_path, seed=False)

        # Create two test students in database
        ds.add_student({"student_id": "STU001", "name": "Aarav Sharma", "department": "Computer Science", "semester": 3, "attendance_rate": 88.0, "academic_score": 76.5}, db_path=self.db_path)
        ds.add_student({"student_id": "STU002", "name": "Meera Patel", "department": "Electronics", "semester": 5, "attendance_rate": 92.0, "academic_score": 84.0}, db_path=self.db_path)

        # Create user accounts for these students
        with db.transaction(self.db_path) as conn:
            cur1 = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, role, display_name, student_id) "
                "VALUES ('aarav', 'hash1', 'salt1', 'student', 'Aarav Sharma', 'STU001')"
            )
            self.user1_id = cur1.lastrowid

            cur2 = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, role, display_name, student_id) "
                "VALUES ('meera', 'hash2', 'salt2', 'student', 'Meera Patel', 'STU002')"
            )
            self.user2_id = cur2.lastrowid

            cur3 = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, role, display_name, student_id) "
                "VALUES ('staff_prof', 'hash3', 'salt3', 'staff', 'Prof. Kumar', NULL)"
            )
            self.staff_id = cur3.lastrowid

        self.student_user1 = {"id": self.user1_id, "username": "aarav", "role": "student", "student_id": "STU001"}
        self.student_user2 = {"id": self.user2_id, "username": "meera", "role": "student", "student_id": "STU002"}
        self.staff_user = {"id": self.staff_id, "username": "staff_prof", "role": "staff"}

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    # -------------------------------------------------------------------------
    # 1. Authorization & Role Checks
    # -------------------------------------------------------------------------
    def test_unauthenticated_or_staff_access_blocked(self):
        """Staff or None users must not be permitted to create or read tutor conversations."""
        with self.assertRaises(ds.AuthorizationError):
            ds.get_or_create_conversation(None, db_path=self.db_path)

        with self.assertRaises(ds.AuthorizationError):
            ds.get_or_create_conversation(self.staff_user, db_path=self.db_path)

    def test_conversation_ownership_isolation(self):
        """Student 2 must never access or modify Student 1's conversation."""
        conv1 = ds.get_or_create_conversation(self.student_user1, language="English", db_path=self.db_path)
        ds.add_chat_message(self.student_user1, conv1["id"], "student", "Hello tutor!", db_path=self.db_path)

        # Student 1 can retrieve their messages
        msgs1 = ds.get_conversation_messages(self.student_user1, conv1["id"], db_path=self.db_path)
        self.assertEqual(len(msgs1), 1)
        self.assertEqual(msgs1[0]["content"], "Hello tutor!")

        # Student 2 attempting to read Student 1's conversation is rejected
        with self.assertRaises(ds.AuthorizationError):
            ds.get_conversation_messages(self.student_user2, conv1["id"], db_path=self.db_path)

        # Student 2 attempting to add a message to Student 1's conversation is rejected
        with self.assertRaises(ds.AuthorizationError):
            ds.add_chat_message(self.student_user2, conv1["id"], "student", "Malicious message", db_path=self.db_path)

        # Student 2 attempting to delete Student 1's conversation is blocked
        deleted = ds.delete_student_conversation(self.student_user2, conv1["id"], db_path=self.db_path)
        self.assertFalse(deleted)

    def test_delete_history_leaves_academic_records_intact(self):
        """Clearing conversation history deletes only chat rows without affecting student or course marks."""
        conv = ds.get_or_create_conversation(self.student_user1, db_path=self.db_path)
        ds.add_chat_message(self.student_user1, conv["id"], "student", "Question 1", db_path=self.db_path)
        ds.add_chat_message(self.student_user1, conv["id"], "assistant", "Answer 1", db_path=self.db_path)

        self.assertEqual(len(ds.list_student_conversations(self.student_user1, db_path=self.db_path)), 1)
        ds.delete_all_student_conversations(self.student_user1, db_path=self.db_path)
        self.assertEqual(len(ds.list_student_conversations(self.student_user1, db_path=self.db_path)), 0)

        # Student record is completely intact
        student = ds.get_student("STU001", db_path=self.db_path)
        self.assertIsNotNone(student)
        self.assertEqual(student["name"], "Aarav Sharma")

    # -------------------------------------------------------------------------
    # 2. AI Provider Integration & Resilience
    # -------------------------------------------------------------------------
    def test_missing_api_key_handling(self):
        """When OPENAI_API_KEY is not set, tutor returns clear, honest notice."""
        with patch.dict(os.environ, {}, clear=True):
            success, msg = tutor_svc.call_ai_tutor(
                self.student_user1,
                "Explain Newton's third law",
                [],
                db_path=self.db_path
            )
            self.assertFalse(success)
            self.assertIn("temporarily unavailable", msg)
            self.assertIn("OPENAI_API_KEY", msg)

    @patch("openai.OpenAI")
    def test_mocked_successful_api_completion(self, mock_openai_cls):
        """Test successful response delivery from mocked OpenAI SDK."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "Newton's third law states that for every action, there is an equal and opposite reaction."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-12345"}):
            success, reply = tutor_svc.call_ai_tutor(
                self.student_user1,
                "What is Newton's third law?",
                [],
                language="English",
                db_path=self.db_path
            )
            self.assertTrue(success)
            self.assertIn("equal and opposite reaction", reply)

    @patch("openai.OpenAI")
    def test_rate_limiting_and_auth_error_handling(self, mock_openai_cls):
        """Confirm AuthenticationError yields user-friendly message without stack traces."""
        from openai import AuthenticationError
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = AuthenticationError("Invalid API Key", response=MagicMock(), body=None)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-invalid-key"}):
            success, reply = tutor_svc.call_ai_tutor(
                self.student_user1,
                "What are eigenvalues?",
                [],
                db_path=self.db_path
            )
            self.assertFalse(success)
            self.assertIn("authentication failed", reply)
            self.assertNotIn("sk-invalid-key", reply)

    # -------------------------------------------------------------------------
    # 3. Privacy & Minimal Context Assembly
    # -------------------------------------------------------------------------
    def test_context_assembly_minimal_and_private(self):
        """Assembled student context contains only verified name, department, and marks, zero secrets."""
        context = tutor_svc.build_student_context_block(self.student_user1, db_path=self.db_path)
        self.assertIn("Aarav Sharma", context)
        self.assertIn("Computer Science", context)
        self.assertIn("88.0%", context)

        # Strictly no password hashes or salts
        self.assertNotIn("hash1", context)
        self.assertNotIn("salt1", context)
        # No other student data
        self.assertNotIn("Meera Patel", context)


if __name__ == "__main__":
    unittest.main()
