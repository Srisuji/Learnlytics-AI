"""My Goals: Student view for transparent study suggestions and goal tracking."""
import streamlit as st

import components as ui
import data_service as ds
import recommendations as rec


def render(db_path=None, user=None):
    ds.require_role(user, ("student",))
    student_id = user.get("student_id")
    if not student_id:
        st.error("No student record linked to this account.")
        return

    ui.page_header(
        "My Goals",
        "Transparent study recommendations and personal action milestones.",
        page_help="Here you can review practical study habits tailored to your marks, mark your progress, and set personal learning milestones."
    )

    recs, screening = ds.get_recommendations_for_student(student_id, db_path=db_path, user=user)
    if not recs:
        st.info("No specific goals generated right now. Keep up the consistent effort!")
        return

    st.markdown("### Suggested Learning Milestones")
    st.caption("These steps are designed to help you stay ahead in coursework and prepare effectively for upcoming milestones.")

    for r in recs:
        with st.container(border=True):
            st.markdown(f"#### {r['action']}")
            st.write(f"**Why this helps:** {r['reason']}")
            c1, c2 = st.columns(2)
            c1.markdown(f"**Recommended Timeframe:** {r['timeframe']}")
            c2.markdown(f"**Target Goal:** {r['goal']}")

            cur_status = r["status"]
            new_status = st.selectbox(
                "My Progress Status",
                rec.REC_STATUSES,
                index=rec.REC_STATUSES.index(cur_status),
                key=f"goal_status_{r['key']}",
                help="Update your progress on this goal"
            )
            if new_status != cur_status:
                if ds.track_recommendation(student_id, r, new_status, db_path=db_path, user=user):
                    ui.flash("Goal progress updated.")
                    st.rerun()

    st.write("")
    if st.button("Save all suggestions to my active goal list", key="btn_save_my_goals",
                 help="Add all above milestones to your tracked list"):
        for r in recs:
            ds.track_recommendation(student_id, r, db_path=db_path, user=user)
        ui.flash("Goals saved to your active tracking list.")
        st.rerun()

    tracked = ds.list_tracked_recommendations(student_id, db_path=db_path, user=user)
    if not tracked.empty:
        st.markdown("### My Tracked Goals History")
        ui.show_df(tracked)

    st.caption("Note: These suggestions are rule-based and supportive aids for your own study planning.")
