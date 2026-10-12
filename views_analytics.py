"""Academic Analytics page and chart builders for Learnlytics AI.

Provides comprehensive academic analytics:
1. Cognitive Level Analysis (K1-K3: Remember, Understand, Apply)
2. Subject Performance Analysis
3. Marks Distribution Analysis
4. Cohort Overview & Department Relations
5. Historical Trends Over Time
"""
import datetime as dt
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

import components as ui
import data_service as ds
import risk_engine as risk

LABELS = {
    "academic_score": "Academic score (%)",
    "attendance_rate": "Attendance (%)",
    "assignment_rate": "Assignment completion (%)"
}

# Electric Blue & Neon Cyan Theme Palette
COLOR_CYAN = "#00E5FF"
COLOR_ELECTRIC_BLUE = "#00A6FF"
COLOR_SKY = "#38BDF8"
COLOR_MUTED_BLUE = "#1E40AF"
COLOR_ALERT = "#F43F5E"
COLOR_WARN = "#F59E0B"
COLOR_SUCCESS = "#10B981"


def fig_cognitive_levels(summary_df):
    """Bar chart comparing performance percentage across K1, K2, and K3 cognitive levels."""
    if summary_df.empty or "Performance %" not in summary_df.columns:
        return None
    
    # Check if there are valid numbers
    valid = summary_df.dropna(subset=["Performance %"])
    if valid.empty:
        return None

    colors = {
        "K1": COLOR_CYAN,          # Remember (Cyan)
        "K2": COLOR_ELECTRIC_BLUE,  # Understand (Electric Blue)
        "K3": COLOR_SKY            # Apply (Sky Blue)
    }
    
    fig = go.Figure()
    for _, row in summary_df.iterrows():
        lvl = row["Level"]
        val = row["Performance %"]
        desc = row["Descriptor"]
        bar_color = colors.get(lvl, COLOR_ELECTRIC_BLUE)
        y_val = [val if val is not None else 0]
        
        fig.add_trace(go.Bar(
            x=[f"{lvl} ({desc})"],
            y=y_val,
            name=f"{lvl} - {desc}",
            marker=dict(
                color=bar_color,
                line=dict(color="rgba(255, 255, 255, 0.2)", width=1)
            ),
            text=[f"{val:.1f}%" if val is not None else "N/A"],
            textposition="auto",
            hovertemplate=(
                f"<b>{lvl} - {desc}</b><br>"
                f"Performance: %{{y:.1f}}%<br>"
                f"Questions: {row.get('Questions', 0)}<br>"
                f"Records: {row.get('Records Assessed', 0)}<extra></extra>"
            )
        ))
        
    fig.update_layout(
        title="Performance Across Cognitive Levels (K1–K3)",
        yaxis=dict(title="Average Performance (%)", range=[0, 100]),
        xaxis=dict(title="Cognitive Domain Level"),
        showlegend=False,
        bargap=0.35,
        margin=dict(t=40, b=20, l=40, r=20)
    )
    return fig


def fig_subject_comparison(subj_df, pass_mark=50.0):
    """Comparison bar chart of average marks and pass percentage across subjects."""
    if subj_df.empty or "Subject" not in subj_df.columns:
        return None
    
    fig = go.Figure()
    
    # Sort for clear visual hierarchy
    sorted_df = subj_df.sort_values(by="Average %", ascending=True)
    
    bar_colors = [
        COLOR_ALERT if row["Average %"] < pass_mark else COLOR_ELECTRIC_BLUE
        for _, row in sorted_df.iterrows()
    ]
    
    fig.add_trace(go.Bar(
        x=sorted_df["Average %"],
        y=sorted_df["Subject"],
        orientation="h",
        name="Average Score (%)",
        marker=dict(
            color=bar_colors,
            line=dict(color="rgba(255, 255, 255, 0.15)", width=1)
        ),
        text=[f"{v:.1f}%" for v in sorted_df["Average %"]],
        textposition="auto",
        hovertemplate="<b>%{y}</b><br>Average: %{x:.1f}%<extra></extra>"
    ))
    
    # Pass threshold vertical reference line
    fig.add_vline(
        x=pass_mark,
        line_dash="dash",
        line_color=COLOR_CYAN,
        annotation_text=f"Pass Threshold ({pass_mark:.0f}%)",
        annotation_position="top right",
        annotation_font=dict(color=COLOR_CYAN, size=11)
    )
    
    fig.update_layout(
        title="Subject Performance Comparison",
        xaxis=dict(title="Average Performance (%)", range=[0, 100]),
        yaxis=dict(title="Subject"),
        margin=dict(t=40, b=20, l=120, r=20),
        height=max(360, len(sorted_df) * 32)
    )
    return fig


