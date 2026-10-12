"""Settings and Data Management: thresholds, CSV import, data quality, backup, demo reset."""
import streamlit as st

import components as ui
import data_service as ds
import database as db
import risk_engine as risk


def _thresholds_tab(db_path):
    cfg = ds.get_config(db_path)
    st.markdown("**How Learnlytics AI Evaluates Support Needs**")
    for line in risk.describe_scoring(cfg):
        st.write(f"- {line}")
    st.caption("ℹ️ Changes apply immediately across all pages. The score is a supportive guideline for human review, not an automated prediction.")
    with st.form("thresholds_form"):
        st.markdown("**Guideline thresholds (%)**")
        c1, c2, c3 = st.columns(3)
        att = c1.number_input("Attendance below (%)", 0.0, 100.0, float(cfg["attendance_threshold"]), 1.0,
                              help="Students with attendance below this percentage receive support points")
        score = c2.number_input("Academic score below (%)", 0.0, 100.0, float(cfg["score_threshold"]), 1.0,
                               help="Students with academic scores below this percentage receive support points")
        asg = c3.number_input("Assignment completion below (%)", 0.0, 100.0, float(cfg["assignment_threshold"]), 1.0,
                              help="Students with assignment rates below this percentage receive support points")
        st.markdown("**Points added when an indicator is triggered**")
        w1, w2, w3, w4 = st.columns(4)
        w_att = w1.number_input("Attendance points", 0, 100, int(cfg["attendance_weight"]), help="Points added for low attendance")
        w_score = w2.number_input("Score points", 0, 100, int(cfg["score_weight"]), help="Points added for low academic score")
        w_asg = w3.number_input("Assignments points", 0, 100, int(cfg["assignment_weight"]), help="Points added for low assignment completion")
        w_dec = w4.number_input("Score decline points", 0, 100, int(cfg["decline_weight"]), help="Points added for declining score history")
        st.markdown("**Trend rule**")
        d1, d2 = st.columns(2)
        drop = d1.number_input("Score drop (points) counting as decline", 1.0, 100.0,
                               float(cfg["decline_points"]), 1.0, help="Point drop between first and latest historical check")
        hist = d2.number_input("Minimum history records needed", 2, 52, int(cfg["min_history"]),
                               help="Minimum weekly performance records required to assess a trend")
        st.markdown("**Support Level Boundaries (minimum score)**")
        b1, b2, b3 = st.columns(3)
        med = b1.number_input("Some support needed from", 1, 100, int(cfg["medium_min"]), help="Minimum score for Some Support Needed")
        high = b2.number_input("Needs attention from", 1, 100, int(cfg["high_min"]), help="Minimum score for Needs Attention")
        crit = b3.number_input("Needs urgent support from", 1, 100, int(cfg["critical_min"]), help="Minimum score for Needs Urgent Support")
        saved = st.form_submit_button("Save thresholds", help="Save these custom screening parameters")
    if saved:
        new_cfg = {"attendance_threshold": att, "score_threshold": score, "assignment_threshold": asg,
                   "attendance_weight": w_att, "score_weight": w_score, "assignment_weight": w_asg,
                   "decline_weight": w_dec, "decline_points": drop, "min_history": hist,
                   "medium_min": med, "high_min": high, "critical_min": crit}
        ok, errors = ds.save_config(new_cfg, db_path)
        if ok:
            ui.flash("Screening thresholds saved successfully.")
            st.rerun()
        else:
            ui.show_errors(errors)
    if st.button("Restore default thresholds", key="cfg_reset", help="Reset all rules back to standard defaults"):
        ds.reset_config(db_path)
        ui.flash("Default screening thresholds restored.")
        st.rerun()


