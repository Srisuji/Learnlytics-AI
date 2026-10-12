"""Authentication and user management for Learnlytics AI.

Security guarantees:
  * Passwords hashed using PBKDF2-HMAC-SHA256 (250,000 iterations) with random per-user salt.
  * Constant-time comparison using hmac.compare_digest.
  * Minimum password length 8.
  * Generic "Incorrect username or password" for both unknown user and bad password.
  * Account lock for 10 minutes after 5 consecutive failed attempts.
  * No Streamlit import in this module so it remains fully unit-testable.
"""
import datetime as dt
import hashlib
import hmac
import os
import secrets
import sqlite3

import database as db

ITERATIONS = 250_000
LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 10
MIN_PASSWORD_LENGTH = 8
ROLES = ("admin", "staff", "student")


class AuthError(Exception):
    """Raised for authentication or permission problems."""


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _to_iso(dt_obj):
    return dt_obj.isoformat()


def _from_iso(iso_str):
    if not iso_str:
        return None
    try:
        # Handle trailing Z or offset
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        return dt.datetime.fromisoformat(iso_str)
    except Exception:
        return None


def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    """Hash password with PBKDF2-HMAC-SHA256. Returns (hex_hash, hex_salt)."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return key.hex(), salt.hex()


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    """Compare password against stored hash using constant-time comparison."""
    try:
        salt_bytes = bytes.fromhex(stored_salt)
        expected_bytes = bytes.fromhex(stored_hash)
        computed_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, ITERATIONS)
        return hmac.compare_digest(computed_bytes, expected_bytes)
    except Exception:
        return False


def count_users(db_path=None) -> int:
    """Return total number of users in the system."""
    with db.transaction(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return row["c"] if row else 0


def get_user_by_id(user_id: int, db_path=None) -> dict | None:
    with db.transaction(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, role, display_name, email, student_id, staff_department, "
            "must_change_password, failed_attempts, locked_until, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str, db_path=None) -> dict | None:
    if not username:
        return None
    with db.transaction(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, role, display_name, email, student_id, staff_department, "
            "must_change_password, failed_attempts, locked_until, is_active, created_at FROM users WHERE lower(username) = ?",
            (username.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None


def create_user(username: str, password: str, role: str, display_name: str,
                email: str = None, student_id: str = None, staff_department: str = None,
                must_change_password: bool = False, db_path=None) -> tuple[dict | None, list[str]]:
    """Create a new user. Returns (user_dict, errors)."""
    errors = []
    u = (username or "").strip()
    if not u:
        errors.append("Username is required.")
    elif len(u) < 3 or len(u) > 32 or any(ch.isspace() for ch in u):
        errors.append("Username must be between 3 and 32 characters with no spaces.")

    if not password:
        errors.append("Password is required.")
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")

    if role not in ROLES:
        errors.append(f"Role must be one of: {', '.join(ROLES)}.")

    dname = (display_name or "").strip()
    if not dname:
        errors.append("Display name is required.")

    if role == "student":
        if not student_id:
            errors.append("A student ID is required for student accounts.")
        else:
            # Check student exists in students table
            with db.transaction(db_path) as conn:
                st_row = conn.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,)).fetchone()
                if not st_row:
                    errors.append(f"No student record exists for student ID '{student_id}'.")
                # Ensure no other user already linked to this student_id
                dup = conn.execute("SELECT id FROM users WHERE student_id = ?", (student_id,)).fetchone()
                if dup:
                    errors.append(f"Student ID '{student_id}' is already linked to another user account.")

    if errors:
        return None, errors

    pwd_hash, pwd_salt = hash_password(password)
    try:
        with db.transaction(db_path) as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, role, display_name, "
                "email, student_id, staff_department, must_change_password, failed_attempts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (u.lower(), pwd_hash, pwd_salt, role, dname, email.strip() if email else None,
                 student_id.strip() if student_id else None,
                 staff_department.strip() if staff_department else None,
                 1 if must_change_password else 0),
            )
            uid = cur.lastrowid
            # Default preferences
            conn.execute(
                "INSERT INTO user_preferences (user_id, default_department, default_page) VALUES (?, NULL, NULL)",
                (uid,),
            )
        return get_user_by_id(uid, db_path), []
    except sqlite3.IntegrityError:
        return None, [f"Username '{u}' is already taken. Please choose another username."]


def authenticate(username: str, password: str, db_path=None) -> tuple[dict | None, str | None]:
    """Authenticate credentials.

    Returns (user_dict, None) on success.
    Returns (None, error_message) on failure.
    Always uses 'Incorrect username or password' unless account is locked or deactivated.
    """
    generic_error = "Incorrect username or password"
    if not username or not password:
        return None, generic_error

    u_clean = username.strip().lower()
    with db.transaction(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, password_salt, role, display_name, email, "
            "student_id, staff_department, must_change_password, failed_attempts, locked_until, is_active "
            "FROM users WHERE lower(username) = ? OR (student_id IS NOT NULL AND lower(student_id) = ?)",
            (u_clean, u_clean),
        ).fetchone()

        if not row:
            return None, generic_error

        # Check deactivation
        if row["is_active"] == 0:
            return None, "This account has been deactivated. Please contact your administrator."

        # Check account lock
        now = _now()
        locked_until_dt = _from_iso(row["locked_until"])
        if locked_until_dt:
            # Normalize timezone comparison
            if locked_until_dt.tzinfo is None:
                locked_until_dt = locked_until_dt.replace(tzinfo=dt.timezone.utc)
            if now < locked_until_dt:
                diff_sec = int((locked_until_dt - now).total_seconds())
                mins = max(1, (diff_sec + 59) // 60)
                return None, f"Account is temporarily locked due to multiple failed attempts. Please try again in {mins} minute(s)."

        # Verify password
        is_valid = verify_password(password, row["password_hash"], row["password_salt"])
        if not is_valid:
            new_attempts = row["failed_attempts"] + 1
            if new_attempts >= LOCKOUT_ATTEMPTS:
                lock_time = now + dt.timedelta(minutes=LOCKOUT_MINUTES)
                conn.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                    (new_attempts, _to_iso(lock_time), row["id"]),
                )
                return None, f"Too many failed login attempts. Account has been locked for {LOCKOUT_MINUTES} minutes."
            else:
                conn.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (new_attempts, row["id"]))
                return None, generic_error

        # Success: reset failed attempts and locked_until
        conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (row["id"],))

    return get_user_by_id(row["id"], db_path), None


def change_password(user_id: int, old_password: str, new_password: str, db_path=None) -> tuple[bool, list[str]]:
    """User changes their own password. Requires correct old_password."""
    errors = []
    if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
        errors.append(f"New password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if old_password == new_password:
        errors.append("New password cannot be the same as the current password.")

    with db.transaction(db_path) as conn:
        row = conn.execute("SELECT password_hash, password_salt FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False, ["User not found."]
        if not verify_password(old_password, row["password_hash"], row["password_salt"]):
            return False, ["Current password is incorrect."]

    if errors:
        return False, errors

    pwd_hash, pwd_salt = hash_password(new_password)
    with db.transaction(db_path) as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, password_salt = ?, must_change_password = 0, "
            "failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (pwd_hash, pwd_salt, user_id),
        )
    return True, []


def reset_password(admin_user: dict, target_user_id: int, db_path=None) -> tuple[str | None, list[str]]:
    """Admin resets a user's password. Generates temporary password shown once, sets must_change_password=1."""
    if not admin_user or admin_user.get("role") != "admin":
        return None, ["Unauthorized: Only administrators can reset user passwords."]

    temp_password = secrets.token_urlsafe(9)  # 12 chars URL-safe
    pwd_hash, pwd_salt = hash_password(temp_password)

    with db.transaction(db_path) as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, password_salt = ?, must_change_password = 1, "
            "failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (pwd_hash, pwd_salt, target_user_id),
        )
        if cur.rowcount == 0:
            return None, ["Target user not found."]

    return temp_password, []


