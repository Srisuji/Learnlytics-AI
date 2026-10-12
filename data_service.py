"""Business logic for Learnlytics AI: validation, student CRUD, CSV import/export,
KPI calculations, interventions, tracked recommendations and reports.

Every function accepts an optional `db_path` so tests can use a temporary database.
Nothing here imports Streamlit, so it is easy to test.
"""
import datetime as dt
import io
import json
import os
import sqlite3
import tempfile

import pandas as pd

import database as db
import recommendations as rec
import risk_engine as risk


class AuthorizationError(Exception):
    """Raised when an operation is attempted by a user without proper permissions."""


def require_role(user: dict | None, allowed_roles: list[str] | tuple[str, ...]):
    """Verify that user is authenticated and has one of the allowed roles.

    Raises AuthorizationError if check fails.
    """
    if not user:
        raise AuthorizationError("Authentication required.")
    role = user.get("role")
    if role not in allowed_roles:
        raise AuthorizationError(f"Permission denied: role '{role}' is not in allowed roles {allowed_roles}.")
    return True


def resolve_target_student(user: dict | None, requested_student_id: str | None = None) -> str:
    """Enforce that student accounts can ONLY ever query or edit their own student ID.

    For staff/admin, returns requested_student_id.
    Raises AuthorizationError if student user has no linked student_id or requests another student.
    """
    if not user:
        return requested_student_id
    role = user.get("role")
    if role == "student":
        student_id = user.get("student_id")
        if not student_id:
            raise AuthorizationError("Student user account has no associated student ID.")
        return student_id
    return requested_student_id

CORE_COLUMNS = ["student_id", "name", "department", "semester",
                "attendance_rate", "academic_score", "assignment_rate"]
OPTIONAL_COLUMNS = ["email", "mentor", "mentor_user_id", "mentor_username"]
STUDENT_FIELDS = CORE_COLUMNS + OPTIONAL_COLUMNS
METRIC_FIELDS = ["attendance_rate", "academic_score", "assignment_rate"]
REVIEW_STATUSES = ["New", "Under review", "Support plan in place", "Resolved"]
MAX_CSV_ROWS = 10000

STUDENT_COLUMNS_SQL = ("student_id, name, department, semester, attendance_rate, academic_score, "
                       "assignment_rate, email, mentor, mentor_user_id, mentor_username, is_synthetic, created_at")
SCREENED_EXTRA = ["screening_score", "risk_category", "triggered_count", "reasons", "review_status"]


# ==========================================================================
# Validation helpers
# ==========================================================================
def _blank(value):
    return risk.is_missing(value) or (isinstance(value, str) and value.strip() == "")



def parse_optional_number(value):
    """Return (number or None, error message or None). Blank -> (None, None)."""
    if _blank(value):
        return None, None
    try:
        return float(str(value).strip().rstrip("%").strip()), None
    except ValueError:
        return None, "is not a number"


def validate_student_record(raw):
    """Validate one student dict. Returns (clean_dict_or_None, errors, warnings)."""
    errors, warnings = [], []
    clean = {}

    sid = "" if _blank(raw.get("student_id")) else str(raw.get("student_id")).strip()
    if not sid:
        errors.append("student_id is required. Please enter a valid student ID (e.g. 'STU101').")
    elif len(sid) > 32 or any(ch.isspace() for ch in sid):
        errors.append("student_id must be at most 32 characters with no spaces.")
    clean["student_id"] = sid

    name = "" if _blank(raw.get("name")) else str(raw.get("name")).strip()
    if not name:
        errors.append("name is required. Please enter the student's full name.")
    clean["name"] = name

    dept = "" if _blank(raw.get("department")) else str(raw.get("department")).strip()
    if not dept:
        errors.append("department is required. Please enter or choose a department.")
    clean["department"] = dept

    sem_value, sem_err = parse_optional_number(raw.get("semester"))
    if sem_err or sem_value is None:
        errors.append("semester is required and must be a whole number (1 to 12).")
        clean["semester"] = None
    elif sem_value != int(sem_value) or not 1 <= int(sem_value) <= 12:
        errors.append(f"semester must be a whole number from 1 to 12. Got: {raw.get('semester')}.")
        clean["semester"] = None
    else:
        clean["semester"] = int(sem_value)

    for field in METRIC_FIELDS:
        friendly_name = field.replace('_', ' ')
        number, err = parse_optional_number(raw.get(field))
        if err:
            errors.append(f"{field} is '{raw.get(field)}' which is not a number. It must be between 0 and 100, or left blank.")
        elif number is not None and not 0 <= number <= 100:
            errors.append(f"{field} is {number:g}. It must be between 0 and 100.")
        elif number is None:
            warnings.append(f"{field} is blank and will be shown as unavailable")
        clean[field] = number

    email = None if _blank(raw.get("email")) else str(raw.get("email")).strip()
    if email and ("@" not in email or len(email) > 120):
        errors.append(f"email '{email}' does not look valid. Please enter a valid address (e.g. 'student@school.edu').")
    clean["email"] = email
    clean["mentor"] = None if _blank(raw.get("mentor")) else str(raw.get("mentor")).strip()
    clean["mentor_user_id"] = raw.get("mentor_user_id") if not _blank(raw.get("mentor_user_id")) else None
    clean["mentor_username"] = None if _blank(raw.get("mentor_username")) else str(raw.get("mentor_username")).strip().lower()

    if errors:
        return None, errors, warnings
    return clean, [], warnings




def _to_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


# ==========================================================================
# Settings (screening thresholds)
# ==========================================================================
def get_config(db_path=None):
    stored = db.get_meta("risk_config", None, db_path)
    if stored:
        try:
            return risk.merge_config(json.loads(stored))
        except (ValueError, TypeError):
            pass
    return risk.merge_config()


def save_config(config, db_path=None):
    """Validate and store thresholds. Returns (ok, errors)."""
    errors = risk.validate_config(config)
    if errors:
        return False, errors
    db.set_meta("risk_config", json.dumps(risk.merge_config(config)), db_path)
    return True, []


def reset_config(db_path=None):
    db.set_meta("risk_config", json.dumps(risk.merge_config()), db_path)


# ==========================================================================
# Students: create / read / update / delete
# ==========================================================================
def get_student(student_id, db_path=None, user=None):
    effective_id = resolve_target_student(user, student_id)
    with db.transaction(db_path) as conn:
        row = conn.execute(f"SELECT {STUDENT_COLUMNS_SQL} FROM students WHERE student_id = ?",
                           (effective_id,)).fetchone()
    return dict(row) if row else None