def _import_tab(db_path):
    # Prominent 3-line import guide and Download Sample CSV button
    with st.container(border=True):
        st.markdown("### How to Import Your Student Spreadsheet")
        st.markdown("""
1. **Download the sample CSV template** using the button below to see the required column format.
2. **Fill in your students' data** in Excel, Google Sheets, or any spreadsheet tool, and save it as a CSV.
3. **Upload the file below**, review the automatic preview of valid and rejected rows, and click **Import**.
        """)
        st.download_button(
            "Download Sample CSV Template",
            data=ds.sample_csv_text(),
            file_name="learnlytics_sample_students.csv",
            mime="text/csv",
            key="dl_template_top",
            help="Download a ready-to-fill CSV file with sample student data and column headers"
        )

    st.write("")
    mode_label = st.radio(
        "If a student ID already exists in the system:",
        ["Skip it and report a conflict (safe — never overwrites existing records)",
         "Update the existing record with new CSV values"],
        key="imp_mode",
        help="Choose whether to skip or update students who are already saved in the database"
    )
    mode = "update_existing" if mode_label.startswith("Update") else "skip_existing"
    upload = st.file_uploader("Upload Student CSV File", type=["csv"], key="imp_file",
                              help="Select your UTF-8 encoded .csv spreadsheet file")
    if upload is None:
        st.info("Ready to import? Upload a CSV spreadsheet above to see a preview of accepted rows and any errors before importing.")
        return
    data = upload.getvalue()
    check = ds.import_students_csv(data, mode, db_path, dry_run=True)
    if check["error"]:
        st.error(f"Could not process file: {check['error']}\n\n**How to fix:** Ensure the file is saved as a UTF-8 CSV and contains the required headers: student_id, name, department, semester, attendance_rate, academic_score, assignment_rate.")
        return
    acc, rej = check["accepted_df"], check["rejected_df"]
    c1, c2 = st.columns(2)
    c1.metric("Rows ready to import", len(acc))
    c2.metric("Rows with issues (rejected)", len(rej))
    if not acc.empty:
        st.markdown("**Preview of Accepted Rows**")
        ui.show_df(acc[["row", "student_id", "name", "department", "semester", "attendance_rate",
                        "academic_score", "assignment_rate", "action", "notes"]])
    if not rej.empty:
        st.markdown("**Rows with Issues (with instructions on how to fix)**")
        ui.show_df(rej)
    if len(acc) and st.button(f"Confirm & Import {len(acc)} Student(s)", key="imp_commit", help="Commit the valid rows to the database"):
        result = ds.import_students_csv(data, mode, db_path)
        rej_count = len(result['rejected_df'])
        rej_msg = f", {rej_count} row(s) skipped due to errors" if rej_count else ""
        ui.flash(f"Success: Import completed: {result['inserted']} new student(s) added, {result['updated']} existing record(s) updated{rej_msg}.")
        st.rerun()


def _quality_tab(db_path):
    st.write("Summary of records, data completeness, and missing values across all students.")
    ui.show_df(ds.data_quality_summary(db_path))


def _backup_tab(db_path):
    st.write("Download an offline copy of your entire database or export the student roster to CSV.")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download Database Backup (.db)", data=ds.export_backup_bytes(db_path),
                           file_name="learnlytics_backup.db", mime="application/octet-stream", key="dl_backup",
                           help="Download complete SQLite database file for offline backup")
    with c2:
        st.download_button("Download Student Roster (.csv)", data=ds.roster_csv(ds.get_screened_df(db_path)),
                           file_name="learnlytics_roster_backup.csv", mime="text/csv", key="dl_roster_backup",
                           help="Download student list as a spreadsheet")
    st.caption("If running on cloud platforms with temporary storage, downloading backups regularly ensures your data is preserved.")


def _reset_tab(db_path):
    st.warning("Warning: This option resets ONLY the synthetic demo students (DEMO001...) and their sample history. Any real students you created or imported will remain untouched.")
    confirm = st.checkbox("I understand and want to reload the synthetic demo records", key="reset_ack")
    typed = st.text_input("Type RESET below to confirm", key="reset_text", help="Type RESET in capital letters")
    if st.button("Reset demo records", disabled=not (confirm and typed.strip() == "RESET"), key="reset_btn",
                 help="Recreate synthetic demo students"):
        count = db.reset_demo_data(db_path)
        ui.flash(f"Demo data reset successfully: {count} synthetic students recreated.")
        st.rerun()


def render(db_path=None, user=None):
    ds.require_role(user, ("admin", "staff"))
    is_admin = user.get("role") == "admin" if user else True

    ui.page_header(
        "Import & Settings",
        "Import student spreadsheets, configure screening thresholds, inspect data quality, and create backups.",
        page_help="Teachers and coordinators can use this page to import classes via CSV, adjust academic guideline thresholds, or download data backups."
    )

    if is_admin:
        tabs = st.tabs(["Import CSV", "Screening Thresholds", "Data Quality", "Backup & Export", "Reset Demo Data"])
        with tabs[0]:
            _import_tab(db_path)
        with tabs[1]:
            _thresholds_tab(db_path)
        with tabs[2]:
            _quality_tab(db_path)
        with tabs[3]:
            _backup_tab(db_path)
        with tabs[4]:
            _reset_tab(db_path)
    else:
        # Staff role: access Import CSV and Data Quality; thresholds/backups/reset are admin only
        tabs = st.tabs(["Import CSV", "Data Quality"])
        with tabs[0]:
            _import_tab(db_path)
        with tabs[1]:
            _quality_tab(db_path)
        st.caption("Note: Screening thresholds, database backups, and demo-data reset are managed by system administrators.")


