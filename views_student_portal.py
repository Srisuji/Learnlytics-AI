"""Student Portal (DEMO). The selector is NOT authentication."""
import streamlit as st

import components as ui
import data_service as ds
import views_analytics as charts
import views_recommendations as vrec

FRIENDLY = {
    "Low": ("On track", "You are doing well on the measures we track. Keep it up!"),
    "Medium": ("A few areas to focus on", "There are one or two areas where some extra effort could help."),
    "High": ("Extra support recommended", "A mentor can help you build a plan. Reaching out is a good step."),
    "Critical": ("Let's plan support together", "Please talk to your mentor soon. Support is available and plans work."),
    "Insufficient data": ("Some records are missing", "Not enough information is recorded yet to give a picture."),
}


def render(db_path=None):
    ui.page_header(
        "Student Portal (demo)",
        "A student-friendly view of progress and study goals.",
        page_help="This demo portal provides a student-facing view showing current progress, strengths, and personal study goals."
    )
    st.warning("**DEMO PREVIEW ONLY:** The student selector below simulates a student login. In a production deployment, this would be secured with student authentication.")
    df = ds.get_screened_df(db_path)
    if df.empty:
        st.info("**No student records found.** Add student records in the **Student Directory** or import a roster in **Import & Settings** to test this demo portal.")
        return
    chosen = ui.student_picker(df, "portal_student", "Choose demo student to view as:")
    if not chosen:
        st.info("Select a student above to see what their personal portal view looks like.")
        return
    student, screening = ds.screen_one(chosen, db_path)
    if student is None:
        st.warning("That student no longer exists.")
        return

    title, message = FRIENDLY[screening["category"]]
    st.subheader(f"Hello, {student['name'].split()[0]}")
    st.markdown(ui.risk_badge(screening["category"], title), unsafe_allow_html=True)
    st.write(message)
    
    ui.render_why_box(student, screening)

    ui.kpi_row([("Attendance", ui.fmt_pct(student["attendance_rate"]), "Class attendance"),
                ("Academic score", ui.fmt_pct(student["academic_score"]), "Overall marks"),
                ("Assignments", ui.fmt_pct(student["assignment_rate"]), "Submitted work")])

    grades = ds.get_subject_grades_df(chosen, db_path)
    if not grades.empty:
        st.subheader("Subject Marks")
        ui.show_chart(charts.fig_subject_marks(grades), "portal_subjects")
    fig = charts.fig_student_trend(ds.get_history_df([chosen], db_path))
    if fig is not None:
        st.subheader("Your Progress Trend")
        ui.show_chart(fig, "portal_trend")

    st.subheader("Your Study Goals & Next Steps")
    recs, _ = ds.get_recommendations_for_student(chosen, db_path)
    if not recs:
        st.caption("No specific study recommendations are needed right now. Keep up the great work!")
    for r in recs:
        vrec.show_recommendation(chosen, r, db_path, "portal")