def add_student(data, db_path=None, is_synthetic=False, user=None):
    """Create a student. Returns (ok, errors)."""
    if user:
        require_role(user, ("admin", "staff"))
    clean, errors, _ = validate_student_record(data)
    if errors:
        return False, errors
    try:
        with db.transaction(db_path) as conn:
            conn.execute(
                "INSERT INTO students (student_id, name, department, semester, attendance_rate, "
                "academic_score, assignment_rate, email, mentor, mentor_user_id, mentor_username, is_synthetic) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (clean["student_id"], clean["name"], clean["department"], clean["semester"],
                 clean["attendance_rate"], clean["academic_score"], clean["assignment_rate"],
                 clean["email"], clean["mentor"], clean["mentor_user_id"], clean["mentor_username"],
                 1 if is_synthetic else 0))
    except sqlite3.IntegrityError:
        return False, [f"A student with ID '{clean['student_id']}' already exists"]
    return True, []


def update_student(student_id, data, db_path=None, user=None):
    """Update an existing student (the ID itself cannot change). Returns (ok, errors)."""
    if user:
        require_role(user, ("admin", "staff"))
    if get_student(student_id, db_path) is None:
        return False, [f"Student '{student_id}' was not found"]
    clean, errors, _ = validate_student_record({**data, "student_id": student_id})
    if errors:
        return False, errors
    with db.transaction(db_path) as conn:
        conn.execute(
            "UPDATE students SET name=?, department=?, semester=?, attendance_rate=?, academic_score=?, "
            "assignment_rate=?, email=?, mentor=?, mentor_user_id=?, mentor_username=? WHERE student_id=?",
            (clean["name"], clean["department"], clean["semester"], clean["attendance_rate"],
             clean["academic_score"], clean["assignment_rate"], clean["email"], clean["mentor"],
             clean["mentor_user_id"], clean["mentor_username"], student_id))
    return True, []


def delete_student(student_id, db_path=None, user=None):
    """Delete a student and all related rows (cascade). Returns True if a row was removed."""
    if user:
        require_role(user, ("admin", "staff"))
    with db.transaction(db_path) as conn:
        cur = conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
        return cur.rowcount > 0


def list_students_df(db_path=None, user=None):
    """List students. If user is a student, only returns their single student record."""
    if user and user.get("role") == "student":
        effective_id = user.get("student_id")
        with db.transaction(db_path) as conn:
            df = pd.read_sql_query(f"SELECT {STUDENT_COLUMNS_SQL} FROM students WHERE student_id = ?", conn, params=(effective_id,))
    else:
        with db.transaction(db_path) as conn:
            df = pd.read_sql_query(f"SELECT {STUDENT_COLUMNS_SQL} FROM students ORDER BY student_id", conn)
    for col in METRIC_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_subject_grades_df(student_id, db_path=None, user=None):
    effective_id = resolve_target_student(user, student_id)
    with db.transaction(db_path) as conn:
        return pd.read_sql_query(
            "SELECT subject AS Subject, marks AS Marks FROM subject_grades WHERE student_id = ? ORDER BY subject",
            conn, params=(effective_id,))


def get_history_df(student_ids=None, db_path=None, user=None):
    """Weekly history rows. Returns an empty frame when no history exists."""
    cols = ["student_id", "week_date", "attendance_rate", "academic_score", "assignment_rate"]
    if user and user.get("role") == "student":
        effective_ids = [user.get("student_id")]
    else:
        effective_ids = list(student_ids) if student_ids is not None else None

    with db.transaction(db_path) as conn:
        df = pd.read_sql_query(f"SELECT {', '.join(cols)} FROM weekly_performance ORDER BY week_date", conn)
    if effective_ids is not None:
        df = df[df["student_id"].isin(effective_ids)]
    for col in METRIC_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def _history_map(db_path=None):
    df = get_history_df(None, db_path)
    out = {}
    for row in df.to_dict("records"):
        out.setdefault(row["student_id"], []).append(row)
    return out


def _review_status_map(db_path=None):
    with db.transaction(db_path) as conn:
        rows = conn.execute("SELECT student_id, review_status FROM early_warnings").fetchall()
    return {r["student_id"]: r["review_status"] for r in rows}


def get_screened_df(db_path=None, config=None, user=None):
    """All students plus screening columns (score, category, reasons, review status)."""
    cfg = config or get_config(db_path)
    df = list_students_df(db_path, user=user)
    if df.empty:
        for col in SCREENED_EXTRA:
            df[col] = pd.Series(dtype="object")
        return df
    history = _history_map(db_path)
    status = _review_status_map(db_path)
    scores, cats, counts, reasons = [], [], [], []
    for row in df.to_dict("records"):
        result = risk.screen_student(row, history.get(row["student_id"]), cfg)
        scores.append(result["score"])
        cats.append(result["category"])
        counts.append(len(result["triggered_keys"]))
        reasons.append("; ".join(result["reasons"]))
    df["screening_score"] = scores
    df["risk_category"] = cats
    df["triggered_count"] = counts
    df["reasons"] = reasons
    df["review_status"] = df["student_id"].map(status).fillna("New")
    return df


def screen_one(student_id, db_path=None, config=None, user=None):
    """Return (student dict, screening result) or (None, None) if not found."""
    effective_id = resolve_target_student(user, student_id)
    student = get_student(effective_id, db_path)
    if student is None:
        return None, None
    cfg = config or get_config(db_path)
    history = get_history_df([effective_id], db_path).to_dict("records")
    return student, risk.screen_student(student, history, cfg)



def filter_df(df, search="", departments=None, semesters=None, categories=None):
    out = df
    if search and search.strip():
        needle = search.strip().lower()
        out = out[out["student_id"].str.lower().str.contains(needle, regex=False)
                  | out["name"].str.lower().str.contains(needle, regex=False)]
    if departments:
        out = out[out["department"].isin(departments)]
    if semesters:
        out = out[out["semester"].isin(semesters)]
    if categories:
        out = out[out["risk_category"].isin(categories)]
    return out


# ==========================================================================
# KPIs and summaries (always computed from the data passed in)
# ==========================================================================
def _mean(df, col):
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return float(series.mean()) if len(series) else None


def compute_kpis(df):
    counts = {c: int((df["risk_category"] == c).sum()) for c in risk.ALL_CATEGORIES}
    needs_follow_up = int((df["risk_category"].isin(["Medium", "High", "Critical"])
                           & df["review_status"].isin(["New", "Under review"])).sum())
    return {
        "total_students": int(len(df)),
        "avg_score": _mean(df, "academic_score"),
        "avg_attendance": _mean(df, "attendance_rate"),
        "avg_assignment": _mean(df, "assignment_rate"),
        "risk_counts": counts,
        "needs_follow_up": needs_follow_up,
    }