def fig_marks_histogram(dist_df, stats=None):
    """Bar chart displaying distribution across score brackets."""
    if dist_df.empty or "Range" not in dist_df.columns:
        return None
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=dist_df["Range"],
        y=dist_df["Student Count"],
        name="Students",
        marker=dict(
            color=COLOR_CYAN,
            line=dict(color="rgba(0, 166, 255, 0.5)", width=1.5)
        ),
        text=[f"{c} ({p:.1f}%)" for c, p in zip(dist_df["Student Count"], dist_df["Percentage %"])],
        textposition="outside",
        hovertemplate="<b>Bracket: %{x}</b><br>Count: %{y} students<extra></extra>"
    ))
    
    fig.update_layout(
        title="Score Frequency Distribution",
        xaxis=dict(title="Score Brackets (%)"),
        yaxis=dict(title="Number of Students"),
        margin=dict(t=40, b=20, l=40, r=20),
        bargap=0.2
    )
    return fig


def _hist(df, column, color):
    data = df.dropna(subset=[column])
    if data.empty:
        return None
    fig = px.histogram(data, x=column, nbins=10, labels=LABELS, color_discrete_sequence=[color])
    fig.update_layout(yaxis_title="Students", bargap=0.06, margin=dict(t=30, b=10))
    fig.update_xaxes(range=[0, 100])
    return fig


def fig_score_hist(df):
    return _hist(df, "academic_score", COLOR_ELECTRIC_BLUE)


def fig_attendance_hist(df):
    return _hist(df, "attendance_rate", COLOR_CYAN)


def fig_assignment_hist(df):
    return _hist(df, "assignment_rate", COLOR_SKY)


def fig_risk_distribution(df):
    if df.empty:
        return None
    counts = df["risk_category"].value_counts().reindex(risk.ALL_CATEGORIES, fill_value=0).reset_index()
    counts.columns = ["Category", "Students"]
    fig = px.bar(counts, x="Category", y="Students", color="Category",
                 color_discrete_map=ui.RISK_COLORS, category_orders={"Category": risk.ALL_CATEGORIES})
    fig.update_layout(showlegend=False, margin=dict(t=30, b=10))
    return fig


def fig_scatter(df):
    data = df.dropna(subset=["attendance_rate", "academic_score"])
    if data.empty:
        return None
    fig = px.scatter(data, x="attendance_rate", y="academic_score", color="risk_category",
                     color_discrete_map=ui.RISK_COLORS, hover_data=["student_id", "name", "department"],
                     labels={**LABELS, "risk_category": "Support category"})
    fig.update_layout(margin=dict(t=30, b=10))
    return fig


def fig_department_comparison(df):
    summary = ds.department_summary_df(df)
    if summary.empty:
        return None
    long = summary.melt(id_vars="Department",
                        value_vars=["Avg attendance %", "Avg score %", "Avg assignment %"],
                        var_name="Metric", value_name="Percent")
    dept_colors = {
        "Avg attendance %": COLOR_CYAN,
        "Avg score %": COLOR_ELECTRIC_BLUE,
        "Avg assignment %": COLOR_SKY,
    }
    fig = px.bar(long, x="Department", y="Percent", color="Metric", barmode="group",
                 color_discrete_map=dept_colors)
    fig.update_layout(yaxis_range=[0, 100], margin=dict(t=30, b=10))
    return fig


