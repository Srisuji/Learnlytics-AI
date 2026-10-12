"""My Progress: Student self-analysis view in friendly, supportive, non-punitive language.

Goal: "Understand your performance at a glance and know exactly what to do next."

Structured in 6 clear, accessible sections:
1. Your Progress (Standing, at-a-glance explanation, attendance, score, coursework KPIs)
2. K1, K2 and K3 Learning Skills
3. Subject Performance
4. Marks Distribution
5. How Can I Improve My Marks?
6. Marks Target Calculator
"""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

import components as ui
import data_service as ds
import views_analytics as charts

FRIENDLY_STATUS = {
    "Low": ("On Track", "You are meeting the benchmark targets across attendance (>= 75%), coursework marks (>= 50%), and assignment completion (>= 60%). Keep up the consistent work."),
    "Medium": ("A Few Areas to Focus On", "You are making steady progress overall, but one or two areas (such as attendance, marks, or assignments) need extra attention to stay on schedule."),
    "High": ("Extra Support Recommended", "We recommend connecting with your mentor or teacher to build a personalized study plan. Reaching out is a positive and proactive step."),
    "Critical": ("Let's Plan Support Together", "Please reach out to your mentor soon. Faculty support, tutoring, and milestone plans are here to help you succeed."),
    "Insufficient data": ("Records Being Updated", "Some course records are not yet entered. Check back soon as attendance and marks are updated."),
}


