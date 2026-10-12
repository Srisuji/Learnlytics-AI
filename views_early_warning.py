"""Students Needing Support: evidence-based support indicators, review status, and follow-up tracking."""
import datetime as dt

import streamlit as st

import components as ui
import data_service as ds
import risk_engine as risk


def _flag_detail(student_id, db_path):
    student, screening = ds.screen_one(student_id, db_path)
    if student is None:
        return
    st.markdown(f"### {student['name']} (`{student_id}`)")
    st.markdown(ui.risk_badge(screening["category"]) +
                f" &nbsp; Support Score: **{screening['score']}** / 100", unsafe_allow_html=True)
    
    # Plain sentence explaining why this student is shown here
    ui.render_why_box(student, screening)

    st.markdown("**Evidence Breakdown**")
    ui.show_df(ui.evidence_dataframe(screening))
    if screening["reasons"]:
        st.markdown("**Key Observations:**")
        for reason in screening["reasons"]:
            st.write(f"- {reason}")
    if screening["unavailable"]:
        st.caption("ℹ️ Not counted because data is unavailable: " + ", ".join(screening["unavailable"]))
    st.markdown("**Suggested Supportive Actions:**")
    for action in screening["faculty_actions"]:
        st.write(f"- {action}")
    ui.screening_disclaimer()

    status = ds.get_review_status(student_id, db_path)
    c1, c2 = st.columns([3, 1])
    new_status = c1.selectbox(
        "Current review status",
        ds.REVIEW_STATUSES,
        index=ds.REVIEW_STATUSES.index(status),
        key=f"ew_status_{student_id}",
        help="Update where this student stands in the faculty support workflow"
    )
    c2.write("")
    c2.write("")
    if c2.button("Save status", key=f"ew_status_btn_{student_id}", help="Save the updated review status"):
        if ds.set_review_status(student_id, new_status, db_path):
            ui.flash("Review status updated successfully.")
            st.rerun()

    st.markdown("**Record a Faculty Follow-Up**")
    with st.form(f"ew_form_{student_id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        when = c1.date_input("Date of check-in", value=dt.date.today(), key=f"ew_date_{student_id}",
                             help="Date when the conversation or intervention occurred")
        follow = c2.date_input("Next scheduled follow-up", value=dt.date.today() + dt.timedelta(days=14),
                               key=f"ew_follow_{student_id}", help="Target date to review progress")
        concern = st.text_input("Area discussed or concern reviewed *", key=f"ew_concern_{student_id}",
                                help="e.g. Attendance drop in Calculus, incomplete lab assignments")
        action = st.text_area("Supportive action agreed upon *", key=f"ew_action_{student_id}",
                              help="e.g. Paired with peer tutor, agreed to weekly milestone submission")
        note = st.text_area("Notes or initial observations (optional)", key=f"ew_note_{student_id}",
                            help="Any relevant context from the conversation")
        submitted = st.form_submit_button("Save follow-up note", help="Record this intervention")
    if submitted:
        ok, errors = ds.add_intervention(student_id, when, concern, action, follow, note, db_path)
        if ok:
            ui.flash("Follow-up recorded successfully.")
            st.rerun()
        else:
            ui.show_errors(errors)

    history = ds.list_interventions_df(student_id, db_path=db_path)
    if not history.empty:
        st.markdown("**Previous Follow-Up History**")
        table_hist = history[["intervention_date", "concern", "action_taken", "follow_up_date", "status_note"]].rename(
            columns={
                "intervention_date": "Date",
                "concern": "Concern",
                "action_taken": "Action Taken",
                "follow_up_date": "Next Check-in",
                "status_note": "Notes"
            }
        )
        ui.show_df(table_hist)


def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Students Needing Support",
        "Students who may benefit from extra guidance, with the evidence behind each support flag.",
        page_help="Identify students who may be falling behind in attendance, coursework, or exams, and record mentoring follow-ups."
    )
    ui.screening_disclaimer()
    df = ds.get_screened_df(db_path, user=user)

    if df.empty:
        st.info("**No student records yet.** Add students in the **Student Directory** or import a class CSV in **Import & Settings** to begin.")
        return
    tab_flags, tab_queue = st.tabs(["Support Flags", "Follow-Up Queue"])

    with tab_flags:
        fdf = ui.filter_bar(df, "ew", default_categories=["Medium", "High", "Critical"])
        fdf = fdf.sort_values("screening_score", ascending=False)
        st.caption(f"Showing {len(fdf)} student(s) matching current criteria. Ranked with highest support score first.")
        
        # Display friendly support level name in table
        fdf_display = fdf.copy()
        fdf_display["support_level"] = fdf_display["risk_category"].map(lambda c: ui.SUPPORT_LEVEL_LABELS.get(c, c))

        table = fdf_display[["student_id", "name", "department", "support_level", "screening_score",
                             "reasons", "review_status"]].rename(columns={
            "student_id": "Student ID", "name": "Name", "department": "Department",
            "support_level": "Support Level", "screening_score": "Score",
            "reasons": "Key Evidence", "review_status": "Review Status"})
        ui.show_df(table)
        st.divider()
        chosen = ui.student_picker(fdf, "ew_selected", "Select a student to review evidence and log a follow-up")
        if chosen:
            _flag_detail(chosen, db_path)

    with tab_queue:
        queue = ds.follow_up_queue(db_path)
        if queue.empty:
            st.info("**All caught up.** No pending follow-ups are due right now. You can schedule follow-ups on the 'Support Flags' tab.")
        else:
            overdue = int((queue["due"] == "Overdue").sum())
            if overdue > 0:
                st.warning(f"Attention needed: You have **{overdue} overdue follow-up(s)** that need faculty attention.")
            else:
                st.success("All scheduled follow-ups are on track.")
            st.metric("Overdue follow-ups", overdue)
            ui.show_df(queue[["due", "follow_up_date", "student_id", "name", "concern", "action_taken",
                              "review_status"]].rename(columns={
                "due": "Status", "follow_up_date": "Due Date", "student_id": "Student ID", "name": "Name",
                "concern": "Concern", "action_taken": "Action Taken", "review_status": "Review Status"}))

