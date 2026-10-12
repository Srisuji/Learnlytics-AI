"""Start Here: Quick onboarding and step-by-step guide for teachers and coordinators."""
import streamlit as st
import components as ui
import data_service as ds


def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Start Here",
        "Welcome to Learnlytics AI! A simple 3-step guide to help you support your students.",
        page_help="New to Learnlytics AI? Follow these three simple steps to add student data, check who needs support, and record interventions."
    )


    st.markdown("""
    This guide walks you through the essential workflows of Learnlytics AI in three easy steps.
    All indicators are supportive flags to help teachers take early action—never automated predictions.
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.markdown("### Step 1: Add or Import Students")
            st.markdown(
                "Bring your student records into the system. You can type in student details one by one "
                "or upload a CSV spreadsheet with attendance and marks."
            )
            st.markdown("**What to do:**")
            st.markdown("- Go to **Student Directory** to add individual students.")
            st.markdown("- Or go to **Import & Settings** to upload an entire class list via CSV.")
            if st.button("Go to Student Directory", key="btn_step1_dir", help="Open the Student Directory page"):
                st.session_state["nav_page"] = "Student Directory"
                st.rerun()
            if st.button("Go to Import & Settings", key="btn_step1_imp", help="Open the Import & Settings page"):
                st.session_state["nav_page"] = "Import & Settings"
                st.rerun()

    with col2:
        with st.container(border=True):
            st.markdown("### Step 2: See Who Needs Support")
            st.markdown(
                "Identify students who might be falling behind in attendance, coursework, or exams. "
                "Learnlytics AI explains the exact reason behind every support flag."
            )
            st.markdown("**What to do:**")
            st.markdown("- Check the **Overview Dashboard** for cohort-wide statistics.")
            st.markdown("- Open **Students Needing Support** to see student flags ranked by urgency.")
            if st.button("Go to Overview Dashboard", key="btn_step2_dash", help="Open the Overview Dashboard"):
                st.session_state["nav_page"] = "Overview Dashboard"
                st.rerun()
            if st.button("Go to Students Needing Support", key="btn_step2_ew", help="Open the Students Needing Support page"):
                st.session_state["nav_page"] = "Students Needing Support"
                st.rerun()

    with col3:
        with st.container(border=True):
            st.markdown("### Step 3: Record a Follow-Up")
            st.markdown(
                "Log your supportive conversations, mentoring check-ins, or tutoring plans so "
                "no student slips through the cracks."
            )
            st.markdown("**What to do:**")
            st.markdown("- Under **Students Needing Support**, select a student to review their evidence.")
            st.markdown("- Fill in the follow-up note and schedule a next check-in date.")
            if st.button("Review Students & Follow-up", key="btn_step3_rec", help="Open Students Needing Support to log an action"):
                st.session_state["nav_page"] = "Students Needing Support"
                st.rerun()

    st.write("")
    with st.expander("Frequently Asked Questions for Teachers & Coordinators", expanded=False):
        st.markdown("""
        - **Is this an AI prediction?**  
          No. Learnlytics AI uses clear, transparent academic guidelines (e.g. attendance below 75% or scores below 50%). It is a decision-support aid for human review, not an automated prediction.
        - **What if a student is missing attendance or marks?**  
          Missing values are marked as *Not recorded* or *Unavailable*. They are **never** treated as failures or zero scores.
        - **Can I export my data?**  
          Yes! Go to **Reports & Exports** anytime to download student lists, department summaries, or follow-up logs in CSV format.
        """)
