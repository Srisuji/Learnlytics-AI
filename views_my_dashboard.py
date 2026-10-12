"""My Dashboard: Staff & Admin personalized dashboard for mentored students and today's tasks."""
import streamlit as st

import components as ui
import data_service as ds
import views_analytics as charts


def render(db_path=None, user=None):
    ds.require_role(user, ("admin", "staff"))
    display_name = user.get("display_name", "")

    ui.page_header(
        "My Dashboard",
        f"Personalized cohort overview for {display_name}.",
        page_help="View students assigned to you as mentor, review upcoming/overdue check-ins, and manage today's action items."
    )

    all_screened = ds.get_screened_df(db_path, user=user)
    if all_screened.empty:
        st.info("No student records found in the system.")
        return

    username = user.get("username", "").strip().lower()
    user_id = user.get("id")

    # Toggle: Show only my mentored students vs Show all students
    col_t1, col_t2 = st.columns([2, 1])
    with col_t1:
        my_students_only = st.toggle(
            f"Show only my mentored students ({display_name} / @{username})",
            value=True,
            key="staff_my_students_toggle",
            help="Toggle between students assigned to you vs the entire school cohort"
        )

    if my_students_only:
        # Stable mapping: check mentor_username or mentor_user_id, with fallback to legacy display_name
        is_my_student = (
            (all_screened["mentor_username"].astype(str).str.strip().str.lower() == username) |
            (all_screened["mentor_user_id"] == user_id) |
            (all_screened["mentor"].astype(str).str.strip().str.lower() == display_name.strip().lower())
        )
        fdf = all_screened[is_my_student]
        st.caption(f"Showing {len(fdf)} students mentored by **{display_name}**.")
    else:
        fdf = all_screened
        st.caption(f"Showing all {len(fdf)} students in the cohort.")

    if fdf.empty and my_students_only:
        st.info(f"You have no students assigned with Mentor username '@{username}' or name '{display_name}' yet. Turn off the toggle above to view all students.")
        return

    # KPIs
    k = ds.compute_kpis(fdf)
    ui.kpi_row([
        ("Students", k["total_students"], "In selected view"),
        ("Average Attendance", ui.fmt_pct(k["avg_attendance"]), "Classroom attendance"),
        ("Average Score", ui.fmt_pct(k["avg_score"]), "Exam marks"),
        ("Needs Follow-Up", k["needs_follow_up"], "Awaiting check-in"),
    ])
    st.write("")

    # Today's Action Items / What to do today
    with st.container(border=True):
        st.markdown("### What to Do Today")
        actions = []
        # Check overdue followups
        all_queue = ds.follow_up_queue(db_path)
        if my_students_only:
            my_ids = set(fdf["student_id"])
            my_queue = all_queue[all_queue["student_id"].isin(my_ids)]
        else:
            my_queue = all_queue

        overdue_items = my_queue[my_queue["due"] == "Overdue"]
        due_today_items = my_queue[my_queue["due"] == "Due today"]
        urgent_students = fdf[fdf["risk_category"].isin(["Critical", "High"])]

        if not overdue_items.empty:
            actions.append(f"**Address {len(overdue_items)} overdue follow-up(s)** scheduled for your students.")
        if not due_today_items.empty:
            actions.append(f"**Complete {len(due_today_items)} follow-up check-in(s)** scheduled for today.")
        if not urgent_students.empty:
            actions.append(f"**Review {len(urgent_students)} student(s)** currently needing support or attention.")
        if not actions:
            actions.append("**All caught up.** No urgent student flags or overdue follow-up check-ins pending today.")

        for act in actions:
            st.markdown(f"- {act}")

    # Two primary charts
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Support Level Breakdown")
        ui.show_chart(charts.fig_risk_distribution(fdf), "staff_dash_risk")
    with c2:
        st.subheader("Attendance vs Academic Score")
        ui.show_chart(charts.fig_scatter(fdf), "staff_dash_scatter")

    # My students needing support table
    st.subheader("Students Needing Support")
    needing_support = fdf[fdf["risk_category"].isin(["Medium", "High", "Critical"])].sort_values("screening_score", ascending=False)
    if needing_support.empty:
        st.success("No students in this view currently require urgent support.")
    else:
        display_tbl = needing_support.copy()
        display_tbl["support_level"] = display_tbl["risk_category"].map(lambda c: ui.SUPPORT_LEVEL_LABELS.get(c, c))
        tbl = display_tbl[["student_id", "name", "department", "support_level", "screening_score", "reasons", "review_status"]].rename(
            columns={
                "student_id": "Student ID", "name": "Name", "department": "Department",
                "support_level": "Support Level", "screening_score": "Score",
                "reasons": "Key Evidence", "review_status": "Review Status"
            }
        )
        ui.show_df(tbl)

    # Follow-up Queue for staff
    st.subheader("Scheduled Follow-Ups")
    if my_queue.empty:
        st.info("No scheduled follow-up check-ins found for these students.")
    else:
        ui.show_df(my_queue[["due", "follow_up_date", "student_id", "name", "concern", "action_taken", "review_status"]].rename(
            columns={
                "due": "Status", "follow_up_date": "Due Date", "student_id": "Student ID", "name": "Name",
                "concern": "Concern", "action_taken": "Action Taken", "review_status": "Review Status"
            }
        ))
