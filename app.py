"""Learnlytics AI - entry point with secure role-based login and navigation.
Run with: streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Learnlytics AI", layout="wide")

import importlib  # noqa: E402
import auth  # noqa: E402
import components as ui  # noqa: E402
importlib.reload(ui)
import database  # noqa: E402
import data_service as ds  # noqa: E402
import views_ai_tutor  # noqa: E402
import views_analytics  # noqa: E402
import views_dashboard  # noqa: E402
import views_directory  # noqa: E402
import views_early_warning  # noqa: E402
import views_manage_accounts  # noqa: E402
import views_my_dashboard  # noqa: E402
import views_my_goals  # noqa: E402
import views_my_progress  # noqa: E402
import views_profile_settings  # noqa: E402
import views_recommendations  # noqa: E402
import views_reports  # noqa: E402
import views_settings  # noqa: E402
import views_start_here  # noqa: E402

# Role-based page registries
ADMIN_PAGES = {
    "Start here": views_start_here.render,
    "My Dashboard": views_my_dashboard.render,
    "Overview Dashboard": views_dashboard.render,
    "Students Needing Support": views_early_warning.render,
    "Student Directory": views_directory.render,
    "Recommendations": views_recommendations.render,
    "Analytics": views_analytics.render,
    "Reports & Exports": views_reports.render,
    "Import & Settings": views_settings.render,
    "Manage Accounts": views_manage_accounts.render,
    "My Profile & Settings": views_profile_settings.render,
}

STAFF_PAGES = {
    "Start here": views_start_here.render,
    "My Dashboard": views_my_dashboard.render,
    "Overview Dashboard": views_dashboard.render,
    "Students Needing Support": views_early_warning.render,
    "Student Directory": views_directory.render,
    "Recommendations": views_recommendations.render,
    "Analytics": views_analytics.render,
    "Reports & Exports": views_reports.render,
    "Import & Settings": views_settings.render,
    "My Profile & Settings": views_profile_settings.render,
}

STUDENT_PAGES = {
    "My Progress": views_my_progress.render,
    "AI Tutor": views_ai_tutor.render,
    "My Goals": views_my_goals.render,
    "My Profile & Settings": views_profile_settings.render,
}


@st.cache_resource
def _init_database():
    """Create tables, seed synthetic demo data once, and seed demo accounts if DEMO_MODE=1."""
    res = database.init_db()
    auth.seed_demo_users_if_needed()
    return res


def _render_first_run_admin_setup():
    """Shown on first run when no users exist in the database."""
    # Ensure sidebar has consistent branding
    ui.sidebar_logo()
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        ui.render_logo(width=220, target=st)
        with st.container(border=True):
            st.markdown("## Welcome to Learnlytics AI")
            st.markdown("### Create the First Administrator Account")
            st.write(
                "No user accounts exist in the database yet. Please set up the primary administrative account "
                "to manage staff, students, and academic data."
            )
            with st.form("first_run_admin_form"):
                uname = st.text_input("Admin Username *", placeholder="e.g. coordinator_admin")
                dname = st.text_input("Full Display Name *", placeholder="e.g. Dr. Jane Smith")
                email = st.text_input("Email Address (optional)", placeholder="jane.smith@institution.edu")
                pwd = st.text_input("Password * (minimum 8 characters)", type="password")
                confirm = st.text_input("Confirm Password *", type="password")
                submitted = st.form_submit_button("Create Administrator Account")

            if submitted:
                if pwd != confirm:
                    st.error("Passwords do not match. Please verify and try again.")
                else:
                    new_u, errs = auth.create_user(
                        username=uname,
                        password=pwd,
                        role="admin",
                        display_name=dname,
                        email=email,
                        must_change_password=False,
                    )
                    if new_u:
                        st.session_state["user"] = None
                        ui.flash("Administrator account created successfully. You can now sign in using the Coordinator Admin tab.")
                        st.rerun()
                    else:
                        ui.show_errors(errs)

            if auth.count_users() > 0:
                if st.button("Already have an account? Go to Login", key="btn_goto_login"):
                    st.session_state["force_login"] = True
                    st.rerun()


def _render_force_password_change(user):
    """Forced password change screen when must_change_password is true."""
    ui.sidebar_logo()
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        ui.render_logo(width=220, target=st)
        with st.container(border=True):
            st.markdown("### Password Change Required")
            st.write(
                f"Hello **{user.get('display_name')}**, you are using a temporary or administrator-reset password. "
                f"Please set a new private password to continue."
            )
            with st.form("force_password_change_form"):
                cur_pwd = st.text_input("Current Temporary Password *", type="password")
                new_pwd = st.text_input("New Password * (min 8 characters)", type="password")
                confirm_pwd = st.text_input("Confirm New Password *", type="password")
                submitted = st.form_submit_button("Save New Password & Continue")

            if submitted:
                if new_pwd != confirm_pwd:
                    st.error("New password and confirmation do not match.")
                else:
                    ok, errs = auth.change_password(user["id"], cur_pwd, new_pwd)
                    if ok:
                        user["must_change_password"] = 0
                        st.session_state["user"] = user
                        ui.flash("Password updated successfully. Welcome to your workspace.")
                        st.rerun()
                    else:
                        ui.show_errors(errs)


def _render_login_page():
    """Render the login screen with separate Student Login and Staff Login options, plus secure Admin access."""
    # Render clean branding in sidebar
    ui.sidebar_logo()
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        ui.render_logo(width=220, target=st)
        if auth.is_demo_mode():
            st.info("Demo mode active: Demo accounts are enabled. Generated credentials are listed in the server logs or environment variables.")

        with st.container(border=True):
            st.markdown("## Sign In to Learnlytics AI")
            st.caption("AI-Powered Student Analytics, Explainable Early-Warning & Success Platform.")

            # Segmented / Radio selector for the two primary login experiences
            login_mode = st.radio(
                "Select Login Type",
                ["Student Login", "Staff Login"],
                horizontal=True,
                key="login_mode_selector",
                label_visibility="collapsed"
            )

            # Option 1: Student Login (Student ID + Password)
            if login_mode == "Student Login":
                st.markdown("##### Student Login")
                st.caption("Enter your Student ID (or username) and password to view your academic records.")
                show_pwd_stu = st.checkbox("Show password", key="chk_show_pwd_stu")
                with st.form("student_login_form"):
                    stu_id = st.text_input("Student ID *", key="stu_id_input", placeholder="e.g. STU101 or DEMO001")
                    stu_pwd = st.text_input("Password *", type="text" if show_pwd_stu else "password", key="stu_pwd_input", placeholder="Enter your password")
                    stu_submit = st.form_submit_button("Sign In to Student Portal", use_container_width=True)

                if stu_submit:
                    if not stu_id.strip() or not stu_pwd:
                        st.error("Please enter both your Student ID and password.")
                    else:
                        user, err = auth.authenticate(stu_id.strip(), stu_pwd)
                        if user:
                            if user.get("role") != "student":
                                st.error("This account is not a student account. Please select Staff Login.")
                            else:
                                st.session_state["user"] = user
                                st.session_state["nav_page"] = "My Progress"
                                ui.flash(f"Welcome back, {user['display_name']}!")
                                st.rerun()
                        else:
                            st.error(f"{err}")

            # Option 2: Staff Login (Staff ID + Password)
            elif login_mode == "Staff Login":
                st.markdown("##### Staff Login")
                st.caption("Enter your Staff ID (or username) and password to access student cohorts.")
                show_pwd_staff = st.checkbox("Show password", key="chk_show_pwd_staff")
                with st.form("staff_login_form"):
                    staff_id = st.text_input("Staff ID / Username *", key="staff_id_input", placeholder="e.g. demo_staff or faculty ID")
                    staff_pwd = st.text_input("Password *", type="text" if show_pwd_staff else "password", key="staff_pwd_input", placeholder="Enter your password")
                    staff_submit = st.form_submit_button("Sign In to Staff Portal", use_container_width=True)

                if staff_submit:
                    if not staff_id.strip() or not staff_pwd:
                        st.error("Please enter both your Staff ID and password.")
                    else:
                        user, err = auth.authenticate(staff_id.strip(), staff_pwd)
                        if user:
                            if user.get("role") not in ("staff", "admin"):
                                st.error("This account does not have staff permissions. Please select Student Login.")
                            else:
                                st.session_state["user"] = user
                                prefs = auth.get_preferences(user["id"])
                                st.session_state["nav_page"] = prefs.get("default_page") or "My Dashboard"
                                ui.flash(f"Welcome back, {user['display_name']}!")
                                st.rerun()
                        else:
                            st.error(f"{err}")

            # Secure Coordinator / Admin Option (collapsible to keep student/staff view clean)
            with st.expander("Institutional Coordinator / Admin Access", expanded=False):
                st.caption("System administration, user account creation, and global configuration.")
                show_pwd_admin = st.checkbox("Show password", key="chk_show_pwd_admin")
                with st.form("admin_login_form"):
                    admin_uname = st.text_input("Admin Username *", key="admin_uname_input", placeholder="e.g. demo_admin")
                    admin_pwd = st.text_input("Password *", type="text" if show_pwd_admin else "password", key="admin_pwd_input", placeholder="Enter admin password")
                    admin_submit = st.form_submit_button("Sign In as Administrator", use_container_width=True)

                if admin_submit:
                    if not admin_uname.strip() or not admin_pwd:
                        st.error("Please enter both Admin username and password.")
                    else:
                        user, err = auth.authenticate(admin_uname.strip(), admin_pwd)
                        if user:
                            if user.get("role") != "admin":
                                st.error("Administrator privileges required.")
                            else:
                                st.session_state["user"] = user
                                prefs = auth.get_preferences(user["id"])
                                st.session_state["nav_page"] = prefs.get("default_page") or "Start here"
                                ui.flash(f"Welcome back, {user['display_name']}!")
                                st.rerun()
                        else:
                            st.error(f"{err}")

            st.caption("**Need an account or password reset?** Please contact your institutional coordinator.")


def main():
    ui.inject_css()
    try:
        _init_database()
    except database.DatabaseError as exc:
        st.error(f"The database could not be prepared: {exc}")
        st.stop()

    # Step 1: Check if any users exist in the database
    if auth.count_users() == 0:
        _render_first_run_admin_setup()
        return

    # Step 2: Check if user is logged in
    user = st.session_state.get("user")
    if not user:
        _render_login_page()
        return

    # Step 3: Check if password change is forced
    if user.get("must_change_password"):
        _render_force_password_change(user)
        return

    # Step 4: Render logged-in layout with sidebar
    role = user.get("role")
    if role == "admin":
        pages = ADMIN_PAGES
    elif role == "staff":
        pages = STAFF_PAGES
    elif role == "student":
        pages = STUDENT_PAGES
    else:
        st.error(f"Unrecognized user role: {role}")
        st.stop()

    # Sidebar Header & User Profile
    ui.sidebar_logo()
    st.sidebar.markdown(f"**{user.get('display_name')}**")
    role_badge = f"<span style='background:#102B4D; color:#00E5FF; border:1px solid rgba(0,229,255,0.40); box-shadow:0 0 10px rgba(0,229,255,0.20); padding:3px 10px; border-radius:12px; font-size:0.75rem; font-weight:700; letter-spacing:0.04em;'>{role.upper()}</span>"
    if auth.is_demo_mode():
        role_badge += " <span style='background:#102B4D; color:#FBBF24; border:1px solid rgba(251,191,36,0.40); box-shadow:0 0 10px rgba(251,191,36,0.20); padding:3px 10px; border-radius:12px; font-size:0.75rem; font-weight:700;'>DEMO MODE</span>"
    st.sidebar.markdown(role_badge, unsafe_allow_html=True)
    if user.get("student_id"):
        st.sidebar.caption(f"Student ID: `{user['student_id']}`")
    elif user.get("staff_department"):
        st.sidebar.caption(f"Dept: {user['staff_department']}")

    if st.sidebar.button("Log Out", key="btn_logout", help="Sign out and clear session"):
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()

    # Ensure selected page is valid for current role
    default_page = list(pages.keys())[0]
    if "nav_page" not in st.session_state or st.session_state["nav_page"] not in pages:
        st.session_state["nav_page"] = default_page

    choice = st.sidebar.radio("Navigate", list(pages.keys()), key="nav_page")
    st.sidebar.divider()
    st.sidebar.caption("Support flags are guidance indicators for human review, not automated predictions.")

    ui.render_flash()

    # Render selected page with logged-in user
    try:
        render_fn = pages[choice]
        # Call with user context
        render_fn(user=user)
    except database.DatabaseError as exc:
        st.error(f"Database problem: {exc}")
    except auth.AuthError as exc:
        st.error(f"Authentication error: {exc}")
    except ds.AuthorizationError as exc:
        st.error(f"Access Denied: {exc}")


main()