def fig_weekly_trend(history_df):
    """Average weekly metrics - only where real history exists."""
    if history_df.empty:
        return None
    weekly = history_df.groupby("week_date")[["attendance_rate", "academic_score", "assignment_rate"]].mean()
    weekly = weekly.reset_index().melt(id_vars="week_date", var_name="Metric", value_name="Average %")
    weekly["Metric"] = weekly["Metric"].map(LABELS)
    trend_colors = {
        LABELS["attendance_rate"]: COLOR_CYAN,
        LABELS["academic_score"]: COLOR_ELECTRIC_BLUE,
        LABELS["assignment_rate"]: COLOR_SKY,
    }
    fig = px.line(weekly, x="week_date", y="Average %", color="Metric", markers=True,
                  color_discrete_map=trend_colors, labels={"week_date": "Week"})
    fig.update_layout(yaxis_range=[0, 100], margin=dict(t=30, b=10))
    return fig


def fig_student_trend(history_df):
    if len(history_df) < 2:
        return None
    return fig_weekly_trend(history_df)


def fig_subject_marks(grades_df):
    if grades_df.empty:
        return None
    fig = px.bar(grades_df, x="Subject", y="Marks", color_discrete_sequence=[COLOR_CYAN])
    fig.update_layout(yaxis_range=[0, 100], margin=dict(t=30, b=10))
    return fig


# --------------------------------------------------------------------------
# Section Renderers
# --------------------------------------------------------------------------