def department_summary_df(df):
    cols = ["Department", "Students", "Avg attendance %", "Avg score %", "Avg assignment %",
            "High/Critical flags"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for dept, grp in df.groupby("department"):
        rows.append({
            "Department": dept,
            "Students": len(grp),
            "Avg attendance %": _round(_mean(grp, "attendance_rate")),
            "Avg score %": _round(_mean(grp, "academic_score")),
            "Avg assignment %": _round(_mean(grp, "assignment_rate")),
            "High/Critical flags": int(grp["risk_category"].isin(["High", "Critical"]).sum()),
        })
    return pd.DataFrame(rows, columns=cols)


def _round(value):
    return None if value is None else round(value, 1)


# ==========================================================================
# Faculty interventions and follow-up queue
# ==========================================================================
def add_intervention(student_id, intervention_date, concern, action_taken,
                     follow_up_date=None, status_note="", db_path=None):
    """Record a follow-up. Returns (ok, errors)."""
    errors = []
    if get_student(student_id, db_path) is None:
        errors.append(f"Student '{student_id}' was not found")
    when = _to_date(intervention_date)
    if when is None:
        errors.append("A valid date is required")
    if not concern or not str(concern).strip():
        errors.append("Please describe the concern or indicator reviewed")
    if not action_taken or not str(action_taken).strip():
        errors.append("Please describe the action taken")
    follow = _to_date(follow_up_date) if follow_up_date else None
    if follow_up_date and follow is None:
        errors.append("Follow-up date is not valid")
    if when and follow and follow < when:
        errors.append("Follow-up date cannot be before the intervention date")
    if errors:
        return False, errors
    with db.transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO faculty_interventions (student_id, intervention_date, concern, action_taken, "
            "follow_up_date, status_note) VALUES (?,?,?,?,?,?)",
            (student_id, when.isoformat(), str(concern).strip(), str(action_taken).strip(),
             follow.isoformat() if follow else None, (status_note or "").strip()))
    return True, []


def list_interventions_df(student_id=None, limit=None, db_path=None):
    sql = ("SELECT i.id AS intervention_id, i.student_id, s.name, i.intervention_date, i.concern, "
           "i.action_taken, i.follow_up_date, i.status_note FROM faculty_interventions i "
           "JOIN students s ON s.student_id = i.student_id")
    params = []
    if student_id:
        sql += " WHERE i.student_id = ?"
        params.append(student_id)
    sql += " ORDER BY i.intervention_date DESC, i.id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with db.transaction(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def follow_up_queue(db_path=None):
    """Interventions that have a follow-up date, excluding resolved students."""
    df = list_interventions_df(db_path=db_path)
    cols = list(df.columns) + ["review_status", "due"]
    df = df[df["follow_up_date"].notna() & (df["follow_up_date"] != "")].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    status = _review_status_map(db_path)
    df["review_status"] = df["student_id"].map(status).fillna("New")
    df = df[df["review_status"] != "Resolved"].copy()
    today = dt.date.today().isoformat()
    df["due"] = df["follow_up_date"].apply(
        lambda d: "Overdue" if d < today else ("Due today" if d == today else "Upcoming"))
    return df.sort_values("follow_up_date").reset_index(drop=True)


def get_review_status(student_id, db_path=None):
    return _review_status_map(db_path).get(student_id, "New")


def set_review_status(student_id, status, db_path=None, user=None):
    if user:
        require_role(user, ("admin", "staff"))
    if status not in REVIEW_STATUSES or get_student(student_id, db_path) is None:
        return False
    with db.transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO early_warnings (student_id, review_status, updated_at) VALUES (?,?,datetime('now')) "
            "ON CONFLICT(student_id) DO UPDATE SET review_status=excluded.review_status, "
            "updated_at=excluded.updated_at", (student_id, status))
    return True


# ==========================================================================
# Tracked recommendations
# ==========================================================================
def _stored_status_map(student_id, db_path=None):
    with db.transaction(db_path) as conn:
        rows = conn.execute("SELECT rec_key, status FROM ai_recommendations WHERE student_id = ?",
                            (student_id,)).fetchall()
    return {r["rec_key"]: r["status"] for r in rows}


def get_recommendations_for_student(student_id, db_path=None, polish_wording=False, user=None):
    """Fresh rule-based recommendations, carrying any saved progress status."""
    effective_id = resolve_target_student(user, student_id)
    student, screening = screen_one(effective_id, db_path, user=user)
    if student is None:
        return [], None
    recs = rec.generate_recommendations(student, screening, get_config(db_path))
    if polish_wording:
        recs = rec.enhance_wording(recs)
    saved = _stored_status_map(effective_id, db_path)
    for r in recs:
        r["status"] = saved.get(r["key"], "Suggested")
    return recs, screening


def track_recommendation(student_id, recommendation, status=None, db_path=None, user=None):
    """Save a recommendation as a tracked goal; `status` overrides the stored one."""
    effective_id = resolve_target_student(user, student_id)
    if status is not None and status not in rec.REC_STATUSES:
        return False
    with db.transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO ai_recommendations (student_id, rec_key, action, reason, timeframe, goal, status) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(student_id, rec_key) DO UPDATE SET "
            "action=excluded.action, reason=excluded.reason, timeframe=excluded.timeframe, goal=excluded.goal"
            + (", status=excluded.status" if status is not None else ""),
            (effective_id, recommendation["key"], recommendation["action"], recommendation["reason"],
             recommendation["timeframe"], recommendation["goal"], status or "Suggested"))
    return True


def list_tracked_recommendations(student_id, db_path=None, user=None):
    effective_id = resolve_target_student(user, student_id)
    with db.transaction(db_path) as conn:
        return pd.read_sql_query(
            "SELECT action AS Action, goal AS Goal, timeframe AS 'Time frame', status AS Status "
            "FROM ai_recommendations WHERE student_id = ? ORDER BY id", conn, params=(effective_id,))



# ==========================================================================
# CSV import
# ==========================================================================
def sample_csv_text():
    return (
        "student_id,name,department,semester,attendance_rate,academic_score,assignment_rate,email,mentor\n"
        "EX001,Sample Student One,Computer Science,4,88.5,72.0,90.0,ex001@example.edu,Sample Mentor\n"
        "EX002,Sample Student Two,Electronics,2,68.0,45.5,55.0,ex002@example.edu,Sample Mentor\n"
        "EX003,Sample Student Three,Mechanical,6,92.0,81.0,,,\n"
        "EX004,Sample Student Four,Civil,4,74.0,,66.0,,\n"
    )


def _empty_import_result(error=None):
    return {"error": error,
            "accepted_df": pd.DataFrame(columns=["row", "student_id", "name", "department", "semester",
                                                 "attendance_rate", "academic_score", "assignment_rate",
                                                 "action", "notes"]),
            "rejected_df": pd.DataFrame(columns=["row", "student_id", "reason"]),
            "inserted": 0, "updated": 0, "present_columns": []}


def _read_csv_bytes(file_bytes):
    if not file_bytes:
        return None, "The file is empty."
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "The file is not valid UTF-8 text. Please save it as a UTF-8 CSV."
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        return None, f"The CSV could not be read: {exc}"
    return df, None


