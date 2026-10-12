"""Reports and Exports. Every download reflects the filters chosen on this page."""
import datetime as dt

import streamlit as st

import components as ui
import data_service as ds


def render(db_path=None, user=None):
    if user:
        ds.require_role(user, ("admin", "staff"))
    ui.page_header(
        "Reports & Exports",
        "Download spreadsheets and summary reports reflecting your current filters.",
        page_help="Export student lists, support evidence, department comparisons, and executive summaries to CSV or text files."
    )
    df = ds.get_screened_df(db_path, user=user)

    if df.empty:
        st.info("**No student records found.** Add students in the **Student Directory** or import a CSV in **Import & Settings** to generate reports.")
        return
    fdf = ui.filter_bar(df, "rep")
    if fdf.empty:
        st.warning("No students match the selected filters. Please adjust the filters above to include students in the export.")
        return
    st.caption(f"{len(fdf)} student record(s) included in export. Email addresses are omitted for privacy.")
    stamp = dt.date.today().isoformat()
    ids = list(fdf["student_id"])
    interventions = ds.list_interventions_df(db_path=db_path)
    interventions = interventions[interventions["student_id"].isin(ids)]
    cfg = ds.get_config(db_path)

    exports = [
        ("Student Roster (CSV)", ds.roster_csv(fdf), f"learnlytics_roster_{stamp}.csv", "text/csv"),
        ("Support Level Report with Evidence (CSV)", ds.risk_report_csv(fdf), f"learnlytics_support_report_{stamp}.csv",
         "text/csv"),
        ("Department Summary (CSV)", ds.department_summary_csv(fdf), f"learnlytics_departments_{stamp}.csv",
         "text/csv"),
        ("Follow-Up Summary (CSV)", ds.intervention_summary_csv(ids, db_path),
         f"learnlytics_followups_{stamp}.csv", "text/csv"),
        ("Executive Summary (TXT)", ds.executive_summary_text(fdf, interventions, cfg),
         f"learnlytics_summary_{stamp}.txt", "text/plain"),
    ]
    for label, data, name, mime in exports:
        c1, c2 = st.columns([1, 3])
        with c1:
            st.download_button(f"⬇️ Download {label}", data=data, file_name=name, mime=mime,
                               key=f"dl_{name}", help=f"Download {label} file ({name})")
        with c2:
            st.caption(f"File: `{name}`")

    st.subheader("Executive Summary Preview")
    st.code(ds.executive_summary_text(fdf, interventions, cfg), language=None)