def _render_cognitive_analysis(df_screened, db_path=None, user=None):
    """Section 1: K1, K2, K3 Cognitive-Level Analysis."""
    st.markdown("### Cognitive Level Analysis (K1–K3)")
    st.markdown(
        "See how well students perform across three simple learning levels:<br>"
        "• **K1 — Remember:** Can students recall the facts and definitions?<br>"
        "• **K2 — Understand:** Can students explain the concepts in their own words?<br>"
        "• **K3 — Apply:** Can students use what they learned to solve real problems?",
        unsafe_allow_html=True
    )

    # Filtering bar
    c1, c2, c3 = st.columns([1.5, 1.5, 1.5])
    
    # Subject list
    assessments_list = ds.list_assessments(db_path=db_path)
    subjects_available = sorted(list({a["subject"] for a in assessments_list})) if assessments_list else []
    all_subjects = ["All subjects"] + subjects_available
    
    with c1:
        selected_subject = st.selectbox(
            "Subject", all_subjects, key="cog_subj_filter",
            help="Filter cognitive analytics by subject"
        )
        
    filtered_asm = ds.list_assessments(
        subject=selected_subject if selected_subject != "All subjects" else None,
        db_path=db_path
    )
    
    asm_options = {0: "All assessments"}
    for a in filtered_asm:
        asm_options[a["id"]] = f"{a['title']} ({a['assessment_date']})"
        
    with c2:
        selected_asm_id = st.selectbox(
            "Assessment", list(asm_options.keys()),
            format_func=lambda x: asm_options[x],
            key="cog_asm_filter",
            help="Select a specific assessment"
        )
        
    # Student filter if user is staff/admin
    selected_student_id = None
    with c3:
        if user and user.get("role") == "student":
            selected_student_id = user.get("student_id")
            st.text_input("Student", value=f"{selected_student_id} (You)", disabled=True)
        else:
            student_choices = ["All students"] + sorted(list(df_screened["student_id"].unique()))
            chosen_s = st.selectbox("Student", student_choices, key="cog_stu_filter")
            if chosen_s != "All students":
                selected_student_id = chosen_s

    # Compute analysis
    asm_param = selected_asm_id if selected_asm_id != 0 else None
    subj_param = selected_subject if selected_subject != "All subjects" else None
    
    result = ds.get_cognitive_analysis(
        student_id=selected_student_id,
        subject=subj_param,
        assessment_id=asm_param,
        db_path=db_path,
        user=user
    )

    if not result["has_data"]:
        st.info(
            "**Data not available.** "
            "Question-level cognitive assessments (K1–K3) have not been recorded for this selection. "
            "Historical grades without cognitive tags cannot be assumed to represent K1/K2/K3 breakdown. "
            "You can record a new assessment using the form below."
        )
    else:
        summary_df = result["summary_df"]
        records_count = result["raw_records_count"]
        st.caption(f"Analysis computed from {records_count} question-level score records.")
        
        # Metric Cards for K1, K2, K3 answering: "What is your score at each level?"
        m1, m2, m3 = st.columns(3)
        cols_map = {"K1": m1, "K2": m2, "K3": m3}
        simple_labels = {
            "K1": "K1 — Remember (Facts)",
            "K2": "K2 — Understand (Concepts)",
            "K3": "K3 — Apply (Problems)"
        }
        for _, row in summary_df.iterrows():
            lvl = row["Level"]
            col = cols_map.get(lvl)
            if col:
                val = row["Performance %"]
                val_str = f"{val:.1f}%" if val is not None else "N/A"
                sub_status = "Going well" if val and val >= 70 else ("Needs practice" if val and val < 50 else "Steady")
                col.metric(
                    simple_labels.get(lvl, lvl),
                    val_str,
                    f"{sub_status} ({row['Questions']} questions)"
                )

        # Chart and Summary Table
        c_left, c_right = st.columns([1.3, 1.0])
        with c_left:
            chart = fig_cognitive_levels(summary_df)
            ui.show_chart(chart, "cog_chart", "No cognitive performance data.")
        with c_right:
            st.markdown("#### Performance Summary")
            display_cols = ["Level", "Descriptor", "Questions", "Avg Marks", "Performance %"]
            st.dataframe(summary_df[display_cols], hide_index=True, use_container_width=True)
            
        # Actionable insight answering: "Which level is going well?" and "Which level needs practice?"
        if result["lowest_level"]:
            low_lvl = result["lowest_level"]
            low_name = result["lowest_level_name"]
            best_row = summary_df.loc[summary_df["Performance %"].idxmax()]
            st.markdown(
                f"""
                <div style="background-color: #0B2342; border-left: 4px solid #00E5FF; padding: 14px 18px; border-radius: 8px; margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                        <div>
                            <span style="font-size: 0.85rem; text-transform: uppercase; color: #10B981; font-weight: 600;">Going Well</span><br>
                            <span style="color: #F1F7FF; font-size: 1rem; font-weight: bold;">{best_row['Level']} — {best_row['Descriptor']} ({best_row['Performance %']:.1f}%)</span>
                        </div>
                        <div>
                            <span style="font-size: 0.85rem; text-transform: uppercase; color: #00E5FF; font-weight: 600;">Needs More Practice</span><br>
                            <span style="color: #F1F7FF; font-size: 1rem; font-weight: bold;">{low_lvl} — {low_name}</span>
                        </div>
                    </div>
                    <div style="color: #A9BCD6; margin-top: 10px; font-size: 0.95rem;">
                        <strong style="color: #00E5FF;">Practical Next Step:</strong> {result['suggestion']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # Staff / Admin Assessment Entry Form to record new K1-K3 assessments
    if not user or user.get("role") in ("admin", "staff"):
        with st.expander("Record Assessment Questions & Cognitive Levels", expanded=False):
            st.markdown("##### Add New Assessment with K1, K2, K3 Mapping")
            st.caption("Record question items with explicit cognitive levels to build comprehensive analytics.")
            
            with st.form("form_create_assessment"):
                fa1, fa2, fa3 = st.columns([2, 1.5, 1])
                new_title = fa1.text_input("Assessment Title", placeholder="e.g. Midterm Test 1")
                dept_subjects = ["Mathematics", "Data Structures", "Algorithms", "Databases", "Operating Systems", "Electronics"]
                new_subject = fa2.selectbox("Subject", dept_subjects)
                new_pass = fa3.number_input("Pass Marks", min_value=1.0, max_value=100.0, value=50.0, step=5.0)
                
                st.markdown("###### Question Items")
                q_cols = st.columns(3)
                q1_lvl = q_cols[0].selectbox("Q1 Cognitive Level", ["K1", "K2", "K3"], index=0, key="q1_lvl", help="K1: Recall facts and definitions")
                q1_max = q_cols[0].number_input("Q1 Max Marks", min_value=1.0, value=10.0, step=1.0, key="q1_max")
                
                q2_lvl = q_cols[1].selectbox("Q2 Cognitive Level", ["K1", "K2", "K3"], index=1, key="q2_lvl", help="K2: Explain concepts")
                q2_max = q_cols[1].number_input("Q2 Max Marks", min_value=1.0, value=15.0, step=1.0, key="q2_max")
                
                q3_lvl = q_cols[2].selectbox("Q3 Cognitive Level", ["K1", "K2", "K3"], index=2, key="q3_lvl", help="K3: Solve problem sets")
                q3_max = q_cols[2].number_input("Q3 Max Marks", min_value=1.0, value=25.0, step=1.0, key="q3_max")

                submitted = st.form_submit_button("Save Assessment Structure")
                if submitted:
                    if not new_title.strip():
                        st.error("Please enter a valid title.")
                    else:
                        try:
                            asm_id = ds.create_assessment(new_title, new_subject, pass_marks=new_pass, db_path=db_path, user=user)
                            questions = [
                                {"question_number": 1, "cognitive_level": q1_lvl, "max_marks": q1_max, "topic": "Definitions and Rules"},
                                {"question_number": 2, "cognitive_level": q2_lvl, "max_marks": q2_max, "topic": "Concept Explanation"},
                                {"question_number": 3, "cognitive_level": q3_lvl, "max_marks": q3_max, "topic": "Problem Application"},
                            ]
                            ds.add_assessment_questions(asm_id, questions, db_path=db_path, user=user)
                            st.success(f"Assessment '{new_title}' created successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creating assessment: {e}")


def _render_subject_performance(df_screened, db_path=None, user=None):
    """Section 2: Subject Performance Analysis."""
    st.markdown("### Subject Performance Analysis")
    st.markdown(
        "See how students are doing in each subject. "
        "Find out which subject is strongest, which subject needs attention, and review the next steps to take."
    )

    # Configuration controls
    cf1, cf2, cf3 = st.columns([1.5, 1.5, 1.5])
    with cf1:
        departments = ["All departments"] + sorted(list(df_screened["department"].dropna().unique()))
        selected_dept = st.selectbox("Department Filter", departments, key="subj_dept_filter")
    with cf2:
        selected_student = None
        if user and user.get("role") == "student":
            selected_student = user.get("student_id")
            st.text_input("Student Filter", value=f"{selected_student} (You)", disabled=True)
        else:
            student_list = ["All students"] + sorted(list(df_screened["student_id"].unique()))
            chosen_stu = st.selectbox("Student Filter", student_list, key="subj_stu_filter")
            if chosen_stu != "All students":
                selected_student = chosen_stu
    with cf3:
        pass_threshold = st.slider(
            "Configurable Pass Mark (%)",
            min_value=35.0, max_value=75.0, value=50.0, step=5.0,
            help="Define the passing mark used to calculate pass rates and identify subjects needing attention"
        )

    # Compute Subject Performance
    result = ds.get_subject_performance_analysis(
        department=selected_dept if selected_dept != "All departments" else None,
        student_id=selected_student,
        pass_mark=pass_threshold,
        db_path=db_path,
        user=user
    )

    if not result["has_data"]:
        st.info("No subject marks available for the selected filters.")
        return

    summary_df = result["summary_df"]
    raw_count = result["raw_records_count"]
    needs_attention = result["needs_attention"]

    st.caption(f"Calculations derived from {raw_count} underlying subject grade records. Missing marks are omitted without assuming zero.")

    # KPI Summary Row: Answering simple questions
    k1, k2, k3, k4 = st.columns(4)
    overall_avg = round(summary_df["Average %"].mean(), 1)
    highest_subj = summary_df.loc[summary_df["Average %"].idxmax()]["Subject"]
    lowest_subj = summary_df.loc[summary_df["Average %"].idxmin()]["Subject"]
    attn_count = len(needs_attention)

    k1.metric("Subjects Analyzed", len(summary_df), "All tracked courses")
    k2.metric("Cohort Average", f"{overall_avg:.1f}%", "Overall mark")
    k3.metric("Strongest Subject", highest_subj, "Highest average mark")
    k4.metric("Needs Attention", f"{attn_count} Subject(s)", help=f"Average mark below {pass_threshold:.0f}%")

    if needs_attention:
        st.warning(
            f"**Subjects Needing Attention:** Average score is below {pass_threshold:.0f}% in: "
            + ", ".join([f"**{s}**" for s in needs_attention])
            + ". Consider organizing review sessions on core topics."
        )

    # Comparison Chart
    c_chart, c_table = st.columns([1.4, 1.2])
    with c_chart:
        fig_subj = fig_subject_comparison(summary_df, pass_mark=pass_threshold)
        ui.show_chart(fig_subj, "subj_comp_chart", "No subject comparison data.")
    with c_table:
        st.markdown("#### Subject Summary Table")
        display_tbl = summary_df[["Subject", "Records Assessed", "Average %", "Highest Mark", "Lowest Mark", "Pass %"]]
        st.dataframe(display_tbl, hide_index=True, use_container_width=True)

    # Student-Level Breakdown
    with st.expander("Student-Level Subject Breakdown", expanded=False):
        st.markdown("##### Detailed Records")
        detail_df = result["student_detail_df"]
        st.dataframe(
            detail_df[["student_id", "student_name", "department", "subject", "marks"]],
            hide_index=True,
            use_container_width=True
        )


def _render_marks_distribution(df_screened, db_path=None, user=None):
    """Section 3: Marks Distribution Analysis."""
    st.markdown("### Marks Distribution")
    st.markdown(
        "See how student marks are spread out across simple, clear levels: "
        "**Excellent (75–100%)**, **Good (50–74%)**, and **Needs Practice (0–49%)**. "
        "All scores are normalized to percentages so you can compare fairly."
    )

    # Filters
    d1, d2, d3, d4 = st.columns([1.5, 1.5, 1.2, 1.2])
    with d1:
        # Determine subjects from database
        with ds.db.transaction(db_path) as conn:
            subj_rows = conn.execute("SELECT DISTINCT subject FROM subject_grades ORDER BY subject").fetchall()
        subj_options = ["All subjects (Overall Academic Score)"] + [r["subject"] for r in subj_rows]
        chosen_subject_opt = st.selectbox("Subject Focus", subj_options, key="dist_subj_focus")
        chosen_subj = None if chosen_subject_opt.startswith("All subjects") else chosen_subject_opt

    with d2:
        depts = ["All departments"] + sorted(list(df_screened["department"].dropna().unique()))
        chosen_dept = st.selectbox("Department", depts, key="dist_dept_focus")

    with d3:
        pass_threshold = st.number_input(
            "Pass Mark (%)", min_value=30.0, max_value=80.0, value=50.0, step=5.0,
            key="dist_pass_mark"
        )

    with d4:
        bin_mode = st.selectbox("Score Brackets", ["Standard (10% Bands)", "Coarse (20% Bands)"], key="dist_bin_mode")

    if bin_mode == "Coarse (20% Bands)":
        custom_bins = [(0, 39), (40, 59), (60, 79), (80, 100)]
    else:
        custom_bins = [(0, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 89), (90, 100)]

    selected_student = None
    if user and user.get("role") == "student":
        selected_student = user.get("student_id")

    dist_result = ds.get_marks_distribution_analysis(
        subject=chosen_subj,
        department=chosen_dept if chosen_dept != "All departments" else None,
        student_id=selected_student,
        pass_mark=pass_threshold,
        custom_bins=custom_bins,
        db_path=db_path,
        user=user
    )

    if not dist_result["has_data"]:
        st.info("No mark records found matching the specified parameters.")
        return

    summary_df = dist_result["summary_df"]
    stats = dist_result["stats"]
    pf = dist_result["pass_fail"]

    # Statistical Overview Metrics answering clear questions
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric("Students Assessed", stats["count"])
    s2.metric("Average Mark", f"{stats['mean']:.1f}%")
    s3.metric("Middle Mark (Median)", f"{stats['median']:.1f}%")
    s4.metric("Spread (Std Dev)", f"{stats['std_dev']:.2f}")
    s5.metric("Highest Mark", f"{stats['max']:.1f}%")
    s6.metric("Lowest Mark", f"{stats['min']:.1f}%")

    # Chart & Distribution Details
    col_hist, col_pf = st.columns([1.5, 1.0])
    with col_hist:
        fig_dist = fig_marks_histogram(summary_df, stats=stats)
        ui.show_chart(fig_dist, "dist_hist_chart", "No distribution data available.")
        st.caption(dist_result["concentration_note"])

    with col_pf:
        st.markdown("#### Pass / Fail Summary")
        st.markdown(
            f"""
            <div style="background-color: #0B2342; border: 1px solid rgba(0, 229, 255, 0.2); border-radius: 10px; padding: 16px; margin-bottom: 12px;">
                <div style="font-size: 0.85rem; color: #A9BCD6; text-transform: uppercase;">Pass Mark: ≥ {pf['pass_mark']:.0f}%</div>
                <div style="display: flex; justify-content: space-between; margin-top: 10px;">
                    <div>
                        <div style="font-size: 1.3rem; font-weight: bold; color: #10B981;">{pf['passed_count']} Passed</div>
                        <div style="font-size: 0.85rem; color: #A9BCD6;">{pf['passed_pct']:.1f}% of cohort</div>
                    </div>
                    <div>
                        <div style="font-size: 1.3rem; font-weight: bold; color: #00E5FF;">{pf['failed_count']} Below Pass</div>
                        <div style="font-size: 0.85rem; color: #A9BCD6;">{pf['failed_pct']:.1f}% needing practice</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown("#### Score Levels Breakdown")
        display_tbl = summary_df[["Range", "Level", "Student Count", "Percentage %"]]
        st.dataframe(display_tbl, hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------
# Main Page Render
# --------------------------------------------------------------------------

def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Academic Analytics",
        "Interactive cognitive mastery, subject competencies, grade distributions, and historical trends.",
        page_help="Explore K1-K3 cognitive levels, subject performance benchmarks, score distributions, and department trends."
    )
    df = ds.get_screened_df(db_path, user=user)

    if df.empty:
        st.info("No student records yet. Add student records in the Student Directory or import your class roster in Settings to view analytics.")
        return
        
    fdf = ui.filter_bar(df, "an")
    if fdf.empty:
        st.warning("No students match the selected filters. Try adjusting the filters above.")
        return
        
    st.caption(f"Showing cohort analytics computed for {len(fdf)} student(s).")
    
    # 5 Organized Analytics Sections
    tab_cog, tab_subj, tab_dist, tab_dept, tab_hist = st.tabs([
        "Cognitive Levels (K1–K3)",
        "Subject Performance",
        "Marks Distribution",
        "Relationships & Departments",
        "Trends Over Time"
    ])
    
    with tab_cog:
        _render_cognitive_analysis(fdf, db_path=db_path, user=user)

    with tab_subj:
        _render_subject_performance(fdf, db_path=db_path, user=user)

    with tab_dist:
        _render_marks_distribution(fdf, db_path=db_path, user=user)

    with tab_dept:
        st.subheader("Attendance vs academic score")
        ui.show_chart(fig_scatter(fdf), "an_scatter", "Need students with both attendance and score recorded.")
        st.subheader("Department comparison")
        ui.show_chart(fig_department_comparison(fdf), "an_chart_dept")
        ui.show_df(ds.department_summary_df(fdf))

    with tab_hist:
        history = ds.get_history_df(list(fdf["student_id"]), db_path)
        if history.empty:
            st.info("No historical records exist for the selected students, so no trend is shown. "
                    "Trends appear only when weekly data has been recorded.")
        else:
            n = history["student_id"].nunique()
            st.caption(f"Weekly averages across {n} student(s) who have history records. "
                       f"Students without history are not included in this chart.")
            ui.show_chart(fig_weekly_trend(history), "an_trend")
