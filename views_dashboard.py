"""Overview Dashboard: live cohort summary, 4 key cards, and 2 primary charts by default."""
import streamlit as st

import components as ui
import data_service as ds
import views_analytics as charts


def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Overview Dashboard",
        "High-level cohort metrics, key academic charts, and follow-up status at a glance.",
        page_help="This dashboard gives coordinators and faculty a quick overview of student attendance, performance, and students who may need academic support."
    )
    df = ds.get_screened_df(db_path, user=user)

    if df.empty:
        st.info("**No student records found yet.** You can add students individually in the **Student Directory** or import your class roster in **Import & Settings**.")
        return
    if df["is_synthetic"].astype(bool).any():
        st.caption("Includes clearly labelled SYNTHETIC demo data. No real student personal information is shown.")

    fdf = ui.filter_bar(df, "dash", with_category=False)
    if fdf.empty:
        st.warning("No students match the selected department or semester filters. Try clearing the filter choices above.")
        return

    k = ds.compute_kpis(fdf)

    # Simpler screen: exactly 4 KPI cards by default
    ui.kpi_row([
        ("Total Students", k["total_students"], "Enrolled in current view"),
        ("Average Attendance", ui.fmt_pct(k["avg_attendance"]), "Classroom attendance"),
        ("Average Score", ui.fmt_pct(k["avg_score"]), "Exam & coursework marks"),
        ("Need Follow-Up", k["needs_follow_up"], "Awaiting faculty check-in"),
    ])
    st.write("")

    # Support level breakdown row (non-punitive wording)
    counts = k["risk_counts"]
    support_cards = [
        (ui.SUPPORT_LEVEL_LABELS["Low"], counts.get("Low", 0), "On track"),
        (ui.SUPPORT_LEVEL_LABELS["Medium"], counts.get("Medium", 0), "Check-in suggested"),
        (ui.SUPPORT_LEVEL_LABELS["High"], counts.get("High", 0), "Support plan advised"),
        (ui.SUPPORT_LEVEL_LABELS["Critical"], counts.get("Critical", 0), "Urgent support needed"),
        ("Insufficient data", counts.get("Insufficient data", 0), "Missing records"),
    ]
    ui.kpi_row(support_cards)
    st.write("")

    # Default view: exactly 2 primary charts
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Support Levels")
        ui.show_chart(charts.fig_risk_distribution(fdf), "dash_risk")
    with c2:
        st.subheader("Attendance vs Academic Score")
        ui.show_chart(charts.fig_scatter(fdf), "dash_scatter",
                      "Requires students with both attendance and academic score recorded.")

    # More charts inside expander to keep the screen uncluttered
    with st.expander("More charts & distributions", expanded=False):
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Academic Score Distribution")
            ui.show_chart(charts.fig_score_hist(fdf), "dash_score", "No academic scores recorded.")
        with c4:
            st.subheader("Attendance Distribution")
            ui.show_chart(charts.fig_attendance_hist(fdf), "dash_att", "No attendance recorded.")
        st.subheader("Department Comparison")
        ui.show_chart(charts.fig_department_comparison(fdf), "dash_chart_dept")

    # Quick Navigation & Actions Row
    st.write("")
    st.subheader("What to Do Next")
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button("Check Students Needing Support", use_container_width=True, help="Open students who may need academic help"):
            st.session_state["nav_page"] = "Students Needing Support"
            st.rerun()
    with qa2:
        if st.button("Browse Student Roster", use_container_width=True, help="Search and view individual student profiles"):
            st.session_state["nav_page"] = "Student Directory"
            st.rerun()
    with qa3:
        if st.button("Explore Subject & Cognitive Analytics", use_container_width=True, help="See K1-K3 cognitive skills and subject breakdowns"):
            st.session_state["nav_page"] = "Analytics"
            st.rerun()
    with qa4:
        if st.button("Download School Reports", use_container_width=True, help="Download spreadsheets and summary summaries"):
            st.session_state["nav_page"] = "Reports & Exports"
            st.rerun()

    st.write("")
    st.subheader("Recent Faculty Follow-Ups")
    recent = ds.list_interventions_df(limit=5, db_path=db_path)
    if recent.empty:
        st.info("No follow-ups recorded yet. You can log check-in notes in the **Students Needing Support** page.")
    else:
        table_follow = recent[["intervention_date", "student_id", "name", "concern", "action_taken", "follow_up_date"]].rename(
            columns={
                "intervention_date": "Date",
                "student_id": "Student ID",
                "name": "Name",
                "concern": "Concern",
                "action_taken": "Action Taken",
                "follow_up_date": "Next Check-in"
            }
        )
        ui.show_df(table_follow)

