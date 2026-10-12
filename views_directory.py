"""Student Directory and Student Profile: search, filter, add, edit, delete (with confirmation)."""
import streamlit as st

import components as ui
import data_service as ds
import views_analytics as charts


def _metric_input(col, label, key_prefix, default_val=None, help_text=""):
    """Render a number input (0.0 to 100.0) with a 'Not recorded' checkbox."""
    is_missing_init = default_val is None or (isinstance(default_val, float) and default_val != default_val)
    with col:
        not_recorded = st.checkbox(
            f"Not recorded",
            value=is_missing_init,
            key=f"{key_prefix}_nr",
            help=f"Check this if {label.lower()} is currently unknown. It will not be counted as zero."
        )
        val = 0.0 if is_missing_init else float(default_val)
        num = st.number_input(
            label,
            min_value=0.0,
            max_value=100.0,
            value=val,
            step=1.0,
            format="%.1f",
            disabled=not_recorded,
            key=f"{key_prefix}_val",
            help=help_text
        )
        return "" if not_recorded else num


def _form_fields(prefix, defaults=None, lock_id=False, existing_departments=None):
    """Draw the student form fields and return the entered values as a dict."""
    d = defaults or {}
    existing_depts = sorted(list(existing_departments or []))
    if "Computer Science" not in existing_depts and not existing_depts:
        existing_depts = ["Computer Science", "Electronics", "Mechanical", "Civil"]

    c1, c2 = st.columns(2)
    student_id = c1.text_input(
        "Student ID *",
        value=d.get("student_id", ""),
        disabled=lock_id,
        key=f"{prefix}_id",
        help="Unique identifier for the student (e.g. 'STU001'). Cannot contain spaces."
    )
    name = c2.text_input(
        "Full Name *",
        value=d.get("name", ""),
        key=f"{prefix}_name",
        help="Full name of the student"
    )

    c3, c4 = st.columns(2)
    current_dept = d.get("department", "")
    dept_options = existing_depts + ["Add new department..."]
    
    default_idx = 0
    if current_dept in existing_depts:
        default_idx = existing_depts.index(current_dept)

    with c3:
        dept_choice = st.selectbox(
            "Department *",
            dept_options,
            index=default_idx,
            key=f"{prefix}_dept_choice",
            help="Choose from existing departments or select 'Add new' to enter a custom department name"
        )
        if dept_choice == "Add new department...":
            department = st.text_input(
                "Enter new department name *",
                value="" if current_dept in existing_depts else current_dept,
                key=f"{prefix}_new_dept",
                help="Type the department or degree name (e.g. 'Biotechnology')"
            )
        else:
            department = dept_choice

    sem_default = int(d.get("semester")) if d.get("semester") and str(d.get("semester")).isdigit() else 1
    semester = c4.number_input(
        "Semester (1-12) *",
        min_value=1,
        max_value=12,
        value=sem_default,
        step=1,
        key=f"{prefix}_sem",
        help="Current active semester (1 to 12)"
    )

    st.markdown("**Academic & Attendance Metrics (0-100%)**")
    st.caption("Check 'Not recorded' if a metric is not yet available. It will never be counted as a failure.")
    c5, c6, c7 = st.columns(3)
    att = _metric_input(c5, "Attendance %", f"{prefix}_att", d.get("attendance_rate"), "Percentage of classes attended (0-100)")
    score = _metric_input(c6, "Academic score %", f"{prefix}_score", d.get("academic_score"), "Overall grade or exam score percentage (0-100)")
    asg = _metric_input(c7, "Assignment %", f"{prefix}_asg", d.get("assignment_rate"), "Percentage of coursework and assignments submitted (0-100)")

    c8, c9 = st.columns(2)
    email = c8.text_input("Email (optional)", value=d.get("email") or "", key=f"{prefix}_email", help="Institutional or contact email")
    mentor = c9.text_input("Mentor or Advisor (optional)", value=d.get("mentor") or "", key=f"{prefix}_mentor", help="Assigned faculty mentor")

    return {
        "student_id": student_id,
        "name": name,
        "department": department,
        "semester": semester,
        "attendance_rate": att,
        "academic_score": score,
        "assignment_rate": asg,
        "email": email,
        "mentor": mentor,
    }


def _add_student_section(db_path, existing_depts=None):
    with st.expander("Add a new student manually", expanded=False):
        st.write("Fill in the student details below. Fields marked with * are required.")
        with st.form("add_student_form", clear_on_submit=False):
            data = _form_fields("add", existing_departments=existing_depts)
            submitted = st.form_submit_button("Add student", help="Save this new student to the database")
        if submitted:
            ok, errors = ds.add_student(data, db_path)
            if ok:
                ui.flash(f"Success: Student {data['student_id'].strip()} ({data['name'].strip()}) was added successfully.")
                st.rerun()
            else:
                ui.show_errors(errors)