def update_profile(user_id: int, display_name: str, email: str = None,
                   staff_department: str = None, db_path=None) -> tuple[bool, list[str]]:
    """Update user personal profile details."""
    dname = (display_name or "").strip()
    if not dname:
        return False, ["Display name cannot be empty."]
    if email and ("@" not in email or len(email) > 120):
        return False, ["Please provide a valid email address."]

    with db.transaction(db_path) as conn:
        conn.execute(
            "UPDATE users SET display_name = ?, email = ?, staff_department = ? WHERE id = ?",
            (dname, email.strip() if email else None,
             staff_department.strip() if staff_department else None, user_id),
        )
    return True, []


def get_preferences(user_id: int, db_path=None) -> dict:
    """Return user preferences dictionary."""
    with db.transaction(db_path) as conn:
        row = conn.execute(
            "SELECT default_department, default_page FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            return {"default_department": row["default_department"], "default_page": row["default_page"]}
        return {"default_department": None, "default_page": None}


def save_preferences(user_id: int, default_department: str = None, default_page: str = None, db_path=None) -> bool:
    """Store or update user preferences."""
    with db.transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO user_preferences (user_id, default_department, default_page, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) ON CONFLICT(user_id) DO UPDATE SET "
            "default_department = excluded.default_department, default_page = excluded.default_page, "
            "updated_at = excluded.updated_at",
            (user_id, default_department or None, default_page or None),
        )
    return True


