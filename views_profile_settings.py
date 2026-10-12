"""My Profile & Settings: Staff and Admin user settings, profile updates, and preferences."""
import streamlit as st

import auth
import components as ui
import data_service as ds


def render(db_path=None, user=None):
    ds.require_role(user, ("admin", "staff", "student"))
    role = user.get("role")
    ui.page_header(
        "My Profile & Settings",
        f"Manage your account details, password, and workspace preferences.",
        page_help="Update your display name, contact email, sign-in password, or preferences."
    )

    if role == "student":
        tab_profile, tab_pwd = st.tabs(["My Profile", "Change Password"])
    else:
        tab_profile, tab_prefs, tab_pwd = st.tabs(["My Profile", "Workspace Preferences", "Change Password"])

    with tab_profile:
        st.markdown("### Profile Information")
        with st.form("edit_profile_form"):
            c1, c2 = st.columns(2)
            dname = c1.text_input("Display Name *", value=user.get("display_name", ""),
                                  help="Your full display name")
            email = c2.text_input("Email Address", value=user.get("email") or "",
                                  help="Notification or contact email")
            dept = None
            if role in ("admin", "staff"):
                dept = st.text_input("Department / Subject Area", value=user.get("staff_department") or "",
                                     help="Your faculty department affiliation")
            elif user.get("student_id"):
                st.info(f"Linked Student ID: **{user.get('student_id')}**")
            st.caption(f"Username: `{user.get('username')}` &nbsp;|&nbsp; Role: `{user.get('role')}`")
            submitted = st.form_submit_button("Save Profile Changes", help="Update your account details")
        if submitted:
            ok, errs = auth.update_profile(user["id"], dname, email, dept, db_path=db_path)
            if ok:
                user["display_name"] = dname
                user["email"] = email
                user["staff_department"] = dept
                st.session_state["user"] = user
                ui.flash("Profile details updated successfully.")
                st.rerun()
            else:
                ui.show_errors(errs)

    if role in ("admin", "staff"):
        with tab_prefs:
            st.markdown("### Workspace Preferences")
            prefs = auth.get_preferences(user["id"], db_path=db_path)
            all_students = ds.get_screened_df(db_path, user=user)
            existing_depts = sorted(all_students["department"].dropna().unique()) if not all_students.empty else []
            dept_options = ["None (Show all)"] + list(existing_depts)
            cur_dept = prefs.get("default_department")
            dept_idx = dept_options.index(cur_dept) if cur_dept in dept_options else 0

            page_options = ["My Dashboard", "Start here", "Overview Dashboard", "Students Needing Support", "Student Directory"]
            cur_page = prefs.get("default_page")
            page_idx = page_options.index(cur_page) if cur_page in page_options else 0

            with st.form("edit_staff_prefs_form"):
                chosen_dept = st.selectbox(
                    "Default Department Filter",
                    dept_options,
                    index=dept_idx,
                    help="Automatically pre-select this department when viewing student rosters"
                )
                chosen_page = st.selectbox(
                    "Default Landing Page after Login",
                    page_options,
                    index=page_idx,
                    help="The page Learnlytics AI opens immediately after you sign in"
                )
                saved_pref = st.form_submit_button("Save Preferences", help="Save workspace defaults")
            if saved_pref:
                save_dept = None if chosen_dept == "None (Show all)" else chosen_dept
                auth.save_preferences(user["id"], default_department=save_dept, default_page=chosen_page, db_path=db_path)
                ui.flash("Workspace preferences saved successfully.")
                st.rerun()

    with tab_pwd:
        st.markdown("### Change Password")
        with st.form("change_staff_pwd_form"):
            old_pwd = st.text_input("Current Password", type="password", help="Verify your existing password")
            new_pwd = st.text_input("New Password (min 8 characters)", type="password", help="Choose a strong new password")
            confirm_pwd = st.text_input("Confirm New Password", type="password", help="Re-enter your new password")
            pwd_btn = st.form_submit_button("Update Password", help="Save your new password")
        if pwd_btn:
            if new_pwd != confirm_pwd:
                st.error("New password and confirmation do not match.")
            else:
                ok, errs = auth.change_password(user["id"], old_pwd, new_pwd, db_path=db_path)
                if ok:
                    user["must_change_password"] = 0
                    st.session_state["user"] = user
                    ui.flash("Password changed successfully.")
                    st.rerun()
                else:
                    ui.show_errors(errs)
