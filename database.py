"""SQLite storage layer for Learnlytics AI.

Responsibilities:
  * open connections safely (foreign keys ON, rows as dict-like objects)
  * create tables if they are missing (never drops or erases anything)
  * seed clearly labelled SYNTHETIC demo students exactly once
  * small helpers for key/value settings stored in the `app_meta` table
"""
import datetime as dt
import os
import random
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = os.environ.get("EDUPULSE_DB_PATH", str(BASE_DIR / "data" / "edupulse.db"))


class DatabaseError(Exception):
    """Raised when the database cannot be opened or initialised."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id       TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    department       TEXT NOT NULL,
    semester         INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 12),
    attendance_rate  REAL CHECK (attendance_rate IS NULL OR attendance_rate BETWEEN 0 AND 100),
    academic_score   REAL CHECK (academic_score  IS NULL OR academic_score  BETWEEN 0 AND 100),
    assignment_rate  REAL CHECK (assignment_rate IS NULL OR assignment_rate BETWEEN 0 AND 100),
    email            TEXT,
    mentor           TEXT,
    mentor_user_id   INTEGER,
    mentor_username  TEXT,
    is_synthetic     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);


CREATE TABLE IF NOT EXISTS subject_grades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    subject    TEXT NOT NULL,
    marks      REAL NOT NULL CHECK (marks BETWEEN 0 AND 100),
    UNIQUE (student_id, subject)
);

CREATE TABLE IF NOT EXISTS weekly_performance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    week_date       TEXT NOT NULL,
    attendance_rate REAL,
    academic_score  REAL,
    assignment_rate REAL,
    UNIQUE (student_id, week_date)
);

-- Review status of a support flag (the flag itself is recalculated live from the rules).
CREATE TABLE IF NOT EXISTS early_warnings (
    student_id    TEXT PRIMARY KEY REFERENCES students(student_id) ON DELETE CASCADE,
    review_status TEXT NOT NULL DEFAULT 'New',
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tracked study-support suggestions (rule-based; the name follows the project brief).
CREATE TABLE IF NOT EXISTS ai_recommendations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    rec_key    TEXT NOT NULL,
    action     TEXT NOT NULL,
    reason     TEXT,
    timeframe  TEXT,
    goal       TEXT,
    status     TEXT NOT NULL DEFAULT 'Suggested',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, rec_key)
);

CREATE TABLE IF NOT EXISTS faculty_interventions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id        TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    intervention_date TEXT NOT NULL,
    concern           TEXT NOT NULL,
    action_taken      TEXT NOT NULL,
    follow_up_date    TEXT,
    status_note       TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT UNIQUE NOT NULL,
    password_hash        TEXT NOT NULL,
    password_salt        TEXT NOT NULL,
    role                 TEXT NOT NULL CHECK (role IN ('admin', 'staff', 'student')),
    display_name         TEXT NOT NULL,
    email                TEXT,
    student_id           TEXT REFERENCES students(student_id) ON DELETE CASCADE,
    staff_department     TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts      INTEGER NOT NULL DEFAULT 0,
    locked_until         TEXT,
    is_active            INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id              INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    default_department   TEXT,
    default_page         TEXT,
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Assessment metadata with cognitive level mapping
CREATE TABLE IF NOT EXISTS assessments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    subject           TEXT NOT NULL,
    assessment_date   TEXT NOT NULL DEFAULT (date('now')),
    pass_marks        REAL DEFAULT 50.0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assessment_questions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id     INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    question_number   INTEGER NOT NULL,
    cognitive_level   TEXT NOT NULL CHECK (cognitive_level IN ('K1', 'K2', 'K3')),
    max_marks         REAL NOT NULL CHECK (max_marks > 0),
    topic             TEXT
);

CREATE TABLE IF NOT EXISTS student_question_scores (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id       INTEGER NOT NULL REFERENCES assessment_questions(id) ON DELETE CASCADE,
    student_id        TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    marks_obtained    REAL NOT NULL CHECK (marks_obtained >= 0),
    UNIQUE (question_id, student_id)
);

-- Persistent student chat conversations with strict ownership
CREATE TABLE IF NOT EXISTS chat_conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_id        TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    title             TEXT NOT NULL DEFAULT 'New Conversation',
    language          TEXT NOT NULL DEFAULT 'English',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id   INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role              TEXT NOT NULL CHECK (role IN ('student', 'assistant')),
    content           TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);


CREATE INDEX IF NOT EXISTS idx_students_department ON students(department);
CREATE INDEX IF NOT EXISTS idx_interventions_student ON faculty_interventions(student_id);
CREATE INDEX IF NOT EXISTS idx_weekly_student ON weekly_performance(student_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_student ON users(student_id);
CREATE INDEX IF NOT EXISTS idx_assessment_subj ON assessments(subject);
CREATE INDEX IF NOT EXISTS idx_questions_assessment ON assessment_questions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_question_scores_student ON student_question_scores(student_id);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_user ON chat_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_student ON chat_conversations(student_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conv ON chat_messages(conversation_id);

"""