def render(db_path=None, user=None):
    ds.require_role(user, ("student",))
    student_id = user.get("student_id")
    if not student_id:
        st.error("No student record is associated with your account. Please contact your coordinator.")
        return

    student, screening = ds.screen_one(student_id, db_path, user=user)
    if student is None:
        st.warning("Your student record could not be found.")
        return

    first_name = student["name"].split()[0] if student.get("name") else "there"
    ui.page_header(
        "My Progress",
        f"Welcome back, {first_name}! Understand your performance at a glance and know exactly what to do next.",
        page_help="Track your attendance, subject marks, cognitive skills, and personalized study recommendations in one place."
    )

    cat = screening["category"]
    title, message = FRIENDLY_STATUS.get(cat, ("On Track", "Keep up the great work."))

    # =========================================================================
    # SECTION 1: Your Progress
    # =========================================================================
    with st.container(border=True):
        st.markdown(f"### Current Standing: {ui.risk_badge(cat, title)}", unsafe_allow_html=True)
        st.write(message)
        # Dynamic, student-facing at-a-glance summary with real numbers
        ui.render_why_box(student, screening, is_self=True)

    # Three primary KPI cards
    ui.kpi_row([
        ("Class Attendance", ui.fmt_pct(student["attendance_rate"]), "Target: ≥ 75% attendance"),
        ("Academic Score", ui.fmt_pct(student["academic_score"]), "Target: ≥ 50% course score"),
        ("Assignments Done", ui.fmt_pct(student["assignment_rate"]), "Target: ≥ 60% completion"),
    ])
    st.write("")

    # Progress Over Time trend (if history exists)
    history = ds.get_history_df([student_id], db_path, user=user)
    fig_hist = charts.fig_student_trend(history)
    if fig_hist is not None:
        with st.expander("My Progress Over Time (Weekly Trends)", expanded=False):
            st.caption("Track whether your weekly performance is improving or holding steady.")
            ui.show_chart(fig_hist, "student_trend")

    # Anonymous Class Average Comparison
    all_students = ds.list_students_df(db_path)
    dept_cohort = all_students[all_students["department"] == student["department"]]
    cohort = dept_cohort if not dept_cohort.empty else all_students
    avg_att = cohort["attendance_rate"].dropna().mean()
    avg_score = cohort["academic_score"].dropna().mean()
    avg_asg = cohort["assignment_rate"].dropna().mean()

    with st.expander("Compare with Anonymous Class Averages", expanded=False):
        st.caption(f"Comparison with the average of classmates in {student['department']}. All individual student marks remain private.")
        comparison_data = [
            {"Metric": "Attendance (%)", "Your Value": student["attendance_rate"] or 0, "Class Average": round(avg_att, 1) if avg_att else 0},
            {"Metric": "Academic Score (%)", "Your Value": student["academic_score"] or 0, "Class Average": round(avg_score, 1) if avg_score else 0},
            {"Metric": "Assignments (%)", "Your Value": student["assignment_rate"] or 0, "Class Average": round(avg_asg, 1) if avg_asg else 0},
        ]
        comp_df = pd.DataFrame(comparison_data).melt(id_vars="Metric", var_name="Type", value_name="Percentage")
        fig_comp = px.bar(comp_df, x="Metric", y="Percentage", color="Type", barmode="group",
                          color_discrete_map={"Your Value": "#00E5FF", "Class Average": "#38BDF8"})
        fig_comp.update_layout(yaxis_range=[0, 100], margin=dict(t=20, b=10))
        ui.show_chart(fig_comp, "student_comp_chart")

    # Retrieve score improvement plan data
    plan = ds.get_student_score_improvement_plan(student_id, db_path=db_path, user=user)

    # =========================================================================
    # SECTION 2: K1, K2 and K3 Learning Skills
    # =========================================================================
    st.markdown("---")
    st.markdown("## K1, K2 and K3 Learning Skills")
    st.markdown(
        "See how well you handle different types of questions:<br>"
        "• **K1 — Remember (Facts):** Can you recall key definitions, terms, and core rules?<br>"
        "• **K2 — Understand (Concepts):** Can you explain the main ideas in your own words?<br>"
        "• **K3 — Apply (Problems):** Can you use what you learned to solve practical exercises?",
        unsafe_allow_html=True
    )

    cog_data = ds.get_cognitive_analysis(student_id=student_id, db_path=db_path, user=user)
    if not cog_data["has_data"]:
        st.info("Cognitive assessment scores (K1–K3) have not been recorded for your tests yet. Check back after your next graded assessment.")
    else:
        summary_cog = cog_data["summary_df"]
        c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
        kpi_cols = {"K1": c_kpi1, "K2": c_kpi2, "K3": c_kpi3}
        for _, r in summary_cog.iterrows():
            col = kpi_cols.get(r["Level"])
            if col:
                val = r["Performance %"]
                val_text = f"{val:.1f}%" if val is not None else "Not assessed"
                status_txt = "Going well" if val and val >= 70 else ("Needs practice" if val and val < 50 else "Steady")
                col.metric(f"{r['Level']} — {r['Descriptor']}", val_text, status_txt)

        col_cchart, col_ctext = st.columns([1.3, 1.0])
        with col_cchart:
            fig_cog = charts.fig_cognitive_levels(summary_cog)
            ui.show_chart(fig_cog, "student_cog_chart")
        with col_ctext:
            st.markdown("#### What This Means")
            best_row = summary_cog.loc[summary_cog["Performance %"].idxmax()]
            st.write(
                f"- **Going Well:** Your highest performance is in **{best_row['Level']} — {best_row['Descriptor']}** ({best_row['Performance %']:.1f}%)."
            )
            if cog_data["lowest_level"]:
                low_lvl = cog_data["lowest_level"]
                low_name = cog_data["lowest_level_name"]
                st.write(f"- **Needs More Practice:** **{low_lvl} ({low_name})**.")
                st.markdown(
                    f"<div style='background: rgba(0, 166, 255, 0.1); border-left: 3px solid #00A6FF; padding: 10px; border-radius: 6px;'>"
                    f"<strong>Practical Tip:</strong> {cog_data['suggestion']}</div>",
                    unsafe_allow_html=True
                )

    # =========================================================================
    # SECTION 3: Subject Performance
    # =========================================================================
    st.markdown("---")
    st.markdown("## Subject Performance")
    st.markdown("Review your marks across every enrolled course and discover which subjects are your strongest.")
    grades = ds.get_subject_grades_df(student_id, db_path, user=user)
    if grades.empty:
        st.info("No individual subject grades have been recorded yet for this semester.")
    else:
        # Quick summary cards
        if plan["strongest_subject"] and plan["focus_subject"]:
            s_top, s_low = st.columns(2)
            s_top.metric("Strongest Subject", plan["strongest_subject"]["name"], f"{plan['strongest_subject']['marks']}% (Going well)")
            s_low.metric("Subject Needing Most Practice", plan["focus_subject"]["name"], f"{plan['focus_subject']['marks']}% (Focus here)")

        c_s1, c_s2 = st.columns([1.3, 1.0])
        with c_s1:
            ui.show_chart(charts.fig_subject_marks(grades), "student_subjects")
        with c_s2:
            st.markdown("#### Subject Recommendations")
            for sub_rec in plan["subject_insights"][:4]:
                st.markdown(f"**{sub_rec['subject']}** ({sub_rec['marks']}% — {sub_rec['status']})")
                st.caption(sub_rec["recommendation"])

    # =========================================================================
    # SECTION 4: Marks Distribution
    # =========================================================================
    st.markdown("---")
    st.markdown("## Marks Distribution")
    st.markdown(
        "See where your marks stand across clear, friendly levels: "
        "**Excellent (75–100%)**, **Good (50–74%)**, and **Needs Practice (0–49%)**."
    )
    dist_res = ds.get_marks_distribution_analysis(department=student["department"], student_id=None, pass_mark=50.0, db_path=db_path, user=user)
    if dist_res["has_data"]:
        d_kpi1, d_kpi2, d_kpi3, d_kpi4 = st.columns(4)
        d_stats = dist_res["stats"]
        d_kpi1.metric("Class Average", f"{d_stats['mean']:.1f}%")
        d_kpi2.metric("Middle Mark (Median)", f"{d_stats['median']:.1f}%")
        d_kpi3.metric("Highest Mark", f"{d_stats['max']:.1f}%")
        d_kpi4.metric("Lowest Mark", f"{d_stats['min']:.1f}%")

        col_d1, col_d2 = st.columns([1.3, 1.0])
        with col_d1:
            fig_d = charts.fig_marks_histogram(dist_res["summary_df"])
            ui.show_chart(fig_d, "student_dist_chart")
        with col_d2:
            st.markdown("#### Score Levels")
            st.dataframe(dist_res["summary_df"][["Range", "Level", "Percentage %"]], hide_index=True, use_container_width=True)
    else:
        st.info("Marks distribution will appear once cohort marks are recorded.")

    # =========================================================================
    # SECTION 5: How Can I Improve My Marks?
    # =========================================================================
    st.markdown("---")
    st.markdown("## How Can I Improve My Marks?")
    st.markdown(
        "Here is your personalized roadmap answering: "
        "**What needs improvement?**, **Why does it matter?**, and **What should I do next?**"
    )

    action_cols = st.columns(len(plan["action_items"])) if plan["action_items"] else [st.container()]
    for idx, act in enumerate(plan["action_items"]):
        with action_cols[idx]:
            with st.container(border=True):
                st.markdown(f"#### {act['title']}")
                st.markdown(f"**What needs improvement?**<br>{act['what']}", unsafe_allow_html=True)
                st.markdown(f"**Why does it matter?**<br>{act['why']}", unsafe_allow_html=True)
                st.markdown(
                    f"<div style='background: rgba(0, 229, 255, 0.08); border-left: 3px solid #00E5FF; padding: 8px 12px; border-radius: 6px; margin-top: 8px;'>"
                    f"<strong style='color: #00E5FF;'>What should I do next?</strong><br>{act['next_step']}</div>",
                    unsafe_allow_html=True
                )

    st.write("")
    c_rev1, c_rev2 = st.columns(2)
    with c_rev1:
        with st.container(border=True):
            st.markdown("### Specific Topics to Practice First")
            if plan["weak_topics"]:
                st.caption("Based on actual assessment questions where you scored below 60%:")
                for wt in plan["weak_topics"]:
                    st.markdown(
                        f"- **{wt['topic']}** ({wt['cognitive_level']}): "
                        f"Scored {wt['marks_obtained']}/{wt['max_marks']} ({wt['pct']}%) — review notes on this concept."
                    )
            else:
                if plan["cog_has_data"]:
                    st.success("Great job! You scored 60% or higher on all tested assessment topics.")
                else:
                    st.info("Topic-level breakdown will appear once question scores are entered for your class assessments.")

    with c_rev2:
        with st.container(border=True):
            st.markdown("### Practice Suggestions for K1, K2, and K3")
            st.markdown(
                """
                - **K1 — Remember (Facts & Definitions):** Spend 10 minutes testing yourself on key formulas and definitions using flashcards.
                - **K2 — Understand (Explain Concepts):** Try explaining each topic to a study buddy or writing a summary in your own words.
                - **K3 — Apply (Solve Problems):** Practice 2 multi-step worked examples without looking at the solution guide first.
                """
            )

    # Realistic Achievable Daily Study Plan
    st.write("")
    with st.expander("My Realistic Daily Study Plan (Small, Achievable Steps)", expanded=True):
        st.caption("Consistency beats cramming. Follow these 20 to 35-minute daily focus sessions:")
        dp_cols = st.columns(3)
        for i, item in enumerate(plan["daily_plan"]):
            col_idx = i % 3
            with dp_cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"**{item['day']}** ({item['time']})")
                    st.write(item["task"])

    # =========================================================================
    # SECTION 6: Marks Target Calculator
    # =========================================================================
    st.markdown("---")
    st.markdown("## Marks Target Calculator")
    st.markdown("Calculate exactly what score you need on upcoming tests to reach your target semester grade.")

    with st.container(border=True):
        tc1, tc2, tc3 = st.columns(3)
        curr_score = float(student["academic_score"] or 65.0)
        tc1.metric("Current Coursework Average", f"{curr_score:.1f}%")
        target_goal = tc2.slider("Desired Final Grade (%)", min_value=50, max_value=95, value=75, step=5, key="calc_target_goal")
        exam_weight = tc3.slider("Final Exam Weight (%)", min_value=20, max_value=60, value=40, step=5, key="calc_exam_weight") / 100.0

        needed = (target_goal - (curr_score * (1.0 - exam_weight))) / exam_weight
        needed = round(needed, 1)

        if needed <= 0:
            st.success(f"You have already secured enough marks to meet your target of {target_goal}%!")
        elif needed > 100:
            st.warning(f"To reach {target_goal}%, you would need {needed}% on the final exam. Consider setting a milestone target of {int(curr_score + 5)}% first.")
        else:
            st.info(f"Target Requirement: You need **{needed}%** on the upcoming exam (weight {int(exam_weight*100)}%) to achieve an overall grade of **{target_goal}%**.")