def list_users(db_path=None) -> list[dict]:
    """List all user accounts for admin management."""
    with db.transaction(db_path) as conn:
        rows = conn.execute(
            "SELECT id, username, role, display_name, email, student_id, staff_department, "
            "must_change_password, failed_attempts, locked_until, is_active, created_at FROM users ORDER BY id",
        ).fetchall()
        return [dict(r) for r in rows]


def deactivate_user(admin_user: dict, target_user_id: int, db_path=None) -> tuple[bool, str | None]:
    """Admin deactivates a user account (prevents login without destroying account history)."""
    if not admin_user or admin_user.get("role") != "admin":
        return False, "Unauthorized: Only administrators can deactivate accounts."
    if admin_user.get("id") == target_user_id:
        return False, "You cannot deactivate your own administrative account."

    with db.transaction(db_path) as conn:
        cur = conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (target_user_id,))
        if cur.rowcount == 0:
            return False, "User not found."
    return True, None


def activate_user(admin_user: dict, target_user_id: int, db_path=None) -> tuple[bool, str | None]:
    """Admin reactivates a user account."""
    if not admin_user or admin_user.get("role") != "admin":
        return False, "Unauthorized: Only administrators can reactivate accounts."

    with db.transaction(db_path) as conn:
        cur = conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (target_user_id,))
        if cur.rowcount == 0:
            return False, "User not found."
    return True, None


def delete_user(admin_user: dict, target_user_id: int, db_path=None) -> tuple[bool, str | None]:
    """Admin permanently deletes a user account."""
    if not admin_user or admin_user.get("role") != "admin":
        return False, "Unauthorized: Only administrators can delete accounts."
    if admin_user.get("id") == target_user_id:
        return False, "You cannot delete your own administrative account."

    with db.transaction(db_path) as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        if cur.rowcount == 0:
            return False, "User not found."
    return True, None


def is_demo_mode() -> bool:
    """True when env variable EDUPULSE_DEMO_MODE is set to '1'."""
    return os.environ.get("EDUPULSE_DEMO_MODE") == "1"


def seed_demo_users_if_needed(db_path=None) -> dict[str, str]:
    """Seed demo accounts if EDUPULSE_DEMO_MODE=1 and they do not already exist.

    Returns dict of {username: password} for accounts seeded in this run.
    """
    if not is_demo_mode():
        return {}

    # Check if demo users already seeded
    seeded_meta = db.get_meta("demo_users_seeded", db_path=db_path)
    if seeded_meta:
        return {}

    seeded_passwords = {}
    demo_accounts = [
        ("demo_admin", "admin", "Coordinator Admin", "admin@edupulse.local", None, None,
         os.environ.get("EDUPULSE_ADMIN_PASSWORD")),
        ("demo_staff", "staff", "Demo Mentor A", "mentor.a@edupulse.local", None, "Computer Science",
         os.environ.get("EDUPULSE_STAFF_PASSWORD")),
        ("demo_student1", "student", "Aarav Sharma", "aarav@example.edu", "DEMO001", None,
         os.environ.get("EDUPULSE_STUDENT1_PASSWORD")),
        ("demo_student2", "student", "Diya Iyer", "diya@example.edu", "DEMO002", None,
         os.environ.get("EDUPULSE_STUDENT2_PASSWORD")),
    ]

    for uname, role, dname, email, sid, sdept, env_pwd in demo_accounts:
        pwd = env_pwd if env_pwd and len(env_pwd) >= MIN_PASSWORD_LENGTH else secrets.token_urlsafe(9)
        u, _ = create_user(
            username=uname,
            password=pwd,
            role=role,
            display_name=dname,
            email=email,
            student_id=sid,
            staff_department=sdept,
            must_change_password=False,
            db_path=db_path,
        )
        if u:
            seeded_passwords[uname] = pwd

    if seeded_passwords:
        db.set_meta("demo_users_seeded", "1", db_path=db_path)
        print("\n=======================================================")
        print("  EDUPULSE DEMO ACCOUNTS CREATED (EDUPULSE_DEMO_MODE=1)")
        print("=======================================================")
        for uname, pwd in seeded_passwords.items():
            print(f"  Username: {uname:<16} Password: {pwd}")
        print("=======================================================\n")

    return seeded_passwords