def get_connection(db_path=None):
    """Open a connection with foreign keys enabled and dict-like rows."""
    path = str(db_path or DEFAULT_DB_PATH)
    try:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseError(f"Could not open the database at '{path}': {exc}") from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_path=None):
    """Commit on success, roll back on any error, always close."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Settings stored as key/value text
# --------------------------------------------------------------------------
def get_meta(key, default=None, db_path=None):
    with transaction(db_path) as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key, value, db_path=None):
    with transaction(db_path) as conn:
        _set_meta(conn, key, value)


def _set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


# --------------------------------------------------------------------------
# Initialisation
# --------------------------------------------------------------------------
def _run_migrations(conn):
    """Safely apply schema additions to existing databases without data loss."""
    # Ensure new tables exist if database existed previously
    conn.execute("""
    CREATE TABLE IF NOT EXISTS assessments (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        title             TEXT NOT NULL,
        subject           TEXT NOT NULL,
        assessment_date   TEXT NOT NULL DEFAULT (date('now')),
        pass_marks        REAL DEFAULT 50.0,
        created_at        TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS assessment_questions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id     INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        question_number   INTEGER NOT NULL,
        cognitive_level   TEXT NOT NULL CHECK (cognitive_level IN ('K1', 'K2', 'K3')),
        max_marks         REAL NOT NULL CHECK (max_marks > 0),
        topic             TEXT
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS student_question_scores (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id       INTEGER NOT NULL REFERENCES assessment_questions(id) ON DELETE CASCADE,
        student_id        TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
        marks_obtained    REAL NOT NULL CHECK (marks_obtained >= 0),
        UNIQUE (question_id, student_id)
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chat_conversations (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        student_id        TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
        title             TEXT NOT NULL DEFAULT 'New Conversation',
        language          TEXT NOT NULL DEFAULT 'English',
        created_at        TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id   INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
        role              TEXT NOT NULL CHECK (role IN ('student', 'assistant')),
        content           TEXT NOT NULL,
        created_at        TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)

    # Check users table columns
    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_active" not in user_cols and "users" in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    # Check students table columns
    student_cols = {r["name"] for r in conn.execute("PRAGMA table_info(students)").fetchall()}
    if "mentor_user_id" not in student_cols and "students" in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        conn.execute("ALTER TABLE students ADD COLUMN mentor_user_id INTEGER")
    if "mentor_username" not in student_cols and "students" in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        conn.execute("ALTER TABLE students ADD COLUMN mentor_username TEXT")


def init_db(db_path=None, seed=True):
    """Create missing tables, apply safe migrations, and (once) seed synthetic demo data.

    Safe to call on every app start: existing records are never touched, and
    demo data is seeded only when the database has never been seeded AND has no
    students. Returns {"seeded": <number of demo students inserted>}.
    """
    try:
        conn = get_connection(db_path)
        try:
            conn.executescript(SCHEMA)
            _run_migrations(conn)
        finally:
            conn.close()
        seeded = 0
        if seed:
            with transaction(db_path) as conn:
                already = conn.execute(
                    "SELECT value FROM app_meta WHERE key = 'demo_seeded'"
                ).fetchone()
                count = conn.execute("SELECT COUNT(*) AS n FROM students").fetchone()["n"]
                if not already and count == 0:
                    seeded = _seed_demo_students(conn)
                    _set_meta(conn, "demo_seeded", "1")
                else:
                    # Safely seed sample cognitive assessments for demo students if assessments table is empty
                    _seed_demo_assessments(conn)
        return {"seeded": seeded}
    except sqlite3.Error as exc:
        raise DatabaseError(f"Database initialisation failed: {exc}") from exc



def reset_demo_data(db_path=None):
    """Delete ONLY synthetic demo students (and their related rows), then re-seed.

    Students added or imported by the user are never touched.
    """
    try:
        with transaction(db_path) as conn:
            conn.execute("DELETE FROM students WHERE is_synthetic = 1")
            inserted = _seed_demo_students(conn)
            _set_meta(conn, "demo_seeded", "1")
        return inserted
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not reset demo data: {exc}") from exc


# --------------------------------------------------------------------------
# Synthetic demo data (NOT real students)
# --------------------------------------------------------------------------
SEED_STUDENT_COUNT = 36
DEPARTMENTS = ["Computer Science", "Electronics", "Mechanical", "Civil"]
SUBJECTS = {
    "Computer Science": ["Data Structures", "Algorithms", "Databases", "Operating Systems", "Mathematics"],
    "Electronics": ["Circuit Theory", "Digital Electronics", "Signals", "Electromagnetics", "Mathematics"],
    "Mechanical": ["Thermodynamics", "Fluid Mechanics", "Machine Design", "Manufacturing", "Mathematics"],
    "Civil": ["Structural Analysis", "Surveying", "Concrete Technology", "Geotechnics", "Mathematics"],
}
MENTORS = {
    "Computer Science": "Demo Mentor A",
    "Electronics": "Demo Mentor B",
    "Mechanical": "Demo Mentor C",
    "Civil": "Demo Mentor D",
}
FIRST_NAMES = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Sana", "Vihaan", "Anika",
               "Ishaan", "Tara", "Arjun", "Nisha"]
LAST_NAMES = ["Sharma", "Iyer", "Patel", "Nair", "Reddy", "Khan", "Das", "Menon",
              "Gupta", "Rao", "Verma", "Pillai"]

# profile -> (attendance range, assignment range, academic score range)
PROFILES = {
    "strong":         ((88, 98), (85, 100), (75, 92)),
    "steady":         ((78, 92), (70, 92), (58, 78)),
    "struggling":     ((55, 72), (35, 58), (30, 48)),
    "attendance_gap": ((55, 72), (65, 85), (55, 70)),
    "assignment_gap": ((80, 92), (30, 55), (50, 65)),
    "declining":      ((72, 85), (60, 80), (52, 62)),
}
PROFILE_NAMES = list(PROFILES)
PROFILE_WEIGHTS = [20, 30, 12, 10, 10, 18]


def _clip(value):
    return max(0.0, min(100.0, round(value, 1)))


def _seed_demo_students(conn):
    """Insert deterministic synthetic students. Existing IDs are left alone."""
    rng = random.Random(2026)
    today = dt.date.today()
    inserted = 0
    for i in range(1, SEED_STUDENT_COUNT + 1):
        dept = DEPARTMENTS[i % len(DEPARTMENTS)]
        semester = rng.choice([2, 4, 6])
        profile = rng.choices(PROFILE_NAMES, weights=PROFILE_WEIGHTS)[0]
        att_r, asg_r, score_r = PROFILES[profile]
        attendance = round(rng.uniform(*att_r), 1)
        assignment = round(rng.uniform(*asg_r), 1)
        base = rng.uniform(*score_r)
        subjects = SUBJECTS[dept]
        marks = [int(_clip(base + rng.uniform(-8, 8))) for _ in subjects]
        score = round(sum(marks) / len(marks), 1)
        # Two students deliberately have a missing metric to demo "unavailable" handling.
        att_value = None if i == 7 else attendance
        asg_value = None if i == 19 else assignment

        sid = f"DEMO{i:03d}"
        name = f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {LAST_NAMES[(i * 5) % len(LAST_NAMES)]}"
        cur = conn.execute(
            "INSERT OR IGNORE INTO students (student_id, name, department, semester, attendance_rate, "
            "academic_score, assignment_rate, email, mentor, is_synthetic) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (sid, name, dept, semester, att_value, score, asg_value,
             f"demo{i:03d}@example.edu", MENTORS[dept]),
        )
        if cur.rowcount == 0:
            continue
        inserted += 1
        conn.executemany(
            "INSERT OR IGNORE INTO subject_grades (student_id, subject, marks) VALUES (?,?,?)",
            [(sid, s, m) for s, m in zip(subjects, marks)],
        )
        # History only for some students, so the app shows trends only where they exist.
        if profile == "declining" or i % 2 == 0:
            drift = {"declining": rng.uniform(13, 18), "struggling": rng.uniform(-3, 3)}.get(
                profile, rng.uniform(-6, 3))
            weeks = 6
            rows = []
            for w in range(weeks):
                frac = w / (weeks - 1)
                week_date = (today - dt.timedelta(days=7 * (weeks - 1 - w))).isoformat()
                if w == weeks - 1:
                    rows.append((sid, week_date, att_value, score, asg_value))
                    continue
                s_w = _clip(score + drift * (1 - frac) + rng.uniform(-1.5, 1.5))
                a_w = None if att_value is None else _clip(att_value + drift * 0.3 * (1 - frac) + rng.uniform(-1.5, 1.5))
                g_w = None if asg_value is None else _clip(asg_value + rng.uniform(-3, 3))
                rows.append((sid, week_date, a_w, s_w, g_w))
            conn.executemany(
                "INSERT OR IGNORE INTO weekly_performance (student_id, week_date, attendance_rate, "
                "academic_score, assignment_rate) VALUES (?,?,?,?,?)", rows)

    # Seed demo cognitive assessment for demonstration of K1, K2, K3
    _seed_demo_assessments(conn)
    return inserted