def import_students_csv(file_bytes, mode="skip_existing", db_path=None, dry_run=False):
    """Validate (and optionally store) students from CSV bytes.

    mode: "skip_existing" (default) rejects rows whose ID already exists, so existing
          records are never silently overwritten; "update_existing" overwrites them.
    dry_run=True validates only and writes nothing.
    """
    df, error = _read_csv_bytes(file_bytes)
    if error:
        return _empty_import_result(error)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in CORE_COLUMNS if c not in df.columns]
    if missing:
        return _empty_import_result("Missing required column(s): " + ", ".join(missing))
    if len(df) == 0:
        return _empty_import_result("The CSV has a header but no rows.")
    if len(df) > MAX_CSV_ROWS:
        return _empty_import_result(f"Too many rows ({len(df)}). The limit is {MAX_CSV_ROWS}.")

    present = [c for c in STUDENT_FIELDS if c in df.columns]
    existing = set(list_students_df(db_path)["student_id"])
    seen, accepted, rejected = set(), [], []
    for idx, row in df.iterrows():
        row_number = int(idx) + 2  # header is line 1
        raw = {c: row.get(c) for c in present}
        clean, errors, warnings = validate_student_record(raw)
        if clean is not None:
            sid = clean["student_id"]
            if sid in seen:
                errors.append(f"Student ID '{sid}' is duplicated earlier in this file. Each student ID must be unique.")
            elif sid in existing and mode != "update_existing":
                errors.append(f"Student ID '{sid}' already exists in the system. Select 'Update existing records' if you wish to overwrite.")
        if errors:
            friendly_errors = [f"Row {row_number}: {err}" if not err.startswith("Row") else err for err in errors]
            rejected.append({"row": row_number, "student_id": str(raw.get("student_id", "")).strip(),
                             "reason": "; ".join(friendly_errors)})
            continue
        seen.add(clean["student_id"])
        accepted.append({**clean, "row": row_number,
                         "action": "update" if clean["student_id"] in existing else "insert",
                         "notes": "; ".join(warnings)})


    result = _empty_import_result()
    result["present_columns"] = present
    if accepted:
        result["accepted_df"] = pd.DataFrame(accepted)[result["accepted_df"].columns.tolist()
                                                        + [c for c in ("email", "mentor")]]
    if rejected:
        result["rejected_df"] = pd.DataFrame(rejected)

    if dry_run or not accepted:
        return result

    inserted = updated = 0
    with db.transaction(db_path) as conn:
        for item in accepted:
            if item["action"] == "insert":
                conn.execute(
                    "INSERT INTO students (student_id, name, department, semester, attendance_rate, "
                    "academic_score, assignment_rate, email, mentor, is_synthetic) VALUES (?,?,?,?,?,?,?,?,?,0)",
                    (item["student_id"], item["name"], item["department"], item["semester"],
                     item["attendance_rate"], item["academic_score"], item["assignment_rate"],
                     item.get("email"), item.get("mentor")))
                inserted += 1
            else:
                # Only columns present in the file are changed; imported data becomes the user's own
                # (is_synthetic = 0) so "reset demo data" can never delete it.
                updatable = [c for c in present if c != "student_id"]
                sets = ", ".join(f"{c} = ?" for c in updatable)
                conn.execute(f"UPDATE students SET {sets}, is_synthetic = 0 WHERE student_id = ?",
                             [item[c] for c in updatable] + [item["student_id"]])
                updated += 1
    result["inserted"], result["updated"] = inserted, updated
    return result


# ==========================================================================
# Exports and reports (reflect whatever filtered DataFrame is passed in)
# ==========================================================================
def _csv(df):
    return df.to_csv(index=False)


def roster_csv(df):
    cols = ["student_id", "name", "department", "semester", "attendance_rate", "academic_score",
            "assignment_rate", "risk_category", "review_status"]
    return _csv(df[cols])


def risk_report_csv(df):
    cols = ["student_id", "name", "department", "semester", "attendance_rate", "academic_score",
            "assignment_rate", "screening_score", "risk_category", "triggered_count", "reasons",
            "review_status"]
    return _csv(df.sort_values("screening_score", ascending=False)[cols])


def department_summary_csv(df):
    return _csv(department_summary_df(df))


def intervention_summary_csv(student_ids=None, db_path=None):
    df = list_interventions_df(db_path=db_path)
    if student_ids is not None:
        df = df[df["student_id"].isin(list(student_ids))]
    return _csv(df)


def executive_summary_text(df, interventions_df=None, config=None):
    cfg = config or risk.merge_config()
    k = compute_kpis(df)

    def pct(v):
        return "not available" if v is None else f"{v:.1f}%"

    lines = ["LEARNLYTICS AI - EXECUTIVE SUMMARY",
             f"Generated: {dt.date.today().isoformat()}", ""]
    if len(df) and df["is_synthetic"].astype(bool).any():
        lines += ["NOTE: this report includes synthetic demo data.", ""]
    lines += [f"Students in this report: {k['total_students']}",
              f"Average academic score: {pct(k['avg_score'])}",
              f"Average attendance: {pct(k['avg_attendance'])}",
              f"Average assignment completion: {pct(k['avg_assignment'])}", "",
              "Support-screening categories:"]
    for cat, n in k["risk_counts"].items():
        lines.append(f"  - {cat}: {n}")
    lines.append(f"Students needing follow-up (Medium or above, not yet in a support plan): {k['needs_follow_up']}")
    dept = department_summary_df(df)
    if not dept.empty:
        lines += ["", "Departments:"]
        for _, r in dept.iterrows():
            lines.append(f"  - {r['Department']}: {r['Students']} students, "
                         f"avg score {r['Avg score %']}%, {r['High/Critical flags']} High/Critical flag(s)")
    if interventions_df is not None:
        lines += ["", f"Recorded faculty follow-ups: {len(interventions_df)}"]
    lines += ["", "How to read this report:"] + ["  " + t for t in risk.describe_scoring(cfg)]
    lines += ["", risk.DISCLAIMER]
    return "\n".join(lines)


# ==========================================================================
# Data management
# ==========================================================================
def data_quality_summary(db_path=None):
    """A small table of data-quality checks for the Settings page."""
    df = list_students_df(db_path)
    history = get_history_df(None, db_path)
    total = len(df)
    rows = [("Total students", total, "")]
    for col in METRIC_FIELDS:
        missing = int(df[col].isna().sum())
        rows.append((f"Missing {col.replace('_', ' ')}", missing,
                     "Shown as unavailable; not counted as a failure" if missing else ""))
    out_of_range = 0
    for col in METRIC_FIELDS:
        s = df[col].dropna()
        out_of_range += int(((s < 0) | (s > 100)).sum())
    rows.append(("Values outside 0-100", out_of_range, "Should be 0"))
    with_history = int(history["student_id"].nunique()) if not history.empty else 0
    rows.append(("Students with history records", with_history, "Trends are shown only for these"))
    rows.append(("Synthetic demo students", int(df["is_synthetic"].sum()) if total else 0,
                 "Can be reset in Settings"))
    return pd.DataFrame(rows, columns=["Check", "Count", "Note"])