def _profile(student_id, db_path, existing_depts=None):
    student, screening = ds.screen_one(student_id, db_path)
    if student is None:
        st.warning("That student no longer exists.")
        return

    st.markdown(f"### {student['name']}  \n`{student['student_id']}` — {student['department']}, Semester {student['semester']}")
    st.markdown(ui.risk_badge(screening["category"]) +
                f" &nbsp; Support Score: **{screening['score']}** / 100", unsafe_allow_html=True)
    
    # One plain sentence: "Why is this student shown here?"
    ui.render_why_box(student, screening)

    if student["is_synthetic"]:
        st.caption("Demo record: this profile is generated synthetic demonstration data.")

    ui.kpi_row([
        ("Attendance", ui.fmt_pct(student["attendance_rate"]), "Class attendance"),
        ("Academic score", ui.fmt_pct(student["academic_score"]), "Exam / course marks"),
        ("Assignments", ui.fmt_pct(student["assignment_rate"]), "Coursework completion"),
    ])

    st.markdown("**Evidence Breakdown**")
    ui.show_df(ui.evidence_dataframe(screening))
    if screening["reasons"]:
        st.markdown("**Key Observations:**")
        for reason in screening["reasons"]:
            st.write(f"- {reason}")
    if screening["unavailable"]:
        st.caption("Not counted because data is unavailable: " + ", ".join(screening["unavailable"]))
    ui.screening_disclaimer()

    left, right = st.columns(2)
    with left:
        st.markdown("**Subject Marks**")
        grades = ds.get_subject_grades_df(student_id, db_path)
        if grades.empty:
            st.caption("No individual subject marks recorded yet for this student.")
        else:
            ui.show_chart(charts.fig_subject_marks(grades), f"prof_subjects_{student_id}")
    with right:
        st.markdown("**Progress Over Time**")
        history = ds.get_history_df([student_id], db_path)
        fig = charts.fig_student_trend(history)
        if fig is None:
            st.caption("No weekly history recorded yet to show a progress trend.")
        else:
            ui.show_chart(fig, f"prof_trend_{student_id}")

    st.markdown("**Faculty Follow-Ups**")
    follow = ds.list_interventions_df(student_id, db_path=db_path)
    if follow.empty:
        st.info("No follow-ups recorded yet for this student. Use the 'Students Needing Support' page to log a check-in.")
    else:
        ui.show_df(follow[["intervention_date", "concern", "action_taken", "follow_up_date", "status_note"]])

    with st.expander("Edit this student's details"):
        with st.form(f"edit_form_{student_id}"):
            data = _form_fields(f"edit_{student_id}", student, lock_id=True, existing_departments=existing_depts)
            saved = st.form_submit_button("Save changes", help="Update this student's details in the database")
        if saved:
            ok, errors = ds.update_student(student_id, data, db_path)
            if ok:
                ui.flash(f"Success: Details for student {student_id} ({data['name']}) have been updated.")
                st.rerun()
            else:
                ui.show_errors(errors)

    with st.expander("Delete this student"):
        st.warning("Warning: This will permanently delete this student record along with all linked marks, history, follow-ups, and goals.")
        confirm = st.checkbox("Yes, I understand and want to permanently delete this student", key=f"del_confirm_{student_id}")
        if st.button("Delete student permanently", disabled=not confirm, key=f"del_btn_{student_id}", help="Permanently remove student"):
            if ds.delete_student(student_id, db_path):
                ui.flash(f"Student {student_id} was permanently removed.", "warning")
                st.rerun()
            else:
                st.error("Could not delete: the student was not found.")


def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Student Directory",
        "Search, filter, view profiles, and update student information.",
        page_help="Use this directory to search for students, view academic profiles, add new students manually, or update existing details."
    )
    all_students_df = ds.get_screened_df(db_path, user=user)
    existing_depts = sorted(all_students_df["department"].dropna().unique()) if not all_students_df.empty else []
    _add_student_section(db_path, existing_depts)

    if all_students_df.empty:
        st.info("**No students found.** You can add a student manually using the 'Add a new student manually' form above, or upload a class spreadsheet in **Import & Settings**.")
        return

    search = st.text_input("Search by student ID or name", key="dir_search", help="Type a student name or ID to filter the table")
    fdf = ui.filter_bar(all_students_df, "dir")
    fdf = ds.filter_df(fdf, search=search)
    st.caption(f"Showing {len(fdf)} of {len(all_students_df)} student(s).")
    
    # Translate risk_category into friendly Support Level for table display
    fdf_display = fdf.copy()
    fdf_display["support_level"] = fdf_display["risk_category"].map(lambda c: ui.SUPPORT_LEVEL_LABELS.get(c, c))

    table = fdf_display[["student_id", "name", "department", "semester", "attendance_rate", "academic_score",
                         "assignment_rate", "support_level", "review_status"]].rename(columns={
        "student_id": "Student ID", "name": "Name", "department": "Department", "semester": "Semester",
        "attendance_rate": "Attendance %", "academic_score": "Score %", "assignment_rate": "Assignments %",
        "support_level": "Support Level", "review_status": "Review Status"})
    ui.show_df(table)
    st.divider()

    chosen = ui.student_picker(fdf, "dir_selected", "Select a student to open their detailed profile")
    if chosen:
        _profile(chosen, db_path, existing_depts)


