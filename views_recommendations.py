"""Personalized Study Recommendations (rule-based; works without any AI service)."""
import streamlit as st

import components as ui
import data_service as ds
import recommendations as rec


def show_recommendation(student_id, recommendation, db_path, key_prefix, allow_status=True):
    with st.container(border=True):
        st.markdown(f"**{recommendation['action']}**")
        st.write(f"Why: {recommendation['reason']}")
        c1, c2 = st.columns(2)
        c1.write(f"Time frame: {recommendation['timeframe']}")
        c2.write(f"Goal: {recommendation['goal']}")
        if allow_status:
            cur = recommendation["status"]
            new = st.selectbox("Progress", rec.REC_STATUSES, index=rec.REC_STATUSES.index(cur),
                               key=f"{key_prefix}_status_{student_id}_{recommendation['key']}")
            if new != cur:
                if ds.track_recommendation(student_id, recommendation, new, db_path):
                    ui.flash("Progress saved.")
                    st.rerun()


def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Personalized Recommendations",
        "Practical, actionable next steps tailored to each student's academic and attendance patterns.",
        page_help="View supportive study suggestions generated automatically for each student, and save them as tracked personal goals."
    )
    df = ds.get_screened_df(db_path, user=user)

    if df.empty:
        st.info("**No student records yet.** Add students in the **Student Directory** or upload a class spreadsheet in **Import & Settings** to see study recommendations.")
        return
    fdf = ui.filter_bar(df, "rec")
    chosen = ui.student_picker(fdf, "rec_selected", "Select a student to generate recommendations")
    if not chosen:
        st.info("Select a student above to view suggested study actions and goals.")
        return
    polish = False
    if rec.llm_enabled():
        polish = st.checkbox("Polish wording with the configured AI model (only generic suggestion text "
                             "is sent - never names, IDs or marks)", key="rec_polish")
    recs, screening = ds.get_recommendations_for_student(chosen, db_path, polish_wording=polish)
    if screening is None:
        st.warning("That student no longer exists.")
        return
    student = ds.get_student(chosen, db_path)
    if student:
        ui.render_why_box(student, screening)

    st.markdown(ui.risk_badge(screening["category"]) + f" &nbsp; Support Score: **{screening['score']}** / 100",
                unsafe_allow_html=True)
    for r in recs:
        show_recommendation(chosen, r, db_path, "rec")
    if st.button("Save these as tracked goals", key="rec_track_all", help="Save these recommendations to the student's tracked goals list"):
        for r in recs:
            ds.track_recommendation(chosen, r, db_path=db_path)
        ui.flash("Goals saved successfully. They now appear in this student's tracked goals.")
        st.rerun()
    tracked = ds.list_tracked_recommendations(chosen, db_path)
    if not tracked.empty:
        st.markdown("**Tracked Goals**")
        ui.show_df(tracked)
    st.caption("ℹ️ Recommendations are rule-based, transparent, and supportive. Faculty judgment and mentoring conversations always come first.")