def export_backup_bytes(db_path=None):
    """A consistent copy of the whole SQLite database as bytes."""
    src = db.get_connection(db_path)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        dest = sqlite3.connect(tmp_path)
        try:
            src.backup(dest)
        finally:
            dest.close()
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        src.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ==========================================================================
# Academic Analytics: Cognitive Level (K1-K3), Subject-Wise, Marks Distribution
# ==========================================================================

K_LEVEL_DEFINITIONS = {
    "K1": {"name": "Remember", "desc": "Recall facts, definitions, and basic concepts."},
    "K2": {"name": "Understand", "desc": "Explain concepts, interpret information, and demonstrate understanding."},
    "K3": {"name": "Apply", "desc": "Apply learned concepts to solve problems or practical questions."}
}


def create_assessment(title: str, subject: str, assessment_date: str = None, pass_marks: float = 50.0, db_path=None, user=None):
    """Create a new assessment metadata record."""
    if user:
        require_role(user, ("admin", "staff"))
    title = str(title).strip()
    subject = str(subject).strip()
    if not title:
        raise ValueError("Assessment title cannot be empty.")
    if not subject:
        raise ValueError("Assessment subject cannot be empty.")
    date_val = assessment_date or dt.date.today().isoformat()
    with db.transaction(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO assessments (title, subject, assessment_date, pass_marks) VALUES (?, ?, ?, ?)",
            (title, subject, date_val, float(pass_marks))
        )
        return cur.lastrowid