def _seed_demo_assessments(conn):
    """Seed sample assessment with K1, K2, K3 questions and scores for demo students."""
    cur = conn.execute("SELECT COUNT(*) AS c FROM assessments")
    if cur.fetchone()["c"] > 0:
        return

    # Check if we have demo students
    rows = conn.execute("SELECT student_id FROM students WHERE is_synthetic = 1 LIMIT 12").fetchall()
    student_ids = [r["student_id"] for r in rows]
    if not student_ids:
        return

    # Create Midterm Assessment for Mathematics
    cur = conn.execute(
        "INSERT INTO assessments (title, subject, assessment_date, pass_marks) "
        "VALUES ('Midterm Assessment - Mathematics', 'Mathematics', '2026-03-15', 50.0)"
    )
    asm_id = cur.lastrowid

    # Questions: 2 K1 (Remember), 2 K2 (Understand), 2 K3 (Apply)
    questions = [
        (asm_id, 1, 'K1', 10.0, 'Definition of Eigenvalues and Vectors'),
        (asm_id, 2, 'K1', 10.0, 'Standard Derivative Formulas'),
        (asm_id, 3, 'K2', 15.0, 'Interpretation of Matrix Transformations'),
        (asm_id, 4, 'K2', 15.0, 'Concept of Gradient and Directional Derivative'),
        (asm_id, 5, 'K3', 25.0, 'Optimization using Lagrange Multipliers'),
        (asm_id, 6, 'K3', 25.0, 'Solving Linear Systems via Gaussian Elimination'),
    ]
    conn.executemany(
        "INSERT INTO assessment_questions (assessment_id, question_number, cognitive_level, max_marks, topic) "
        "VALUES (?, ?, ?, ?, ?)", questions
    )

    q_rows = conn.execute("SELECT id, cognitive_level, max_marks FROM assessment_questions WHERE assessment_id = ?", (asm_id,)).fetchall()
    
    # Generate realistic marks for demo students
    # K1 high performance (~80%), K2 moderate (~68%), K3 challenging (~54%)
    rng = random.Random(42)
    score_entries = []
    for sid in student_ids:
        for q in q_rows:
            qid = q["id"]
            k_level = q["cognitive_level"]
            max_m = q["max_marks"]
            if k_level == 'K1':
                fraction = rng.uniform(0.65, 0.95)
            elif k_level == 'K2':
                fraction = rng.uniform(0.50, 0.85)
            else: # K3
                fraction = rng.uniform(0.35, 0.75)
            obtained = round(max_m * fraction, 1)
            score_entries.append((qid, sid, obtained))

    conn.executemany(
        "INSERT OR IGNORE INTO student_question_scores (question_id, student_id, marks_obtained) "
        "VALUES (?, ?, ?)", score_entries
    )