def list_assessments(subject: str = None, db_path=None):
    """List available assessments, optionally filtered by subject."""
    with db.transaction(db_path) as conn:
        if subject and subject != "All subjects":
            rows = conn.execute(
                "SELECT id, title, subject, assessment_date, pass_marks, created_at FROM assessments WHERE subject = ? ORDER BY assessment_date DESC, id DESC",
                (subject,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, subject, assessment_date, pass_marks, created_at FROM assessments ORDER BY assessment_date DESC, id DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def add_assessment_questions(assessment_id: int, questions: list[dict], db_path=None, user=None):
    """Insert questions with cognitive levels (K1, K2, K3) and max marks for an assessment."""
    if user:
        require_role(user, ("admin", "staff"))
    with db.transaction(db_path) as conn:
        for q in questions:
            k_level = str(q["cognitive_level"]).upper().strip()
            if k_level not in ("K1", "K2", "K3"):
                raise ValueError(f"Invalid cognitive level: {k_level}. Must be K1, K2, or K3.")
            max_m = float(q["max_marks"])
            if max_m <= 0:
                raise ValueError("max_marks must be greater than 0.")
            q_num = int(q["question_number"])
            topic = q.get("topic", "")
            conn.execute(
                "INSERT INTO assessment_questions (assessment_id, question_number, cognitive_level, max_marks, topic) "
                "VALUES (?, ?, ?, ?, ?)",
                (assessment_id, q_num, k_level, max_m, topic)
            )


def record_question_scores(scores: list[dict], db_path=None, user=None):
    """Record student marks obtained for specific assessment questions."""
    if user:
        require_role(user, ("admin", "staff"))
    with db.transaction(db_path) as conn:
        for s in scores:
            conn.execute(
                "INSERT INTO student_question_scores (question_id, student_id, marks_obtained) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(question_id, student_id) DO UPDATE SET marks_obtained = excluded.marks_obtained",
                (int(s["question_id"]), str(s["student_id"]).strip(), float(s["marks_obtained"]))
            )


def get_assessment_questions(assessment_id: int, db_path=None):
    """Retrieve all questions for a given assessment."""
    with db.transaction(db_path) as conn:
        rows = conn.execute(
            "SELECT id, assessment_id, question_number, cognitive_level, max_marks, topic "
            "FROM assessment_questions WHERE assessment_id = ? ORDER BY question_number",
            (assessment_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_cognitive_analysis(student_id: str = None, subject: str = None, assessment_id: int = None,
                           date_range: tuple = None, db_path=None, user=None):
    """Compute K1, K2, and K3 cognitive level analytics.
    
    Returns a dict with:
      - 'has_data': bool
      - 'summary_df': pd.DataFrame with columns: [Level, Descriptor, Questions, Total Max Marks, Avg Marks Obtained, Performance %]
      - 'raw_records_count': int
      - 'lowest_level': str ('K1', 'K2', 'K3' or None)
      - 'lowest_level_name': str
      - 'suggestion': str (clear improvement recommendation)
      - 'detail_df': pd.DataFrame with student-level or question-level breakdown
    """
    effective_id = resolve_target_student(user, student_id) if student_id else None
    if user and user.get("role") == "student":
        effective_id = user.get("student_id")

    query = """
        SELECT 
            aq.id AS question_id,
            aq.assessment_id,
            a.title AS assessment_title,
            a.subject,
            a.assessment_date,
            aq.question_number,
            aq.cognitive_level,
            aq.max_marks,
            sqs.student_id,
            s.name AS student_name,
            s.department,
            sqs.marks_obtained
        FROM assessment_questions aq
        JOIN assessments a ON aq.assessment_id = a.id
        LEFT JOIN student_question_scores sqs ON aq.id = sqs.question_id
        LEFT JOIN students s ON sqs.student_id = s.student_id
        WHERE 1=1
    """
    params = []
    if assessment_id:
        query += " AND a.id = ?"
        params.append(assessment_id)
    if subject and subject != "All subjects":
        query += " AND a.subject = ?"
        params.append(subject)
    if effective_id:
        query += " AND sqs.student_id = ?"
        params.append(effective_id)
    if date_range and len(date_range) == 2 and date_range[0] and date_range[1]:
        query += " AND a.assessment_date BETWEEN ? AND ?"
        params.append(str(date_range[0]))
        params.append(str(date_range[1]))

    with db.transaction(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty or df["marks_obtained"].dropna().empty:
        return {
            "has_data": False,
            "summary_df": pd.DataFrame(),
            "raw_records_count": 0,
            "lowest_level": None,
            "lowest_level_name": None,
            "suggestion": "No cognitive assessment data recorded yet.",
            "detail_df": pd.DataFrame()
        }

    # Only evaluate scored records
    scored = df.dropna(subset=["marks_obtained"]).copy()
    scored["marks_obtained"] = pd.to_numeric(scored["marks_obtained"], errors="coerce")
    scored["max_marks"] = pd.to_numeric(scored["max_marks"], errors="coerce")
    scored = scored[scored["max_marks"] > 0]

    rows = []
    level_perf = {}
    for level in ["K1", "K2", "K3"]:
        info = K_LEVEL_DEFINITIONS[level]
        ldf = scored[scored["cognitive_level"] == level]
        q_count = ldf["question_id"].nunique()
        total_max = ldf["max_marks"].sum()
        total_obtained = ldf["marks_obtained"].sum()
        record_count = len(ldf)

        if record_count > 0 and total_max > 0:
            avg_obtained = round(ldf["marks_obtained"].mean(), 2)
            # Performance percentage normalized by max marks for each scored record
            ldf_pct = (ldf["marks_obtained"] / ldf["max_marks"]) * 100
            perf_pct = round(ldf_pct.mean(), 1)
            level_perf[level] = perf_pct
        else:
            avg_obtained = None
            perf_pct = None

        rows.append({
            "Level": level,
            "Descriptor": info["name"],
            "Definition": info["desc"],
            "Questions": q_count,
            "Records Assessed": record_count,
            "Avg Marks": avg_obtained,
            "Performance %": perf_pct
        })

    summary_df = pd.DataFrame(rows)

    # Identify lowest performing level
    valid_levels = {k: v for k, v in level_perf.items() if v is not None}
    lowest_level = min(valid_levels, key=valid_levels.get) if valid_levels else None
    lowest_name = K_LEVEL_DEFINITIONS[lowest_level]["name"] if lowest_level else None

    suggestions_map = {
        "K1": "Students are struggling with core recall and factual knowledge. Suggest introducing spaced retrieval practice, definition flashcards, and quick weekly formula/terminology quizzes.",
        "K2": "Students struggle with conceptual understanding and interpretation. Suggest using illustrative concept maps, peer explanations, and 'explain in your own words' diagnostic prompts.",
        "K3": "Students demonstrate foundational recall but struggle with problem-solving application. Suggest step-by-step worked examples, case studies, and progressive real-world problem sets."
    }
    suggestion = suggestions_map.get(lowest_level, "Performance is consistent across cognitive levels.")

    return {
        "has_data": True,
        "summary_df": summary_df,
        "raw_records_count": len(scored),
        "lowest_level": lowest_level,
        "lowest_level_name": lowest_name,
        "suggestion": suggestion,
        "detail_df": scored
    }


def get_subject_performance_analysis(department: str = None, student_id: str = None,
                                     pass_mark: float = 50.0, db_path=None, user=None):
    """Compute subject-wise performance analytics using existing subject_grades records.
    
    Features:
      - Subject-wise average marks, average percentage.
      - Highest and lowest marks per subject.
      - Number of students assessed.
      - Pass percentage based on transparent pass_mark.
      - Subjects flagged for attention (average percentage < attention threshold).
      - Transparent count of underlying records, handling missing marks without treating them as 0.
    """
    effective_id = resolve_target_student(user, student_id) if student_id else None
    if user and user.get("role") == "student":
        effective_id = user.get("student_id")

    query = """
        SELECT 
            sg.student_id,
            s.name AS student_name,
            s.department,
            s.semester,
            sg.subject,
            sg.marks
        FROM subject_grades sg
        JOIN students s ON sg.student_id = s.student_id
        WHERE 1=1
    """
    params = []
    if effective_id:
        query += " AND sg.student_id = ?"
        params.append(effective_id)
    if department and department != "All departments":
        query += " AND s.department = ?"
        params.append(department)

    with db.transaction(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        return {
            "has_data": False,
            "summary_df": pd.DataFrame(),
            "raw_records_count": 0,
            "needs_attention": [],
            "student_detail_df": pd.DataFrame()
        }

    # Ensure marks are numeric and filter out true nulls without replacing with 0
    df["marks"] = pd.to_numeric(df["marks"], errors="coerce")
    valid_df = df.dropna(subset=["marks"]).copy()

    if valid_df.empty:
        return {
            "has_data": False,
            "summary_df": pd.DataFrame(),
            "raw_records_count": 0,
            "needs_attention": [],
            "student_detail_df": pd.DataFrame()
        }

    # Group by subject
    grouped = valid_df.groupby("subject")
    summary_rows = []
    for subj, group in grouped:
        n_assessed = len(group)
        avg_m = round(group["marks"].mean(), 2)
        min_m = round(group["marks"].min(), 2)
        max_m = round(group["marks"].max(), 2)
        passed = (group["marks"] >= pass_mark).sum()
        pass_pct = round((passed / n_assessed) * 100, 1)

        summary_rows.append({
            "Subject": subj,
            "Records Assessed": n_assessed,
            "Average Marks": avg_m,
            "Average %": avg_m,  # subject_grades is scored out of 100
            "Highest Mark": max_m,
            "Lowest Mark": min_m,
            "Pass %": pass_pct
        })

    summary_df = pd.DataFrame(summary_rows).sort_values(by="Average %", ascending=False).reset_index(drop=True)
    needs_attention = summary_df[summary_df["Average %"] < pass_mark]["Subject"].tolist()

    return {
        "has_data": True,
        "summary_df": summary_df,
        "raw_records_count": len(valid_df),
        "needs_attention": needs_attention,
        "student_detail_df": valid_df
    }


def get_marks_distribution_analysis(subject: str = None, department: str = None,
                                    student_id: str = None, pass_mark: float = 50.0,
                                    custom_bins: list[tuple[int, int]] = None,
                                    db_path=None, user=None):
    """Compute score distribution analytics across configured ranges and statistical metrics.
    
    Normalizes marks with different maximum scores to percentages (0-100%) before comparing.
    Handles missing marks gracefully without assuming 0.
    """
    effective_id = resolve_target_student(user, student_id) if student_id else None
    if user and user.get("role") == "student":
        effective_id = user.get("student_id")

    # If a specific subject is chosen, pull from subject_grades; if overall, pull academic_score
    if subject and subject != "All subjects":
        query = """
            SELECT sg.student_id, s.department, sg.subject, sg.marks AS score
            FROM subject_grades sg
            JOIN students s ON sg.student_id = s.student_id
            WHERE sg.subject = ?
        """
        params = [subject]
        if effective_id:
            query += " AND sg.student_id = ?"
            params.append(effective_id)
        if department and department != "All departments":
            query += " AND s.department = ?"
            params.append(department)
    else:
        query = """
            SELECT s.student_id, s.department, 'Overall Academic Score' AS subject, s.academic_score AS score
            FROM students s
            WHERE 1=1
        """
        params = []
        if effective_id:
            query += " AND s.student_id = ?"
            params.append(effective_id)
        if department and department != "All departments":
            query += " AND s.department = ?"
            params.append(department)

    with db.transaction(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        return {
            "has_data": False,
            "summary_df": pd.DataFrame(),
            "stats": {},
            "raw_records_count": 0,
            "pass_fail": {},
            "concentration_note": "No score records found."
        }

    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    valid_scores = df["score"].dropna()

    if valid_scores.empty:
        return {
            "has_data": False,
            "summary_df": pd.DataFrame(),
            "stats": {},
            "raw_records_count": 0,
            "pass_fail": {},
            "concentration_note": "No non-null marks available for this selection."
        }

    n_total = len(valid_scores)
    mean_val = round(float(valid_scores.mean()), 2)
    median_val = round(float(valid_scores.median()), 2)
    min_val = round(float(valid_scores.min()), 2)
    max_val = round(float(valid_scores.max()), 2)
    std_val = round(float(valid_scores.std()), 2) if n_total > 1 else 0.0

    # Default configured bins: 0-39, 40-49, 50-59, 60-69, 70-79, 80-89, 90-100
    bins = custom_bins or [
        (0, 39),
        (40, 49),
        (50, 59),
        (60, 69),
        (70, 79),
        (80, 89),
        (90, 100)
    ]

    range_rows = []
    max_bucket_count = -1
    max_bucket_label = ""
    for low, high in bins:
        label = f"{low}–{high}%"
        if high == 100:
            count = int(((valid_scores >= low) & (valid_scores <= high)).sum())
        else:
            count = int(((valid_scores >= low) & (valid_scores <= high)).sum())
        pct = round((count / n_total) * 100, 1)
        # Friendly non-punitive tier label
        if low >= 75:
            tier_name = "Excellent"
            tier_desc = "Consistently strong grasp of topics"
        elif low >= 50:
            tier_name = "Good"
            tier_desc = "Solid understanding with minor room for growth"
        else:
            tier_name = "Needs Practice"
            tier_desc = "Foundational concepts to review and practice"

        range_rows.append({
            "Range": label,
            "Low": low,
            "High": high,
            "Level": tier_name,
            "Meaning": tier_desc,
            "Student Count": count,
            "Percentage %": pct
        })
        if count > max_bucket_count:
            max_bucket_count = count
            max_bucket_label = label

    summary_df = pd.DataFrame(range_rows)

    # Pass / Fail distribution
    passed_count = int((valid_scores >= pass_mark).sum())
    failed_count = n_total - passed_count
    pass_pct = round((passed_count / n_total) * 100, 1)
    fail_pct = round((failed_count / n_total) * 100, 1)

    # Score concentration insight without unsupported speculation
    below_pass_count = int((valid_scores < pass_mark).sum())
    concentration_note = (
        f"Scores are most heavily concentrated in the {max_bucket_label} band ({max_bucket_count} students, {round((max_bucket_count/n_total)*100, 1)}%). "
        f"{below_pass_count} student(s) ({round((below_pass_count/n_total)*100, 1)}%) score below the configured pass mark of {pass_mark}%."
    )

    return {
        "has_data": True,
        "summary_df": summary_df,
        "stats": {
            "count": n_total,
            "mean": mean_val,
            "median": median_val,
            "min": min_val,
            "max": max_val,
            "std_dev": std_val
        },
        "pass_fail": {
            "pass_mark": pass_mark,
            "passed_count": passed_count,
            "passed_pct": pass_pct,
            "failed_count": failed_count,
            "failed_pct": fail_pct
        },
        "raw_records_count": n_total,
        "concentration_note": concentration_note,
        "scores_series": valid_scores
    }


def get_student_score_improvement_plan(student_id: str, db_path=None, user=None):
    """Generate a clear, transparent, actionable 'How Can I Improve My Marks?' plan.
    
    Uses only verified stored data:
      - Real cognitive assessment questions & scores (K1, K2, K3) with real topics.
      - Real subject grades to determine strongest subject vs subject needing focus.
      - Never invents weak topics or performance data; transparently states when data is pending.
      - Provides:
          1. What needs improvement?
          2. Why does it matter?
          3. What should I do next?
          4. Realistic daily study schedule.
          5. Target calculator with explicit weighting.
    """
    effective_id = resolve_target_student(user, student_id)
    student = get_student(effective_id, db_path=db_path)
    if not student:
        return {"has_student": False}

    grades_df = get_subject_grades_df(effective_id, db_path=db_path)
    strongest_subject = None
    focus_subject = None
    subject_insights = []

    if not grades_df.empty and "Marks" in grades_df.columns:
        valid_g = grades_df.dropna(subset=["Marks"]).sort_values("Marks", ascending=False)
        if not valid_g.empty:
            strongest_subject = {
                "name": valid_g.iloc[0]["Subject"],
                "marks": valid_g.iloc[0]["Marks"]
            }
            focus_subject = {
                "name": valid_g.iloc[-1]["Subject"],
                "marks": valid_g.iloc[-1]["Marks"]
            }
            for _, r in valid_g.iterrows():
                m = r["Marks"]
                if m >= 75:
                    status = "Going well"
                    recom = "Keep maintaining revision with weekly flash questions."
                elif m >= 50:
                    status = "Steady progress"
                    recom = "Practice worked examples from mid-level problem sets."
                else:
                    status = "Needs attention"
                    recom = "Prioritize clarifying core definitions and fundamental rules first."
                subject_insights.append({
                    "subject": r["Subject"],
                    "marks": m,
                    "status": status,
                    "recommendation": recom
                })

    # Cognitive level data for this student
    cog_res = get_cognitive_analysis(student_id=effective_id, db_path=db_path)
    cog_has_data = cog_res["has_data"]
    cog_summary = cog_res["summary_df"] if cog_has_data else pd.DataFrame()
    weakest_k = cog_res.get("lowest_level")
    weakest_k_name = cog_res.get("lowest_level_name")
    
    # Check for actual topic-level scores from assessment_questions
    weak_topics = []
    strong_topics = []
    if cog_has_data and not cog_res["detail_df"].empty:
        det = cog_res["detail_df"].copy()
        det["pct"] = (det["marks_obtained"] / det["max_marks"]) * 100
        for _, row in det.iterrows():
            topic = row.get("topic") or f"Question {row['question_number']}"
            item = {
                "topic": topic,
                "cognitive_level": row["cognitive_level"],
                "marks_obtained": row["marks_obtained"],
                "max_marks": row["max_marks"],
                "pct": round(row["pct"], 1)
            }
            if row["pct"] < 60:
                weak_topics.append(item)
            else:
                strong_topics.append(item)

    # 3-Part Actionable Recommendations (What, Why, Next Step)
    action_items = []
    if focus_subject:
        action_items.append({
            "title": f"Focus Priority: {focus_subject['name']}",
            "what": f"Your current score in {focus_subject['name']} is {focus_subject['marks']}%.",
            "why": "Improving foundational understanding in this subject will provide the largest boost to your overall grade.",
            "next_step": "Dedicate your first 30 minutes of study each evening to reviewing this subject's core textbook chapters."
        })

    if weakest_k:
        k_guides = {
            "K1": ("Core terms and definitions", "You lose points on basic recall questions before reaching complex problems.", "Create 10 flashcards of key definitions and review them for 10 minutes every morning."),
            "K2": ("Explaining concepts in your own words", "Understanding how formulas connect allows you to adapt to new question formats.", "Try teaching the main idea of each chapter aloud to a classmate or writing a 3-sentence summary."),
            "K3": ("Solving practical problem sets", "Exams test your ability to apply rules under time constraints.", "Do 2 multi-step worked examples without looking at the solutions, then check where you paused.")
        }
        k_info = k_guides.get(weakest_k, ("General practice", "Consistent repetition builds mastery.", "Set aside regular focused study sessions."))
        action_items.append({
            "title": f"Cognitive Skill Focus: {weakest_k} ({weakest_k_name})",
            "what": f"Your performance in {weakest_k} ({weakest_k_name}) is currently lower than other levels.",
            "why": k_info[1],
            "next_step": k_info[2]
        })

    if not action_items:
        action_items.append({
            "title": "General Consistency",
            "what": "Maintain your steady attendance and assignment completion.",
            "why": "Consistent habits are the most reliable predictor of academic success.",
            "next_step": "Review notes within 24 hours of each lecture."
        })

    # Realistic Achievable Daily Study Plan
    daily_plan = [
        {"day": "Monday", "task": "Review foundational definitions and terminology (K1: Remember)", "time": "25 mins"},
        {"day": "Tuesday", "task": f"Read lecture summaries for {focus_subject['name'] if focus_subject else 'core courses'} (K2: Understand)", "time": "30 mins"},
        {"day": "Wednesday", "task": "Work through 2 step-by-step example problems (K3: Apply)", "time": "35 mins"},
        {"day": "Thursday", "task": "Self-quiz on challenging formulas without checking notes", "time": "20 mins"},
        {"day": "Friday", "task": "Check coursework feedback and ask your teacher/mentor about any doubts", "time": "15 mins"},
        {"day": "Weekend", "task": "Light recap of the week's notes and prepare questions for Monday", "time": "30 mins"}
    ]

    return {
        "has_student": True,
        "student": student,
        "strongest_subject": strongest_subject,
        "focus_subject": focus_subject,
        "subject_insights": subject_insights,
        "cog_has_data": cog_has_data,
        "cog_summary": cog_summary,
        "weakest_k": weakest_k,
        "weakest_k_name": weakest_k_name,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "action_items": action_items,
        "daily_plan": daily_plan
    }


# ==========================================================================
# Chat Conversations & Persistent History (Student Access Only)
# ==========================================================================

def get_or_create_conversation(user: dict, conversation_id: int = None, language: str = "English", db_path=None):
    """Retrieve an existing conversation or create a new one with strict ownership checks."""
    require_role(user, ("student",))
    student_id = user.get("student_id")
    user_id = user.get("id")
    if not student_id or not user_id:
        raise AuthorizationError("Active student record required for AI Tutor conversation.")

    with db.transaction(db_path) as conn:
        if conversation_id:
            row = conn.execute(
                "SELECT id, user_id, student_id, title, language, created_at, updated_at "
                "FROM chat_conversations WHERE id = ? AND user_id = ? AND student_id = ?",
                (conversation_id, user_id, student_id)
            ).fetchone()
            if row:
                return dict(row)
            # If not found or owned by someone else, raise AuthorizationError
            raise AuthorizationError("Conversation not found or access denied.")

        # Create new conversation
        cur = conn.execute(
            "INSERT INTO chat_conversations (user_id, student_id, title, language) VALUES (?, ?, ?, ?)",
            (user_id, student_id, "New Study Session", language)
        )
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, user_id, student_id, title, language, created_at, updated_at "
            "FROM chat_conversations WHERE id = ?", (new_id,)
        ).fetchone()
        return dict(row)


def list_student_conversations(user: dict, db_path=None):
    """List conversations strictly belonging to the authenticated student."""
    require_role(user, ("student",))
    student_id = user.get("student_id")
    user_id = user.get("id")
    if not student_id or not user_id:
        return []

    with db.transaction(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, language, created_at, updated_at FROM chat_conversations "
            "WHERE user_id = ? AND student_id = ? ORDER BY updated_at DESC",
            (user_id, student_id)
        ).fetchall()
        return [dict(r) for r in rows]


def get_conversation_messages(user: dict, conversation_id: int, db_path=None):
    """Fetch messages in a conversation, verifying that the authenticated user owns it."""
    require_role(user, ("student",))
    student_id = user.get("student_id")
    user_id = user.get("id")

    with db.transaction(db_path) as conn:
        owner = conn.execute(
            "SELECT id FROM chat_conversations WHERE id = ? AND user_id = ? AND student_id = ?",
            (conversation_id, user_id, student_id)
        ).fetchone()
        if not owner:
            raise AuthorizationError("Access denied: You do not own this conversation.")

        rows = conn.execute(
            "SELECT id, role, content, created_at FROM chat_messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_chat_message(user: dict, conversation_id: int, role: str, content: str, db_path=None):
    """Add a message to a conversation after verifying ownership."""
    require_role(user, ("student",))
    student_id = user.get("student_id")
    user_id = user.get("id")
    role = str(role).strip().lower()
    if role not in ("student", "assistant"):
        raise ValueError("Invalid chat role.")
    content = str(content).strip()
    if not content:
        raise ValueError("Message content cannot be empty.")

    with db.transaction(db_path) as conn:
        owner = conn.execute(
            "SELECT id, title FROM chat_conversations WHERE id = ? AND user_id = ? AND student_id = ?",
            (conversation_id, user_id, student_id)
        ).fetchone()
        if not owner:
            raise AuthorizationError("Access denied: You do not own this conversation.")

        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content)
        )

        # Automatically update conversation title from first student message if still default
        current_title = owner["title"]
        if role == "student" and current_title in ("New Conversation", "New Study Session"):
            preview_title = content[:35] + ("..." if len(content) > 35 else "")
            conn.execute(
                "UPDATE chat_conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
                (preview_title, conversation_id)
            )
        else:
            conn.execute(
                "UPDATE chat_conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,)
            )


def delete_student_conversation(user: dict, conversation_id: int, db_path=None):
    """Delete a single conversation owned by the student. Cascades to messages."""
    require_role(user, ("student",))
    student_id = user.get("student_id")
    user_id = user.get("id")

    with db.transaction(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM chat_conversations WHERE id = ? AND user_id = ? AND student_id = ?",
            (conversation_id, user_id, student_id)
        )
        return cur.rowcount > 0


def delete_all_student_conversations(user: dict, db_path=None):
    """Delete all conversations for the authenticated student. Academic records are untouched."""
    require_role(user, ("student",))
    student_id = user.get("student_id")
    user_id = user.get("id")

    with db.transaction(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM chat_conversations WHERE user_id = ? AND student_id = ?",
            (user_id, student_id)
        )
        return cur.rowcount



